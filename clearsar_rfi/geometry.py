"""Acquisition geometry: sub-swath seams and azimuth-interval detection.

The single most exploitable property of ClearSAR RFI annotations is that they
are **quantised to Sentinel-1 IW sub-swath boundaries**.  IW mode images three
sub-swaths (IW1/IW2/IW3), and interference is a receiver-side phenomenon that
affects a whole sub-swath over some stretch of azimuth.  The boxes reflect that:
measured over a sample of annotated scenes, box widths cluster at 1/3 and 2/3 of
the image width, column-profile seams appear at ~0.35 and ~0.69, and ~70% of box
x-edges land on a seam or on the image edge.

That halves the localisation problem: the x-extent of every box is drawn from a
*three-element menu* (and their contiguous unions), leaving only the azimuth
interval to find.

**Measured on 12 annotated scenes** (boxes recovered from burned-in overlays, so
treat as approximate):

* the x-prior holds -- box x-extents match the nearest sub-swath union with
  median 1-D IoU **0.80**; 70% at IoU>=0.5, 57% at IoU>=0.7;
* snapping a jittered detector's x-edges to seams gives a real but modest
  **+3%** mean IoU at 15-25 px of jitter;
* **azimuth detection by thresholding a 1-D profile does not work.**  Median
  y-extent IoU is 0.26, and it collapses with box size: 0.37 for thin boxes
  (<10% of image height), 0.14 for mid, **0.04** for large ones.  End-to-end
  that is 22% recall at IoU 0.25 and 8% at IoU 0.5.

So use this module for the geometry -- seam detection, x-snapping, restricting
the hypothesis space -- and **not** as a detector.  The honest reading of the
failure is that terrain varies along azimuth just as interference does, and a
hand-built statistic cannot separate them; a threshold on an excursion also
structurally cannot emit the large boxes that cover most of a sub-swath.  That
part needs a learned model, for which the natural form given this geometry is a
1-D sequence model over azimuth, run per sub-swath.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_dilation, median_filter, uniform_filter1d

from .io import Box

#: Nominal IW sub-swath edges as a fraction of image width, for fallback when
#: seam detection fails (e.g. a scene that is uniformly dark across the swath).
NOMINAL_IW_EDGES: tuple[float, ...] = (0.0, 1 / 3, 2 / 3, 1.0)


def annotation_overlay_mask(dn: np.ndarray, dilate: int = 5) -> np.ndarray:
    """Mask of burned-in pure-red annotation rectangles.

    Some ClearSAR previews circulate with the boxes drawn into the pixels as
    (255, 0, 0).  Those pixels are not data: left in, they corrupt channel
    regressions and dominate any contrast stretch.  Masking them is a
    prerequisite for measuring anything on such a file -- and their presence is
    itself a warning that the file is a rendering rather than the original
    product.
    """
    r, g, b = dn[:, :, 0], dn[:, :, 1], dn[:, :, 2]
    mask = (r > 150) & (g < 90) & (b < 90)
    if dilate > 1:  # catch anti-aliased edges
        mask = binary_dilation(mask, np.ones((dilate, dilate)))
    return mask


def _valid_mask(dn: np.ndarray) -> np.ndarray:
    """Data pixels: not annotation overlay, not black border padding."""
    lum = dn.mean(axis=2)
    return (~annotation_overlay_mask(dn)) & (lum > 0.12 * np.percentile(lum, 99))


def detect_seams(
    dn: np.ndarray,
    n_seams: int = 2,
    guard: float = 0.06,
    min_separation: float = 0.08,
) -> list[int]:
    """Locate sub-swath boundaries as discontinuities in the column profile.

    Sub-swaths are acquired with different look angles and antenna patterns, so
    the mean level steps across their boundaries even where the terrain does
    not.  Returns column indices, sorted; may return fewer than ``n_seams`` if
    the image does not support them.
    """
    valid = _valid_mask(dn)
    lum = np.where(valid, dn.mean(axis=2), np.nan)
    # Fully masked columns are legitimate (black padding), so average only over
    # columns that have data and fill the rest, rather than letting nanmean warn.
    has_data = np.isfinite(lum).any(axis=0)
    if not has_data.any():
        return []
    profile = np.full(lum.shape[1], np.nan)
    profile[has_data] = np.nanmean(lum[:, has_data], axis=0)
    profile = np.nan_to_num(profile, nan=float(np.nanmean(profile[has_data])))

    grad = np.abs(np.gradient(uniform_filter1d(profile, 5)))
    grad[profile <= 0.15 * profile.max()] = 0.0  # ignore dark padding
    width = len(profile)
    edge = int(guard * width)
    grad[:edge] = 0.0
    grad[width - edge:] = 0.0

    positive = grad[grad > 0]
    if positive.size == 0:
        return []
    floor = 3.0 * float(np.median(positive))

    seams: list[int] = []
    work = grad.copy()
    sep = int(min_separation * width)
    for _ in range(n_seams):
        i = int(np.argmax(work))
        if work[i] <= floor:
            break
        seams.append(i)
        work[max(0, i - sep):i + sep] = 0.0
    return sorted(seams)


def subswath_bounds(dn: np.ndarray, n_seams: int = 2) -> list[tuple[int, int]]:
    """Column ranges of the sub-swaths, falling back to nominal IW thirds."""
    width = dn.shape[1]
    seams = detect_seams(dn, n_seams)
    if len(seams) != n_seams:
        seams = [int(f * width) for f in NOMINAL_IW_EDGES[1:-1]][:n_seams]
    edges = [0, *seams, width]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def azimuth_profile(
    dn: np.ndarray,
    cols: tuple[int, int],
    detrend: int = 61,
) -> np.ndarray:
    """Robust 1-D azimuth profile of the channel difference for one sub-swath.

    Uses ``R - G`` in dB -- the polarimetric differential -- because terrain is
    largely common-mode across the two channels while interference is not.  The
    median across range collapses the sub-swath to one number per azimuth line;
    subtracting a long median filter removes the slow along-track trend, leaving
    localised excursions.  Returned in units of its own robust sigma, so the
    values read directly as significance.
    """
    valid = _valid_mask(dn)
    x0, x1 = cols
    diff = 20 * np.log10(dn[:, :, 0] + 0.5) - 20 * np.log10(dn[:, :, 1] + 0.5)
    band = np.where(valid, diff, np.nan)[:, x0:x1]
    has_data = np.isfinite(band).any(axis=1)
    if not has_data.any():
        return np.zeros(dn.shape[0])
    profile = np.full(band.shape[0], np.nan)
    profile[has_data] = np.nanmedian(band[has_data], axis=1)
    profile = np.nan_to_num(profile, nan=float(np.nanmedian(profile[has_data])))

    residual = profile - median_filter(profile, max(int(detrend), 3))
    sigma = 1.4826 * np.median(np.abs(residual - np.median(residual)))
    return residual / max(float(sigma), 1e-6)


def detect_intervals(
    profile: np.ndarray,
    threshold: float = 2.5,
    min_length: int = 4,
    merge_gap: int = 6,
) -> list[tuple[int, int]]:
    """Azimuth intervals where a profile exceeds ``threshold`` in absolute value."""
    hot = np.abs(profile) > threshold
    if not hot.any():
        return []
    idx = np.flatnonzero(hot)
    splits = np.flatnonzero(np.diff(idx) > merge_gap)
    groups = np.split(idx, splits + 1)
    return [(int(g[0]), int(g[-1]) + 1) for g in groups if len(g) >= min_length]


def propose_boxes(
    dn: np.ndarray,
    threshold: float = 2.5,
    min_length: int = 4,
    n_seams: int = 2,
) -> list[Box]:
    """Candidates whose x-extent is a sub-swath by construction.

    Each candidate spans a full sub-swath in range and a profile excursion in
    azimuth.  **This is a weak baseline, not a usable detector** -- measured
    recall is 22% at IoU 0.25 (see the module docstring), because terrain
    excursions are indistinguishable from interference in this statistic and
    because thresholding cannot produce a box covering most of a sub-swath.
    It is kept as a reference point to beat and as a way to visualise where the
    azimuth signal is.  ``label`` records the sub-swath, ``score`` the peak
    significance.
    """
    boxes: list[Box] = []
    for k, (x0, x1) in enumerate(subswath_bounds(dn, n_seams)):
        profile = azimuth_profile(dn, (x0, x1))
        for y0, y1 in detect_intervals(profile, threshold, min_length):
            peak = float(np.max(np.abs(profile[y0:y1])))
            boxes.append(Box(float(x0), float(y0), float(x1), float(y1),
                             label=f"iw{k + 1}", score=peak))
    return boxes


def snap_to_seams(box: Box, dn: np.ndarray, tol: float = 0.05, n_seams: int = 2) -> Box:
    """Snap a box's x-edges to the nearest sub-swath seam or image edge.

    A free post-processing win for any detector: the ground-truth x-edges live
    on this small set of positions, so moving a predicted edge that is already
    within ``tol`` of one costs nothing and recovers IoU.  Edges further away
    than the tolerance are left alone.
    """
    width = dn.shape[1]
    anchors = [0.0, *(float(s) for s in detect_seams(dn, n_seams)), float(width)]
    window = tol * width

    def _snap(value: float) -> float:
        nearest = min(anchors, key=lambda a: abs(a - value))
        return nearest if abs(nearest - value) <= window else value

    x1, x2 = _snap(box.x1), _snap(box.x2)
    if x2 <= x1:  # never collapse a box onto a single column
        x1, x2 = box.x1, box.x2
    return Box(x1, box.y1, x2, box.y2, box.label, box.score)
