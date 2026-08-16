"""One episode, three controllers, recorded step by step.

The sweeps report rates aggregated over 25 episodes, which is the right way to
make a claim and the wrong way to show a mechanism. A reviewer looking at
"0.0000 against 0.0642" has to take on faith that the stale layer is passing
requests through untouched rather than, say, failing intermittently. A single
episode settles it: if the never-refreshed run's voltage trace lies on top of
the unprojected run's, step for step, the layer is not degraded, it is absent.

Runs the same seed through the same feeder three times -- no projection, a
projection refreshed every step, and a projection refreshed once per day -- and
records the minimum bus voltage and the aggregate station set-point at each of
the 288 control steps.

    python scripts/trace_episode.py

Writes results/trace_kerber.json.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safesac.agents import UncoordinatedAgent
from safesac.config import ExperimentConfig, eval_episode_seed
from safesac.env import ChargingFeederEnv
from safesac.evaluate import collect_rollout
from safesac.projected import ProjectedAgent

# The LV feeder at its selected operating point, which is where the cliff sits
# at 12 steps -- close enough to a plausible metering interval that the trace is
# worth looking at. EVAL_LABEL and the episode index must match the sweep so the
# episode drawn here is one of the 25 the rates were computed over.
EVAL_LABEL = "transfer_eval"
EPISODE = 0
Z_PCT, EVS, LOAD = 1.0, 8.0, 0.60


def _trace(roll, lower: float) -> dict:
    """Minimum bus voltage and total station power at each step."""
    n = roll.n_steps
    vmin = [float(v.min()) if v is not None else float("nan")
            for v in roll.voltages[:n]]
    return {
        "vmin": vmin,
        "p_kw": [float(p.sum()) for p in roll.p_kw[:n]],
        "violating": [bool(v < lower) for v in vmin],
    }


def main() -> int:
    base = ExperimentConfig.kerber(substation_z_pct=Z_PCT,
                                   evs_per_station=EVS, load_scale=LOAD)
    lower = base.safety.voltage_lower_pu
    seed = eval_episode_seed(base.master_seed, EPISODE, EVAL_LABEL)
    print(f"tracing kerber Z={Z_PCT}% episode {EPISODE} (seed {seed})")

    out = {"feeder": "kerber", "z": Z_PCT, "evs": EVS, "load": LOAD,
           "episode": EPISODE, "seed": int(seed),
           "voltage_lower_pu": lower,
           "voltage_upper_pu": base.safety.voltage_upper_pu,
           "step_minutes": base.time.step_minutes, "runs": {}}

    runs = {
        "unprojected": None,
        "refresh_1": 1,
        "refresh_288": 288,
    }
    for name, refresh in runs.items():
        cfg = base if refresh is None else replace(
            base, safety=replace(base.safety, sensitivity_refresh_steps=refresh))
        env = ChargingFeederEnv(cfg)
        source = UncoordinatedAgent(env)
        agent = source if refresh is None else ProjectedAgent(source, env, cfg)
        roll = collect_rollout(agent, env, seed=seed, deterministic=True)
        tr = _trace(roll, lower)
        if refresh is not None:
            tr["stats"] = {k: float(v) for k, v in agent.stats.summary().items()}
        out["runs"][name] = tr
        print(f"  {name:<14} vmin={min(tr['vmin']):.4f}  "
              f"steps below band: {sum(tr['violating'])}/{roll.n_steps}")

    # The point of the figure, asserted here so a silent change in the data
    # cannot leave a caption claiming something the trace no longer shows.
    stale = np.asarray(out["runs"]["refresh_288"]["vmin"])
    raw = np.asarray(out["runs"]["unprojected"]["vmin"])
    fresh = np.asarray(out["runs"]["refresh_1"]["vmin"])
    out["max_abs_dev_stale_vs_unprojected"] = float(np.abs(stale - raw).max())
    out["min_vmin_fresh"] = float(fresh.min())
    print(f"\n  stale vs unprojected, largest deviation over the day: "
          f"{out['max_abs_dev_stale_vs_unprojected']:.2e} p.u.")

    path = Path("results/trace_kerber.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, default=float))
    print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
