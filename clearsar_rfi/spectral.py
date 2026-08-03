"""Block-wise spectral features of the quicklook.

Two signatures live here that brightness cannot reach:

* **Periodic RFI.**  Pulsed interference prints repeated pale rectangles, whose
  regular spacing becomes a comb of discrete peaks in the 2-D spectrum.  A
  stripe becomes a line through the origin perpendicular to itself.
* **Notch-filter residue.**  Sentinel-1 IPF RFI mitigation is deliberately
  conservative, so it leaves low-level residuals -- and where it *did* act it
  removed a band, narrowing the effective bandwidth.  That changes the local
  spatial spectrum and texture correlation at an unchanged mean level.  This is
  precisely the class of "labelled but invisible" box that no amount of
  contrast stretching will reveal.

The spectrum is whitened against its own radial profile first, so the features
respond to *anisotropy and peakiness* rather than to how bright or smooth the
underlying terrain happens to be.
"""

from __future__ import annotations

import numpy as np

from .speckle import EPS


def _whitened_spectrum(block: np.ndarray, n_radial: int = 24) -> np.ndarray:
    """Power spectrum divided by its own radial average.

    Natural terrain has a smooth, roughly isotropic power-law spectrum; dividing
    it out leaves a field that is flat for terrain and structured for anything
    directional or periodic.
    """
    b = np.asarray(block, dtype=np.float64)
    b = b - b.mean()
    win = np.hanning(b.shape[0])[:, None] * np.hanning(b.shape[1])[None, :]
    power = np.abs(np.fft.fftshift(np.fft.fft2(b * win))) ** 2

    h, w = power.shape
    yy, xx = np.mgrid[0:h, 0:w]
    radius = np.hypot(yy - h / 2.0, xx - w / 2.0)
    r_max = radius.max()
    bins = np.clip((radius / max(r_max, EPS) * n_radial).astype(int), 0, n_radial - 1)

    background = np.zeros_like(power)
    for k in range(n_radial):
        sel = bins == k
        if sel.any():
            background[sel] = np.median(power[sel])
    return power / np.maximum(background, EPS)


def block_features(
    img: np.ndarray,
    block: int = 64,
    stride: int | None = None,
    n_angles: int = 36,
) -> dict[str, np.ndarray]:
    """Spectral anisotropy and peakiness, as full-resolution maps.

    Returns
    -------
    dict
        ``anisotropy``   ratio of the strongest orientation's energy to the
        median across orientations -- large for stripes and directional texture.
        ``peak_z``       robust z-score of the strongest non-DC spectral peak --
        large for periodic (pulsed) interference.
    """
    img = np.nan_to_num(np.asarray(img, dtype=np.float64))
    stride = stride or block // 2
    h, w = img.shape
    block = int(min(block, h, w))
    if block < 8:
        z = np.zeros((h, w))
        return {"anisotropy": z, "peak_z": z.copy()}

    ys = list(range(0, max(h - block, 0) + 1, stride)) or [0]
    xs = list(range(0, max(w - block, 0) + 1, stride)) or [0]
    aniso = np.zeros((len(ys), len(xs)))
    peakz = np.zeros((len(ys), len(xs)))

    bh = bw = block
    yy, xx = np.mgrid[0:bh, 0:bw]
    radius = np.hypot(yy - bh / 2.0, xx - bw / 2.0)
    angle = np.mod(np.arctan2(yy - bh / 2.0, xx - bw / 2.0), np.pi)
    abins = np.clip((angle / np.pi * n_angles).astype(int), 0, n_angles - 1)
    keep = radius > 2.0  # exclude DC and its immediate neighbourhood

    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            wspec = _whitened_spectrum(img[y:y + block, x:x + block])
            vals = wspec[keep]
            energy = np.array([
                vals[abins[keep] == k].mean() if np.any(abins[keep] == k) else 0.0
                for k in range(n_angles)
            ])
            med = np.median(energy)
            aniso[i, j] = energy.max() / max(med, EPS)
            mad = np.median(np.abs(vals - np.median(vals)))
            peakz[i, j] = (vals.max() - np.median(vals)) / max(1.4826 * mad, EPS)

    return {
        "anisotropy": _upsample(aniso, ys, xs, block, (h, w)),
        "peak_z": _upsample(peakz, ys, xs, block, (h, w)),
    }


def _upsample(
    grid: np.ndarray,
    ys: list[int],
    xs: list[int],
    block: int,
    shape: tuple[int, int],
) -> np.ndarray:
    """Paint block values back onto a full-resolution map (nearest block centre)."""
    h, w = shape
    centres_y = np.array([y + block / 2.0 for y in ys])
    centres_x = np.array([x + block / 2.0 for x in xs])
    row_idx = np.abs(np.arange(h)[:, None] - centres_y[None, :]).argmin(axis=1)
    col_idx = np.abs(np.arange(w)[:, None] - centres_x[None, :]).argmin(axis=1)
    return grid[np.ix_(row_idx, col_idx)]
