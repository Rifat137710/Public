"""Physics-aware decomposition toolkit for RFI detection in Sentinel-1 quicklooks.

Built for the ESA Phi-lab ClearSAR Track-1 dataset (Sentinel-1 quicklook RGB PNGs
with bounding-box annotations of radio-frequency interference).

The central premise: a Sentinel-1 dual-pol quicklook is not a natural RGB image.
Per the Sentinel-1 product spec, quicklooks are power-detected, averaged and
decimated, scaled to 8 bit, and for dual-pol products composed as

    R = first polarisation (co-pol,    e.g. VV / HH)
    G = second polarisation (cross-pol, e.g. VH / HV)
    B = average of the absolute values of the two polarisations

so the image carries only *two* independent channels. Interference enters the
receiver in one polarisation channel and does not obey the co-pol/cross-pol
relationship terrain does, which makes the channel ratio far more sensitive to
RFI than any single channel or their RGB rendering.

Modules
-------
io          Loading quicklooks and bounding boxes (COCO / YOLO / VOC / CSV).
unmix       RGB -> polarimetric channels, ratio, blue-channel consistency, PCA.
speckle     Speckle-model identification and local-statistics departure maps.
directional Radon matched filtering and unidirectional stripe-layer extraction.
spectral    Block-wise 2-D spectral anisotropy and periodicity features.
features    Assembly of the multi-channel physics feature stack.
triage      Per-box recoverability metrics ("which ghost boxes are findable?").
synth       Synthetic quicklooks with RFI injected at a known dB level.
viz         Diagnostic panels.
"""

__version__ = "0.1.0"

__all__ = [
    "io",
    "unmix",
    "speckle",
    "directional",
    "spectral",
    "features",
    "triage",
    "synth",
    "viz",
]
