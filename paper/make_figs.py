"""Build the paper figures directly from the production result files.

Every value plotted here is read from ../results/production/*.pkl, which are the
pickles written by the notebooks during the run of 2026-08-19, or parsed from
../results/e11b_log_20260819.txt for the per-hour angle tables (E11b stores only
per-seed summaries in its pickle). Nothing is transcribed by hand, so the figures
and the tables in the paper cannot drift apart.

    python3 make_figs.py

Writes fig1..fig5 as PDF (for LaTeX) and PNG (for quick review).

Each load level carries its own colour pair (see PAIR below) so the mild and
aggressive panels of a figure are never mistaken for one another. Grey is reserved
for limits and the untreated feeder.
"""

import os
import pickle
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
PROD = os.path.join(RES, "production")

COL, DBL = 3.5, 7.16          # IEEE single- and double-column widths, inches

# Each load level gets its own pair so the two panels of a figure are never
# confused. Within a panel, the darker/cooler hue is the reference or optimum and
# the warmer hue is the learned policy; line style repeats the distinction so the
# figures also read in greyscale. The two pairs are validated separately because
# they never appear side by side.
PAIR = {"mild": ("#2a78d6", "#eb6834"),     # blue  / orange
        "aggr": ("#008300", "#4a3aa7")}     # green / violet
LIM = "#6b6b6b"                             # limits, untreated feeder

plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "lines.linewidth": 1.3,
    "lines.markersize": 3.5,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linewidth": 0.4,
    "figure.dpi": 150,
})


def load(name):
    with open(os.path.join(PROD, name), "rb") as fh:
        return pickle.load(fh)


R = load("results.pkl")["results"]
E13 = load("e13_results.pkl")["E13"]


def mean_ci(rows, key="IntViol"):
    v = np.array([r[key] for r in rows], dtype=float)
    ci = 1.96 * v.std(ddof=1) / np.sqrt(v.size) if v.size > 1 else 0.0
    return v.mean(), ci


def save(fig, stem):
    fig.savefig(os.path.join(HERE, stem + ".pdf"), bbox_inches="tight")
    fig.savefig(os.path.join(HERE, stem + ".png"), bbox_inches="tight", dpi=200)
    plt.close(fig)
    print("wrote", stem)


# --------------------------------------------------------------------------- #
# Fig. 1  Violation split into its energy and control parts
# --------------------------------------------------------------------------- #
def fig1():
    E2 = R["E2 multi-hub fleet-constrained"]
    E8 = R["E8 optimized ceiling"]
    E13m = mean_ci(E13["mild/100000"])[0]
    E13a = mean_ci(E13["aggr/100000"])[0]

    def col(case, e8key):
        d = E2[case]
        return [
            mean_ci(d["Baseline"])[0],
            sum(v["IntViol"] for v in E8[e8key]["raw"].values()),
            mean_ci(d["Droop (unconstr)"])[0],
            mean_ci(d["Droop"])[0],
        ]

    labels = ["No V2G", "Upper\nbound", "Droop,\nenergy\nunlimited",
              "Droop,\nreal fleet", "Learned,\nreal fleet"]
    mild = col("mild", "multi_mild") + [E13m]
    aggr = col("aggr", "multi_aggr") + [E13a]

    fig, axes = plt.subplots(1, 2, figsize=(DBL, 2.35))
    for ax, vals, ttl, case in ((axes[0], mild, "Mild peak", "mild"),
                                (axes[1], aggr, "Aggressive peak", "aggr")):
        x = np.arange(len(vals))
        ax.bar(x, vals, width=0.62, color=PAIR[case][0], edgecolor="white",
               linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylim(0, max(vals) * 1.22)
        for xi, v in zip(x, vals):
            ax.text(xi, v + max(vals) * 0.025, f"{v:.2f}", ha="center", fontsize=7)
        ax.set_title(ttl)
        ax.set_ylabel("integrated violation (p.u.$\\cdot$h)")
    fig.tight_layout()
    save(fig, "fig1_decomposition")


# --------------------------------------------------------------------------- #
# Fig. 2  Hourly worst-phase voltage: untreated vs optimized five-hub dispatch
# --------------------------------------------------------------------------- #
def fig2():
    E5 = R["E5+E7 ceiling and P/Q"]
    E8 = R["E8 optimized ceiling"]

    fig, axes = plt.subplots(2, 1, figsize=(COL, 2.45), sharex=True)
    for ax, key, ttl, case in ((axes[0], "multi_mild", "Mild peak", "mild"),
                               (axes[1], "multi_aggr", "Aggressive peak", "aggr")):
        cool, warm = PAIR[case]
        ph5 = E5[key]["per_hour"]
        raw = E8[key]["raw"]
        hours = sorted(raw)
        base = [ph5[h]["PQ"]["Vmin"][0] for h in hours]
        opt = [raw[h]["Vmin"] for h in hours]
        ax.plot(hours, base, ls="--", color=warm, label="no V2G")
        ax.plot(hours, opt, ls="-", color=cool, label="optimized dispatch")
        ax.axhline(0.95, color=LIM, ls=":", lw=1.0, label="0.95 p.u. limit")
        ax.set_title(ttl, pad=3)
        ax.set_xticks(range(6, 24, 2))
        lo, hi = min(base + opt), max(base + opt)
        ax.set_ylim(lo - 0.42 * (hi - lo), hi + 0.08 * (hi - lo))
        ax.legend(loc="lower left", ncol=3, fontsize=6, framealpha=0.9,
                  handlelength=1.3, borderpad=0.25, columnspacing=0.9,
                  handletextpad=0.4)
    axes[1].set_xlabel("hour of day")
    fig.supylabel("worst-phase voltage (p.u.)", fontsize=8, x=0.005)
    fig.tight_layout(h_pad=0.8)
    save(fig, "fig2_ceiling")


# --------------------------------------------------------------------------- #
# Fig. 4  Violation against training budget
# --------------------------------------------------------------------------- #
def fig3():
    ckpts = [20000, 40000, 60000, 80000, 100000]
    fig, axes = plt.subplots(1, 2, figsize=(COL, 2.25))
    for ax, case, ttl in ((axes[0], "mild", "Mild peak"),
                          (axes[1], "aggr", "Aggressive peak")):
        cool, warm = PAIR[case]
        m = [mean_ci(E13[f"{case}/{c}"]) for c in ckpts]
        y = [a for a, _ in m]
        e = [b for _, b in m]
        dr = mean_ci(E13[f"{case}/droop"])[0]
        bl = mean_ci(E13[f"{case}/baseline"])[0]
        p1 = ax.errorbar(ckpts, y, yerr=e, fmt="o-", color=warm, capsize=2.0,
                         label="learned")
        p2 = ax.axhline(dr, color=cool, ls="--", lw=1.2, label="droop")
        p3 = ax.axhline(bl, color=LIM, ls=":", lw=1.2, label="no V2G")
        lo = min(min(y) - max(e) * 2, dr)
        hi = max(max(y) + max(e) * 2, bl)
        pad = (hi - lo) * 0.30
        ax.set_ylim(lo - pad * 0.3, hi + pad)
        ax.set_xlabel("training steps (thousands)")
        ax.set_ylabel("integrated violation (p.u.$\\cdot$h)")
        ax.set_title(ttl)
        ax.set_xticks(ckpts[::2])
        ax.set_xticklabels([str(c // 1000) for c in ckpts[::2]])
        ax.legend(handles=[p1, p2, p3], loc="upper right", fontsize=6,
                  framealpha=0.9, handlelength=1.0, borderpad=0.18,
                  labelspacing=0.15, handletextpad=0.4, borderaxespad=0.25)
    fig.tight_layout()
    save(fig, "fig4_learning")


# --------------------------------------------------------------------------- #
# Fig. 3  Commanded injection angle against the voltage-optimal angle
# --------------------------------------------------------------------------- #
_HDR = re.compile(r"per-hour P/Q angle at (\d+) steps -- (\w+), seed (\d+)")


def parse_e11b_tables(path):
    """Return {(case, seed): {hour: (agent_angle, optimal_angle)}} at the last budget."""
    out, cur = {}, None
    with open(path) as fh:
        for line in fh:
            m = _HDR.search(line)
            if m:
                cur = {}
                out[(m.group(2), int(m.group(3)))] = cur
                continue
            if cur is None:
                continue
            f = line.split()
            if len(f) == 7 and f[0].isdigit():
                if f[2] == "-":
                    continue
                cur[int(f[0])] = (float(f[2]), float(f[6]))
            elif line.strip() and not line.lstrip().startswith(("h ", "---")):
                if not line.strip()[0].isdigit():
                    cur = None
    return out


def fig4():
    tab = parse_e11b_tables(os.path.join(RES, "e11b_log_20260819.txt"))
    fig, axes = plt.subplots(1, 2, figsize=(DBL, 2.45))
    for ax, case, ttl in ((axes[0], "mild", "Mild peak"),
                          (axes[1], "aggr", "Aggressive peak")):
        cool, warm = PAIR[case]
        seeds = [s for (c, s) in tab if c == case]
        hours = sorted({h for s in seeds for h in tab[(case, s)]})
        ag, op = [], []
        for h in hours:
            a = [tab[(case, s)][h][0] for s in seeds if h in tab[(case, s)]]
            o = [tab[(case, s)][h][1] for s in seeds if h in tab[(case, s)]]
            ag.append(np.mean(a))
            op.append(np.mean(o))
        ax.plot(hours, op, ls="--", marker="s", color=cool, markerfacecolor="white",
                label="voltage-optimal")
        ax.plot(hours, ag, ls="-", marker="o", color=warm, label="commanded by policy")
        ax.axhline(0, color=LIM, lw=1.0, label="pure active power")
        ax.axhline(38.7, color=LIM, ls=":", lw=1.0, label="hub rating ratio")
        ax.set_xlabel("hour of day")
        ax.set_ylabel("injection angle (deg)")
        ax.set_title(ttl)
        ax.set_ylim(-25, 108)
        ax.set_xticks(range(6, 24, 2))
        ax.legend(loc="upper left", ncol=2, fontsize=6.5, framealpha=0.9,
                  handlelength=1.4, borderpad=0.3, columnspacing=1.0)
    fig.tight_layout()
    save(fig, "fig3_pq")


# --------------------------------------------------------------------------- #
# Fig. 5  Violation against battery throughput as the wear weight is swept
# --------------------------------------------------------------------------- #
def fig5():
    pts = R["E3 frontier mild"]
    rl = [p for p in pts if p["w"] != "droop"]
    dr = [p for p in pts if p["w"] == "droop"]
    rl.sort(key=lambda p: p["w"])

    # the low-weight points sit almost on top of one another, so the labels are
    # placed on alternating sides to keep them readable
    offs = {0.0: (-3, -11), 1.0: (-13, 3), 3.0: (-13, -4), 10.0: (-3, 6),
            30.0: (5, -3), 100.0: (-3, 6), 300.0: (-3, 6)}

    cool, warm = PAIR["mild"]
    fig, ax = plt.subplots(figsize=(COL, 2.25))
    ax.plot([p["Thru"] for p in rl], [p["IntViol"] for p in rl], "o-", color=warm,
            label="learned policy, wear weight swept")
    for p in rl:
        ax.annotate(f'{p["w"]:g}', (p["Thru"], p["IntViol"]), fontsize=6.5,
                    xytext=offs.get(p["w"], (4, 4)), textcoords="offset points")
    if dr:
        ax.plot([p["Thru"] for p in dr], [p["IntViol"] for p in dr], "s",
                ms=6, color=cool, label="droop")
    ax.set_xlabel("battery throughput (kWh/day)")
    ax.set_ylabel("integrated violation (p.u.$\\cdot$h)")
    ax.set_xlim(1000, 7300)
    ax.legend(loc="lower right")
    fig.tight_layout()
    save(fig, "fig5_frontier")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
