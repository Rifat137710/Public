"""Measure the Stage 1 operating point before anything is trained on it.

Reports, on the shared eval seeds:
  * the heuristic bracket (zero / uncoordinated / droop) -- audit A4;
  * the projection infeasibility rate against margin -- audit A5, which is how
    the margin gets chosen by measurement instead of inherited as 0.010.

    python scripts/characterize_operating_point.py [--episodes 10]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.agents import DroopAgent, UncoordinatedAgent, ZeroAgent
from safesac.config import MASTER_SEED, ExperimentConfig, eval_episode_seed
from safesac.env import N_BUS_CANONICAL, ChargingFeederEnv
from safesac.evaluate import evaluate
from safesac.powerflow import JacobianSensitivities
from safesac.projection import (
    SensitivityCache,
    SensitivityProjector,
    compute_loading_sensitivities,
)

EVAL_LABEL = "stage1_eval"
AGENTS = {"zero": ZeroAgent, "uncoordinated": UncoordinatedAgent, "droop": DroopAgent}


def heuristic_bracket(cfg: ExperimentConfig, n_episodes: int) -> dict:
    out = {}
    for name, cls in AGENTS.items():
        env = ChargingFeederEnv(cfg)
        agg = evaluate(cls(env), env, cfg, n_episodes=n_episodes, run_label=EVAL_LABEL)[
            "aggregate"
        ]
        out[name] = {
            "viol": agg["voltage_violation_step_rate_mean"],
            "viol_std": agg["voltage_violation_step_rate_std"],
            "soc_met": agg["frac_meeting_soc_target_mean"],
            "vmin": agg["vmin_pu_mean"],
            "net_cost": agg["net_cost_usd_mean"],
            "n_evs": agg["n_evs_departed_mean"],
            "viol_magnitude": agg["voltage_violation_magnitude_pu_mean"],
        }
        print(
            f"  {name:15s} viol={out[name]['viol']:.4f}+-{out[name]['viol_std']:.4f}  "
            f"soc={out[name]['soc_met']:.3f}  vmin={out[name]['vmin']:.4f}  "
            f"cost=${out[name]['net_cost']:8.2f}  EVs/ep={out[name]['n_evs']:.0f}"
        )
    return out


def infeasibility_vs_margin(cfg: ExperimentConfig, margins, n_episodes: int) -> dict:
    """Drive the projector with a full-charge request under a droop-like policy.

    Uses the uncoordinated request (-1 pu at every active station), which is the
    most demanding thing the projector will ever be asked to make safe.
    """
    out = {}
    for margin in margins:
        c = replace(cfg, safety=replace(cfg.safety, projection_margin_pu=margin))
        env = ChargingFeederEnv(c)
        requester = UncoordinatedAgent(env)
        proj = SensitivityProjector(c, env.n_stations, N_BUS_CANONICAL)

        n_calls = n_infeasible = n_frozen = n_viol = 0
        soc_met = []
        for ep in range(n_episodes):
            obs, info = env.reset(seed=eval_episode_seed(MASTER_SEED, ep, EVAL_LABEL))
            cache = SensitivityCache(c, env.feeder, env._pf_solver)
            proj.on_refresh()
            for _ in range(env.scenario.n_steps):
                cache.maybe_refresh(env.current_step)
                raw = requester.select_action(obs) * c.feeder.ev_station_kva
                n = env.n_stations
                res = proj.project(
                    raw[:n], raw[n:], env._prev_p_kw, env._prev_q_kvar,
                    cache.sens, cache.loading, skip_when_feasible=False,
                )
                n_calls += 1
                n_infeasible += (not res.ok)
                n_frozen += bool(res.frozen.any())
                action = np.clip(
                    np.concatenate([res.p_kw, res.q_kvar]) / c.feeder.ev_station_kva, -1, 1
                )
                obs, _, term, trunc, info = env.step(action)
                v = info.voltages
                if v.size and (
                    (v < c.safety.voltage_lower_pu).any() or (v > c.safety.voltage_upper_pu).any()
                ):
                    n_viol += 1
                if term or trunc:
                    break
            deps = env.departed_evs
            if deps:
                soc_met.append(
                    float(np.mean([ev.soc_target - ev.soc < 0.01 for ev in deps]))
                )
        out[margin] = {
            "infeasible_rate": n_infeasible / n_calls,
            "frozen_rate": n_frozen / n_calls,
            "realized_violation_rate": n_viol / n_calls,
            "soc_met": float(np.mean(soc_met)) if soc_met else float("nan"),
            "n_calls": n_calls,
        }
        o = out[margin]
        print(
            f"  margin={margin:.3f}  bound=[{c.safety.voltage_lower_pu + margin:.3f}, "
            f"{c.safety.voltage_upper_pu - margin:.3f}]  "
            f"infeasible={o['infeasible_rate']:.4f}  frozen={o['frozen_rate']:.4f}  "
            f"realized_viol={o['realized_violation_rate']:.4f}  soc={o['soc_met']:.3f}"
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--evs", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=Path("results/stage1_operating_point.json"))
    args = ap.parse_args()

    cfg = ExperimentConfig.stage1("weak", evs_per_station=args.evs)
    print(f"Stage 1 operating point: load {cfg.scenario.load_scale}, "
          f"{args.evs:.0f} EVs/station/day, loss term {cfg.reward.include_loss_term}")
    print(f"fingerprint {cfg.fingerprint()}, {args.episodes} episodes\n")

    print("[1] heuristic bracket (weak feeder)")
    bracket = heuristic_bracket(cfg, args.episodes)

    print("\n[2] projection infeasibility vs margin (worst-case full-charge request)")
    margins = infeasibility_vs_margin(cfg, [0.0, 0.005, 0.010, 0.020], args.episodes)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"fingerprint": cfg.fingerprint(), "evs_per_station": args.evs,
             "episodes": args.episodes, "bracket": bracket,
             "infeasibility_vs_margin": {str(k): v for k, v in margins.items()}},
            indent=2, default=float,
        )
    )
    print(f"\nwrote {args.out}")

    idle = bracket["zero"]["viol"]
    print(f"\nidle floor = {idle:.4f}", "OK" if idle == 0.0 else "NOT ZERO -- lower the load")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
