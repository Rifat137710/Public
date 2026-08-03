#!/usr/bin/env python3
"""Step 3: export the physics feature stack for detector training.

Writes one compressed ``.npz`` per quicklook holding the multi-channel stack
described in ``clearsar_rfi.features.FEATURE_NAMES``.  Planes 0-2 are the
untouched R/G/B, so an RGB-pretrained backbone can be fine-tuned by inflating
its stem convolution and seeding the extra input channels at zero -- training
then starts from exactly the pretrained behaviour and improves from there.

    python scripts/build_features.py \\
        --images /path/to/clearsar/train/images --out features/ --workers 4
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearsar_rfi import features, io  # noqa: E402


def _process(path_str: str, out_dir: str, with_spectral: bool, normalise: bool) -> str:
    ql = io.load_quicklook(path_str)
    planes = features.build_stack(ql, with_spectral=with_spectral)
    stack = features.stack_array(planes)
    if normalise:
        stack = features.normalise(stack)
    out = Path(out_dir) / (Path(path_str).stem + ".npz")
    np.savez_compressed(out, stack=stack.astype(np.float32),
                        names=np.array(features.FEATURE_NAMES))
    return out.name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-spectral", action="store_true")
    ap.add_argument("--raw", action="store_true",
                    help="skip per-plane robust normalisation")
    args = ap.parse_args()

    paths = io.find_images(args.images)
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        print(f"no images under {args.images}", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    todo = [str(p) for p in paths]
    if args.workers > 1:
        with ProcessPoolExecutor(args.workers) as pool:
            futures = [
                pool.submit(_process, p, str(out_dir), not args.no_spectral, not args.raw)
                for p in todo
            ]
            for i, fut in enumerate(futures, 1):
                fut.result()
                if i % 50 == 0:
                    print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    else:
        for i, p in enumerate(todo, 1):
            _process(p, str(out_dir), not args.no_spectral, not args.raw)
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)

    print(f"wrote {len(todo)} stacks of {len(features.FEATURE_NAMES)} planes to {out_dir} "
          f"in {time.time() - t0:.0f}s")
    print("plane order:", ", ".join(features.FEATURE_NAMES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
