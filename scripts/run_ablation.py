"""Audit A1: the ablation the thesis claimed to run.

Two arms that differ in exactly one thing -- whether the action is projected --
and are identical in everything else: same budget, same seeds, same entropy
ceiling, same cost-critic treatment, same learning rates. The published
comparison had none of that (85 vs 97 episodes, an alpha cap on one arm only, a
critic-learning-rate override on one arm only, and a Lagrange multiplier stuck
at zero in the baseline).

Each arm is also evaluated against a paired zero-injection run, so violations
are reported as *attributable* excess rather than as a raw rate dominated by the
exogenous background (audit A4).

    python scripts/run_ablation.py --seeds 0 1 2 --episodes 60

Gate 1 wants three pilot seeds. Report whatever comes out -- including a null.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.agents import DroopAgent, UncoordinatedAgent, ZeroAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv, StateNormalizer
from safesac.evaluate import attributable, evaluate
from safesac.learned import AgentHParams, SACLagAgent, SafeSACLagAgent
from safesac.train import TrainConfig, train

EVAL_LABEL = "stage1_eval"

# The only difference between the arms.
ARMS = {"no_projection": False, "projection": True}


def make_hparams() -> AgentHParams:
    """Identical for both arms -- that is the whole point."""
    return AgentHParams(
        clamp_cost_critic=True,   # audit A2
        alpha_ceiling=1.0,        # audit B5, applied to BOTH arms
        projection_skip_when_feasible=True,   # proven equivalent, just faster
    )


def train_arm(arm: str, seed: int, cfg: ExperimentConfig, episodes: int, out_dir: Path):
    hp = make_hparams()
    env = ChargingFeederEnv(cfg, normalizer=StateNormalizer(dim=95))
    label = f"{arm}_s{seed}"

    if ARMS[arm]:
        agent = SafeSACLagAgent(
            env.obs_dim, env.action_dim, env, cfg=cfg, hp=hp, device="cpu", seed=seed
        )
    else:
        agent = SACLagAgent(env.obs_dim, env.action_dim, hp=hp, device="cpu", seed=seed)

    tc = TrainConfig(
        max_episodes=episodes,
        run_label=label,
        checkpoint_every=10,
        early_stopping=False,     # audit A1/A6: identical budget
        verbose=True,
        log_every=max(1, episodes // 10),
    )
    res = train(agent, env, cfg, tc, out_dir=out_dir)
    return agent, env, res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--episodes", type=int, default=60)
    ap.add_argument("--eval-episodes", type=int, default=25)
    ap.add_argument("--variant", default="weak")
    ap.add_argument("--out-dir", type=Path, default=Path("results/ablation"))
    args = ap.parse_args()

    cfg = ExperimentConfig.stage1(args.variant)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Stage 1 fair ablation | fingerprint {cfg.fingerprint()}")
    print(f"arms {list(ARMS)} | seeds {args.seeds} | {args.episodes} train eps "
          f"| {args.eval_episodes} eval eps\n")

    # ---- reference rows, seed-independent -------------------------------
    print("[reference] heuristics and the zero-injection baseline")
    reference, baseline_per_ep = {}, None
    for name, cls in (("zero", ZeroAgent), ("uncoordinated", UncoordinatedAgent),
                      ("droop", DroopAgent)):
        env = ChargingFeederEnv(cfg)
        r = evaluate(cls(env), env, cfg, n_episodes=args.eval_episodes, run_label=EVAL_LABEL)
        reference[name] = r["aggregate"]
        if name == "zero":
            baseline_per_ep = r["per_episode"]
        a = r["aggregate"]
        print(f"  {name:14s} viol={a['voltage_violation_step_rate_mean']:.4f}  "
              f"soc={a['frac_meeting_soc_target_mean']:.3f}  "
              f"cost=${a['net_cost_usd_mean']:8.2f}")

    # ---- the ablation ----------------------------------------------------
    results = {"config_fingerprint": cfg.fingerprint(), "reference": reference, "arms": {}}

    for arm in ARMS:
        results["arms"][arm] = {}
        for seed in args.seeds:
            t0 = time.perf_counter()
            print(f"\n[{arm} | seed {seed}] training {args.episodes} episodes")
            agent, env, tr = train_arm(arm, seed, cfg, args.episodes, args.out_dir)

            agent.eval_mode()
            ev = evaluate(
                agent, env, cfg, n_episodes=args.eval_episodes, run_label=EVAL_LABEL
            )
            agg = ev["aggregate"]
            attr = attributable(ev["per_episode"], baseline_per_ep)

            row = {
                "aggregate": agg,
                "attributable": attr,
                "lambda_final": float(agent.lambda_lagrange),
                "alpha_final": float(agent.alpha),
                "episodes_trained": tr.n_episodes_completed,
                "converged_at": tr.converged_at,
                "train_seconds": tr.elapsed_s,
                "lambda_trace": [h.lambda_lagrange for h in tr.history],
                "realised_cost_trace": [h.realised_cost for h in tr.history],
                "mean_qc_trace": [h.mean_qc for h in tr.history],
            }
            if hasattr(agent, "stats"):
                row["projection"] = agent.stats.summary()
            results["arms"][arm][str(seed)] = row

            print(
                f"  -> viol={agg['voltage_violation_step_rate_mean']:.4f}  "
                f"attributable={attr['voltage_violation_step_rate_excess_mean']:+.4f}  "
                f"soc={agg['frac_meeting_soc_target_mean']:.3f}  "
                f"cost=${agg['net_cost_usd_mean']:8.2f}  "
                f"lambda={agent.lambda_lagrange:.4f}  ({time.perf_counter() - t0:.0f}s)"
            )

    out = args.out_dir / "ablation.json"
    out.write_text(json.dumps(results, indent=2, default=float))

    # ---- summary ---------------------------------------------------------
    print("\n" + "=" * 78)
    print("STAGE 1 PILOT -- mean +- sd across seeds")
    print("=" * 78)
    print(f"{'arm':<16}{'viol':>10}{'attributable':>15}{'SoC met':>10}"
          f"{'net cost':>11}{'lambda':>10}")
    summary = {}
    for arm in ARMS:
        rows = results["arms"][arm].values()
        g = lambda k: np.array([r["aggregate"][k] for r in rows])  # noqa: E731
        att = np.array(
            [r["attributable"]["voltage_violation_step_rate_excess_mean"] for r in rows]
        )
        lam = np.array([r["lambda_final"] for r in rows])
        summary[arm] = {
            "viol": [float(g("voltage_violation_step_rate_mean").mean()),
                     float(g("voltage_violation_step_rate_mean").std(ddof=0))],
            "attributable": [float(att.mean()), float(att.std(ddof=0))],
            "soc": [float(g("frac_meeting_soc_target_mean").mean()),
                    float(g("frac_meeting_soc_target_mean").std(ddof=0))],
            "cost": [float(g("net_cost_usd_mean").mean()),
                     float(g("net_cost_usd_mean").std(ddof=0))],
            "lambda": [float(lam.mean()), float(lam.std(ddof=0))],
        }
        s = summary[arm]
        print(f"{arm:<16}{s['viol'][0]:>7.4f}+-{s['viol'][1]:.3f}"
              f"{s['attributable'][0]:>+11.4f}+-{s['attributable'][1]:.3f}"
              f"{s['soc'][0]:>7.3f}+-{s['soc'][1]:.2f}"
              f"{s['cost'][0]:>8.2f}+-{s['cost'][1]:.1f}"
              f"{s['lambda'][0]:>7.3f}+-{s['lambda'][1]:.2f}")

    d_soc = summary["projection"]["soc"][0] - summary["no_projection"]["soc"][0]
    d_viol = summary["projection"]["viol"][0] - summary["no_projection"]["viol"][0]
    print(f"\nprojection - no_projection:  SoC {d_soc:+.4f}   violations {d_viol:+.4f}")
    print("thesis reported SoC +0.2921 for the same contrast (unequal budgets, "
          "lambda pinned at 0 in the baseline)")

    # ---- Gate 1 ----------------------------------------------------------
    # "lambda demonstrably tracks the constraint" is two separate claims, and
    # they can come apart: a cost critic fitted off-distribution can push lambda
    # up while the realised cost is flat at zero. Report both.
    print("\n" + "-" * 78)
    lam_engaged, correlations = True, {}
    for arm in ARMS:
        for seed, r in results["arms"][arm].items():
            lam = np.asarray(r["lambda_trace"], dtype=float)
            jc = np.asarray(r["realised_cost_trace"], dtype=float)
            engaged = float(lam[-1]) > 1e-6
            lam_engaged &= engaged
            if jc.std() > 1e-12 and lam.std() > 1e-12:
                rho = float(np.corrcoef(lam, jc)[0, 1])
            else:
                rho = float("nan")   # nothing to track
            correlations[f"{arm}_s{seed}"] = {
                "lambda_final": float(lam[-1]),
                "realised_cost_mean": float(jc.mean()),
                "corr_lambda_vs_realised_cost": rho,
            }
            print(f"  {arm:<16} seed {seed}:  lambda_final={lam[-1]:8.4f}  "
                  f"mean J_C={jc.mean():7.4f}  corr(lambda, J_C)={rho:+.3f}"
                  f"{'' if engaged else '   <-- PINNED AT ZERO'}")

    informative = [
        c["corr_lambda_vs_realised_cost"]
        for c in correlations.values()
        if c["realised_cost_mean"] > 1e-6
    ]
    print(f"\nGate 1a -- lambda leaves zero in every run: {'PASS' if lam_engaged else 'FAIL'}")
    if informative:
        print(f"Gate 1b -- lambda vs realised cost, mean corr over runs with any "
              f"violation: {np.mean(informative):+.3f} (n={len(informative)})")
    else:
        print("Gate 1b -- NOT ASSESSABLE: realised cost is ~0 in every run, so "
              "there is no constraint for lambda to track. Raise EV penetration "
              "or lengthen training before reading anything into lambda.")

    results["summary"] = summary
    results["gate1_lambda_engaged"] = lam_engaged
    results["gate1_lambda_tracking"] = correlations
    out.write_text(json.dumps(results, indent=2, default=float))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
