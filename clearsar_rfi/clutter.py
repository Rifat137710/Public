"""Clutter-limited detectability of RFI in the polarisation difference.

This module holds the two measurements that set the ceiling on any detector
built from the R-G polarisation difference of a ClearSAR quicklook. Both were
made on real dataset images, and together they explain why hand-built detection
of the "invisible" boxes fails.

1. The background is TERRAIN-CLUTTER-limited, not speckle-limited
   ---------------------------------------------------------------
   If the residual after terrain removal were independent speckle, averaging an
   ``h x w`` window would reduce its standard deviation as ``(h*w)**-0.5``.
   Measured over dataset quicklooks it falls as ``(h*w)**(-alpha/2)`` with

       alpha = 0.426          (alpha_h = 0.59, alpha_w = 0.31)

   so a 4x12 window averages 48 pixels and gains a factor of 1.07 -- essentially
   nothing. Integrating a median-sized box (10 x 138 px) buys ~8.6x rather than
   the speckle-limited ~37x. Matched filtering therefore cannot rescue a weak
   box, and any noise model that assumes independent looks will be optimistic by
   more than an order of magnitude.

2. The clutter is violently non-Gaussian, and its tail depends on scale
   --------------------------------------------------------------------
   For the magnitude of the azimuth top-hat response, ``q99.9 / MAD-sigma`` runs

       h =  4 px  ->  33          h = 17 px  ->  20
       h = 11 px  ->  24          h = 43 px  ->  13

   against 5.5 for the magnitude of a Gaussian. The smallest scale carries a
   2.5x heavier tail than the largest,
   so comparing MAD z-scores across scales hands every detection to the smallest
   window regardless of the true object size. Scales must be normalised by a
   measured high quantile, not by a robust sigma.

3. The consequence: a detection ceiling
   -------------------------------------
   Scoring each annotated box at its own scale and asking where it sits in the
   response distribution of its own image gives

       true RFI boxes      q25 56.0   median 82.1   q75 95.5   q90 99.6
       random background   q25 22.9   median 48.0   q75 71.5   q90 89.0
       AUC = 0.733

   The feature carries real information -- but only 14% of true boxes clear the
   99th percentile of their own image and 23% fall below the median. A detector
   asked to return ~3 boxes per image is working far out on that tail, so recall
   is bounded near 20% however the boxes are grouped. Grouping is not the
   binding constraint; detection power is.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import median_filter, uniform_filter

# Measured on ClearSAR Track-1 quicklooks; see module docstring.
CLUTTER_ALPHA = 0.426
CLUTTER_ALPHA_AZIMUTH = 0.588
CLUTTER_ALPHA_RANGE = 0.306
# Reference value of `tail_ratio`, which scores |response|: for a half-normal
# q99.9 = 3.29 sigma while 1.4826 * MAD = 0.63 sigma, giving 5.5 -- NOT the 3.3
# that applies to a signed Gaussian.
GAUSSIAN_TAIL_RATIO = 5.5

__all__ = [
    "CLUTTER_ALPHA",
    "ClutterScaling",
    "azimuth_tophat",
    "effective_looks",
    "measure_clutter_scaling",
    "tail_ratio",
]


def _shift_rows(a: np.ndarray, k: int) -> np.ndarray:
    """``out[y] == a[y - k]``, edges replicated."""
    out = np.empty_like(a)
    if k == 0:
        return a.copy()
    if k > 0:
        out[k:], out[:k] = a[:-k], a[0]
    else:
        out[:k], out[k:] = a[-k:], a[-1]
    return out


def _rsig(x: np.ndarray) -> float:
    x = np.asarray(x, float).ravel()
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 1.0
    return max(float(1.4826 * np.median(np.abs(x - np.median(x)))), 1e-9)


def azimuth_tophat(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """Range-extended, azimuth-confined matched response.

    The centre band minus the mean of the equal-sized bands ``h`` rows above and
    below. The symmetric flanks cancel any azimuth trend to first order, which
    removes terrain without requiring the anomaly to span the full sub-swath.

    RFI is range-extended and azimuth-confined -- interference arrives during a
    short along-track interval and spreads across range -- whereas terrain has no
    such preferred orientation, so the orientation of the filter is itself a
    discriminator.
    """
    c = uniform_filter(np.asarray(a, float), size=(h, w), mode="nearest")
    return c - 0.5 * (_shift_rows(c, h) + _shift_rows(c, -h))


def detrend_range(d: np.ndarray, bg_rows: int = 61) -> np.ndarray:
    """Remove range-dependent terrain that is stable over ``bg_rows`` in azimuth."""
    d = np.asarray(d, float)
    return d - median_filter(d, size=(bg_rows, 1), mode="nearest")


@dataclass(frozen=True)
class ClutterScaling:
    """Result of :func:`measure_clutter_scaling`.

    Attributes
    ----------
    alpha:
        Exponent in ``sigma(h, w) = sigma_pixel * (h * w) ** (-alpha / 2)``.
        1.0 means independent pixels; the measured value on this dataset is
        ~0.43, i.e. strongly correlated, terrain-limited clutter.
    alpha_azimuth, alpha_range:
        The same exponent fitted separately per axis.
    sigma_pixel:
        Per-pixel robust sigma of the detrended difference, in dB.
    sigma:
        ``{(h, w): measured robust sigma of the window mean}``.
    """

    alpha: float
    alpha_azimuth: float
    alpha_range: float
    sigma_pixel: float
    sigma: dict[tuple[int, int], float]

    def effective_looks(self, h: int, w: int) -> float:
        """Independent samples an ``h x w`` average is actually worth."""
        return float((h * w) ** self.alpha)

    def ideal_gain(self, h: int, w: int) -> float:
        """Noise reduction a speckle-limited detector would have expected."""
        return float(np.sqrt(h * w))

    def actual_gain(self, h: int, w: int) -> float:
        """Noise reduction actually obtained at this window size."""
        return float((h * w) ** (self.alpha / 2))


def measure_clutter_scaling(
    diff_db: np.ndarray,
    heights=(4, 7, 11, 17, 27, 43),
    widths=(12, 24, 48, 96, 160),
    bg_rows: int = 61,
) -> ClutterScaling:
    """Fit how fast window averaging actually reduces the clutter.

    Parameters
    ----------
    diff_db:
        The polarisation difference ``dB(R) - dB(G)`` for one image or sub-swath,
        with invalid pixels already filled.

    Notes
    -----
    ``sigma_pixel`` is estimated from the range-direction first difference, which
    is dominated by the high-frequency residual rather than by terrain, so it is
    not inflated by the very correlation being measured.
    """
    a = detrend_range(diff_db, bg_rows)
    sigma_pixel = _rsig(np.diff(a, axis=1)) / np.sqrt(2.0)

    sigma: dict[tuple[int, int], float] = {}
    logs, vals = [], []
    for h in heights:
        for w in widths:
            if h >= a.shape[0] or w >= a.shape[1]:
                continue
            s = _rsig(uniform_filter(a, size=(h, w), mode="nearest"))
            sigma[(h, w)] = s
            logs.append((np.log(h), np.log(w), 1.0))
            # ratio to the independent-pixel expectation
            vals.append(np.log(s * np.sqrt(h * w) / sigma_pixel))
    if len(vals) < 3:
        raise ValueError("image too small to fit a clutter scaling")

    x = np.array(logs)
    y = np.array(vals)
    ch, cw, _ = np.linalg.lstsq(x, y, rcond=None)[0]
    # sigma ~ (h*w)**(-alpha/2)  =>  ratio ~ (h*w)**((1-alpha)/2)
    slope = np.polyfit(x[:, 0] + x[:, 1], y, 1)[0]
    return ClutterScaling(
        alpha=float(1 - 2 * slope),
        alpha_azimuth=float(1 - 2 * ch),
        alpha_range=float(1 - 2 * cw),
        sigma_pixel=float(sigma_pixel),
        sigma=sigma,
    )


def effective_looks(h: int, w: int, alpha: float = CLUTTER_ALPHA) -> float:
    """Independent samples an ``h x w`` average is worth under the measured alpha.

    A 10 x 138 px box -- the dataset median -- averages 1380 pixels but is worth
    only ~24 independent samples, an 8.6x noise reduction against the 37x a
    speckle-limited calculation predicts.
    """
    return float((h * w) ** alpha)


def tail_ratio(response: np.ndarray, q: float = 99.9) -> float:
    """``percentile(|response|, q) / MAD-sigma`` of the magnitude.

    The reference for pure noise is :data:`GAUSSIAN_TAIL_RATIO` = 5.5, the value
    for a half-normal -- not the 3.3 of a signed Gaussian, since this scores the
    magnitude.

    Use this to normalise responses across scales. A robust sigma is not enough:
    the ratio itself varies from ~33 at h=4 px to ~13 at h=43 px, so MAD
    z-scores are not comparable between window sizes.
    """
    r = np.abs(np.asarray(response, float))
    return float(np.percentile(r[np.isfinite(r)], q) / _rsig(r))
