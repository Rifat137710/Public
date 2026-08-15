# Reconciliation — the three standing plans vs. measured state

**Written:** 2026-08-15
**Inputs:** `final_plan.md` (ISGT plan, rev. 2026-08-13) · `Q1_workflow.md`
(TSG phase workflow) · `SafeSAC_ISGT_vs_Journal_allocation_1.md` (the
allocation document from the parallel chat).

---

## 0. The assumption all three share, and it is false

Every one of these documents allocates assets on the premise that **the
contribution is SafeSAC — a learned policy composed with a projection.** Doc 1
splits assets between conference and journal on that basis. Doc 2's flowchart
validates and hardens that controller. Doc 3's allocation table is organised
around it row by row.

Two measurements removed that premise:

- **D12** — the fair ablation reversed sign, +0.2921 → **−0.1285**.
- **D15** — the same projection on a zero-intelligence greedy charger delivers
  **8.0× the service** of the projection on the trained policy, at identical
  zero violations.

The learned policy is not the load-bearing component. **The allocation tables in
all three documents therefore need re-deriving, not patching** — they are
dividing an asset that turned out not to exist.

What *is* load-bearing is the projection, and the only property of it that
survived scrutiny as a headline is its dependence on base-point currency.

---

## 1. `final_plan.md` — ISGT plan

### 1.1 Execution: near-complete

| # | Task | State |
|---|---|---|
| **G0** | Operating-point sweep | ✅ **done — and it decided against the RL framing.** Sequencing gain negative in all 6 cells; no reachable operating point rewards a learner |
| T1 | Parametric stiffness axis | ✅ done — `ExperimentConfig.stiffness()`, obs dim held at 95 across the sweep |
| T2 | Frozen-sensitivity deployment mode | ✅ done **and extended** — `ProjectedAgent.frozen_mode ∈ {jacobian, snapshot}`, the split that exposed my own confound |
| T3 | Mixture-line frontier | ✅ done |
| **T4** | Train 5 seeds at training stiffness | ❌ **retired** — axis invalidated |
| **T5** | Deploy 4 stiffness × arms × 5 seeds | ❌ **retired** — axis invalidated |
| T6 | CVXPY inaccuracy warnings | ✅ done — accepted on *measured residual*, not on the solver's label |
| T7 | Tests for the new surfaces | ✅ done — **84 tests** |

D1–D18 in §3a all remain true; they are execution facts, not claims.

**T4/T5 were not skipped — they were killed by a measurement.** Freezing the
Jacobian while measuring deployment voltages gives 0.0000 violations, identical
to the correct model, because station-bus ∂V/∂P is dominated by radial path
impedance that substation stiffness does not change (Jacobians differ **1.16×**
across Z ∈ [0.5 %, 12 %]). `scripts/transfer_study.py` is retained with a
retirement docstring as the record.

### 1.2 Framing: both branches of §1 are dead

| §1 branch | Status |
|---|---|
| "If G0 finds a non-trivial regime" → *where network physics enters determines whether constraint satisfaction survives deployment* | **dead** — G0 found no such regime |
| "If it does not" → *deployment-parametrised projection … zero-shot across feeder stiffness* | **dead** — stiffness is a weak mismatch axis; the frozen-Jacobian arm is as safe as the correct one |

The plan was explicitly built so that "G0 does not change what we build, only
what the abstract claims." That held — every artifact T1–T3, T6–T7 is in use.
**What it did not anticipate is that G0 would kill both prepared abstracts.**

The replacement claim came from §4 of the same document — row **J5**.

### 1.3 Category placement: shifted

Planned *lead 5, prove 4, describe 2*. Current: **still 5, for a different
reason.** The realistic uncertainty is now **base-point age**, not
deployment-grid mismatch. Category 4 (new formulation) is no longer earned at
the conference — we propose no formulation there — and **moves to the journal**,
where age-aware projection is exactly a new formulation.

### 1.4 The journal table (§4) — hollowed out from the top

| # | Item | State |
|---|---|---|
| **J1** | C3 network-distance predictor — regress degradation on ‖S_P^i − S_P^j‖_F, SCR, R/X | ❌ **dead on the only axis we built**, and the mechanism predicts it fails generally: the dependent variable is ≈0 whenever deployment voltages are measured, so there is nothing for network distance to predict. *This was the designated journal headline.* |
| J2 | MPC / multi-period OPF oracle | ⬜ not started — **still required** |
| J3 | Second real feeder (123-bus / European LV) | ⬜ not started — **still required** |
| **J4** | Kou-style fixed-model ablation | ✅ **done, and spent at the conference** — it is `frozen_mode` |
| **J5** | Sensitivity-staleness sweep {1, 12, 288, never} | ✅ **done, and promoted to the conference headline** |
| J6 | Infeasibility-fallback redesign | ⬜ not started — **now more urgent**: freeze-to-zero becomes the dominant failure mode past Z = 8 % (0.1171 at Z = 10 %, r48) |
| J7 | A3 high-PV reactive channel | ✅ built, off-topic for this framing |
| J8 | 5–10 seeds, IQM + stratified bootstrap | 🟨 3 seeds; **per-episode arrays not stored** — blocks all interval estimates |
| J9 | Robustness — noise, latency, estimation from measured data, forecast error, topology | ⬜ **this is no longer an appendix; it is the journal spine** |
| J10 | Measured load data (UK-DALE / REFIT / ELAAD) | ⬜ **now on the critical path** — the drift bound is not credible on synthetic load |
| J11 | A5 failure gallery | ✅ rate measured (T10) |
| J12 | N1/N2/N3 full treatment | 🟨 fixed; **N2 remains publishable alone** |
| J13 | Margin / refresh / cone-vs-linear ablations | 🟨 margin ✅, refresh ✅, cone-vs-linear ⬜ |

**This is the central finding of the reconciliation.** The journal was planned
around J1, with J4 and J5 held back as supporting material. J1 is dead; J4 and
J5 have been spent at the conference because they were the only assets that
survived. **The journal has lost its headline and two of its reserves.**

That is precisely the hole `05-research-programme.md` proposes to fill:
age-aware safety projection is a *replacement* journal headline, derived from
the surviving asset rather than from the dead one.

---

## 2. `Q1_workflow.md` — TSG phase workflow

| Phase | State |
|---|---|
| **Phase 0** — structural vs. policy violation decomposition | ✅ **done.** Attributable-violation metric (D6, paired zero-injection, 95 % CI). Decision node D0 = **YES**, projection kills policy-attributable violations (0.0000) |
| **Phase 1** — successive-linearization projection → near-zero true-AC | ⬜ **not started** |
| **FREEZE** | not reached |
| **Phase 2** — baselines: OPF, MPC, PPO-Lag, CPO, PI-TD3, vanilla | ⬜ not started |
| **Phase 3** — feeders 33/69/123 + real load-PV-EV data | ⬜ not started |
| **Phase 4/5/6** — sharded campaign | 🟨 partial: 3 seeds × 200 ep on the staleness axis; 3 seeds on the ablation. Not the full matrix |
| **Phase 7** — writing | ⬜ not started |

Two observations.

**The flowchart passed its gate but its downstream premise is wrong.** D0 asks
whether the projection removes policy-attributable violations. It does — so the
chart routes to "harden SafeSAC." But G0 and D15 showed the *policy* is not
worth hardening. The workflow has no branch for "the policy is unnecessary,"
which is the branch we are actually on.

**Phase 1 is not wasted — it is half of the journal method.** Successive
linearization re-linearises *within* a control step until the AC solution
satisfies the band. Age-aware projection bounds drift *across* steps between
measurements. Both attack linearisation currency, at different timescales, and
they compose: intra-step iteration removes the residual the tightening would
otherwise have to cover. **Phase 1 should be retained and folded into the
journal method, not discarded.**

**Phase 2's baseline list was well chosen** — PI-TD3 appears on it, and PI-TD3
is exactly what the competitive-set audit (`05-research-programme.md` §1) found
running IEEE 34- and 123-bus with hundreds of EVs. That instinct was right.

---

## 3. `SafeSAC_ISGT_vs_Journal_allocation_1.md` — the parallel-chat allocation

### 3.1 Both of its papers are dead

| Paper | Claim | Status |
|---|---|---|
| ISGT Asia 2026 | "projection roughly doubles EV service (0.28 → 0.57) at a statistically indistinguishable violation rate" | ❌ **dead** — that is the +0.292 that reverses to **−0.1285** under matched budgets, α ceiling and episode count |
| Journal | "where network physics is placed determines robustness to deployment-grid mismatch; Lagrangian safety does not transfer, projection rebuilt from deployment sensitivities transfers by construction" | ❌ **dead** — the frozen-Jacobian arm transfers fine. The effect was the base point, not the placement of physics |

Its σ result survives: safety variance across seeds **0.027 → 0.000**.

### 3.2 It contained the one line that survived

Row: *"Sensitivity-staleness sweep — ✕ ISGT | ✅ journal **new contribution**.
'How stale can the linearisation get before safety breaks?' Nobody reports
this. Cheap to run, genuinely novel."*

**That is the paper.** Of every claim, framing and allocation across all three
documents, this single line is the one that survived contact with the
measurements and became a headline. It was filed as a minor journal extra, in
the wrong paper, next to two dead headlines — but it was right about where the
value was.

Recorded plainly because I argued against that document at length, and this row
was correct.

### 3.3 Its appendix fixes — still outstanding, still free

| # | Fix | State |
|---|---|---|
| 1 | **Sign convention** — code is authoritative: `p_kw > 0` = injection = V2G discharge (pandapower `sgen`); thesis §4.6 states the opposite | ⬜ **outstanding — must be fixed in any text we write** |
| 2 | Retrain SAC-Lag with matched α ceiling, `lr_critic`, episode budget | ✅ done — this *is* D12 |
| 3 | ≥ 3 training seeds, mean ± std across seeds | ✅ done |
| 4 | Delete transformer / thermal-limit claims | ⬜ outstanding (text-only) |
| 5 | "State the refresh honestly as hourly, frame staleness as a limitation" | ❌ **obsolete and inverted** — the 677× sensitivity speedup makes any cadence affordable, and we *measured* that 12 steps sits inside the safe band. It is a validated design choice, not a confession |
| 6 | Correct the reward equation to match code; fix Eq. (4.6) units | ⬜ outstanding (text-only) |
| 7 | Add Kou et al. 2020 + AAMAS 2023 to related work | 🟨 **superseded and expanded** — see `04-novelty-and-reviewer-defence.md`: add Bai et al. TPWRS 2022 (nearest prior art), INDI, AoI-aware LFC, sporadic-measurement CBFs, adaptive smart-meter certification |

---

## 4. Net position

**Conference (ISGT 2026).** Execution against `final_plan.md` is complete —
G0, T1, T2, T3, T6, T7 all done, T4/T5 killed by measurement, 84 tests, Stage 0
reproduction gate re-verified. The framing changed twice and settled on J5. The
outstanding work is not experimental; it is the claim discipline in
`04-novelty-and-reviewer-defence.md` §5 (demote the weak claim, concede the
mechanism, ship the diagnostic) plus text fixes 1, 4 and 6 above.

**Journal.** `Q1_workflow.md` sits at Phase 0 complete, Phase 1 not started,
everything downstream not started. `final_plan.md`'s journal table has lost its
headline (J1) and spent two reserves (J4, J5) at the conference. **The journal
needs a new contribution, not a longer version of the conference paper.**

The proposal in `05-research-programme.md` — age-aware safety projection —
fills that hole, retains Phase 1 as its intra-step half, keeps J2, J3, J6, J9,
J10 as its required supporting work, and inherits J8's statistics debt.

**Immediate next action is unchanged:** run the realistic-cadence falsification
(`05-research-programme.md` §5) before investing in the theory.
