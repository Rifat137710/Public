"""
Phase-3 environment — RESIDUAL-OVER-DROOP, DISCHARGE-ONLY.

Fixes the two failure modes seen in the direct-action foresight agent:
  (1) It couldn't match droop's basic competence from a cold start.
  (2) It "rationed" by CHARGING mid-day (banking SOC), which draws grid power and
      pushes sagging voltages even lower -> it *created* violations.

Here the agent outputs a bounded RESIDUAL added to the droop setpoint:
      P = clip( droop_P + a_P * P_rated , 0 , P_rated )    # discharge-only (>= 0)
      Q = clip( droop_Q + a_Q * Q_rated , -Q_rated , Q_rated )
so a = 0  ==>  plain droop (a guaranteed performance floor), and the agent can only
learn to *withhold* discharge in the morning (save SOC) or *add* discharge in the
evening. It can never charge during the support window. The augmented state
(SOC / availability / time) lets it time this intertemporally.
"""
import numpy as np, gymnasium as gym
from gymnasium import spaces
from v2g_core import Feeder, EVFleet, reward_from_v, lam_profile, droop_pq, CFG, AVAIL


class V2GVoltEnvResidual(gym.Env):
    def __init__(self, hub_buses, cfg=CFG, peak_range=(1.0, 3.5), load_noise=0.05,
                 soc_cost=0.5, seed=0):
        super().__init__()
        self.cfg = cfg; self.peak_range = peak_range; self.load_noise = load_noise
        self.soc_cost = soc_cost
        self.fd = Feeder(hub_buses); self.nb = len(self.fd.buses); self.nh = len(hub_buses)
        self.hours = list(cfg["active_hours"]); self.H = len(self.hours)
        self.fleets = {b: EVFleet(cfg) for b in hub_buses}
        self.rng = np.random.default_rng(seed)
        self.action_space = spaces.Box(-1.0, 1.0, shape=(2 * self.nh,), dtype=np.float32)
        obs_dim = self.nb + 2 + 2 * self.nh
        self.observation_space = spaces.Box(-0.1, 2.0, shape=(obs_dim,), dtype=np.float32)
        self._ti = 0; self._peak = 1.5; self._lam_day = lam_profile(1.5)

    def _hour(self):
        return self.hours[min(self._ti, self.H - 1)]

    def _obs(self):
        h = self._hour(); lam = self._lam_day[h]
        self.fd.set_load(lam); self.fd.zero_hubs(); self.fd.solve()
        vpu = self.fd.bus_vpu()
        lam_norm = (lam - 0.1) / (4.0 - 0.1)
        hour_norm = (h - self.hours[0]) / (self.hours[-1] - self.hours[0])
        socs = [self.fleets[b].soc for b in self.fd.hub_buses]
        navs = [self.fleets[b].n_avail(h) / self.cfg["n_ev"] for b in self.fd.hub_buses]
        return np.concatenate([vpu, [lam_norm, hour_norm], socs, navs]).astype(np.float32)

    def reset(self, seed=None, options=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self._peak = float(self.rng.uniform(*self.peak_range))
        shape = lam_profile(self._peak)
        noise = 1.0 + self.rng.normal(0.0, self.load_noise, size=shape.shape)
        self._lam_day = np.clip(shape * noise, 0.05, None)
        for fl in self.fleets.values():
            fl.reset()
        self._ti = 0
        return self._obs(), {}

    def _residual_setpoint(self, b, i, a):
        """droop baseline (from current raw voltage) + bounded residual; discharge-only P."""
        v = self.fd.hub_vpu(b)
        p_d, q_d = droop_pq(v, self.cfg["P_rated"], self.cfg["Q_rated"])
        p_req = float(np.clip(max(0.0, p_d) + a[2 * i]     * self.cfg["P_rated"], 0.0, self.cfg["P_rated"]))
        q_req = float(np.clip(q_d          + a[2 * i + 1] * self.cfg["Q_rated"], -self.cfg["Q_rated"], self.cfg["Q_rated"]))
        return p_req, q_req

    def step(self, action):
        a = np.clip(action, -1, 1); h = self._hour()
        discharge = 0.0
        for i, b in enumerate(self.fd.hub_buses):
            p_req, q_req = self._residual_setpoint(b, i, a)
            p_sup, q_sup, _, _ = self.fleets[b].apply(p_req, q_req, h)
            self.fd.set_hub(b, p_sup, q_sup)
            discharge += max(0.0, p_sup) / self.cfg["P_rated"]
        self.fd.solve()
        r = reward_from_v(self.fd.bus_vpu(), self.cfg["v_min"], self.cfg["v_max"])
        r -= self.soc_cost * discharge
        self._ti += 1
        trunc = self._ti >= self.H; term = False
        return self._obs(), float(r), term, trunc, {}


def evaluate_day_residual(feeder, peak, policy, cfg=CFG):
    """Deterministic daily rollout of a residual-over-droop policy. If policy is None,
    plays ZERO residual == plain (open-loop) droop, to verify the performance floor.
    Obs layout matches V2GVoltEnvResidual._obs exactly."""
    lam = lam_profile(peak); hours = list(cfg["active_hours"])
    fleets = {b: EVFleet(cfg) for b in feeder.hub_buses}
    for fl in fleets.values():
        fl.reset()
    rec = {"hour": [], "vmean": [], "soc": [], "rho": []}
    for h in hours:
        feeder.set_load(lam[h]); feeder.zero_hubs(); feeder.solve()
        vpu = feeder.bus_vpu()
        lam_norm = (lam[h] - 0.1) / (4.0 - 0.1)
        hour_norm = (h - hours[0]) / (hours[-1] - hours[0])
        socs = [fleets[b].soc for b in feeder.hub_buses]
        navs = [fleets[b].n_avail(h) / cfg["n_ev"] for b in feeder.hub_buses]
        if policy is None:
            act = np.zeros(2 * len(feeder.hub_buses), dtype=np.float32)
        else:
            obs = np.concatenate([vpu, [lam_norm, hour_norm], socs, navs]).astype(np.float32)
            act, _ = policy.predict(obs, deterministic=True)
        rho_last = 1.0
        for i, b in enumerate(feeder.hub_buses):
            v = feeder.hub_vpu(b)
            p_d, q_d = droop_pq(v, cfg["P_rated"], cfg["Q_rated"])
            p_req = float(np.clip(max(0.0, p_d) + act[2 * i]     * cfg["P_rated"], 0.0, cfg["P_rated"]))
            q_req = float(np.clip(q_d          + act[2 * i + 1] * cfg["Q_rated"], -cfg["Q_rated"], cfg["Q_rated"]))
            p_sup, q_sup, rho, _ = fleets[b].apply(p_req, q_req, h); rho_last = rho
            feeder.set_hub(b, p_sup, q_sup)
        feeder.solve()
        rec["hour"].append(h); rec["vmean"].append(feeder.feeder_mean())
        rec["soc"].append(float(np.mean([fleets[b].soc for b in feeder.hub_buses])))
        rec["rho"].append(rho_last)
    vm = np.array(rec["vmean"])
    stats = dict(Mean=round(vm.mean(), 3), Min=round(vm.min(), 3), Max=round(vm.max(), 3),
                 Viol=int((vm < cfg["v_min"]).sum()))
    return stats, rec
