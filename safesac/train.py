"""Training loop, ported from thesis11.ipynb §14.1/14.4.

Adds what a fair ablation needs and the notebook lacked: a fixed-budget mode
(audit A1/A6 -- the shipped runs stopped at different episode counts, so the
published comparison is between policies given unequal training), and a per
episode log that records the Lagrange multiplier and the projection outcome
rates rather than throwing them away.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from .config import ExperimentConfig, train_episode_seed


class ConvergenceDetector:
    """Two-window moving average on episode return.

    Kept because it is what produced the shipped checkpoints, but note that
    stopping on it gives each method a *different* number of gradient steps.
    `TrainConfig.early_stopping = False` is the fair-comparison setting.
    """

    def __init__(self, window: int = 20, rel_tol: float = 0.01, min_episodes: int = 50):
        self.window = int(window)
        self.rel_tol = float(rel_tol)
        self.min_episodes = int(min_episodes)
        self.returns: List[float] = []
        self.converged_at: Optional[int] = None

    def update(self, episode_return: float) -> bool:
        self.returns.append(float(episode_return))
        n = len(self.returns)
        if n < max(2 * self.window, self.min_episodes):
            return False
        w_prev = float(np.mean(self.returns[-2 * self.window : -self.window]))
        w_curr = float(np.mean(self.returns[-self.window :]))
        if abs(w_curr - w_prev) / max(abs(w_prev), 1.0) < self.rel_tol:
            self.converged_at = n
            return True
        return False


@dataclass
class TrainConfig:
    max_episodes: int = 100
    run_label: str = "run"
    checkpoint_every: int = 5
    updates_per_step: int = 1

    early_stopping: bool = False
    """False gives every method the same budget. The thesis ran with it on."""

    convergence_window: int = 20
    convergence_rel_tol: float = 0.01
    min_episodes_before_convergence: int = 50

    eval_every: Optional[int] = None
    log_every: Optional[int] = None
    verbose: bool = True


@dataclass
class EpisodeRecord:
    episode_idx: int
    seed: int
    total_reward: float
    n_steps: int
    n_violation_steps: int
    pf_failures: int
    mean_step_ms: float
    lambda_lagrange: float
    alpha: float
    mean_qc: float
    realised_cost: float
    """Undiscounted sum of the per-step constraint cost -- the quantity the
    Lagrangian is supposed to be driving down, which the thesis never logged."""
    projection_infeasible_rate: float
    projection_frozen_step_rate: float


@dataclass
class TrainResult:
    run_label: str
    history: List[EpisodeRecord] = field(default_factory=list)
    converged: bool = False
    converged_at: Optional[int] = None
    elapsed_s: float = 0.0
    n_episodes_completed: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["history"] = [asdict(h) if not isinstance(h, dict) else h for h in self.history]
        return d


_CSV_HEADER = (
    "episode_idx,seed,total_reward,n_steps,n_violation_steps,pf_failures,"
    "mean_step_ms,lambda,alpha,mean_qc,realised_cost,proj_infeasible_rate,"
    "proj_frozen_rate\n"
)


def train(
    agent,
    env,
    cfg: ExperimentConfig,
    tc: TrainConfig,
    out_dir: Optional[Path] = None,
    eval_fn: Optional[Callable] = None,
) -> TrainResult:
    """Run `tc.max_episodes` episodes of online training.

    Resumes from `<out_dir>/<run_label>_state.json` if present.
    """
    out_dir = Path(out_dir) if out_dir is not None else None
    model_path = state_path = csv_path = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / f"{tc.run_label}_model.pt"
        state_path = out_dir / f"{tc.run_label}_state.json"
        csv_path = out_dir / f"{tc.run_label}_episodes.csv"

    start_episode = 0
    if state_path is not None and state_path.exists() and model_path.exists():
        try:
            agent.load(model_path)
            start_episode = int(json.loads(state_path.read_text())["next_episode"])
            if tc.verbose:
                print(f"[{tc.run_label}] resuming at episode {start_episode}")
        except Exception as exc:
            print(f"[{tc.run_label}] resume failed ({exc}); starting fresh")
            start_episode = 0

    if csv_path is not None and (start_episode == 0 or not csv_path.exists()):
        csv_path.write_text(_CSV_HEADER)

    detector = ConvergenceDetector(
        tc.convergence_window, tc.convergence_rel_tol, tc.min_episodes_before_convergence
    )

    result = TrainResult(run_label=tc.run_label)
    wall_t0 = time.perf_counter()
    log_every = tc.log_every or max(1, tc.max_episodes // 20)
    has_projection = hasattr(agent, "stats")

    for episode_idx in range(start_episode, tc.max_episodes):
        seed = train_episode_seed(cfg.master_seed, episode_idx, tc.run_label)
        obs, info = env.reset(seed=seed)
        agent.reset_episode()

        # Projection counters are cumulative; snapshot so the row is per-episode.
        proj0 = (agent.stats.n_calls, agent.stats.n_infeasible, agent.stats.n_frozen_steps) if has_projection else (0, 0, 0)

        ep_t0 = time.perf_counter()
        total_r = 0.0
        realised_cost = 0.0
        n_viol = pf_fail = n_steps = 0
        last_metrics: Dict[str, float] = {}

        for t in range(env.scenario.n_steps):
            action = agent.select_action(obs, info=info, deterministic=False)
            next_obs, reward, terminated, truncated, info = env.step(action)
            agent.add_to_replay(
                obs, action, reward, info.constraint_cost, next_obs, float(terminated)
            )
            for _ in range(tc.updates_per_step):
                m = agent.train_step()
                if m:
                    last_metrics = m

            total_r += reward
            realised_cost += info.constraint_cost
            if info.constraint_cost > 1e-4:
                n_viol += 1
            if not info.pf_converged:
                pf_fail += 1
            n_steps = t + 1
            obs = next_obs
            if terminated or truncated:
                break

        mean_step_ms = 1000.0 * (time.perf_counter() - ep_t0) / max(1, n_steps)

        # Episodic dual ascent, if the agent uses it. Must come after the
        # episode, since it is the *measured* cost that drives it.
        if hasattr(agent, "update_dual_from_episode"):
            agent.update_dual_from_episode(realised_cost)

        if has_projection:
            d_calls = agent.stats.n_calls - proj0[0]
            inf_rate = (agent.stats.n_infeasible - proj0[1]) / d_calls if d_calls else 0.0
            frz_rate = (agent.stats.n_frozen_steps - proj0[2]) / d_calls if d_calls else 0.0
        else:
            inf_rate = frz_rate = 0.0

        rec = EpisodeRecord(
            episode_idx=episode_idx,
            seed=seed,
            total_reward=total_r,
            n_steps=n_steps,
            n_violation_steps=n_viol,
            pf_failures=pf_fail,
            mean_step_ms=mean_step_ms,
            lambda_lagrange=float(getattr(agent, "lambda_lagrange", 0.0)),
            alpha=float(getattr(agent, "alpha", 0.0)),
            mean_qc=float(last_metrics.get("mean_qc", float("nan"))),
            realised_cost=realised_cost,
            projection_infeasible_rate=inf_rate,
            projection_frozen_step_rate=frz_rate,
        )
        result.history.append(rec)

        if csv_path is not None:
            with csv_path.open("a") as fh:
                fh.write(
                    f"{rec.episode_idx},{rec.seed},{rec.total_reward:.6f},{rec.n_steps},"
                    f"{rec.n_violation_steps},{rec.pf_failures},{rec.mean_step_ms:.3f},"
                    f"{rec.lambda_lagrange:.6f},{rec.alpha:.6f},{rec.mean_qc:.6f},"
                    f"{rec.realised_cost:.6f},{rec.projection_infeasible_rate:.6f},"
                    f"{rec.projection_frozen_step_rate:.6f}\n"
                )

        if tc.verbose and (
            episode_idx == start_episode
            or (episode_idx + 1) % log_every == 0
            or episode_idx == tc.max_episodes - 1
        ):
            print(
                f"[{tc.run_label}] ep {episode_idx:4d}  R={total_r:9.2f}  viol={n_viol:3d}  "
                f"lam={rec.lambda_lagrange:7.3f}  Jc={realised_cost:6.3f}  "
                f"Qc={rec.mean_qc:+7.3f}  "
                f"inf={inf_rate:.3f}  {mean_step_ms:5.1f} ms/step  "
                f"{time.perf_counter() - wall_t0:6.0f}s"
            )

        if model_path is not None and (episode_idx + 1) % tc.checkpoint_every == 0:
            agent.save(model_path)
            state_path.write_text(
                json.dumps(
                    {
                        "next_episode": episode_idx + 1,
                        "run_label": tc.run_label,
                        "elapsed_time_s": time.perf_counter() - wall_t0,
                        "config_fingerprint": cfg.fingerprint(),
                    },
                    indent=2,
                )
            )

        converged_now = detector.update(total_r)
        if converged_now and result.converged_at is None:
            result.converged_at = episode_idx + 1
            result.converged = True
            if tc.verbose:
                print(f"[{tc.run_label}] convergence criterion met at episode {episode_idx + 1}")
            if tc.early_stopping:
                break

        if eval_fn is not None and tc.eval_every and (episode_idx + 1) % tc.eval_every == 0:
            try:
                eval_fn(agent, episode_idx + 1)
            except Exception as exc:
                print(f"[{tc.run_label}] eval failed: {exc}")

    result.elapsed_s = time.perf_counter() - wall_t0
    result.n_episodes_completed = len(result.history)

    if model_path is not None:
        agent.save(model_path)
        state_path.write_text(
            json.dumps(
                {
                    "next_episode": tc.max_episodes,
                    "run_label": tc.run_label,
                    "elapsed_time_s": result.elapsed_s,
                    "converged": result.converged,
                    "converged_at": result.converged_at,
                    "completed": True,
                    "config_fingerprint": cfg.fingerprint(),
                },
                indent=2,
            )
        )
        if getattr(env, "normalizer", None) is not None:
            (out_dir / f"{tc.run_label}_normalizer.json").write_text(
                json.dumps(env.normalizer.state_dict())
            )

    return result


__all__ = ["ConvergenceDetector", "TrainConfig", "TrainResult", "EpisodeRecord", "train"]
