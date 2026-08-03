"""Per-box recoverability metrics: which annotated boxes are findable at all?

Some ClearSAR boxes are invisible for reasons that have nothing to do with model
capacity.  Sentinel-1 carries RFI annotations derived from echo-domain
detection, and the mission's own screening acknowledges that weak RFI of small
geographic extent is not always reported; interference that entered the receiver
need not have left a mark in a power-detected, decimated, 8-bit PNG.  On top of
that, IPF RFI mitigation is deliberately conservative, so what survives into the
product is often a spectral and textural residue rather than a bright stripe.

So before tuning a detector, measure each box against the channels interference
actually perturbs, and calibrate against **control boxes** -- same size
distribution, placed where nothing is annotated.  The controls give the null
distribution of every metric on this exact data, which is the only defensible
way to set thresholds; the alternative is asserting a z-score cut and hoping
speckle correlation does not invalidate it.

The output partitions the annotations into: visible in brightness, recoverable
only in the polarimetric ratio, recoverable only by directional integration,
recoverable only in speckle statistics, and no measurable signature.  That last
group is a label-noise estimate for this product level, and it belongs in your
model card.
"""

from __future__ import annotations

import numpy as np

from . import directional, spectral, speckle, unmix
from .io import Box, Quicklook

#: Metrics for which large *positive* values indicate a detection.
DETECTION_METRICS: tuple[str, ...] = (
    "abs_z_p1", "abs_z_p2", "abs_z_ratio",
    "abs_dcv_p1", "abs_dcv_p2", "abs_dkurt_p2",
    "stripe_snr_ratio", "stripe_snr_p2",
    "abs_d_anisotropy", "abs_d_peak_z",
)

#: Which family each metric belongs to, used to attribute a box to a mechanism.
METRIC_FAMILY: dict[str, str] = {
    "abs_z_p1": "brightness",
    "abs_z_p2": "brightness",
    "abs_z_ratio": "polarimetric",
    "abs_dcv_p1": "statistical",
    "abs_dcv_p2": "statistical",
    "abs_dkurt_p2": "statistical",
    "stripe_snr_ratio": "directional",
    "stripe_snr_p2": "directional",
    "abs_d_anisotropy": "spectral",
    "abs_d_peak_z": "spectral",
}


def _inner_outer(shape: tuple[int, int], box: Box, pad: int | None = None):
    """Crop slices plus inner/outer boolean masks within that crop.

    The reference is an annulus around the box rather than the whole image, so
    the comparison is against locally comparable terrain -- interference
    visibility is a local contrast question, and a global reference would make
    every box over dark water look like a detection.
    """
    h, w = shape
    if pad is None:
        pad = int(max(16, 0.5 * min(box.width, box.height)))
    ys, xs = box.slices(shape)
    yp, xp = box.slices(shape, pad=pad)
    inner = np.zeros((yp.stop - yp.start, xp.stop - xp.start), dtype=bool)
    inner[ys.start - yp.start:ys.stop - yp.start, xs.start - xp.start:xs.stop - xp.start] = True
    return (yp, xp), inner, ~inner


def _contrast(channel: np.ndarray, inner: np.ndarray, outer: np.ndarray) -> tuple[float, float]:
    """(median contrast, z-score) of the inner region against its surround.

    The z-score treats inner pixels as independent, which speckle correlation and
    the detail filter both violate; it is therefore an optimistic bound and is
    only meaningful relative to the control-box null distribution, which is
    affected in exactly the same way.
    """
    a, b = channel[inner], channel[outer]
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if a.size < 8 or b.size < 8:
        return float("nan"), float("nan")
    delta = float(np.median(a) - np.median(b))
    sigma = directional.robust_sigma(b)
    if not np.isfinite(sigma) or sigma <= 0:
        return delta, float("nan")
    return delta, float(delta / (sigma / np.sqrt(a.size)))


def measure_box(
    ql: Quicklook,
    box: Box,
    um: unmix.Unmixed | None = None,
    detail_scale: int = 31,
    window: int = 9,
    with_spectral: bool = True,
    kind: str = "label",
) -> dict[str, float | str]:
    """Measure one box across every decomposition channel."""
    um = um or unmix.unmix(ql.dn, single_pol=ql.single_pol)
    (yp, xp), inner, outer = _inner_outer(ql.shape, box)

    row: dict[str, float | str] = {
        "image": ql.name,
        "kind": kind,
        "label": box.label,
        "x1": box.x1, "y1": box.y1, "x2": box.x2, "y2": box.y2,
        "box_w": box.width, "box_h": box.height, "box_area": box.area,
        "single_pol": float(ql.single_pol),
        "detection_mode": um.detection,
        "looks_p2": um.model_p2.looks,
    }

    for name, ch in (("p1", um.p1_db), ("p2", um.p2_db), ("ratio", um.ratio_db)):
        delta, z = _contrast(ch[yp, xp], inner, outer)
        row[f"d_{name}_db"] = delta
        row[f"z_{name}"] = z
        row[f"abs_z_{name}"] = abs(z) if np.isfinite(z) else np.nan

    for name, raw, model in (("p1", ql.dn[:, :, 0], um.model_p1),
                             ("p2", ql.dn[:, :, 1], um.model_p2)):
        dep = speckle.departure_maps(raw[yp, xp], model, window)
        d_cv, _ = _contrast(dep["cv_departure"], inner, outer)
        row[f"dcv_{name}"] = d_cv
        row[f"abs_dcv_{name}"] = abs(d_cv) if np.isfinite(d_cv) else np.nan
        if name == "p2":
            d_k, _ = _contrast(dep["kurtosis"], inner, outer)
            row["dkurt_p2"] = d_k
            row["abs_dkurt_p2"] = abs(d_k) if np.isfinite(d_k) else np.nan

    for name, ch in (("ratio", um.ratio_db), ("p2", um.p2_db)):
        crop = ch[yp, xp]
        if min(crop.shape) < 12:
            row[f"stripe_snr_{name}"] = np.nan
            row[f"stripe_angle_{name}"] = np.nan
            continue
        det = directional.stripe_snr(directional.detail_image(crop, detail_scale))
        row[f"stripe_snr_{name}"] = det.snr
        row[f"stripe_angle_{name}"] = det.angle_deg

    if with_spectral and min(inner.shape) >= 32:
        spec = spectral.block_features(um.p2_db[yp, xp], block=min(64, *inner.shape))
        for key, out in (("anisotropy", "d_anisotropy"), ("peak_z", "d_peak_z")):
            d, _ = _contrast(spec[key], inner, outer)
            row[out] = d
            row[f"abs_{out}"] = abs(d) if np.isfinite(d) else np.nan
    else:
        for out in ("d_anisotropy", "d_peak_z"):
            row[out] = np.nan
            row[f"abs_{out}"] = np.nan

    finite = {m: row[m] for m in DETECTION_METRICS
              if isinstance(row.get(m), float) and np.isfinite(row[m])}
    row["best_metric"] = max(finite, key=finite.get) if finite else ""
    row["best_family"] = METRIC_FAMILY.get(str(row["best_metric"]), "")
    return row


def control_boxes(
    shape: tuple[int, int],
    boxes: list[Box],
    rng: np.random.Generator,
    per_box: int = 2,
    max_tries: int = 50,
) -> list[Box]:
    """Random boxes matching the annotated size distribution, placed elsewhere.

    These carry the null distribution of every metric: whatever speckle
    correlation, terrain texture and the detail filter do to a z-score, they do
    it here too.  Thresholds read off these controls are therefore honest in a
    way that any assumed parametric cut is not.
    """
    h, w = shape
    out: list[Box] = []
    for box in boxes:
        bw, bh = max(int(box.width), 1), max(int(box.height), 1)
        if bw >= w or bh >= h:
            continue
        for _ in range(per_box):
            for _ in range(max_tries):
                x1 = float(rng.integers(0, w - bw))
                y1 = float(rng.integers(0, h - bh))
                cand = Box(x1, y1, x1 + bw, y1 + bh, "control")
                if all(_iou(cand, b) == 0.0 for b in boxes):
                    out.append(cand)
                    break
    return out


def _iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def triage_image(
    ql: Quicklook,
    rng: np.random.Generator | None = None,
    controls_per_box: int = 2,
    **kwargs,
) -> list[dict[str, float | str]]:
    """Metrics for every annotated box in one quicklook, plus its controls."""
    if not ql.boxes:
        return []
    rng = rng or np.random.default_rng(0)
    um = unmix.unmix(ql.dn, single_pol=ql.single_pol)
    rows = [measure_box(ql, b, um=um, kind="label", **kwargs) for b in ql.boxes]
    for cb in control_boxes(ql.shape, ql.boxes, rng, controls_per_box):
        rows.append(measure_box(ql, cb, um=um, kind="control", **kwargs))
    return rows


def summarise(rows, quantile: float = 0.99) -> dict:
    """Attribute annotated boxes to the mechanism that makes them recoverable.

    Thresholds are the ``quantile`` of each metric over the control boxes, i.e. a
    per-metric false-positive rate of ``1 - quantile`` measured on this data.
    A box counts as recoverable by a family if any of that family's metrics
    exceeds its threshold.
    """
    import pandas as pd

    df = rows if hasattr(rows, "columns") else pd.DataFrame(list(rows))
    if df.empty:
        return {"n_labels": 0, "thresholds": {}, "families": {}, "table": df}

    ctrl = df[df["kind"] == "control"]
    lab = df[df["kind"] == "label"].copy()

    thresholds: dict[str, float] = {}
    for metric in DETECTION_METRICS:
        if metric not in df.columns:
            continue
        vals = ctrl[metric].dropna() if not ctrl.empty else df[metric].dropna()
        if len(vals) >= 10:
            thresholds[metric] = float(np.quantile(vals, quantile))

    families = sorted(set(METRIC_FAMILY.values()))
    for fam in families:
        metrics = [m for m, f in METRIC_FAMILY.items() if f == fam and m in thresholds]
        if metrics:
            hit = np.zeros(len(lab), dtype=bool)
            for m in metrics:
                hit |= (lab[m].fillna(-np.inf) > thresholds[m]).to_numpy()
        else:
            hit = np.zeros(len(lab), dtype=bool)
        lab[f"hit_{fam}"] = hit

    hit_cols = [f"hit_{f}" for f in families]
    lab["recoverable"] = lab[hit_cols].any(axis=1)
    # Attribute each box to a single mechanism, brightness first: a box the eye
    # can already see is not evidence that a subtler channel was needed.
    order = ["brightness", "polarimetric", "directional", "statistical", "spectral"]
    order = [f for f in order if f in families]

    def _attribute(r):
        if not r["recoverable"]:
            return "none"
        for fam in order:
            if r[f"hit_{fam}"]:
                return fam
        return "none"

    lab["mechanism"] = lab.apply(_attribute, axis=1)
    counts = lab["mechanism"].value_counts().to_dict()
    return {
        "n_labels": int(len(lab)),
        "n_controls": int(len(ctrl)),
        "thresholds": thresholds,
        "families": {f: int(lab[f"hit_{f}"].sum()) for f in families},
        "mechanisms": counts,
        "recoverable_fraction": float(lab["recoverable"].mean()),
        "table": lab,
    }
