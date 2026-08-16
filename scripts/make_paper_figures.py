"""Draw the paper's figures straight from the result files.

Same rule as scripts/make_paper_tables.py: nothing is typed in by hand. Axis
limits, annotated cliff locations and the shaded tolerance window are all
derived from results/*.json, so a re-run that moves a number moves the figure
with it instead of leaving a caption quietly describing the previous campaign.

    python scripts/make_paper_figures.py

Writes paper/figures/*.pdf, sized for a single IEEEtran column (3.4 in).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "figures"

COL = 3.4          # IEEEtran single column, inches
MV, LV = "#0B4F6C", "#C1440E"
GREY, BAND = "#6B6B6B", "#D9E8EF"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["STIXGeneral", "Liberation Serif", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 6.5,
    "axes.linewidth": 0.6,
    "grid.linewidth": 0.4,
    "lines.linewidth": 1.1,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "legend.frameon": False,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.01,
    "pdf.fonttype": 42,
})


def load(name: str) -> dict:
    return json.loads((ROOT / "results" / name).read_text())


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=200)
    plt.close(fig)
    print(f"  wrote paper/figures/{name}.pdf")


def _tidy(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, color="#CCCCCC", alpha=0.55, linewidth=0.4)
    ax.set_axisbelow(True)


# --- Fig. 1: where the two halves of the linearisation come from ------------


def fig_loop() -> None:
    """The argument of the paper, before any data: the layer has two inputs and
    they are procured differently. One is computed, the other is observed."""
    fig, ax = plt.subplots(figsize=(COL, 1.9))
    ax.set_xlim(0, 10.7)
    ax.set_ylim(0, 5.35)
    ax.axis("off")

    def box(x, y, w, h, text, fc, ec, fs=7):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.06,rounding_size=0.12",
                                    linewidth=0.8, facecolor=fc, edgecolor=ec))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

    def arrow(x0, y0, x1, y1, label=None, ls="-", lx=0, ly=0.22, color="black"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1),
                                     arrowstyle="-|>", mutation_scale=7,
                                     linewidth=0.8, linestyle=ls, color=color,
                                     shrinkA=0, shrinkB=0))
        if label:
            ax.text((x0 + x1) / 2 + lx, (y0 + y1) / 2 + ly, label,
                    ha="center", va="center", fontsize=6.5)

    box(0.15, 3.85, 2.55, 1.10, "Controller\n(RL / heuristic)", "#FFFFFF", GREY)
    box(3.60, 3.85, 2.75, 1.10, "Safety\nprojection", "#EAF2F6", MV)
    box(7.35, 3.85, 2.20, 1.10, "Feeder", "#FFFFFF", GREY)
    arrow(2.70, 4.40, 3.60, 4.40, r"$u^{\mathrm{req}}$")
    arrow(6.35, 4.40, 7.35, 4.40, r"$u^{\star}$")

    box(0.15, 1.60, 4.05, 1.05,
        "Jacobian\n$\\partial V/\\partial P,\\ \\partial V/\\partial Q$",
        "#FFFFFF", MV, fs=6.8)
    box(5.15, 1.60, 4.05, 1.05,
        "Base point\n$(v^{0},\\, p^{0},\\, q^{0})$", "#FDEDE6", LV, fs=6.8)
    arrow(2.20, 2.65, 4.15, 3.85)
    arrow(7.15, 2.65, 5.75, 3.85)

    box(0.15, 0.05, 4.05, 0.95, "network model\ncomputed offline", "#F4F4F4",
        GREY, fs=6.5)
    box(5.15, 0.05, 4.05, 0.95, "metering\nobserved, age $\\tau$", "#FFF6F2",
        LV, fs=6.5)
    arrow(2.20, 1.00, 2.20, 1.60)
    arrow(7.15, 1.00, 7.15, 1.60)

    # The measurement path closes the loop from the feeder, and is the only
    # input the designer cannot buy with compute -- routed clear of the boxes.
    ax.add_patch(FancyArrowPatch((8.45, 3.85), (9.95, 3.85),
                                 arrowstyle="-", linewidth=0.8,
                                 linestyle=(0, (2.5, 2)), color=LV,
                                 shrinkA=0, shrinkB=0))
    ax.add_patch(FancyArrowPatch((9.95, 3.85), (9.95, 0.52),
                                 arrowstyle="-", linewidth=0.8,
                                 linestyle=(0, (2.5, 2)), color=LV,
                                 shrinkA=0, shrinkB=0))
    ax.add_patch(FancyArrowPatch((9.95, 0.52), (9.28, 0.52),
                                 arrowstyle="-|>", mutation_scale=7,
                                 linewidth=0.8, linestyle=(0, (2.5, 2)),
                                 color=LV, shrinkA=0, shrinkB=0))
    ax.text(10.15, 2.2, "measurement", fontsize=6.2, color=LV, rotation=90,
            ha="center", va="center")
    save(fig, "fig_loop")


# --- Fig. 2: the cliff ------------------------------------------------------


def fig_cliff() -> dict:
    """Every cell's violation rate as a fraction of its own unprojected rate.

    Normalising is what lets the two feeders share an axis at all: their
    absolute rates differ threefold and their impedances by an order of
    magnitude. Divided by the rate the same feeder produces with no projection
    whatsoever, every cell answers one question -- how much of the unprotected
    outcome has come back -- and the twelve curves can be read together.
    """
    sets = [("MV feeder (IEEE 33-bus)", "staleness_sweep_25ep.json",
             ["6.0", "8.0", "10.0"], MV),
            ("LV feeder (Kerber Dorfnetz)", "staleness_kerber.json",
             ["1.0", "2.0", "3.0"], LV)]
    fig, ax = plt.subplots(figsize=(COL, 2.15))
    notes, recovery, envelope = {}, [], []
    TOL = 1e-3      # what counts as "still holding" for the shaded band

    for label, fn, zs, colour in sets:
        d = load(fn)
        refresh = [int(r) for r in d["refresh"]]
        last_clean, first = [], True
        for z in zs:
            for src, ls, mk in (("uncoordinated", "-", "o"),
                                ("urgency", (0, (3, 1.6)), "s")):
                if src not in d["cells"][z]:
                    continue
                row = d["cells"][z][src]
                raw = row["raw"]["viol"]
                y = [row[str(r)]["viol"] / raw for r in refresh]
                ax.plot(refresh, y, linestyle=ls, color=colour, marker=mk,
                        markersize=2.1, markeredgewidth=0, linewidth=0.85,
                        alpha=0.85, label=label if first else None)
                first = False
                recovery.append(y[-1])
                clean = [r for r in refresh if row[str(r)]["viol"] == 0.0]
                last_clean.append(max(clean) if clean else 0)
                # A cell is "within the envelope" if the layer can hold the band
                # at all, i.e. at the freshest cadence tested. Two MV cells at
                # Z=10% cannot, and they are excluded from the band -- and
                # labelled in the figure rather than dropped from it.
                if row[str(refresh[0])]["viol"] == 0.0:
                    envelope.append({r: row[str(r)]["viol"] for r in refresh})
        notes[label.split()[0]] = sorted(set(last_clean))

    refresh = [int(r) for r in load(sets[0][1])["refresh"]]
    holding = [r for r in refresh if all(c[r] <= TOL for c in envelope)]
    band = max(holding)

    ax.axhline(1.0, color=GREY, linewidth=0.6, linestyle=(0, (3, 2)))
    ax.text(330, 1.04, "as if unprotected", fontsize=6.2, color=GREY,
            ha="right")
    ax.axvspan(0.85, band, color="#E7F1E7", zorder=0)
    ax.text(np.sqrt(0.85 * band), 0.80, "protection\nintact", fontsize=6.2,
            ha="center", va="center", color="#3C6E3C", linespacing=1.25)

    mv = load("staleness_sweep_25ep.json")["cells"]["10.0"]["uncoordinated"]
    ax.annotate("MV $Z_\\mathrm{sub}\\!=\\!10\\%$:\nnever protects, at any $\\tau$",
                xy=(1.35, mv["1"]["viol"] / mv["raw"]["viol"]),
                xytext=(1.15, 0.50), fontsize=6, color=MV, ha="left",
                linespacing=1.25,
                arrowprops=dict(arrowstyle="-", linewidth=0.5, color=MV))

    ax.set_xscale("log")
    ax.set_xticks([1, 3, 12, 24, 48, 288])
    ax.set_xticklabels(["1", "3", "12", "24", "48", "288"])
    ax.minorticks_off()
    ax.set_xlim(0.85, 360)
    ax.set_ylim(-0.04, 1.36)
    ax.set_xlabel("base-point age $\\tau$ (control steps of 5 min)")
    ax.set_ylabel("violation rate $\\div$ unprojected rate")
    ax.legend(loc="upper left", handlelength=1.6, borderpad=0.15,
              labelspacing=0.2, handletextpad=0.4)
    _tidy(ax)
    save(fig, "fig_cliff")
    print(f"    [last clean interval: {notes}]")
    print(f"    [band: all {len(envelope)} in-envelope cells <= {TOL} "
          f"out to tau={band}]")
    print(f"    [recovery at tau=288: {100*min(recovery):.1f}--"
          f"{100*max(recovery):.1f}% over {len(recovery)} cells]")
    return notes


# --- Fig. 3: one episode, three controllers ---------------------------------


def fig_trace() -> float:
    d = load("trace_kerber.json")
    step_h = d["step_minutes"] / 60.0
    runs = d["runs"]
    t = np.arange(len(runs["unprojected"]["vmin"])) * step_h
    lo = d["voltage_lower_pu"]

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(COL, 2.75), sharex=True,
                                 gridspec_kw={"height_ratios": [1.5, 1]})

    v_all = np.concatenate([runs[k]["vmin"] for k in runs])
    a1.axhspan(v_all.min() - 0.004, lo, color="#FBE9E7", zorder=0)
    a1.axhline(lo, color=LV, linewidth=0.6, linestyle=(0, (3, 2)))
    # The unprojected run is drawn as a wide halo rather than a line: the point
    # of the panel is that the never-refreshed run sits inside it everywhere.
    a1.plot(t, runs["unprojected"]["vmin"], color=GREY, linewidth=2.8,
            alpha=0.32, solid_capstyle="round", label="no projection")
    a1.plot(t, runs["refresh_288"]["vmin"], color=LV, linewidth=0.9,
            linestyle=(0, (2.5, 1.6)), label="$\\tau = 288$, never refreshed")
    a1.plot(t, runs["refresh_1"]["vmin"], color=MV, linewidth=1.0,
            label="$\\tau = 1$, refreshed")
    a1.set_ylabel("min. bus voltage (p.u.)")
    a1.set_ylim(v_all.min() - 0.004, v_all.max() + 0.011)
    a1.text(23.6, lo + 0.0018, "0.95 p.u.", fontsize=6, color=LV, ha="right")
    a1.legend(loc="lower left", ncol=1, handlelength=1.7, borderpad=0.1,
              labelspacing=0.16, handletextpad=0.4)
    _tidy(a1)

    a2.plot(t, runs["unprojected"]["p_kw"], color=GREY, linewidth=2.8,
            alpha=0.32, solid_capstyle="round")
    a2.plot(t, runs["refresh_288"]["p_kw"], color=LV, linewidth=0.9,
            linestyle=(0, (2.5, 1.6)))
    a2.plot(t, runs["refresh_1"]["p_kw"], color=MV, linewidth=1.0)
    a2.set_ylabel("station power (kW)\n($<0$: charging)")
    a2.set_xlabel("time of day (h)")
    a2.set_xlim(0, 24)
    a2.set_xticks([0, 4, 8, 12, 16, 20, 24])
    a2.annotate("layer curtails", xy=(19.4, -46), xytext=(12.2, -22),
                fontsize=6, color=MV,
                arrowprops=dict(arrowstyle="->", linewidth=0.5, color=MV))
    _tidy(a2)

    save(fig, "fig_trace")
    dev = d["max_abs_dev_stale_vs_unprojected"]
    print(f"    [stale vs unprojected, max deviation {dev:.2e} p.u.]")
    return dev


# --- Fig. 4: model error ----------------------------------------------------


def fig_model_error() -> tuple[float, float]:
    mv, lv = load("model_error_case33bw.json"), load("model_error_kerber.json")
    ks = mv["scale"]

    safe = [k for k in ks
            if all(d["cells"][s][str(k)]["viol"] == 0.0
                   for d in (mv, lv) for s in ("uncoordinated", "urgency"))]
    band = (min(mv["jacobian_ratio"][str(k)] for k in safe),
            max(mv["jacobian_ratio"][str(k)] for k in safe))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(COL, 2.5), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1]})
    for ax in (a1, a2):
        ax.axvspan(*band, color="#E8F3E8", zorder=0)
        ax.axvline(1.0, color=GREY, linewidth=0.5, linestyle=(0, (1, 2)))

    for label, d, c, mk in (("MV", mv, MV, "o"), ("LV", lv, LV, "s")):
        x = [d["jacobian_ratio"][str(k)] for k in ks]
        a1.plot(x, [d["cells"]["uncoordinated"][str(k)]["viol"] for k in ks],
                color=c, marker=mk, markersize=2.4, markeredgewidth=0,
                label=f"{label} feeder")
        a2.plot(x, [d["cells"]["uncoordinated"][str(k)]["soc"] for k in ks],
                color=c, marker=mk, markersize=2.4, markeredgewidth=0)
        a2.plot(x, [d["cells"]["uncoordinated"][str(k)]["frozen"] for k in ks],
                color=c, marker=mk, markersize=2.0, markeredgewidth=0,
                linestyle=(0, (2.5, 1.6)), alpha=0.75)

    a1.set_ylabel("violation step rate")
    a1.set_ylim(-0.003, 0.038)
    a1.legend(loc="upper right", handlelength=1.4, borderpad=0.1,
              labelspacing=0.15, handletextpad=0.4)
    a1.text(np.sqrt(band[0] * band[1]), 0.032, "safe on both", fontsize=6,
            ha="center", color="#3C6E3C")
    _tidy(a1)

    a2.set_xscale("log")
    a2.set_xticks([0.2, 0.5, 1, 2, 5])
    a2.set_xticklabels(["0.2", "0.5", "1", "2", "5"])
    a2.minorticks_off()
    a2.set_xlabel("Jacobian magnitude relative to truth ($\\times$)")
    a2.set_ylabel("service, freeze rate")
    a2.set_ylim(-0.03, 0.99)
    a2.text(0.215, 0.86, "service (solid)", fontsize=6, color=GREY)
    a2.text(0.215, 0.20, "frozen (dashed)", fontsize=6, color=GREY)
    _tidy(a2)

    save(fig, "fig_model_error")
    print(f"    [safe window {band[0]:.2f}x--{band[1]:.2f}x]")
    return band


def main() -> int:
    print("generating paper figures from results/")
    fig_loop()
    fig_cliff()
    fig_trace()
    fig_model_error()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
