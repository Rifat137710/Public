"""Assembly of the physics-aware feature stack fed to a detector.

Replaces the three-channel RGB -- whose blue plane is redundant and whose two
real planes are never identified as separate receive channels -- with a stack in
which each plane is a quantity interference actually perturbs.  Feeding this to
a detector removes the burden of learning the transforms from ~3k boxes, the
same reasoning behind wavelet- and frequency-enhanced detectors for faint
targets in remote sensing.

To fine-tune an existing RGB-pretrained detector, keep the first three planes in
their original order (they are the untouched R/G/B) and inflate the stem
convolution, seeding the new input channels at zero so training starts from the
pretrained behaviour.
"""

from __future__ import annotations

import numpy as np

from . import directional, spectral, speckle, unmix
from .io import Quicklook

#: Plane order of the assembled stack.  Kept stable so trained weights transfer.
FEATURE_NAMES: tuple[str, ...] = (
    "r_dn", "g_dn", "b_dn",
    "p1_db", "p2_db", "ratio_db",
    "blue_residual", "pc2",
    "ratio_detail", "p2_detail",
    "cv_departure_p1", "cv_departure_p2",
    "kurtosis_p2",
    "directional_ratio", "directional_p2",
    "spectral_anisotropy", "spectral_peak_z",
)


def build_stack(
    ql: Quicklook,
    detail_scale: int = 31,
    window: int = 9,
    with_spectral: bool = True,
    block: int = 64,
) -> dict[str, np.ndarray]:
    """Compute every feature plane for one quicklook.

    ``with_spectral=False`` skips the block-wise FFT features, which dominate the
    runtime; the rest of the stack is separable filtering and rotations.
    """
    um = unmix.unmix(ql.dn, single_pol=ql.single_pol)

    ratio_detail = directional.detail_image(um.ratio_db, detail_scale)
    p2_detail = directional.detail_image(um.p2_db, detail_scale)

    dep1 = speckle.departure_maps(ql.dn[:, :, 0], um.model_p1, window)
    dep2 = speckle.departure_maps(ql.dn[:, :, 1], um.model_p2, window)

    planes: dict[str, np.ndarray] = {
        "r_dn": ql.dn[:, :, 0],
        "g_dn": ql.dn[:, :, 1],
        "b_dn": ql.dn[:, :, 2],
        "p1_db": um.p1_db,
        "p2_db": um.p2_db,
        "ratio_db": um.ratio_db,
        "blue_residual": um.blue_residual,
        "pc2": um.pc2,
        "ratio_detail": ratio_detail,
        "p2_detail": p2_detail,
        "cv_departure_p1": dep1["cv_departure"],
        "cv_departure_p2": dep2["cv_departure"],
        "kurtosis_p2": dep2["kurtosis"],
        "directional_ratio": directional.directional_response(ratio_detail),
        "directional_p2": directional.directional_response(p2_detail),
    }

    if with_spectral:
        spec = spectral.block_features(um.p2_db, block=block)
        planes["spectral_anisotropy"] = spec["anisotropy"]
        planes["spectral_peak_z"] = spec["peak_z"]
    else:
        zeros = np.zeros(ql.shape)
        planes["spectral_anisotropy"] = zeros
        planes["spectral_peak_z"] = zeros.copy()

    return {k: np.nan_to_num(np.asarray(planes[k], dtype=np.float32)) for k in FEATURE_NAMES}


def stack_array(planes: dict[str, np.ndarray]) -> np.ndarray:
    """Channels-first ``(C, H, W)`` float32 array in :data:`FEATURE_NAMES` order."""
    return np.stack([planes[name] for name in FEATURE_NAMES], axis=0)


def normalise(stack: np.ndarray, robust: bool = True) -> np.ndarray:
    """Per-plane standardisation, so planes with different units train together.

    Median/MAD by default: quicklooks routinely contain saturated returns and
    the interference itself is an outlier, so mean/std normalisation would let
    the very signal of interest set the scale.
    """
    out = np.empty_like(stack, dtype=np.float32)
    for i, plane in enumerate(stack):
        flat = plane[np.isfinite(plane)]
        if flat.size == 0:
            out[i] = 0.0
            continue
        if robust:
            centre = np.median(flat)
            scale = 1.4826 * np.median(np.abs(flat - centre))
        else:
            centre, scale = flat.mean(), flat.std()
        out[i] = (plane - centre) / max(float(scale), 1e-6)
    return out
