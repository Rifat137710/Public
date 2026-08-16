"""Emit the paper's tables as LaTeX, straight from the result files.

Every number in the manuscript comes from here. Nothing is typed into the .tex
by hand, because a transcription error in a table is invisible to every check
this repository runs -- the tests, the reproduction gate and the sweeps all pass
regardless of what ends up in the paper. Regenerate after any re-run:

    python scripts/make_paper_tables.py

Writes paper/tables/*.tex, each a bare `tabular` for \\input.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "tables"


def load(name: str) -> dict:
    return json.loads((ROOT / "results" / name).read_text())


def w(name: str, body: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(body.rstrip() + "\n")
    print(f"  wrote paper/tables/{name}")


# --- Table I: the two testbeds ---------------------------------------------


def table_testbeds() -> None:
    kop = load("kerber_operating_point.json")
    pick = min((r for r in kop["cells"] if r["usable"]),
               key=lambda r: ((r["uncoord_viol"] - 0.0626) / 0.0626) ** 2
               + ((r["uncoord_soc"] - 0.8041) / 0.8041) ** 2)
    rows = [
        ("Base network", "IEEE 33-bus (Baran--Wu)", "Kerber \\emph{Dorfnetz}"),
        ("Buses (incl.\\ Th\\'evenin)", "34", "117"),
        ("Nominal voltage", "12.66\\,kV", "0.4\\,kV"),
        ("Laterals", "1 trunk + 3 spurs", "6"),
        ("Load points / total", "32 / 3.72\\,MW", "57 / 0.34\\,MW"),
        ("Charging stations", "4 $\\times$ 80\\,kVA", "4 $\\times$ 22\\,kVA"),
        ("Idle $V_{\\min}$", "0.9658\\,p.u.", f"{pick['idle_vmin']:.4f}\\,p.u."),
        ("Idle violations", "0.0000", f"{pick['idle_viol']:.4f}"),
        ("Uncoordinated violations", "0.0626", f"{pick['uncoord_viol']:.4f}"),
        ("Uncoordinated service", "0.804", f"{pick['uncoord_soc']:.3f}"),
    ]
    body = ["\\begin{tabular}{lcc}", "\\toprule",
            " & \\textbf{MV feeder} & \\textbf{LV feeder} \\\\", "\\midrule"]
    body += [f"{a} & {b} & {c} \\\\" for a, b, c in rows]
    body += ["\\bottomrule", "\\end{tabular}"]
    w("testbeds.tex", "\n".join(body))


# --- Table II: the layer, not the learner ----------------------------------


def table_layer_not_learner() -> None:
    ph = load("projected_heuristics.json")
    ab = load("ablation/ablation.json")

    def agg(key):
        a = ph[key]["aggregate"]
        return (a["voltage_violation_step_rate_mean"],
                a["frac_meeting_soc_target_mean"],
                a["net_cost_usd_mean"],
                a.get("mean_step_time_ms_mean", float("nan")))

    learned = ab["summary"]["projection"]
    rows = [
        ("Idle (no charging)", *agg("zero")),
        ("Uncoordinated", *agg("uncoordinated")),
        ("IEEE 1547 droop", *agg("droop")),
        ("SafeSAC (learned $+$ projection)", learned["viol"][0],
         learned["soc"][0], learned["cost"][0], float("nan")),
        ("\\textbf{Uncoordinated $+$ projection}", *agg("uncoordinated+proj")),
    ]
    body = ["\\begin{tabular}{lrrrr}", "\\toprule",
            "Controller & Viol.\\ rate & Service & Net cost & ms/step \\\\",
            "\\midrule"]
    for name, v, s, c, ms in rows:
        msc = "---" if ms != ms else f"{ms:.2f}"
        body.append(f"{name} & {v:.4f} & {s:.4f} & \\$"
                    f"{c:.0f} & {msc} \\\\")
    body += ["\\bottomrule", "\\end{tabular}"]
    w("layer_not_learner.tex", "\n".join(body))

    ratio = agg("uncoordinated+proj")[1] / learned["soc"][0]
    print(f"    [service ratio, greedy+proj over learned+proj: {ratio:.1f}x]")


# --- Table III: the staleness cliff, both feeders ---------------------------


def table_staleness() -> None:
    src = "uncoordinated"
    refresh = ["1", "3", "12", "24", "48", "288"]
    body = ["\\begin{tabular}{llrrrrrrr}", "\\toprule",
            "&& \\multicolumn{1}{c}{No} & \\multicolumn{6}{c}{"
            "Base-point refresh interval (control steps)} \\\\",
            "\\cmidrule(lr){3-3}\\cmidrule(lr){4-9}",
            "Feeder & $Z_{\\mathrm{sub}}$ & proj. & "
            + " & ".join(refresh) + " \\\\", "\\midrule"]
    for label, fn, zs in [("MV", "staleness_sweep_25ep.json", ["6.0", "8.0", "10.0"]),
                          ("LV", "staleness_kerber.json", ["1.0", "2.0", "3.0"])]:
        d = load(fn)
        for i, z in enumerate(zs):
            row = d["cells"][z][src]
            cells = []
            for r in refresh:
                v = row[r]["viol"]
                cells.append(f"\\textbf{{{v:.4f}}}" if v == 0.0 else f"{v:.4f}")
            head = label if i == 0 else ""
            body.append(f"{head} & {float(z):.0f}\\% & {row['raw']['viol']:.4f} & "
                        + " & ".join(cells) + " \\\\")
        if label == "MV":
            body.append("\\midrule")
    body += ["\\bottomrule", "\\end{tabular}"]
    w("staleness.tex", "\n".join(body))

    # the recovery statistic quoted in the abstract
    recs = []
    for fn, zs in [("staleness_sweep_25ep.json", ["6.0", "8.0", "10.0"]),
                   ("staleness_kerber.json", ["1.0", "2.0", "3.0"])]:
        d = load(fn)
        for z in zs:
            for s in d["cells"][z]:
                c = d["cells"][z][s]
                recs.append(c["288"]["viol"] / c["raw"]["viol"])
    print(f"    [never-refreshed recovers {100*min(recs):.1f}--{100*max(recs):.1f}% "
          f"of the unprojected rate, {len(recs)} cells]")


# --- Table IV: model error --------------------------------------------------


def table_model_error() -> None:
    mv, lv = load("model_error_case33bw.json"), load("model_error_kerber.json")
    ks = mv["scale"]
    body = ["\\begin{tabular}{lrrrrrrrr}", "\\toprule",
            "& \\multicolumn{8}{c}{Jacobian error "
            "$\\lVert\\partial V/\\partial P\\rVert$ relative to truth} \\\\",
            "\\cmidrule(lr){2-9}",
            "Feeder & " + " & ".join(
                f"{mv['jacobian_ratio'][str(k)]:.2f}$\\times$" for k in ks)
            + " \\\\", "\\midrule"]
    for label, d in [("MV", mv), ("LV", lv)]:
        cells = []
        for k in ks:
            v = d["cells"]["uncoordinated"][str(k)]["viol"]
            cells.append(f"\\textbf{{{v:.4f}}}" if v == 0.0 else f"{v:.4f}")
        body.append(f"{label} & " + " & ".join(cells) + " \\\\")
    body += ["\\bottomrule", "\\end{tabular}"]
    w("model_error.tex", "\n".join(body))

    safe = [k for k in ks
            if all(d["cells"][s][str(k)]["viol"] == 0.0
                   for d in (mv, lv) for s in ("uncoordinated", "urgency"))]
    lo = min(mv["jacobian_ratio"][str(k)] for k in safe)
    hi = max(mv["jacobian_ratio"][str(k)] for k in safe)
    print(f"    [safe on both feeders and both sources: {lo:.2f}x--{hi:.2f}x]")


# --- Table V: the diagnostic ------------------------------------------------


def table_diagnostic() -> None:
    """Two failure modes, both invisible in the violation rate.

    The unprojected row is carried alongside each feeder deliberately. On the LV
    feeder it is numerically identical to the never-refreshed row, which is the
    whole claim sitting in two adjacent lines of a table rather than asserted in
    prose. The never-refreshed row comes from the LV sweep and the
    under-estimated row from the MV one: not a convenience, since the MV
    staleness run predates the freeze counter, and the two failure modes landing
    on *different* feeders is the stronger statement anyway.
    """
    st = load("staleness_kerber.json")["cells"]["1.0"]["uncoordinated"]
    me = load("model_error_case33bw.json")["cells"]["uncoordinated"]
    D = "---"
    rows = [
        ("MV", "No projection at all",
         me["raw"]["viol"], D, D, me["raw"]["soc"]),
        ("MV", "Correct model, $\\tau = 1$",
         me["correct"]["viol"], me["correct"]["infeasible"], 0.0,
         me["correct"]["soc"]),
        ("MV", "Jacobian under-estimated $5\\times$",
         me["0.2"]["viol"], me["0.2"]["infeasible"], me["0.2"]["frozen"],
         me["0.2"]["soc"]),
        None,
        ("LV", "No projection at all",
         st["raw"]["viol"], D, D, st["raw"]["soc"]),
        ("LV", "Correct model, $\\tau = 12$",
         st["12"]["viol"], st["12"]["infeasible"], st["12"]["frozen"],
         st["12"]["soc"]),
        ("LV", "Base point never refreshed",
         st["288"]["viol"], st["288"]["infeasible"], st["288"]["frozen"],
         st["288"]["soc"]),
    ]
    body = ["\\begin{tabular}{llrrrr}", "\\toprule",
            "& Condition & Viol. & Infeas. & Frozen & Service \\\\",
            "\\midrule"]
    for row in rows:
        if row is None:
            body.append("\\addlinespace[1.5pt]")
            continue
        fd, n, v, i, f, s = row
        cells = [x if isinstance(x, str) else f"{x:.4f}" for x in (v, i, f, s)]
        body.append(f"{fd} & {n} & " + " & ".join(cells) + " \\\\")
    body += ["\\bottomrule", "\\end{tabular}"]
    w("diagnostic.tex", "\n".join(body))

    # Guard the sentence the table is meant to license.
    if st["288"]["viol"] != st["raw"]["viol"]:
        print(f"    [note: LV never-refreshed {st['288']['viol']:.4f} vs "
              f"unprojected {st['raw']['viol']:.4f} -- no longer identical]")
    else:
        print("    [LV never-refreshed is numerically identical to unprojected]")


# --- Every number quoted in the running text -------------------------------


def numbers() -> None:
    """Macros for the figures quoted in prose, not just in tables.

    Tables were already generated; the sentences around them were not, and that
    is where a stale number survives longest -- nobody re-reads a paragraph
    against a JSON file. Anything the manuscript asserts numerically is defined
    here and used as a macro, so a re-run either updates the claim or breaks the
    build.
    """
    mv_st = load("staleness_sweep_25ep.json")
    lv_st = load("staleness_kerber.json")
    mv_me = load("model_error_case33bw.json")
    lv_me = load("model_error_kerber.json")
    ph = load("projected_heuristics.json")
    ab = load("ablation/ablation.json")
    tr = load("trace_kerber.json")

    # recovery of the unprojected rate when the base point is never refreshed
    rec, cells = [], 0
    for d, zs in ((mv_st, ["6.0", "8.0", "10.0"]), (lv_st, ["1.0", "2.0", "3.0"])):
        for z in zs:
            for s in d["cells"][z]:
                c = d["cells"][z][s]
                rec.append(c["288"]["viol"] / c["raw"]["viol"])
                cells += 1

    # widest Jacobian error tolerated on both feeders and both sources
    ks = mv_me["scale"]
    safe = [k for k in ks
            if all(d["cells"][s][str(k)]["viol"] == 0.0
                   for d in (mv_me, lv_me) for s in ("uncoordinated", "urgency"))]
    ratios = [mv_me["jacobian_ratio"][str(k)] for k in ks]

    # last cadence at which every in-envelope cell still holds the band exactly
    def last_clean(d, z, s):
        row = d["cells"][z][s]
        clean = [int(r) for r in d["refresh"] if row[str(r)]["viol"] == 0.0]
        return max(clean) if clean else 0

    mv6 = min(last_clean(mv_st, "6.0", s) for s in mv_st["cells"]["6.0"])
    mv8 = [last_clean(mv_st, "8.0", s) for s in mv_st["cells"]["8.0"]]
    lv_all = {last_clean(lv_st, z, s)
              for z in lv_st["cells"] for s in lv_st["cells"][z]}
    assert len(lv_all) == 1, f"LV cliff no longer uniform: {lv_all}"

    me_mv = mv_me["cells"]["uncoordinated"]
    lv1 = lv_st["cells"]["1.0"]["uncoordinated"]
    greedy = ph["uncoordinated+proj"]["aggregate"]["frac_meeting_soc_target_mean"]
    learned = ab["summary"]["projection"]["soc"][0]

    dev = tr["max_abs_dev_stale_vs_unprojected"]
    exp = int(np.floor(np.log10(dev)))

    m = {
        "RecoveryLo": f"{100 * min(rec):.1f}", "RecoveryHi": f"{100 * max(rec):.1f}",
        "NCells": str(cells),
        "JacLo": f"{min(ratios):.2f}", "JacHi": f"{max(ratios):.2f}",
        "SafeLo": f"{min(mv_me['jacobian_ratio'][str(k)] for k in safe):.2f}",
        "SafeHi": f"{max(mv_me['jacobian_ratio'][str(k)] for k in safe):.2f}",
        "MvUnderInfeas": f"{100 * me_mv['0.2']['infeasible']:.1f}",
        "MvUnderFrozen": f"{100 * me_mv['0.2']['frozen']:.1f}",
        "MvUnderService": f"{me_mv['0.2']['soc']:.4f}",
        "MvCorrectService": f"{me_mv['correct']['soc']:.4f}",
        "MvUnderServiceLoss":
            f"{100 * (me_mv['correct']['soc'] - me_mv['0.2']['soc']):.1f}",
        "LvOverServiceLoss": f"{100 * (lv_me['cells']['uncoordinated']['correct']['soc'] - lv_me['cells']['uncoordinated']['5.0']['soc']):.0f}",
        "LvStaleViol": f"{lv1['288']['viol']:.4f}",
        "LvRawViol": f"{lv1['raw']['viol']:.4f}",
        "MvCliff": str(mv6), "MvCliffEightLo": str(min(mv8)),
        "MvCliffEightHi": str(max(mv8)), "LvCliff": str(sorted(lv_all)[0]),
        "ServiceRatio": f"{greedy / learned:.1f}",
        "GreedyService": f"{greedy:.4f}", "LearnedService": f"{learned:.4f}",
        "TraceDev": f"{dev / 10 ** exp:.1f}\\times 10^{{{exp}}}",
        "TraceBelow": str(sum(tr["runs"]["unprojected"]["violating"])),
        "TraceSteps": str(len(tr["runs"]["unprojected"]["vmin"])),
        "Episodes": str(lv_st["episodes"]),
    }
    body = [f"\\newcommand{{\\n{k}}}{{{v}}}" for k, v in m.items()]
    w("numbers.tex", "% generated -- do not edit\n" + "\n".join(body))
    for k in ("RecoveryLo", "RecoveryHi", "SafeLo", "SafeHi", "ServiceRatio",
              "MvCliff", "LvCliff", "TraceDev"):
        print(f"      {k:<18} {m[k]}")


def main() -> int:
    print("generating paper tables from results/")
    table_testbeds()
    table_layer_not_learner()
    table_staleness()
    table_model_error()
    table_diagnostic()
    numbers()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
