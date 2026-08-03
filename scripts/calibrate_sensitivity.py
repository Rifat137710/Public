#!/usr/bin/env python3
"""Step 2: measure the detectability floor of the quicklook product.

Injects interference at a known interference-to-signal ratio into synthetic
dual-pol quicklooks built with the same detection, multilooking, 8-bit
quantisation and B=(R+G)/2 composition as the real product, then runs the same
triage metrics used on the real boxes.

The measurement is **paired**: every scene is generated twice from one speckle
realisation, once with the interference and once without, and each metric is
compared against its own interference-free twin at the identical box.  This
matters more than it sounds.  Raw box-versus-surround contrast is dominated by
whatever terrain happens to lie under the box -- on the default synthetic scene
the cross-pol z-score sits near 84 before any interference exists at all -- so
an unpaired sweep measures terrain, not sensitivity.

Two things usually fall out, and both are worth knowing before tuning a model:

* the polarimetric ratio starts from a far lower terrain baseline than either
  single channel, because terrain is common-mode across polarisations and
  interference is not;
* the level at which each metric separates is the floor below which a labelled
  box carries no recoverable signature *at this product level* -- which is a
  property of the 8-bit quicklook, not of your detector.

    python scripts/calibrate_sensitivity.py --out sensitivity.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearsar_rfi import synth, triage  # noqa: E402

METRICS = ("abs_z_p1", "abs_z_p2", "abs_z_ratio",
           "stripe_snr_ratio", "stripe_snr_p2", "abs_dcv_p2")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", type=float, nargs="+",
                    default=[0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 4.0, 8.0],
                    help="injected interference-to-signal ratios, dB")
    ap.add_argument("--morphologies", nargs="+", default=["stripe", "patch", "periodic"])
    ap.add_argument("--channel", type=int, default=1,
                    help="0 = co-pol, 1 = cross-pol (default; nearest the noise floor)")
    ap.add_argument("--repeats", type=int, default=5, help="scenes per (level, morphology)")
    ap.add_argument("--looks", type=float, default=4.0)
    ap.add_argument("--size", type=int, default=384)
    ap.add_argument("--margin", type=float, default=1.15,
                    help="injected metric must exceed its twin by this factor to count")
    ap.add_argument("--out", default="sensitivity.csv")
    args = ap.parse_args()

    rows: list[dict] = []
    for morph in args.morphologies:
        for level in args.levels:
            for rep in range(args.repeats):
                cfg = synth.SynthConfig(
                    shape=(args.size, args.size), looks=args.looks, seed=1000 * rep + 7
                )
                scene = synth.make_scene(level, morph, args.channel, cfg)
                inj = triage.measure_box(scene.quicklook, scene.truth_box,
                                         with_spectral=False)
                base = triage.measure_box(scene.baseline, scene.truth_box,
                                          with_spectral=False)
                row = {
                    "morphology": morph, "injected_db": level, "repeat": rep,
                    "channel": args.channel, **scene.realised,
                }
                for m in METRICS:
                    row[f"{m}_injected"] = inj.get(m, np.nan)
                    row[f"{m}_baseline"] = base.get(m, np.nan)
                row["d_ratio_db_injected"] = inj.get("d_ratio_db", np.nan)
                row["d_ratio_db_baseline"] = base.get("d_ratio_db", np.nan)
                rows.append(row)
            print(f"  {morph:<9} {level:5.2f} dB done", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"\nwrote {len(df)} paired scenes to {args.out}\n")

    base_levels = df.groupby("morphology")[[f"{m}_baseline" for m in METRICS]].median()
    print("interference-free baseline of each metric (pure terrain response):")
    print(base_levels.to_string(float_format=lambda v: f"{v:8.2f}"))
    print("\nThe gap between the single-channel and ratio baselines is the terrain "
          "suppression the polarimetric un-mixing buys you.\n")

    print(f"paired win rate: fraction of scenes where injected > {args.margin:g} x its "
          "interference-free twin\n")
    header = (f"{'morph':<10}{'dB':>6}{'dDN':>7}{'unchgd':>8}  "
              + "".join(f"{m.replace('abs_', ''):>18}" for m in METRICS))
    print(header)
    print("-" * len(header))
    floors: dict[tuple[str, str], float] = {}
    for morph in args.morphologies:
        for level in args.levels:
            sel = df[(df["morphology"] == morph) & (df["injected_db"] == level)]
            if sel.empty:
                continue
            line = (f"{morph:<10}{level:6.2f}{sel['dn_delta_median'].median():7.1f}"
                    f"{sel['dn_unchanged_fraction'].median():8.2f}  ")
            for m in METRICS:
                inj, base = sel[f"{m}_injected"], sel[f"{m}_baseline"]
                rate = float((inj > args.margin * base).mean())
                line += f"{rate:18.2f}"
                if rate >= 1.0 and (morph, m) not in floors:
                    floors[(morph, m)] = level
            print(line)
        print()

    print("detection floor -- lowest swept level at which every repeat separated:")
    for morph in args.morphologies:
        parts = [f"{m.replace('abs_', '')}={floors.get((morph, m), float('nan')):g}dB"
                 for m in METRICS]
        print(f"  {morph:<10} " + "  ".join(parts))

    print("\n'dDN' is the median number of digital numbers the interference actually moved "
          "the 8-bit image by inside its footprint, and 'unchgd' the fraction of its pixels "
          "the quantiser left untouched. Rows where those show 0 and ~1 but a win rate is "
          "still 1.00 are detections of signal that is literally absent from most pixels.")
    print("\nCompare these floors against the contrasts triage_boxes.py measures on the real "
          "ghost boxes: annotations below the floor are label noise at this product level.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
