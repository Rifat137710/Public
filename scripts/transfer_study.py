"""T4 + T5 -- the transfer study. This is the conference paper.

One policy per seed, trained at a single feeder stiffness, then deployed
zero-shot across a stiffness sweep under four treatments:

    A  raw                    the learned policy alone
    B  frozen projection      projected, but against the *training* feeder's
                              sensitivities -- the prior-art parametrisation
    C  deployment projection  projected against the deployment feeder's
                              sensitivities -- ours
    H  uncoordinated + C      the honest upper reference: what the safety layer
                              achieves with no learning at all

A, B and C share one trained policy, so nothing differs between them except
what physics the projection carries. That is the whole experiment: if C holds
the band and B does not, the contribution is the *deployment-side
parametrisation*, not the projection.

The normalizer is frozen at training statistics. A controller deployed on an
unseen feeder cannot re-estimate its input statistics from that feeder's data
without collecting it first, so letting it adapt would smuggle in target-network
information and inflate the result.

    python scripts/transfer_study.py --seeds 0 1 2 3 4 --episodes 200

Runs on CPU. ~35 min/seed for training on 4 vCPUs; deployment is cheap.
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
from safesac.learned import AgentHParams, SACLagAgent
from safesac.projected import ProjectedAgent
from safesac.projection import SensitivityCache
from safesac.train import TrainConfig, train

EVAL_LABEL = "transfer_eval"

# Overwritten by --train-z / --deploy-z / --load / --evs. Defaults are the
# Stage 1 operating point; G0 (scripts/operating_point_sweep.py) decides whether
# they move.
TRAIN_Z_PCT = 0.5          # stiff: the policy never meets a binding voltage limit
DEPLOY_Z_PCT = [0.5, 2.0, 4.0, 6.0]


def make_hparams(alpha: float) -> AgentHParams:
    """Every Stage 1 fix, and no entropy autotuning -- see docs/01 item N2."""
    return AgentHParams(
        autotune_alpha=False,
        init_alpha=alpha,
        clamp_cost_critic=True,
        dual_update="realised",
        cost_limit_episode=0.01,
        lambda_max=100.0,
        projection_skip_when_feasible=True,
    )


def training_sensitivities(cfg: ExperimentConfig):
    """Sensitivities of the *training* feeder, for arm B.

    Taken at the feeder's own idle state, which is all a controller shipped
    with a fixed model would carry.
    """
    env = ChargingFeederEnv(cfg)
    env.reset(seed=0)
    cache = SensitivityCache(cfg, env.feeder, env._pf_solver)
    cache.maybe_refresh(0)
    return cache.sens, cache.loading


def train_one(seed: int, cfg: ExperimentConfig, episodes: int, alpha: float,
              out_dir: Path):
    env = ChargingFeederEnv(cfg, normalizer=StateNormalizer(dim=95))
    agent = SACLagAgent(env.obs_dim, env.action_dim, hp=make_hparams(alpha),
                        device="cpu", seed=seed)
    tc = TrainConfig(
        max_episodes=episodes,
        run_label=f"transfer_train_s{seed}",
        checkpoint_every=25,
        early_stopping=False,       # identical budget for every seed
        verbose=True,
        log_every=max(1, episodes // 10),
    )
    res = train(agent, env, cfg, tc, out_dir=out_dir)
    return agent, env.normalizer, res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--episodes", type=int, default=200)
    ap.add_argument("--eval-episodes", type=int, default=20)
    ap.add_argument("--alpha", type=float, default=0.003)
    ap.add_argument("--train-z", type=float, default=TRAIN_Z_PCT)
    ap.add_argument("--deploy-z", type=float, nargs="+", default=DEPLOY_Z_PCT)
    ap.add_argument("--load", type=float, default=0.40)
    ap.add_argument("--evs", type=float, default=30.0)
    ap.add_argument("--out-dir", type=Path, default=Path("results/transfer"))
    args = ap.parse_args()

    def cfg_at(z):
        return ExperimentConfig.stiffness(
            z, evs_per_station=args.evs, load_scale=args.load
        )

    train_cfg = cfg_at(args.train_z)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"TRANSFER STUDY  train Z={args.train_z}%  deploy Z={args.deploy_z}%")
    print(f"load {args.load}  {args.evs:.0f} EVs/station  alpha {args.alpha}")
    print(f"{len(args.seeds)} seeds x {args.episodes} episodes  "
          f"| fingerprint {train_cfg.fingerprint()}")
    print("=" * 78)

    frozen_sens, frozen_loading = training_sensitivities(train_cfg)

    results = {
        "train_z_pct": args.train_z, "deploy_z_pct": args.deploy_z,
        "load_scale": args.load, "evs_per_station": args.evs, "alpha": args.alpha,
        "episodes": args.episodes, "seeds": args.seeds,
        "train_fingerprint": train_cfg.fingerprint(),
        "reference": {}, "cells": {},
    }

    # ---- heuristic references at every deployment point ------------------
    print("\n[references] per deployment point")
    baselines = {}
    for z in args.deploy_z:
        cfg = cfg_at(z)
        row = {}
        for name, make in (
            ("zero", lambda e: ZeroAgent(e)),
            ("uncoordinated", lambda e: UncoordinatedAgent(e)),
            ("droop", lambda e: DroopAgent(e)),
            ("uncoordinated+proj", lambda e: ProjectedAgent(UncoordinatedAgent(e), e, cfg)),
        ):
            env = ChargingFeederEnv(cfg)
            ev = evaluate(make(env), env, cfg, n_episodes=args.eval_episodes,
                          run_label=EVAL_LABEL)
            row[name] = ev["aggregate"]
            if name == "zero":
                baselines[z] = ev["per_episode"]
        results["reference"][str(z)] = row
        print(f"  Z={z:4.1f}%  idle_viol={row['zero']['voltage_violation_step_rate_mean']:.4f}"
              f"  uncoord={row['uncoordinated']['voltage_violation_step_rate_mean']:.4f}"
              f"/{row['uncoordinated']['frac_meeting_soc_target_mean']:.3f}"
              f"  u+proj={row['uncoordinated+proj']['voltage_violation_step_rate_mean']:.4f}"
              f"/{row['uncoordinated+proj']['frac_meeting_soc_target_mean']:.3f}")

    # ---- train, then deploy ---------------------------------------------
    for seed in args.seeds:
        t0 = time.perf_counter()
        print(f"\n[seed {seed}] training at Z={args.train_z}% "
              f"for {args.episodes} episodes")
        agent, normalizer, tr = train_one(seed, train_cfg, args.episodes,
                                          args.alpha, args.out_dir)
        agent.eval_mode()
        print(f"  trained in {time.perf_counter() - t0:.0f}s  "
              f"lambda={agent.lambda_lagrange:.3f}")

        for z in args.deploy_z:
            cfg = cfg_at(z)
            arms = {}
            for arm in ("A_raw", "B_frozen_proj", "C_deploy_proj"):
                env = ChargingFeederEnv(cfg, normalizer=normalizer)
                env.normalizer.freeze()   # no target-network adaptation
                if arm == "A_raw":
                    actor = agent
                elif arm == "B_frozen_proj":
                    actor = ProjectedAgent(agent, env, cfg,
                                           frozen_sensitivities=frozen_sens,
                                           frozen_loading=frozen_loading)
                else:
                    actor = ProjectedAgent(agent, env, cfg)
                ev = evaluate(actor, env, cfg, n_episodes=args.eval_episodes,
                              run_label=EVAL_LABEL)
                row = {"aggregate": ev["aggregate"],
                       "attributable": attributable(ev["per_episode"], baselines[z])}
                if hasattr(actor, "stats"):
                    row["projection"] = actor.stats.summary()
                arms[arm] = row

            results["cells"].setdefault(str(z), {})[str(seed)] = arms
            fmt = lambda a: (f"{a['aggregate']['voltage_violation_step_rate_mean']:.4f}"  # noqa: E731
                             f"/{a['aggregate']['frac_meeting_soc_target_mean']:.3f}")
            print(f"    Z={z:4.1f}%   A={fmt(arms['A_raw'])}   "
                  f"B={fmt(arms['B_frozen_proj'])}   C={fmt(arms['C_deploy_proj'])}")

        (args.out_dir / "transfer.json").write_text(
            json.dumps(results, indent=2, default=float))

    # ---- summary ---------------------------------------------------------
    print("\n" + "=" * 78)
    print("TRANSFER MATRIX -- violations / SoC met, mean +- sd across seeds")
    print("=" * 78)
    print(f"{'Z%':>6}  {'A raw':>18}{'B frozen proj':>20}{'C deploy proj':>20}"
          f"{'uncoord+proj':>18}")
    summary = {}
    for z in args.deploy_z:
        cells = results["cells"][str(z)]
        row = {}
        for arm in ("A_raw", "B_frozen_proj", "C_deploy_proj"):
            v = np.array([c[arm]["aggregate"]["voltage_violation_step_rate_mean"]
                          for c in cells.values()])
            s = np.array([c[arm]["aggregate"]["frac_meeting_soc_target_mean"]
                          for c in cells.values()])
            row[arm] = {"viol": [float(v.mean()), float(v.std(ddof=0))],
                        "soc": [float(s.mean()), float(s.std(ddof=0))]}
        summary[str(z)] = row
        h = results["reference"][str(z)]["uncoordinated+proj"]
        print(f"{z:>6.1f}  "
              + "".join(
                  f"{row[a]['viol'][0]:>8.4f}/{row[a]['soc'][0]:.3f}"
                  f"+-{row[a]['soc'][1]:.2f}   " for a in row)
              + f"{h['voltage_violation_step_rate_mean']:>8.4f}"
                f"/{h['frac_meeting_soc_target_mean']:.3f}")

    results["summary"] = summary
    (args.out_dir / "transfer.json").write_text(
        json.dumps(results, indent=2, default=float))

    # ---- the claims, checked --------------------------------------------
    print("\n" + "-" * 78)
    far = str(max(args.deploy_z))
    near = str(min(args.deploy_z))
    a_deg = summary[far]["A_raw"]["viol"][0] - summary[near]["A_raw"]["viol"][0]
    c_deg = summary[far]["C_deploy_proj"]["viol"][0] - summary[near]["C_deploy_proj"]["viol"][0]
    b_far = summary[far]["B_frozen_proj"]["viol"][0]
    c_far = summary[far]["C_deploy_proj"]["viol"][0]
    print(f"C1  unprojected safety degrades with deployment distance: "
          f"{a_deg:+.4f} violations from Z={near}% to Z={far}%  "
          f"{'PASS' if a_deg > 0.01 else 'NOT SHOWN'}")
    print(f"C2  deployment-parametrised projection holds the band: "
          f"{c_far:.4f} at Z={far}%  {'PASS' if c_far < 1e-9 else 'FAIL'}")
    c3 = ("PASS" if b_far > c_far + 1e-9 else
          "NOT SHOWN -- the projection is robust to stale physics; report that")
    print(f"C3  the parametrisation is what matters (B vs C at Z={far}%): "
          f"B={b_far:.4f} vs C={c_far:.4f}  {c3}")
    print(f"    (C degradation for reference: {c_deg:+.4f})")
    print(f"\nwrote {args.out_dir / 'transfer.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
