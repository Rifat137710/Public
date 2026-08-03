"""Directional matched filtering: recovering stripes from below the noise floor.

RFI in SAR imagery is strongly anisotropic -- bright lines and stripes for
narrowband sources, repeated pale rectangles for pulsed ones, curved streaks and
foggy directional blocks for wideband ones.  That structure is a matched filter
the pixel-wise eye never applies.

The Radon transform *is* the matched filter for a linear feature: integrating
along the correct line accumulates signal coherently and noise as ``sqrt(N)``.
For an L-look quicklook the per-pixel amplitude CV is roughly ``0.52/sqrt(L)``,
about 0.26 at four looks, so pooling a stripe 400 pixels long and 8 wide -- 3200
samples -- drops it to ~0.005, a few hundredths of a dB in principle.  Speckle
also dithers the 8-bit quantiser, so sub-LSB contrast averages down instead of
being clipped away.

In practice that bound is not what limits you: **terrain is**.  Scene structure
leaks into the background-removed detail image and raises the null far above the
speckle floor.  On the paired synthetic benchmark in
``scripts/calibrate_sensitivity.py`` the Radon statistic separates from its
interference-free twin at roughly 1 dB, whereas the polarimetric ratio contrast
-- which *cancels* terrain rather than averaging it down -- separates at roughly
0.2 dB, a level at which most pixels are still unchanged at 8-bit precision.
Which one wins on a given box depends on the terrain under it, so measure both.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import median_filter, rotate, uniform_filter, uniform_filter1d
from skimage.transform import radon

from .speckle import EPS


def detail_image(img: np.ndarray, scale: int = 31, robust: bool = False) -> np.ndarray:
    """Remove the local scene level, leaving the additive residual.

    Interference visibility is governed by the interference-to-signal *ratio*,
    not by absolute brightness: the same emitter that saturates dark water is a
    fraction of a dB over bright forest or urban terrain.  Working on the
    background-normalised residual (in dB, so "additive" means "ratio") is what
    puts those two cases on the same footing.
    """
    img = np.asarray(img, dtype=np.float64)
    if robust:
        background = median_filter(img, size=scale, mode="nearest")
    else:
        background = uniform_filter(img, scale, mode="nearest")
    return img - background


def robust_sigma(x: np.ndarray) -> float:
    """Median-absolute-deviation estimate of the noise standard deviation."""
    x = np.asarray(x, dtype=np.float64).ravel()
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    mad = np.median(np.abs(x - np.median(x)))
    return float(1.4826 * mad) or EPS


@dataclass
class StripeDetection:
    """Outcome of a Radon matched-filter search over orientations and widths."""

    snr: float  # peak band-integrated signal-to-noise ratio
    angle_deg: float  # orientation of the strongest band
    offset: int  # Radon bin index of the peak
    width: int  # number of adjacent Radon bins integrated at the peak
    n_pixels: float  # pixels contributing to the peak
    contrast_db: float  # mean residual over the peak band, in dB
    sigma: float  # per-pixel noise used for normalisation


#: Band widths (in Radon offset bins) searched by :func:`stripe_snr`.
DEFAULT_WIDTHS: tuple[int, ...] = (1, 3, 5, 9, 17, 33)


def stripe_snr(
    detail: np.ndarray,
    n_angles: int = 90,
    min_fraction: float = 0.25,
    sigma: float | None = None,
    widths: tuple[int, ...] = DEFAULT_WIDTHS,
) -> StripeDetection:
    """Multi-width Radon matched filter for linear structure.

    Every Radon bin sums a different number of pixels, so the raw sinogram is
    normalised by the path length taken from the projection of an all-ones mask:
    the per-line mean is ``R/N`` with noise ``sigma/sqrt(N)``, giving
    ``SNR = R / (sigma * sqrt(N))``.  Bins whose path is shorter than
    ``min_fraction`` of the longest are discarded, as short chords through the
    corners are noisy and uninformative.

    Real interference stripes have finite width, so integrating a single
    one-pixel line throws away most of the available signal: a stripe 8 pixels
    wide and 400 long holds 3200 pixels, not 400, and the difference is a factor
    of ~2.8 in SNR.  Adjacent offset bins are therefore summed over a range of
    band widths and the best combination is reported -- a matched filter over
    scale as well as orientation.

    Adjacent Radon bins are not statistically independent, so the reported SNR
    is an optimistic bound.  Calibrate it against control regions
    (:func:`clearsar_rfi.triage.control_boxes`) rather than reading it as a
    Gaussian sigma.
    """
    detail = np.asarray(detail, dtype=np.float64)
    detail = np.nan_to_num(detail, nan=0.0, posinf=0.0, neginf=0.0)
    if sigma is None:
        sigma = robust_sigma(detail)
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = EPS

    theta = np.linspace(0.0, 180.0, int(n_angles), endpoint=False)
    sino = radon(detail, theta=theta, circle=False, preserve_range=True)
    paths = radon(np.ones_like(detail), theta=theta, circle=False, preserve_range=True)
    keep = paths >= max(min_fraction * paths.max(), 4.0)

    best = StripeDetection(0.0, 0.0, 0, 1, 0.0, 0.0, float(sigma))
    for width in widths:
        if width > sino.shape[0]:
            continue
        if width == 1:
            band, band_paths, band_keep = sino, paths, keep
        else:
            # uniform_filter1d gives the mean over the band; multiply back to a sum.
            band = uniform_filter1d(sino, width, axis=0, mode="constant") * width
            band_paths = uniform_filter1d(paths, width, axis=0, mode="constant") * width
            # Only trust bands built entirely from valid bins.
            band_keep = uniform_filter1d(
                keep.astype(np.float64), width, axis=0, mode="constant"
            ) > 0.999

        snr = np.zeros_like(band)
        np.divide(band, sigma * np.sqrt(np.maximum(band_paths, EPS)), out=snr, where=band_keep)
        snr[~band_keep] = 0.0
        if not np.isfinite(snr).any():
            continue

        idx = int(np.argmax(np.abs(snr)))
        off, ang = np.unravel_index(idx, snr.shape)
        value = float(np.abs(snr[off, ang]))
        if value > best.snr:
            n_pix = float(band_paths[off, ang])
            best = StripeDetection(
                snr=value,
                angle_deg=float(theta[ang]),
                offset=int(off),
                width=int(width),
                n_pixels=n_pix,
                contrast_db=float(band[off, ang] / max(n_pix, EPS)),
                sigma=float(sigma),
            )
    return best


def stripe_layer(detail: np.ndarray, angle_deg: float, min_samples: int = 8) -> np.ndarray:
    """Extract the additive stripe layer at a given orientation.

    A robust stand-in for the variational destriping models (unidirectional TV,
    LRSID, morphological component analysis) that decompose an image into
    ``scene + stripe + noise``: rotate so the stripes run along the array rows,
    take a *median* profile across them -- median rather than mean so terrain
    structure crossing the stripe does not leak into the estimate -- and rotate
    back.  Here the stripe layer is the product and the scene is discarded,
    which is the inverse of the usual destriping objective.
    """
    detail = np.nan_to_num(np.asarray(detail, dtype=np.float64))
    rot = rotate(detail, angle_deg, reshape=True, order=1, mode="constant", cval=0.0)
    mask = rotate(np.ones_like(detail), angle_deg, reshape=True, order=1,
                  mode="constant", cval=0.0)
    valid = mask > 0.9

    counts = valid.sum(axis=0)
    usable = counts >= min_samples
    profile = np.zeros(rot.shape[1])
    if usable.any():
        # Restrict to columns that actually have samples: nanmedian over an
        # all-NaN column is both a warning and a meaningless value.
        masked = np.where(valid[:, usable], rot[:, usable], np.nan)
        profile[usable] = np.nan_to_num(np.nanmedian(masked, axis=0))

    layer_rot = np.where(valid, profile[None, :], 0.0)
    back = rotate(layer_rot, -angle_deg, reshape=False, order=1, mode="constant", cval=0.0)
    return _center_crop(back, detail.shape)


def _center_crop(arr: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    y0 = max((arr.shape[0] - h) // 2, 0)
    x0 = max((arr.shape[1] - w) // 2, 0)
    out = arr[y0:y0 + h, x0:x0 + w]
    if out.shape != (h, w):  # rounding at odd sizes
        pad = ((0, h - out.shape[0]), (0, w - out.shape[1]))
        out = np.pad(out, pad, mode="edge")
    return out


def directional_response(
    detail: np.ndarray,
    n_angles: int = 12,
    length: int = 31,
) -> np.ndarray:
    """Per-pixel maximum response of a bank of oriented line filters.

    A cheap dense complement to :func:`stripe_snr`, which returns one number for
    a whole region.  Each orientation smooths along a line of ``length`` pixels,
    so terrain averages down while a stripe aligned with the filter does not;
    taking the maximum over orientations gives a map that lights up on linear
    structure of any bearing.
    """
    detail = np.nan_to_num(np.asarray(detail, dtype=np.float64))
    best = np.full(detail.shape, -np.inf)
    for angle in np.linspace(0.0, 180.0, int(n_angles), endpoint=False):
        rot = rotate(detail, angle, reshape=True, order=1, mode="constant", cval=0.0)
        smoothed = uniform_filter(rot, size=(1, int(length)), mode="constant")
        back = rotate(smoothed, -angle, reshape=False, order=1, mode="constant", cval=0.0)
        best = np.maximum(best, _center_crop(back, detail.shape))
    return np.where(np.isfinite(best), best, 0.0)
