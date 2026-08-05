"""Episode rollout, metrics, and evaluation over a shared seed band.

Metric definitions match `thesis11.ipynb` Block 6 §14.2-14.3 so that the port
can be checked against published numbers, with three additions the audit calls
for: violation magnitude in pu-steps, time outside band, and -- once a zero
injection reference is supplied -- violations in excess of that reference.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .config import ExperimentConfig, eval_episode_seed


@dataclass
class Rollout:
    rewards: np.ndarray
    constraint_costs: np.ndarray
    voltages: list
    transformer_loading: np.ndarray
    p_kw: np.ndarray
    q_kvar: np.ndarray
    p_loss_mw: np.ndarray
    retail_price: np.ndarray
    user_penalty: np.ndarray
    step_times_ms: np.ndarray
    pf_converged: np.ndarray
    n_steps: int
    seed: int
    departed_evs: list = field(default_factory=list)


def collect_rollout(agent, env, *, seed: int, deterministic: bool = True) -> Rollout:
    obs, info = env.reset(seed=seed)
    agent.reset_episode()
    t_max = env.scenario.n_steps
    n_st = env.n_stations

    rec = {
        "rewards": np.zeros(t_max),
        "constraint_costs": np.zeros(t_max),
        "transformer_loading": np.zeros(t_max),
        "p_kw": np.zeros((t_max, n_st)),
        "q_kvar": np.zeros((t_max, n_st)),
        "p_loss_mw": np.zeros(t_max),
        "retail_price": np.zeros(t_max),
        "user_penalty": np.zeros(t_max),
        "step_times_ms": np.zeros(t_max),
        "pf_converged": np.zeros(t_max, dtype=bool),
    }
    voltages: List[Optional[np.ndarray]] = [None] * t_max
    n_steps = 0

    for t in range(t_max):
        t0 = time.perf_counter()
        action = agent.select_action(obs, info=info, deterministic=deterministic)
        obs, reward, terminated, truncated, info = env.step(action)
        rec["step_times_ms"][t] = (time.perf_counter() - t0) * 1000.0

        rec["rewards"][t] = reward
        rec["constraint_costs"][t] = info.constraint_cost
        voltages[t] = info.voltages.copy() if info.voltages.size else None
        rec["transformer_loading"][t] = info.transformer_loading_pu
        rec["p_kw"][t] = info.p_kw_per_station
        rec["q_kvar"][t] = info.q_kvar_per_station
        rec["p_loss_mw"][t] = info.p_loss_mw
        # FAITHFUL: recorded after stepping, so this is the t+1 price -- the
        # thesis's economic metrics are computed against it. See env.py.
        rec["retail_price"][t] = env._current_price
        rec["user_penalty"][t] = info.user_penalty
        rec["pf_converged"][t] = info.pf_converged
        n_steps = t + 1
        if terminated or truncated:
            break

    return Rollout(
        voltages=voltages, n_steps=n_steps, seed=seed, departed_evs=env.departed_evs, **rec
    )


def compute_metrics(cfg: ExperimentConfig, roll: Rollout) -> Dict[str, float]:
    t = roll.n_steps
    if t == 0:
        return {"n_steps": 0}

    s = cfg.safety
    step_h = cfg.time.step_minutes / 60.0

    # ---- safety ----
    n_viol = 0
    viol_magnitude = 0.0
    v_min, v_max = float("inf"), float("-inf")
    for v in roll.voltages[:t]:
        if v is None:
            continue
        v_min, v_max = min(v_min, float(v.min())), max(v_max, float(v.max()))
        viol_magnitude += float(np.clip(s.voltage_lower_pu - v, 0, None).sum()) + float(
            np.clip(v - s.voltage_upper_pu, 0, None).sum()
        )
        if (v < s.voltage_lower_pu).any() or (v > s.voltage_upper_pu).any():
            n_viol += 1

    # ---- service ----
    deps = roll.departed_evs
    if deps:
        shortfall = np.array([max(0.0, ev.soc_target - ev.soc) for ev in deps])
        frac_met = float((shortfall < 0.01).mean())
    else:
        shortfall = np.array([0.0])
        frac_met = 1.0

    # ---- economics ----
    p_kw = roll.p_kw[:t]
    price = roll.retail_price[:t]
    kwh = p_kw * step_h
    charge = kwh < 0
    discharge = kwh > 0
    price_bcast = np.broadcast_to(price[:, None], kwh.shape)

    cost_buy = float(np.where(charge, -kwh * price_bcast, 0.0).sum())
    rev_sell = float(
        np.where(discharge, kwh * cfg.scenario.v2g_price_fraction * price_bcast, 0.0).sum()
    )
    charge_kwh = float(np.where(charge, -kwh, 0.0).sum())
    discharge_kwh = float(np.where(discharge, kwh, 0.0).sum())
    throughput = charge_kwh + discharge_kwh

    loss = roll.p_loss_mw[:t].clip(min=0)
    trafo = roll.transformer_loading[:t]

    return {
        "voltage_violation_step_rate": n_viol / t,
        "voltage_violation_magnitude_pu": viol_magnitude,
        "time_outside_band_h": n_viol * step_h,
        "vmin_pu": v_min if v_min != float("inf") else float("nan"),
        "vmax_pu": v_max if v_max != float("-inf") else float("nan"),
        "transformer_overload_step_rate": float((trafo > s.transformer_loading_limit_pu).mean()),
        "transformer_max_loading_pu": float(trafo.max()),
        "n_evs_departed": len(deps),
        "frac_meeting_soc_target": frac_met,
        "mean_soc_shortfall": float(shortfall.mean()),
        "max_soc_shortfall": float(shortfall.max()),
        "total_user_penalty": float(roll.user_penalty[:t].sum()),
        "cost_buy_usd": cost_buy,
        "revenue_sell_usd": rev_sell,
        "net_cost_usd": cost_buy - rev_sell,
        "mean_price_usd_per_kwh": float(price.mean()),
        "total_charge_kwh": charge_kwh,
        "total_discharge_kwh": discharge_kwh,
        "throughput_kwh": throughput,
        "v2g_utilization_rate": float(discharge.mean()),
        "total_line_losses_kwh": float(loss.sum() * 1000.0 * step_h),
        "mean_step_time_ms": float(roll.step_times_ms[:t].mean()),
        "max_step_time_ms": float(roll.step_times_ms[:t].max()),
        "pf_failure_rate": float((~roll.pf_converged[:t]).mean()),
        "total_reward": float(roll.rewards[:t].sum()),
        "total_constraint_cost": float(roll.constraint_costs[:t].sum()),
        "n_steps": t,
    }


def aggregate(per_episode: List[Dict[str, float]]) -> Dict[str, float]:
    if not per_episode:
        return {}
    out: Dict[str, float] = {}
    for key in per_episode[0]:
        vals = np.asarray([m[key] for m in per_episode if key in m], dtype=np.float64)
        if vals.size:
            out[f"{key}_mean"] = float(vals.mean())
            out[f"{key}_std"] = float(vals.std(ddof=0))
    out["n_episodes"] = len(per_episode)
    return out


def evaluate(agent, env, cfg: ExperimentConfig, *, n_episodes: int, run_label: str = "eval"):
    """Evaluate over a shared seed band so methods are paired episode-by-episode."""
    per_episode = []
    for ep in range(n_episodes):
        seed = eval_episode_seed(cfg.master_seed, ep, run_label)
        roll = collect_rollout(agent, env, seed=seed, deterministic=True)
        per_episode.append(compute_metrics(cfg, roll))
    return {"aggregate": aggregate(per_episode), "per_episode": per_episode}


def attributable(
    method: List[Dict[str, float]],
    baseline: List[Dict[str, float]],
    keys=("voltage_violation_step_rate", "voltage_violation_magnitude_pu"),
) -> Dict[str, float]:
    """Paired excess of a method over a zero-injection run on the same seeds.

    Audit item A4. A raw violation rate mixes what the controller caused with
    what the feeder was going to do anyway; at the thesis operating point the
    idle feeder alone violates 9.47 % of steps, so ~96 % of the headline number
    is exogenous and the published ranking is mostly noise about the background.
    Subtracting the paired zero-injection run leaves only what the charging
    decisions are responsible for -- which can be negative, meaning the
    controller actively helped.

    `method` and `baseline` must be the per-episode lists from `evaluate` runs
    that used the same `run_label` and episode count.
    """
    if len(method) != len(baseline):
        raise ValueError(f"unpaired: {len(method)} vs {len(baseline)} episodes")

    out: Dict[str, float] = {"n_episodes": len(method)}
    for key in keys:
        d = np.asarray(
            [m[key] - b[key] for m, b in zip(method, baseline)], dtype=np.float64
        )
        n = d.size
        mean = float(d.mean())
        # Paired-difference CI; ddof=1 because this is a sample of episodes.
        sem = float(d.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
        out[f"{key}_excess_mean"] = mean
        out[f"{key}_excess_std"] = float(d.std(ddof=1)) if n > 1 else 0.0
        out[f"{key}_excess_ci95_lo"] = mean - 1.96 * sem
        out[f"{key}_excess_ci95_hi"] = mean + 1.96 * sem
        out[f"{key}_baseline_mean"] = float(
            np.mean([b[key] for b in baseline])
        )
    return out
