"""What actually makes the safety layer fail: a stale base point.

The transfer experiment I ran first conflated two things. Freezing the whole
`Sensitivities` object freezes the Jacobian *and* the operating point it was
linearised about. Splitting them (safesac/projected.py, `frozen_mode`) shows the
Jacobian is not what matters on this testbed:

    deploy Z    raw       snapshot   jacobian-only   correct model
      6.0%    0.0577       0.0577       0.0000          0.0000
      8.0%    0.0994       0.0994       0.0000          0.0000

A projection carrying a *different feeder's* Jacobian but measuring its own
voltages is exactly as safe as one with the right Jacobian. A projection
carrying the right Jacobian about a stale base point is exactly as unsafe as no
projection at all.

That is a claim about refresh cadence, not about network transfer, so it has to
be measured on one feeder with the correct model and nothing varying but the
refresh interval. Audit item B3: the thesis refreshed hourly (12 steps) while
claiming per-step, and the 677x sensitivity speed-up is what makes per-step
affordable.

    python scripts/staleness_sweep.py --episodes 12
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safesac.agents import UncoordinatedAgent, UrgencyAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv
from safesac.evaluate import evaluate
from safesac.projected import ProjectedAgent

EVAL_LABEL = "transfer_eval"
SOURCES = {"uncoordinated": UncoordinatedAgent, "urgency": UrgencyAgent}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=12)
    ap.add_argument("--z", type=float, nargs="+", default=[6.0, 8.0, 10.0])
    # 1 = every control step; 12 = hourly, the thesis's actual setting;
    # 288 = once per episode, i.e. never refreshed after the first solve.
    ap.add_argument("--refresh", type=int, nargs="+", default=[1, 3, 12, 48, 288])
    ap.add_argument("--load", type=float, default=0.40)
    ap.add_argument("--evs", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=Path("results/staleness_sweep.json"))
    args = ap.parse_args()

    print(f"staleness sweep | Z={args.z}% | refresh every {args.refresh} steps")
    print(f"load {args.load} | {args.evs:.0f} EVs/station | {args.episodes} episodes")
    print("correct network model throughout; only the base point ages\n")

    t0, out = time.perf_counter(), {"z": args.z, "refresh": args.refresh, "cells": {}}

    for z in args.z:
        base_cfg = ExperimentConfig.stiffness(z, evs_per_station=args.evs,
                                              load_scale=args.load)
        print(f"Z={z:4.1f}%")
        for sname, scls in SOURCES.items():
            env = ChargingFeederEnv(base_cfg)
            raw = evaluate(scls(env), env, base_cfg, n_episodes=args.episodes,
                           run_label=EVAL_LABEL)["aggregate"]
            row = {"raw": {"viol": raw["voltage_violation_step_rate_mean"],
                           "soc": raw["frac_meeting_soc_target_mean"]}}
            line = f"   {sname:<14} raw={row['raw']['viol']:.4f}/{row['raw']['soc']:.3f}"

            for r in args.refresh:
                cfg = replace(base_cfg,
                              safety=replace(base_cfg.safety,
                                             sensitivity_refresh_steps=r))
                env = ChargingFeederEnv(cfg)
                agent = ProjectedAgent(scls(env), env, cfg)
                agg = evaluate(agent, env, cfg, n_episodes=args.episodes,
                               run_label=EVAL_LABEL)["aggregate"]
                s = agent.stats.summary()
                row[str(r)] = {
                    "viol": agg["voltage_violation_step_rate_mean"],
                    "soc": agg["frac_meeting_soc_target_mean"],
                    "infeasible": s["projection_infeasible_rate"],
                    "ms_step": agg["mean_step_time_ms_mean"],
                }
                line += f"   {r}={row[str(r)]['viol']:.4f}/{row[str(r)]['soc']:.3f}"
            out["cells"].setdefault(str(z), {})[sname] = row
            print(line)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, default=float))

    print("\n" + "=" * 78)
    print("Violation step rate against refresh interval (correct model throughout)")
    print("=" * 78)
    hdr = "".join(f"{('every ' + str(r)):>12}" for r in args.refresh)
    print(f"{'Z%':>5}{'source':>16}{'raw':>10}{hdr}")
    for z in args.z:
        for sname in SOURCES:
            row = out["cells"][str(z)][sname]
            print(f"{z:>5.1f}{sname:>16}{row['raw']['viol']:>10.4f}"
                  + "".join(f"{row[str(r)]['viol']:>12.4f}" for r in args.refresh))
    print(f"\n({time.perf_counter() - t0:.0f}s)  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
