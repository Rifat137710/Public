"""Audit A2: does clamping the cost critic let the Lagrange multiplier engage?

Trains SAC-Lag twice at the Stage 1 operating point, identical in every respect
but `clamp_cost_critic`, and reports the trajectory of Q_C, lambda and the
realised constraint cost.

    python scripts/lambda_diagnostic.py [--episodes 15]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv, StateNormalizer
from safesac.learned import AgentHParams, SACLagAgent
from safesac.train import TrainConfig, train


def run(clamp: bool, episodes: int, seed: int) -> list:
    cfg = ExperimentConfig.stage1("weak")
    env = ChargingFeederEnv(cfg, normalizer=StateNormalizer(dim=95))
    hp = AgentHParams(clamp_cost_critic=clamp)
    agent = SACLagAgent(env.obs_dim, env.action_dim, hp=hp, device="cpu", seed=seed)
    tc = TrainConfig(
        max_episodes=episodes,
        run_label=f"lambda_clamp{int(clamp)}_s{seed}",
        checkpoint_every=10**9,
        early_stopping=False,
        verbose=False,
    )
    res = train(agent, env, cfg, tc, out_dir=None)
    return res.history


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=15)
    ap.add_argument("--seeds", type=int, nargs="*", default=[0, 1])
    ap.add_argument("--out", type=Path, default=Path("results/lambda_diagnostic.json"))
    args = ap.parse_args()

    out = {}
    for clamp in (False, True):
        tag = "clamped" if clamp else "unclamped"
        print(f"\n=== cost critic {tag} ===")
        print(f"{'seed':>4} {'ep':>3} {'Q_C':>9} {'lambda':>9} {'J_C':>8} {'viol':>5}")
        out[tag] = {}
        for seed in args.seeds:
            hist = run(clamp, args.episodes, seed)
            out[tag][seed] = [
                {
                    "episode": h.episode_idx,
                    "mean_qc": h.mean_qc,
                    "lambda": h.lambda_lagrange,
                    "realised_cost": h.realised_cost,
                    "n_violation_steps": h.n_violation_steps,
                }
                for h in hist
            ]
            for h in hist:
                if h.episode_idx % max(1, args.episodes // 5) == 0 or h.episode_idx == args.episodes - 1:
                    print(
                        f"{seed:>4} {h.episode_idx:>3} {h.mean_qc:>9.4f} "
                        f"{h.lambda_lagrange:>9.5f} {h.realised_cost:>8.4f} "
                        f"{h.n_violation_steps:>5d}"
                    )
            final = hist[-1]
            print(
                f"  seed {seed}: final lambda={final.lambda_lagrange:.5f}  "
                f"Q_C={final.mean_qc:+.4f}  "
                f"{'ENGAGED' if final.lambda_lagrange > 1e-6 else 'PINNED AT ZERO'}"
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {args.out}")

    for tag in ("unclamped", "clamped"):
        finals = [out[tag][s][-1]["lambda"] for s in out[tag]]
        qcs = [out[tag][s][-1]["mean_qc"] for s in out[tag]]
        print(
            f"{tag:>10}: lambda {np.round(finals, 5).tolist()}   "
            f"Q_C {np.round(qcs, 4).tolist()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
