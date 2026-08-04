#!/usr/bin/env python3
"""Self-checking tests for the decomposition pipeline.

Runs standalone (``python tests/test_pipeline.py``) and under pytest.  The
synthetic generator supplies ground truth, so these assert real behaviour --
that the speckle model is identified correctly, that the ratio channel beats the
single channels on cross-pol interference, and that directional integration
recovers a stripe whose per-pixel contrast is below one digital number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearsar_rfi import directional, features, io, speckle, synth, triage, unmix  # noqa: E402


def test_speckle_moment_formulas():
    """Nakagami and Gamma moments must match their known closed forms."""
    cv, skew = speckle.nakagami_moments(1.0)  # Rayleigh amplitude
    assert abs(cv - 0.5227) < 1e-3, cv
    assert abs(skew - 0.6311) < 1e-3, skew
    cv_i, skew_i = speckle.gamma_moments(4.0)
    assert abs(cv_i - 0.5) < 1e-9
    assert abs(skew_i - 1.0) < 1e-9
    # The discriminator used by estimate_speckle_model: skew/CV is exactly 2 for
    # intensity at any look number, and strictly below 2 for amplitude.
    for looks in (1.0, 4.0, 16.0):
        c, s = speckle.nakagami_moments(looks)
        assert s / c < 1.99, (looks, s / c)


def test_composition_matches_spec():
    """The synthetic quicklook reproduces the documented B = (R+G)/2 rule."""
    scene = synth.make_scene(6.0, "stripe")
    comp = unmix.check_composition(scene.quicklook.dn)
    assert comp.matches_spec, comp.summary()
    assert comp.r2 > 0.999, comp.summary()


def test_speckle_model_identified_as_amplitude():
    """DNs built from sqrt(power) must be identified as amplitude, at ~the true ENL."""
    cfg = synth.SynthConfig(shape=(384, 384), looks=4.0, seed=3)
    scene = synth.make_scene(0.0, "stripe", cfg=cfg)  # 0 dB => no interference
    model = speckle.estimate_speckle_model(scene.quicklook.dn[:, :, 1])
    assert model.detection == "amplitude", model
    assert 1.5 < model.looks < 12.0, model  # terrain texture inflates CV a little


def test_ratio_channel_beats_single_channels():
    """Cross-pol interference must be more significant in the ratio than in either pol."""
    cfg = synth.SynthConfig(shape=(384, 384), looks=4.0, seed=11)
    scene = synth.make_scene(1.5, "patch", channel=1, cfg=cfg)
    row = triage.measure_box(scene.quicklook, scene.truth_box, with_spectral=False)
    assert row["abs_z_ratio"] > row["abs_z_p1"], row
    # And it recovers the right sign: extra cross-pol power lowers VV/VH.
    assert row["d_ratio_db"] < 0, row


def test_stripe_layer_recovers_injected_orientation():
    """The extracted stripe layer must correlate with the injected footprint."""
    cfg = synth.SynthConfig(shape=(256, 256), looks=4.0, seed=5)
    scene = synth.make_scene(8.0, "stripe", channel=1, cfg=cfg)
    um = unmix.unmix(scene.quicklook.dn)
    detail = directional.detail_image(um.ratio_db, 31)
    det = directional.stripe_snr(detail)
    layer = directional.stripe_layer(detail, det.angle_deg)
    assert layer.shape == detail.shape
    inside = layer[scene.truth_mask]
    outside = layer[~scene.truth_mask]
    # Cross-pol interference makes the ratio channel darker inside the stripe.
    assert np.median(inside) < np.median(outside), (np.median(inside), np.median(outside))
    assert det.snr > 5.0, det


def test_ratio_channel_suppresses_terrain():
    """The reason the ratio channel works: terrain is common-mode, so it cancels.

    Measured on an interference-free scene, the box-versus-surround z-score in a
    single polarisation is driven entirely by the terrain under the box.  The
    ratio channel must start from a far lower baseline, or none of its
    sensitivity advantage would be real.
    """
    cfg = synth.SynthConfig(shape=(384, 384), looks=4.0, seed=17)
    scene = synth.make_scene(1.0, "stripe", channel=1, cfg=cfg)
    base = triage.measure_box(scene.baseline, scene.truth_box, with_spectral=False)
    assert base["abs_z_ratio"] < 0.25 * base["abs_z_p2"], base
    assert base["abs_z_ratio"] < 0.25 * base["abs_z_p1"], base


def test_faint_interference_detected_below_the_quantiser():
    """Sub-LSB contrast is still recoverable, measured against a paired twin.

    At 0.3 dB into cross-pol the interference leaves most of its own footprint
    bit-identical after 8-bit quantisation.  The polarimetric ratio contrast must
    still separate the injected scene from its interference-free twin at the
    same box -- which is the whole claim about "invisible" boxes being findable.
    """
    cfg = synth.SynthConfig(shape=(384, 384), looks=4.0, seed=17)
    scene = synth.make_scene(0.3, "stripe", channel=1, cfg=cfg)

    assert abs(scene.realised["dn_delta_median"]) <= 1.0, scene.realised
    assert scene.realised["dn_unchanged_fraction"] > 0.1, scene.realised

    inj = triage.measure_box(scene.quicklook, scene.truth_box, with_spectral=False)
    base = triage.measure_box(scene.baseline, scene.truth_box, with_spectral=False)
    assert inj["abs_z_ratio"] > 1.2 * base["abs_z_ratio"], (
        inj["abs_z_ratio"], base["abs_z_ratio"])
    # Co-pol is untouched by a cross-pol injection, so it must not move: this is
    # what rules out the separation being a scene-wide brightness artefact.
    assert np.isclose(inj["abs_z_p1"], base["abs_z_p1"], rtol=1e-6), (
        inj["abs_z_p1"], base["abs_z_p1"])


def test_triage_summary_separates_labels_from_controls():
    """End-to-end: a strong box is attributed to a mechanism, not to 'none'."""
    cfg = synth.SynthConfig(shape=(320, 320), looks=4.0, seed=23)
    scene = synth.make_scene(6.0, "patch", channel=1, cfg=cfg)
    rng = np.random.default_rng(1)
    rows = triage.triage_image(scene.quicklook, rng=rng, controls_per_box=25,
                               with_spectral=False)
    result = triage.summarise(rows, quantile=0.95)
    assert result["n_labels"] == 1
    assert result["n_controls"] >= 10
    assert result["recoverable_fraction"] == 1.0, result["mechanisms"]


def test_feature_stack_shape_and_finiteness():
    """The exported stack must be complete, ordered and free of NaNs."""
    cfg = synth.SynthConfig(shape=(192, 192), looks=4.0, seed=31)
    scene = synth.make_scene(3.0, "periodic", channel=1, cfg=cfg)
    planes = features.build_stack(scene.quicklook, with_spectral=True, block=64)
    stack = features.stack_array(planes)
    assert stack.shape == (len(features.FEATURE_NAMES), 192, 192), stack.shape
    assert np.isfinite(stack).all()
    normed = features.normalise(stack)
    assert np.isfinite(normed).all()
    # Planes 0-2 must remain the untouched RGB, for pretrained-weight transfer.
    assert np.allclose(stack[0], scene.quicklook.dn[:, :, 0])
    assert np.allclose(stack[2], scene.quicklook.dn[:, :, 2])


def test_single_pol_is_flagged_and_degenerate():
    """Greyscale (single-pol) scenes must be flagged and yield a zero ratio channel."""
    cfg = synth.SynthConfig(shape=(128, 128), seed=41)
    scene = synth.make_scene(6.0, "stripe", cfg=cfg)
    grey = scene.quicklook.dn.copy()
    grey[:, :, 1] = grey[:, :, 0]
    grey[:, :, 2] = grey[:, :, 0]
    ql = io.Quicklook(dn=grey, name="grey.png", single_pol=True)
    um = unmix.unmix(ql.dn, single_pol=True)
    assert np.allclose(um.ratio_db, 0.0)
    assert np.allclose(um.pc2, 0.0)


def test_annotation_loaders_roundtrip(tmp_path: Path | None = None):
    """COCO, CSV and YOLO annotations must all load to the same boxes."""
    import json
    import tempfile

    tmp = Path(tmp_path or tempfile.mkdtemp())
    expected = io.Box(10.0, 20.0, 60.0, 80.0, "rfi")

    coco = tmp / "ann.json"
    coco.write_text(json.dumps({
        "images": [{"id": 1, "file_name": "a.png", "height": 100, "width": 100}],
        "annotations": [{"image_id": 1, "category_id": 1, "bbox": [10, 20, 50, 60]}],
        "categories": [{"id": 1, "name": "rfi"}],
    }))
    def _same(got: io.Box) -> bool:
        # YOLO coordinates are normalised, so de-normalising them lands within
        # floating-point distance of the target rather than exactly on it.
        return np.allclose([got.x1, got.y1, got.x2, got.y2],
                           [expected.x1, expected.y1, expected.x2, expected.y2])

    got = io.load_annotations(coco)["a.png"][0]
    assert _same(got), got

    csv_path = tmp / "ann.csv"
    csv_path.write_text("image,xmin,ymin,xmax,ymax,label\na.png,10,20,60,80,rfi\n")
    got = io.load_annotations(csv_path)["a.png"][0]
    assert _same(got), got

    yolo_dir = tmp / "yolo"
    yolo_dir.mkdir()
    (yolo_dir / "a.txt").write_text("0 0.35 0.5 0.5 0.6\n")
    got = io.load_annotations(yolo_dir, {"a.png": (100, 100)})["a.png"][0]
    assert _same(got), got
    assert np.isclose(expected.area, got.area), (expected.area, got.area)


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface any error as a failure
            failures += 1
            print(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {fn.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())


def test_clutter_scaling_detects_correlated_background():
    """Correlated clutter must fit alpha well below the independent-pixel 1.0."""
    from clearsar_rfi.clutter import measure_clutter_scaling

    rng = np.random.default_rng(3)
    # 1/f-like field: sum of progressively smoother random layers, which is how
    # terrain behaves and why window averaging stops helping.
    field = np.zeros((256, 256))
    for k in (2, 4, 8, 16, 32):
        coarse = rng.normal(size=(256 // k + 2, 256 // k + 2))
        field += np.kron(coarse, np.ones((k, k)))[:256, :256] * np.sqrt(k)
    field += 0.3 * rng.normal(size=field.shape)

    fit = measure_clutter_scaling(field)
    assert 0.0 < fit.alpha < 0.8, fit.alpha
    assert fit.actual_gain(10, 138) < 0.5 * fit.ideal_gain(10, 138)

    white = rng.normal(size=(256, 256))
    assert measure_clutter_scaling(white).alpha > fit.alpha


def test_azimuth_tophat_is_orientation_selective():
    """The filter must respond to a range-extended band, not to a vertical one."""
    from clearsar_rfi.clutter import azimuth_tophat

    a = np.zeros((128, 128))
    a[60:70, 20:110] = 1.0                     # RFI-shaped: wide and short
    horiz = np.abs(azimuth_tophat(a, 10, 48)).max()

    b = np.zeros((128, 128))
    b[20:110, 60:70] = 1.0                     # same area, wrong orientation
    vert = np.abs(azimuth_tophat(b, 10, 48)).max()

    assert horiz > 3 * vert, (horiz, vert)


def test_tail_ratio_flags_non_gaussian_clutter():
    """A Gaussian sits near 3.3; heavy-tailed clutter must score far above it."""
    from clearsar_rfi.clutter import GAUSSIAN_TAIL_RATIO, tail_ratio

    rng = np.random.default_rng(11)
    gauss = tail_ratio(rng.normal(size=200_000))
    assert abs(gauss - GAUSSIAN_TAIL_RATIO) < 1.0, gauss

    heavy = tail_ratio(rng.standard_t(df=2, size=200_000))
    assert heavy > 2 * gauss, (heavy, gauss)


def test_effective_looks_matches_measured_alpha():
    """The dataset-median box must be worth far fewer looks than its pixel count."""
    from clearsar_rfi.clutter import CLUTTER_ALPHA, effective_looks

    assert effective_looks(10, 138) < 0.05 * (10 * 138)
    assert effective_looks(10, 138, alpha=1.0) == 10 * 138
    assert 0.4 < CLUTTER_ALPHA < 0.45
