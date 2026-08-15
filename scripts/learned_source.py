"""Does the staleness cliff hold when a *learned* policy generates the request?

The headline results (`scripts/staleness_sweep.py`) use heuristic request
sources, because G0 found no operating point on this testbed where a learner
beats greedy. That is the honest framing -- but the paper still has to answer
"does this apply to the RL controller you started from?".

So: train SAC-Lag at the deployment stiffness, then run it through the same
refresh axis as the heuristics. If the cliff sits in the same place for a
learned request as for a greedy one, the finding is about the safety layer and
not about what is upstream of it -- which is the claim.

This is the only part of the conference paper that needs real compute, and it
is a supporting row rather than the headline. Three seeds is enough for that;
five is better if the quota is there.

    python scripts/learned_source.py --seeds 0 1 2 --episodes 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.agents import UncoordinatedAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv, StateNormalizer
from safesac.evaluate import evaluate
from safesac.learned import AgentHParams, SACLagAgent
from safesac.projected import ProjectedAgent
from safesac.train import TrainConfig, train

EVAL_LABEL = "transfer_eval"


def make_hparams(alpha: float) -> AgentHParams:
    """Every Stage 1 fix; no entropy autotuning (docs/01 item N2)."""
    return AgentHParams(
        autotune_alpha=False,
        init_alpha=alpha,
        clamp_cost_critic=True,
        dual_update="realised",
        cost_limit_episode=0.01,
        lambda_max=100.0,
        projection_skip_when_feasible=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--episodes", type=int, default=200)
    ap.add_argument("--eval-episodes", type=int, default=20)
    ap.add_argument("--alpha", type=float, default=0.003)
    ap.add_argument("--train-z", type=float, default=6.0)
    ap.add_argument("--eval-z", type=float, nargs="+", default=[6.0, 8.0])
    ap.add_argument("--refresh", type=int, nargs="+", default=[1, 12, 48, 288])
    ap.add_argument("--load", type=float, default=0.40)
    ap.add_argument("--evs", type=float, default=30.0)
    ap.add_argument("--out-dir", type=Path, default=Path("results/learned_source"))
    args = ap.parse_args()

    def cfg_at(z, refresh=None):
        c = ExperimentConfig.stiffness(z, evs_per_station=args.evs,
                                       load_scale=args.load)
        if refresh is not None:
            c = replace(c, safety=replace(c.safety,
                                          sensitivity_refresh_steps=refresh))
        return c

    train_cfg = cfg_at(args.train_z)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"LEARNED REQUEST SOURCE  train Z={args.train_z}%  eval Z={args.eval_z}%")
    print(f"refresh axis {args.refresh} | {len(args.seeds)} seeds x "
          f"{args.episodes} episodes | fingerprint {train_cfg.fingerprint()}")
    print("=" * 78)

    results = {"train_z_pct": args.train_z, "eval_z_pct": args.eval_z,
               "refresh": args.refresh, "seeds": args.seeds,
               "episodes": args.episodes, "alpha": args.alpha,
               "fingerprint": train_cfg.fingerprint(),
               "heuristic": {}, "cells": {}}

    # ---- heuristic reference on the same axis ----------------------------
    print("\n[reference] uncoordinated request, same refresh axis")
    for z in args.eval_z:
        row = {}
        env = ChargingFeederEnv(cfg_at(z))
        raw = evaluate(UncoordinatedAgent(env), env, cfg_at(z),
                       n_episodes=args.eval_episodes,
                       run_label=EVAL_LABEL)["aggregate"]
        row["raw"] = {"viol": raw["voltage_violation_step_rate_mean"],
                      "soc": raw["frac_meeting_soc_target_mean"]}
        for r in args.refresh:
            cfg = cfg_at(z, r)
            env = ChargingFeederEnv(cfg)
            agg = evaluate(ProjectedAgent(UncoordinatedAgent(env), env, cfg), env,
                           cfg, n_episodes=args.eval_episodes,
                           run_label=EVAL_LABEL)["aggregate"]
            row[str(r)] = {"viol": agg["voltage_violation_step_rate_mean"],
                           "soc": agg["frac_meeting_soc_target_mean"]}
        results["heuristic"][str(z)] = row
        print(f"  Z={z:4.1f}%  raw={row['raw']['viol']:.4f}  "
              + "  ".join(f"{r}={row[str(r)]['viol']:.4f}" for r in args.refresh))

    # ---- train, then walk the refresh axis -------------------------------
    for seed in args.seeds:
        t0 = time.perf_counter()
        print(f"\n[seed {seed}] training at Z={args.train_z}%")
        env = ChargingFeederEnv(train_cfg, normalizer=StateNormalizer(dim=95))
        agent = SACLagAgent(env.obs_dim, env.action_dim,
                            hp=make_hparams(args.alpha), device="cpu", seed=seed)
        tc = TrainConfig(max_episodes=args.episodes,
                         run_label=f"learned_src_s{seed}", checkpoint_every=25,
                         early_stopping=False, verbose=True,
                         log_every=max(1, args.episodes // 10))
        tr = train(agent, env, train_cfg, tc, out_dir=args.out_dir)
        agent.eval_mode()
        normalizer = env.normalizer
        print(f"  trained in {time.perf_counter() - t0:.0f}s  "
              f"lambda={agent.lambda_lagrange:.3f}")

        for z in args.eval_z:
            row = {}
            e = ChargingFeederEnv(cfg_at(z), normalizer=normalizer)
            e.normalizer.freeze()
            agg = evaluate(agent, e, cfg_at(z), n_episodes=args.eval_episodes,
                           run_label=EVAL_LABEL)["aggregate"]
            row["raw"] = {"viol": agg["voltage_violation_step_rate_mean"],
                          "soc": agg["frac_meeting_soc_target_mean"]}
            for r in args.refresh:
                cfg = cfg_at(z, r)
                e = ChargingFeederEnv(cfg, normalizer=normalizer)
                e.normalizer.freeze()
                a = ProjectedAgent(agent, e, cfg)
                agg = evaluate(a, e, cfg, n_episodes=args.eval_episodes,
                               run_label=EVAL_LABEL)["aggregate"]
                row[str(r)] = {"viol": agg["voltage_violation_step_rate_mean"],
                               "soc": agg["frac_meeting_soc_target_mean"],
                               "infeasible": a.stats.summary()["projection_infeasible_rate"]}
            results["cells"].setdefault(str(z), {})[str(seed)] = row
            print(f"    Z={z:4.1f}%  raw={row['raw']['viol']:.4f}  "
                  + "  ".join(f"{r}={row[str(r)]['viol']:.4f}" for r in args.refresh))

        (args.out_dir / "learned_source.json").write_text(
            json.dumps(results, indent=2, default=float))

    # ---- summary ---------------------------------------------------------
    print("\n" + "=" * 78)
    print("Violation rate against refresh interval, learned request "
          "(mean +- sd across seeds)")
    print("=" * 78)
    hdr = "".join(f"{('every ' + str(r)):>14}" for r in args.refresh)
    print(f"{'Z%':>6}{'raw':>10}{hdr}")
    summary = {}
    for z in args.eval_z:
        cells = results["cells"][str(z)].values()
        row = {}
        for key in ["raw"] + [str(r) for r in args.refresh]:
            v = np.array([c[key]["viol"] for c in cells])
            s = np.array([c[key]["soc"] for c in cells])
            row[key] = {"viol": [float(v.mean()), float(v.std(ddof=0))],
                        "soc": [float(s.mean()), float(s.std(ddof=0))]}
        summary[str(z)] = row
        print(f"{z:>6.1f}{row['raw']['viol'][0]:>10.4f}"
              + "".join(f"{row[str(r)]['viol'][0]:>9.4f}+-{row[str(r)]['viol'][1]:.2f}"
                        for r in args.refresh))

    results["summary"] = summary
    (args.out_dir / "learned_source.json").write_text(
        json.dumps(results, indent=2, default=float))

    # Does the cliff land in the same place as for the heuristic request?
    z0 = str(args.eval_z[0])
    tight = [r for r in args.refresh if summary[z0][str(r)]["viol"][0] < 1e-9]
    h = results["heuristic"][z0]
    h_tight = [r for r in args.refresh if h[str(r)]["viol"] < 1e-9]
    print(f"\nAt Z={z0}%: learned request is violation-free for refresh <= "
          f"{max(tight) if tight else 'none'}; "
          f"uncoordinated for refresh <= {max(h_tight) if h_tight else 'none'}")
    print("Same cliff location => the finding is about the safety layer, "
          "not the upstream controller.")
    print(f"wrote {args.out_dir / 'learned_source.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
