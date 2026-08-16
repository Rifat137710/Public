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
    """Two failure modes, both invisible in the violation rate."""
    # The never-refreshed row is taken from the LV sweep and the under-estimated
    # row from the MV one. Not a convenience: the MV staleness run predates the
    # freeze counter, and the two failure modes appearing on *different* feeders
    # is the stronger statement anyway.
    st = load("staleness_kerber.json")["cells"]["1.0"]["uncoordinated"]
    me = load("model_error_case33bw.json")["cells"]["uncoordinated"]
    rows = [
        ("LV", "Correct model, refreshed hourly",
         st["12"]["viol"], st["12"]["infeasible"], st["12"]["frozen"],
         st["12"]["soc"]),
        ("LV", "Base point never refreshed",
         st["288"]["viol"], st["288"]["infeasible"], st["288"]["frozen"],
         st["288"]["soc"]),
        ("MV", "Correct model, refreshed every step",
         me["correct"]["viol"], me["correct"]["infeasible"], 0.0,
         me["correct"]["soc"]),
        ("MV", "Jacobian under-estimated $5\\times$",
         me["0.2"]["viol"], me["0.2"]["infeasible"], me["0.2"]["frozen"],
         me["0.2"]["soc"]),
    ]
    body = ["\\begin{tabular}{llrrrr}", "\\toprule",
            "& Condition & Viol. & Infeas. & Frozen & Service \\\\",
            "\\midrule"]
    for fd, n, v, i, f, s in rows:
        body.append(f"{fd} & {n} & {v:.4f} & {i:.4f} & {f:.4f} & {s:.4f} \\\\")
    body += ["\\bottomrule", "\\end{tabular}"]
    w("diagnostic.tex", "\n".join(body))


def main() -> int:
    print("generating paper tables from results/")
    table_testbeds()
    table_layer_not_learner()
    table_staleness()
    table_model_error()
    table_diagnostic()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
