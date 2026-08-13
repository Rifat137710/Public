"""The headline experiment: does the safety layer's *model* transfer?

G0 (`scripts/operating_point_sweep.py`) found no operating point on this testbed
where a learner beats a greedy request passed through the projection. So the
claim cannot be about the learner. It can be about the safety layer -- and the
open question there is not whether a projection works, but whether one carrying
a *fixed* network model still works on a feeder it was not built for.

That question needs no training at all. For each deployment stiffness:

    raw       the request, unprojected
    frozen    projected against the TRAINING feeder's sensitivities
    deploy    projected against the DEPLOYMENT feeder's sensitivities

across several request sources, because a claim about the safety layer should
not depend on what is upstream of it.

    python scripts/projection_transfer.py --episodes 15
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.agents import DroopAgent, UncoordinatedAgent, UrgencyAgent, ZeroAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv
from safesac.evaluate import evaluate
from safesac.projected import ProjectedAgent
from safesac.projection import SensitivityCache

EVAL_LABEL = "transfer_eval"

SOURCES = {
    "uncoordinated": UncoordinatedAgent,
    "droop": DroopAgent,
    "urgency": UrgencyAgent,
}


def model_of(cfg: ExperimentConfig):
    """The sensitivities a controller shipped with a fixed model would carry."""
    env = ChargingFeederEnv(cfg)
    env.reset(seed=0)
    cache = SensitivityCache(cfg, env.feeder, env._pf_solver)
    cache.maybe_refresh(0)
    return cache.sens, cache.loading


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=15)
    ap.add_argument("--train-z", type=float, default=0.5)
    ap.add_argument("--deploy-z", type=float, nargs="+", default=[0.5, 2.0, 4.0, 6.0])
    ap.add_argument("--load", type=float, default=0.40)
    ap.add_argument("--evs", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=Path("results/projection_transfer.json"))
    args = ap.parse_args()

    def cfg_at(z):
        return ExperimentConfig.stiffness(z, evs_per_station=args.evs,
                                          load_scale=args.load)

    print(f"projection transfer | model built at Z={args.train_z}% | "
          f"deployed at {args.deploy_z}%")
    print(f"load {args.load} | {args.evs:.0f} EVs/station | "
          f"{args.episodes} episodes\n")

    frozen_sens, frozen_loading = model_of(cfg_at(args.train_z))
    t0 = time.perf_counter()
    out = {"train_z_pct": args.train_z, "deploy_z_pct": args.deploy_z,
           "load_scale": args.load, "evs_per_station": args.evs,
           "episodes": args.episodes, "cells": {}}

    for z in args.deploy_z:
        cfg = cfg_at(z)
        env = ChargingFeederEnv(cfg)
        idle = evaluate(ZeroAgent(env), env, cfg, n_episodes=args.episodes,
                        run_label=EVAL_LABEL)["aggregate"]
        cell = {"idle": idle, "sources": {}}
        print(f"Z={z:4.1f}%   idle viol={idle['voltage_violation_step_rate_mean']:.4f}  "
              f"Vmin={idle['vmin_pu_mean']:.4f}")

        for sname, scls in SOURCES.items():
            row = {}
            for treat in ("raw", "frozen", "deploy"):
                env = ChargingFeederEnv(cfg)
                base = scls(env)
                if treat == "raw":
                    agent = base
                elif treat == "frozen":
                    agent = ProjectedAgent(base, env, cfg,
                                           frozen_sensitivities=frozen_sens,
                                           frozen_loading=frozen_loading)
                else:
                    agent = ProjectedAgent(base, env, cfg)
                agg = evaluate(agent, env, cfg, n_episodes=args.episodes,
                               run_label=EVAL_LABEL)["aggregate"]
                r = {"viol": agg["voltage_violation_step_rate_mean"],
                     "viol_mag": agg["voltage_violation_magnitude_pu_mean"],
                     "soc": agg["frac_meeting_soc_target_mean"],
                     "cost": agg["net_cost_usd_mean"],
                     "vmin": agg["vmin_pu_mean"]}
                if hasattr(agent, "stats"):
                    s = agent.stats.summary()
                    r["infeasible"] = s["projection_infeasible_rate"]
                row[treat] = r
            cell["sources"][sname] = row
            print(f"   {sname:<14} "
                  + "   ".join(f"{t}={row[t]['viol']:.4f}/{row[t]['soc']:.3f}"
                               for t in ("raw", "frozen", "deploy")))
        out["cells"][str(z)] = cell

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, default=float))

    # ---- the claim, checked ---------------------------------------------
    print("\n" + "=" * 78)
    print("Does a fixed network model survive deployment?  (violations)")
    print("=" * 78)
    print(f"{'source':<16}{'Z%':>6}{'raw':>10}{'frozen':>10}{'deploy':>10}"
          f"{'frozen-deploy':>15}")
    verdict = {}
    for sname in SOURCES:
        gaps = []
        for z in args.deploy_z:
            r = out["cells"][str(z)]["sources"][sname]
            gap = r["frozen"]["viol"] - r["deploy"]["viol"]
            gaps.append(gap)
            print(f"{sname:<16}{z:>6.1f}{r['raw']['viol']:>10.4f}"
                  f"{r['frozen']['viol']:>10.4f}{r['deploy']['viol']:>10.4f}"
                  f"{gap:>+15.4f}")
        verdict[sname] = {"max_gap": float(max(gaps)),
                          "gap_at_weakest": float(gaps[-1])}

    out["verdict"] = verdict
    args.out.write_text(json.dumps(out, indent=2, default=float))

    best = max(verdict.values(), key=lambda v: v["max_gap"])["max_gap"]
    print("\n" + "-" * 78)
    if best > 1e-9:
        print(f"CLAIM HOLDS: a projection carrying the training feeder's model "
              f"admits up to {best:.4f} more violating steps than one rebuilt at "
              f"the deployment feeder.")
        print("The contribution is the deployment-side parametrisation.")
    else:
        print("CLAIM DOES NOT HOLD: the frozen model is as safe as the rebuilt "
              "one across this range.")
        print("Either widen the stiffness range or report the projection's "
              "robustness to model error as the finding -- it is a real one.")
    print(f"({time.perf_counter() - t0:.0f}s)  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
