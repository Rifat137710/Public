"""Projection port: reproduce thesis Table 5.3, and pin the infeasibility finding."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv
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


# --- audit item A3: the missing V2G upper-bound experiment ------------------


def _high_pv_state(v2g_kw: float):
    cfg = ExperimentConfig.high_pv_overvoltage("weak")
    feeder = build_feeder(cfg.feeder)
    scale_loads(feeder, cfg.scenario.load_scale)
    set_pv_power(feeder, np.array(cfg.feeder.pv_rated_kw))
    set_station_power(feeder, np.full(4, v2g_kw), np.zeros(4))
    solver = RadialPowerFlow(feeder)
    return cfg, feeder, solver, solver.solve()


def test_v2g_injection_causes_the_upper_bound_breach():
    """Idle is compliant; the V2G request itself is what breaks the band."""
    cfg = ExperimentConfig.high_pv_overvoltage("weak")
    _, _, _, idle = _high_pv_state(0.0)
    _, _, _, full = _high_pv_state(cfg.feeder.ev_station_kva)

    tightened = cfg.safety.voltage_upper_pu - cfg.safety.projection_margin_pu
    assert idle.v_pu.max() == pytest.approx(1.0230, abs=1e-3)
    assert idle.v_pu.max() < tightened, "idle must sit inside the band the projector enforces"
    assert full.v_pu.max() == pytest.approx(1.0538, abs=1e-3)
    assert full.v_pu.max() > cfg.safety.voltage_upper_pu


# The upper-bound analogue of published Table 5.3, linearised about a hub that
# is already exporting at full rate -- so the voltage constraint binds rather
# than the ramp limiter.
UPPER_BOUND_SAFE_P = {
    "weak": [208.535, 310.823, 306.053, 292.546],
    "strong": [276.152, 319.621, 317.592, 311.657],
}


def _project_full_export(variant: str):
    cfg = ExperimentConfig.high_pv_overvoltage(variant)
    rated = cfg.feeder.ev_station_kva
    feeder = build_feeder(cfg.feeder)
    scale_loads(feeder, cfg.scenario.load_scale)
    set_pv_power(feeder, np.array(cfg.feeder.pv_rated_kw))
    set_station_power(feeder, np.full(4, rated), np.zeros(4))
    solver = RadialPowerFlow(feeder)
    pf = solver.solve()
    sens = JacobianSensitivities(feeder).compute(pf)
    loading = compute_loading_sensitivities(feeder, solver)
    proj = SensitivityProjector(cfg, 4, 34)
    res = proj.project(
        np.full(4, rated), np.zeros(4), np.full(4, rated), np.zeros(4),
        sens, loading, skip_when_feasible=False,
    )
    return cfg, feeder, solver, pf, res


@pytest.mark.parametrize("variant", ["weak", "strong"])
def test_projection_curtails_v2g_against_the_upper_bound(variant):
    """The V2G-support demonstration the thesis claims but never ran (audit A3).

    A full +320 kW export request at every station is curtailed downward until
    the linearised Vmax re-enters the tightened upper bound -- the mirror image
    of the charging curtailment the thesis published *as* a V2G result.
    """
    cfg, feeder, solver, pf, res = _project_full_export(variant)
    rated = cfg.feeder.ev_station_kva

    tightened = cfg.safety.voltage_upper_pu - cfg.safety.projection_margin_pu
    assert res.ok
    # Both feeders exceed the bound the projector enforces, so both get curtailed;
    # only the weak one actually breaches the hard 1.05 pu limit.
    assert pf.v_pu.max() > tightened
    assert (pf.v_pu.max() > cfg.safety.voltage_upper_pu) == (variant == "weak")
    assert res.p_kw == pytest.approx(UPPER_BOUND_SAFE_P[variant], abs=1e-2)
    assert np.all(res.p_kw > 0.0), "still an injection, not a reversal into charging"
    assert np.all(res.p_kw < rated), "and genuinely curtailed"

    set_station_power(feeder, res.p_kw, res.q_kvar)
    assert solver.solve().v_pu.max() <= cfg.safety.voltage_upper_pu


def test_upper_bound_curtailment_also_absorbs_reactive_power():
    """P and Q are coordinated -- the charging-only case never showed this."""
    _, _, _, _, res = _project_full_export("weak")
    assert res.q_kvar.min() == pytest.approx(-95.385, abs=1e-2)
    assert np.all(res.q_kvar <= 0.0), "absorbing vars is what lowers the voltage"


def test_upper_bound_grid_awareness_gap_exceeds_the_published_lower_bound_one():
    """The weak feeder needs 67.6 kW more curtailment than the strong one.

    Published Table 5.3's lower-bound gap is 25.865 kW; this case separates the
    two feeders far more sharply, and on the mechanism the paper is about.
    """
    safe = {v: _project_full_export(v)[4].p_kw for v in ("weak", "strong")}
    gap = float(np.max(np.abs(safe["weak"] - safe["strong"])))
    assert gap == pytest.approx(67.617, abs=1e-2)
    assert gap > 25.865


def test_both_bounds_bind_on_the_same_feeder():
    """The high-PV case exercises the projection in both directions.

    Full injection is curtailed downward by the 1.04 pu upper bound; full
    charging at the same 320 kVA rating is curtailed upward by the 0.96 pu lower
    bound. The thesis only ever demonstrated the second and described it as the
    first.
    """
    cfg, feeder, solver, pf = _high_pv_state(0.0)
    sens = JacobianSensitivities(feeder).compute(pf)
    loading = compute_loading_sensitivities(feeder, solver)
    rated = cfg.feeder.ev_station_kva

    def project(raw_p):
        proj = SensitivityProjector(cfg, 4, 34)
        return proj.project(
            raw_p, np.zeros(4), np.zeros(4), np.zeros(4), sens, loading,
            skip_when_feasible=False,
        )

    inject = project(np.full(4, rated))
    charge = project(np.full(4, -rated))

    assert inject.ok and charge.ok
    assert np.all(inject.p_kw < rated)      # curtailed by the upper bound
    assert np.all(charge.p_kw > -rated)     # curtailed by the lower bound
    assert np.all(inject.p_kw > 0) and np.all(charge.p_kw < 0)


# --- ProjectedAgent: the baseline the thesis never ran -----------------------


def test_projection_makes_a_greedy_charger_strictly_safe():
    """The headline of docs/03: the safety layer does the work, not the learner.

    Uncoordinated charging violates the band on ~6 % of steps. The same request
    passed through the projection violates on none of them, while keeping most
    of the service -- which is why "why RL at all?" is the question the paper
    has to answer rather than avoid.
    """
    from safesac.agents import UncoordinatedAgent
    from safesac.evaluate import evaluate
    from safesac.projected import ProjectedAgent

    cfg = ExperimentConfig.stage1("weak")

    env = ChargingFeederEnv(cfg)
    raw = evaluate(UncoordinatedAgent(env), env, cfg, n_episodes=3,
                   run_label="stage1_eval")["aggregate"]

    env = ChargingFeederEnv(cfg)
    proj = evaluate(ProjectedAgent(UncoordinatedAgent(env), env, cfg), env, cfg,
                    n_episodes=3, run_label="stage1_eval")["aggregate"]

    assert raw["voltage_violation_step_rate_mean"] > 0.02
    assert proj["voltage_violation_step_rate_mean"] == 0.0
    # service is retained, not destroyed
    assert proj["frac_meeting_soc_target_mean"] > 0.5 * raw["frac_meeting_soc_target_mean"]


def test_the_base_point_carries_the_safety_not_the_jacobian():
    """The correction to my first transfer claim, pinned so it cannot recur.

    Freezing a `Sensitivities` object freezes two different things: the Jacobian
    dV/dP, dV/dQ, and the operating point it was linearised about. My first
    transfer experiment froze both and attributed the whole effect to the
    Jacobian. Splitting them shows the opposite:

      * a projection carrying a Jacobian understated 20x, but *measuring* its
        own voltages, still holds the band -- the base point tells it where it
        is, and the Jacobian only sets the step size;
      * a projection carrying the right Jacobian about a stale idle base point
        is exactly as unsafe as no projection at all.

    Hence the finding is about refresh cadence (audit B3), not about network
    transfer, and `frozen_mode` exists so the two cannot be conflated again.
    """
    from safesac.agents import UncoordinatedAgent
    from safesac.evaluate import evaluate
    from safesac.projected import ProjectedAgent

    cfg = ExperimentConfig.stiffness(6.0)   # weak enough that greedy violates

    env = ChargingFeederEnv(cfg)
    raw = evaluate(UncoordinatedAgent(env), env, cfg, n_episodes=3,
                   run_label="transfer_eval")["aggregate"]
    assert raw["voltage_violation_step_rate_mean"] > 0.02, "no safety problem to solve"

    # The model a fixed-model controller would ship with: idle feeder, t = 0.
    env = ChargingFeederEnv(cfg)
    probe = ProjectedAgent(UncoordinatedAgent(env), env, cfg)
    obs, _ = env.reset(seed=3)
    probe.reset_episode()
    probe.select_action(obs)
    idle_sens, idle_loading = probe.cache.sens, probe.cache.loading
    understated = replace(idle_sens, dv_dp=idle_sens.dv_dp * 0.05)

    def run(**kw):
        e = ChargingFeederEnv(cfg)
        return evaluate(ProjectedAgent(UncoordinatedAgent(e), e, cfg, **kw), e, cfg,
                        n_episodes=3, run_label="transfer_eval")["aggregate"]

    snapshot = run(frozen_sensitivities=idle_sens, frozen_loading=idle_loading,
                   frozen_mode="snapshot")
    jacobian = run(frozen_sensitivities=understated, frozen_loading=idle_loading,
                   frozen_mode="jacobian")

    # A stale base point removes the protection entirely.
    assert snapshot["voltage_violation_step_rate_mean"] == pytest.approx(
        raw["voltage_violation_step_rate_mean"], abs=1e-9
    )
    # A badly wrong Jacobian, with the base point measured, does not.
    assert jacobian["voltage_violation_step_rate_mean"] == 0.0
