"""
Phase 1.3 — Gate B: does the projection need the learning?

Run as a notebook cell against the live training stack::

    exec(open("phase1_ablation.py").read())
    results = run_gate_b(globals())

The thesis isolates the projection's value *given* RL (SafeSAC vs SAC-Lag) but
never isolates RL's value *given* the projection. If ``droop + SOCP`` matches
SafeSAC, the safety layer is the contribution and the learning is not — which
is a publishable claim, but a different one, and better discovered now than in
review.

No training required: the two new arms wrap existing controllers in the
existing projector.
"""

from __future__ import annotations

import numpy as np

EVAL_LABEL = "phase1_gate_b"
N_EVAL = 25


class ProjectedAgent:
    """Wraps any agent so its action passes through the SOCP projection.

    Mirrors ``SafeSACLagAgent.select_action`` but with an arbitrary inner
    policy, so ``uncoordinated + SOCP`` and ``droop + SOCP`` see exactly the
    safety layer SafeSAC sees.
    """

    def __init__(self, inner, env_ref, ns, projector=None, sens_cache=None):
        self.inner = inner
        self.env_ref = env_ref
        self.ns = ns
        self.name = f"{getattr(inner, 'name', 'inner')}_socp"
        self.projector = projector or ns["SensitivityProjector"](
            n_stations=env_ref.n_stations,
            n_bus_canonical=ns["N_BUS_CANONICAL"])
        self.sens_cache = sens_cache or ns["SensitivityCache"]()
        self.n_infeasible = 0
        self.n_exceptions = 0
        self.n_calls = 0

    def select_action(self, obs, info=None, deterministic=True):
        raw = self.inner.select_action(obs, info=info, deterministic=deterministic)
        self.n_calls += 1
        try:
            if self.sens_cache.maybe_refresh(self.env_ref.nc,
                                             self.env_ref.current_step):
                self.projector.on_sensitivity_refresh()
            sm = self.sens_cache.get()
        except Exception:
            self.n_exceptions += 1
            return raw

        s_rated = self.ns["CFG"]("ev_station_S_rated_kva")
        n_st = self.env_ref.n_stations
        res = self.projector.project(
            raw[:n_st] * s_rated, raw[n_st:] * s_rated,
            self.env_ref._prev_p_kw, self.env_ref._prev_q_kvar, sm)
        if res.get("status") != "ok":
            self.n_infeasible += 1
        if res.get("all_frozen"):
            safe_p = np.zeros(n_st); safe_q = np.zeros(n_st)
        else:
            safe_p, safe_q = res["safe_p_kw"], res["safe_q_kvar"]
        return np.clip(np.concatenate([safe_p / s_rated, safe_q / s_rated]),
                       -1.0, 1.0).astype(np.float32)

    # pass-throughs so the evaluation harness can treat this like an agent
    def add_to_replay(self, *a, **k): pass
    def train_step(self): return None


def run_gate_b(ns: dict, grid: str = "weak", n_eval: int = N_EVAL) -> dict:
    """Evaluate the six arms on identical seeds and print the Gate B verdict."""
    EVChargingFeederEnv = ns["EVChargingFeederEnv"]
    evaluate_agent = ns["evaluate_agent"]
    StateNormalizer = ns["StateNormalizer"]

    norm = StateNormalizer(dim=EVChargingFeederEnv(config=grid, episode_days=1).obs_dim)
    env = EVChargingFeederEnv(config=grid, episode_days=1,
                              normalizer=norm, update_normalizer=False)

    arms = {}
    arms["uncoord"] = ns["UncoordinatedAgent"](env.obs_dim, env.action_dim)
    arms["droop"] = ns["DroopAgent"](env.obs_dim, env.action_dim)
    arms["uncoord_socp"] = ProjectedAgent(arms["uncoord"], env, ns)
    arms["droop_socp"] = ProjectedAgent(arms["droop"], env, ns)
    # Add the two trained agents from disk here, loaded exactly as Patch 7 does.

    out = {}
    for name, agent in arms.items():
        res = evaluate_agent(agent, env, n_episodes=n_eval,
                             run_label=EVAL_LABEL, verbose=False)
        out[name] = res
        extra = ""
        if isinstance(agent, ProjectedAgent) and agent.n_calls:
            extra = (f"   [SOCP infeasible {agent.n_infeasible / agent.n_calls * 100:.0f}%"
                     f", exceptions {agent.n_exceptions}]")
        print(f"{name:16s} viol={res['viol_rate_mean']:.4f}  "
              f"soc_met={res['soc_met_mean']:.4f}  "
              f"cost={res['net_cost_usd_mean']:8.2f}{extra}")

    print("\n" + "=" * 64)
    print("GATE B — does the projection need the learning?")
    print("=" * 64)
    ds = out.get("droop_socp")
    ss = out.get("safe_sac_weak")
    if ds and ss:
        d_viol = ds["viol_rate_mean"] - ss["viol_rate_mean"]
        d_soc = ds["soc_met_mean"] - ss["soc_met_mean"]
        print(f"  droop+SOCP vs SafeSAC: viol {d_viol:+.4f}, soc_met {d_soc:+.4f}")
        if abs(d_viol) < 0.01 and abs(d_soc) < 0.05:
            print("  -> MATCHED. The safety layer carries the benefit, not the "
                  "learning. Reframe the contribution around the projection and "
                  "show separately what foresight buys.")
        elif d_soc < -0.05:
            print("  -> RL AHEAD on service. Show explicitly that the gap is "
                  "foresight (TOU arbitrage, pre-peak charging), not noise.")
        else:
            print("  -> droop+SOCP ahead. Investigate before spending compute "
                  "on retraining.")
    else:
        print("  load the two trained agents into `arms` to complete the gate.")
    return out
