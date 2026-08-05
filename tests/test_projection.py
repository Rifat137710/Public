"""Projection port: reproduce thesis Table 5.3, and pin the infeasibility finding."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from safesac.config import ExperimentConfig
from safesac.network import build_feeder, scale_loads, set_loads, set_pv_power, set_station_power
from safesac.powerflow import JacobianSensitivities, RadialPowerFlow
from safesac.projection import SensitivityProjector, compute_loading_sensitivities

# thesis11.ipynb Block 4, Test 2 (load scale 0.40, zero margin, -80 kW request)
PUBLISHED_SAFE_P = {
    "weak": [-54.135, -77.948, -76.850, -73.303],
    "strong": [-80.0, -80.0, -80.0, -80.0],
}


def _staged(variant: str, scale: float, margin: float):
    cfg = ExperimentConfig.thesis_block1(variant)
    cfg = replace(cfg, safety=replace(cfg.safety, projection_margin_pu=margin))
    feeder = build_feeder(cfg.feeder)
    scale_loads(feeder, scale)
    set_pv_power(feeder, np.zeros(3))
    set_station_power(feeder, np.zeros(4), np.zeros(4))
    solver = RadialPowerFlow(feeder)
    pf = solver.solve()
    sens = JacobianSensitivities(feeder).compute(pf)
    loading = compute_loading_sensitivities(feeder, solver)
    return cfg, feeder, solver, sens, loading


@pytest.mark.parametrize("variant", ["weak", "strong"])
def test_reproduces_published_table_5_3(variant):
    cfg, _, _, sens, loading = _staged(variant, scale=0.40, margin=0.0)
    proj = SensitivityProjector(cfg, 4, 34)
    raw = np.full(4, -80.0)
    res = proj.project(
        raw, np.zeros(4), raw.copy(), np.zeros(4), sens, loading, skip_when_feasible=False
    )
    assert res.ok
    assert res.p_kw == pytest.approx(PUBLISHED_SAFE_P[variant], abs=1e-3)


def test_grid_awareness_gap_matches_published():
    """||safe_weak - safe_strong||_inf = 25.865 kW at the Block 4 operating point."""
    out = {}
    for variant in ("weak", "strong"):
        cfg, _, _, sens, loading = _staged(variant, scale=0.40, margin=0.0)
        proj = SensitivityProjector(cfg, 4, 34)
        raw = np.full(4, -80.0)
        out[variant] = proj.project(
            raw, np.zeros(4), raw.copy(), np.zeros(4), sens, loading, skip_when_feasible=False
        ).p_kw
    gap = float(np.max(np.abs(out["weak"] - out["strong"])))
    assert gap == pytest.approx(25.865, abs=1e-3)


def test_projection_is_identity_on_a_feasible_action():
    cfg, _, _, sens, loading = _staged("weak", scale=0.40, margin=0.0)
    proj = SensitivityProjector(cfg, 4, 34)
    raw = np.full(4, -10.0)
    res = proj.project(
        raw, np.zeros(4), np.zeros(4), np.zeros(4), sens, loading, skip_when_feasible=False
    )
    assert res.ok
    assert res.p_kw == pytest.approx(raw, abs=1e-3)


def test_feasibility_precheck_agrees_with_the_solver():
    """The skip path must never let through something the solver would change."""
    cfg, _, _, sens, loading = _staged("weak", scale=0.40, margin=0.0)
    proj = SensitivityProjector(cfg, 4, 34)
    rng = np.random.default_rng(0)
    prev = np.zeros(4)
    for _ in range(40):
        p = rng.uniform(-40, 40, 4)
        q = rng.uniform(-40, 40, 4)
        skipped = proj.project(p, q, prev, np.zeros(4), sens, loading, skip_when_feasible=True)
        solved = proj.project(p, q, prev, np.zeros(4), sens, loading, skip_when_feasible=False)
        if not skipped.solved:  # pre-check claimed feasible
            assert solved.ok
            assert skipped.p_kw == pytest.approx(solved.p_kw, abs=1e-4)
            assert skipped.q_kvar == pytest.approx(solved.q_kvar, abs=1e-4)


# --- audit item A5 ---------------------------------------------------------


def _weekday_multiplier(hour: float) -> float:
    return (
        0.40
        + 0.40 * math.exp(-0.5 * ((hour - 7.5) / 1.5) ** 2)
        + 0.60 * math.exp(-0.5 * ((hour - 19.0) / 2.0) ** 2)
    )


def _daily_infeasibility_rate(scale: float, margin: float) -> float:
    cfg = ExperimentConfig.thesis_final("weak")
    cfg = replace(cfg, safety=replace(cfg.safety, projection_margin_pu=margin))
    feeder = build_feeder(cfg.feeder)
    solver = RadialPowerFlow(feeder)
    proj = SensitivityProjector(cfg, 4, 34)

    prev = np.zeros(4)
    sens = loading = None
    n_infeasible = 0
    for step in range(288):
        m = _weekday_multiplier(step * 5 / 60.0)
        set_loads(feeder, feeder.base_load_p_mw * scale * m, feeder.base_load_q_mvar * scale * m)
        set_pv_power(feeder, np.zeros(3))
        set_station_power(feeder, prev, np.zeros(4))
        pf = solver.solve()
        if step % cfg.safety.sensitivity_refresh_steps == 0:
            sens = JacobianSensitivities(feeder).compute(pf)
            loading = compute_loading_sensitivities(feeder, solver)
            proj.on_refresh()
        res = proj.project(
            np.full(4, -40.0), np.zeros(4), prev, np.zeros(4), sens, loading,
            skip_when_feasible=False,
        )
        if not res.ok:
            n_infeasible += 1
        prev = res.p_kw
    return n_infeasible / 288


def test_thesis_operating_point_makes_the_projection_infeasible():
    """At load 0.50 with the 0.010 pu margin the layer fails on ~1 step in 8.

    Idle Vmin is 0.9441, below the margin-tightened bound of 0.960, and the
    stations cannot lift the deepest buses that far. The fallback returns an
    all-zero command -- so during the evening peak SafeSAC was switched off
    rather than projected.
    """
    assert _daily_infeasibility_rate(0.50, 0.010) == pytest.approx(0.125, abs=0.01)
    assert _daily_infeasibility_rate(0.50, 0.005) == pytest.approx(0.045, abs=0.01)
    assert _daily_infeasibility_rate(0.50, 0.000) == 0.0


def test_clean_operating_point_keeps_the_projection_feasible():
    assert _daily_infeasibility_rate(0.40, 0.010) == 0.0
