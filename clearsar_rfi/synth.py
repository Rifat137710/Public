"""Synthetic quicklooks with interference injected at a known dB level.

This is the calibration harness, and it is the part that turns "my detector
misses these boxes" into a measurement.  Because the injected
interference-to-signal ratio is known exactly, sweeping it and re-running the
triage metrics traces out the *detectability floor of the quicklook product* --
the contrast below which no method can recover anything from an 8-bit,
multi-looked, decimated PNG.  Ghost boxes whose measured contrast falls under
that floor are label noise with respect to this product level, not detector
failures, and that distinction is worth establishing before tuning a model.

It doubles as the test fixture for the rest of the package.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter

from .io import Box, Quicklook


@dataclass
class SynthConfig:
    """Parameters of a synthetic dual-pol quicklook."""

    shape: tuple[int, int] = (512, 512)
    looks: float = 4.0  # equivalent number of looks after multilooking
    copol_mean_db: float = -8.0  # typical land co-pol sigma0
    copol_texture_db: float = 3.0  # spatial std of the terrain in dB
    crosspol_offset_db: float = 11.0  # cross-pol sits this far below co-pol
    texture_scale: float = 24.0  # correlation length of the terrain, pixels
    bright_patches: int = 6  # urban/forest-like bright blobs
    clip_percentile: float = 99.0  # display stretch saturation point
    common_stretch: bool = True  # one stretch for both channels, per the spec
    seed: int | None = 0


@dataclass
class SynthScene:
    """A synthetic quicklook, its interference-free twin, and the ground truth.

    ``baseline`` is the identical scene -- same terrain, same speckle
    realisation, same display stretch -- with the interference omitted.  It is
    what makes the sensitivity sweep a paired measurement: metrics computed on a
    box are dominated by whatever terrain happens to lie under it, so the
    quantity that isolates the interference is the *difference* between the two
    scenes at the same box, not the raw value.
    """

    quicklook: Quicklook
    baseline: Quicklook
    truth_mask: np.ndarray  # bool, where interference was injected
    truth_box: Box
    injected_db: float  # nominal interference-to-signal ratio, dB
    channel: int  # 0 = co-pol, 1 = cross-pol
    morphology: str
    realised: dict[str, float] = field(default_factory=dict)


def _terrain(cfg: SynthConfig, rng: np.random.Generator) -> np.ndarray:
    """Smooth, log-normal-ish terrain backscatter field in dB."""
    h, w = cfg.shape
    field_ = gaussian_filter(rng.standard_normal((h, w)), cfg.texture_scale)
    field_ /= max(field_.std(), 1e-9)
    db = cfg.copol_mean_db + cfg.copol_texture_db * field_

    for _ in range(cfg.bright_patches):
        cy, cx = rng.integers(0, h), rng.integers(0, w)
        ry, rx = rng.integers(h // 12, h // 4), rng.integers(w // 12, w // 4)
        yy, xx = np.ogrid[0:h, 0:w]
        blob = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0
        db = db + gaussian_filter(blob.astype(float), 8.0) * rng.uniform(3.0, 9.0)
    return db


def _speckle(shape: tuple[int, int], looks: float, rng: np.random.Generator) -> np.ndarray:
    """Multiplicative Gamma speckle with unit mean, as produced by L-look averaging."""
    return rng.gamma(shape=looks, scale=1.0 / looks, size=shape)


def _rfi_mask(shape: tuple[int, int], morphology: str, rng: np.random.Generator
              ) -> tuple[np.ndarray, Box]:
    """Boolean footprint of the interference, plus its bounding box."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    morphology = morphology.lower()

    # Footprints are deliberately of limited extent: a real RFI annotation covers
    # part of a scene, and a feature spanning the whole image would leave no
    # surrounding terrain to measure the contrast against.
    if morphology == "stripe":
        angle = np.deg2rad(rng.uniform(0, 180))
        cy, cx = h * rng.uniform(0.35, 0.65), w * rng.uniform(0.35, 0.65)
        width = rng.uniform(4.0, 12.0)
        length = rng.uniform(0.35, 0.55) * np.hypot(h, w)
        perp = (xx - cx) * np.cos(angle) + (yy - cy) * np.sin(angle)
        along = -(xx - cx) * np.sin(angle) + (yy - cy) * np.cos(angle)
        mask = (np.abs(perp) <= width / 2.0) & (np.abs(along) <= length / 2.0)
    elif morphology == "patch":
        y0, x0 = rng.integers(h // 8, h // 2), rng.integers(w // 8, w // 2)
        mask = np.zeros(shape, dtype=bool)
        mask[y0:y0 + h // 5, x0:x0 + w // 4] = True
    elif morphology == "periodic":
        # Pulsed interference: a train of equally spaced blocks.
        period = int(rng.integers(24, 48))
        duty = max(int(period * 0.35), 3)
        y0 = int(rng.integers(h // 8, h // 2))
        x0, x1 = int(w * 0.15), int(w * 0.6)
        band = (yy >= y0) & (yy < y0 + h // 5) & (xx >= x0) & (xx < x1)
        mask = band & ((xx % period) < duty)
    else:
        raise ValueError(f"unknown morphology {morphology!r}")

    if not mask.any():
        mask[h // 2, w // 2] = True
    ys, xs = np.nonzero(mask)
    box = Box(float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1),
              f"rfi_{morphology}")
    return mask, box


def make_scene(
    injected_db: float,
    morphology: str = "stripe",
    channel: int = 1,
    cfg: SynthConfig | None = None,
) -> SynthScene:
    """Build one synthetic quicklook with interference at a known contrast.

    ``injected_db`` is the interference-to-signal ratio inside the footprint:
    the added power is ``P_scene * (10**(d/10) - 1)`` evaluated against the
    *local* scene level, so the nominal figure is the local contrast the
    interference actually produces rather than an absolute power.

    ``channel`` selects which polarisation receives it; the default is 1
    (cross-pol), matching the operational reality that interference shows up
    first in the channel closest to the noise floor.
    """
    cfg = cfg or SynthConfig()
    rng = np.random.default_rng(cfg.seed)

    copol_db = _terrain(cfg, rng)
    crosspol_db = copol_db - cfg.crosspol_offset_db + 0.8 * gaussian_filter(
        rng.standard_normal(cfg.shape), cfg.texture_scale * 1.5
    )
    base_power = [10 ** (copol_db / 10.0), 10 ** (crosspol_db / 10.0)]

    mask, box = _rfi_mask(cfg.shape, morphology, rng)
    gain = 10 ** (float(injected_db) / 10.0) - 1.0
    inj_power = [p.copy() for p in base_power]
    inj_power[channel][mask] = base_power[channel][mask] * (1.0 + gain)

    # One speckle realisation shared by both scenes, so their difference is the
    # interference alone and not a different draw of the noise.
    speck = [_speckle(cfg.shape, cfg.looks, rng) for _ in (0, 1)]
    base_amp = [np.sqrt(np.maximum(p, 0) * s) for p, s in zip(base_power, speck)]
    inj_amp = [np.sqrt(np.maximum(p, 0) * s) for p, s in zip(inj_power, speck)]

    # The stretch is derived from the interference-free scene and applied to
    # both, so a brighter injected scene cannot rescale itself back down.
    if cfg.common_stretch:
        hi = float(np.percentile(np.concatenate([a.ravel() for a in base_amp]),
                                 cfg.clip_percentile))
        scales = [hi, hi]
    else:
        scales = [float(np.percentile(a, cfg.clip_percentile)) for a in base_amp]

    def _quantise(amp: list[np.ndarray]) -> np.ndarray:
        dn = np.zeros((*cfg.shape, 3), dtype=np.float32)
        for k in (0, 1):
            dn[:, :, k] = np.clip(amp[k] / max(scales[k], 1e-12) * 255.0, 0, 255)
        dn = np.round(dn)
        dn[:, :, 2] = np.round(0.5 * (dn[:, :, 0] + dn[:, :, 1]))  # spec: B = mean(|p1|,|p2|)
        return dn

    dn_inj, dn_base = _quantise(inj_amp), _quantise(base_amp)
    name = f"synth_{morphology}_{injected_db:g}dB"
    ql = Quicklook(dn=dn_inj, name=f"{name}.png", boxes=[box])
    base_ql = Quicklook(dn=dn_base, name=f"{name}_baseline.png", boxes=[box])

    delta = (dn_inj[:, :, channel] - dn_base[:, :, channel])[mask]
    realised = {
        # The true effect of the injection at 8-bit precision: how many digital
        # numbers the interference actually moved the image by, inside its own
        # footprint.  Zero here means the signal fell entirely below the
        # quantiser, which is where the interesting part of the sweep begins.
        "dn_delta_median": float(np.median(delta)),
        "dn_delta_mean": float(np.mean(delta)),
        "dn_unchanged_fraction": float(np.mean(delta == 0)),
    }
    return SynthScene(ql, base_ql, mask, box, float(injected_db), int(channel),
                      morphology, realised)
