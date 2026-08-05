"""Learned agents: checkpoint compatibility, and the facts the checkpoints prove.

The full Table 6.1 reproduction lives in `scripts/reproduce_table_6_1.py` -- it
takes about three minutes, too slow for CI. What is pinned here is everything
that can be established from the checkpoints directly plus a one-episode
projection trace.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from safesac.config import MASTER_SEED, ExperimentConfig, derive_seed, eval_episode_seed
from safesac.env import ChargingFeederEnv, StateNormalizer
from safesac.learned import AgentHParams, ReplayBuffer, SACLagAgent, SafeSACLagAgent

CKPT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "checkpoints"
EVAL_LABEL = "patch7_weak_eval"

pytestmark = pytest.mark.skipif(
    not (CKPT_DIR / "saclag_weak_v2_model.pt").exists(),
    reason="thesis checkpoints not present",
)

OBS_DIM, ACTION_DIM = 95, 8

# label -> (lambda, alpha, step_count) read out of the shipped .pt files
SHIPPED = {
    "saclag_weak_v2": (0.0, 0.8469766974449158, 27936),
    "saclag_strong_v2": (0.0, 19.401611328125, 32832),
    "safesac_weak_v3": (17.32471322874821, 0.6128024458885193, 24480),
    "safesac_strong_v3": (17.847470766811742, 0.4180065691471100, 24768),
}


def _load(label: str, cfg: ExperimentConfig, hp: AgentHParams | None = None):
    probe = ChargingFeederEnv(cfg)
    norm = StateNormalizer(dim=probe.obs_dim)
    norm.load_state_dict(json.loads((CKPT_DIR / f"{label}_normalizer.json").read_text()))
    norm.freeze()
    env = ChargingFeederEnv(cfg, normalizer=norm, update_normalizer=False)
    env.reset(seed=derive_seed(MASTER_SEED, "init_for_load", label))
    if label.startswith("safesac"):
        agent = SafeSACLagAgent(env.obs_dim, env.action_dim, env, cfg=cfg, hp=hp, device="cpu")
    else:
        agent = SACLagAgent(env.obs_dim, env.action_dim, hp=hp, device="cpu")
    agent.load(CKPT_DIR / f"{label}_model.pt")
    agent.eval_mode()
    return agent, env


@pytest.mark.parametrize("label", sorted(SHIPPED))
def test_checkpoint_loads_with_expected_geometry(label):
    cfg = ExperimentConfig.thesis_final("weak")
    env = ChargingFeederEnv(cfg)
    assert (env.obs_dim, env.action_dim) == (OBS_DIM, ACTION_DIM)
    agent = SACLagAgent(OBS_DIM, ACTION_DIM, device="cpu")
    agent.load(CKPT_DIR / f"{label}_model.pt")
    assert agent.actor.trunk[0].weight.shape == (256, OBS_DIM)
    assert agent.actor.mean_head.weight.shape == (ACTION_DIM, 256)


def test_the_sac_lag_baseline_never_engaged_its_constraint():
    """Audit A1/A2, straight off disk.

    Both SAC-Lag checkpoints carry lambda = 0.0 exactly while both SafeSAC ones
    carry lambda ~ 17. The published headline is therefore not
    "projection helps a constrained agent" -- it is a constrained agent with a
    projection against an effectively unconstrained SAC.
    """
    for label in ("saclag_weak_v2", "saclag_strong_v2"):
        agent = SACLagAgent(OBS_DIM, ACTION_DIM, device="cpu")
        agent.load(CKPT_DIR / f"{label}_model.pt")
        assert agent.lambda_lagrange == 0.0

    for label in ("safesac_weak_v3", "safesac_strong_v3"):
        agent = SACLagAgent(OBS_DIM, ACTION_DIM, device="cpu")
        agent.load(CKPT_DIR / f"{label}_model.pt")
        assert agent.lambda_lagrange > 17.0


def test_entropy_temperature_diverged_on_the_strong_baseline():
    """Audit B5: the cross-deployment 'collapse' baseline trained at alpha = 19.4.

    The alpha ceiling of 1.0 arrived with Patch 6/7, after this checkpoint was
    written, so its policy is close to uniform noise. Every other run sits below 1.
    """
    alphas = {}
    for label in SHIPPED:
        agent = SACLagAgent(OBS_DIM, ACTION_DIM, device="cpu")
        agent.load(CKPT_DIR / f"{label}_model.pt")
        alphas[label] = agent.alpha
    assert alphas["saclag_strong_v2"] > 19.0
    assert all(a < 1.0 for k, a in alphas.items() if k != "saclag_strong_v2")


def test_training_budgets_were_unequal():
    """Audit A6. Episode counts differ by up to 34 % across the compared runs."""
    steps_per_episode = 288
    episodes = {
        label: SHIPPED[label][2] // steps_per_episode for label in SHIPPED
    }
    assert episodes == {
        "saclag_weak_v2": 97,
        "saclag_strong_v2": 114,
        "safesac_weak_v3": 85,
        "safesac_strong_v3": 86,
    }
    # The in-distribution comparison the thesis headlines.
    assert episodes["saclag_weak_v2"] - episodes["safesac_weak_v3"] == 12


@pytest.mark.parametrize("label", sorted(SHIPPED))
def test_scalars_match_the_shipped_values(label):
    lam, alpha, step_count = SHIPPED[label]
    agent = SACLagAgent(OBS_DIM, ACTION_DIM, device="cpu")
    agent.load(CKPT_DIR / f"{label}_model.pt")
    assert agent.lambda_lagrange == pytest.approx(lam)
    assert agent.alpha == pytest.approx(alpha, rel=1e-6)
    assert agent.step_count == step_count


def test_save_load_roundtrip_is_exact(tmp_path):
    agent = SACLagAgent(OBS_DIM, ACTION_DIM, device="cpu", seed=3)
    obs = np.random.default_rng(0).normal(size=OBS_DIM).astype(np.float32)
    before = agent.select_action(obs, deterministic=True)

    path = tmp_path / "m.pt"
    agent.save(path)
    other = SACLagAgent(OBS_DIM, ACTION_DIM, device="cpu", seed=99)
    other.load(path)
    after = other.select_action(obs, deterministic=True)

    assert after == pytest.approx(before, abs=0.0)
    assert other.lambda_lagrange == agent.lambda_lagrange


def test_deterministic_action_is_repeatable():
    agent, _ = _load("saclag_weak_v2", ExperimentConfig.thesis_final("weak"))
    obs = np.random.default_rng(1).normal(size=OBS_DIM).astype(np.float32)
    a1 = agent.select_action(obs, deterministic=True)
    a2 = agent.select_action(obs, deterministic=True)
    assert a1 == pytest.approx(a2, abs=0.0)
    assert np.all(np.abs(a1) <= 1.0)


def test_replay_buffer_keeps_raw_and_executed_apart():
    buf = ReplayBuffer(4, 2, capacity=8, seed=0)
    buf.add([1, 2, 3, 4], [0.5, 0.5], [0.1, 0.1], 1.0, 0.0, [4, 3, 2, 1], 0.0)
    assert len(buf) == 1
    b = buf.sample(3)
    assert b["action_raw"] == pytest.approx(np.full((3, 2), 0.5))
    assert b["action_exec"] == pytest.approx(np.full((3, 2), 0.1))


def test_replay_buffer_sampling_is_seed_reproducible():
    def draw(seed):
        buf = ReplayBuffer(2, 1, capacity=64, seed=seed)
        for i in range(64):
            buf.add([i, i], [i], [i], i, 0.0, [i, i], 0.0)
        return buf.sample(16)["reward"]

    assert draw(7) == pytest.approx(draw(7))
    assert not np.array_equal(draw(7), draw(8))


# --- audit item A5, measured on the published operating point ---------------


def test_safety_layer_is_infeasible_on_an_eighth_of_steps():
    """The projection cannot meet its own tightened band near the evening peak.

    At load 0.50 the margin puts the effective lower bound at 0.960 pu while the
    idle feeder sits at 0.9441, and four 80 kVA stations cannot close that. The
    program returns `infeasible`, the layer emits an all-zero command, and after
    three consecutive failures it latches the station off. None of this was
    logged in the thesis, so those steps are indistinguishable from a policy
    that chose to idle.
    """
    cfg = ExperimentConfig.thesis_final("weak")
    agent, env = _load("safesac_weak_v3", cfg)

    obs, info = env.reset(seed=eval_episode_seed(MASTER_SEED, 0, EVAL_LABEL))
    agent.reset_episode()
    for _ in range(env.scenario.n_steps):
        action = agent.select_action(obs, info=info, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break

    s = agent.stats
    assert s.n_calls == 288
    assert s.infeasible_rate == pytest.approx(0.125, abs=0.005)
    assert set(s.statuses) == {"infeasible"}
    assert s.n_frozen_steps == 30
    # Refresh cadence: 288 steps / 12 = 24 refreshes in an episode.
    assert agent.cache.n_refreshes == 24


def test_clean_operating_point_leaves_the_layer_feasible():
    """Stage 1's operating point removes the failure entirely."""
    cfg = ExperimentConfig.clean_operating_point("weak")
    agent, env = _load("safesac_weak_v3", cfg)

    obs, info = env.reset(seed=eval_episode_seed(MASTER_SEED, 0, EVAL_LABEL))
    agent.reset_episode()
    for _ in range(env.scenario.n_steps):
        action = agent.select_action(obs, info=info, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break

    assert agent.stats.n_infeasible == 0
    assert agent.stats.n_frozen_steps == 0


# --- audit item A2: why the Lagrange multiplier could never leave zero -------


def _rollout_tensors(label: str, cfg: ExperimentConfig, n_steps: int = 288):
    agent, env = _load(label, cfg)
    obs, info = env.reset(seed=eval_episode_seed(MASTER_SEED, 0, EVAL_LABEL))
    agent.reset_episode()
    observations, executed, costs = [], [], []
    for _ in range(n_steps):
        action = agent.select_action(obs, info=info, deterministic=True)
        observations.append(obs)
        executed.append(action)
        obs, _, terminated, truncated, info = env.step(action)
        costs.append(info.constraint_cost)
        if terminated or truncated:
            break
    return (
        agent,
        torch.tensor(np.array(observations), dtype=torch.float32),
        torch.tensor(np.array(executed), dtype=torch.float32),
        np.array(costs),
    )


def test_the_baseline_cost_critic_is_negative_on_a_nonnegative_target():
    """`saclag_weak_v2` cannot ever raise lambda, and this is why.

    The constraint cost is a sum of non-negative band excursions, so Q_C is
    regressed on a non-negative target and its true value is positive -- the
    realised episode cost is 0.26. The fitted critic nonetheless returns a mean
    of about -0.74. Since the multiplier update is
    ``lambda <- max(0, lambda + lr * (Q_C - 0.01))`` and Q_C sits below the
    threshold, lambda is pinned at its floor forever. Nothing then pushes the
    cost down, so nothing corrects the critic: the failure sustains itself.
    """
    cfg = ExperimentConfig.thesis_final("weak")
    agent, obs, executed, costs = _rollout_tensors("saclag_weak_v2", cfg)

    assert costs.min() >= 0.0
    assert costs.sum() > 0.2          # the true cost is positive

    with torch.no_grad():
        qc = agent.cost_critic(obs, executed)
    assert qc.mean().item() < 0.0     # ...yet the critic is negative
    assert (qc < agent.hp.constraint_threshold).float().mean().item() > 0.5

    with torch.no_grad():
        sampled, _, _ = agent.actor.sample(obs)
        cv = agent.cost_critic(obs, sampled).mean().item() - agent.hp.constraint_threshold
    assert cv < 0.0
    assert max(0.0, agent.lambda_lagrange + agent.hp.lr_lambda * cv) == 0.0


def test_the_proposed_cost_critic_is_positive_so_its_multiplier_climbs():
    """Same code, opposite sign -- which is the whole difference in lambda."""
    cfg = ExperimentConfig.thesis_final("weak")
    agent, obs, executed, costs = _rollout_tensors("safesac_weak_v3", cfg)

    with torch.no_grad():
        qc = agent.cost_critic(obs, executed)
    assert qc.min().item() > 0.0
    assert qc.mean().item() > agent.hp.constraint_threshold
    assert agent.lambda_lagrange > 17.0

    # And the realised cost is *higher* than the baseline's, so the multiplier
    # gap is not a difference in actual constraint satisfaction.
    assert costs.sum() > 0.2609


def test_the_raw_versus_executed_gap_is_not_what_drove_the_multiplier():
    """Rules out the other candidate explanation.

    The critics are trained on executed actions while the actor loss queries
    them at raw ones. That mismatch is real, but at the published operating
    point it moves Q_C by ~1 %, far too little to explain a 0-vs-17 difference.
    """
    cfg = ExperimentConfig.thesis_final("weak")
    agent, env = _load("safesac_weak_v3", cfg)

    obs_t, raw_t, exec_t = [], [], []
    obs, info = env.reset(seed=eval_episode_seed(MASTER_SEED, 0, EVAL_LABEL))
    agent.reset_episode()
    for _ in range(env.scenario.n_steps):
        action = agent.select_action(obs, info=info, deterministic=True)
        obs_t.append(obs)
        raw_t.append(agent._last_raw_action)
        exec_t.append(action)
        obs, _, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break

    to_t = lambda x: torch.tensor(np.array(x), dtype=torch.float32)  # noqa: E731
    with torch.no_grad():
        qc_raw = agent.cost_critic(to_t(obs_t), to_t(raw_t)).mean().item()
        qc_exec = agent.cost_critic(to_t(obs_t), to_t(exec_t)).mean().item()

    # The projection genuinely changes the action...
    assert np.abs(np.array(raw_t) - np.array(exec_t)).max() > 0.1
    # ...but barely moves the cost critic, so it cannot explain lambda = 0 vs 17.
    assert abs(qc_raw - qc_exec) / abs(qc_exec) < 0.05


def test_clamping_the_cost_critic_keeps_the_target_nonnegative():
    """The Stage 1 fix: a non-negative target cannot produce a negative bootstrap."""
    hp = AgentHParams(clamp_cost_critic=True, batch_size=8, buffer_size=64)
    agent = SACLagAgent(OBS_DIM, ACTION_DIM, hp=hp, device="cpu", seed=0)

    # Force the cost critic strongly negative, then check the clamp holds.
    with torch.no_grad():
        agent.target_cost_critic.net[-1].bias.fill_(-5.0)
        agent.cost_critic.net[-1].bias.fill_(-5.0)

    rng = np.random.default_rng(0)
    for _ in range(32):
        agent.add_to_replay(
            rng.normal(size=OBS_DIM).astype(np.float32),
            rng.uniform(-1, 1, ACTION_DIM).astype(np.float32),
            0.0, 0.0,
            rng.normal(size=OBS_DIM).astype(np.float32), 0.0,
        )
    metrics = agent.train_step()
    assert metrics is not None
    assert metrics["mean_qc"] >= 0.0


def test_alpha_ceiling_caps_the_entropy_temperature():
    """Audit B5. Applied to one arm only, this is an unfair-ablation lever."""
    hp = AgentHParams(alpha_ceiling=1.0, batch_size=8, buffer_size=64, init_alpha=0.9)
    agent = SACLagAgent(OBS_DIM, ACTION_DIM, hp=hp, device="cpu", seed=0)
    with torch.no_grad():
        agent.log_alpha.data.fill_(float(np.log(50.0)))   # as if it had diverged

    rng = np.random.default_rng(0)
    for _ in range(32):
        agent.add_to_replay(
            rng.normal(size=OBS_DIM).astype(np.float32),
            rng.uniform(-1, 1, ACTION_DIM).astype(np.float32),
            0.0, 0.0,
            rng.normal(size=OBS_DIM).astype(np.float32), 0.0,
        )
    agent.train_step()
    assert agent.alpha <= 1.0 + 1e-6

    # Without the ceiling it stays where it was pushed.
    free = SACLagAgent(
        OBS_DIM, ACTION_DIM, hp=AgentHParams(batch_size=8, buffer_size=64),
        device="cpu", seed=0,
    )
    with torch.no_grad():
        free.log_alpha.data.fill_(float(np.log(50.0)))
    free.replay = agent.replay
    free.train_step()
    assert free.alpha > 10.0


def test_sensitivity_refresh_cadence_is_configurable():
    """Audit B3: the thesis claims per-step refresh; the code refreshes hourly."""
    from safesac.projection import SensitivityCache

    cfg = ExperimentConfig.stage1("weak")
    assert cfg.safety.sensitivity_refresh_steps == 12   # 12 x 5 min = 1 hour

    env = ChargingFeederEnv(cfg)
    env.reset(seed=1)
    counts = {}
    for steps in (1, 12, 288):
        c = ExperimentConfig.stage1("weak")
        c = c.with_(safety=replace(c.safety, sensitivity_refresh_steps=steps))
        env2 = ChargingFeederEnv(c)
        env2.reset(seed=1)
        cache = SensitivityCache(c, env2.feeder, env2._pf_solver)
        for t in range(288):
            cache.maybe_refresh(t)
        counts[steps] = cache.n_refreshes

    assert counts == {1: 288, 12: 24, 288: 1}
