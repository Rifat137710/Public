"""Stage 0 acceptance: the port must reproduce the published results.

The two heuristic rows of thesis Table 6.1 exercise the entire chain -- seed
derivation, scenario sampling, fleet sampling, environment dynamics, reward,
and metrics -- without needing any trained weights. If these match, the port is
faithful.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from safesac.agents import DroopAgent, UncoordinatedAgent, ZeroAgent
from safesac.config import ExperimentConfig, derive_seed, eval_episode_seed, train_episode_seed
from safesac.env import ChargingFeederEnv, compute_reward
from safesac.evaluate import evaluate
from safesac.scenario import sample_fleet

EVAL_LABEL = "patch7_weak_eval"


@pytest.fixture(scope="module")
def cfg():
    return ExperimentConfig.thesis_final("weak")


# --- Seeds -----------------------------------------------------------------


def test_seed_derivation_matches_thesis():
    """Printed by Block 1: train_seed[0]=2276961450, eval_seed[0]=1358827877."""
    assert train_episode_seed(137710, 0) == 2276961450
    assert eval_episode_seed(137710, 0) == 1358827877
    assert derive_seed(137710, "train", "", 1_000_000) != derive_seed(137710, "eval", "eval", 9_000_000)


# --- Fleet -----------------------------------------------------------------


def test_patch1_fleet_feasibility(cfg):
    """Patch 1 acceptance test 1a: 273/273 requests deliverable within dwell."""
    fleet = sample_fleet(cfg, 4, episode_days=7, seed=derive_seed(cfg.master_seed, "patch1_feas"))
    total = feasible = 0
    for station in fleet:
        for ev in station:
            if ev.no_show:
                continue
            need = max(0.0, ev.soc_target - ev.soc_init) * ev.battery_capacity_kwh
            hours = ev.dwell_steps / cfg.time.steps_per_hour
            if cfg.fleet.max_charge_kw * cfg.fleet.charge_efficiency * hours >= need:
                feasible += 1
            total += 1
    assert (feasible, total) == (273, 273)


# --- Reward ----------------------------------------------------------------


def test_reward_decomposition_is_dominated_by_the_loss_term(cfg):
    """Audit item B1, pinned as a number.

    Random-policy day totals from Block 3: cost 119.27818876063301,
    user 9831.84910818133, deg 52.633517437948164, loss 578.6223659659252,
    reward -1120.3872178460924.
    """
    w = {"cost": 1.0, "user": 5.0, "deg": 0.5, "loss": 1.0}
    s = {"cost": 5.0, "user": 100.0, "deg": 1.0, "loss": 1.0}
    raw = {
        "cost": 119.27818876063301,
        "user": 9831.84910818133,
        "deg": 52.633517437948164,
        "loss": 578.6223659659252,
    }
    weighted = {k: w[k] * raw[k] / s[k] for k in raw}
    assert -sum(weighted.values()) == pytest.approx(-1120.3872178460924, abs=1e-9)

    total = sum(weighted.values())
    assert weighted["loss"] / total == pytest.approx(0.516, abs=0.002)
    assert weighted["cost"] / total == pytest.approx(0.021, abs=0.002)


def test_loss_term_can_be_disabled(cfg):
    p = np.array([-40.0, -40.0, 0.0, 0.0])
    with_loss, _ = compute_reward(cfg, p, 0.3, 0.15, 0.0)
    without, _ = compute_reward(replace(cfg, reward=replace(cfg.reward, include_loss_term=False)),
                                p, 0.3, 0.15, 0.0)
    assert without > with_loss


# --- The Stage 0 gate ------------------------------------------------------

PUBLISHED = {
    "uncoordinated": {
        "voltage_violation_step_rate": 0.1156,
        "frac_meeting_soc_target": 0.9955,
        "net_cost_usd": 230.7311,
        "vmin_pu": 0.9383,
        "total_reward": -205.5954,
        "v2g_utilization_rate": 0.0000,
        "throughput_kwh": 1128.8000,
    },
    "droop": {
        "voltage_violation_step_rate": 0.0521,
        "frac_meeting_soc_target": 0.3245,
        "net_cost_usd": 66.2656,
        "vmin_pu": 0.9474,
        "total_reward": -733.1634,
        "v2g_utilization_rate": 0.0969,
        "throughput_kwh": 1326.6790,
    },
}


@pytest.mark.parametrize(
    "name,agent_cls", [("uncoordinated", UncoordinatedAgent), ("droop", DroopAgent)]
)
def test_reproduces_published_table_6_1(cfg, name, agent_cls):
    env = ChargingFeederEnv(cfg, normalizer=None, update_normalizer=False)
    env.reset(seed=1)
    agg = evaluate(agent_cls(env), env, cfg, n_episodes=25, run_label=EVAL_LABEL)["aggregate"]
    for metric, expected in PUBLISHED[name].items():
        got = agg[f"{metric}_mean"]
        tol = max(5e-4, abs(expected) * 1e-4)  # published to 4 decimals
        assert got == pytest.approx(expected, abs=tol), f"{name}.{metric}"


# --- The reference the thesis never ran ------------------------------------


def test_idle_baseline_exceeds_the_published_learned_rates(cfg):
    """Audit A4, on the exact evaluation seeds used for Table 6.1.

    With the chargers switched off the feeder still violates 9.47 % of steps --
    more than the published SafeSAC (0.0912) and SAC-Lag (0.0904). Nearly all
    the reported safety signal is background load.
    """
    env = ChargingFeederEnv(cfg, normalizer=None, update_normalizer=False)
    env.reset(seed=1)
    agg = evaluate(ZeroAgent(env), env, cfg, n_episodes=25, run_label=EVAL_LABEL)["aggregate"]
    idle = agg["voltage_violation_step_rate_mean"]
    assert idle == pytest.approx(0.0947, abs=5e-4)
    assert idle > 0.0912  # SafeSAC as published
    assert idle > 0.0904  # SAC-Lag as published


def test_clean_operating_point_has_no_idle_violations():
    cfg = ExperimentConfig.clean_operating_point("weak")
    env = ChargingFeederEnv(cfg, normalizer=None, update_normalizer=False)
    env.reset(seed=1)
    agg = evaluate(ZeroAgent(env), env, cfg, n_episodes=10, run_label=EVAL_LABEL)["aggregate"]
    assert agg["voltage_violation_step_rate_mean"] == 0.0
    assert agg["voltage_violation_magnitude_pu_mean"] == 0.0


# --- Determinism -----------------------------------------------------------


def test_evaluation_is_deterministic(cfg):
    results = []
    for _ in range(2):
        env = ChargingFeederEnv(cfg, normalizer=None, update_normalizer=False)
        env.reset(seed=1)
        agg = evaluate(DroopAgent(env), env, cfg, n_episodes=3, run_label=EVAL_LABEL)["aggregate"]
        results.append(agg["total_reward_mean"])
    assert results[0] == results[1]
