"""
Deterministic reference studies -- no RL training, no seeds, minutes to run.

Everything here is a power-flow computation, so the numbers are exact rather than
sampled. They are also PREREQUISITES for the training runs: each one changes how the
trained results should be read, so they run first.

E5  injection scan / achievable ceiling                                     (adds X4)
    Per hour, sweep total hub injection from zero to full inverter rating and record the
    worst-phase voltage. This is the ceiling: how far ANY controller could push the feeder
    that hour, whatever its control law. Without it droop is the only reference, and
    "the learner underperformed" cannot be separated from "the hour is not clearable".

E6  droop implementation variants                                           (adds X5)
    The target paper's coordinated droop reaches 2 violation-hours at aggressive multi-hub
    load; our closed-loop droop reaches 10. Droop evaluated OPEN-LOOP -- response computed
    once from the pre-injection voltage, which is lower, so the droop fraction is larger --
    injects more and should land closer to their number. Report both rather than leave the
    discrepancy unexplained.

E7  P/Q allocation                                                          (adds the P/Q study)
    Their Eq. (4) drains the battery on APPARENT power: a kVAr of reactive support costs
    exactly as much stored energy as a kW of active support. They never explore the
    consequence. Holding S fixed and varying only the P/Q split answers the question a
    fleet operator actually faces -- given a limited energy budget, where does it buy the
    most voltage?

E5 and E7 share one scan, so they are computed together and reported separately.
"""
import numpy as np

from v2g_sys import CFG, droop_pq, lam_profile
import v2g_metrics as M
from v2g_study import make_scenarios, _reset_fleets, _log, build_env


# --------------------------------------------------------------------------- #
# Shared primitive: sweep injection at one hour, in three P/Q allocations
# --------------------------------------------------------------------------- #
def injection_scan(env, lam_h, n_grid=33):
    """Sweep total per-hub apparent power 0 -> full rating at fixed load multiplier.

    All three allocations are swept over the SAME apparent-power axis, because that is
    what the battery pays for (Eq. 4). So the comparison is like-for-like in stored
    energy, and any difference between the curves is pure network sensitivity.
    """
    cfg = env.cfg
    s_max = float(np.hypot(cfg["P_rated"], cfg["Q_rated"]))       # kVA per hub
    theta = float(np.arctan2(cfg["Q_rated"], cfg["P_rated"]))
    modes = {"P": (1.0, 0.0),                      # all active
             "Q": (0.0, 1.0),                      # all reactive
             "PQ": (np.cos(theta), np.sin(theta))}  # rating-proportional

    env.fd.set_load(lam_h)
    out = {}
    for name, (cp, cq) in modes.items():
        grid = np.linspace(0.0, s_max, n_grid)
        vmin, vmax, ivio, conv = [], [], [], []
        for s in grid:
            for b in env.hubs:
                env.fd.set_hub(b, s * cp, s * cq)
            ok = bool(env.fd.solve())
            conv.append(ok)
            if not ok:
                # A non-converged solve still leaves voltages in the OpenDSS arrays, and
                # they are meaningless -- at deep-sag hours the high-injection end of the
                # sweep sits past the nose of the PV curve. Reading them anyway produced a
                # spurious ceiling and a spurious collapse. Mask instead.
                vmin.append(np.nan); vmax.append(np.nan); ivio.append(np.nan)
                continue
            vp = env.fd.phase_vpu()
            vmin.append(float(vp.min()))
            vmax.append(float(vp.max()))
            lo = float(np.clip(M.V_MIN - M.V_TOL - vp, 0, None).sum())
            hi = float(np.clip(vp - M.V_MAX - M.V_TOL, 0, None).sum())
            ivio.append(lo + hi)
        out[name] = dict(S=grid, Vmin=np.array(vmin), Vmax=np.array(vmax),
                         IntViol=np.array(ivio), Conv=np.array(conv, dtype=bool))
    env.fd.zero_hubs()
    env.fd.solve()
    return out


def _clearing_point(scan_mode):
    """Smallest CONVERGED S that puts every phase in band; None if the hour never clears."""
    iv = scan_mode["IntViol"]
    # Parentheses matter: `&` binds tighter than `<=` in Python.
    ok = np.flatnonzero(scan_mode["Conv"] & (np.nan_to_num(iv, nan=1.0) <= 1e-9))
    return float(scan_mode["S"][ok[0]]) if ok.size else None


def _best_point(scan_mode):
    """Best worst-phase voltage over CONVERGED points, and the S that reaches it.

    Returns (nan, nan) if nothing converged at this hour.
    """
    v = scan_mode["Vmin"]
    if not np.any(np.isfinite(v)):
        return float("nan"), float("nan")
    i = int(np.nanargmax(v))
    return float(v[i]), float(scan_mode["S"][i])


def _conv_frac(sc):
    """Fraction of swept points that converged, over all three allocations."""
    tot = sum(m["Conv"].size for m in sc.values())
    good = sum(int(m["Conv"].sum()) for m in sc.values())
    return good / tot if tot else 0.0


def angle_sweep(env, lam_h, s_frac=0.5, n_ang=19):
    """Voltage uplift vs P/Q split at FIXED apparent power.

    The three-mode comparison says P beats Q; it does not say where the optimum is. Sweeping
    the injection angle theta at constant S does, and constant S means constant battery
    drain (Eq. 4) -- so this is the allocation question a fleet operator actually faces:
    given the energy you are willing to spend this hour, what power factor buys the most
    voltage? theta=0 is pure active, theta=90 is pure reactive, and the hubs' rating ratio
    (500 kW / 400 kVAr) sits at 38.7 deg.
    """
    cfg = env.cfg
    s = s_frac * float(np.hypot(cfg["P_rated"], cfg["Q_rated"]))
    env.fd.set_load(lam_h)
    angs = np.linspace(0.0, np.pi / 2, n_ang)
    vmin, conv = [], []
    for th in angs:
        for b in env.hubs:
            env.fd.set_hub(b, s * np.cos(th), s * np.sin(th))
        ok = bool(env.fd.solve())
        conv.append(ok)
        vmin.append(float(env.fd.phase_vpu().min()) if ok else np.nan)
    env.fd.zero_hubs()
    env.fd.solve()
    vmin = np.array(vmin)
    deg = np.degrees(angs)
    if np.any(np.isfinite(vmin)):
        i = int(np.nanargmax(vmin))
        best_deg, best_v = float(deg[i]), float(vmin[i])
    else:
        best_deg, best_v = float("nan"), float("nan")
    return dict(deg=deg, Vmin=vmin, Conv=np.array(conv, dtype=bool),
                best_deg=best_deg, best_Vmin=best_v, S=s)


# --------------------------------------------------------------------------- #
# E5 + E7 -- achievable ceiling and P/Q allocation
# --------------------------------------------------------------------------- #
def E5_reference_and_pq(control_mode="OFF", n_grid=33, n_scen=1):
    """Per-hour achievable ceiling and P/Q allocation, for both hub configs and peaks.

    Also rolls out closed-loop droop on the same hours so the delivered injection can be
    placed against the required injection -- the whole point of having a reference.
    """
    res = {}
    for tag, hubs in (("single", CFG["hub_bus_single"]), ("multi", CFG["hub_buses_multi"])):
        env = build_env(hubs, control_mode=control_mode)       # ONE live circuit
        for pk_name, pk in (("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])):
            lam = lam_profile(pk)
            rows_ref, rows_pq = [], []
            per_hour = {}
            for h in env.hours:
                sc = injection_scan(env, lam[h], n_grid=n_grid)
                per_hour[h] = sc

                s_clear = _clearing_point(sc["PQ"])
                v0 = float(sc["PQ"]["Vmin"][0])                 # no injection (always solves)
                vbest_pq, s_at_best = _best_point(sc["PQ"])
                rows_ref.append([h, round(lam[h], 2), round(v0, 4), round(vbest_pq, 4),
                                 round(vbest_pq - v0, 4),
                                 "-" if s_clear is None else round(s_clear, 1),
                                 "no" if s_clear is None else "yes",
                                 f"{_conv_frac(sc):.0%}"])

                # P/Q at matched apparent power: compare at full rating and at half
                half = n_grid // 2
                rows_pq.append([h, round(lam[h], 2),
                                round(sc["P"]["Vmin"][half] - v0, 4),
                                round(sc["Q"]["Vmin"][half] - v0, 4),
                                round(sc["PQ"]["Vmin"][half] - v0, 4),
                                round(sc["P"]["Vmin"][-1] - v0, 4),
                                round(sc["Q"]["Vmin"][-1] - v0, 4),
                                round(sc["PQ"]["Vmin"][-1] - v0, 4)])

            # optimal P/Q split per hour, at half and full rating
            rows_ang, ang_raw = [], {}
            for h in env.hours:
                a_half = angle_sweep(env, lam[h], s_frac=0.5)
                a_full = angle_sweep(env, lam[h], s_frac=1.0)
                ang_raw[h] = (a_half, a_full)
                rows_ang.append([h, round(lam[h], 2),
                                 round(a_half["best_deg"], 1), round(a_half["best_Vmin"], 4),
                                 round(a_full["best_deg"], 1), round(a_full["best_Vmin"], 4)])

            # fleet energy ceiling at initial SOC, for context against S_clear
            fl = env.fleets[env.hubs[0]]
            fl.reset()
            avail_kw = {h: fl.avail_power(h) for h in env.hours}

            res[f"{tag}_{pk_name}"] = dict(ref=rows_ref, pq=rows_pq, ang=rows_ang,
                                           ang_raw=ang_raw, per_hour=per_hour,
                                           avail=avail_kw, n_hubs=len(env.hubs))
        del env
    return res


def report_E5(res):
    for key, d in res.items():
        M.fmt_table(
            f"E5 achievable ceiling -- {key}  ({d['n_hubs']} hub(s), PQ allocation)",
            ["h", "lam", "Vmin(0)", "Vmin(best)", "uplift", "S_clear/hub", "clearable",
             "conv"],
            d["ref"])
        n_clear = sum(1 for r in d["ref"] if r[6] == "yes")
        print(f"    clearable hours: {n_clear}/{len(d['ref'])}")
        print("    'conv' = fraction of swept injection points whose power flow converged;"
              "\n    non-converged points are excluded from Vmin(best) and S_clear.")


def report_E7(res):
    for key, d in res.items():
        M.fmt_table(
            f"E7 P/Q allocation at matched apparent power -- {key}  (voltage uplift, p.u.)",
            ["h", "lam", "P@half", "Q@half", "PQ@half", "P@full", "Q@full", "PQ@full"],
            d["pq"])
        # nan-aware: the full-rating column is the one most likely to be masked out.
        full = np.array([[r[5], r[6], r[7]] for r in d["pq"]], dtype=float)
        half = np.array([[r[2], r[3], r[4]] for r in d["pq"]], dtype=float)
        for lab, arr in (("half rating", half), ("full rating", full)):
            n_ok = int(np.isfinite(arr).all(axis=1).sum())
            if n_ok == 0:
                print(f"    {lab}: no hour converged in all three allocations")
                continue
            mp, mq, mpq = np.nanmean(arr[:, 0]), np.nanmean(arr[:, 1]), np.nanmean(arr[:, 2])
            print(f"    mean uplift at {lab} ({n_ok}/{len(arr)} hrs) -- "
                  f"P {mp:.4f}   Q {mq:.4f}   PQ {mpq:.4f}")
            if mq > 1e-6:
                print(f"      -> P delivers {mp/mq:.2f}x the uplift of Q "
                      f"per unit of battery drain")

        M.fmt_table(
            f"E7b voltage-optimal P/Q split at fixed apparent power -- {key}",
            ["h", "lam", "best_deg@half", "Vmin@half", "best_deg@full", "Vmin@full"],
            d["ang"])
        ang = np.array([[r[2], r[4]] for r in d["ang"]], dtype=float)
        rating_deg = np.degrees(np.arctan2(CFG["Q_rated"], CFG["P_rated"]))
        print(f"    hub rating ratio sits at {rating_deg:.1f} deg "
              f"(0 = pure active, 90 = pure reactive)")
        for j, lab in ((0, "half"), (1, "full")):
            if np.any(np.isfinite(ang[:, j])):
                print(f"    mean voltage-optimal split at {lab} rating: "
                      f"{np.nanmean(ang[:, j]):.1f} deg")


# --------------------------------------------------------------------------- #
# E8 -- per-hub optimized dispatch (replaces the uniform-injection ceiling)
# --------------------------------------------------------------------------- #
def _intviol_now(fd):
    vp = fd.phase_vpu()
    lo = float(np.clip(M.V_MIN - M.V_TOL - vp, 0, None).sum())
    hi = float(np.clip(vp - M.V_MAX - M.V_TOL, 0, None).sum())
    return lo + hi


def _apply_and_score(env, sp):
    """Set every hub, solve, return two-sided violation. Non-convergence scores +inf so
    the search treats it as infeasible rather than reading stale voltages."""
    for b, (p, q) in sp.items():
        env.fd.set_hub(b, p, q)
    if not env.fd.solve():
        return float("inf")
    return _intviol_now(env.fd)


def optimal_dispatch(env, lam_h, n_pass=3, n_s=9, n_th=5, refine=True):
    """Per-hub (P, Q) minimizing two-sided violation, by coordinate descent on the AC flow.

    WHY THIS EXISTS. The uniform-injection scan answers "what can all hubs do together at
    EQUAL output", which is not the achievable ceiling. With five hubs at equal output,
    lifting the far end of the feeder to 0.95 drives the near buses past 1.05, so hours
    that are clearable by an uneven dispatch score as unclearable -- and the five-hub case
    then scores worse than the single-hub case, which is impossible. Searching per hub
    removes that artifact.

    Coordinate descent rather than a gradient method because the objective is piecewise
    linear with a kink at each voltage limit, and because every evaluation is a full AC
    power flow whose derivative we do not have.
    """
    cfg = env.cfg
    s_max = float(np.hypot(cfg["P_rated"], cfg["Q_rated"]))
    env.fd.set_load(lam_h)

    sp = {b: (0.0, 0.0) for b in env.hubs}
    best = _apply_and_score(env, sp)
    s_grid = np.linspace(0.0, s_max, n_s)
    th_grid = np.linspace(0.0, np.pi / 2, n_th)
    n_solve = 1

    for _ in range(n_pass):
        improved = False
        for b in env.hubs:
            keep, loc = sp[b], best
            for s in s_grid:
                for th in th_grid:
                    sp[b] = (s * np.cos(th), s * np.sin(th))
                    val = _apply_and_score(env, sp)
                    n_solve += 1
                    if val < loc - 1e-9:
                        loc, keep = val, sp[b]
            sp[b] = keep
            if loc < best - 1e-9:
                best, improved = loc, True
        if not improved:
            break

    if refine:                       # local polish around the incumbent
        for b in env.hubs:
            p0, q0 = sp[b]
            s0, th0 = float(np.hypot(p0, q0)), float(np.arctan2(q0, p0))
            keep, loc = sp[b], best
            ds = s_max / (n_s - 1) if n_s > 1 else s_max
            for s in np.linspace(max(0.0, s0 - ds), min(s_max, s0 + ds), 7):
                for th in np.linspace(max(0.0, th0 - 0.4), min(np.pi / 2, th0 + 0.4), 7):
                    sp[b] = (s * np.cos(th), s * np.sin(th))
                    val = _apply_and_score(env, sp)
                    n_solve += 1
                    if val < loc - 1e-9:
                        loc, keep = val, sp[b]
            sp[b] = keep
            best = min(best, loc)

    for b, (p, q) in sp.items():
        env.fd.set_hub(b, p, q)
    env.fd.solve()
    vp = env.fd.phase_vpu()
    s_tot = float(sum(np.hypot(p, q) for p, q in sp.values()))
    env.fd.zero_hubs()
    env.fd.solve()
    return dict(IntViol=best, dispatch=dict(sp), S_total=s_tot, n_solve=n_solve,
                Vmin=float(vp.min()), Vmax=float(vp.max()),
                clearable=bool(best <= 1e-9))


def E8_optimal_ceiling(control_mode="OFF", n_pass=3):
    """True achievable ceiling per hour, and the value of coordinating hubs unevenly.

    Reports optimized dispatch against the uniform-injection best, so the gap IS the value
    of coordination -- independent of any controller. That is directly relevant to the
    target paper's multi-hub claim: their RL coordinates hubs, droop is purely local.
    """
    res = {}
    for tag, hubs in (("single", CFG["hub_bus_single"]), ("multi", CFG["hub_buses_multi"])):
        env = build_env(hubs, control_mode=control_mode)
        for pk_name, pk in (("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])):
            lam = lam_profile(pk)
            rows, raw = [], {}
            for h in env.hours:
                uni = injection_scan(env, lam[h], n_grid=17)
                u_best = float(np.nanmin(uni["PQ"]["IntViol"])) if np.any(
                    np.isfinite(uni["PQ"]["IntViol"])) else float("nan")
                opt = optimal_dispatch(env, lam[h], n_pass=n_pass)
                raw[h] = opt
                rows.append([h, round(lam[h], 2),
                             round(u_best, 2), round(opt["IntViol"], 2),
                             round(opt["Vmin"], 4), round(opt["Vmax"], 4),
                             round(opt["S_total"], 0),
                             "yes" if opt["clearable"] else "no"])
            res[f"{tag}_{pk_name}"] = dict(rows=rows, raw=raw, n_hubs=len(env.hubs))
        del env
    return res


def report_E8(res):
    for key, d in res.items():
        M.fmt_table(
            f"E8 optimized per-hub dispatch -- {key}  ({d['n_hubs']} hub(s))",
            ["h", "lam", "IntViol(uniform)", "IntViol(opt)", "Vmin", "Vmax",
             "S_total kVA", "clearable"], d["rows"])
        n_clear = sum(1 for r in d["rows"] if r[7] == "yes")
        uni = np.array([r[2] for r in d["rows"]], dtype=float)
        opt = np.array([r[3] for r in d["rows"]], dtype=float)
        print(f"    clearable hours (optimized): {n_clear}/{len(d['rows'])}")
        print(f"    day-total IntViol -- uniform {np.nansum(uni):.2f}   "
              f"optimized {np.nansum(opt):.2f}")
        if d["n_hubs"] > 1 and np.nansum(uni) > 1e-9:
            gain = 1 - np.nansum(opt) / np.nansum(uni)
            print(f"    value of uneven hub coordination: {gain:.1%} lower violation "
                  f"at equal inverter rating")


# --------------------------------------------------------------------------- #
# E6 -- droop implementation variants
# --------------------------------------------------------------------------- #
def rollout_droop_openloop(env, scen, ev_constrained=True):
    """Droop computed ONCE from the pre-injection voltage, applied, solved.

    This is the natural reading of a 'local Volt-Var/Volt-Watt droop controller' if it is
    not iterated to equilibrium. The pre-injection voltage is the lowest voltage of the
    hour, so the droop fraction is at its largest -- this variant injects strictly more
    than the closed-loop version and should sit closer to the paper's Table II.
    """
    cfg = env.cfg
    lam = lam_profile(scen.peak)
    _reset_fleets(env, scen)
    rec = M.hourly_record()
    thru_cum = 0.0
    for h in env.hours:
        env.fd.set_load(lam[h])
        env.fd.zero_hubs()
        env.fd.solve()                       # pre-injection state -> droop reads this
        disch, rho, n = 0.0, 1.0, np.nan
        for b in env.hubs:
            v = env.fd.hub_vpu(b)
            p, q = droop_pq(v, cfg["P_rated"], cfg["Q_rated"])
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
    return M.summarize(rec, env.fleets[env.hubs[0]].soc_series), rec


def E6_droop_variants(control_mode="OFF", n_scen=3):
    """Open-loop vs closed-loop droop, both hub configs, both peaks, both constraint states.

    The paper's Table II coordinated-droop row is the target: VMean 1.024/0.998,
    VMin 1.004/0.940, violation-hours 0/2 for mild/aggressive.
    """
    from v2g_study import rollout_static
    out = {}
    for tag, hubs in (("single", CFG["hub_bus_single"]), ("multi", CFG["hub_buses_multi"])):
        env = build_env(hubs, control_mode=control_mode)
        for pk_name, pk in (("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])):
            scens = make_scenarios(n_scen, pk, seed0=0)
            rows = []
            for con in (False, True):
                lab = "constrained" if con else "unconstrained"
                for name, fn in (("closed-loop", rollout_static),
                                 ("open-loop", rollout_droop_openloop)):
                    accum = []
                    for sc in scens:
                        if fn is rollout_static:
                            s, _ = fn(env, sc, controller="droop", ev_constrained=con)
                        else:
                            s, _ = fn(env, sc, ev_constrained=con)
                        accum.append(s)
                    a = M.aggregate(accum)
                    rows.append([f"{name} ({lab})",
                                 round(a["VMean"]["mean"], 3), round(a["VMin"]["mean"], 3),
                                 round(a["VMax"]["mean"], 3),
                                 round(a["ViolMean"]["mean"], 1),
                                 round(a["ViolPh"]["mean"], 1),
                                 round(a["IntViol"]["mean"], 2),
                                 round(a["VphMax"]["mean"], 3),
                                 round(a["Thru"]["mean"], 0)])
            out[f"{tag}_{pk_name}"] = rows
        del env
    return out


def report_E6(out):
    paper = {"multi_mild": "paper Table II: VMean 1.024  VMin 1.004  ViolMean 0",
             "multi_aggr": "paper Table II: VMean 0.998  VMin 0.940  ViolMean 2"}
    for key, rows in out.items():
        M.fmt_table(f"E6 droop variants -- {key}",
                    ["variant", "VMean", "VMin", "VMax", "ViolMean", "ViolPh",
                     "IntViol", "VphMax", "Thru"], rows)
        if key in paper:
            print(f"    {paper[key]}")


# --------------------------------------------------------------------------- #
# E9 -- droop convergence sweep
# --------------------------------------------------------------------------- #
def E9_droop_iters(control_mode="OFF", n_scen=3,
                   iters=(1, 2, 3, 5, 10, 25, 50), damps=(0.3, 0.6)):
    """How far the droop loop is driven, swept.

    E6 showed neither pure variant reproduces both of the paper's Table II rows: closed-loop
    matches mild (VMean 1.009 vs their 1.024, ViolMean 0 vs 0) while open-loop is wildly
    over-injected there (VphMax 2.095); open-loop is closer at aggressive (1.011/0.944 vs
    their 0.998/0.940) while closed-loop undershoots (0.961/0.925).

    A PARTIALLY converged loop sits between the two. With damp=0.6 from a zero start, one
    iteration injects 0.6x the open-loop response and the sequence then decays toward the
    equilibrium, so this sweep spans the gap. If a single iteration count reproduces both
    rows, that identifies their droop; if none does, the difference is elsewhere and the
    paper reports it as a limitation rather than guessing.
    """
    from v2g_study import rollout_static
    out = {}
    for tag, hubs in (("multi", CFG["hub_buses_multi"]),
                      ("single", CFG["hub_bus_single"])):
        env = build_env(hubs, control_mode=control_mode)
        for pk_name, pk in (("mild", CFG["peak_mild"]), ("aggr", CFG["peak_aggr"])):
            scens = make_scenarios(n_scen, pk, seed0=0)
            rows = []
            for dp in damps:
                for it in iters:
                    # backoff=False so `iters=k` means exactly k iterations at damping dp.
                    # With backoff on, a small k silently becomes four restarts at halved
                    # damping, which is not a partially converged loop.
                    acc = [rollout_static(env, sc, controller="droop", ev_constrained=False,
                                          damp=dp, iters=it, backoff=False)[0]
                           for sc in scens]
                    a = M.aggregate(acc)
                    rows.append([f"d{dp}/i{it}", round(a["VMean"]["mean"], 3),
                                 round(a["VMin"]["mean"], 3),
                                 round(a["ViolMean"]["mean"], 1),
                                 round(a["ViolPh"]["mean"], 1),
                                 round(a["IntViol"]["mean"], 2),
                                 round(a["VphMax"]["mean"], 3),
                                 round(a["Thru"]["mean"], 0)])
            acc = [rollout_droop_openloop(env, sc, ev_constrained=False)[0] for sc in scens]
            a = M.aggregate(acc)
            rows.append(["open-loop", round(a["VMean"]["mean"], 3),
                         round(a["VMin"]["mean"], 3), round(a["ViolMean"]["mean"], 1),
                         round(a["ViolPh"]["mean"], 1), round(a["IntViol"]["mean"], 2),
                         round(a["VphMax"]["mean"], 3), round(a["Thru"]["mean"], 0)])
            out[f"{tag}_{pk_name}"] = rows
        del env
    return out


def report_E9(out):
    paper = {"multi_mild": (1.024, 1.004, 0.0), "multi_aggr": (0.998, 0.940, 2.0)}
    for key, rows in out.items():
        M.fmt_table(f"E9 droop convergence sweep -- {key}  (unconstrained)",
                    ["setting", "VMean", "VMin", "ViolMean", "ViolPh", "IntViol",
                     "VphMax", "Thru"], rows)
        if key not in paper:
            continue
        pm, pv, pviol = paper[key]
        print(f"    paper Table II: VMean {pm}  VMin {pv}  ViolMean {pviol:.0f}")
        # closest row on the two voltage columns the paper actually reports
        d = sorted((abs(r[1] - pm) + abs(r[2] - pv), r[0]) for r in rows)
        print(f"    closest on (VMean, VMin): {d[0][1]}  |dVMean|+|dVMin| = {d[0][0]:.3f}")
        # Is the sweep even converging? Compare the two largest iteration counts per damping.
        for dp in sorted({r[0].split("/")[0] for r in rows if "/" in r[0]}):
            th = [(int(r[0].split("i")[1]), r[7]) for r in rows if r[0].startswith(dp + "/")]
            th.sort()
            if len(th) >= 2:
                spread = abs(th[-1][1] - th[-2][1])
                verdict = "converged" if spread < 0.02 * max(1.0, abs(th[-1][1])) \
                    else "NOT converged (limit cycle)"
                print(f"    {dp}: throughput at i={th[-2][0]} vs i={th[-1][0]} -> "
                      f"{th[-2][1]:.0f} vs {th[-1][1]:.0f} kWh  [{verdict}]")
