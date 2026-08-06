"""The charging-feeder environment.

Ported from `thesis11.ipynb` Block 3, with Block 5's `_ScaledLoadEnv` load
scaling folded in rather than monkey-patched on afterwards.

Behaviour is deliberately bug-for-bug faithful to the shipped run so that the
port can be validated against published numbers. Two quirks worth naming,
because they look like mistakes and are reproduced on purpose:

* the observation is built *after* the exogenous state has advanced to t+1,
  while the power-flow result in it is from step t;
* `collect_episode_rollout` records `retail_price` after stepping, so the
  economic metrics are computed against the t+1 price while the reward uses t.

Both are marked ``FAITHFUL:`` below. Stage 1 fixes them behind a config flag.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .config import ExperimentConfig
from .network import Feeder, build_feeder, set_loads, set_pv_power, set_station_power
from .powerflow import PFResult, RadialPowerFlow, run_pf_reference
from .scenario import EV, Scenario, sample_scenario, v2g_buyback_price

N_BUS_CANONICAL = 34  # weak-grid bus count; strong is padded with V = 1.0


class StateNormalizer:
    """Welford online mean/variance per dimension, with a freeze switch."""

    def __init__(self, dim: int):
        self.dim = int(dim)
        self.count = 0
        self.mean = np.zeros(self.dim, dtype=np.float64)
        self.m2 = np.zeros(self.dim, dtype=np.float64)
        self.frozen = False

    def update(self, x) -> None:
        if self.frozen:
            return
        x = np.asarray(x, dtype=np.float64)
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (x - self.mean)

    @property
    def std(self) -> np.ndarray:
        if self.count < 2:
            return np.ones_like(self.mean)
        return np.sqrt(self.m2 / (self.count - 1))

    def normalize(self, x) -> np.ndarray:
        return (np.asarray(x, dtype=np.float64) - self.mean) / (self.std + 1e-8)

    def freeze(self) -> None:
        self.frozen = True

    def state_dict(self) -> dict:
        return {
            "count": int(self.count),
            "mean": self.mean.tolist(),
            "M2": self.m2.tolist(),
            "frozen": bool(self.frozen),
        }

    def load_state_dict(self, sd: dict) -> None:
        self.count = int(sd["count"])
        self.mean = np.asarray(sd["mean"], dtype=np.float64)
        self.m2 = np.asarray(sd["M2"], dtype=np.float64)
        self.frozen = bool(sd["frozen"])


# --------------------------------------------------------------------------
# Per-EV power allocation
# --------------------------------------------------------------------------


def distribute_station_power(cfg, p_kw: float, q_kvar: float, evs: List[EV]):
    """Split a station set-point across its connected vehicles.

    Charging is shared in proportion to energy still owed; discharging in
    proportion to headroom above the V2G floor, and only for opted-in vehicles.
    Sign convention: p_kw > 0 is V2G injection, p_kw < 0 is charging.
    """
    n = len(evs)
    if n == 0:
        return [], [], 0.0, 0.0

    f = cfg.fleet
    q_per_ev = q_kvar / n
    if abs(p_kw) < 1e-6:
        return [0.0] * n, [q_per_ev] * n, 0.0, q_per_ev * n

    if p_kw < 0:  # charging
        priorities = [max(0.0, ev.soc_target - ev.soc) * ev.battery_capacity_kwh for ev in evs]
    else:  # discharging
        priorities = [
            max(0.0, ev.soc - f.soc_floor_discharge) * ev.battery_capacity_kwh
            if ev.v2g_allowed
            else 0.0
            for ev in evs
        ]

    total = sum(priorities)
    if total < 1e-9:
        return [0.0] * n, [q_per_ev] * n, 0.0, q_per_ev * n

    alloc = [p_kw * pri / total for pri in priorities]

    # Clip to the per-vehicle rating and hand the residual to whoever has room.
    for _ in range(3):
        residual = 0.0
        non_clipped = []
        for i in range(n):
            limit = -f.max_charge_kw if p_kw < 0 else f.max_discharge_kw
            over = alloc[i] < limit if p_kw < 0 else alloc[i] > limit
            if over:
                residual += alloc[i] - limit
                alloc[i] = limit
            elif priorities[i] > 0:
                non_clipped.append(i)
        if abs(residual) < 1e-6 or not non_clipped:
            break
        extra = residual / len(non_clipped)
        for i in non_clipped:
            alloc[i] += extra

    return alloc, [q_per_ev] * n, float(sum(alloc)), q_per_ev * n


def update_ev_soc(cfg, ev: EV, p_kw: float) -> None:
    step_h = cfg.time.step_minutes / 60.0
    f = cfg.fleet
    if p_kw < 0:  # charging
        delta = -p_kw * step_h * f.charge_efficiency / ev.battery_capacity_kwh
        ev.energy_delivered_kwh += -p_kw * step_h * f.charge_efficiency
    elif p_kw > 0:  # discharging
        delta = -p_kw * step_h / f.discharge_efficiency / ev.battery_capacity_kwh
        ev.energy_discharged_kwh += p_kw * step_h / f.discharge_efficiency
    else:
        delta = 0.0
    ev.soc = max(0.0, min(1.0, ev.soc + delta))


# --------------------------------------------------------------------------
# Reward
# --------------------------------------------------------------------------


def compute_reward(cfg, p_kw_per_station, p_loss_mw: float, retail_price: float, user_penalty: float):
    r = cfg.reward
    step_h = cfg.time.step_minutes / 60.0

    cost_energy = 0.0
    for p in p_kw_per_station:
        kwh = abs(p) * step_h
        if p < 0:
            cost_energy += kwh * retail_price
        else:
            cost_energy -= kwh * v2g_buyback_price(cfg, retail_price)

    cost_deg = sum(r.degradation_usd_per_kwh * abs(p) * step_h for p in p_kw_per_station)
    loss_kwh = max(0.0, p_loss_mw) * 1000.0 * step_h
    cost_loss = loss_kwh * retail_price if r.include_loss_term else 0.0

    components = {"cost": cost_energy, "user": user_penalty, "deg": cost_deg, "loss": cost_loss}
    weights = {"cost": r.weight_cost, "user": r.weight_user, "deg": r.weight_deg, "loss": r.weight_loss}
    scales = {"cost": r.scale_cost, "user": r.scale_user, "deg": r.scale_deg, "loss": r.scale_loss}

    reward = -sum(weights[k] * components[k] / max(scales[k], 1e-9) for k in components)
    reward /= max(r.reward_scale, 1e-9)
    return float(reward), components


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------


@dataclass
class StepInfo:
    p_kw_per_station: np.ndarray
    q_kvar_per_station: np.ndarray
    voltages: np.ndarray
    transformer_loading_pu: float
    p_loss_mw: float
    reward_components: dict
    constraint_cost: float
    step: int
    user_penalty: float
    pf_converged: bool
    raw_obs: np.ndarray


class ChargingFeederEnv:
    """Gymnasium-style API without the hard dependency on gymnasium."""

    def __init__(
        self,
        cfg: ExperimentConfig,
        normalizer: Optional[StateNormalizer] = None,
        update_normalizer: bool = True,
        use_fast_pf: bool = True,
    ):
        self.cfg = cfg
        self.normalizer = normalizer
        self.update_normalizer = update_normalizer
        self.use_fast_pf = use_fast_pf

        probe = build_feeder(cfg.feeder)
        self.n_stations = probe.n_stations
        self.n_loads = len(probe.net.load)
        self.n_pv = len(probe.pv_buses)

        self.obs_dim = (
            N_BUS_CANONICAL + 1 + self.n_loads + 4 * self.n_stations + self.n_pv + 1 + 1 + 6 + 1
        )
        self.action_dim = 2 * self.n_stations

        self.feeder: Optional[Feeder] = None
        self.scenario: Optional[Scenario] = None
        self._pf_solver: Optional[RadialPowerFlow] = None
        self.current_step = 0
        self.active_evs: List[List[EV]] = []
        self._prev_p_kw = np.zeros(self.n_stations)
        self._prev_q_kvar = np.zeros(self.n_stations)
        self._current_loads_p_mw = np.zeros(self.n_loads)
        self._current_pv_kw = np.zeros(self.n_pv)
        self._current_price = 0.0
        self._running_load_max = 1e-3
        self._last_pf: Optional[PFResult] = None
        self._reset_seed = cfg.master_seed

    # -- helpers -----------------------------------------------------------

    def _solve_pf(self) -> PFResult:
        if self.use_fast_pf:
            return self._pf_solver.solve()
        return run_pf_reference(self.feeder)

    def _denormalize_action(self, action):
        a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        s = self.cfg.feeder.ev_station_kva
        return a[: self.n_stations] * s, a[self.n_stations : 2 * self.n_stations] * s

    def _apply_ramp(self, target, prev):
        step = self.cfg.safety.station_ramp_per_step_pu * self.cfg.feeder.ev_station_kva
        return np.clip(target, prev - step, prev + step)

    def _apply_apparent_power_limit(self, p_kw, q_kvar):
        s = self.cfg.feeder.ev_station_kva
        mag = np.sqrt(p_kw**2 + q_kvar**2)
        scale = np.where(mag > s, s / np.maximum(mag, 1e-9), 1.0)
        return p_kw * scale, q_kvar * scale

    def _update_exogenous(self):
        t = min(self.current_step, self.scenario.n_steps - 1)
        scale = self.cfg.scenario.load_scale
        mult = self.scenario.load_multiplier[t]
        p_mw = self.feeder.base_load_p_mw * scale * mult
        q_mvar = self.feeder.base_load_q_mvar * scale * mult
        set_loads(self.feeder, p_mw, q_mvar)
        self._current_loads_p_mw = p_mw.copy()
        pv = self.scenario.pv_kw[t]
        set_pv_power(self.feeder, pv)
        self._current_pv_kw = pv.copy()
        self._current_price = float(self.scenario.retail_price[t])

    def _process_arrivals(self):
        for st_idx, evs in enumerate(self.scenario.fleet):
            for ev in evs:
                if (
                    ev.arrival_step == self.current_step
                    and not ev.no_show
                    and not ev.connected
                    and not ev.departed
                ):
                    ev.soc = ev.soc_init
                    ev.connected = True
                    self.active_evs[st_idx].append(ev)

    def _process_departures(self) -> float:
        penalty = 0.0
        for st_idx in range(self.n_stations):
            keep = []
            for ev in self.active_evs[st_idx]:
                if self.current_step >= ev.arrival_step + ev.dwell_steps:
                    shortfall_kwh = max(0.0, ev.soc_target - ev.soc) * ev.battery_capacity_kwh
                    penalty += (
                        shortfall_kwh**2 if self.cfg.reward.user_penalty_quadratic else shortfall_kwh
                    )
                    ev.connected = False
                    ev.departed = True
                else:
                    keep.append(ev)
            self.active_evs[st_idx] = keep
        return penalty

    def fleet_aggregates(self) -> np.ndarray:
        out = np.zeros((self.n_stations, 4))
        for st_idx, evs in enumerate(self.active_evs):
            if not evs:
                continue
            out[st_idx] = [
                len(evs),
                float(np.mean([e.soc for e in evs])),
                float(sum(max(0.0, e.soc_target - e.soc) * e.battery_capacity_kwh for e in evs)),
                float(
                    np.mean([e.arrival_step + e.dwell_steps - self.current_step for e in evs])
                )
                / self.cfg.time.steps_per_hour,
            ]
        return out

    def _voltage_obs(self, pf: PFResult) -> np.ndarray:
        v = pf.v_pu
        if len(v) < N_BUS_CANONICAL:
            return np.concatenate([v, np.ones(N_BUS_CANONICAL - len(v))])
        return v[:N_BUS_CANONICAL]

    def _build_observation(self, pf: PFResult) -> np.ndarray:
        sc = self.scenario
        t = min(self.current_step, sc.n_steps - 1)
        hod, dow, doy = float(sc.hour_of_day[t]), float(sc.day_of_week[t]), float(sc.day_of_year[t])
        time_enc = np.array(
            [
                math.sin(2 * math.pi * hod / 24),
                math.cos(2 * math.pi * hod / 24),
                math.sin(2 * math.pi * dow / 7),
                math.cos(2 * math.pi * dow / 7),
                math.sin(2 * math.pi * doy / 365),
                math.cos(2 * math.pi * doy / 365),
            ]
        )
        t_next = min(t + 1, sc.n_steps - 1)
        forecast = float(sc.load_multiplier[t_next].mean())
        total = float(self._current_loads_p_mw.sum())
        self._running_load_max = max(self._running_load_max, total)
        rel_load = total / max(self._running_load_max, 1e-6)

        return np.concatenate(
            [
                self._voltage_obs(pf),
                [pf.transformer_loading_pu],
                self._current_loads_p_mw,
                self.fleet_aggregates().flatten(),
                self._current_pv_kw,
                [self._current_price],
                [forecast],
                time_enc,
                [rel_load],
            ]
        ).astype(np.float32)

    def _maybe_normalize(self, obs):
        if self.normalizer is None:
            return obs.astype(np.float32)
        if self.update_normalizer and not self.normalizer.frozen:
            self.normalizer.update(obs)
        return self.normalizer.normalize(obs).astype(np.float32)

    def constraint_cost(self, pf: PFResult) -> float:
        s = self.cfg.safety
        v = pf.v_pu
        excursion = (np.maximum(0.0, s.voltage_lower_pu - v) + np.maximum(0.0, v - s.voltage_upper_pu)).sum()
        overload = max(0.0, pf.transformer_loading_pu - s.transformer_loading_limit_pu)
        return float(excursion + overload)

    # -- API ---------------------------------------------------------------

    def reset(self, seed: Optional[int] = None):
        if seed is not None:
            self._reset_seed = int(seed)

        self.feeder = build_feeder(self.cfg.feeder)
        self._pf_solver = RadialPowerFlow(self.feeder)
        self.scenario = sample_scenario(
            self.cfg,
            seed=self._reset_seed,
            n_loads=len(self.feeder.net.load),
            n_stations=self.n_stations,
        )

        self.current_step = 0
        self.active_evs = [[] for _ in range(self.n_stations)]
        self._prev_p_kw = np.zeros(self.n_stations)
        self._prev_q_kvar = np.zeros(self.n_stations)
        self._running_load_max = 1e-3

        self._update_exogenous()
        set_station_power(self.feeder, np.zeros(self.n_stations), np.zeros(self.n_stations))
        pf = self._solve_pf()
        if not pf.converged:
            raise RuntimeError("initial power flow did not converge")
        self._last_pf = pf
        self._process_arrivals()

        obs = self._build_observation(pf)
        return self._maybe_normalize(obs), {"raw_obs": obs.copy()}

    def step(self, action):
        p_target, q_target = self._denormalize_action(action)
        p_ramped = self._apply_ramp(p_target, self._prev_p_kw)
        q_ramped = self._apply_ramp(q_target, self._prev_q_kvar)
        p_cmd, q_cmd = self._apply_apparent_power_limit(p_ramped, q_ramped)

        user_penalty = self._process_departures()

        realized_p = np.zeros(self.n_stations)
        realized_q = np.zeros(self.n_stations)
        for st_idx in range(self.n_stations):
            evs = self.active_evs[st_idx]
            alloc, _, rp, rq = distribute_station_power(
                self.cfg, float(p_cmd[st_idx]), float(q_cmd[st_idx]), evs
            )
            for ev, p_ev in zip(evs, alloc):
                update_ev_soc(self.cfg, ev, p_ev)
            realized_p[st_idx] = rp
            realized_q[st_idx] = rq

        set_station_power(self.feeder, realized_p, realized_q)
        pf = self._solve_pf()

        terminated = False
        if not pf.converged:
            # Scaled like every other reward term, so its relative size is fixed.
            reward = -self.cfg.reward.pf_failure_penalty / max(
                self.cfg.reward.reward_scale, 1e-9
            )
            components = {"cost": 0.0, "user": user_penalty, "deg": 0.0, "loss": 0.0}
            terminated = True
        else:
            # FAITHFUL: reward uses the step-t price, before the exogenous advance.
            reward, components = compute_reward(
                self.cfg, realized_p, pf.p_loss_mw, self._current_price, user_penalty
            )
        self._last_pf = pf

        self.current_step += 1
        if self.current_step < self.scenario.n_steps:
            self._update_exogenous()
            self._process_arrivals()

        # FAITHFUL: observation mixes the step-t power flow with t+1 exogenous state.
        if pf.converged and self.current_step < self.scenario.n_steps:
            obs = self._build_observation(pf)
        else:
            obs = np.zeros(self.obs_dim, dtype=np.float32)

        self._prev_p_kw = realized_p
        self._prev_q_kvar = realized_q
        truncated = self.current_step >= self.scenario.n_steps

        info = StepInfo(
            p_kw_per_station=realized_p.copy(),
            q_kvar_per_station=realized_q.copy(),
            voltages=pf.v_pu.copy() if pf.converged else np.zeros(0),
            transformer_loading_pu=float(pf.transformer_loading_pu),
            p_loss_mw=float(pf.p_loss_mw),
            reward_components=components,
            constraint_cost=self.constraint_cost(pf) if pf.converged else 1.0,
            step=int(self.current_step),
            user_penalty=float(user_penalty),
            pf_converged=bool(pf.converged),
            raw_obs=obs.copy(),
        )
        return self._maybe_normalize(obs), float(reward), bool(terminated), bool(truncated), info

    @property
    def departed_evs(self) -> List[EV]:
        return [ev for evs in self.scenario.fleet for ev in evs if ev.departed]
