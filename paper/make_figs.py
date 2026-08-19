"""Figures for the ISGT Asia 2026 paper.

Numbers are transcribed from the production logs in ../results/ so the figures cannot
silently drift from the tables:

  run_log_20260819.txt   E0, E2, E3, E6, E8, E9, E5/E7, E1, E10, E11
  e12_log_20260819.txt   E12
  e13_log_20260819.txt   E13

Everything is drawn at IEEE column width (3.5 in) or full width (7.16 in), 8 pt labels,
so nothing has to be rescaled inside LaTeX -- rescaling is what makes conference figures
illegible.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7,
    "font.family": "serif", "font.serif": ["DejaVu Serif"],
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "savefig.dpi": 400, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})
COL, FULL = 3.5, 7.16

# --------------------------------------------------------------------------- #
# Fig. 1 -- the decomposition. The paper's central claim in one picture.
# --------------------------------------------------------------------------- #
# integrated two-sided violation, p.u.-h, multi-hub, day total
MILD = dict(base=45.61, ceil=0.00, droop_u=4.15, droop=42.77, rl=43.56)
AGGR = dict(base=171.21, ceil=17.99, droop_u=50.14, droop=165.83, rl=168.41)
# throughput, kWh
THRU = dict(mild=(9264, 1342), aggr=(27814, 1582))       # (unconstrained want, delivered)

fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.5))
labels = ["No\nV2G", "Physics\nceiling", "Droop\n(energy\nunlimited)",
          "Droop\n(fleet)", "RL\n(fleet)"]
keys = ["base", "ceil", "droop_u", "droop", "rl"]
cols = ["0.55", "tab:green", "tab:olive", "tab:red", "tab:blue"]

for ax, (D, name) in zip(axes, ((MILD, "(a) mild peak"), (AGGR, "(b) aggressive peak"))):
    v = [D[k] for k in keys]
    bars = ax.bar(range(5), v, color=cols, width=0.68, edgecolor="k", linewidth=0.4)
    for i, (b, val) in enumerate(zip(bars, v)):
        ax.text(b.get_x() + b.get_width() / 2, val + max(v) * 0.025, f"{val:.2f}",
                ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(5)); ax.set_xticklabels(labels, fontsize=6.2)
    ax.set_ylabel("integrated violation (p.u.$\\cdot$h)")
    ax.set_title(name)
    ax.set_xlim(-0.6, 6.9)
    ax.set_ylim(0, max(v) * 1.20)
    # guide lines out to the annotation lane, then two vertical spans
    for y in (D["droop_u"], D["droop"], D["rl"]):
        ax.plot([-0.4, 6.35], [y, y], color="0.6", lw=0.5, ls=(0, (4, 3)), zorder=0)
    # energy span
    ax.annotate("", xy=(4.85, D["droop_u"]), xytext=(4.85, D["droop"]),
                arrowprops=dict(arrowstyle="<->", color="k", lw=1.0))
    ax.text(5.0, (D["droop_u"] + D["droop"]) / 2,
            f"energy\n{D['droop']-D['droop_u']:.1f}",
            fontsize=6.5, va="center", ha="left")
    # control span -- deliberately drawn to the same scale, which is the point
    lo_c, hi_c = sorted((D["droop"], D["rl"]))
    ax.plot([6.15, 6.15], [lo_c, hi_c], color="k", lw=2.2, solid_capstyle="butt")
    ax.annotate(f"control {abs(D['rl']-D['droop']):.1f}",
                xy=(6.15, (lo_c + hi_c) / 2), xytext=(6.05, max(v) * 0.60),
                fontsize=6.5, ha="right", va="center", rotation=90,
                arrowprops=dict(arrowstyle="->", color="k", lw=0.7,
                                shrinkA=2, shrinkB=2))

fig.tight_layout()
fig.savefig("fig1_decomposition.pdf"); fig.savefig("fig1_decomposition.png", dpi=200)
print("fig1_decomposition.pdf")

# --------------------------------------------------------------------------- #
# Fig. 2 -- achievable ceiling per hour (E8 / E5), multi-hub
# --------------------------------------------------------------------------- #
H = list(range(6, 24))
# worst-phase voltage with no injection, and best reachable under optimized dispatch
NOINJ_M = [.7756, .7565, .7409, .7301, .7194, .7126, .7075, .7050, .7009, .6960,
           .6885, .6817, .6779, .6830, .6960, .7276, .7529, .7756]
OPT_M = [1.05, 1.05, 1.05, .9521, .9524, .9504, .9507, .9524, .9535, .9519,
         .9507, .9508, .9511, .9528, .9519, .9503, 1.05, 1.05]
NOINJ_A = [.8194, .7565, .6960, .6605, .6316, .6170, .6060, .5989, .5883, .5749,
           .5567, .5417, .5316, .5442, .5749, .6316, .6817, .8194]
OPT_A = [.9518, .9529, .9469, .9146, .8876, .8662, .8458, .8323, .8158, .7969,
         .7864, .7421, .7290, .7466, .7969, .9011, .9508, .9518]

fig, ax = plt.subplots(figsize=(COL, 2.15))
ax.plot(H, OPT_M, "o-", ms=3, lw=1.2, color="tab:blue", label="reachable, mild")
ax.plot(H, NOINJ_M, "--", lw=1.0, color="tab:blue", alpha=0.65, label="no V2G, mild")
ax.plot(H, OPT_A, "s-", ms=3, lw=1.2, color="tab:red", label="reachable, aggressive")
ax.plot(H, NOINJ_A, ":", lw=1.0, color="tab:red", alpha=0.75, label="no V2G, aggressive")
ax.axhline(0.95, color="k", lw=0.9, ls="-.", label="ANSI lower limit")
ax.set_xlabel("hour of day"); ax.set_ylabel("worst-phase voltage (p.u.)")
ax.set_xlim(6, 23); ax.set_xticks(range(6, 24, 3))
ax.legend(loc="lower left", ncol=1, framealpha=0.9)
fig.tight_layout(); fig.savefig("fig2_ceiling.pdf"); fig.savefig("fig2_ceiling.png", dpi=200)
print("fig2_ceiling.pdf")

# --------------------------------------------------------------------------- #
# Fig. 3 -- learning curve (E13)
# --------------------------------------------------------------------------- #
CK = [20000, 40000, 60000, 80000, 100000]
M_MU = [45.05, 44.74, 44.09, 44.33, 43.56]; M_CI = [.23, .23, .27, .39, .27]
A_MU = [169.20, 168.21, 168.27, 168.25, 168.41]; A_CI = [.77, .50, .38, .31, .36]

fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.1))
for ax, (mu, ci, dr, bs, nm) in zip(
        axes, ((M_MU, M_CI, 42.77, 45.61, "(a) mild peak"),
               (A_MU, A_CI, 165.83, 171.21, "(b) aggressive peak"))):
    ax.errorbar([c / 1000 for c in CK], mu, yerr=ci, fmt="o-", ms=3.5, lw=1.2,
                capsize=2.5, color="tab:blue", label="learned policy")
    ax.axhline(dr, color="tab:red", ls="--", lw=1.1, label=f"droop ({dr:.1f})")
    ax.axhline(bs, color="0.45", ls=":", lw=1.1, label=f"no V2G ({bs:.1f})")
    ax.set_xlabel("training steps (thousands)")
    ax.set_ylabel("integrated violation (p.u.$\\cdot$h)")
    lo = min(min(mu) - max(ci), dr); hi = max(max(mu) + max(ci), bs)
    pad = (hi - lo) * 0.12
    ax.set_ylim(lo - pad, hi + pad * 2.6)
    ax.set_title(nm); ax.legend(loc="upper right", framealpha=0.95)
fig.tight_layout(); fig.savefig("fig3_learning.pdf"); fig.savefig("fig3_learning.png", dpi=200)
print("fig3_learning.pdf")

# --------------------------------------------------------------------------- #
# Fig. 4 -- degradation frontier (E3), mild
# --------------------------------------------------------------------------- #
W = [0, 1, 3, 10, 30, 100, 300]
IV = [44.94, 45.18, 44.85, 46.01, 44.83, 45.08, 45.45]
TH = [6188, 6048, 5948, 6401, 6315, 5008, 2449]

fig, ax = plt.subplots(figsize=(COL, 2.1))
ax.plot(TH, IV, "o", ms=5, color="tab:blue")
OFF = {0: (4, -8), 1: (2, 5), 3: (-9, -8), 10: (-4, 6), 30: (5, -3),
       100: (3, 5), 300: (3, 5)}
for w, t, v in zip(W, TH, IV):
    ax.annotate(f"{w:g}", (t, v), fontsize=6.5, xytext=OFF[w],
                textcoords="offset points")
ax.plot([TH[0], TH[-1]], [IV[0], IV[-1]], "-", lw=1.0, color="tab:blue", alpha=0.5)
ax.plot(1342, 42.77, "s", ms=6, color="tab:red", label="droop")
ax.axhspan(min(IV), max(IV), color="tab:blue", alpha=0.08)
ax.text(3550, max(IV) - 0.07, "2.6% violation band", fontsize=6.5,
        color="tab:blue")
ax.set_xlabel("battery throughput (kWh/day)")
ax.set_ylabel("integrated violation (p.u.$\\cdot$h)")
ax.legend(loc="lower right")
fig.tight_layout(); fig.savefig("fig4_frontier.pdf"); fig.savefig("fig4_frontier.png", dpi=200)
print("fig4_frontier.pdf")

# --------------------------------------------------------------------------- #
# Fig. 5 -- P/Q allocation (E11 at 20k; refreshed from E11b when it lands)
# --------------------------------------------------------------------------- #
HRS = list(range(6, 24))
AG_M = [-66.9, 50.4, 44.8, 44.3, 41.0, 45.7, 37.8, 35.1, 42.8, 43.9, 47.9, 51.8,
        43.8, 36.4, 31.0, 16.5, 5.2, 5.7]
OP_M = [65.0, 30.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 30.0, 35.0, 35.0, 35.0,
        35.0, 35.0, 35.0, 30.0, 75.0, 90.0]
AG_A = [12.3, 15.8, 24.1, 59.3, 65.1, 64.1, 61.1, 59.0, 55.5, 54.6, 53.0, 51.1,
        50.3, 50.6, 50.6, 51.0, 43.5, -9.9]
OP_A = [30.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0,
        40.0, 40.0, 35.0, 35.0, 35.0, 35.0]

fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.1))
for ax, (ag, op, nm) in zip(axes, ((AG_M, OP_M, "(a) mild peak"),
                                   (AG_A, OP_A, "(b) aggressive peak"))):
    ax.plot(HRS, ag, "o-", ms=3, lw=1.2, color="tab:blue", label="policy (S-weighted)")
    ax.plot(HRS, op, "s--", ms=3, lw=1.2, color="tab:green", label="voltage-optimal")
    ax.axhline(38.7, color="tab:red", ls=":", lw=1.1, label="hub rating ratio")
    ax.axhline(0, color="k", lw=0.7)
    ax.set_xlabel("hour of day"); ax.set_ylabel("injection angle (deg)")
    ax.set_xlim(6, 23); ax.set_xticks(range(6, 24, 3))
    lo = min(min(ag), min(op)); hi = max(max(ag), max(op))
    ax.set_ylim(lo - (hi - lo) * 0.10, hi + (hi - lo) * 0.12)
    ax.set_title(nm)
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc="lower center", ncol=3, frameon=False,
           bbox_to_anchor=(0.5, -0.06), handlelength=1.6, columnspacing=1.6)
fig.tight_layout(); fig.savefig("fig5_pq.pdf"); fig.savefig("fig5_pq.png", dpi=200)
print("fig5_pq.pdf")
