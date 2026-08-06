"""Training loop: convergence detector, logging, and the fixed-budget switch."""

from __future__ import annotations

import csv

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv, StateNormalizer
from safesac.learned import AgentHParams, SACLagAgent, SafeSACLagAgent  # noqa: F401
from safesac.train import ConvergenceDetector, TrainConfig, train

SMALL = AgentHParams(batch_size=32, buffer_size=2000, warmup_random_steps=0)


def _env(cfg):
    return ChargingFeederEnv(cfg, normalizer=StateNormalizer(dim=95))


def test_convergence_detector_needs_two_full_windows():
    d = ConvergenceDetector(window=5, rel_tol=0.01, min_episodes=5)
    for _ in range(9):
        assert d.update(-100.0) is False  # only 9 samples, needs 2*5
    assert d.update(-100.0) is True
    assert d.converged_at == 10


def test_convergence_detector_ignores_a_moving_average():
    d = ConvergenceDetector(window=3, rel_tol=0.01, min_episodes=3)
    for i in range(12):
        fired = d.update(-1000.0 + 100.0 * i)
    assert fired is False


def test_training_runs_and_logs_the_multiplier(tmp_path):
    cfg = ExperimentConfig.clean_operating_point("weak")
    env = _env(cfg)
    agent = SACLagAgent(env.obs_dim, env.action_dim, hp=SMALL, device="cpu", seed=0)
    tc = TrainConfig(max_episodes=1, run_label="smoke", checkpoint_every=1, verbose=False)

    res = train(agent, env, cfg, tc, out_dir=tmp_path)

    assert res.n_episodes_completed == 1
    assert res.history[0].n_steps == 288
    assert (tmp_path / "smoke_model.pt").exists()
    assert (tmp_path / "smoke_normalizer.json").exists()

    rows = list(csv.DictReader((tmp_path / "smoke_episodes.csv").open()))
    assert len(rows) == 1
    assert {"lambda", "alpha", "mean_qc", "proj_infeasible_rate"} <= set(rows[0])
    assert agent.update_step > 0


def test_training_records_projection_outcomes(tmp_path):
    """The per-episode log carries what the thesis discarded."""
    cfg = ExperimentConfig.thesis_final("weak")
    env = _env(cfg)
    agent = SafeSACLagAgent(
        env.obs_dim, env.action_dim, env, cfg=cfg, hp=SMALL, device="cpu", seed=0
    )
    tc = TrainConfig(max_episodes=1, run_label="proj", checkpoint_every=99, verbose=False)

    res = train(agent, env, cfg, tc, out_dir=tmp_path)

    rec = res.history[0]
    assert rec.projection_infeasible_rate == pytest.approx(0.125, abs=0.02)
    assert agent.stats.n_calls == 288


def test_fixed_budget_ignores_the_convergence_break(tmp_path):
    """Audit A1/A6: early stopping is what gave the compared runs unequal budgets."""
    cfg = ExperimentConfig.clean_operating_point("weak")
    env = _env(cfg)
    agent = SACLagAgent(env.obs_dim, env.action_dim, hp=SMALL, device="cpu", seed=0)
    tc = TrainConfig(
        max_episodes=3,
        run_label="fixed",
        checkpoint_every=99,
        verbose=False,
        early_stopping=False,
        convergence_window=1,
        min_episodes_before_convergence=1,
        convergence_rel_tol=1e9,  # always "converged"
    )

    res = train(agent, env, cfg, tc, out_dir=None)

    assert res.converged is True
    assert res.converged_at == 2
    assert res.n_episodes_completed == 3  # ran the full budget anyway


def test_resume_picks_up_where_it_stopped(tmp_path):
    cfg = ExperimentConfig.clean_operating_point("weak")
    env = _env(cfg)
    agent = SACLagAgent(env.obs_dim, env.action_dim, hp=SMALL, device="cpu", seed=0)
    tc = TrainConfig(max_episodes=1, run_label="r", checkpoint_every=1, verbose=False)
    train(agent, env, cfg, tc, out_dir=tmp_path)

    agent2 = SACLagAgent(env.obs_dim, env.action_dim, hp=SMALL, device="cpu", seed=0)
    tc2 = TrainConfig(max_episodes=1, run_label="r", checkpoint_every=1, verbose=False)
    res2 = train(agent2, env, cfg, tc2, out_dir=tmp_path)

    assert res2.n_episodes_completed == 0  # already at the budget
    assert agent2.update_step == agent.update_step


def test_training_loop_drives_the_episodic_dual(tmp_path):
    """`train` must call the episodic dual update once per episode."""
    cfg = ExperimentConfig.stage1("weak")
    env = _env(cfg)
    hp = AgentHParams(
        batch_size=32, buffer_size=2000, warmup_random_steps=0,
        dual_update="realised", cost_limit_episode=0.0, lr_lambda_episode=1000.0,
    )
    agent = SACLagAgent(env.obs_dim, env.action_dim, hp=hp, device="cpu", seed=0)
    calls = []
    original = agent.update_dual_from_episode
    agent.update_dual_from_episode = lambda c: (calls.append(c), original(c))[1]

    tc = TrainConfig(max_episodes=2, run_label="dual", checkpoint_every=99, verbose=False)
    res = train(agent, env, cfg, tc, out_dir=None)

    assert len(calls) == 2
    assert calls == [h.realised_cost for h in res.history]
