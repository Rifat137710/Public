# FINAL PIPELINE — ISGT conference + Q1 journal

**Md. Rifat Rahman (BUET EEE)** · **Frozen 2026-08-15**

This is the settled plan. The conference half is closed and may be written from
as-is. The journal half is a programme with named gates, not a plan — and the
difference is deliberate.

Supporting detail: `03` results · `04` novelty and reviewer defence ·
`05` programme validation · `06` reconciliation of the earlier plans ·
`07` evidence that the sector is real · `08` retroactive-risk register.

---

## 0. One page

| | Conference | Journal |
|---|---|---|
| **Venue** | IEEE PES ISGT (topical, EV-grid-integration track) | IEEE Trans. Smart Grid → Applied Energy → SEGAN |
| **Type** | characterisation + runtime diagnostic | method + guarantee |
| **Status** | **experimentally closed** | **not started; Gate 1 outstanding** |
| **Compute left** | none | ~2–3 months part-time |
| **Rejection risk** | **low–moderate** | **moderate–high** |
| **Can the journal falsify it?** | **no** | — |

**The one-sentence claim:** *A sensitivity-based voltage safety layer's
protection depends on the currency of its linearisation base point rather than
the accuracy of its network model, and when either fails the violation rate
does not reveal it.*

---

## 1. The claim

Six frozen claims. Each is measured, each is scoped to what was measured, none
is falsifiable by any remaining open gate. Full wording in
`00-state-of-play.md` §2b — do not strengthen them when drafting.

| # | Claim | Evidence |
|---|---|---|
| **C1** | A never-refreshed projection reproduces the **unprojected** violation rate (96.9–100.0 %) while reporting **0.0000** infeasibilities. Total, and silent. | 12/12 cells, 2 feeders, 3 request sources |
| **C2** | The transition is a **cliff, not a slope**. Its location varies by feeder and operating point (24 steps vs 12 steps) and must be measured per deployment. *We do not claim to know what sets it.* | 12/12 cells |
| **C3** | A Jacobian wrong by **0.80×–2.06×** costs nothing. Outside that the failure is asymmetric: under-estimating impedance latches stations off, over-estimating costs up to 12 pp of service. | 0.20×–5.67× span, 2 feeders |
| **C4** | **A clean violation rate does not mean the layer works.** Two independent failure modes each produce one. Instrument the layer; don't outcome-check it. | both failure modes measured |
| **C5** | *On this testbed, at this budget*, the **layer not the learner** delivers safe service — 8.0× on a zero-intelligence charger. | ablation + G0 six-cell sweep |
| **C6** | Cost is negligible: **0.004 %** duty against a 300 s interval. | 0.662 ms vs 447.6 ms |

**C4 is the spine.** It began as an add-on and is now the strongest thing in
the work, because two unrelated failure modes independently demonstrate it:

| failure mode | violation rate says | reality |
|---|---|---|
| stale base point | *unprotected* — but **0.0000 infeasibilities** | layer switched off |
| under-estimated impedance | **0.0000 violations** — looks perfect | 8.3 % infeasible, 6.9 % latched to zero; the *fallback* did it |

---

## 2. The contribution

Ranked, and stated as what a reviewer would credit.

| # | Contribution | Why it is one |
|---|---|---|
| **1** | **The silent-failure characterisation.** A widely used safety mechanism does not degrade when its linearisation ages — it becomes inert, at the unprojected violation rate, reporting no fault. | unreported anywhere; the condition is the *default* state of a distribution feeder |
| **2** | **Decomposing the linearisation into Jacobian and base point, and measuring each.** The expensive artefact (a network model) tolerates ±2× error; the cheap one (a current measurement) carries everything. | the decomposition experiment does not exist in the literature |
| **3** | **A runtime diagnostic, shipped.** A projection reporting zero infeasibilities on a loaded feeder has stopped binding. One assertion any of the six papers building on this mechanism could adopt. | converts a characterisation into something actionable |
| **4** | **Operating envelope and failure-mode map.** Where the fallback becomes the dominant failure, and in which direction model error is dangerous. | practical output for a designer |
| **5** | **Separating the safety layer from the controller**, demonstrated on our own system. | methodological critique made concrete, not asserted |

**Explicitly NOT contributions** — say so in the paper:

- the projection itself (Dalal et al. 2018, 452 citations)
- SAC-Lagrangian
- the testbed
- **the principle that measurement feedback compensates model error** — conceded to three literatures (INDI; model-less voltage control; Bai et al., TPWRS 2022). Our contribution is the *closed-loop consequence*, not the mechanism.

**Novelty category:** **5 — existing method + realistic uncertainty.** The
uncertainty is base-point age. Supported by 2. Never 8.

---

## 3. Allocation — what is kept where

### Conference

| Asset | State |
|---|---|
| C1–C6 frozen claim set | ✅ |
| Two feeders: `case33bw` (34-bus MV) + `kerber_dorfnetz` (117-bus LV) | ✅ |
| Three request sources (3 on `case33bw`, 2 on `kerber`) | ✅ |
| Staleness sweep, 6 refresh intervals × 3 stiffness × 25 episodes | ✅ |
| Model-error sweep, 0.20×–5.67× Jacobian, both feeders | ✅ |
| Baselines: zero · uncoordinated · droop · **mixture line** · **projected heuristic** | ✅ |
| Infeasibility / freeze-latch telemetry (A5) | ✅ |
| Compute cost measurement | ✅ |
| Reproducibility: 90 tests, exact reproduction of the thesis table, bit-exact seeds | ✅ |

### Held for the journal — deliberately

| Asset | Why held |
|---|---|
| **Age-aware safety projection** (the method) | the journal's contribution; the conference proposes no method |
| Drift bound → constraint tightening → violation guarantee | requires Gates 1 and 3 |
| MPC / multi-period OPF oracle | "how far from optimal" is journal-mandatory, conference-optional |
| Third feeder — `ieee_european_lv_asymmetric` (unbalanced 3-phase) | needs a 3-phase solver |
| Real measured load / PV data | Gate 1 depends on it |
| Sensor-placement result ("how many real-time meters, and where") | the practical payoff of the method |
| Infeasibility-fallback redesign (J6) | replacing freeze-to-zero with graceful degradation is a method contribution |
| 5–10 seed statistics, IQM + stratified bootstrap | conference reports point estimates |
| N2 entropy-temperature treatment | publishable alone; off-topic here |
| A3 high-PV reactive channel | built, off-topic for this framing |

### Cut from both

+0.292 in-distribution gain (sign reversed) · §6.9 transfer numbers (diverged
run) · five-gate protocol · ±80 kW projection demo · "V–P dominance" as a
*finding* · transformer/thermal constraint · line-loss reward term ·
episode-level *p*-values · convergence-detector early stopping · 7-day
capability · random rollout · fleet Monte-Carlo as built.

---

## 4. Conference pipeline

### Done

| # | Item | Result |
|---|---|---|
| G0 | Operating-point sweep | sequencing gain negative 6/6 → paper is about the layer |
| D12 | Fair ablation, 3 seeds × 200 ep | **+0.2921 → −0.1285**, sign reversed |
| D15 | Projected-heuristic baseline | uncoordinated+proj **0.7094 @ 0.0000** vs SafeSAC 0.0889 |
| T1–T3 | Stiffness axis, `frozen_mode`, mixture line | built |
| T4/T5 | Stiffness transfer study | **killed by measurement** (Jacobians differ 1.16×) |
| T6 | Residual-based solver acceptance | built |
| T10 | A5 infeasibility quantified | freeze latch 0.0000 at Z ≤ 6 % |
| **G4** | **Second feeder** | **claim replicates 12/12; "2 h" design rule withdrawn** |
| **R5** | **Model-error sweep** | **±2× tolerance; second failure mode found** |
| — | Stage 0 reproduction gate | **PASS**, all six rows |
| — | Test suite | **90 passing** |

**Compute remaining: none.**

### Remaining — all writing

| # | Task |
|---|---|
| 1 | Four scoping edits: base-point **age** framing · quote the **0.80×–2.06×** window in the model-error sentence · testbed scope on C5 · *"varies by deployment"* not *"feeder-specific"* on C2 |
| 2 | Design rule reads **"measure your feeder's cliff"**, never "2 hours" |
| 3 | Concede the mechanism in the introduction; cite INDI, model-less voltage control, **Bai et al. TPWRS 2022** |
| 4 | Put C4 (the diagnostic) in the abstract |
| 5 | Text fixes: **sign convention** (`p_kw > 0` = injection), transformer claims, reward equation |
| 6 | Read Bai et al. TPWRS 2022 in full via BUET IEEE Xplore **before** writing the introduction |
| 7 | Draft |

---

## 5. Conference rejection risk — **LOW–MODERATE**

### Closed

| Standard rejection cause | Status |
|---|---|
| unsound / unverifiable | 90 tests · exact reproduction · physics to 5e-9 pu · bit-exact seeds |
| no credible baseline | five baselines incl. mixture line and projected heuristic |
| **single feeder** | **two unrelated feeders, 12/12 cells** |
| out of scope | named EV-grid-integration track |
| no practical output | runtime diagnostic + envelope + failure-mode map |
| "why RL at all?" | C5 scoping; RL is one request source, not the contribution |

### Residual, ranked

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **"Characterisation, not a method."** Taste-dependent; some reviewers want a method. | **moderate** | C4 shipped as an implementable assertion; lead with it |
| 2 | **Novelty challenged by someone who knows Bai et al.** | moderate | concede the mechanism in sentence one; differentiate open-loop accuracy vs closed-loop enforcement |
| 3 | **"Voltage doesn't bind on real feeders"** (NREL: <0.01 pu on ten actual feeders; thermal binds first) | moderate | scope explicitly to weak, low-SCR feeders; `kerber` sits at Vmin 0.9550 unloaded |
| 4 | **No confidence intervals** | low | effects are 0.0000 vs 0.0642 — not a statistical question; report as measured rates |
| 5 | **"Your RL is bad"** | low | it is, and the paper says so; it is one of three sources |
| 6 | Simulation only | low | standard for the venue |

**Assessment.** Every failure mode that reliably sinks papers at this class of
venue is closed by measurement. What remains is taste (#1) and positioning
(#2, #3), both addressable in the writing. The work sits **above** the venue's
norm — most ISGT papers are 5–6 pages, one feeder, few seeds, no test suite.

**The one thing that would still get it rejected:** submitting with the
mechanism claimed rather than conceded, or with "refresh within 2 hours" in it.
Both are wording, and both are already fixed in the frozen claim set.

---

## 6. Journal pipeline

**Direction (working hypothesis, not frozen): age-aware safety projection.**
Make base-point age τ an explicit argument of the constraint; tighten the band
by a data-driven bound on net-load drift over τ. Foundation is citable
(sporadic-measurement CBFs, measurement-robust CBFs); the contribution is the
grid adaptation — drift is *forecastable and boundable from data*, not
adversarial; the constraint is an AC power-flow band; the actuator is an
energy-coupled fleet where conservatism has a measurable service cost.

### Corrected workflow

The inherited `Q1_workflow.md` is a good build system with a bad compass. Keep
the freeze rule verbatim, the sharded campaign, and the baseline list. Add:

- **Phase −1** literature gate ✅ done (`04`)
- **Phase −0.5** premise falsification ⬜ **= Gate 1**
- **Phase 0** inherited-result audit ✅ done — it killed two claims
- **a kill branch on every gate** — the original could pass or escalate, never abandon

### Gates, in order

| # | Gate | Question | If it fails |
|---|---|---|---|
| **1** | Real metering cadence | At DSSE 1–15 min / AMI 15 min–1 h, is the naive filter unsafe? | the *method* loses motivation; the failure-mode axis survives |
| **3** | Bound tightness | Is the drift bound tight enough to leave useful service? | method useless — matches refresh-always on safety, loses on service |
| **2** | Fixed margin | Does age-dependent tightening beat a *constant* conservative margin? | **method contribution collapses** to "use a bigger margin" |
| ~~4~~ | Second feeder | ✅ **retired early** — it protected the conference | — |

Gates 2 and 3 are one build-then-test block: the bound must exist before it can
be compared.

### Supporting work — effort, not risk

| Item | Status |
|---|---|
| Second feeder (117-bus) | ✅ done |
| Real load + PV data | ⬜ — Gate 1 depends on it |
| Drift bound → tightening → violation bound | ⬜ ~1–2 weeks |
| MPC / multi-period OPF oracle | ⬜ ~1–2 weeks |
| Sensor placement (greedy/submodular) | ⬜ ~1 week |
| Third feeder, unbalanced 3-phase | ⬜ |
| 5–10 seeds, per-episode arrays, bootstrap | ⬜ CPU-hours |
| Baselines: naive-at-τ, refresh-always, fixed margin, event-triggered | ⬜ ~1 week |
| Fallback redesign (J6) | ⬜ |

Realistically 2–3 months part-time. None of it needs compute we lack.

---

## 7. Journal risk — **MODERATE–HIGH**

| # | Risk | Severity | Note |
|---|---|---|---|
| 1 | **Gate 2 — a fixed margin matches age-aware tightening** | **high** | the largest single risk. A constant tightening tuned once may achieve the same safety at the same service, collapsing the contribution |
| 2 | **Gate 3 — worst-case drift bound too loose** | moderate–high | worst-case bounds routinely are; a data-driven bound is the hedge |
| 3 | **Gate 1 — real cadences all safe** | **moderate, reduced** | `kerber`'s cliff is at 12 steps = **1 h = exactly the AMI interval**. Much closer to deployment than the 2 h/4 h figure feared earlier |
| 4 | **Competitive pressure** | moderate | PI-TD3-class work runs IEEE 34+123-bus with hundreds of EVs and beats optimisation baselines. We do **not** enter that race — we compete on insight, not scale |
| 5 | TSG first-submission rejection | moderate–high | normal; the cascade TSG → Applied Energy → SEGAN is the plan, not a fallback |
| 6 | Execution — real data, oracle, statistics | low | effort with known outcome |

**Correction on the record.** I previously said a failed Gate 1 means *"the
paper dies."* That is now too strong. The model-error result (C3, C4) is
**cadence-independent**, so a bad Gate 1 costs the *tightening method* its
motivation but leaves a journal built on the failure-mode and diagnostic axis.
**The journal degrades under a bad Gate 1; it does not collapse.**

**Overall:** materially riskier than the conference, and the risk is
concentrated in Gate 2. Run Gate 1 first because it is cheapest, but understand
that **Gate 2 is the one that decides whether there is a method paper.**

---

## 8. Decision log — what died, and why it matters

| Claim | Fate |
|---|---|
| "SafeSAC beats SAC-Lag, +0.292 SoC" | **dead** — matched-budget ablation gives −0.1285 |
| "Constraint satisfaction doesn't transfer" | **dead** — my own script's confound; base point, not Jacobian |
| "Refresh within 2 hours" | **withdrawn** — 2 h on `case33bw`, 1 h on `kerber` |
| "Faster refresh is worse" | **dead** — 6/6 helps on one feeder, 0/6 on the other |
| "Network model error is free" | **bounded** — free only within 0.80×–2.06× |
| J1 network-distance predictor | **dead as specified** — nothing left for network distance to predict |

Six claims died before publication rather than after. Two were mine. That is
the system working, and it is why the surviving six can be frozen.

**Before submission, one conversation:** the paper contains none of the
thesis's defended claims. It is built from the thesis's *infrastructure* plus
new experiments. Settle the framing and author list with Dr. Forkan Uddin and
Sad Sami first.
