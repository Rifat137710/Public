"""Regression tests: the port must reproduce the thesis exactly.

Every expected value here is taken from `thesis11.ipynb` outputs or the shipped
artifact bundle, and is recorded in docs/00-knowledge-base.md.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from safesac.network import (
    FeederConfig,
    build_feeder,
    scale_loads,
    set_loads,
    set_pv_power,
    set_station_power,
)
from safesac.powerflow import (
    JacobianSensitivities,
    RadialPowerFlow,
    finite_difference_sensitivities,
    run_pf_reference,
)


@pytest.fixture(params=["weak", "strong"])
def feeder(request):
    return build_feeder(FeederConfig(variant=request.param))


# --- Thesis Table 4.1 and the Block-1 validation output --------------------

THESIS_SENSITIVITIES = {
    "weak": {
        17: (9.0772e-05, 7.1038e-05),
        21: (2.4648e-05, 2.2285e-05),
        24: (2.5527e-05, 1.6804e-05),
        32: (5.7101e-05, 4.4578e-05),
    },
    "strong": {
        17: (7.9881e-05, 6.4585e-05),
        21: (1.8230e-05, 1.8769e-05),
        24: (1.8595e-05, 1.3171e-05),
        32: (4.7741e-05, 3.8907e-05),
    },
}


def test_topology_matches_thesis(feeder):
    expected_n_bus = 34 if feeder.config.variant == "weak" else 33
    assert feeder.n_bus == expected_n_bus
    assert feeder.ev_buses == [17, 21, 24, 32]
    assert feeder.pv_buses == [5, 12, 29]


def test_nominal_baseline_matches_thesis(feeder):
    expected = {"weak": (0.8816, 338.6), "strong": (0.9131, 202.7)}[feeder.config.variant]
    res = run_pf_reference(feeder)
    assert res.converged
    assert res.v_pu.min() == pytest.approx(expected[0], abs=5e-5)
    assert res.p_loss_mw * 1000 == pytest.approx(expected[1], abs=0.05)


def test_radial_sweep_matches_pandapower(feeder):
    """The fast solver is only useful if it is the same solver."""
    fast = RadialPowerFlow(feeder)
    rng = np.random.default_rng(0)
    for _ in range(100):
        scale_loads(feeder, rng.uniform(0.2, 1.0))
        set_station_power(feeder, rng.uniform(-80, 80, 4), rng.uniform(-80, 80, 4))
        ref, got = run_pf_reference(feeder), fast.solve()
        assert got.converged
        assert np.max(np.abs(ref.v_pu - got.v_pu)) < 1e-7
        assert got.p_loss_mw == pytest.approx(ref.p_loss_mw, abs=1e-7)


def test_analytic_sensitivities_match_thesis(feeder):
    """Jacobian sensitivities must agree with the published finite differences."""
    analytic = JacobianSensitivities(feeder).compute(run_pf_reference(feeder))
    for j, bus in enumerate(feeder.ev_buses):
        dp, dq = THESIS_SENSITIVITIES[feeder.config.variant][bus]
        assert abs(analytic.dv_dp[bus, j]) == pytest.approx(dp, rel=1e-3)
        assert abs(analytic.dv_dq[bus, j]) == pytest.approx(dq, rel=1e-3)


def test_analytic_agrees_with_finite_difference(feeder):
    analytic = JacobianSensitivities(feeder).compute(run_pf_reference(feeder))
    fd = finite_difference_sensitivities(feeder, perturb_kw=4.0)
    assert np.max(np.abs(analytic.dv_dp - fd.dv_dp)) < 1e-8
    assert np.max(np.abs(analytic.dv_dq - fd.dv_dq)) < 1e-8


def test_vp_dominance_on_weak_feeder():
    """The thesis's central physical premise, at its reported operating point."""
    feeder = build_feeder(FeederConfig(variant="weak"))
    scale_loads(feeder, 0.50)
    s = JacobianSensitivities(feeder).compute(run_pf_reference(feeder))
    dp = np.mean([abs(s.dv_dp[b, j]) for j, b in enumerate(feeder.ev_buses)])
    dq = np.mean([abs(s.dv_dq[b, j]) for j, b in enumerate(feeder.ev_buses)])
    assert dp == pytest.approx(4.512e-05, rel=1e-3)
    assert dq == pytest.approx(3.550e-05, rel=1e-3)
    assert dp / dq == pytest.approx(1.271, abs=1e-3)


@pytest.mark.parametrize("scale,expected_vmin", [(0.40, 0.9557), (0.50, 0.9441)])
def test_quoted_operating_points(scale, expected_vmin):
    feeder = build_feeder(FeederConfig(variant="weak"))
    scale_loads(feeder, scale)
    assert run_pf_reference(feeder).v_pu.min() == pytest.approx(expected_vmin, abs=5e-5)


# --- Sign convention, pinned. See docs/01-audit item A3. -------------------


def test_positive_power_is_injection_and_raises_voltage():
    feeder = build_feeder(FeederConfig(variant="weak"))
    scale_loads(feeder, 0.50)
    pf = RadialPowerFlow(feeder)

    set_station_power(feeder, np.zeros(4), np.zeros(4))
    v_idle = pf.solve().v_pu.min()

    set_station_power(feeder, np.full(4, +80.0), np.zeros(4))
    v_inject = pf.solve().v_pu.min()

    set_station_power(feeder, np.full(4, -80.0), np.zeros(4))
    v_charge = pf.solve().v_pu.min()

    assert v_inject > v_idle > v_charge, (
        "p_kw > 0 must inject (V2G, raises voltage); p_kw < 0 must charge (lowers it)"
    )


# --- The exogenous-violation floor. See docs/01-audit item A4. -------------


def _weekday_multiplier(hour: float) -> float:
    return (
        0.40
        + 0.40 * math.exp(-0.5 * ((hour - 7.5) / 1.5) ** 2)
        + 0.60 * math.exp(-0.5 * ((hour - 19.0) / 2.0) ** 2)
    )


def _daily_violation_rate(feeder, pf, scale: float, station_kw: float) -> float:
    n = 0
    for step in range(288):
        m = _weekday_multiplier(step * 5 / 60.0)
        set_loads(feeder, feeder.base_load_p_mw * scale * m, feeder.base_load_q_mvar * scale * m)
        set_pv_power(feeder, np.zeros(3))
        set_station_power(feeder, np.full(4, station_kw), np.zeros(4))
        if pf.solve().v_pu.min() < 0.95:
            n += 1
    return n / 288


def test_load_scale_050_has_a_large_exogenous_violation_floor():
    """At the thesis operating point, ~10% of steps violate with zero EV power.

    That floor exceeds the measured SafeSAC (0.0912) and SAC-Lag (0.0904)
    rates, so the published safety comparison is dominated by background load.
    """
    feeder = build_feeder(FeederConfig(variant="weak"))
    pf = RadialPowerFlow(feeder)
    assert _daily_violation_rate(feeder, pf, 0.50, 0.0) == pytest.approx(0.1007, abs=0.002)


def test_load_scale_040_is_the_clean_operating_point():
    """Zero violations when idle, real violations under full charging.

    This is the operating point the re-run uses: every violation is then
    attributable to the controller rather than to background demand.
    """
    feeder = build_feeder(FeederConfig(variant="weak"))
    pf = RadialPowerFlow(feeder)
    assert _daily_violation_rate(feeder, pf, 0.40, 0.0) == 0.0
    assert _daily_violation_rate(feeder, pf, 0.40, -40.0) == 0.0
    assert _daily_violation_rate(feeder, pf, 0.40, -80.0) == pytest.approx(0.0868, abs=0.002)


def test_v2g_injection_never_violates_the_lower_bound():
    """Why the paper needs an overvoltage scenario to show V2G curtailment."""
    feeder = build_feeder(FeederConfig(variant="weak"))
    pf = RadialPowerFlow(feeder)
    for scale in (0.35, 0.40, 0.45, 0.50):
        assert _daily_violation_rate(feeder, pf, scale, +80.0) == 0.0
