"""Is the residual service gap a training-budget problem?

Every failure so far has been a defect with a mechanism. This asks whether what
remains is simply that SAC has not had enough experience: one long unprojected
run at the swept alpha, reporting service against the heuristic bracket at
intervals. A curve that is still climbing at the end says budget; a flat one
says the operating point or the reward is wrong.

    python scripts/budget_probe.py --episodes 500
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
    ap.add_argument("--episodes", type=int, default=500)
    ap.add_argument("--alpha", type=float, default=0.003)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eval-every", type=int, default=50)
    ap.add_argument("--eval-episodes", type=int, default=10)
    ap.add_argument("--out", type=Path, default=Path("results/budget_probe.json"))
    args = ap.parse_args()

    cfg = ExperimentConfig.stage1("weak")
    print(f"budget probe | alpha={args.alpha} | seed {args.seed} | "
          f"{args.episodes} episodes ({args.episodes * 288:,} steps)\n")

    for name, cls in (("uncoordinated", UncoordinatedAgent), ("droop", DroopAgent)):
        env = ChargingFeederEnv(cfg)
        a = evaluate(cls(env), env, cfg, n_episodes=args.eval_episodes,
                     run_label=EVAL_LABEL)["aggregate"]
        print(f"  {name:14s} viol={a['voltage_violation_step_rate_mean']:.4f}  "
              f"soc={a['frac_meeting_soc_target_mean']:.3f}")

    hp = AgentHParams(
        autotune_alpha=False,
        init_alpha=args.alpha,
        clamp_cost_critic=True,
        dual_update="realised",
        cost_limit_episode=0.01,
        lambda_max=100.0,
    )
    env = ChargingFeederEnv(cfg, normalizer=StateNormalizer(dim=95))
    agent = SACLagAgent(env.obs_dim, env.action_dim, hp=hp, device="cpu", seed=args.seed)

    curve = []

    def probe(ag, episode):
        ag.actor.eval()
        agg = evaluate(ag, env, cfg, n_episodes=args.eval_episodes,
                       run_label=EVAL_LABEL)["aggregate"]
        ag.actor.train()
        curve.append({
            "episode": episode,
            "viol": agg["voltage_violation_step_rate_mean"],
            "soc": agg["frac_meeting_soc_target_mean"],
            "cost": agg["net_cost_usd_mean"],
            "lambda": float(ag.lambda_lagrange),
        })
        print(f"  ep {episode:4d}  viol={curve[-1]['viol']:.4f}  "
              f"soc={curve[-1]['soc']:.3f}  cost=${curve[-1]['cost']:7.2f}  "
              f"lambda={curve[-1]['lambda']:.3f}")

    print(f"\ntraining, probing every {args.eval_every} episodes:")
    tc = TrainConfig(
        max_episodes=args.episodes,
        run_label=f"budget_a{args.alpha}_s{args.seed}",
        checkpoint_every=10**9,
        early_stopping=False,
        eval_every=args.eval_every,
        verbose=False,
    )
    t0 = time.perf_counter()
    tr = train(agent, env, cfg, tc, out_dir=None, eval_fn=probe)
    print(f"\ntrained in {time.perf_counter() - t0:.0f}s")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"alpha": args.alpha, "seed": args.seed, "curve": curve,
         "reward_trace": [h.total_reward for h in tr.history]},
        indent=2, default=float,
    ))

    if len(curve) >= 4:
        early = np.mean([c["soc"] for c in curve[: len(curve) // 2]])
        late = np.mean([c["soc"] for c in curve[len(curve) // 2 :]])
        print(f"\nSoC met, first half {early:.3f} -> second half {late:.3f}")
        print("verdict:", "still climbing - budget-limited"
              if late > early * 1.25 else
              "flat - more episodes will not fix this")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
