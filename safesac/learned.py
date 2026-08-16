"""SAC-Lagrangian and SafeSAC (SAC-Lag + projection), ported from thesis11.ipynb §12.

The networks, the update rule, and the checkpoint format are byte-compatible with
the shipped `.pt` artifacts, so `SACLagAgent.load` reads them directly.

Two deliberate departures from the notebook, both marked `DEPARTURE:`:

* the replay buffer draws from an owned ``np.random.Generator`` instead of the
  global ``np.random`` state, so a training run is reproducible from its seed;
* projection outcomes are counted (`ProjectionStats`). The notebook discarded
  them, which is why audit item A5 -- the safety layer failing on ~1 step in 8
  at the published operating point -- went unnoticed.

Neither changes a forward pass, so evaluation of a loaded checkpoint is exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal

from .agents import BaseAgent
from .config import ExperimentConfig
from .env import N_BUS_CANONICAL, ChargingFeederEnv
from .projection import SensitivityCache, SensitivityProjector


# ---------------------------------------------------------------------------
# hyperparameters (thesis11.ipynb CONFIG["sac_lag_hparams"])
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentHParams:
    gamma: float = 0.99
    tau: float = 0.005
    lr_actor: float = 3e-4
    lr_critic: float = 3e-4
    lr_alpha: float = 3e-4
    lr_lambda: float = 1e-3
    hidden_dim: int = 256
    n_hidden_layers: int = 2
    batch_size: int = 256
    buffer_size: int = 200_000
    init_alpha: float = 0.2
    constraint_threshold: float = 0.01
    quad_penalty_max: float = 1.0
    quad_penalty_warmup_steps: int = 10_000
    warmup_random_steps: int = 1000
    target_entropy_factor: float = -1.0

    # -- audit switches; both defaults reproduce the thesis exactly ----------

    clamp_cost_critic: bool = False
    """Audit A2. The cost critic is regressed on a non-negative cost, so its
    output should be non-negative too; unclamped it can go negative and drive
    the Lagrange multiplier to the ``max(0, .)`` floor, which is where both
    shipped SAC-Lag checkpoints sit (lambda = 0.0 exactly). Measured on
    `saclag_weak_v2`: realised episode cost 0.2609, but Q_C averages -0.7434 and
    sits below the 0.01 threshold on 73 % of steps, so
    ``lambda <- max(0, lambda + lr * (Q_C - 0.01))`` can never leave zero."""

    dual_update: str = "cost_critic"
    """Where the Lagrange multiplier's ascent signal comes from.

    ``"cost_critic"`` is the thesis's scheme: lambda integrates
    ``Q_C(s, pi(s)) - constraint_threshold`` on every gradient step. Q_C is a
    bootstrapped, off-policy, extrapolating estimate, so any positive bias is
    integrated without bound -- 72 000 steps over a 250-episode run. Measured:
    on a projection arm whose realised cost is *identically zero*, Q_C still
    climbs to 10.3 and lambda to 270; on one seed Q_C reaches 152.8 and lambda
    1888. At that point the ``lambda * (Q_C - d)`` term dwarfs the reward and
    the optimal policy is to idle, which is what SoC met ~ 0.02 was.

    ``"realised"`` ascends on the *measured* episode cost instead, once per
    episode. It is unbiased and on-policy: where the projection removes every
    violation the signal is exactly zero and lambda correctly stays put.
    """

    cost_limit_episode: float = 0.01
    """Per-episode budget in pu-steps of band excursion, for ``dual_update="realised"``.
    Distinct from `constraint_threshold`, which is a bound on discounted cost-to-go."""

    lr_lambda_episode: float = 0.5
    """Episodic dual step. Sized so that a persistent 0.02 pu-step overshoot moves
    lambda to O(1) over ~100 episodes -- there are ~288x fewer updates than in the
    per-gradient-step scheme, so the per-step rate cannot carry over."""

    lambda_max: Optional[float] = None
    """Hard anti-windup cap. Belt-and-braces next to `dual_update`."""

    autotune_alpha: bool = True
    """Whether the entropy temperature is learned.

    SAC's auto-tuner chases a target entropy of ``-dim(A)``, which assumes the
    optimum is not on the action bounds. Here it is: the best policy charges at
    full rate, so actions sit near +-1. The tanh change-of-variables term
    ``-log(1 - tanh(z)^2)`` then inflates the log-density -- measured at +13.4
    on average, against a Gaussian part that is small -- so log pi exceeds the
    threshold on 46 % of states and the tuner reads a saturated policy as
    "insufficient entropy". It raises alpha, that pushes the policy off the
    bounds, performance drops, and the loop repeats.

    Every setting tried diverged or pinned: uncapped alpha reached 19.4 (thesis
    SAC-Lag) and 8.7 (after rescaling); capped at 1.0 it pins against the cap
    and the entropy term swamps the task. Fixing alpha removes the loop, at the
    cost of one hyperparameter chosen by sweep and reported.
    """

    alpha_ceiling: Optional[float] = None
    """Audit A1/B5. The thesis capped the entropy temperature at 1.0, but only
    from Patch 6 onward -- so `safesac_*_v3` trained under the cap and
    `saclag_strong_v2` did not, finishing at alpha = 19.4 with a near-uniform
    policy. That checkpoint is the "collapse" baseline in the cross-deployment
    claim. Any fair ablation must apply the same value to every arm."""

    projection_skip_when_feasible: bool = False
    """The feasibility pre-check the thesis wrote as Patch 4 and then commented
    out. Off by default so the published path is what runs."""

    stale_cache_across_episodes: bool = False
    """The base `SensitivityCache` refresh test is
    ``current_step - last_refresh >= refresh_steps``. `current_step` restarts at
    0 each episode while `last_refresh` does not, so on its own the test could
    never fire again after episode 1. The thesis caught this: a patch cell
    rewires `select_action` to clear the cache whenever `env.reset()` builds a
    new network object, which is what the published run used and what False
    reproduces. True is kept only to quantify what the unpatched code would
    have done -- it inflates SoC met by ~0.12 and net cost by ~$60."""

    reset_projector_each_episode: bool = True
    """The same patch also calls `on_sensitivity_refresh()`, clearing the
    projector's freeze latch at every episode boundary."""

    def replace(self, **kw) -> "AgentHParams":
        return replace(self, **kw)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


class ReplayBuffer:
    """Stores the raw (pre-projection) and executed (post-projection) actions.

    Keeping both is what lets SafeSAC learn off the action the grid actually
    saw while still crediting the policy's own output.
    """

    def __init__(self, obs_dim: int, action_dim: int, capacity: int, seed: int = 0):
        self.capacity = int(capacity)
        self.obs = np.zeros((self.capacity, obs_dim), dtype=np.float32)
        self.action_raw = np.zeros((self.capacity, action_dim), dtype=np.float32)
        self.action_exec = np.zeros((self.capacity, action_dim), dtype=np.float32)
        self.reward = np.zeros(self.capacity, dtype=np.float32)
        self.cost = np.zeros(self.capacity, dtype=np.float32)
        self.next_obs = np.zeros((self.capacity, obs_dim), dtype=np.float32)
        self.done = np.zeros(self.capacity, dtype=np.float32)
        self.size = 0
        self.ptr = 0
        # DEPARTURE: owned RNG. The notebook used the global np.random state.
        self.rng = np.random.default_rng(seed)

    def add(self, obs, action_raw, action_exec, reward, cost, next_obs, done) -> None:
        i = self.ptr
        self.obs[i] = obs
        self.action_raw[i] = action_raw
        self.action_exec[i] = action_exec
        self.reward[i] = reward
        self.cost[i] = cost
        self.next_obs[i] = next_obs
        self.done[i] = done
        self.ptr = (self.ptr + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int) -> Dict[str, np.ndarray]:
        idx = self.rng.integers(0, self.size, batch_size)
        return {
            "obs": self.obs[idx],
            "action_raw": self.action_raw[idx],
            "action_exec": self.action_exec[idx],
            "reward": self.reward[idx],
            "cost": self.cost[idx],
            "next_obs": self.next_obs[idx],
            "done": self.done[idx],
        }

    def __len__(self) -> int:
        return self.size


# ---------------------------------------------------------------------------
# networks
# ---------------------------------------------------------------------------


class GaussianActor(nn.Module):
    """Squashed-Gaussian policy. Layer names match the shipped checkpoints."""

    LOG_STD_MIN = -20.0
    LOG_STD_MAX = 2.0

    def __init__(self, obs_dim: int, action_dim: int, hidden_dim: int = 256, n_hidden: int = 2):
        super().__init__()
        layers = []
        in_dim = obs_dim
        for _ in range(n_hidden):
            layers.extend([nn.Linear(in_dim, hidden_dim), nn.ReLU()])
            in_dim = hidden_dim
        self.trunk = nn.Sequential(*layers)
        self.mean_head = nn.Linear(hidden_dim, action_dim)
        self.log_std_head = nn.Linear(hidden_dim, action_dim)

    def forward(self, obs):
        h = self.trunk(obs)
        mean = self.mean_head(h)
        log_std = torch.clamp(self.log_std_head(h), self.LOG_STD_MIN, self.LOG_STD_MAX)
        return mean, log_std

    def sample(self, obs):
        mean, log_std = self.forward(obs)
        std = log_std.exp()
        normal = Normal(mean, std)
        z = normal.rsample()
        action = torch.tanh(z)
        log_prob = (normal.log_prob(z) - torch.log(1.0 - action.pow(2) + 1e-6)).sum(-1)
        return action, log_prob, torch.tanh(mean)


class QCritic(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int, hidden_dim: int = 256, n_hidden: int = 2):
        super().__init__()
        layers = []
        in_dim = obs_dim + action_dim
        for _ in range(n_hidden):
            layers.extend([nn.Linear(in_dim, hidden_dim), nn.ReLU()])
            in_dim = hidden_dim
        layers.append(nn.Linear(hidden_dim, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, obs, action):
        return self.net(torch.cat([obs, action], dim=-1)).squeeze(-1)


# ---------------------------------------------------------------------------
# SAC-Lagrangian
# ---------------------------------------------------------------------------


class SACLagAgent(BaseAgent):
    """Soft actor-critic with an augmented-Lagrangian constraint on a cost critic."""

    name = "sac_lag"

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hp: Optional[AgentHParams] = None,
        device: Optional[str] = None,
        seed: int = 0,
    ):
        self.hp = hp or AgentHParams()
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        self.target_entropy = self.hp.target_entropy_factor * action_dim

        h, n = self.hp.hidden_dim, self.hp.n_hidden_layers
        mk_q = lambda: QCritic(obs_dim, action_dim, h, n).to(self.device)  # noqa: E731

        self.actor = GaussianActor(obs_dim, action_dim, h, n).to(self.device)
        self.critic1, self.critic2, self.cost_critic = mk_q(), mk_q(), mk_q()
        self.target_critic1, self.target_critic2, self.target_cost_critic = mk_q(), mk_q(), mk_q()
        self.target_critic1.load_state_dict(self.critic1.state_dict())
        self.target_critic2.load_state_dict(self.critic2.state_dict())
        self.target_cost_critic.load_state_dict(self.cost_critic.state_dict())

        self.log_alpha = torch.tensor(
            math.log(self.hp.init_alpha), device=self.device, requires_grad=True
        )
        self.lambda_lagrange = 0.0
        self.quad_penalty = 0.0

        adam = torch.optim.Adam
        self.actor_optim = adam(self.actor.parameters(), lr=self.hp.lr_actor)
        self.critic1_optim = adam(self.critic1.parameters(), lr=self.hp.lr_critic)
        self.critic2_optim = adam(self.critic2.parameters(), lr=self.hp.lr_critic)
        self.cost_critic_optim = adam(self.cost_critic.parameters(), lr=self.hp.lr_critic)
        self.alpha_optim = adam([self.log_alpha], lr=self.hp.lr_alpha)

        self.replay = ReplayBuffer(obs_dim, action_dim, self.hp.buffer_size, seed=seed)
        self.explore_rng = np.random.default_rng(seed + 1)
        self.update_step = 0
        self.step_count = 0

    @property
    def alpha(self) -> float:
        return float(self.log_alpha.exp().item())

    def reset_episode(self) -> None:
        pass

    # -- acting ------------------------------------------------------------

    def select_action(self, obs, info=None, deterministic: bool = False) -> np.ndarray:
        # FAITHFUL: step_count advances on every call, evaluation included.
        self.step_count += 1
        if self.step_count < self.hp.warmup_random_steps and not deterministic:
            return self.explore_rng.uniform(-1.0, 1.0, self.action_dim).astype(np.float32)
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
            if deterministic:
                mean, _ = self.actor(o)
                action = torch.tanh(mean)
            else:
                action, _, _ = self.actor.sample(o)
        return action.squeeze(0).cpu().numpy().astype(np.float32)

    def add_to_replay(
        self, obs, action_raw, reward, cost, next_obs, done, action_executed=None
    ) -> None:
        if action_executed is None:
            action_executed = action_raw
        self.replay.add(obs, action_raw, action_executed, reward, cost, next_obs, done)

    # -- learning ----------------------------------------------------------

    def _clip_lambda(self, value: float) -> float:
        value = max(0.0, value)
        if self.hp.lambda_max is not None:
            value = min(value, self.hp.lambda_max)
        return value

    def update_dual_from_episode(self, realised_cost: float) -> float:
        """Ascend the multiplier on the measured episode cost.

        No-op unless `dual_update == "realised"`. Called once per episode by
        `safesac.train.train`, which is the only place the realised cost is known.
        """
        if self.hp.dual_update != "realised":
            return self.lambda_lagrange
        gap = float(realised_cost) - self.hp.cost_limit_episode
        self.lambda_lagrange = self._clip_lambda(
            self.lambda_lagrange + self.hp.lr_lambda_episode * gap
        )
        return self.lambda_lagrange

    def _polyak(self, target: nn.Module, source: nn.Module) -> None:
        with torch.no_grad():
            for tp, sp in zip(target.parameters(), source.parameters()):
                tp.data.mul_(1.0 - self.hp.tau).add_(self.hp.tau * sp.data)

    def train_step(self) -> Optional[Dict[str, float]]:
        if len(self.replay) < self.hp.batch_size:
            return None
        b = self.replay.sample(self.hp.batch_size)
        t = lambda k: torch.as_tensor(b[k], device=self.device)  # noqa: E731
        obs, action_e = t("obs"), t("action_exec")
        reward, cost = t("reward"), t("cost")
        next_obs, done = t("next_obs"), t("done")

        gamma = self.hp.gamma
        with torch.no_grad():
            next_action, next_log_prob, _ = self.actor.sample(next_obs)
            target_q = (
                torch.min(
                    self.target_critic1(next_obs, next_action),
                    self.target_critic2(next_obs, next_action),
                )
                - self.alpha * next_log_prob
            )
            y = reward + gamma * (1.0 - done) * target_q
            next_qc = self.target_cost_critic(next_obs, next_action)
            if self.hp.clamp_cost_critic:
                next_qc = torch.clamp(next_qc, min=0.0)
            y_c = cost + gamma * (1.0 - done) * next_qc

        loss_q1 = F.mse_loss(self.critic1(obs, action_e), y)
        loss_q2 = F.mse_loss(self.critic2(obs, action_e), y)
        loss_qc = F.mse_loss(self.cost_critic(obs, action_e), y_c)
        for optim, loss in (
            (self.critic1_optim, loss_q1),
            (self.critic2_optim, loss_q2),
            (self.cost_critic_optim, loss_qc),
        ):
            optim.zero_grad()
            loss.backward()
            optim.step()

        new_action, log_prob, _ = self.actor.sample(obs)
        q_new = torch.min(self.critic1(obs, new_action), self.critic2(obs, new_action))
        qc_new = self.cost_critic(obs, new_action)
        if self.hp.clamp_cost_critic:
            qc_new = torch.clamp(qc_new, min=0.0)

        cost_excess = qc_new - self.hp.constraint_threshold
        lag_term = self.lambda_lagrange * cost_excess.mean()
        quad_term = (self.quad_penalty / 2.0) * torch.clamp(cost_excess, min=0).pow(2).mean()
        actor_loss = (self.alpha * log_prob - q_new).mean() + lag_term + quad_term
        self.actor_optim.zero_grad()
        actor_loss.backward()
        self.actor_optim.step()

        if self.hp.autotune_alpha:
            alpha_loss = -(self.log_alpha * (log_prob.detach() + self.target_entropy)).mean()
            self.alpha_optim.zero_grad()
            alpha_loss.backward()
            self.alpha_optim.step()
            if self.hp.alpha_ceiling is not None:
                with torch.no_grad():
                    self.log_alpha.data.clamp_(max=math.log(self.hp.alpha_ceiling))
        else:
            alpha_loss = torch.zeros((), device=self.device)

        with torch.no_grad():
            cv = float(qc_new.mean().item()) - self.hp.constraint_threshold
        if self.hp.dual_update == "cost_critic":
            self.lambda_lagrange = self._clip_lambda(
                self.lambda_lagrange + self.hp.lr_lambda * cv
            )
        self.quad_penalty = min(
            self.hp.quad_penalty_max,
            (self.update_step / max(1, self.hp.quad_penalty_warmup_steps))
            * self.hp.quad_penalty_max,
        )

        self._polyak(self.target_critic1, self.critic1)
        self._polyak(self.target_critic2, self.critic2)
        self._polyak(self.target_cost_critic, self.cost_critic)
        self.update_step += 1

        return {
            "loss_q1": float(loss_q1.item()),
            "loss_q2": float(loss_q2.item()),
            "loss_qc": float(loss_qc.item()),
            "actor_loss": float(actor_loss.item()),
            "alpha_loss": float(alpha_loss.item()),
            "alpha": self.alpha,
            "lambda": float(self.lambda_lagrange),
            "quad_penalty": float(self.quad_penalty),
            "mean_qc": float(qc_new.mean().item()),
            "constraint_violation": cv,
        }

    # -- checkpoints -------------------------------------------------------

    def state_dict(self) -> dict:
        return {
            "actor": self.actor.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "cost_critic": self.cost_critic.state_dict(),
            "target_critic1": self.target_critic1.state_dict(),
            "target_critic2": self.target_critic2.state_dict(),
            "target_cost_critic": self.target_cost_critic.state_dict(),
            "log_alpha": self.log_alpha.detach().cpu().numpy(),
            "lambda": self.lambda_lagrange,
            "quad_penalty": self.quad_penalty,
            "update_step": self.update_step,
            "step_count": self.step_count,
        }

    def save(self, path) -> None:
        torch.save(self.state_dict(), path)

    def load(self, path) -> "SACLagAgent":
        ck = torch.load(path, map_location=self.device, weights_only=False)
        self.actor.load_state_dict(ck["actor"])
        self.critic1.load_state_dict(ck["critic1"])
        self.critic2.load_state_dict(ck["critic2"])
        self.cost_critic.load_state_dict(ck["cost_critic"])
        self.target_critic1.load_state_dict(ck["target_critic1"])
        self.target_critic2.load_state_dict(ck["target_critic2"])
        self.target_cost_critic.load_state_dict(ck["target_cost_critic"])
        self.log_alpha.data = torch.as_tensor(
            np.asarray(ck["log_alpha"]), dtype=torch.float32, device=self.device
        )
        self.lambda_lagrange = float(ck["lambda"])
        self.quad_penalty = float(ck["quad_penalty"])
        self.update_step = int(ck["update_step"])
        self.step_count = int(ck["step_count"])
        return self

    def eval_mode(self) -> "SACLagAgent":
        """Freeze the warmup counter so a loaded policy is used from step 0."""
        self.actor.eval()
        self.step_count = max(self.step_count, self.hp.warmup_random_steps)
        return self


# ---------------------------------------------------------------------------
# SafeSAC
# ---------------------------------------------------------------------------


@dataclass
class ProjectionStats:
    """What the safety layer actually did. Audit item A5.

    The thesis logged none of this, so an infeasible program returning an
    all-zero command was indistinguishable from a policy choosing to idle.
    """

    n_calls: int = 0
    n_solved: int = 0
    n_skipped_feasible: int = 0
    n_infeasible: int = 0
    n_frozen_steps: int = 0
    n_unavailable: int = 0
    n_inaccurate: int = 0        # solver said "inaccurate" but the point passed
    max_residual: float = 0.0    # worst accepted constraint violation seen
    statuses: Dict[str, int] = field(default_factory=dict)
    solver_statuses: Dict[str, int] = field(default_factory=dict)

    @property
    def infeasible_rate(self) -> float:
        return self.n_infeasible / self.n_calls if self.n_calls else 0.0

    def record(self, res) -> None:
        self.n_calls += 1
        if res.solved:
            self.n_solved += 1
            ss = getattr(res, "solver_status", "") or "unknown"
            self.solver_statuses[ss] = self.solver_statuses.get(ss, 0) + 1
            if res.ok:
                # Accepted despite the solver's own hedge -- worth counting, so
                # "how often did we trust a hedged solve?" has an answer.
                if "inaccurate" in ss:
                    self.n_inaccurate += 1
                self.max_residual = max(self.max_residual,
                                        float(getattr(res, "residual", 0.0)))
        else:
            self.n_skipped_feasible += 1
        if not res.ok:
            self.n_infeasible += 1
            self.statuses[res.status] = self.statuses.get(res.status, 0) + 1
        if res.frozen.any():
            self.n_frozen_steps += 1

    def summary(self) -> Dict[str, float]:
        return {
            "projection_calls": self.n_calls,
            "projection_infeasible_rate": self.infeasible_rate,
            "projection_frozen_step_rate": (
                self.n_frozen_steps / self.n_calls if self.n_calls else 0.0
            ),
            "projection_skip_rate": (
                self.n_skipped_feasible / self.n_calls if self.n_calls else 0.0
            ),
            "projection_unavailable": self.n_unavailable,
            "projection_inaccurate_rate": (
                self.n_inaccurate / self.n_solved if self.n_solved else 0.0
            ),
            "projection_max_residual": self.max_residual,
        }


class SafeSACLagAgent(SACLagAgent):
    """SAC-Lag whose action is projected onto the linearised feasible set.

    On an infeasible program the projector returns zeros, which the env then
    executes as "all stations idle". That fallback is the method's real safety
    behaviour whenever the band cannot be met, and `stats` measures how often
    it fires.
    """

    name = "safe_sac_lag"

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        env: ChargingFeederEnv,
        cfg: Optional[ExperimentConfig] = None,
        hp: Optional[AgentHParams] = None,
        device: Optional[str] = None,
        seed: int = 0,
    ):
        super().__init__(obs_dim, action_dim, hp=hp, device=device, seed=seed)
        self.env = env
        self.cfg = cfg or env.cfg
        self.projector = SensitivityProjector(self.cfg, env.n_stations, env.n_bus_canonical)
        self.cache: Optional[SensitivityCache] = None
        self.stats = ProjectionStats()
        self._last_raw_action: Optional[np.ndarray] = None
        self._last_safe_action: Optional[np.ndarray] = None

    def reset_episode(self) -> None:
        """Rebind to the feeder the env just built, and clear the freeze latch.

        Whether the refresh clock survives the episode boundary is the
        `stale_cache_across_episodes` switch; see `AgentHParams`.
        """
        if self.cache is None:
            self.cache = SensitivityCache(self.cfg, self.env.feeder, self.env._pf_solver)
        else:
            self.cache.rebind(self.env.feeder, self.env._pf_solver)
            if not self.hp.stale_cache_across_episodes:
                self.cache.invalidate()
        if self.hp.reset_projector_each_episode:
            self.projector.on_refresh()

    def select_action(self, obs, info=None, deterministic: bool = False) -> np.ndarray:
        raw_action = super().select_action(obs, info=info, deterministic=deterministic)
        n = self.env.n_stations
        rated = self.cfg.feeder.ev_station_kva

        if self.cache is None or self.env._last_pf is None:
            self.stats.n_unavailable += 1
            self._last_raw_action = raw_action
            self._last_safe_action = raw_action.copy()
            return raw_action

        # pf=None: re-solve at the feeder's current state, as the thesis did.
        if self.cache.maybe_refresh(self.env.current_step):
            self.projector.on_refresh()

        res = self.projector.project(
            raw_action[:n] * rated,
            raw_action[n:] * rated,
            self.env._prev_p_kw,
            self.env._prev_q_kvar,
            self.cache.sens,
            self.cache.loading,
            skip_when_feasible=self.hp.projection_skip_when_feasible,
        )
        self.stats.record(res)

        if res.all_frozen:
            safe_p, safe_q = np.zeros(n), np.zeros(n)
        else:
            safe_p, safe_q = res.p_kw, res.q_kvar

        safe_action = np.clip(
            np.concatenate([safe_p / rated, safe_q / rated]), -1.0, 1.0
        ).astype(np.float32)
        self._last_raw_action = raw_action
        self._last_safe_action = safe_action
        return safe_action

    def add_to_replay(
        self, obs, action_raw, reward, cost, next_obs, done, action_executed=None
    ) -> None:
        if action_executed is None:
            action_executed = self._last_safe_action
        if action_executed is None:
            action_executed = action_raw
        raw = self._last_raw_action if self._last_raw_action is not None else action_raw
        self.replay.add(obs, raw, action_executed, reward, cost, next_obs, done)


__all__ = [
    "AgentHParams",
    "ReplayBuffer",
    "GaussianActor",
    "QCritic",
    "SACLagAgent",
    "SafeSACLagAgent",
    "ProjectionStats",
]
