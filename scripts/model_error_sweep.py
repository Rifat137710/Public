"""How wrong can the network model be before the safety layer stops protecting?

The claim on the books -- *carrying the wrong network's Jacobian costs nothing*
-- was measured across substation stiffness, where station-bus Jacobians differ
by only **1.16x**. Correctly scoped that sentence cannot be falsified, and a
reviewer can fairly answer that a 1.16x perturbation is not a test of model
error. It survives as a sentence and dies as a contribution
(docs/08-retroactive-risk.md, R5).

A second feeder cannot fix it: 34-bus and 117-bus Jacobians have different
dimensions, so one cannot be transplanted into the other. Scaling a single
feeder's line impedances can. Same dimensions, genuine model error, and a range
set by how wrong we choose to make it.

The arms, all deployed on the *true* feeder, all measuring their own voltages:

    raw       the request, unprojected
    wrong-k   projected with a Jacobian computed on a feeder whose line
              impedances are k times the truth
    correct   projected with the true Jacobian

`frozen_mode="jacobian"` matters here and is the whole point: it carries the
wrong Jacobian while refreshing the base point from the real feeder, which is
what a deployed controller with a stale model but live telemetry actually does.
Freezing the base point too would make every arm degenerate to `raw` and measure
nothing about model error.

    python scripts/model_error_sweep.py --episodes 15
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.agents import UncoordinatedAgent, UrgencyAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv
from safesac.evaluate import evaluate
from safesac.projected import ProjectedAgent
from safesac.projection import SensitivityCache

EVAL_LABEL = "transfer_eval"
SOURCES = {"uncoordinated": UncoordinatedAgent, "urgency": UrgencyAgent}

FEEDERS = {
    "case33bw": lambda: ExperimentConfig.stiffness(6.0),
    "kerber": lambda: ExperimentConfig.kerber(),
}


def model_of(cfg: ExperimentConfig):
    """The sensitivities a controller shipped with this model would carry."""
    env = ChargingFeederEnv(cfg)
    env.reset(seed=0)
    cache = SensitivityCache(cfg, env.feeder, env._pf_solver)
    cache.maybe_refresh(0)
    return cache.sens, cache.loading


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=15)
    ap.add_argument("--feeder", choices=sorted(FEEDERS), default="case33bw")
    ap.add_argument("--scale", type=float, nargs="+",
                    default=[0.33, 0.5, 0.8, 1.25, 2.0, 3.0])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out_path = args.out or Path(f"results/model_error_{args.feeder}.json")
    true_cfg = FEEDERS[args.feeder]()
    true_sens, _ = model_of(true_cfg)
    ref = np.abs(true_sens.dv_dp).max()

    print(f"model-error sweep | {args.feeder} | line Z scaled by {args.scale}")
    print(f"{args.episodes} episodes | wrong Jacobian, base point measured on "
          f"the true feeder\n")

    t0 = time.perf_counter()
    out = {"feeder": args.feeder, "scale": args.scale,
           "episodes": args.episodes, "cells": {}}

    # How wrong does each scale actually make the Jacobian? Reported so the
    # claim can quote a measured range instead of a scaling factor.
    ratios = {}
    for k in args.scale:
        sens_k, _ = model_of(
            replace(true_cfg, feeder=replace(true_cfg.feeder, line_z_scale=k)))
        ratios[str(k)] = float(np.abs(sens_k.dv_dp).max() / ref)
    out["jacobian_ratio"] = ratios
    print("line Z scale -> station-bus |dV/dP| ratio vs truth:")
    for k in args.scale:
        print(f"   k={k:<6} ratio={ratios[str(k)]:.3f}x")
    print(f"   (substation-stiffness axis spanned only 1.16x)\n")

    for sname, scls in SOURCES.items():
        row = {}
        env = ChargingFeederEnv(true_cfg)
        raw = evaluate(scls(env), env, true_cfg, n_episodes=args.episodes,
                       run_label=EVAL_LABEL)["aggregate"]
        row["raw"] = {"viol": raw["voltage_violation_step_rate_mean"],
                      "soc": raw["frac_meeting_soc_target_mean"]}

        env = ChargingFeederEnv(true_cfg)
        agent = ProjectedAgent(scls(env), env, true_cfg)
        corr = evaluate(agent, env, true_cfg, n_episodes=args.episodes,
                        run_label=EVAL_LABEL)["aggregate"]
        row["correct"] = {"viol": corr["voltage_violation_step_rate_mean"],
                          "soc": corr["frac_meeting_soc_target_mean"],
                          "infeasible": agent.stats.summary()[
                              "projection_infeasible_rate"]}

        line = (f"   {sname:<14} raw={row['raw']['viol']:.4f}"
                f"   correct={row['correct']['viol']:.4f}")

        for k in args.scale:
            wrong_sens, wrong_loading = model_of(
                replace(true_cfg,
                        feeder=replace(true_cfg.feeder, line_z_scale=k)))
            env = ChargingFeederEnv(true_cfg)
            agent = ProjectedAgent(scls(env), env, true_cfg,
                                   frozen_sensitivities=wrong_sens,
                                   frozen_loading=wrong_loading,
                                   frozen_mode="jacobian")
            agg = evaluate(agent, env, true_cfg, n_episodes=args.episodes,
                           run_label=EVAL_LABEL)["aggregate"]
            s = agent.stats.summary()
            row[str(k)] = {"viol": agg["voltage_violation_step_rate_mean"],
                           "soc": agg["frac_meeting_soc_target_mean"],
                           "infeasible": s["projection_infeasible_rate"],
                           "frozen": s["projection_frozen_step_rate"]}
            line += f"   k{k}={row[str(k)]['viol']:.4f}"
        out["cells"][sname] = row
        print(line)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=float))

    # ---- the claim, checked ------------------------------------------------
    print("\n" + "=" * 84)
    print("Violations against how wrong the Jacobian is (base point always measured)")
    print("=" * 84)
    hdr = "".join(f"{('k=' + str(k)):>10}" for k in args.scale)
    print(f"{'source':<16}{'raw':>9}{'correct':>9}{hdr}")
    for sname in SOURCES:
        r = out["cells"][sname]
        print(f"{sname:<16}{r['raw']['viol']:>9.4f}{r['correct']['viol']:>9.4f}"
              + "".join(f"{r[str(k)]['viol']:>10.4f}" for k in args.scale))
    print(f"{'':<16}{'':>9}{'service':>9}"
          + "".join(f"{out['cells']['uncoordinated'][str(k)]['soc']:>10.3f}"
                    for k in args.scale))

    worst = max(
        out["cells"][s][str(k)]["viol"] - out["cells"][s]["correct"]["viol"]
        for s in SOURCES for k in args.scale)
    out["worst_excess_violations"] = float(worst)
    # An under-estimated impedance is the dangerous direction: the model thinks
    # the feeder is stiffer than it is, so it permits more than it should.
    under = max(
        out["cells"][s][str(k)]["viol"] - out["cells"][s]["correct"]["viol"]
        for s in SOURCES for k in args.scale if k < 1.0)
    out["worst_excess_under_estimated"] = float(under)
    out_path.write_text(json.dumps(out, indent=2, default=float))

    lo, hi = min(ratios.values()), max(ratios.values())
    print("\n" + "-" * 84)
    print(f"Jacobian error actually spanned: {lo:.2f}x to {hi:.2f}x "
          f"(stiffness axis managed 1.16x)")
    if worst <= 1e-9:
        print(f"MODEL ERROR IS FREE over this range. A projection carrying a "
              f"Jacobian wrong by {lo:.2f}x-{hi:.2f}x is exactly as safe as the "
              f"correct one, provided it measures its own voltages.")
    else:
        print(f"MODEL ERROR IS NOT FREE: up to {worst:.4f} excess violating "
              f"steps over the correct model ({under:.4f} when the impedance is "
              f"under-estimated). The claim must be bounded to the range where "
              f"it holds.")
    print(f"({time.perf_counter() - t0:.0f}s)  wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
