"""Pick the Kerber operating point by measurement, not by assumption.

`case33bw`'s operating point was chosen this way in Stage 1 and the choice
turned out to matter more than anything else in the thesis: load 0.40 / margin
0.010 was selected for projection feasibility and, in doing so, trivialised the
control task. The same discipline applies here, with the same two requirements:

  1. **Idle must be strictly safe.** If the feeder violates with every station
     at zero, violations cannot be attributed to a charging decision and audit
     A4 is dead. This is the binding requirement.
  2. **Uncoordinated must violate.** If a greedy charger cannot break the band,
     the safety layer has nothing to do and the feeder proves nothing.

The window between those two is the operating point. Anything outside it is not
a testbed, it is a rigged demonstration in one direction or the other.

    python scripts/characterize_kerber.py --episodes 6
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safesac.agents import UncoordinatedAgent, ZeroAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv
from safesac.evaluate import evaluate

EVAL_LABEL = "transfer_eval"

# `case33bw` at the stage-1 operating point: uncoordinated violates on 6.26 % of
# steps while meeting 80.4 % of SoC targets. A replication has to be *like for
# like* -- a second feeder tuned to be harder would inflate the effect and one
# tuned to be easier would hide it -- so the target here is the cell closest to
# that violation rate, not the cell with the largest.
REF_UNCOORD_VIOL = 0.0626
REF_UNCOORD_SOC = 0.8041
MIN_UNCOORD_SOC = 0.50


def _distance_from_reference(row) -> float:
    """How unlike `case33bw` this cell is, on both axes at once.

    Matching the violation rate alone is not enough. At 4 EVs per station the
    Kerber feeder reproduces the reference violation rate almost exactly while
    meeting 98.7 % of SoC targets -- there is no service left for the projection
    to trade away, so the retention measurement would have no dynamic range and
    the cell would look like a success for trivial reasons.
    """
    return ((row["uncoord_viol"] - REF_UNCOORD_VIOL) / REF_UNCOORD_VIOL) ** 2 + (
        (row["uncoord_soc"] - REF_UNCOORD_SOC) / REF_UNCOORD_SOC
    ) ** 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=6)
    ap.add_argument("--z", type=float, nargs="+", default=[0.5, 1.0, 2.0])
    ap.add_argument("--load", type=float, nargs="+", default=[0.60, 0.70, 0.80])
    ap.add_argument("--kva", type=float, nargs="+", default=[22.0])
    # Fleet size has to be swept, not inherited. `case33bw` runs 30 EVs against
    # an 80 kVA hub -- 2.7 kVA per vehicle. Carrying 30 across to a 22 kVA LV
    # charge point saturates it: uncoordinated meets 4.5 % of SoC targets at
    # every stiffness and load, so "service retained by the projection" would be
    # a percentage of nothing and the whole service axis would be dead.
    ap.add_argument("--evs", type=float, nargs="+", default=[30.0])
    ap.add_argument("--out", type=Path,
                    default=Path("results/kerber_operating_point.json"))
    args = ap.parse_args()

    t0 = time.perf_counter()
    rows = []
    print(f"kerber_dorfnetz | {args.episodes} episodes per cell\n")
    print(f"{'Z%':>5}{'load':>7}{'kVA':>6}{'EVs':>6}{'idle viol':>11}{'idle vmin':>11}"
          f"{'uncoord viol':>14}{'uncoord SoC':>13}{'verdict':>10}")

    for kva in args.kva:
      for evs in args.evs:
        for z in args.z:
            for load in args.load:
                cfg = ExperimentConfig.kerber(substation_z_pct=z, load_scale=load,
                                              station_kva=kva,
                                              evs_per_station=evs)
                env = ChargingFeederEnv(cfg)
                idle = evaluate(ZeroAgent(env), env, cfg, n_episodes=args.episodes,
                                run_label=EVAL_LABEL)["aggregate"]
                env = ChargingFeederEnv(cfg)
                unc = evaluate(UncoordinatedAgent(env), env, cfg,
                               n_episodes=args.episodes,
                               run_label=EVAL_LABEL)["aggregate"]

                iv = idle["voltage_violation_step_rate_mean"]
                uv = unc["voltage_violation_step_rate_mean"]
                us = unc["frac_meeting_soc_target_mean"]
                ok = iv == 0.0 and uv > 0.01 and us >= MIN_UNCOORD_SOC
                verdict = ("USABLE" if ok else "idle!" if iv > 0.0
                           else "sat." if us < MIN_UNCOORD_SOC else "flat")
                rows.append({"z": z, "load": load, "kva": kva, "evs": evs,
                             "idle_viol": iv, "idle_vmin": idle["vmin_pu_mean"],
                             "uncoord_viol": uv,
                             "uncoord_soc": unc["frac_meeting_soc_target_mean"],
                             "usable": ok})
                print(f"{z:>5.1f}{load:>7.2f}{kva:>6.0f}{evs:>6.0f}{iv:>11.4f}"
                      f"{idle['vmin_pu_mean']:>11.4f}{uv:>14.4f}"
                      f"{unc['frac_meeting_soc_target_mean']:>13.3f}{verdict:>10}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"cells": rows}, indent=2, default=float))

    usable = [r for r in rows if r["usable"]]
    print(f"\n{len(usable)}/{len(rows)} cells usable")
    if usable:
        best = min(usable, key=_distance_from_reference)
        print(f"pick: Z={best['z']}% load={best['load']} kVA={best['kva']:.0f} "
              f"EVs={best['evs']:.0f}  "
              f"idle {best['idle_viol']:.4f} @ vmin {best['idle_vmin']:.4f}  "
              f"uncoord {best['uncoord_viol']:.4f} / SoC {best['uncoord_soc']:.3f}")
    else:
        print("no usable cell -- widen the sweep before running anything else")
    print(f"({time.perf_counter() - t0:.0f}s)  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
