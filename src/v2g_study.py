"""
Study driver: paired scenarios, controller rollouts, and the five experiments.

Two structural rules enforced here:

1. ONE LIVE CIRCUIT. Feeder.__init__ issues Clear/Compile, which resets the global
   OpenDSS state and silently invalidates any previously built Feeder. So each
   experiment builds exactly one V2GDayEnv, trains on it, and evaluates every
   controller through env.fd / env.fleets. Never hold two feeders at once.

2. COMMON RANDOM NUMBERS. Every controller in a comparison is evaluated on the
   IDENTICAL scenario list -- same availability realisation, same initial SOC, same
   peak. Differences are then paired, which removes scenario noise from the
   comparison instead of leaving it in the error bars.
"""
import time
from collections import namedtuple

import numpy as np
import torch
torch.set_num_threads(4)

from v2g_sys import CFG, droop_pq, lam_profile, draw_availability
from v2g_env2 import V2GDayEnv
import v2g_metrics as M
from stable_baselines3 import SAC

Scenario = namedtuple("Scenario", "peak avail_day soc_init")


def make_scenarios(n, peak, seed0=0, n_ev=None, soc_init=None):
    """n paired scenarios at a fixed load peak."""
    n_ev = n_ev or CFG["n_ev"]
    out = []
    for k in range(n):
        rng = np.random.default_rng(1000 + seed0 + k)
        out.append(Scenario(peak=peak,
                            avail_day=draw_availability(rng, n_ev),
                            soc_init=soc_init if soc_init is not None else CFG["soc_init"]))
    return out


# --------------------------------------------------------------------------- #
# Controller rollouts -- all driven through the env's single live feeder
# --------------------------------------------------------------------------- #
def _reset_fleets(env, scen):
    for b in env.hubs:
        env.fleets[b].reset(n_avail_day=scen.avail_day, soc_init=scen.soc_init)


def _log(env, rec, h, disch, rho, n, thru_cum):
    """thru_cum is passed explicitly: when the fleet model is disabled the fleet objects
    never accumulate, so reading fleet.throughput would silently report zero energy."""
    soc = float(np.mean([env.fleets[b].soc for b in env.hubs]))
    M.log_hour(rec, h, env.fd, disch, soc, n, rho, thru_cum, env.fd.tap_positions())


def droop_equilibrium(env, h, ev_constrained, damp=0.3, iters=200, tol=1e-2,
                      max_backoff=4, backoff=True):
    """Damped Jacobi iteration to the droop fixed point, with a real convergence test.

    A FIXED ITERATION COUNT HIDES NON-CONVERGENCE. At damp=0.6 the five-hub system does not
    settle: it enters a period-2 limit cycle -- total active power alternating 1298 / 630 kW
    at mild-load hour 18 -- so "iters=25" returns whichever branch iteration 25 lands on
    rather than an equilibrium, and the answer flips with the parity of the iteration count.
    Measured behaviour at that hour: damp 0.2 and 0.3 converge to 922 kW; 0.5 oscillates
    1059/801; 0.6 oscillates 1298/630; 0.8 oscillates 1978/-110.

    So: iterate to a residual test rather than a fixed count, and if the residual stalls,
    halve the damping and restart. Returns (setpoints, converged, iters_used, damp_used).

    backoff=False disables the retry, so `iters` means EXACTLY that many iterations at the
    given damping. E9 needs that: with backoff on, a small `iters` silently becomes four
    restarts at successively halved damping, which is not "a partially converged loop" and
    made the sweep read non-monotone (iters=25 landing below iters=10).
    """
    cfg = env.cfg
    for _ in range(max_backoff if backoff else 1):
        sp = {b: (0.0, 0.0) for b in env.hubs}
        for k in range(iters):
            delta = 0.0
            for b in env.hubs:
                v = env.fd.hub_vpu(b)
                p, q = droop_pq(v, cfg["P_rated"], cfg["Q_rated"])
                p0, q0 = sp[b]
                pn, qn = (1 - damp) * p0 + damp * p, (1 - damp) * q0 + damp * q
                delta = max(delta, abs(pn - p0), abs(qn - q0))
                sp[b] = (pn, qn)
            for b, (p, q) in sp.items():
                if ev_constrained:
                    p, q, _, _ = env.fleets[b].apply(p, q, h, commit=False)
                env.fd.set_hub(b, p, q)
            env.fd.solve()
            if delta < tol:
                return sp, True, k + 1, damp
        damp *= 0.5                      # stalled -> back off and retry
    return sp, False, iters, damp


def rollout_static(env, scen, controller="droop", ev_constrained=True, damp=0.3, iters=200,
                   backoff=True):
    """controller in {'baseline','droop'}. Returns summarize() dict."""
    cfg = env.cfg
    lam = lam_profile(scen.peak)
    _reset_fleets(env, scen)
    rec = M.hourly_record()
    thru_cum = 0.0
    n_unconv = 0
    for h in env.hours:
        env.fd.set_load(lam[h]); env.fd.zero_hubs(); env.fd.solve()
        disch, rho, n = 0.0, 1.0, np.nan

        if controller == "baseline":
            env.fd.solve()

        else:  # closed-loop droop: fixed point driven to a residual test, not a fixed count
            sp, conv, _, _ = droop_equilibrium(env, h, ev_constrained,
                                               damp=damp, iters=iters, backoff=backoff)
            n_unconv += (not conv)
            for b, (p, q) in sp.items():
                if ev_constrained:
                    p, q, rho, n = env.fleets[b].apply(p, q, h, commit=True)
                else:
                    thru_cum += abs(p) / cfg["eta_inv"]
                env.fd.set_hub(b, p, q)
                disch += max(0.0, p)
            env.fd.solve()

        if ev_constrained:
            thru_cum = float(sum(env.fleets[b].throughput for b in env.hubs))
        _log(env, rec, h, disch, rho, n, thru_cum)

    socs = env.fleets[env.hubs[0]].soc_series
    s = M.summarize(rec, socs)
    # Surfaced, not swallowed: a droop row computed from a non-converged fixed point is not
    # an equilibrium and must not be reported as one.
    s["DroopUnconv"] = int(n_unconv)
    return s, rec


def rollout_policy(env, policy, scen, ev_constrained=True):
    """Deterministic policy rollout through the env itself (guarantees obs consistency)."""
    saved, saved_iid = env.ev_in_loop, env.iid_lambda
    env.ev_in_loop = ev_constrained
    env.iid_lambda = False        # evaluation always uses the real daily load profile
    obs, _ = env.reset(options=dict(peak=scen.peak, avail_day=scen.avail_day,
                                    soc_init=scen.soc_init))
    rec = M.hourly_record()
    thru_cum = 0.0
    for t, h in enumerate(env.hours):
        act, _ = policy.predict(obs, deterministic=True)
        obs, _, done, _, info = env.step(act)
        thru_cum += info["thru"]
        _log(env, rec, h, info["p_sup"], 1.0, np.nan, thru_cum)
        if done:
            break
    env.ev_in_loop, env.iid_lambda = saved, saved_iid
    socs = env.fleets[env.hubs[0]].soc_series
    return M.summarize(rec, socs), rec


def rollout_zero(env, scen, ev_constrained=True):
    """a=0 in residual mode == open-loop droop; the per-step floor sanity check."""
    class _Zero:
        def predict(self, obs, deterministic=True):
            return np.zeros(env.action_space.shape, dtype=np.float32), None
    return rollout_policy(env, _Zero(), scen, ev_constrained)


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #
def make_sac(env, seed=0):
    """The single definition of the agent's hyperparameters.

    E13 needs to build the same agent train_on builds, otherwise its learning curve measures
    a different agent than the fixed-budget experiments and cannot speak for them. Keeping
    one constructor makes that structural rather than a thing to remember.
    """
    return SAC("MlpPolicy", env, learning_rate=3e-4, batch_size=256, gamma=0.99,
               buffer_size=200_000, learning_starts=1000, tau=0.005,
               policy_kwargs=dict(net_arch=[256, 256]), device="cpu",
               seed=seed, verbose=0)


def train_on(env, steps, seed=0, chunk=5000, label=""):
    m = make_sac(env, seed)
    t0, done = time.time(), 0
    while done < steps:
        n = min(chunk, steps - done)
        m.learn(total_timesteps=n, reset_num_timesteps=(done == 0), progress_bar=False)
        done += n
        print(f"      [{label}] {done}/{steps}  {time.time()-t0:.0f}s", flush=True)
    return m


def build_env(hub_buses, mode="residual", w_deg=0.0, control_mode="OFF",
              peak_range=(1.2, 3.3), reward_on="bus", iid_lambda=False, seed=0):
    return V2GDayEnv(hub_buses, peak_range=peak_range, mode=mode, w_deg=w_deg,
                     control_mode=control_mode, reward_on=reward_on,
                     iid_lambda=iid_lambda, seed=seed)


def build_paper_env(hub_buses, control_mode="OFF", seed=0):
    """The paper's Phase-1 training setup: direct action, i.i.d. load multiplier per step,
    no fleet in the loop. Used as the reproduction baseline and as E4's comparison arm."""
    env = build_env(hub_buses, mode="direct", w_deg=0.0, control_mode=control_mode,
                    peak_range=(0.1, 4.0), iid_lambda=True, seed=seed)
    env.ev_in_loop = False
    return env


# --------------------------------------------------------------------------- #
# E0 -- fidelity calibration
# --------------------------------------------------------------------------- #
def E0_calibration(n_scen=3):
    """Which (ControlMode, droop saturation) reproduces the paper's baseline fingerprint?

    Paper Table I baseline: feeder-mean Min = 0.907 (mild) / 0.807 (aggressive),
    violation hours (mean metric) = 13 / 17.
    """
    target = {"mild": dict(VMin=0.907, ViolMean=13),
              "aggr": dict(VMin=0.807, ViolMean=17)}
    rows = []
    for cm in ["OFF", "STATIC"]:
        env = build_env(CFG["hub_bus_single"], control_mode=cm)
        for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
            scens = make_scenarios(n_scen, peak, seed0=0)
            rs = [rollout_static(env, s, "baseline")[0] for s in scens]
            agg = M.aggregate(rs, ["VMean", "VMin", "ViolMean", "ViolBus", "ViolPh",
                                   "IntViol", "VphMax"])
            rows.append([cm, tag,
                         f"{agg['VMean']['mean']:.3f}",
                         f"{agg['VMin']['mean']:.3f}",
                         f"{agg['ViolMean']['mean']:.1f}",
                         f"{agg['ViolBus']['mean']:.1f}",
                         f"{agg['ViolPh']['mean']:.1f}",
                         f"{agg['IntViol']['mean']:.2f}",
                         f"{target[tag]['VMin']:.3f} / {target[tag]['ViolMean']}"])
        del env
    M.fmt_table("E0  Baseline fingerprint vs paper Table I (no V2G)",
                ["ControlMode", "load", "VMean", "VMin", "ViolMean",
                 "ViolBus", "ViolPh", "IntViol", "paper VMin/Viol"], rows)
    print("\n  Pick the ControlMode whose (VMin, ViolMean) is closest to the paper column.")
    print("  ViolBus / ViolPh / IntViol show how much the mean metric hides.")
    return rows


# --------------------------------------------------------------------------- #
# E1 -- reproduction of their Tables I and II
# --------------------------------------------------------------------------- #
def E1_reproduction(control_mode="OFF", steps=20000, n_scen=5, seed=0):
    """Their table structure, with our added metric columns."""
    out = {}
    for scope, hubs in [("single", CFG["hub_bus_single"]),
                        ("multi", CFG["hub_buses_multi"])]:
        # paper-style agent: direct action, i.i.d. lambda, no fleet in training (Phase 1)
        env = build_paper_env(hubs, control_mode=control_mode, seed=seed)
        print(f"\n  [E1/{scope}] training paper-style agent (direct, i.i.d. lambda, no fleet)")
        pol = train_on(env, steps, seed=seed, label=f"E1-{scope}")
        rows = []
        for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
            scens = make_scenarios(n_scen, peak, seed0=0)
            cases = [
                ("Baseline",        lambda s: rollout_static(env, s, "baseline")[0]),
                ("RL (no EV)",      lambda s: rollout_policy(env, pol, s, False)[0]),
                ("Droop (no EV)",   lambda s: rollout_static(env, s, "droop", False)[0]),
                ("RL (EV-constr)",  lambda s: rollout_policy(env, pol, s, True)[0]),
                ("Droop (EV-con.)", lambda s: rollout_static(env, s, "droop", True)[0]),
            ]
            for name, fn in cases:
                rs = [fn(s) for s in scens]
                a = M.aggregate(rs)
                rows.append([f"{tag}/{name}",
                             f"{a['VMean']['mean']:.3f}", f"{a['VMin']['mean']:.3f}",
                             f"{a['VphMax']['mean']:.3f}",
                             f"{a['ViolMean']['mean']:.1f}", f"{a['ViolBus']['mean']:.1f}",
                             f"{a['ViolPh']['mean']:.1f}", f"{a['ViolHi']['mean']:.1f}",
                             f"{a['IntViol']['mean']:.2f}",
                             f"{a['Thru']['mean']:.0f}", f"{a['SOCend']['mean']:.3f}"])
                out[f"{scope}/{tag}/{name}"] = rs
        M.fmt_table(f"E1  {scope}-hub reproduction  (ControlMode={control_mode}, {n_scen} paired scenarios)",
                    ["case", "VMean", "VMin", "VphMax", "ViolMean", "ViolBus",
                     "ViolPh", "ViolHi", "IntViol", "Thru", "SOCend"], rows)
        del env, pol
    return out


# --------------------------------------------------------------------------- #
# E2 (C1) -- multi-hub WITH realistic fleet constraints
# --------------------------------------------------------------------------- #
def E2_multihub_constrained(control_mode="OFF", steps=20000, n_scen=5, seeds=(0, 1, 2)):
    """Their explicitly untested case: multi-hub coordination under 45-85% availability."""
    out = {}
    for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
        scens = make_scenarios(n_scen, peak, seed0=0)
        rows, store = [], {}
        # controllers that need no training
        env = build_env(CFG["hub_buses_multi"], mode="residual", w_deg=0.0,
                        control_mode=control_mode, peak_range=(peak * 0.8, peak * 1.2))
        store["Baseline"] = [rollout_static(env, s, "baseline")[0] for s in scens]
        store["Droop"] = [rollout_static(env, s, "droop", True)[0] for s in scens]
        store["Droop (unconstr)"] = [rollout_static(env, s, "droop", False)[0] for s in scens]
        store["a=0 floor"] = [rollout_zero(env, s, True)[0] for s in scens]
        # trained closed-loop agent, one per seed, evaluated on the same scenarios
        rl_rows = []
        for sd in seeds:
            print(f"\n  [E2/{tag}] training closed-loop agent seed={sd}")
            pol = train_on(env, steps, seed=sd, label=f"E2-{tag}-s{sd}")
            rl_rows.append([rollout_policy(env, pol, s, True)[0] for s in scens])
            del pol
        store["RL closed-loop"] = [r for rs in rl_rows for r in rs]
        for name, rs in store.items():
            a = M.aggregate(rs)
            rows.append([name,
                         f"{a['VMean']['mean']:.3f}", f"{a['VMin']['mean']:.3f}",
                         f"{a['VphMax']['mean']:.3f}",
                         f"{a['ViolMean']['mean']:.1f}", f"{a['ViolBus']['mean']:.1f}",
                         f"{a['ViolPh']['mean']:.1f}", f"{a['ViolHi']['mean']:.1f}",
                         f"{a['IntViol']['mean']:.2f}±{a['IntViol']['ci95']:.2f}",
                         f"{a['Thru']['mean']:.0f}", f"{a['SOCend']['mean']:.3f}"])
        M.fmt_table(f"E2  multi-hub, EV-CONSTRAINED  ({tag}, {n_scen} paired scenarios x {len(seeds)} seeds)",
                    ["controller", "VMean", "VMin", "VphMax", "ViolMean", "ViolBus",
                     "ViolPh", "ViolHi", "IntViol(±ci)", "Thru", "SOCend"], rows)
        # paired deltas vs droop, the statistically meaningful comparison
        for key in ["IntViol", "ViolBus", "Thru"]:
            d = M.paired_delta(store["RL closed-loop"][:n_scen], store["Droop"], key)
            print(f"    paired RL-Droop  {key:8s}: {d['mean']:+.2f} ± {d['ci95']:.2f} "
                  f"(RL better in {d['a_better']}/{d['n']}, ties {d['ties']})")
        out[tag] = store
        del env
    return out


# --------------------------------------------------------------------------- #
# E3 (C2) -- degradation-weight sweep -> violation/wear frontier
# --------------------------------------------------------------------------- #
def E3_degradation_frontier(peak, weights=(0.0, 1.0, 3.0, 10.0, 30.0, 100.0),
                            control_mode="OFF", steps=20000, n_scen=5, seed=0,
                            hubs=None):
    """Trace the trade-off. Droop is plotted as a POINT on this frontier, not a rival."""
    hubs = hubs or CFG["hub_buses_multi"]
    scens = make_scenarios(n_scen, peak, seed0=0)
    pts, rows = [], []

    env0 = build_env(hubs, mode="residual", w_deg=0.0, control_mode=control_mode,
                     peak_range=(peak * 0.8, peak * 1.2))
    dr = [rollout_static(env0, s, "droop", True)[0] for s in scens]
    a = M.aggregate(dr)
    rows.append(["droop (reference)", "-",
                 f"{a['IntViol']['mean']:.2f}", f"{a['IntHi']['mean']:.2f}",
                 f"{a['Thru']['mean']:.0f}",
                 f"{a['ViolBus']['mean']:.1f}", f"{a['VphMax']['mean']:.3f}",
                 f"{a['SOCend']['mean']:.3f}", f"{a['MaxDoD']['mean']:.3f}"])
    pts.append(dict(w="droop", IntViol=a["IntViol"]["mean"], Thru=a["Thru"]["mean"],
                    ViolBus=a["ViolBus"]["mean"]))
    del env0

    for w in weights:
        env = build_env(hubs, mode="residual", w_deg=w, control_mode=control_mode,
                        peak_range=(peak * 0.8, peak * 1.2))
        print(f"\n  [E3] training w_deg={w}")
        pol = train_on(env, steps, seed=seed, label=f"E3-w{w}")
        rs = [rollout_policy(env, pol, s, True)[0] for s in scens]
        a = M.aggregate(rs)
        rows.append([f"RL w_deg={w:g}", f"{w:g}",
                     f"{a['IntViol']['mean']:.2f}", f"{a['IntHi']['mean']:.2f}",
                     f"{a['Thru']['mean']:.0f}",
                     f"{a['ViolBus']['mean']:.1f}", f"{a['VphMax']['mean']:.3f}",
                     f"{a['SOCend']['mean']:.3f}", f"{a['MaxDoD']['mean']:.3f}"])
        pts.append(dict(w=w, IntViol=a["IntViol"]["mean"], Thru=a["Thru"]["mean"],
                        ViolBus=a["ViolBus"]["mean"]))
        del env, pol

    M.fmt_table(f"E3  violation / wear frontier  (peak={peak}, {n_scen} paired scenarios)",
                ["controller", "w_deg", "IntViol", "IntHi", "Thru(kWh)", "ViolBus",
                 "VphMax", "SOCend", "MaxDoD"], rows)
    print("\n  Read it as a frontier: IntViol should rise as Thru falls. Where droop sits")
    print("  relative to the RL frontier is the result -- above, on, or below it.")
    return pts


# --------------------------------------------------------------------------- #
# E4 (C3) -- the multi-hub aggressive stress case (their droop 2 vs RL 15)
# --------------------------------------------------------------------------- #
def E4_stress(control_mode="OFF", steps=20000, n_scen=5, seeds=(0, 1, 2)):
    """Does day-structured, fleet-in-loop training change the aggressive-case gap?

    Also runs the paper-style agent (i.i.d. load multiplier, no fleet in training) on
    the same scenarios, so the two training regimes are compared directly.
    """
    peak = CFG["peak_aggr"]
    scens = make_scenarios(n_scen, peak, seed0=0)
    store, rows = {}, []

    env = build_env(CFG["hub_buses_multi"], mode="residual", w_deg=0.0,
                    control_mode=control_mode, peak_range=(peak * 0.8, peak * 1.2))
    store["Droop"] = [rollout_static(env, s, "droop", True)[0] for s in scens]
    store["Droop (unconstr)"] = [rollout_static(env, s, "droop", False)[0] for s in scens]
    for sd in seeds:
        print(f"\n  [E4] day-structured closed-loop agent seed={sd}")
        pol = train_on(env, steps, seed=sd, label=f"E4-day-s{sd}")
        store.setdefault("RL day-structured", []).extend(
            [rollout_policy(env, pol, s, True)[0] for s in scens])
        del pol
    del env

    env2 = build_paper_env(CFG["hub_buses_multi"], control_mode=control_mode)
    for sd in seeds:
        print(f"\n  [E4] paper-style agent (i.i.d. lambda, no fleet) seed={sd}")
        pol = train_on(env2, steps, seed=sd, label=f"E4-iid-s{sd}")
        store.setdefault("RL paper-style", []).extend(
            [rollout_policy(env2, pol, s, True)[0] for s in scens])
        del pol
    del env2

    for name, rs in store.items():
        a = M.aggregate(rs)
        rows.append([name,
                     f"{a['VMean']['mean']:.3f}", f"{a['VMin']['mean']:.3f}",
                     f"{a['VphMax']['mean']:.3f}",
                     f"{a['ViolMean']['mean']:.1f}", f"{a['ViolBus']['mean']:.1f}",
                     f"{a['ViolPh']['mean']:.1f}", f"{a['ViolHi']['mean']:.1f}",
                     f"{a['IntViol']['mean']:.2f}±{a['IntViol']['ci95']:.2f}",
                     f"{a['Thru']['mean']:.0f}"])
    M.fmt_table(f"E4  multi-hub AGGRESSIVE stress  ({n_scen} paired scenarios x {len(seeds)} seeds)",
                ["controller", "VMean", "VMin", "VphMax", "ViolMean", "ViolBus",
                 "ViolPh", "ViolHi", "IntViol(±ci)", "Thru"], rows)
    return store


# --------------------------------------------------------------------------- #
# E12 -- safety projection: does the gap survive once the agent stops overvolting?
# --------------------------------------------------------------------------- #
def _bisect_max_feasible(feas, iters=18):
    """Largest lam in [0,1] with feas(lam) true. ASSUMES feas(0) is true.

    Assumes monotonicity in lam -- less injection, lower voltage. That holds on this feeder
    over the range we use, but the guarantee is only that the returned point IS feasible
    (it is verified before return by the caller), not that it is the largest such point.
    """
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if feas(mid):
            lo = mid
        else:
            hi = mid
    return lo


def make_safety_filter(mode="scale", tol=1e-3, iters=18):
    """Project commanded setpoints onto the OVERVOLTAGE-feasible set (all phases <= v_max).

    A projection layer of this kind is standard practice in learning-based Volt-VAR control
    (SAVER; model-augmented safe Volt-VAR; safety-constrained MARL), so the reviewer question
    "why is there no safety layer" has to be answered. Because IntViol is two-sided, part of
    any RL penalty could be overvoltage rather than poor allocation, and only measuring the
    projection separates the two.

    MEASURED RESULT: in this study the projection is a NO-OP wherever the agent is trained on
    the day with the fleet in the loop. E12 gives IntHi 0.00 and VphMax 1.050 for the
    unprojected direct-action agent at both load levels, matching E2's residual agent. The
    feasibility test below reads the COMMANDED setpoints, before EVFleet.apply clips them to
    the available SOC and connected vehicles, so the filter can fire on a command the fleet
    was never going to deliver -- which is exactly what the small throughput deltas show
    (aggressive: 2262 kWh raw vs 2223 shed_q, IntViol 169.82 vs 169.19). The reading is that
    the fleet ENERGY constraint binds harder than the voltage constraint, so there is nothing
    left for a voltage projection to do. Overvoltage in this study tracks the TRAINING REGIME,
    not the action mode: paper-style training (i.i.d. lambda, no fleet in the loop) exceeds
    1.05 in every configuration tested, reaching 1.229.

    modes
      scale   : reduce P and Q together along the commanded ray. The plainest projection.
      shed_q  : reduce REACTIVE power first, and touch active power only if shedding all Q
                is still not enough. Motivated by our own E7 result -- at matched apparent
                power Q buys 1.25-1.49x LESS voltage than P while costing the same stored
                energy, so reactive is the right thing to give up first.
    """
    def _filter(env, h, raw):
        vmax = env.cfg["v_max"]

        def feas(sp, sq):
            for b, (p, q) in raw.items():
                env.fd.set_hub(b, p * sp, q * sq)
            if not env.fd.solve():
                return False
            return float(env.fd.phase_vpu().max()) <= vmax + tol

        if feas(1.0, 1.0):
            return raw                                   # nothing to project

        if mode == "shed_q":
            if feas(1.0, 0.0):                           # shedding Q alone is enough
                lam = _bisect_max_feasible(lambda l: feas(1.0, l), iters)
                out = {b: (p, q * lam) for b, (p, q) in raw.items()}
                return out if feas(1.0, lam) else {b: (p, 0.0) for b, (p, q) in raw.items()}
            if feas(0.0, 0.0):                           # Q gone, now scale P
                lam = _bisect_max_feasible(lambda l: feas(l, 0.0), iters)
                if feas(lam, 0.0):
                    return {b: (p * lam, 0.0) for b, (p, q) in raw.items()}
            return {b: (0.0, 0.0) for b in raw}

        if not feas(0.0, 0.0):
            # Zero injection is already over the limit, so the overvoltage is not ours to
            # fix -- back all the way off rather than pretending a projection exists.
            return {b: (0.0, 0.0) for b in raw}
        lam = _bisect_max_feasible(lambda l: feas(l, l), iters)
        return ({b: (p * lam, q * lam) for b, (p, q) in raw.items()} if feas(lam, lam)
                else {b: (0.0, 0.0) for b in raw})

    return _filter


def rollout_policy_safe(env, policy, scen, mode=None, ev_constrained=True):
    """rollout_policy with a safety projection inserted before the fleet commits."""
    saved = env.safety_filter
    env.safety_filter = make_safety_filter(mode) if mode else None
    try:
        return rollout_policy(env, policy, scen, ev_constrained)
    finally:
        env.safety_filter = saved


def E12_safety_projection(control_mode="OFF", steps=20000, n_scen=5, seeds=(0, 1, 2),
                          residual_ref=False):
    """Does the overvoltage need a projection layer, or does the action space already fix it?

    RETARGETED AFTER THE FIRST PRODUCTION RUN. This was written to project the overvoltage
    out of the residual-mode agent, but that run showed the residual agent never breaks the
    bound under the fleet constraint: E2 reports VphMax 1.050 and ViolHi 0.0 at both load
    levels. Projecting there is a no-op and answers nothing.

    The overvoltage lives in the paper's DIRECT action (Eq. 7), where the same fleet-
    constrained multi-hub case reaches VphMax 1.151 mild / 1.077 aggressive (E1). So the
    comparison that carries information is:

        direct raw            -- the paper's formulation, which violates the upper bound
        direct + projection   -- the standard fix from the safe-RL Volt-VAR literature
        residual              -- our droop prior, no projection layer at all

    If residual matches projected-direct on IntHi, the droop prior is doing the safety
    layer's job inside the action space, at no inference cost and with nothing to tune.

    residual_ref=False by default because E2 ALREADY TRAINED THAT ARM. Its "RL closed-loop"
    row uses the same env (residual, w_deg 0, peak_range +-20%), the same scenarios
    (make_scenarios(n_scen, peak, seed0=0)), the same seeds and the same step count, and
    train_on seeds only from `seed` -- `label` is print-only. Retraining it here would
    reproduce E2 bit for bit and double this experiment's runtime, so read the reference
    off E2 instead. Set True only to re-derive it inside one table.
    """
    out, rows = {}, []
    arms = ((None, "direct raw"), ("scale", "direct + proj (scale)"),
            ("shed_q", "direct + proj (shed Q)"))
    for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
        scens = make_scenarios(n_scen, peak, seed0=0)
        pr = (peak * 0.8, peak * 1.2)
        env = build_env(CFG["hub_buses_multi"], mode="direct", w_deg=0.0,
                        control_mode=control_mode, peak_range=pr)
        env_res = (build_env(CFG["hub_buses_multi"], mode="residual", w_deg=0.0,
                             control_mode=control_mode, peak_range=pr)
                   if residual_ref else None)
        store = {"Droop": [rollout_static(env, s, "droop", True)[0] for s in scens]}
        for _, name in arms:
            store[name] = []
        if residual_ref:
            store["residual (no proj)"] = []
        for sd in seeds:
            print(f"\n  [E12/{tag}] training direct-action seed={sd}")
            pol = train_on(env, steps, seed=sd, label=f"E12-{tag}-dir-s{sd}")
            for mode, name in arms:
                store[name] += [rollout_policy_safe(env, pol, s, mode)[0] for s in scens]
            del pol
            if residual_ref:
                print(f"\n  [E12/{tag}] training residual reference seed={sd}")
                pol = train_on(env_res, steps, seed=sd, label=f"E12-{tag}-res-s{sd}")
                store["residual (no proj)"] += [rollout_policy(env_res, pol, s)[0]
                                                for s in scens]
                del pol
        for name, rs in store.items():
            a = M.aggregate(rs)
            rows.append([f"{tag}/{name}", f"{a['IntViol']['mean']:.2f}",
                         f"{a['IntViol']['ci95']:.2f}", f"{a['IntLo']['mean']:.2f}",
                         f"{a['IntHi']['mean']:.2f}", f"{a['ViolPh']['mean']:.1f}",
                         f"{a['VphMax']['mean']:.3f}", f"{a['Thru']['mean']:.0f}"])
            out[f"{tag}/{name}"] = rs
        # Droop has no seed, so it holds n_scen rows against each arm's len(seeds)*n_scen.
        # paired_delta tiles the shorter list to restore the scenario pairing.
        for name in [n for n in store if n != "Droop"]:
            d = M.paired_delta(store[name], store["Droop"], "IntViol")
            print(f"    paired {name} - Droop  IntViol: {d['mean']:+.2f} +- {d['ci95']:.2f} "
                  f"({name} better in {d['a_better']}/{d['n']})")
        del env, env_res
    M.fmt_table(f"E12  safety projection  (multi-hub, fleet-constrained, {len(seeds)} seeds "
                f"x {n_scen} paired scenarios)",
                ["case", "IntViol", "+-95%", "IntLo", "IntHi", "ViolPh", "VphMax",
                 "Thru(kWh)"], rows)
    print("\n  IntHi is the overvoltage half, and it is the column that decides this.")
    print("  'direct raw' should show IntHi > 0; both projections should drive it to ~0.")
    if not residual_ref:
        print("  Residual reference: read E2's 'RL closed-loop' row -- same env, scenarios,")
        print("  seeds and steps, so it is the identical training, already paid for.")
        print("  If it sits at IntHi ~0 with no projection, the droop prior in the action")
        print("  space is already doing the safety layer's job.")
    return out


# --------------------------------------------------------------------------- #
# E10 -- ablations: does the agent use what we gave it?
# --------------------------------------------------------------------------- #
def E10_ablations(control_mode="OFF", steps=20000, n_scen=5, seeds=(0, 1),
                  w_deg_on=10.0):
    """Two ablations on the multi-hub constrained case.

    fleet-in-state   : the paper's agent sees bus voltages + load multiplier only. Ours also
                       sees SOC, availability and the hour. Blanking those entries asks
                       whether the agent uses its battery state or merely reacts to voltage.
    degradation term : w_deg = 0 vs w_deg > 0, isolating the reward change from the state
                       change so the two are not confounded in the headline result.
    """
    out, rows = {}, []
    for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
        scens = make_scenarios(n_scen, peak, seed0=0)
        for st_fleet in (True, False):
            for w in (0.0, w_deg_on):
                acc = []
                for sd in seeds:
                    env = V2GDayEnv(CFG["hub_buses_multi"], mode="residual", w_deg=w,
                                    control_mode=control_mode,
                                    peak_range=(peak * 0.8, peak * 1.2),
                                    state_fleet=st_fleet, seed=sd)
                    lab = f"E10-{tag}-{'fleet' if st_fleet else 'nofleet'}-w{w:g}-s{sd}"
                    print(f"\n  [{lab}]")
                    pol = train_on(env, steps, seed=sd, label=lab)
                    acc += [rollout_policy(env, pol, s, True)[0] for s in scens]
                    del env, pol
                a = M.aggregate(acc)
                name = f"{tag}/state={'fleet' if st_fleet else 'voltage-only'}/w={w:g}"
                out[name] = acc
                rows.append([name, f"{a['IntViol']['mean']:.2f}",
                             f"{a['IntViol']['ci95']:.2f}",
                             f"{a['ViolPh']['mean']:.1f}", f"{a['Thru']['mean']:.0f}",
                             f"{a['VphMax']['mean']:.3f}", f"{a['SOCend']['mean']:.3f}"])
    M.fmt_table(f"E10  ablations  (multi-hub, fleet-constrained, {len(seeds)} seeds x "
                f"{n_scen} paired scenarios)",
                ["case", "IntViol", "+-95%", "ViolPh", "Thru(kWh)", "VphMax", "SOCend"],
                rows)
    print("\n  fleet-in-state pays only if 'state=fleet' beats 'state=voltage-only' by more")
    print("  than the confidence interval. If it does not, say so -- the paper's simpler")
    print("  state was sufficient, which is itself a reportable result.")
    return out


# --------------------------------------------------------------------------- #
# E11 -- what P/Q split does the trained policy actually choose?
# --------------------------------------------------------------------------- #
def policy_pq_angles(env, policy, scens, ev_constrained=False, s_floor=25.0):
    """Per-hour (angle, S) pairs actually commanded by the policy. Angle in degrees.

    Costs nothing extra: it reads the setpoints the policy already committed.

    ev_constrained defaults to FALSE, and that matters. Under the fleet constraint the
    battery reaches soc_min by hour 8 or 9, so from then on every hub is idle and there is
    no allocation left to measure -- a first version of this run produced 9 usable samples
    out of a possible 180. The reference it is compared against (E7b) is also computed
    without a fleet limit, so unconstrained is the like-for-like setting.

    Sign convention: atan2(Q, P) with P > 0 lies in (-90, 90]. NEGATIVE means the hub is
    ABSORBING reactive power, which is a different action from supplying it, not a smaller
    amount of it. Those samples are returned too and counted separately rather than being
    averaged in.
    """
    saved, saved_iid = env.ev_in_loop, env.iid_lambda
    env.ev_in_loop, env.iid_lambda = ev_constrained, False
    per_hour = {h: [] for h in env.hours}
    for sc in scens:
        obs, _ = env.reset(options=dict(peak=sc.peak, avail_day=sc.avail_day,
                                        soc_init=sc.soc_init))
        for _ in env.hours:
            act, _ = policy.predict(obs, deterministic=True)
            obs, _, done, _, info = env.step(act)
            for (p, q) in info["pq"].values():
                s = float(np.hypot(p, q))
                if s >= s_floor and p > 0:            # supporting, not charging
                    per_hour[info["hour"]].append(
                        (float(np.degrees(np.arctan2(q, p))), s))
            if done:
                break
    env.ev_in_loop, env.iid_lambda = saved, saved_iid
    return per_hour


def _pq_report(env, ang, peak, n_scen):
    """Per-hour rows and day-level stats from a policy_pq_angles result.

    Extracted so E11 and E11b summarize identically by construction. The gap is computed
    from the underlying floats rather than from the formatted strings the table prints, so
    it no longer inherits the table's one-decimal rounding -- expect differences of ~0.05 deg
    against the first E11 run.
    """
    from v2g_ref import angle_sweep          # local: v2g_ref imports this module
    lam = lam_profile(peak)
    s_max = float(np.hypot(CFG["P_rated"], CFG["Q_rated"]))
    rows, gaps = [], []
    for h in env.hours:
        v = ang[h]
        if not v:
            rows.append([h, 0, "-", "-", "-", "-", "-"])
            continue
        a = np.array([x for x, _ in v])
        s = np.array([y for _, y in v])
        n_abs = int((a < 0).sum())                 # absorbing reactive, not supplying
        a_w = float(np.average(a, weights=s))      # a 600 kVA hub must outweigh a 26 kVA one
        s_mean = float(s.mean())
        # what WAS optimal at the injection level the agent actually chose
        opt = float(angle_sweep(env, lam[h], s_frac=min(1.0, s_mean / s_max))["best_deg"])
        rows.append([h, len(v), f"{a_w:.1f}", f"{a.std():.1f}", n_abs,
                     f"{s_mean:.0f}", f"{opt:.1f}"])
        gaps.append(abs(a_w - opt))
    allv = [x for v in ang.values() for x in v]
    st = {}
    if allv:
        a = np.array([x for x, _ in allv])
        s = np.array([y for _, y in allv])
        st = dict(n=len(allv), n_poss=len(env.hours) * len(env.hubs) * n_scen,
                  n_absorb=int((a < 0).sum()),
                  day_ang=float(np.average(a, weights=s)),
                  gap=float(np.mean(gaps)) if gaps else float("nan"))
    return rows, st


def E11_policy_pq(control_mode="OFF", steps=20000, n_scen=5, seed=0):
    """Does the learned policy find the voltage-optimal P/Q split that E7b measures?

    E7b says the optimum is ~35-40 deg at half rating and shifts to ~15-25 deg at full
    rating, against a hub rating ratio of 38.7 deg. If the agent sits at the rating ratio
    regardless of loading, it has not learned the allocation -- it is just scaling a fixed
    power factor.
    """
    out = {}
    for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
        scens = make_scenarios(n_scen, peak, seed0=0)
        env = build_env(CFG["hub_buses_multi"], mode="direct", w_deg=0.0,
                        control_mode=control_mode, peak_range=(peak * 0.8, peak * 1.2),
                        seed=seed)
        print(f"\n  [E11/{tag}] training direct-action agent")
        pol = train_on(env, steps, seed=seed, label=f"E11-{tag}")
        ang = policy_pq_angles(env, pol, scens)
        rows, st = _pq_report(env, ang, peak, n_scen)
        M.fmt_table(
            f"E11  policy P/Q angle by hour -- {tag}  (deg; 0=pure P, 90=pure Q, <0=absorbing)",
            ["h", "n", "angle_Swtd", "sd", "n_absorb", "S_mean kVA", "optimal_deg"], rows)
        if st:
            print(f"    samples {st['n']} of {st['n_poss']} possible   |   "
                  f"absorbing reactive in {st['n_absorb']}")
            print(f"    day S-weighted mean {st['day_ang']:.1f} deg   |   "
                  f"hub rating ratio 38.7 deg")
            print(f"    mean |agent - optimal| = {st['gap']:.1f} deg")
            print("    A small gap means the agent found the allocation. A gap that")
            print("    tracks the rating ratio (38.7) means it is scaling a fixed")
            print("    power factor rather than allocating.")
        else:
            print("    no usable samples -- every hub stayed below the reporting floor")
        out[tag] = ang
        del env, pol
    return out


# --------------------------------------------------------------------------- #
# E11b -- does the P/Q allocation improve with training budget?
# --------------------------------------------------------------------------- #
def E11b_policy_pq_curve(control_mode="OFF", total_steps=100000, checkpoints=None,
                         n_scen=5, seeds=(0, 1), chunk=5000):
    """The angle gap as a function of training budget, not at one arbitrary point.

    WHY THIS SUPERSEDES E11. E11 measured the allocation at 20k steps. E13 then showed the
    mild agent is still improving at 100k -- IntViol falling 45.05 -> 43.56 with the gap to
    droop narrowing from +2.27 to +0.79 -- so E11's mild number describes an agent we now
    know is not converged, and the claim "the policy has not learned the allocation" cannot
    rest on it. This re-measures on E13's checkpoint grid, so the allocation is reported as a
    trajectory: if the gap shrinks with budget the original reading was a training artifact,
    and if it holds flat the diagnosis stands at five times the budget.

    Same two design points as E13, for the same reasons: checkpoints on chunk boundaries so
    the RNG is consumed as train_on consumes it, and a separate env for evaluation so
    stable-baselines3's cached observation is never invalidated mid-run. Both feeders address
    the one global OpenDSS circuit, which is safe here only because the two envs are built
    with identical topology -- the separation that matters is the Python-side fleet, clock and
    RNG state, which is exactly what the E13 guard verified to 1e-9.
    """
    if checkpoints is None:
        checkpoints = tuple(range(20000, total_steps + 1, 20000))
    checkpoints = tuple(sorted(checkpoints))
    bad = [c for c in checkpoints if c % chunk]
    if bad:
        raise ValueError(f"checkpoints must be multiples of chunk={chunk}; got {bad}")
    if checkpoints[-1] > total_steps:
        raise ValueError(f"last checkpoint {checkpoints[-1]} exceeds total_steps {total_steps}")

    out, rows = {}, []
    for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
        scens = make_scenarios(n_scen, peak, seed0=0)
        kw = dict(mode="direct", w_deg=0.0, control_mode=control_mode,
                  peak_range=(peak * 0.8, peak * 1.2))
        train_env = build_env(CFG["hub_buses_multi"], **kw)
        eval_env = build_env(CFG["hub_buses_multi"], **kw)

        per_ck = {c: [] for c in checkpoints}
        last_rows = {}
        for sd in seeds:
            print(f"\n  [E11b/{tag}] training direct-action seed={sd} to "
                  f"{checkpoints[-1]} steps")
            m = make_sac(train_env, seed=sd)
            t0, done = time.time(), 0
            for ck in checkpoints:
                while done < ck:
                    n = min(chunk, ck - done)
                    m.learn(total_timesteps=n, reset_num_timesteps=(done == 0),
                            progress_bar=False)
                    done += n
                r, st = _pq_report(eval_env, policy_pq_angles(eval_env, m, scens),
                                   peak, n_scen)
                if st:
                    per_ck[ck].append(st)
                if ck == checkpoints[-1]:
                    last_rows[sd] = r
                g = st.get("gap", float("nan")) if st else float("nan")
                d = st.get("day_ang", float("nan")) if st else float("nan")
                print(f"      [E11b-{tag}-s{sd}] {done:6d} steps  {time.time()-t0:5.0f}s   "
                      f"|gap| {g:5.1f} deg   day angle {d:5.1f} deg   "
                      f"n {st.get('n', 0) if st else 0}", flush=True)
            del m

        for ck in checkpoints:
            sts = per_ck[ck]
            if not sts:
                rows.append([f"{tag}/{ck}", "-", "-", "-", "-", "-"])
                continue
            g = np.array([x["gap"] for x in sts])
            d = np.array([x["day_ang"] for x in sts])
            ci = (1.96 * g.std(ddof=1) / np.sqrt(g.size)) if g.size > 1 else 0.0
            rows.append([f"{tag}/{ck}", f"{g.mean():.1f}", f"{ci:.1f}",
                         f"{d.mean():.1f}", f"{int(np.mean([x['n'] for x in sts]))}",
                         f"{int(np.mean([x['n_absorb'] for x in sts]))}"])
            out[f"{tag}/{ck}"] = sts

        for sd, r in last_rows.items():
            M.fmt_table(f"E11b  per-hour P/Q angle at {checkpoints[-1]} steps -- {tag}, "
                        f"seed {sd}  (deg; 0=pure P, 90=pure Q, <0=absorbing)",
                        ["h", "n", "angle_Swtd", "sd", "n_absorb", "S_mean kVA",
                         "optimal_deg"], r)

        if per_ck[checkpoints[0]] and per_ck[checkpoints[-1]]:
            f = np.array([x["gap"] for x in per_ck[checkpoints[0]]])
            l = np.array([x["gap"] for x in per_ck[checkpoints[-1]]])
            band = 0.0
            for v in (f, l):
                if v.size > 1:
                    band += 1.96 * v.std(ddof=1) / np.sqrt(v.size)
            print(f"\n  [{tag}] |agent - optimal| {checkpoints[0]} -> {checkpoints[-1]} "
                  f"steps: {f.mean():.1f} -> {l.mean():.1f} deg  "
                  f"(change {l.mean() - f.mean():+.1f}, combined 95% CI {band:.1f})")
            if abs(l.mean() - f.mean()) <= band:
                print(f"  VERDICT[{tag}]: FLAT -- the allocation gap does not close with "
                      f"budget, so E11's diagnosis stands at "
                      f"{checkpoints[-1] // checkpoints[0]}x the training.")
            elif l.mean() < f.mean():
                print(f"  VERDICT[{tag}]: CLOSING -- the agent learns the allocation given "
                      f"budget. E11's reading was a training artifact and must be requoted.")
            else:
                print(f"  VERDICT[{tag}]: WIDENING -- more training moves the agent further "
                      f"from the voltage-optimal split, which needs saying explicitly.")
        del train_env, eval_env

    M.fmt_table(f"E11b  P/Q allocation vs training budget  ({len(seeds)} seeds x {n_scen} "
                f"scenarios; hub rating ratio 38.7 deg)",
                ["case/steps", "|gap| deg", "+-95%", "day_ang", "n_samp", "n_absorb"], rows)
    print("\n  |gap| is the mean over hours of |agent angle - voltage-optimal angle|,")
    print("  both S-weighted and both evaluated at the injection level the agent chose.")
    return out


def runtime_estimate(steps, n_trainings, sec_per_20k=440, overhead=1.25):
    """sec_per_20k=440 is MEASURED on the target machine (4000 steps took 85-92 s across
    22 trainings, so ~438 s per 20k). The earlier default of 240 was taken from a faster
    box and under-predicted a full run by a factor of ~1.8. `overhead` covers the droop and
    policy rollouts, which scale with n_scen and are not free at 200 droop iterations."""
    mins = n_trainings * steps / 20000 * sec_per_20k / 60
    print(f"  ~{n_trainings} trainings x {steps} steps  ->  approx {mins:.0f} min of training")
    print(f"  with rollout overhead: approx {mins * overhead / 60:.1f} h wall clock")


# --------------------------------------------------------------------------- #
# E13 -- learning curve: is the 20k-step budget converged?
# --------------------------------------------------------------------------- #
def E13_learning_curve(control_mode="OFF", total_steps=100000, checkpoints=None,
                       n_scen=5, seeds=(0, 1), chunk=5000):
    """IntViol vs training budget, so the fixed-budget results can be defended.

    WHY THIS EXISTS. Every negative result in this study is trained for 20k steps -- about
    1100 episodes of 18 hours, ~19k gradient updates for a 10-dimensional action space. The
    obvious reviewer objection is that the agent is simply undertrained, and that one
    objection would invalidate E2, E4, E10, E11 and E12 at a stroke. A curve that plateaus
    settles it with evidence instead of assertion; a curve that does not plateau is something
    we need to know before submission rather than after.

    TWO DESIGN POINTS THAT MAKE THE CURVE TRUSTWORTHY.

    Checkpoints must fall on chunk boundaries. train_on calls m.learn in `chunk`-sized pieces,
    so stopping to evaluate on the same boundaries consumes the model RNG in the same order.
    The 20k checkpoint then reproduces the corresponding E2 seeds exactly, which is a direct
    check that the curve measures the same agent the headline table reports rather than
    something subtly different.

    Evaluation runs on a SEPARATE env instance. rollout_policy resets the env to place a
    scenario, and stable-baselines3 caches the last observation of the training env between
    learn() calls; resetting the training env mid-run would leave that cache pointing at a
    state the agent never sees again. A second env built with identical arguments avoids the
    interaction entirely, and costs nothing -- rollout_policy fully specifies the scenario
    through reset options, so the two envs are interchangeable for evaluation.
    """
    if checkpoints is None:
        checkpoints = tuple(range(20000, total_steps + 1, 20000))
    checkpoints = tuple(sorted(checkpoints))
    bad = [c for c in checkpoints if c % chunk]
    if bad:
        raise ValueError(f"checkpoints must be multiples of chunk={chunk}; got {bad}")
    if checkpoints[-1] > total_steps:
        raise ValueError(f"last checkpoint {checkpoints[-1]} exceeds total_steps {total_steps}")

    out, rows = {}, []
    for tag, peak in [("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])]:
        scens = make_scenarios(n_scen, peak, seed0=0)
        pr = (peak * 0.8, peak * 1.2)
        kw = dict(mode="residual", w_deg=0.0, control_mode=control_mode, peak_range=pr)
        train_env = build_env(CFG["hub_buses_multi"], **kw)
        eval_env = build_env(CFG["hub_buses_multi"], **kw)

        droop = [rollout_static(eval_env, s, "droop", True)[0] for s in scens]
        base = [rollout_static(eval_env, s, "baseline")[0] for s in scens]
        d_iv = M.aggregate(droop)["IntViol"]["mean"]
        b_iv = M.aggregate(base)["IntViol"]["mean"]

        per_ck = {c: [] for c in checkpoints}
        for sd in seeds:
            print(f"\n  [E13/{tag}] training seed={sd} to {checkpoints[-1]} steps")
            m = make_sac(train_env, seed=sd)
            t0, done = time.time(), 0
            for ck in checkpoints:
                while done < ck:
                    n = min(chunk, ck - done)
                    m.learn(total_timesteps=n, reset_num_timesteps=(done == 0),
                            progress_bar=False)
                    done += n
                rs = [rollout_policy(eval_env, m, s, True)[0] for s in scens]
                per_ck[ck] += rs
                a = M.aggregate(rs)
                print(f"      [E13-{tag}-s{sd}] {done:6d} steps  {time.time()-t0:5.0f}s   "
                      f"IntViol {a['IntViol']['mean']:7.2f}   Thru {a['Thru']['mean']:6.0f}",
                      flush=True)
            del m

        for ck in checkpoints:
            rs = per_ck[ck]
            a = M.aggregate(rs)
            d = M.paired_delta(rs, droop, "IntViol")
            rows.append([f"{tag}/{ck}", f"{a['IntViol']['mean']:.2f}",
                         f"{a['IntViol']['ci95']:.2f}", f"{d['mean']:+.2f}",
                         f"{d['a_better']}/{d['n']}", f"{a['ViolPh']['mean']:.1f}",
                         f"{a['VphMax']['mean']:.3f}", f"{a['Thru']['mean']:.0f}"])
            out[f"{tag}/{ck}"] = rs
        out[f"{tag}/droop"] = droop
        out[f"{tag}/baseline"] = base

        first, last = M.aggregate(per_ck[checkpoints[0]]), M.aggregate(per_ck[checkpoints[-1]])
        f_iv, l_iv = first["IntViol"]["mean"], last["IntViol"]["mean"]
        band = first["IntViol"]["ci95"] + last["IntViol"]["ci95"]
        print(f"\n  [{tag}] IntViol {checkpoints[0]} -> {checkpoints[-1]} steps: "
              f"{f_iv:.2f} -> {l_iv:.2f}  (change {l_iv - f_iv:+.2f}, combined 95% CI "
              f"{band:.2f})")
        if abs(l_iv - f_iv) <= band:
            print(f"  VERDICT[{tag}]: PLATEAU -- the change from {checkpoints[0]} to "
                  f"{checkpoints[-1]} steps is inside the confidence interval, so the "
                  f"{checkpoints[0]}-step budget is not the binding limitation.")
        elif l_iv < f_iv:
            print(f"  VERDICT[{tag}]: STILL IMPROVING -- more training helps. Report the "
                  f"curve and requote the fixed-budget results at the plateau, not at 20k.")
        else:
            print(f"  VERDICT[{tag}]: DEGRADING -- longer training makes it worse, which is "
                  f"its own finding and needs saying explicitly.")
        print(f"  reference: droop {d_iv:.2f}   no-V2G baseline {b_iv:.2f}")
        del train_env, eval_env

    M.fmt_table(f"E13  learning curve  (multi-hub, fleet-constrained, {len(seeds)} seeds "
                f"x {n_scen} paired scenarios)",
                ["case/steps", "IntViol", "+-95%", "vs droop", "RL wins", "ViolPh", "VphMax",
                 "Thru(kWh)"], rows)
    print("\n  The 20000-step rows should sit on top of E2's RL closed-loop numbers for the")
    print("  same seeds -- same agent, same env, same scenarios, checkpoints on chunk")
    print("  boundaries. A mismatch there means the curve is not measuring E2's agent.")
    return out
