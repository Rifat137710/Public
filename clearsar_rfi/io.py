"""Loading quicklook PNGs and bounding-box annotations.

The ClearSAR distribution ships quicklooks as PNGs plus bounding boxes, but the
exact annotation container can differ between the challenge starter pack and any
local re-export.  ``load_annotations`` therefore sniffs the layout and accepts
COCO JSON, YOLO ``.txt`` sidecars, Pascal-VOC XML and flat CSV.
"""

from __future__ import annotations

import csv
import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_SUFFIXES = {".png", ".PNG", ".tif", ".tiff", ".jpg", ".jpeg"}


@dataclass
class Box:
    """An axis-aligned bounding box in pixel coordinates (x1, y1 inclusive)."""

    x1: float
    y1: float
    x2: float
    y2: float
    label: str = "rfi"
    score: float | None = None

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def clipped(self, shape: tuple[int, int]) -> "Box":
        h, w = shape[:2]
        return Box(
            float(np.clip(self.x1, 0, w - 1)),
            float(np.clip(self.y1, 0, h - 1)),
            float(np.clip(self.x2, 0, w - 1)),
            float(np.clip(self.y2, 0, h - 1)),
            self.label,
            self.score,
        )

    def slices(self, shape: tuple[int, int], pad: int = 0) -> tuple[slice, slice]:
        """Row/column slices for indexing an array, optionally padded outwards."""
        h, w = shape[:2]
        y1 = int(np.clip(np.floor(self.y1) - pad, 0, h))
        y2 = int(np.clip(np.ceil(self.y2) + pad, 0, h))
        x1 = int(np.clip(np.floor(self.x1) - pad, 0, w))
        x2 = int(np.clip(np.ceil(self.x2) + pad, 0, w))
        return slice(y1, max(y2, y1 + 1)), slice(x1, max(x2, x1 + 1))


@dataclass
class Quicklook:
    """A loaded quicklook: raw 8-bit digital numbers plus provenance flags."""

    dn: np.ndarray  # (H, W, 3) float32 digital numbers, 0..255
    name: str
    single_pol: bool = False  # True when the product was single-polarisation
    boxes: list[Box] = field(default_factory=list)

    @property
    def shape(self) -> tuple[int, int]:
        return self.dn.shape[0], self.dn.shape[1]


def load_quicklook(path: str | os.PathLike, boxes: list[Box] | None = None) -> Quicklook:
    """Read a quicklook PNG into float32 digital numbers in [0, 255].

    Single-polarisation products are greyscale; they are broadcast to three
    identical channels and flagged, because none of the polarimetric
    decompositions in :mod:`clearsar_rfi.unmix` carry information for them.
    """
    path = Path(path)
    img = Image.open(path)
    if img.mode in ("L", "I;16", "I"):
        arr = np.asarray(img.convert("F"), dtype=np.float32)
        if arr.max() > 255.0:  # 16-bit greyscale, rescale to a common DN range
            arr = arr * (255.0 / max(arr.max(), 1.0))
        dn = np.repeat(arr[:, :, None], 3, axis=2)
        single_pol = True
    else:
        dn = np.asarray(img.convert("RGB"), dtype=np.float32)
        # A 3-band file can still be a replicated greyscale (single-pol export).
        single_pol = bool(
            np.array_equal(dn[:, :, 0], dn[:, :, 1])
            and np.array_equal(dn[:, :, 1], dn[:, :, 2])
        )
    return Quicklook(dn=dn, name=path.name, single_pol=single_pol, boxes=list(boxes or []))


def find_images(root: str | os.PathLike) -> list[Path]:
    """Recursively collect quicklook image files under ``root``, sorted by name."""
    root = Path(root)
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*") if p.suffix in IMAGE_SUFFIXES)


# --------------------------------------------------------------------------- #
# Annotations
# --------------------------------------------------------------------------- #

def load_annotations(
    path: str | os.PathLike,
    image_shapes: dict[str, tuple[int, int]] | None = None,
) -> dict[str, list[Box]]:
    """Load bounding boxes, auto-detecting the annotation container.

    Parameters
    ----------
    path
        A COCO JSON file, a CSV file, or a directory of YOLO ``.txt`` / VOC
        ``.xml`` sidecars.
    image_shapes
        ``{image_name: (H, W)}``.  Required only for YOLO annotations, whose
        coordinates are normalised and cannot be de-normalised without it.

    Returns
    -------
    dict
        Maps image file name (basename) to a list of :class:`Box`.
    """
    path = Path(path)
    if path.is_dir():
        txts = sorted(path.rglob("*.txt"))
        xmls = sorted(path.rglob("*.xml"))
        jsons = sorted(path.rglob("*.json"))
        if jsons and not (txts or xmls):
            return _load_coco(jsons[0])
        if xmls:
            return _load_voc(xmls)
        if txts:
            return _load_yolo(txts, image_shapes or {})
        raise FileNotFoundError(f"no .json/.txt/.xml annotations found under {path}")
    if path.suffix.lower() == ".json":
        return _load_coco(path)
    if path.suffix.lower() in (".csv", ".tsv"):
        return _load_csv(path)
    if path.suffix.lower() == ".xml":
        return _load_voc([path])
    if path.suffix.lower() == ".txt":
        return _load_yolo([path], image_shapes or {})
    raise ValueError(f"unrecognised annotation file type: {path}")


def _load_coco(path: Path) -> dict[str, list[Box]]:
    with open(path) as fh:
        data = json.load(fh)
    if "images" not in data or "annotations" not in data:
        raise ValueError(f"{path} is JSON but not COCO-shaped")
    id_to_name = {im["id"]: Path(im["file_name"]).name for im in data["images"]}
    cat = {c["id"]: c.get("name", str(c["id"])) for c in data.get("categories", [])}
    out: dict[str, list[Box]] = {n: [] for n in id_to_name.values()}
    for ann in data["annotations"]:
        x, y, w, h = ann["bbox"]  # COCO: [x_min, y_min, width, height]
        name = id_to_name.get(ann["image_id"])
        if name is None:
            continue
        out[name].append(
            Box(float(x), float(y), float(x + w), float(y + h),
                cat.get(ann.get("category_id"), "rfi"))
        )
    return out


def _load_yolo(paths: list[Path], shapes: dict[str, tuple[int, int]]) -> dict[str, list[Box]]:
    out: dict[str, list[Box]] = {}
    for p in paths:
        stem = p.stem
        shape = None
        for name, s in shapes.items():
            if Path(name).stem == stem:
                shape = s
                key = name
                break
        if shape is None:
            raise KeyError(
                f"YOLO annotations are normalised; no image shape supplied for '{stem}'. "
                "Pass image_shapes={image_name: (H, W)}."
            )
        h, w = shape
        boxes: list[Box] = []
        for line in p.read_text().splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            cls, cx, cy, bw, bh = parts[0], *map(float, parts[1:5])
            boxes.append(
                Box((cx - bw / 2) * w, (cy - bh / 2) * h,
                    (cx + bw / 2) * w, (cy + bh / 2) * h, str(cls))
            )
        out[key] = boxes
    return out


def _load_voc(paths: list[Path]) -> dict[str, list[Box]]:
    out: dict[str, list[Box]] = {}
    for p in paths:
        root = ET.parse(p).getroot()
        fn = root.findtext("filename") or (p.stem + ".png")
        boxes = []
        for obj in root.findall("object"):
            bb = obj.find("bndbox")
            if bb is None:
                continue
            boxes.append(
                Box(float(bb.findtext("xmin", "0")), float(bb.findtext("ymin", "0")),
                    float(bb.findtext("xmax", "0")), float(bb.findtext("ymax", "0")),
                    obj.findtext("name", "rfi"))
            )
        out[Path(fn).name] = boxes
    return out


_CSV_ALIASES = {
    "image": ("image", "image_name", "filename", "file_name", "img", "name"),
    "x1": ("x1", "xmin", "x_min", "left"),
    "y1": ("y1", "ymin", "y_min", "top"),
    "x2": ("x2", "xmax", "x_max", "right"),
    "y2": ("y2", "ymax", "y_max", "bottom"),
    "label": ("label", "class", "category", "cls"),
}


def _load_csv(path: Path) -> dict[str, list[Box]]:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    out: dict[str, list[Box]] = {}
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")
        lower = {f.lower().strip(): f for f in reader.fieldnames}
        cols = {}
        for canon, aliases in _CSV_ALIASES.items():
            for a in aliases:
                if a in lower:
                    cols[canon] = lower[a]
                    break
        missing = {"image", "x1", "y1", "x2", "y2"} - cols.keys()
        if missing:
            raise ValueError(f"{path} missing columns for {sorted(missing)}")
        for row in reader:
            name = Path(row[cols["image"]]).name
            out.setdefault(name, []).append(
                Box(float(row[cols["x1"]]), float(row[cols["y1"]]),
                    float(row[cols["x2"]]), float(row[cols["y2"]]),
                    row.get(cols.get("label", ""), "rfi") or "rfi")
            )
    return out


def iter_dataset(
    image_root: str | os.PathLike,
    annotations: str | os.PathLike | None = None,
):
    """Yield :class:`Quicklook` objects with their boxes attached.

    YOLO annotations need image shapes, so images are opened once up-front to
    collect them when that format is detected.
    """
    paths = find_images(image_root)
    ann: dict[str, list[Box]] = {}
    if annotations is not None:
        try:
            ann = load_annotations(annotations)
        except KeyError:
            shapes = {}
            for p in paths:
                with Image.open(p) as im:
                    shapes[p.name] = (im.size[1], im.size[0])
            ann = load_annotations(annotations, shapes)
    for p in paths:
        yield load_quicklook(p, ann.get(p.name, []))
