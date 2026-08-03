"""Speckle-model identification and local-statistics departure maps.

Fully developed speckle has a *known* distribution, which is what makes it a
usable reference.  For an L-look intensity image the distribution is Gamma with
coefficient of variation ``CV = 1/sqrt(L)`` and skewness ``2/sqrt(L)``; for the
corresponding amplitude image it is Nakagami-m with ``m = L``.  Interference
violates this model:

* partially coherent / deterministic interference is *smoother* than speckle,
  so the local CV falls below the model value;
* pulsed or impulsive interference raises local skewness and kurtosis;
* notch-filtered residual RFI narrows the effective bandwidth, which changes the
  local texture correlation without necessarily changing the mean level at all.

That last case is the one no brightness-based detector can reach, and it is the
reason these maps exist.

An important practical wrinkle: the quicklook spec says images are *power*
detected, but the 8-bit display stretch applied afterwards is not documented, so
whether a digital number is proportional to amplitude or to intensity is
unknown.  :func:`estimate_speckle_model` settles it from the data, using the
fact that the skewness-to-CV ratio is exactly 2 for Gamma intensity but
markedly lower for Nakagami amplitude (1.21 at single look).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter
from scipy.special import gammaln

EPS = 1e-6


# --------------------------------------------------------------------------- #
# Theoretical speckle moments
# --------------------------------------------------------------------------- #

def gamma_moments(looks: float) -> tuple[float, float]:
    """(CV, skewness) of an L-look *intensity* image of fully developed speckle."""
    looks = max(float(looks), 1e-3)
    return 1.0 / np.sqrt(looks), 2.0 / np.sqrt(looks)


def nakagami_moments(looks: float) -> tuple[float, float]:
    """(CV, skewness) of an L-look *amplitude* image of fully developed speckle.

    Uses the Nakagami-m moments ``E[A^k] = Gamma(L + k/2) / (Gamma(L) L^{k/2})``
    with the second moment normalised to unity.
    """
    looks = max(float(looks), 1e-3)

    def ratio(k: float) -> float:
        return float(np.exp(gammaln(looks + k / 2.0) - gammaln(looks) - (k / 2.0) * np.log(looks)))

    m1, m3 = ratio(1.0), ratio(3.0)
    var = max(1.0 - m1 * m1, EPS)  # m2 == 1 by construction
    cv = np.sqrt(var) / m1
    skew = (m3 - 3.0 * m1 * var - m1**3) / var**1.5
    return float(cv), float(skew)


# --------------------------------------------------------------------------- #
# Local statistics
# --------------------------------------------------------------------------- #

def local_moments(img: np.ndarray, window: int = 9) -> dict[str, np.ndarray]:
    """Local mean, standard deviation, CV, skewness and excess kurtosis.

    Computed with box filters over ``window``x``window`` neighbourhoods, which is
    separable and therefore cheap enough to run over a whole dataset.
    """
    img = np.asarray(img, dtype=np.float64)
    m1 = uniform_filter(img, window)
    m2 = uniform_filter(img * img, window)
    m3 = uniform_filter(img**3, window)
    m4 = uniform_filter(img**4, window)

    var = np.maximum(m2 - m1**2, EPS)
    sd = np.sqrt(var)
    # Central moments from raw moments.
    mu3 = m3 - 3.0 * m1 * m2 + 2.0 * m1**3
    mu4 = m4 - 4.0 * m1 * m3 + 6.0 * m1**2 * m2 - 3.0 * m1**4
    return {
        "mean": m1,
        "std": sd,
        "cv": sd / np.maximum(np.abs(m1), EPS),
        "skew": mu3 / var**1.5,
        "kurtosis": mu4 / var**2 - 3.0,
    }


def _homogeneous_mask(img: np.ndarray, window: int, keep: float = 0.3) -> np.ndarray:
    """Boolean mask of the structurally flattest ``keep`` fraction of pixels.

    Selection is driven by the gradient of a *smoothed* image, so it is blind to
    the speckle statistics themselves and does not bias the CV estimate the way
    selecting on low CV directly would.
    """
    smooth = uniform_filter(np.asarray(img, dtype=np.float64), max(window * 3, 9))
    gy, gx = np.gradient(smooth)
    grad = np.hypot(gy, gx) / np.maximum(smooth, EPS)
    edge = max(window, 8)
    interior = np.zeros(img.shape, dtype=bool)
    interior[edge:-edge or None, edge:-edge or None] = True
    if not interior.any():
        interior[:] = True
    thresh = np.quantile(grad[interior], np.clip(keep, 0.02, 1.0))
    return interior & (grad <= thresh)


@dataclass
class SpeckleModel:
    """Identified speckle model for one channel of a quicklook."""

    detection: str  # "amplitude" or "intensity"
    looks: float  # equivalent number of looks
    cv: float  # model CV at these looks, in the observed domain
    skew: float  # model skewness
    cv_observed: float
    skew_observed: float
    residual: float  # normalised misfit; large values mean "do not trust this"

    def as_dict(self) -> dict[str, float | str]:
        return {
            "detection": self.detection,
            "looks": self.looks,
            "model_cv": self.cv,
            "model_skew": self.skew,
            "observed_cv": self.cv_observed,
            "observed_skew": self.skew_observed,
            "model_residual": self.residual,
        }


def estimate_speckle_model(
    channel: np.ndarray,
    window: int = 9,
    looks_grid: np.ndarray | None = None,
) -> SpeckleModel:
    """Identify whether DNs behave as amplitude or intensity, and estimate ENL.

    Both hypotheses predict a constant CV, so CV alone cannot separate them; the
    skewness-to-CV *ratio* can, being 2 for Gamma intensity at every look number
    and strictly below 2 for Nakagami amplitude.
    """
    ch = np.asarray(channel, dtype=np.float64)
    mom = local_moments(ch, window)
    mask = _homogeneous_mask(ch, window)
    if mask.sum() < 64:  # degenerate (tiny or near-constant) image
        mask = np.isfinite(ch)
    cv_obs = float(np.median(mom["cv"][mask]))
    skew_obs = float(np.median(mom["skew"][mask]))

    if looks_grid is None:
        looks_grid = np.geomspace(0.5, 200.0, 400)

    best: SpeckleModel | None = None
    for detection, fn in (("amplitude", nakagami_moments), ("intensity", gamma_moments)):
        for looks in looks_grid:
            cv_th, skew_th = fn(looks)
            resid = ((cv_th - cv_obs) / max(cv_obs, EPS)) ** 2 + (
                (skew_th - skew_obs) / max(abs(skew_obs), 0.05)
            ) ** 2
            if best is None or resid < best.residual:
                best = SpeckleModel(detection, float(looks), cv_th, skew_th,
                                    cv_obs, skew_obs, float(resid))
    assert best is not None
    return best


def departure_maps(
    channel: np.ndarray,
    model: SpeckleModel,
    window: int = 9,
) -> dict[str, np.ndarray]:
    """Maps of how far local statistics stray from the fitted speckle model.

    ``cv_departure`` is the fractional deviation of the local CV from the model
    value: negative where the field is smoother than speckle (coherent or
    partially coherent interference), positive where it is rougher (terrain
    structure, or impulsive interference).
    """
    mom = local_moments(channel, window)
    return {
        "cv_departure": mom["cv"] / max(model.cv, EPS) - 1.0,
        "skew_departure": mom["skew"] - model.skew,
        "kurtosis": mom["kurtosis"],
    }
