"""Diagnostic panels: seeing a ghost box in every decomposed domain at once."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import directional, speckle, unmix
from .io import Box, Quicklook


def _stretch(x: np.ndarray, lo: float = 2.0, hi: float = 98.0) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    finite = x[np.isfinite(x)]
    if finite.size == 0:
        return np.zeros_like(x)
    a, b = np.percentile(finite, [lo, hi])
    return np.clip((x - a) / max(b - a, 1e-9), 0, 1)


def box_panel(
    ql: Quicklook,
    box: Box,
    out_path: str | Path | None = None,
    pad: int | None = None,
    detail_scale: int = 31,
):
    """Render one annotated box across the decomposition channels.

    The point of looking at these side by side is diagnostic: a box that is flat
    in the RGB crop but obvious in ``ratio detail`` is polarisation-specific
    interference, one that only appears after directional integration is a faint
    stripe, and one that shows up solely in ``CV departure`` is most likely
    notch-filtered residue with no brightness signature left.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if pad is None:
        # Scale context off the *long* side: RFI stripes are thin and long, and
        # padding by the short side alone leaves a sliver with no terrain to
        # compare against.
        pad = int(np.clip(0.25 * max(box.width, box.height), 24, 128))
    ys, xs = box.slices(ql.shape, pad=pad)
    um = unmix.unmix(ql.dn, single_pol=ql.single_pol)

    rgb = ql.dn[ys, xs].astype(np.uint8)
    dcs = unmix.decorrelation_stretch(ql.dn)[ys, xs]
    ratio = um.ratio_db[ys, xs]
    ratio_detail = directional.detail_image(ratio, detail_scale)
    dep = speckle.departure_maps(ql.dn[:, :, 1][ys, xs], um.model_p2)
    dirmap = directional.directional_response(ratio_detail)
    det = directional.stripe_snr(ratio_detail)
    layer = directional.stripe_layer(ratio_detail, det.angle_deg)

    panels = [
        ("RGB quicklook", rgb, None),
        ("decorrelation stretch", dcs, None),
        ("ratio VV/VH [dB]", _stretch(ratio), "viridis"),
        ("ratio detail", _stretch(ratio_detail), "coolwarm"),
        ("CV departure (p2)", _stretch(dep["cv_departure"]), "coolwarm"),
        ("directional response", _stretch(dirmap), "magma"),
        (f"stripe layer @{det.angle_deg:.0f}deg  SNR={det.snr:.1f}", _stretch(layer), "coolwarm"),
        ("kurtosis (p2)", _stretch(dep["kurtosis"]), "magma"),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(16, 8.5))
    for ax, (title, data, cmap) in zip(axes.ravel(), panels):
        ax.imshow(data, cmap=cmap)
        ax.set_title(title, fontsize=10)
        ax.axis("off")
        # Outline the annotation itself within the padded crop.
        rect = plt.Rectangle(
            (box.x1 - xs.start, box.y1 - ys.start), box.width, box.height,
            fill=False, edgecolor="red", linewidth=1.2,
        )
        ax.add_patch(rect)
    fig.suptitle(f"{ql.name}  box=({box.x1:.0f},{box.y1:.0f})-({box.x2:.0f},{box.y2:.0f})")
    fig.tight_layout()

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return Path(out_path)
    return fig
