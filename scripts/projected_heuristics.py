"""Does the learned policy contribute anything the projection does not?

The thesis's ablation composes the projection only with the learned policy, so
it cannot separate "the safety layer works" from "the learned policy is good".
This runs the missing cell: the same projection applied to a *heuristic*
request, on the same eval seeds and the same metric code as the ablation.

    python scripts/projected_heuristics.py --episodes 25

It is a two-line experiment. A reviewer will run it. Better to run it first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from safesac.agents import DroopAgent, UncoordinatedAgent, ZeroAgent
from safesac.config import ExperimentConfig
from safesac.env import ChargingFeederEnv
from safesac.evaluate import attributable, evaluate
from safesac.projected import ProjectedAgent

EVAL_LABEL = "stage1_eval"   # identical to run_ablation.py -- paired seeds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=25)
    ap.add_argument("--variant", default="weak")
    ap.add_argument("--out", type=Path, default=Path("results/projected_heuristics.json"))
    args = ap.parse_args()

    cfg = ExperimentConfig.stage1(args.variant)
    print(f"projected heuristics | fingerprint {cfg.fingerprint()} | "
          f"{args.episodes} episodes | margin {cfg.safety.projection_margin_pu}\n")

    def build(name):
        env = ChargingFeederEnv(cfg)
        if name == "zero":
            return ZeroAgent(env), env
        if name == "uncoordinated":
            return UncoordinatedAgent(env), env
        if name == "droop":
            return DroopAgent(env), env
        if name == "uncoordinated+proj":
            return ProjectedAgent(UncoordinatedAgent(env), env, cfg), env
        if name == "droop+proj":
            return ProjectedAgent(DroopAgent(env), env, cfg), env
        raise KeyError(name)

    order = ["zero", "uncoordinated", "droop", "uncoordinated+proj", "droop+proj"]
    results, baseline_per_ep = {}, None

    print(f"{'method':<22}{'viol':>9}{'attr':>10}{'SoC met':>10}{'net cost':>11}"
          f"{'infeas':>9}{'ms/step':>9}")
    for name in order:
        agent, env = build(name)
        ev = evaluate(agent, env, cfg, n_episodes=args.episodes, run_label=EVAL_LABEL)
        agg = ev["aggregate"]
        if name == "zero":
            baseline_per_ep = ev["per_episode"]
        attr = attributable(ev["per_episode"], baseline_per_ep)
        row = {"aggregate": agg, "attributable": attr}
        if hasattr(agent, "stats"):
            row["projection"] = agent.stats.summary()
        results[name] = row
        infeas = row.get("projection", {}).get("infeasible_rate", float("nan"))
        print(f"{name:<22}{agg['voltage_violation_step_rate_mean']:>9.4f}"
              f"{attr['voltage_violation_step_rate_excess_mean']:>+10.4f}"
              f"{agg['frac_meeting_soc_target_mean']:>10.4f}"
              f"{agg['net_cost_usd_mean']:>11.2f}"
              f"{infeas:>9.4f}{agg['mean_step_time_ms_mean']:>9.2f}")

    # ---- the comparison that matters ------------------------------------
    abl = Path("results/ablation/ablation.json")
    if abl.exists():
        s = json.loads(abl.read_text())["summary"]
        print("\n" + "=" * 78)
        print("against the learned arms (3 seeds x 200 episodes, same eval seeds)")
        print("=" * 78)
        print(f"{'method':<22}{'viol':>9}{'SoC met':>10}{'net cost':>11}")
        for arm, lbl in (("no_projection", "SAC-Lag (learned)"),
                         ("projection", "SafeSAC (learned+proj)")):
            print(f"{lbl:<22}{s[arm]['viol'][0]:>9.4f}{s[arm]['soc'][0]:>10.4f}"
                  f"{s[arm]['cost'][0]:>11.2f}")
        up = results["uncoordinated+proj"]["aggregate"]
        learned = s["projection"]["soc"][0]
        ratio = up["frac_meeting_soc_target_mean"] / max(learned, 1e-9)
        print(f"\nuncoordinated+projection reaches SoC "
              f"{up['frac_meeting_soc_target_mean']:.4f} at violations "
              f"{up['voltage_violation_step_rate_mean']:.4f}")
        print(f"the learned projected policy reaches {learned:.4f} -- "
              f"a factor of {ratio:.1f}")
        results["verdict"] = {
            "uncoordinated_proj_soc": up["frac_meeting_soc_target_mean"],
            "uncoordinated_proj_viol": up["voltage_violation_step_rate_mean"],
            "learned_proj_soc": learned,
            "ratio": ratio,
        }

    # ---- the heuristic mixture frontier ---------------------------------
    # Any convex combination of two controllers is achievable by per-episode
    # randomisation, so the segment between them is a real baseline. If a
    # learned controller sits below it, a coin flip beats it.
    u = results["uncoordinated"]["aggregate"]
    d = results["droop"]["aggregate"]
    uv, us = u["voltage_violation_step_rate_mean"], u["frac_meeting_soc_target_mean"]
    dv, ds = d["voltage_violation_step_rate_mean"], d["frac_meeting_soc_target_mean"]
    print("\nheuristic mixture line (uncoordinated <-> droop), SoC at matched violations:")
    for name in order[3:]:
        a = results[name]["aggregate"]
        v, s_ = a["voltage_violation_step_rate_mean"], a["frac_meeting_soc_target_mean"]
        theta = 0.0 if uv <= dv else np.clip((v - dv) / (uv - dv), 0.0, 1.0)
        mix = ds + theta * (us - ds)
        print(f"  {name:<22} viol={v:.4f}  SoC={s_:.4f}  mixture={mix:.4f}  "
              f"{'DOMINATES' if s_ > mix else 'BEATEN BY'} the mixture")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, default=float))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
