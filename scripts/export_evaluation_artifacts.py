"""
Export the SafeSAC reference study artefacts into JSON the browser simulator can read.

Run this in the evaluation environment AFTER the definition cells have
executed and the four checkpoints are loaded. It writes into ./web_export/.

The script is deliberately defensive: it introspects for the objects it needs
and prints what it found, so a name that differs from the guess below can be
fixed in one place rather than debugged blind. Run `probe()` first.

What the simulator actually needs, in priority order:

  1. sensitivities.json  — THE critical one. Without it there is no physics.
  2. topology.json       — the 33-bus one-line diagram, for the map.
  3. baseline.json       — v0 voltage profile per step, both grids.
  4. episodes/*.json     — recorded per-step behaviour of each controller.
  5. results.json        — the Table 6.1 aggregates.
  6. actor.json          — optional stretch: run the policy live in-browser.
"""

import json
import os
from pathlib import Path

import numpy as np

OUT = Path("web_export")
OUT.mkdir(exist_ok=True)
(OUT / "episodes").mkdir(exist_ok=True)


def _jsonable(x):
    """NumPy and friends -> plain Python, so json.dump stops complaining."""
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, np.ndarray):
        return [_jsonable(v) for v in x.tolist()]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def write(name, payload):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(_jsonable(payload), f, indent=1)
    print(f"  wrote {path}  ({path.stat().st_size / 1024:.1f} KB)")


# ---------------------------------------------------------------------------
# 0. Probe — run this FIRST and read the output
# ---------------------------------------------------------------------------

def probe():
    """Report which expected globals exist, so the rest can be adapted."""
    wanted = [
        "CFG", "build_network", "NetworkContext",
        "compute_voltage_sensitivities", "SensitivityMatrices",
        "compute_grid_sensitivities", "GridSensitivities",
        "SensitivityProjector", "EVChargingFeederEnv",
        "sample_scenario", "Scenario", "run_pf",
        "evaluate_agent", "collect_episode_rollout", "_run_episode",
        "EV_STATION_NODE_NAMES", "PV_NODE_NAMES",
        "EV_MAX_CHARGE_KW", "EV_MAX_DISCHARGE_KW",
        "MASTER_SEED", "_load_trained",
        "SACLagAgent", "SafeSACLagAgent", "DroopAgent", "UncoordinatedAgent",
    ]
    g = globals()
    print("Present:")
    for w in wanted:
        mark = "ok " if w in g else "MISSING"
        print(f"  [{mark:7s}] {w}")
    print("\nAgent-like globals found:")
    for k, v in sorted(g.items()):
        if isinstance(v, type) and k.endswith("Agent"):
            print(f"  {k}")
    print("\nLoaded checkpoint-like globals:")
    for k, v in sorted(g.items()):
        if k.lower().startswith(("safesac", "sac_lag", "saclag", "agent")):
            print(f"  {k}: {type(v).__name__}")


# ---------------------------------------------------------------------------
# 1. Sensitivities — the one artefact the simulator cannot work without
# ---------------------------------------------------------------------------

def export_sensitivities(weak_ctx, strong_ctx):
    """
    Sp[b][i] = dV_b / dP_i  and  Sq[b][i] = dV_b / dQ_i
    for every bus b and every EV-station index i, on both networks.

    This is what turns the browser into a real power-flow simulator:
        v = v0 + Sp @ dp + Sq @ dq
    """
    out = {}
    for label, ctx in (("weak", weak_ctx), ("strong", strong_ctx)):
        s = compute_voltage_sensitivities(ctx)  # noqa: F821
        Sp = np.asarray(getattr(s, "dVdP", getattr(s, "Sp", None)), dtype=float)
        Sq = np.asarray(getattr(s, "dVdQ", getattr(s, "Sq", None)), dtype=float)
        if Sp is None or Sq is None:
            raise RuntimeError(
                f"Could not find dVdP/dVdQ on {type(s).__name__}; "
                f"attributes are {[a for a in dir(s) if not a.startswith('_')]}"
            )
        ratio = float(np.mean(np.abs(Sp)) / np.mean(np.abs(Sq)))
        out[label] = {
            "n_bus": int(Sp.shape[0]),
            "n_station": int(Sp.shape[1]),
            "dVdP": Sp,
            "dVdQ": Sq,
            # Gate 1 of the pre-registered protocol. Weak feeder should be ~1.271.
            "vp_dominance_ratio": ratio,
        }
        print(f"  {label}: Sp{Sp.shape} Sq{Sq.shape}  V-P dominance = {ratio:.3f}")
    write("sensitivities.json", out)


# ---------------------------------------------------------------------------
# 2. Topology — the map
# ---------------------------------------------------------------------------

def export_topology(weak_ctx, strong_ctx):
    """Bus list and line R/X for the one-line diagram."""
    out = {}
    for label, ctx in (("weak", weak_ctx), ("strong", strong_ctx)):
        net = getattr(ctx, "net", ctx)
        lines = []
        for _, r in net.line.iterrows():
            lines.append({
                "from": int(r["from_bus"]),
                "to": int(r["to_bus"]),
                "r_ohm": float(r["r_ohm_per_km"] * r["length_km"]),
                "x_ohm": float(r["x_ohm_per_km"] * r["length_km"]),
            })
        out[label] = {
            "n_bus": int(len(net.bus)),
            "vn_kv": float(net.bus.vn_kv.iloc[0]),
            "lines": lines,
            "station_buses": [int(b) for b in getattr(ctx, "ev_station_buses", [])],
            "pv_buses": [int(b) for b in getattr(ctx, "pv_buses", [])],
            "slack_bus": int(net.ext_grid.bus.iloc[0]),
        }
        print(f"  {label}: {out[label]['n_bus']} buses, {len(lines)} lines, "
              f"stations at {out[label]['station_buses']}")
    write("topology.json", out)


# ---------------------------------------------------------------------------
# 3. Baseline voltage profile per timestep
# ---------------------------------------------------------------------------

def export_baseline(env_weak, env_strong, n_steps=288):
    """
    v0[t][b] — the bus voltage at step t with the EV stations at zero, i.e. the
    background load/PV condition the learner acts on top of. The browser adds
    the station contribution with the sensitivity matrices.
    """
    out = {}
    for label, env in (("weak", env_weak), ("strong", env_strong)):
        obs, _ = env.reset(seed=MASTER_SEED)  # noqa: F821
        rows, load_mult, pv_kw, price = [], [], [], []
        for _ in range(n_steps):
            zero = np.zeros(env.action_space.shape, dtype=np.float32)
            obs, _, term, trunc, info = env.step(zero)
            v = info.get("bus_voltages", info.get("v_pu"))
            rows.append(np.asarray(v, dtype=float))
            load_mult.append(float(info.get("load_mult", np.nan)))
            pv_kw.append(float(info.get("pv_kw", np.nan)))
            price.append(float(info.get("price", np.nan)))
            if term or trunc:
                break
        out[label] = {
            "n_steps": len(rows),
            "v0": np.asarray(rows),
            "load_mult": load_mult,
            "pv_kw": pv_kw,
            "price_usd_per_kwh": price,
        }
        print(f"  {label}: {len(rows)} steps of baseline profile")
    write("baseline.json", out)


# ---------------------------------------------------------------------------
# 4. Recorded controller episodes — the ghost, and Act 3's reveal
# ---------------------------------------------------------------------------

def export_episode(name, agent, env, seed, n_steps=288):
    """
    One full episode of a controller's behaviour, recorded per step.

    `sac_lag_strong_xdeploy` is the important one: it is the controller that
    looks safest on the dashboard and has soc_met = 0.000 because it stopped
    serving vehicles. Act 3 is built on this file.
    """
    obs, _ = env.reset(seed=seed)
    steps = []
    for t in range(n_steps):
        act = agent.select_action(obs, deterministic=True)
        obs, rew, term, trunc, info = env.step(act)
        v = np.asarray(info.get("bus_voltages", info.get("v_pu")), dtype=float)
        steps.append({
            "t": t,
            "action_kw": np.asarray(info.get("station_p_kw", act), dtype=float),
            "v_min": float(v.min()),
            "v_min_bus": int(v.argmin()),
            "reward": float(rew),
            "cost": float(info.get("cost", 0.0)),
            "soc_mean": float(info.get("soc_mean", np.nan)),
            "violation": bool(info.get("violation", v.min() < 0.95)),
        })
        if term or trunc:
            break
    payload = {
        "name": name,
        "seed": int(seed),
        "n_steps": len(steps),
        "summary": {
            "soc_met": float(info.get("soc_met", np.nan)),
            "viol_rate": float(np.mean([s["violation"] for s in steps])),
            "net_cost": float(info.get("net_cost", np.nan)),
            "v_min": float(min(s["v_min"] for s in steps)),
        },
        "steps": steps,
    }
    write(f"episodes/{name}.json", payload)
    return payload


# ---------------------------------------------------------------------------
# 5. Projection probe — Table 5.3, for Act 2
# ---------------------------------------------------------------------------

def export_projection_probe(weak_ctx, strong_ctx, request_kw=-80.0):
    """
    The identical-request comparison. Reproduces Table 5.3: the same -80 kW V2G
    request curtailed to -54.13 kW at station 1 on the weak feeder, and passed
    essentially unaltered on the strong one.
    """
    out = {"request_kw": request_kw, "grids": {}}
    for label, ctx in (("weak", weak_ctx), ("strong", strong_ctx)):
        proj = SensitivityProjector(ctx)  # noqa: F821
        n = len(getattr(ctx, "ev_station_buses", [0, 0, 0, 0]))
        raw = np.full(n, request_kw, dtype=float)
        safe = np.asarray(proj.project(raw), dtype=float)
        out["grids"][label] = {
            "raw_kw": raw,
            "safe_kw": safe,
            "curtailment_kw": raw - safe,
        }
        print(f"  {label}: {np.round(safe, 2).tolist()}")
    write("projection_probe.json", out)


# ---------------------------------------------------------------------------
# 6. Aggregate results — Table 6.1
# ---------------------------------------------------------------------------

def export_results():
    """
    The headline table. Transcribed from the reference study so the simulator's Act 3
    leaderboard shows exactly the published numbers.
    """
    write("results.json", {
        "n_episodes": 25,
        "load_scale": 0.50,
        "voltage_band": [0.95, 1.05],
        "master_seed": 137710,
        "methods": [
            {"id": "uncoord", "label": "Uncoordinated",
             "viol_rate": 0.116, "viol_sd": 0.009, "v_min": 0.9383,
             "soc_met": 0.996, "soc_sd": 0.012, "net_cost": 230.7,
             "reward": -205.6, "v2g_util": 0.000},
            {"id": "droop", "label": "Droop (IEEE 1547)",
             "viol_rate": 0.052, "viol_sd": 0.009, "v_min": 0.9474,
             "soc_met": 0.325, "soc_sd": 0.113, "net_cost": 66.3,
             "reward": -733.2, "v2g_util": 0.097},
            {"id": "sac_lag_weak", "label": "SAC-Lag (weak)",
             "viol_rate": 0.090, "viol_sd": 0.024, "v_min": 0.9425,
             "soc_met": 0.277, "soc_sd": 0.117, "net_cost": 104.3,
             "reward": -923.5, "v2g_util": 0.176},
            {"id": "safe_sac_weak", "label": "SafeSAC (weak)",
             "viol_rate": 0.091, "viol_sd": 0.002, "v_min": 0.9438,
             "soc_met": 0.569, "soc_sd": 0.164, "net_cost": 125.9,
             "reward": -505.2, "v2g_util": 0.103},
            {"id": "sac_lag_xdeploy", "label": "SAC-Lag (strong to weak)",
             "viol_rate": 0.015, "viol_sd": 0.014, "v_min": 0.9492,
             "soc_met": 0.000, "soc_sd": 0.000, "net_cost": -38.2,
             "reward": -1898.7, "v2g_util": 0.105},
            {"id": "safe_sac_xdeploy", "label": "SafeSAC (strong to weak)",
             "viol_rate": 0.106, "viol_sd": 0.003, "v_min": 0.9438,
             "soc_met": 0.447, "soc_sd": 0.074, "net_cost": 69.7,
             "reward": -1024.1, "v2g_util": 0.048},
        ],
        "paired_tests": [
            {"metric": "viol_rate", "delta": 0.0008, "ci": [-0.008, 0.011],
             "p_t": 0.86, "p_wilcoxon": 0.58, "cohens_d": 0.06},
            {"metric": "soc_met", "delta": 0.292, "ci": [0.232, 0.352],
             "p_t": 2.2e-9, "p_wilcoxon": 6.0e-8, "cohens_d": 2.04},
            {"metric": "net_cost", "delta": 21.6, "ci": [9.5, 34.0],
             "p_t": 0.0019, "p_wilcoxon": 0.0025, "cohens_d": 0.89},
        ],
    })


# ---------------------------------------------------------------------------
# 7. Optional stretch — run the policy live in the browser
# ---------------------------------------------------------------------------

def export_actor(agent, name="safe_sac_weak"):
    """
    The actor is a small MLP. Exporting its weights lets the browser run the
    real policy live instead of replaying a recording — a much stronger claim
    on slide 2. Only worth doing once everything else is finished.
    """
    actor = agent.actor
    layers = []
    for mod in actor.modules():
        if hasattr(mod, "weight") and hasattr(mod, "bias") and mod.bias is not None:
            layers.append({
                "W": mod.weight.detach().cpu().numpy(),
                "b": mod.bias.detach().cpu().numpy(),
            })
    payload = {"name": name, "layers": layers}
    norm = getattr(agent, "normalizer", None)
    if norm is not None:
        payload["obs_mean"] = np.asarray(getattr(norm, "mean", []), dtype=float)
        payload["obs_std"] = np.asarray(getattr(norm, "std", []), dtype=float)
    write(f"{name}_actor.json", payload)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def export_all(weak_ctx, strong_ctx, env_weak, env_strong, agents):
    """
    agents: dict of {export_name: (agent, env, seed)}. Use the eval seeds from
    the paired evaluation so the recorded episodes match the reported numbers.
    """
    print("1. sensitivities");     export_sensitivities(weak_ctx, strong_ctx)
    print("2. topology");          export_topology(weak_ctx, strong_ctx)
    print("3. baseline");          export_baseline(env_weak, env_strong)
    print("4. projection probe");  export_projection_probe(weak_ctx, strong_ctx)
    print("5. results");           export_results()
    print("6. episodes")
    for name, (agent, env, seed) in agents.items():
        export_episode(name, agent, env, seed)
    print(f"\nDone. Zip {OUT}/ and send it over.")
    os.system(f"cd {OUT.parent} && zip -qr web_export.zip {OUT.name}")


if __name__ == "__main__":
    print(__doc__)
    print("Run probe() in the source evaluation first, then export_all(...).")
