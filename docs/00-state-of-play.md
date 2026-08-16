# State of play — entry point

**Md. Rifat Rahman (BUET EEE)** · **Updated:** 2026-08-15
Read this first. Everything else is detail.

| Doc | Contains |
|---|---|
| `03-isgt-2026-plan.md` | the live conference plan, all measured results |
| `04-novelty-and-reviewer-defence.md` | novelty audit, ten reviewer attacks, pre-submission actions |
| `05-research-programme.md` | direction validation, the journal proposal, pipeline critique (§8) |
| `06-plan-reconciliation.md` | the three standing plans vs. measured state |
| `07-does-this-matter.md` | evidence that the sector, mechanism and condition are real |

---

## 1. Three claims. Two dead, one alive.

| Claim | Verdict |
|---|---|
| "SafeSAC beats SAC-Lag in-distribution, +0.292 SoC" | **DEAD** — fair 3-seed × 200-ep ablation gives **−0.1285**. Sign reversed |
| "Constraint satisfaction doesn't transfer; deployment-parametrised projection restores it" | **DEAD** — my script's confound. Freezing the Jacobian while measuring deployment voltages gives **0.0000** violations, identical to the correct model |
| **"Base-point staleness, not model error, is what makes a safety layer fail"** | **ALIVE** — replicated 6/6 cells, 3 request sources, mechanism measured |

The thesis's defended claims are not in the paper. The paper is built from the
thesis's *infrastructure* plus new experiments. **Settle this with Dr. Forkan
Uddin and Sad Sami before submission, not after.**

---

## 2. The surviving claim

> A sensitivity-based safety layer's protection depends on the **currency of its
> linearisation base point**, not on the accuracy of its network model — and
> when the base point goes stale the layer does not degrade, **it switches off.**

**Headline evidence.**

| Result | Numbers | Strength |
|---|---|---|
| Never-refreshed ≈ completely unprotected | recovers **96.9–100 %** of raw violation rate | **12/12 cells on two unrelated feeders**, solid |
| The failure is **silent** | infeasibility rate **0.0000** while fully unprotected | 12/12 cells, solid |
| Cliff, not slope | zero violations, then near-full raw rate one interval later | 12/12 heuristic + 6/6 learned, solid |
| Wrong Jacobian is free | 0.0000 vs 0.0000 | 2 deploy points × 2 modes, solid |
| Safety layer carries the service | uncoordinated+projection **0.7094 SoC at 0.0000 viol**, vs droop 0.0067 | solid |
| ~~"Refresh within 2 h" as a design rule~~ | `case33bw` 2 h, `kerber` **1 h** | **WITHDRAWN — feeder-specific** |
| ~~"Faster refresh is worse"~~ | 6/6 helps on `case33bw`, **0/6 on `kerber`** | **DEAD — opposite sign per feeder** |

**Second feeder run (`kerber_dorfnetz`, 116-bus German village LV benchmark).**
The qualitative claim replicates in full; the *quantitative* design rule does
not — the cliff sits at 1 h there, not 2 h. Publishing "refresh within 2 hours"
would have been contradicted by our own journal work. See
`08-retroactive-risk.md` §3.

Envelope: **Z ≤ 8 %**. Past it, freeze-to-zero fallback becomes the dominant
failure mode (0.1171 at Z = 10 %, r48). Compute: **0.004 %** duty against a
300 s interval.

---

## 2b. FROZEN CLAIM SET — conference

Every sentence below is measured, scoped to what was measured, and cannot be
falsified by any of the remaining open gates. **Write from these; do not
strengthen them.**

**C1 — the headline.** On two unrelated radial feeders, a sensitivity-based
voltage safety projection whose linearisation base point is never refreshed
reproduces the **unprojected** violation rate to within 3 % (96.9–100.0 %,
12/12 cells) while reporting an infeasibility rate of **0.0000**. The failure is
total and silent.

**C2 — the shape, not a number.** The transition is a cliff, not a slope: zero
violations at one refresh interval, near-full unprojected rate at the next. Its
**location varies across feeders and operating points** — 24 steps on
`case33bw` at Z = 6 %, 12 steps on `kerber` across a 3× stiffness range and two
request sources — and must be measured for a given deployment. *We do not claim
to know what sets it.*

**C3 — model error, bounded.** Across a station-bus Jacobian error spanning
0.20×–5.67×, a wrong network model costs nothing within **0.80×–2.06×** on both
feeders and both request sources. Outside that band the failure is asymmetric:
under-estimating line impedance drives the QP infeasible (8.3 % of steps) and
latches stations to zero (6.9 %); over-estimating is conservative, costing up to
12 pp of service on `kerber` at 5.5×.

**C4 — the diagnostic, and the strongest thing here.** A clean violation rate
does not mean the layer is working. Two independent failure modes both produce
one: a stale base point (unprotected, zero infeasibilities) and an
under-estimated impedance (fallback doing the work). **A safety layer must be
instrumented, not outcome-checked** — a projection reporting zero
infeasibilities on a loaded feeder has stopped binding.

**C5 — layer, not learner.** *At this operating point, on this testbed, at this
training budget*: the projection applied to a zero-intelligence greedy charger
delivers **8.0×** the service of the same projection on the trained policy, at
identical zero violations. G0 swept six cells and found none where sequencing
helps. **Not** a claim that RL cannot help.

**C6 — cost.** 0.004 % duty against a 300 s control interval; analytic
sensitivities at 0.662 ms against 447.6 ms.

**Reporting rules that go with the set.** Three request sources on `case33bw`,
two on `kerber` — never "three sources" flat. Point estimates, no intervals
claimed. Weak, low-SCR feeders only; no generalisation to well-built
distribution. Refresh is simulated by recomputing power flow, not by a metering
pipeline.

---

## 3. Does it matter? Evidence, not opinion.

| Question | Answer |
|---|---|
| Is the mechanism mainstream? | **Yes** — Dalal 2018 has **452 citations**; action projection is one of two techniques inside one of the two top-level categories of the field's own taxonomy; ≥6 recent power papers depend on it, none reporting refresh cadence |
| Is staleness a real condition? | **Yes — it is the default.** Distribution systems are "practically unobservable in real time," "measurement-scarce with multiple reporting rates," "easily unobservable due to communication failure and delay" |
| Does the failure type matter? | **Yes** — 2003 Northeast Blackout: a topology error crashed the state estimator and operators lost the solution they depended on |
| Is the application real? | **On weak/rural feeders yes** (voltage issues at 2 BEVs); **on robust feeders no** — NREL finds <0.01 pu impact on ten actual feeders, and PNNL finds transformer thermal binds first. **Must scope explicitly to weak, low-SCR feeders** |
| Did anyone do this? | The *principle* is conceded to three literatures (INDI, model-less voltage control, Bai et al. TPWRS 2022). **The closed-loop safety-filter characterisation is unoccupied** |

---

## 4. Conference — ISGT 2026

**Experimentally complete.** G0, T1, T2, T3, T6, T7 done; T4/T5 killed by
measurement; 84 tests; reproduction gate re-verified.

**Above the venue bar, with margin.** ISGT is a reputable IEEE PES *topical*
conference (ISGT Europe H-index 10), not a flagship. ISGT Asia 2026 has an exact-fit
track: *Electric Vehicle-Grid Integration and Smart Charging*. Typical papers are
5–6 pages, one feeder, few seeds, no test suite.

**Remaining work is not experimental:**

1. Demote "faster refresh is worse" to what survives: *at Z ≤ 6 %, extending to 2 h costs exactly zero violations*
2. Concede the mechanism in the intro; cite INDI, model-less voltage control, Bai et al. TPWRS 2022
3. Ship the runtime diagnostic in the abstract: *a filter reporting zero infeasibilities on a loaded feeder has stopped binding*
4. Reframe as **age of the base point**; admit refresh is simulated by recomputing power flow
5. Call the Z-sweep **operating stiffness**, never topological diversity
6. Text fixes: sign convention (`p_kw > 0` = injection), transformer claims, reward equation
7. Read Bai et al. TPWRS 2022 in full via BUET's IEEE Xplore before writing the intro

**Deadline fact:** ISGT Asia 2026 submission closes **20 August 2026**.

---

## 5. Journal — the hole, and the fill

**The plan lost its headline.** J1 (network-distance predictor) is dead — the
dependent variable is ≈0 whenever deployment voltages are measured. J4 and J5
were held as journal reserves and have both been spent at the conference,
because they were the only assets that survived.

**Proposed fill: age-aware safety projection.** Make base-point age τ an
explicit argument of the constraint; tighten the band by a data-driven bound on
net-load drift over τ. Foundation exists and is citable (sporadic-measurement
CBFs, measurement-robust CBFs); the grid-specific adaptation is the
contribution — drift is *forecastable and empirically boundable* rather than
adversarial, the constraint is an AC power-flow band, and the actuator is an
energy-coupled fleet where conservatism has a measurable service cost.

**Four outcome-dependent gates.** Everything else (123-bus, MPC oracle, seeds,
real data) is effort with a known outcome.

| # | Gate | If it fails |
|---|---|---|
| **1** | At real metering cadences, is the naive filter actually unsafe? | **Paper dies** — we'd be warning about a regime nobody occupies |
| **2** | Does age-dependent tightening beat a *fixed* conservative margin? | **Method dies** — contribution collapses to "use a bigger margin" |
| **3** | Is the drift bound tight enough to leave useful service? | **Method useless** — matches refresh-always on safety, loses on service |
| **4** | Does the cliff exist on IEEE 123-bus? | **External validity dies** |

Order: **1 → build the bound (3 emerges) → 2 → 4.**

---

## 6. Pipeline verdict

`Q1_workflow.md` is a **good build system with a bad compass.**

Keep verbatim: the freeze rule, gate-before-build, parallel tracks, one sharded
campaign, the baseline list (it named PI-TD3 independently and correctly).

Add: **Phase −1 literature gate · Phase −0.5 premise falsification · Phase 0
inherited-result audit · a kill branch on every gate.** Its D0 can pass or
escalate but never abandon, which is why it asked whether the projection works
and never whether the policy was worth keeping.

---

## 7. Next action

**Gate 1, on real load and PV data.** Days of work, no new theory, retires the
largest risk in the programme, and simultaneously answers the harder framing
question NREL raises — whether voltage binds once the parametric load model is
replaced by measured data.

Two risks, one experiment, and everything downstream depends on its result.
