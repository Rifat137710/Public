#!/usr/bin/env python3
"""Generate a small synthetic dataset in ClearSAR-like layout.

Useful for smoke-testing the pipeline before pointing it at the real data, and
for sanity-checking that your annotation loader path works: it writes quicklook
PNGs composed exactly as the Sentinel-1 spec describes plus a COCO JSON of the
interference footprints.

    python scripts/make_demo_dataset.py --out demo/ -n 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearsar_rfi import synth  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("-n", type=int, default=12, help="number of scenes")
    ap.add_argument("--size", type=int, default=384)
    ap.add_argument("--looks", type=float, default=4.0)
    ap.add_argument("--levels", type=float, nargs="+",
                    default=[0.2, 0.5, 1.0, 3.0, 8.0],
                    help="interference levels cycled across the scenes, dB")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    out = Path(args.out)
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    morphologies = ["stripe", "patch", "periodic"]
    images, annotations, manifest = [], [], []

    for i in range(args.n):
        level = args.levels[i % len(args.levels)]
        morph = morphologies[i % len(morphologies)]
        cfg = synth.SynthConfig(shape=(args.size, args.size), looks=args.looks,
                                seed=args.seed + 1000 * i)
        scene = synth.make_scene(level, morph, channel=1, cfg=cfg)

        name = f"scene_{i:03d}_{morph}_{level:g}dB.png"
        Image.fromarray(scene.quicklook.dn.astype(np.uint8), mode="RGB").save(img_dir / name)

        b = scene.truth_box
        images.append({"id": i, "file_name": name,
                       "height": args.size, "width": args.size})
        annotations.append({
            "id": i, "image_id": i, "category_id": 1, "iscrowd": 0,
            "bbox": [b.x1, b.y1, b.width, b.height], "area": b.area,
        })
        manifest.append({"file_name": name, "injected_db": level, "morphology": morph,
                         **scene.realised})

    coco = {"images": images, "annotations": annotations,
            "categories": [{"id": 1, "name": "rfi"}]}
    (out / "annotations.json").write_text(json.dumps(coco, indent=1))
    (out / "truth.json").write_text(json.dumps(manifest, indent=1))

    print(f"wrote {args.n} scenes to {img_dir}")
    print(f"       annotations -> {out / 'annotations.json'}")
    print(f"       ground truth -> {out / 'truth.json'}")
    print("\nnext:")
    print(f"  python scripts/check_composition.py --images {img_dir}")
    print(f"  python scripts/triage_boxes.py --images {img_dir} "
          f"--annotations {out / 'annotations.json'} --out demo_triage.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
