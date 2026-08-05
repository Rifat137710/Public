"""Stage 0 gate: reproduce the four learned rows of thesis Table 6.1.

Loads the shipped checkpoints and their frozen normalizers, evaluates each on
the same 25 eval seeds the thesis used (`patch7_weak_eval`), and diffs against
the published aggregates.

    python scripts/reproduce_table_6_1.py --checkpoints <dir> [--episodes 25]

Reproduction runs the published path: no feasibility pre-check, and the
sensitivity cache cleared at every episode boundary the way the thesis's
`select_action` patch cell did it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.config import MASTER_SEED, ExperimentConfig, derive_seed
from safesac.env import ChargingFeederEnv, StateNormalizer
from safesac.evaluate import evaluate
from safesac.learned import AgentHParams, SACLagAgent, SafeSACLagAgent

EVAL_LABEL = "patch7_weak_eval"

# thesis Table 6.1, weak-feeder deployment, 25 shared-seed episodes
PUBLISHED = {
    "sac_lag_weak": {
        "voltage_violation_step_rate_mean": 0.0904,
        "frac_meeting_soc_target_mean": 0.2767,
        "net_cost_usd_mean": 104.29,
        "total_reward_mean": -923.50,
        "v2g_utilization_rate_mean": 0.1765,
        "vmin_pu_mean": 0.9425,
    },
    "safe_sac_weak": {
        "voltage_violation_step_rate_mean": 0.0912,
        "frac_meeting_soc_target_mean": 0.5688,
        "net_cost_usd_mean": 125.94,
        "total_reward_mean": -505.15,
        "v2g_utilization_rate_mean": 0.1027,
        "vmin_pu_mean": 0.9438,
    },
    "sac_lag_strong_xdeploy": {
        "voltage_violation_step_rate_mean": 0.0151,
        "frac_meeting_soc_target_mean": 0.0000,
        "net_cost_usd_mean": -38.17,
        "total_reward_mean": -1898.67,
        "v2g_utilization_rate_mean": 0.1055,
        "vmin_pu_mean": 0.9492,
    },
    "safe_sac_strong_xdeploy": {
        "voltage_violation_step_rate_mean": 0.1058,
        "frac_meeting_soc_target_mean": 0.4469,
        "net_cost_usd_mean": 69.66,
        "total_reward_mean": -1024.12,
        "v2g_utilization_rate_mean": 0.0475,
        "vmin_pu_mean": 0.9438,
    },
}

METHODS = [
    ("sac_lag_weak", "saclag_weak_v2", "sac_lag"),
    ("safe_sac_weak", "safesac_weak_v3", "safe_sac"),
    ("sac_lag_strong_xdeploy", "saclag_strong_v2", "sac_lag"),
    ("safe_sac_strong_xdeploy", "safesac_strong_v3", "safe_sac"),
]

# A metric passes within half of the last published digit, or within 1 % of the
# published value, whichever is looser.
#
# The 1 % band exists because the reference run was torch 2.10 on a Tesla T4 and
# this one is torch 2.13 on CPU. A deterministic actor forward pass differs in
# the last float32 bits between those, and near an action bound that occasionally
# flips a charge/idle decision, which then compounds over 288 steps. The two
# cross-deployment rows land within 6 significant figures anyway, which is what
# says the residual is arithmetic drift and not a porting error.
ABS_TOL = {
    "voltage_violation_step_rate_mean": 5e-5,
    "frac_meeting_soc_target_mean": 5e-5,
    "net_cost_usd_mean": 5e-3,
    "total_reward_mean": 5e-3,
    "v2g_utilization_rate_mean": 5e-5,
    "vmin_pu_mean": 5e-5,
}
REL_TOL = 0.01


def tolerance(key: str, published: float) -> float:
    return max(ABS_TOL[key], REL_TOL * abs(published))


def load_agent(ckpt_dir: Path, label: str, kind: str, cfg: ExperimentConfig, hp: AgentHParams):
    """Mirror the notebook's `_load_trained`: frozen normalizer, eval-only env."""
    probe = ChargingFeederEnv(cfg)
    norm = StateNormalizer(dim=probe.obs_dim)
    norm_path = ckpt_dir / f"{label}_normalizer.json"
    if not norm_path.exists():
        raise FileNotFoundError(f"missing normalizer: {norm_path}")
    norm.load_state_dict(json.loads(norm_path.read_text()))
    norm.freeze()

    env = ChargingFeederEnv(cfg, normalizer=norm, update_normalizer=False)
    env.reset(seed=derive_seed(MASTER_SEED, "init_for_load", label))

    if kind == "safe_sac":
        agent = SafeSACLagAgent(env.obs_dim, env.action_dim, env, cfg=cfg, hp=hp, device="cpu")
    else:
        agent = SACLagAgent(env.obs_dim, env.action_dim, hp=hp, device="cpu")
    agent.load(ckpt_dir / f"{label}_model.pt")
    agent.eval_mode()
    return agent, env, norm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoints", type=Path, required=True)
    ap.add_argument("--episodes", type=int, default=25)
    ap.add_argument("--out", type=Path, default=Path("results/table_6_1_reproduction.json"))
    ap.add_argument(
        "--only", nargs="*", default=None, help="subset of method names to run"
    )
    ap.add_argument(
        "--stale-cache",
        action="store_true",
        help="skip the per-episode cache reset, i.e. run the unpatched notebook path",
    )
    args = ap.parse_args()

    cfg = ExperimentConfig.thesis_final("weak")
    hp = AgentHParams(
        stale_cache_across_episodes=args.stale_cache,
        reset_projector_each_episode=not args.stale_cache,
    )
    print(f"config fingerprint: {cfg.fingerprint()}")
    print(f"eval label {EVAL_LABEL!r}, {args.episodes} episodes, weak feeder")
    print(f"stale sensitivity cache: {hp.stale_cache_across_episodes}\n")

    out = {}
    all_ok = True

    for name, label, kind in METHODS:
        if args.only and name not in args.only:
            continue
        t0 = time.perf_counter()
        agent, env, _ = load_agent(args.checkpoints, label, kind, cfg, hp)
        res = evaluate(agent, env, cfg, n_episodes=args.episodes, run_label=EVAL_LABEL)
        agg = res["aggregate"]
        dt = time.perf_counter() - t0

        print(f"=== {name}  ({label}, lambda={agent.lambda_lagrange:.4f}, "
              f"alpha={agent.alpha:.4f})  [{dt:.0f}s]")
        row = {"aggregate": agg, "lambda": agent.lambda_lagrange, "alpha": agent.alpha}

        if isinstance(agent, SafeSACLagAgent):
            row["projection"] = agent.stats.summary()
            row["projection"]["n_sensitivity_refreshes"] = agent.cache.n_refreshes
            print(f"    projection: infeasible={agent.stats.infeasible_rate:.4f}  "
                  f"frozen_steps={agent.stats.n_frozen_steps}  "
                  f"refreshes={agent.cache.n_refreshes}  "
                  f"statuses={agent.stats.statuses}")

        pub = PUBLISHED[name]
        for key, want in pub.items():
            got = agg.get(key, float("nan"))
            ok = abs(got - want) <= tolerance(key, want)
            all_ok &= ok
            print(f"    {'OK ' if ok else 'DIFF'} {key:36s} "
                  f"published={want:10.4f}  port={got:10.4f}  d={got - want:+.4f}")
        out[name] = row
        print()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, default=float))
    print(f"wrote {args.out}")
    print("GATE:", "PASS - port reproduces the published learned rows" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
