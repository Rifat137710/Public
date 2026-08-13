"""G0 -- is there a control problem at this operating point, or not?

`scripts/projected_heuristics.py` showed that at the Stage 1 operating point a
greedy charger passed through the safety projection reaches SoC 0.709 at zero
violations, against 0.089 for the trained policy. If a zero-intelligence request
is already near the ceiling, no learner can earn its place there -- and the
conference paper cannot claim one.

That is a property of the *operating point*, not of RL. This sweeps load and EV
penetration looking for a regime where it stops being true, using heuristics
only. No training, no GPU.

Three diagnostics per grid point:

  retention  SoC(uncoordinated+proj) / SoC(uncoordinated)
             How much service the projection has to give up. Near 1.0 means the
             feeder has slack and the safety layer costs nothing.

  sequencing SoC(urgency+proj) - SoC(uncoordinated+proj)
             THE decisive number. Both are projected, both are myopic; they
             differ only in *which* stations they ask to charge. A material gap
             means ordering matters -- which is exactly what a policy can learn
             and a greedy request cannot express.

  headroom   1 - SoC(uncoordinated+proj)
             What is left on the table for any controller at all.

    python scripts/operating_point_sweep.py --episodes 8
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

from safesac.agents import DroopAgent, UncoordinatedAgent, UrgencyAgent, ZeroAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv
from safesac.evaluate import evaluate
from safesac.projected import ProjectedAgent

EVAL_LABEL = "stage1_eval"

# Enough separation to be worth building a paper on, not so much that we are
# chasing noise. Set before looking at the numbers.
SEQUENCING_THRESHOLD = 0.05
RETENTION_CEILING = 0.85


def build(name, cfg):
    env = ChargingFeederEnv(cfg)
    if name == "zero":
        return ZeroAgent(env), env
    if name == "uncoordinated":
        return UncoordinatedAgent(env), env
    if name == "droop":
        return DroopAgent(env), env
    if name == "urgency":
        return UrgencyAgent(env), env
    if name == "uncoordinated+proj":
        return ProjectedAgent(UncoordinatedAgent(env), env, cfg), env
    if name == "urgency+proj":
        return ProjectedAgent(UrgencyAgent(env), env, cfg), env
    raise KeyError(name)


METHODS = ["zero", "uncoordinated", "droop", "urgency",
           "uncoordinated+proj", "urgency+proj"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=8)
    ap.add_argument("--loads", type=float, nargs="+", default=[0.40, 0.55, 0.70])
    ap.add_argument("--evs", type=float, nargs="+", default=[30.0, 60.0, 100.0])
    ap.add_argument("--variant", default="weak")
    ap.add_argument("--out", type=Path, default=Path("results/operating_point_sweep.json"))
    args = ap.parse_args()

    print(f"G0 operating-point sweep | {args.variant} | {args.episodes} episodes/cell")
    print(f"load scales {args.loads} x EVs/station {args.evs}\n")

    grid, t0 = [], time.perf_counter()
    for load in args.loads:
        for evs in args.evs:
            base = ExperimentConfig.stage1(args.variant, evs_per_station=evs)
            cfg = replace(base, scenario=replace(base.scenario, load_scale=load))

            cell = {"load_scale": load, "evs_per_station": evs,
                    "fingerprint": cfg.fingerprint(), "methods": {}}
            for name in METHODS:
                agent, env = build(name, cfg)
                agg = evaluate(agent, env, cfg, n_episodes=args.episodes,
                               run_label=EVAL_LABEL)["aggregate"]
                row = {
                    "viol": agg["voltage_violation_step_rate_mean"],
                    "soc": agg["frac_meeting_soc_target_mean"],
                    "cost": agg["net_cost_usd_mean"],
                    "vmin": agg["vmin_pu_mean"],
                    "throughput": agg["throughput_kwh_mean"],
                    "n_evs": agg["n_evs_departed_mean"],
                }
                if hasattr(agent, "stats"):
                    s = agent.stats.summary()
                    row["infeasible"] = s["projection_infeasible_rate"]
                    row["frozen"] = s["projection_frozen_step_rate"]
                cell["methods"][name] = row

            m = cell["methods"]
            retention = m["uncoordinated+proj"]["soc"] / max(m["uncoordinated"]["soc"], 1e-9)
            sequencing = m["urgency+proj"]["soc"] - m["uncoordinated+proj"]["soc"]
            cell["diagnostics"] = {
                "retention": retention,
                "sequencing_gain": sequencing,
                "headroom": 1.0 - m["uncoordinated+proj"]["soc"],
                "idle_clean": m["zero"]["viol"] == 0.0,
                "projection_safe": m["uncoordinated+proj"]["viol"] == 0.0,
                "safety_problem_exists": m["uncoordinated"]["viol"] >= 0.02,
            }
            d = cell["diagnostics"]
            d["interesting"] = bool(
                d["idle_clean"] and d["projection_safe"] and d["safety_problem_exists"]
                and (sequencing >= SEQUENCING_THRESHOLD or retention <= RETENTION_CEILING)
            )
            grid.append(cell)

            print(f"load {load:.2f} | {evs:3.0f} EVs/station  "
                  f"idle_viol={m['zero']['viol']:.4f}  "
                  f"uncoord={m['uncoordinated']['viol']:.4f}/{m['uncoordinated']['soc']:.3f}  "
                  f"u+proj={m['uncoordinated+proj']['viol']:.4f}/{m['uncoordinated+proj']['soc']:.3f}  "
                  f"urg+proj={m['urgency+proj']['viol']:.4f}/{m['urgency+proj']['soc']:.3f}")
            print(f"{'':16s}retention={retention:.3f}  sequencing={sequencing:+.4f}  "
                  f"headroom={d['headroom']:.3f}  infeas={m['uncoordinated+proj'].get('infeasible', float('nan')):.4f}"
                  f"   {'<-- CONTROL PROBLEM' if d['interesting'] else ''}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"episodes": args.episodes, "variant": args.variant,
         "sequencing_threshold": SEQUENCING_THRESHOLD,
         "retention_ceiling": RETENTION_CEILING, "grid": grid},
        indent=2, default=float))

    # ---- verdict ---------------------------------------------------------
    print("\n" + "=" * 78)
    good = [c for c in grid if c["diagnostics"]["interesting"]]
    if good:
        best = max(good, key=lambda c: c["diagnostics"]["sequencing_gain"])
        print(f"G0 VERDICT: {len(good)}/{len(grid)} cells have a control problem.")
        print(f"Best: load {best['load_scale']:.2f}, {best['evs_per_station']:.0f} "
              f"EVs/station -- sequencing gain "
              f"{best['diagnostics']['sequencing_gain']:+.4f}, retention "
              f"{best['diagnostics']['retention']:.3f}")
        print("The paper can claim safe RL. Train there, not at the Stage 1 point.")
    else:
        print("G0 VERDICT: no cell shows a control problem.")
        print("Greedy + projection is at the ceiling everywhere tested. The paper")
        print("is about the safety layer, not about the learner -- say so plainly.")
    print(f"({time.perf_counter() - t0:.0f}s)  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
