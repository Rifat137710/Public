"""Pick the fixed entropy temperature by sweep, and report it.

SAC's auto-tuner cannot be used here (see `AgentHParams.autotune_alpha`), so
alpha becomes a hyperparameter. This picks it honestly: one sweep, one seed, the
unprojected arm only, judged on service against the heuristic bracket -- never on
the projected-vs-unprojected contrast the ablation is meant to measure.

    python scripts/alpha_sweep.py --alphas 0.003 0.01 0.03 0.1 --episodes 80
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.agents import DroopAgent, UncoordinatedAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv, StateNormalizer
from safesac.evaluate import evaluate
from safesac.learned import AgentHParams, SACLagAgent
from safesac.train import TrainConfig, train

EVAL_LABEL = "stage1_eval"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alphas", type=float, nargs="+", default=[0.003, 0.01, 0.03, 0.1])
    ap.add_argument("--episodes", type=int, default=80)
    ap.add_argument("--eval-episodes", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("results/alpha_sweep.json"))
    args = ap.parse_args()

    cfg = ExperimentConfig.stage1("weak")
    print(f"alpha sweep | fingerprint {cfg.fingerprint()} | seed {args.seed} | "
          f"{args.episodes} episodes\n")

    print("reference (what the learner has to sit between):")
    for name, cls in (("uncoordinated", UncoordinatedAgent), ("droop", DroopAgent)):
        env = ChargingFeederEnv(cfg)
        a = evaluate(cls(env), env, cfg, n_episodes=args.eval_episodes,
                     run_label=EVAL_LABEL)["aggregate"]
        print(f"  {name:14s} viol={a['voltage_violation_step_rate_mean']:.4f}  "
              f"soc={a['frac_meeting_soc_target_mean']:.3f}")
    print()

    out = {}
    print(f"{'alpha':>8}{'viol':>10}{'SoC met':>10}{'net cost':>11}{'lambda':>9}{'sec':>7}")
    for alpha in args.alphas:
        t0 = time.perf_counter()
        hp = AgentHParams(
            autotune_alpha=False,
            init_alpha=alpha,
            clamp_cost_critic=True,
            dual_update="realised",
            cost_limit_episode=0.01,
            lambda_max=100.0,
        )
        env = ChargingFeederEnv(cfg, normalizer=StateNormalizer(dim=95))
        agent = SACLagAgent(env.obs_dim, env.action_dim, hp=hp, device="cpu", seed=args.seed)
        tc = TrainConfig(
            max_episodes=args.episodes,
            run_label=f"alpha{alpha}",
            checkpoint_every=10**9,
            early_stopping=False,
            verbose=False,
        )
        tr = train(agent, env, cfg, tc, out_dir=None)
        agent.eval_mode()
        agg = evaluate(agent, env, cfg, n_episodes=args.eval_episodes,
                       run_label=EVAL_LABEL)["aggregate"]
        out[str(alpha)] = {
            "aggregate": agg,
            "lambda_final": float(agent.lambda_lagrange),
            "reward_trace": [h.total_reward for h in tr.history],
        }
        print(f"{alpha:>8.3f}{agg['voltage_violation_step_rate_mean']:>10.4f}"
              f"{agg['frac_meeting_soc_target_mean']:>10.3f}"
              f"{agg['net_cost_usd_mean']:>11.2f}{agent.lambda_lagrange:>9.3f}"
              f"{time.perf_counter() - t0:>7.0f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, default=float))
    best = max(out, key=lambda a: out[a]["aggregate"]["frac_meeting_soc_target_mean"])
    print(f"\nbest service at alpha={best} "
          f"(SoC {out[best]['aggregate']['frac_meeting_soc_target_mean']:.3f})")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
