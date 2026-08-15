# Research programme — is this the right direction for a Q1 journal?

**Author:** Md. Rifat Rahman (BUET EEE) · **Written:** 2026-08-15
**Question asked:** the direction chosen was "characterise when a sensitivity-based
safety filter stops protecting." Is that the best path to a Q1 journal?

**Short answer: the diagnosis is correct and worth an ISGT paper, but as a
research direction it is incomplete. It stops at a finding. A Q1 journal in this
field needs a method with a guarantee. The direction must be extended, not
replaced — and the extension it needs is now identifiable and unoccupied.**

---

## 1. Calibrating against the actual competitive set

Before judging our direction, measure the bar. Recent work in exactly our space:

| Work | Feeder(s) | Scale | Baselines beaten |
|---|---|---|---|
| PI-TD3, physics-informed RL for EV smart charging (2025) | IEEE 34-bus **and** 123-bus | hundreds of EVs | model-free RL **and** optimisation-based |
| Safety-Aware RL for EV Charging Station Management (2024) | distribution network | fleet | PCPO baselines |
| DuMES dual-layer safety (IET, 2025) | distribution | fleet | rule-based + DRL |
| Safe MADRL w/ communication delay (Applied Energy 2023) | distribution | multi-agent | delay-naive baselines |

Now our position, honestly:

| Dimension | Competitive set | Us |
|---|---|---|
| Feeders | 34-bus + 123-bus | **33-bus only** |
| Scale | hundreds of EVs | 30–100 EVs |
| Optimisation baseline | yes (they beat it) | **none — no MPC/OPF oracle** |
| RL quality | beats optimisation baselines | **loses to a coin flip between two heuristics** |
| Contribution type | method + improvement | **characterisation** |

**Conclusion: the current work, extended by scale alone, loses this race.** Going
head-to-head on "better safe RL for EV charging" means competing on feeder size,
fleet size and compute against well-resourced groups. One researcher with Kaggle
will not win that. **Do not enter that race.**

This is the strongest argument *for* the chosen direction: it competes on
insight rather than scale. But insight alone does not clear a Q1 desk.

---

## 2. What is wrong with the direction as currently stated

A characterisation paper — "here is when the existing mechanism breaks" — is a
conference contribution. Q1 journals in this field (IEEE TSG, TPWRS, Applied
Energy) reliably want one of:

1. a new method with demonstrated improvement over strong baselines,
2. a new problem formulation with a solution,
3. a theoretical guarantee, or
4. validation at a scale or on data that changes practice.

Our staleness result is closest to (4) but without real data or a second feeder.
Submitted as-is to TSG it reads as: *one simulated feeder, an RL controller the
authors admit is poor, and a negative result about a mechanism whose underlying
principle is conceded to prior art.* That is a reject.

**The direction produces a diagnosis. A Q1 paper needs the cure.**

---

## 3. The cure, and why this specific one

### 3.1 The proposal

**Age-aware safety projection.** Instead of projecting onto a voltage band
computed at a base point of unknown age, make the base point's **age τ** an
explicit argument of the constraint: tighten the band by an amount derived from
a bound on how far net load (and hence voltage) can drift in time τ.

The properties this buys, each of which maps onto a failure we measured:

| Measured failure | What age-awareness does |
|---|---|
| Filter goes silently inert when stale | Tightening grows with τ, so the constraint never becomes vacuous |
| Failure is binary, not graceful | Violation bound degrades continuously in τ |
| Refresh-always is over-conservative | At τ→0 the tightening →0, recovering full service |
| No way to know the filter stopped binding | τ is an observable the operator already has |

That is a method, with a guarantee, motivated by our own diagnosis, evaluated
against the same axis we characterised. The two papers chain: Paper 1 establishes
that τ matters; Paper 2 makes τ a design variable.

### 3.2 The theory already exists — and that is good news

Searching the control literature turned up the exact construction:

- **Robust Safety-Critical Control for Systems with Sporadic Measurements and Dwell Time Constraints** — extends control-barrier-function theory to a controller that "only receives measurements infrequently and operates open-loop between measurements, while still satisfying state constraints," using an open-loop observer that "bounds the worst-case uncertainty between measurements."
- **Measurement-Robust Control Barrier Functions** — safety guarantees under erroneous state estimates.
- **Control barrier functionals / CBFs for sampled-data systems with input delay** — the delay-side analogues.

My first instinct was that this kills the idea. It does not. It means we build
on a **citable, refereed theoretical foundation** instead of inventing an ad-hoc
margin that reviewers will dismantle. Power-systems Q1 journals routinely and
happily publish *transfer* contributions: take a rigorous construction from
control theory, adapt it to the grid-specific structure, validate on standard
feeders.

The grid-specific adaptation is real work and is where our contribution lives:

- the "state" is a voltage profile, and drift is driven by **net load and PV**, which are *forecastable and empirically boundable from data* — unlike the adversarial disturbance the CBF papers assume. A data-driven drift bound is less conservative and is a genuine methodological step.
- the constraint is an **AC power-flow band**, enforced through a linearisation whose own error must be folded into the same bound.
- the actuator is a **bidirectional EV fleet with energy coupling across time**, so conservatism costs service in a way the CBF literature never measures.

### 3.3 Adjacent work to cite and differentiate (searched, not assumed)

| Work | Overlap | Our difference |
|---|---|---|
| Age-of-Information-aware PI controller for **load frequency control** (PCMP 2023) | AoI as a formal staleness metric in power systems — **the naming and framing we should adopt** | theirs is transmission-level frequency *stabilisation*; ours is distribution *constraint enforcement*, where the failure is inertness rather than instability |
| Bai et al., online feedback-based linearised power flow (TPWRS 2022) | sweeps update frequency, models a communication "freeze" | open-loop *accuracy* metric; ours is closed-loop *enforcement* |
| Real-time Assessment of Distribution Grid Security through Adaptive Smart Meter Measurements (2026) | certifies voltages in-bound from limited meters under "unknown but bounded" load — **the same uncertainty model our drift bound needs** | theirs *certifies*; ours *actuates*. Natural control-side companion, and a strong citation |
| Safe MADRL with communication delay (Applied Energy 2023) | delayed measurements in a safety layer | treats delay as a millisecond comms problem to be imputed away; ours is hour-scale metering cadence treated as a design variable |
| Event-triggered voltage control / DMPC | "when to recompute" | **crowded field — this is why event-triggered refresh is the weaker cure (§4)** |

**Nothing found does age-dependent constraint tightening for a distribution
voltage safety filter.** The AoI framing exists in power systems but has not
reached distribution constraint enforcement. That is the gap, and it is
nameable, which matters for a title and an abstract.

---

## 4. Alternatives considered and rejected

| Alternative | Why not |
|---|---|
| **Fix the RL, compete conventionally** | Crowded, well-resourced, and PI-TD3 already does 34+123-bus with hundreds of EVs beating optimisation baselines. We lose on compute. User has also ruled out recovering the thesis claim. |
| **Event-triggered / adaptive refresh** ("refresh when a trigger fires") | Event-triggered control is a mature field with event-triggered DMPC and sensitivity-matrix consensus schemes already published for voltage control. We would be a minor variant. **Keep as a comparison baseline in Paper 2, not as the spine.** |
| **Pure critique paper** ("published safe-RL voltage results don't survive fair comparison") | We have the material — projection on a zero-intelligence greedy beats projection on the trained policy 8.0×. But a critique without a fix is a hard Q1 sell and makes enemies among exactly our reviewer pool. **Keep it as the baseline-discipline section of Paper 2, where it is evidence rather than an accusation.** |
| **Sensor placement as the spine** | Strong and grid-native, but partially occupied by the 2026 adaptive-smart-meter certification work, and without the age-aware filter there is no principled objective to place sensors against. **Demote to Paper 2's second contribution — where it becomes the practical payoff: "how many real-time meters do you need, and where."** |
| **Hosting-capacity framing** | Viable and Applied-Energy-friendly. **Keep as the fallback framing of the same work if TSG rejects**, not as a separate direction. |

---

## 5. The experiment that decides whether the programme is real

The programme's whole motivation is: *base-point currency is constrained by
metering infrastructure, not compute.* Right now that is a rhetorical argument
backed by a citation. A reviewer can answer it with "then just refresh more
often" and we have nothing quantitative to say back.

**The decisive experiment: run the safety filter at realistic measurement
cadences on real load and PV data, and show that at the cadences utilities
actually have, the naive filter is unsafe and the age-aware filter is not.**

Cadences to instantiate from the literature already gathered: DSSE 1–15 min,
AMI 15 min–1 h, SCADA telemetry concentrated at the substation rather than at
station buses.

If the naive filter turns out to be safe at every realistic cadence, the
programme is dead and we should know that early, cheaply. **Run this before
investing in the theory.** It is the cheapest possible falsification of our own
direction, and running it first is the discipline that was missing from the
thesis.

---

## 6. What Paper 2 needs that we do not have

| # | Item | Status | Effort |
|---|---|---|---|
| 1 | Realistic-cadence falsification test (§5) | not started | **days — do first** |
| 2 | Real load + PV data (thesis limitation C1) | not started | days (public datasets) |
| 3 | Drift bound → tightening derivation + violation bound | not started | ~1–2 weeks |
| 4 | IEEE 123-bus second feeder | not started | days (pandapower has it) |
| 5 | MPC / multi-period OPF oracle baseline | not started | ~1–2 weeks |
| 6 | Sensor-placement contribution (greedy/submodular) | not started | ~1 week |
| 7 | Proper statistics — ≥5 seeds, per-episode arrays, stratified bootstrap | partially | CPU-hours |
| 8 | Baselines: naive-at-τ, refresh-always, fixed margin, event-triggered | not started | ~1 week |

Realistically 2–3 months part-time. Every item is within reach of one person
with Kaggle. None of it requires the compute scale that would lose us the
conventional race.

---

## 7. Verdict

**The direction is right in kind and incomplete in degree.**

Right in kind: it competes on insight rather than scale, which is the only race
a single researcher with limited compute can win; it turns the thesis's central
weakness (an RL policy that does not work) into a non-issue by making the
*filter* the object of study; and it has an unoccupied, nameable gap.

Incomplete in degree: it currently ends at a diagnosis. Q1 needs the cure. The
cure is **age-aware safety projection**, it has a citable theoretical
foundation, it has a grid-specific adaptation that constitutes real
contribution, and it has a practical payoff (metering requirements) that grid
journals value.

**Recommended programme:**

- **Paper 1 — ISGT 2026.** The diagnosis. Base-point currency, not model
  accuracy, carries the protection; the failure is silent and binary; envelope
  Z ≤ 8 %; design rule and runtime diagnostic. Already largely done.
- **Paper 2 — IEEE TSG (fallback: Applied Energy under a hosting-capacity
  framing).** The cure. Age-aware projection with a violation bound, validated
  on 33-bus and 123-bus with real load/PV data against an MPC oracle, plus the
  metering-requirement result.

**Immediate next action: §5. Falsify our own premise before building on it.**
