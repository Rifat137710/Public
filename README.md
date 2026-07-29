# V2G voltage support on IEEE-34 — reproduction + one improvement over droop

A faithful reproduction of an EV-charging-hub voltage-support study on the IEEE-34
distribution feeder (OpenDSS + fleet-constrained droop + SAC), plus **one deliberate
change** that gives the RL agent a capability droop lacks by construction.

## The idea in one line
Make the agent **see energy and train against it**: put aggregate fleet **SOC,
availability, and hour-of-day** in the observation, and shape the action as a
**bounded residual over droop** — `P = clip(droop_P + a·P_rated, 0, P_rated)` — so
`a = 0` *is* droop (a guaranteed performance floor) and the agent can only *withhold*
wasteful discharge or *add* support, timed intertemporally.

## The result we target (single-hub)
Droop is memoryless: it discharges on instantaneous local voltage, even for cosmetic
(in-band) sags, and drains the fleet to its SOC floor. The SOC-aware residual agent
holds **equal voltage support** (same violation-hours, same worst-bus voltage) while
discharging **materially less energy** and **retaining more end-of-day charge** — the
"same support, less battery wear" result droop cannot produce. An availability sweep
(40–70%) locates the regime where foresight *also* opens a violation-hour gap.

> Status: code complete and wiring-tested end-to-end. Full-scale training numbers are
> produced by running the notebook (see below); a short dev run already shows the
> single-hub-mild energy/SOC gap in the expected direction.

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
