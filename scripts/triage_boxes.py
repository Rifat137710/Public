#!/usr/bin/env python3
"""Step 1: measure every annotated box, and find out which ghosts are recoverable.

For each ClearSAR bounding box this measures the contrast in the two
polarimetric channels and their ratio, the departure of local speckle statistics
from the fitted model, the Radon matched-filter SNR of any linear structure, and
block-wise spectral anisotropy -- then repeats the whole thing on control boxes
placed where nothing is annotated, to get the null distribution of every metric
on this data.

The summary partitions the annotations by the mechanism that makes them
findable.  Boxes in the "none" bucket have no measurable signature in an 8-bit
quicklook: that is a property of the product level, not of your detector, and it
is the number to quote when reporting recall.

    python scripts/triage_boxes.py \\
        --images  /path/to/clearsar/train/images \\
        --annotations /path/to/clearsar/train/annotations.json \\
        --out triage.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearsar_rfi import io, triage  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True)
    ap.add_argument("--annotations", required=True)
    ap.add_argument("--out", default="triage.csv")
    ap.add_argument("--limit", type=int, default=0, help="stop after N images (0 = all)")
    ap.add_argument("--controls-per-box", type=int, default=2)
    ap.add_argument("--quantile", type=float, default=0.99,
                    help="control-box quantile used as the per-metric threshold")
    ap.add_argument("--no-spectral", action="store_true",
                    help="skip block-wise FFT features (much faster)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    rows: list[dict] = []
    n_img = 0
    t0 = time.time()

    for ql in io.iter_dataset(args.images, args.annotations):
        if not ql.boxes:
            continue
        rows.extend(
            triage.triage_image(
                ql, rng=rng,
                controls_per_box=args.controls_per_box,
                with_spectral=not args.no_spectral,
            )
        )
        n_img += 1
        if n_img % 25 == 0:
            print(f"  {n_img} images, {len(rows)} rows, {time.time() - t0:.0f}s", flush=True)
        if args.limit and n_img >= args.limit:
            break

    if not rows:
        print("no annotated boxes found -- check --images / --annotations paths",
              file=sys.stderr)
        return 1

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"\nwrote {len(df)} rows from {n_img} images to {args.out}")

    result = triage.summarise(df, quantile=args.quantile)
    print(f"\nlabelled boxes : {result['n_labels']}")
    print(f"control boxes  : {result['n_controls']}")
    print(f"\nper-metric thresholds (control-box q={args.quantile}):")
    for metric, thr in sorted(result["thresholds"].items()):
        print(f"  {metric:<22} {thr:10.3f}")

    print("\nboxes exceeding threshold, by family (families overlap):")
    for fam, n in sorted(result["families"].items(), key=lambda kv: -kv[1]):
        print(f"  {fam:<14} {n:6d}  ({n / max(result['n_labels'], 1):6.1%})")

    print("\nattributed mechanism (first family that fires, brightness first):")
    for mech, n in sorted(result["mechanisms"].items(), key=lambda kv: -kv[1]):
        print(f"  {mech:<14} {n:6d}  ({n / max(result['n_labels'], 1):6.1%})")

    frac = result["recoverable_fraction"]
    print(f"\nrecoverable at all : {frac:.1%}")
    print(f"no signature       : {1 - frac:.1%}  <- label noise floor for this product level")

    lab = result["table"]
    ghosts = lab[lab["mechanism"] == "none"]
    if len(ghosts):
        print("\nghost boxes (no measurable signature) -- median measured contrast:")
        for col in ("d_p1_db", "d_p2_db", "d_ratio_db"):
            if col in ghosts:
                print(f"  {col:<12} {ghosts[col].median():+.3f} dB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
