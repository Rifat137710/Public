"""
Closed-loop training environment for the V2G gap study.

What this changes relative to the paper's two-phase setup, and why:

  * Episode = ONE DAY (hours 06:00-23:00) driven by the daily load shape, with the
    peak multiplier sampled per episode. The paper samples the load multiplier
    i.i.d. per step from [0.1, 4.0], which leaves the MDP with no temporal
    structure -- intertemporal rationing is not representable there.
  * The EV fleet is IN THE TRAINING LOOP, so SOC depletes as the agent discharges.
    The paper applies the fleet only at deployment (Phase 2) via rho-clipping.
  * SOC, availability and hour-of-day are IN THE STATE, so the agent can condition
    on how much energy it has left and how much of the day remains.
  * The reward carries an explicit Ah-throughput (degradation) term. The paper's
    reward is purely voltage (Eqs. 8-10) and has no battery term at all.

Action modes:
  "direct"    p = a * P_rated                       (the paper's formulation, Eq. 7)
  "residual"  p = clip(droop_p + a * P_rated, ...)  (droop prior; a=0 reproduces droop
                                                     at each STEP -- note this is a
                                                     per-step floor, NOT a day-level
                                                     performance guarantee, since
                                                     discharging early leaves less later)

Reward:
    r = R_vb - R_vp - w_deg * (battery kWh this step) / (P_rated_total * dt)

w_deg is expressed on the same scale as the voltage penalty (~100 per p.u. of
deviation), so sweeping it from 0 upward traces the violation/wear trade-off
directly. Sweep it rather than guessing one value.
"""
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from v2g_sys import (CFG, Feeder, EVFleet, droop_pq, lam_profile,
                     reward_from_v, draw_availability)


class V2GDayEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, hub_buses, peak_range=(1.2, 3.3), mode="residual",
                 w_deg=0.0, control_mode="OFF", ev_in_loop=True,
                 reward_on="bus", iid_lambda=False, seed=0, cfg=CFG):
        super().__init__()
        self.cfg = cfg
        self.mode = mode
        self.w_deg = float(w_deg)
        self.peak_range = peak_range
        self.ev_in_loop = ev_in_loop
        self.reward_on = reward_on
        # iid_lambda=True reproduces the paper's Phase-1 training distribution: the load
        # multiplier is drawn i.i.d. per STEP from [0.1, 4.0], so the episode carries no
        # temporal structure. Training-only -- evaluation always uses the daily profile.
        self.iid_lambda = iid_lambda
        self.lam_iid_range = (0.1, 4.0)
        self.hours = cfg["active_hours"]
        self.rng = np.random.default_rng(seed)

        self.fd = Feeder(hub_buses, control_mode=control_mode)
        self.hubs = self.fd.hub_buses
        self.nh = len(self.hubs)
        self.fleets = {b: EVFleet(cfg) for b in self.hubs}

        n_obs = len(self.fd.buses) + 2 + 2 * self.nh
        self.observation_space = spaces.Box(-np.inf, np.inf, (n_obs,), np.float32)
        self.action_space = spaces.Box(-1.0, 1.0, (2 * self.nh,), np.float32)

        self.p_total = self.nh * cfg["P_rated"]
        self._t = 0
        self.peak = peak_range[0]

    # ------------------------------------------------------------------ #
    def _obs(self, vbus, lam):
        lam_norm = (lam - 0.1) / (4.0 - 0.1)
        hour_norm = self._t / max(1, len(self.hours) - 1)
        socs = [self.fleets[b].soc for b in self.hubs]
        navs = [self.fleets[b].n_avail(self.hours[min(self._t, len(self.hours) - 1)])
                / self.cfg["n_ev"] for b in self.hubs]
        return np.concatenate([vbus, [lam_norm, hour_norm], socs, navs]).astype(np.float32)

    def _lam_at(self, h):
        """Load multiplier for hour h. i.i.d. draw in paper-Phase-1 mode, else the profile."""
        if self.iid_lambda:
            return float(self.rng.uniform(*self.lam_iid_range))
        return float(lam_profile(self.peak)[h])

    def reset(self, *, seed=None, options=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        options = options or {}
        self.peak = float(options.get("peak",
                          self.rng.uniform(*self.peak_range)))
        avail_day = options.get("avail_day")
        soc0 = options.get("soc_init")
        for b in self.hubs:
            day = avail_day if avail_day is not None else draw_availability(
                self.rng, self.cfg["n_ev"])
            self.fleets[b].reset(n_avail_day=day, soc_init=soc0)
        self._t = 0
        lam0 = self._lam_at(self.hours[0])
        self.fd.set_load(lam0); self.fd.zero_hubs(); self.fd.solve()
        return self._obs(self.fd.bus_vpu(), lam0), {}

    # ------------------------------------------------------------------ #
    def _setpoint(self, b, i, a):
        P, Q = self.cfg["P_rated"], self.cfg["Q_rated"]
        if self.mode == "residual":
            v = self.fd.hub_vpu(b)
            p_d, q_d = droop_pq(v, P, Q)
            p = float(np.clip(p_d + a[2 * i] * P, -P, P))
            q = float(np.clip(q_d + a[2 * i + 1] * Q, -Q, Q))
        else:                                   # "direct" -- the paper's Eq. 7
            p = float(np.clip(a[2 * i] * P, -P, P))
            q = float(np.clip(a[2 * i + 1] * Q, -Q, Q))
        return p, q

    def step(self, action):
        h = self.hours[self._t]
        self.fd.set_load(self._lam_at(h)); self.fd.zero_hubs(); self.fd.solve()

        thru_before = sum(self.fleets[b].throughput for b in self.hubs)
        p_sup_total = 0.0
        p_batt_uncapped = 0.0
        for i, b in enumerate(self.hubs):
            p, q = self._setpoint(b, i, np.asarray(action, dtype=float))
            if self.ev_in_loop:
                p, q, _, _ = self.fleets[b].apply(p, q, h, commit=True)
            else:
                # fleet model disabled: no SOC/availability limit, but still account the
                # battery energy the command implies, so energy columns stay comparable.
                p_batt_uncapped += abs(p) / self.cfg["eta_inv"]
            self.fd.set_hub(b, p, q)
            p_sup_total += max(0.0, p)
        self.fd.solve()
        thru = (sum(self.fleets[b].throughput for b in self.hubs) - thru_before
                if self.ev_in_loop else p_batt_uncapped)

        v = self.fd.phase_vpu() if self.reward_on == "phase" else self.fd.bus_vpu()
        r = reward_from_v(v, self.cfg["v_min"], self.cfg["v_max"])
        r -= self.w_deg * (thru / max(1e-6, self.p_total))

        self._t += 1
        done = self._t >= len(self.hours)
        nh = self.hours[min(self._t, len(self.hours) - 1)]
        obs = self._obs(self.fd.bus_vpu(), self._lam_at(nh))
        return obs, float(r), bool(done), False, {"thru": thru, "p_sup": p_sup_total}
