"""Un-mixing a dual-pol quicklook RGB back into its polarimetric channels.

The Sentinel-1 product spec composes dual-polarisation quicklooks as

    R = first polarisation        (co-pol,    VV or HH)
    G = second polarisation       (cross-pol, VH or HV)
    B = average of the absolute values of the two polarisations

so the blue channel is redundant by construction and the image has two real
degrees of freedom.  Two consequences drive everything here:

1. The **channel ratio** is the RFI-sensitive quantity.  Terrain drives both
   polarisations in a strongly correlated way -- scene structure is largely
   common-mode -- whereas interference enters the receiver in one polarisation
   channel only.  Differencing in the log domain suppresses the scene and keeps
   the interference.  This is the basis of the published dual-pol RFI Index.

2. Cross-pol backscatter sits 8-13 dB lower and much closer to the noise floor,
   so a given interference power is a large relative bump in the cross-pol
   channel and a negligible one in co-pol.  In an RGB rendering that is a
   near-isoluminant *chromatic* change, which both human vision and
   ImageNet-pretrained CNNs are poor at.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .speckle import EPS, SpeckleModel, estimate_speckle_model


@dataclass
class Composition:
    """Result of regressing the blue channel on the two polarimetric channels."""

    a: float  # coefficient on R
    b: float  # coefficient on G
    c: float  # intercept (DN)
    r2: float  # coefficient of determination
    matches_spec: bool  # consistent with B = (R + G) / 2

    def summary(self) -> str:
        verdict = "matches spec B=(R+G)/2" if self.matches_spec else "DOES NOT match spec"
        return (f"B = {self.a:.4f}*R + {self.b:.4f}*G + {self.c:.2f}  "
                f"(R^2={self.r2:.5f})  [{verdict}]")


def check_composition(dn: np.ndarray, tol: float = 0.05) -> Composition:
    """Verify empirically how the blue channel is built from R and G.

    Worth running once on your own copy of the data before trusting anything
    downstream: a re-exported or re-stretched dataset can use different
    coefficients, and single-pol scenes give a degenerate fit.
    """
    r = dn[:, :, 0].ravel().astype(np.float64)
    g = dn[:, :, 1].ravel().astype(np.float64)
    b = dn[:, :, 2].ravel().astype(np.float64)
    design = np.column_stack([r, g, np.ones_like(r)])
    coef, *_ = np.linalg.lstsq(design, b, rcond=None)
    pred = design @ coef
    ss_res = float(np.sum((b - pred) ** 2))
    ss_tot = float(np.sum((b - b.mean()) ** 2))
    r2 = 1.0 - ss_res / max(ss_tot, EPS)
    a, bb, c = (float(x) for x in coef)
    matches = abs(a - 0.5) < tol and abs(bb - 0.5) < tol and abs(c) < tol * 255.0
    return Composition(a, bb, c, r2, bool(matches))


def to_db(dn: np.ndarray, detection: str = "amplitude") -> np.ndarray:
    """Convert digital numbers to a decibel scale.

    ``detection`` selects the assumed relationship between DN and radar power;
    use :func:`clearsar_rfi.speckle.estimate_speckle_model` to determine it from
    the data rather than guessing.  The scale is relative -- quicklooks are not
    radiometrically calibrated -- but all downstream measurements are local
    contrasts, which are unaffected by an unknown common gain.
    """
    x = np.asarray(dn, dtype=np.float64) + 0.5  # half-DN offset: avoids log(0)
    factor = 20.0 if detection == "amplitude" else 10.0
    return factor * np.log10(x)


@dataclass
class Unmixed:
    """Polarimetric channels recovered from a quicklook RGB."""

    p1_db: np.ndarray  # co-pol, dB
    p2_db: np.ndarray  # cross-pol, dB
    ratio_db: np.ndarray  # p1 - p2, the differential channel
    blue_residual: np.ndarray  # B - (R + G)/2, in DN
    pc2: np.ndarray  # second principal component of (p1, p2)
    detection: str
    model_p1: SpeckleModel
    model_p2: SpeckleModel
    single_pol: bool

    def channels(self) -> dict[str, np.ndarray]:
        return {
            "p1_db": self.p1_db,
            "p2_db": self.p2_db,
            "ratio_db": self.ratio_db,
            "blue_residual": self.blue_residual,
            "pc2": self.pc2,
        }


def unmix(dn: np.ndarray, single_pol: bool = False, detection: str | None = None) -> Unmixed:
    """Recover polarimetric channels and derived differential channels.

    For single-polarisation products the ratio and PC2 channels are identically
    zero and carry no information; they are still returned so that downstream
    array shapes stay uniform, and ``single_pol`` flags the situation.
    """
    dn = np.asarray(dn, dtype=np.float64)
    r, g, b = dn[:, :, 0], dn[:, :, 1], dn[:, :, 2]

    m1 = estimate_speckle_model(r)
    m2 = estimate_speckle_model(g)
    if detection is None:
        # Trust whichever channel fits its model better; they share a stretch.
        detection = m1.detection if m1.residual <= m2.residual else m2.detection

    p1_db = to_db(r, detection)
    p2_db = to_db(g, detection)
    ratio_db = p1_db - p2_db
    blue_residual = b - 0.5 * (r + g)

    if single_pol:
        pc2 = np.zeros_like(p1_db)
        ratio_db = np.zeros_like(p1_db)
    else:
        pc2 = _second_component(p1_db, p2_db)

    return Unmixed(p1_db, p2_db, ratio_db, blue_residual, pc2,
                   detection, m1, m2, bool(single_pol))


def _second_component(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Minor principal component of two correlated channels.

    With only two highly correlated channels, PC1 is essentially total
    brightness and PC2 is what is left once the common-mode scene response is
    projected out -- differential response plus noise, which is where
    channel-specific interference lives.
    """
    stack = np.stack([a.ravel(), b.ravel()])
    stack = stack - stack.mean(axis=1, keepdims=True)
    cov = np.cov(stack)
    vals, vecs = np.linalg.eigh(cov)  # ascending
    minor = vecs[:, 0]
    return (minor[0] * (a - a.mean()) + minor[1] * (b - b.mean()))


def decorrelation_stretch(dn: np.ndarray, target_sd: float = 40.0) -> np.ndarray:
    """Decorrelation stretch of the RGB composite, returned as uint8.

    Rotates into the principal-component basis, equalises the component
    variances, and rotates back.  Because the quicklook channels are strongly
    correlated, this pulls apart exactly the subtle chromatic differences that a
    plain rendering compresses -- which is what makes polarisation-specific
    interference visible by eye.  Purely a visualisation aid; the quantitative
    detectors work on the log channels instead.
    """
    x = np.asarray(dn, dtype=np.float64).reshape(-1, 3)
    mean = x.mean(axis=0)
    xc = x - mean
    cov = np.cov(xc, rowvar=False)
    vals, vecs = np.linalg.eigh(cov)
    vals = np.maximum(vals, EPS)
    scale = target_sd / np.sqrt(vals)
    transform = vecs @ np.diag(scale) @ vecs.T
    out = xc @ transform.T + mean
    return np.clip(out, 0, 255).astype(np.uint8).reshape(dn.shape)
