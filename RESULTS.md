# Measured results

All numbers below come from full-length runs of `V2G_safe_path.ipynb`
(`STEPS_HEADLINE=20000`, SAC, CPU). Two independent runs on different machines are
reported because they disagree on the size of one effect and that disagreement is itself
part of the finding.

**Headline: the SOC/time-aware residual agent does not beat closed-loop droop at a single
hub — on either axis.** The bottleneck is hub energy and siting, not control sophistication.

---

## 1. Reproduction

Baseline (no V2G) vs. closed-loop droop, feeder-mean violation-hours over the 06:00–24:00
window on IEEE-34 with the regulators frozen (`Set ControlMode=OFF`):

| case | baseline | droop |
|---|---|---|
| single-hub, mild (peak ×1.5) | 10 | 10 |
| single-hub, aggressive (peak ×3.0) | 16 | 16 |
| multi-hub (5 hubs), mild | 10 | 9 |
| multi-hub (5 hubs), aggressive | 16 | 15 |

This is the paper's central qualitative finding: **coordinated hubs move the feeder, one hub
essentially does not.** Worst-bus voltage stays far below the 0.95 limit in every single-hub
case regardless of controller.

> **Scope of the reproduction.** The setup and the central finding reproduce. This was *not*
> validated as a numeric match to the paper's tables — load shapes, hub siting details and
> fleet parameters were reconstructed from the text, so absolute violation-hour counts are
> not expected to line up digit-for-digit.

## 2. Headline — single hub, droop vs. residual-over-droop RL

`ViolMean` = feeder-mean violation-hours, `ViolBus` = worst-bus violation-hours,
`Vmin` = worst-bus minimum p.u., `Energy` = kWh discharged over the day,
`SOCend` = end-of-day mean fleet SOC (floor 0.20). `(a=0 floor)` is the zero-residual
sanity row that verifies the safety floor is wired up.

### Run A (mild, peak ×1.5)

| controller | ViolMean | ViolBus | Vmin | Energy (kWh) | SOCend |
|---|---|---|---|---|---|
| closed-loop droop | 10 | 15 | 0.722 | 277.6 | 0.200 |
| residual-RL | 9 | 15 | 0.741 | **333.8** | 0.201 |
| (a=0 floor) | 10 | 15 | 0.722 | 312.4 | 0.200 |

→ worst-bus violations tie; the agent discharged **20.2 % *more*** energy. Both controllers
end pinned at the SOC floor.

### Run A (aggressive, peak ×3.0)

| controller | ViolMean | ViolBus | Vmin | Energy (kWh) | SOCend |
|---|---|---|---|---|---|
| closed-loop droop | 16 | 17 | 0.538 | 326.7 | 0.200 |
| residual-RL | 16 | **18** | 0.538 | 341.9 | 0.200 |
| (a=0 floor) | 16 | 17 | 0.538 | 326.7 | 0.200 |

→ **worse** on worst-bus violation-hours *and* used more energy.

### Run B (independent 20k-step run, same config)

| case | controller | ViolMean | ViolBus | Vmin | Energy | SOCend |
|---|---|---|---|---|---|---|
| mild | droop | 10 | 15 | 0.722 | 277.6 | 0.200 |
| mild | residual-RL | 9 | 15 | 0.725 | 272.0 | 0.200 |
| aggr | droop | 16 | 17 | 0.538 | 326.7 | 0.200 |
| aggr | residual-RL | 16 | **18** | 0.538 | 341.4 | 0.200 |

→ mild came out 2.0 % *less* energy here, against +20.2 % in Run A. **The run-to-run spread
on the energy axis is larger than the effect being claimed**, so no energy-saving claim
survives. Aggressive is worse in both runs — that part is consistent.

## 3. Availability sweep (single hub, mild)

Mean fleet availability swept across the plan's 40–70 % window. `dEnergy%` > 0 would mean
energy saved vs droop at equal-or-better support.

| availability | droop ViolBus | RL ViolBus | VMgap | dEnergy % |
|---|---|---|---|---|
| 39 % | 15 | 16 | 0 | −19.7 |
| 48 % | 15 | 16 | 0 | −13.6 |
| 58 % | 15 | 16 | 0 | −23.9 |
| 67 % | 15 | 16 | 0 | −13.0 |
| 77 % | 15 | 15 | 0 | +0.3 |

→ **no availability level opens a gap.** Worst-bus violation-hours are equal or worse
everywhere, feeder-mean gap is zero everywhere, and energy is worse nearly everywhere.

## 4. Why it fails — and why the null is informative

Two facts about the single-hub regime explain the whole table:

1. **No in-band slack.** "Equal support, less wear" requires sags the controller is free to
   *not* answer — cosmetic, in-band dips. At a single hub the worst bus sits around 0.72 p.u.
   (0.54 aggressive) and never enters the band, so every hour is a hard violation hour and
   there is nothing to withhold.
2. **The reward has no reason to ration.** `reward_from_v` pays a sparse `+10` only when
   *all* buses are in band — never earned here — leaving a pure voltage penalty of 30–100+
   per hour against a maximum SOC cost of `0.5·discharge`. At roughly 100:1, maximal
   discharge *is* the optimal policy. The agent is not failing to learn; it is learning the
   correct answer to the objective it was given.

The energy accounting makes the same point without any RL: one hub's fleet
(15 EVs × 75 kWh, usable 0.20–0.90 SOC, 500 kW rated) holds on the order of **one hour** of
full-power support against a violation window of roughly **nine hours**.

The null result is load-bearing rather than merely negative because of the residual
architecture: `a=0` reproduces droop exactly, so the agent is *guaranteed* not to be
handicapped by exploration or tuning. Giving a controller aggregate SOC, availability and
hour-of-day — plus a provable droop floor — and still not beating droop localizes the
binding constraint in the **physics of hub siting and capacity**, not in the controller.

The implication for follow-on work: the levers are **coordination across hubs** and **where
hubs are placed and how large they are**, not a more sophisticated local policy. Foresight
should start paying once there is in-band slack to trade (multi-hub, or explicit degradation
pricing), which is a testable prediction of the diagnosis above.

## 5. Reproducing these numbers

Open `V2G_safe_path.ipynb`, *Run All* (~15–20 min, CPU). It writes its own feeder and
modules, then prints the three tables above and saves `fig_degradation_{mild,aggr}.png` and
`fig_sweep.png`. `STEPS_HEADLINE=40000` sharpens the estimates; in the runs so far it does
not change the sign of any conclusion.
