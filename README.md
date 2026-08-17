# V2G voltage support on IEEE-34 — reproduction, and where control stops helping

An independent reproduction of an EV-charging-hub voltage-support study on the IEEE-34
distribution feeder (OpenDSS + fleet-constrained droop + SAC), plus a deliberate test of
whether giving the agent **foresight** lets it beat droop.

Reproduction target: Wang, Jacob, Kaushik & Zhang, *"Reinforcement Learning for
Vehicle-to-Grid Voltage Regulation: Single-Hub to Multi-Hub Coordination with
Battery-Aware Constraints,"* [arXiv:2603.07237](https://arxiv.org/abs/2603.07237)
(UT Dallas, March 2026).

## The extension tested
Give the agent what droop lacks — aggregate fleet **SOC, availability and hour-of-day**
in the observation — and shape the action as a **bounded residual over droop**,
`P = clip(droop_P + a·P_rated, 0, P_rated)`, so `a = 0` *is* droop. That makes droop a
guaranteed performance floor: the agent can only *withhold* wasteful discharge or *add*
support, and it cannot be handicapped by exploration or tuning.

## What actually happened: it does not beat droop

At a single hub the agent ties droop on worst-bus violation-hours at mild load, is
**worse** at aggressive load, and shows no energy saving that survives seed variance.
The availability sweep (40–70%) finds no level where a gap opens. Full tables in
**[`RESULTS.md`](RESULTS.md)**.

The reason is structural, not a training failure. The worst bus sits near 0.72 p.u.
against a 0.95 limit and never enters the band, so there is no in-band slack to withhold
and the voltage penalty outweighs the SOC cost roughly 100:1 — under that reward,
maximal discharge *is* optimal. Because `a = 0` reproduces droop exactly, the null
localizes the bottleneck in the **physics of hub siting and capacity**, not the
controller.

> One caution recorded in `RESULTS.md`: at 3k training steps the agent appeared to save
> 12.8% energy at equal support; at 20k steps the same setup used 20.2% *more*. The
> apparent "battery-aware" benefit was an undertraining artifact that inverted on
> convergence.

## Where this is going
The follow-on work splits feasibility into two independent constraints — per-hour **power
adequacy** and daily **energy adequacy** — and characterizes the regime in which foresight
can pay at all. See **[`PAPER_PLAN.md`](PAPER_PLAN.md)**.

## Run it
Open **`V2G_safe_path.ipynb`** and *Run All* (Kaggle or local, CPU is fine, ~15–20 min).
The notebook is **self-contained**: it writes its own feeder and modules, installs any
missing deps, then prints three tables (reproduction / degradation headline / sweep) and
saves three figures. Bump `STEPS_HEADLINE` for a sharper result.

## Layout
| path | what |
|---|---|
| `V2G_safe_path.ipynb` | self-contained experiment (the deliverable) |
| `src/v2g_core.py` | feeder wrapper, EV fleet, droop baseline, daily evaluation |
| `src/v2g_env_residual.py` | residual-over-droop Gymnasium env (SOC/time-aware) |
| `src/safe_path.py` | unified rollout + training + droop-vs-RL comparison |
| `feeder/` | IEEE-34 master + line codes (OpenDSS) |

`src/` and `feeder/` are committed copies for browsing; the notebook regenerates them
on run, so it stands alone.
