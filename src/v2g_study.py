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
def train_on(env, steps, seed=0, chunk=5000, label=""):
    m = SAC("MlpPolicy", env, learning_rate=3e-4, batch_size=256, gamma=0.99,
            buffer_size=200_000, learning_starts=1000, tau=0.005,
            policy_kwargs=dict(net_arch=[256, 256]), device="cpu",
            seed=seed, verbose=0)
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
def policy_pq_angles(env, policy, scens, ev_constrained=True, s_floor=10.0):
    """Per-hour injection angle atan2(Q, P) actually commanded, in degrees.

    Costs nothing extra: it reads the setpoints the policy already committed. Hours where
    the hub is essentially idle (S < s_floor kVA) carry no meaningful angle and are skipped.
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
                    per_hour[info["hour"]].append(float(np.degrees(np.arctan2(q, p))))
            if done:
                break
    env.ev_in_loop, env.iid_lambda = saved, saved_iid
    return per_hour


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
        rows = []
        for h in env.hours:
            v = ang[h]
            rows.append([h, len(v),
                         f"{np.mean(v):.1f}" if v else "-",
                         f"{np.std(v):.1f}" if v else "-"])
        M.fmt_table(f"E11  policy P/Q angle by hour -- {tag}  (deg; 0=pure P, 90=pure Q)",
                    ["h", "n", "mean_deg", "sd_deg"], rows)
        allv = [x for v in ang.values() for x in v]
        if allv:
            print(f"    day mean {np.mean(allv):.1f} deg   |   hub rating ratio 38.7 deg")
            print(f"    E7b voltage-optimal: ~35-40 deg at half rating, "
                  f"~15-25 deg at full rating")
        out[tag] = ang
        del env, pol
    return out


def runtime_estimate(steps, n_trainings, sec_per_20k=240):
    mins = n_trainings * steps / 20000 * sec_per_20k / 60
    print(f"  ~{n_trainings} trainings x {steps} steps  ->  approx {mins:.0f} min of training")
