#!/usr/bin/env python3
"""Step 0: verify what your quicklook channels actually contain.

Run this before anything else.  The Sentinel-1 spec says dual-pol quicklooks put
the first polarisation in R, the second in G, and their mean in B -- but a
re-exported or re-stretched dataset can differ, and single-pol scenes are
greyscale and carry no polarimetric information at all.  Everything downstream
assumes the spec composition, so it is worth ten seconds to confirm it.

Also reports the fitted speckle model, which settles whether digital numbers
behave as amplitude or intensity -- the 8-bit display stretch applied after
power detection is not documented, so it has to be measured.

    python scripts/check_composition.py --images /path/to/clearsar/train/images -n 40
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearsar_rfi import io, unmix  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True, help="directory of quicklook PNGs")
    ap.add_argument("-n", type=int, default=25, help="how many images to sample")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    paths = io.find_images(args.images)
    if not paths:
        print(f"no images found under {args.images}", file=sys.stderr)
        return 1
    rng = np.random.default_rng(args.seed)
    sample = [paths[i] for i in rng.choice(len(paths), min(args.n, len(paths)), replace=False)]

    coeffs, r2s, modes, looks, n_single = [], [], [], [], 0
    print(f"{'image':<44} {'a(R)':>7} {'b(G)':>7} {'c':>7} {'R^2':>8} {'mode':>10} {'ENL':>6}")
    print("-" * 92)
    for p in sorted(sample):
        ql = io.load_quicklook(p)
        if ql.single_pol:
            n_single += 1
            print(f"{p.name[:43]:<44} {'--':>7} {'--':>7} {'--':>7} {'--':>8} "
                  f"{'SINGLE-POL':>10} {'--':>6}")
            continue
        comp = unmix.check_composition(ql.dn)
        um = unmix.unmix(ql.dn)
        coeffs.append((comp.a, comp.b, comp.c))
        r2s.append(comp.r2)
        modes.append(um.detection)
        looks.append(um.model_p2.looks)
        print(f"{p.name[:43]:<44} {comp.a:7.4f} {comp.b:7.4f} {comp.c:7.2f} {comp.r2:8.5f} "
              f"{um.detection:>10} {um.model_p2.looks:6.1f}")

    print("-" * 92)
    if n_single:
        print(f"{n_single}/{len(sample)} sampled scenes are single-polarisation: for these the "
              "ratio and PC2 channels are identically zero, so only the directional, "
              "statistical and spectral decompositions apply.")
    if not coeffs:
        print("no dual-pol scenes sampled; nothing further to report.")
        return 0

    a, b, c = np.mean(coeffs, axis=0)
    print(f"mean composition : B = {a:.4f}*R + {b:.4f}*G + {c:.2f}   "
          f"(mean R^2 = {np.mean(r2s):.5f})")
    if abs(a - 0.5) < 0.05 and abs(b - 0.5) < 0.05 and np.mean(r2s) > 0.99:
        print("VERDICT: matches the spec, B = (R+G)/2. The blue channel is redundant -- "
              "your RGB has two real degrees of freedom, not three.")
    else:
        print("VERDICT: does NOT match B=(R+G)/2. Re-derive the un-mixing before using "
              "clearsar_rfi.unmix; the ratio channel assumes R and G are the two "
              "polarisations under a shared stretch.")

    mode = max(set(modes), key=modes.count)
    print(f"speckle model    : DN behaves as {mode.upper()}, "
          f"median ENL ~= {np.median(looks):.1f} looks")
    print(f"                   per-pixel amplitude CV ~= {0.52 / np.sqrt(np.median(looks)):.3f}; "
          f"integrating N pixels along a stripe scales this by 1/sqrt(N).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
