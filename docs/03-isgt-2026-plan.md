# ISGT 2026 vs. Journal — allocation and plan

**Author:** Md. Rifat Rahman (BUET EEE) · **Status:** live plan, revised after the
projected-heuristic measurement of 2026-08-13.

**Strategy.** The journal is the primary target. ISGT gets the *minimum sufficient
slice* — enough to be accepted, not one experiment more. The journal keeps the
predictive contribution.

---

## 0. The finding that set this plan

The thesis composes the safety projection **only** with the learned policy, so its
ablation cannot separate two questions: *does the safety layer work?* and *does the
learned policy add anything on top of it?*

`scripts/projected_heuristics.py` runs the missing cell — the same projection applied
to a zero-intelligence greedy charger, on the same eval seeds and the same metric code
as the ablation.

| method | violations | SoC met | net cost | $/unit service | ms/step |
|---|---|---|---|---|---|
| zero (idle) | 0.0000 | 0.0000 | $0.00 | — | 1.01 |
| droop (IEEE 1547) | 0.0000 | 0.0067 | $63.12 | $9,400 | 1.04 |
| uncoordinated | 0.0626 | 0.8041 | $685.78 | $853 | 1.04 |
| **SafeSAC** (learned + projection) | **0.0000** | **0.0889** | $255.19 | **$2,870** | ~35 |
| **uncoordinated + projection** | **0.0000** | **0.7094** | $594.66 | **$838** | 3.10 |

**The projection applied to a policy with no learning at all delivers 8.0× the service
of the projection applied to the trained RL policy**, at identical zero violations and
3.4× lower cost per unit of service. It removes 100 % of greedy's violations while
retaining 88 % of its service. Infeasible on 0.15 % of steps; frozen on 0.00 %.

**Consequences.**

1. The safety layer is the load-bearing component. That result is strong and defensible.
2. At this operating point the RL contributes nothing positive — it is worse on service
   *and* on cost efficiency.
3. Therefore neither "SafeSAC beats SAC-Lag" (already dead by sign reversal) nor
   "the learned policy's safety fails to transfer" can be the conference claim without
   an unanswerable *why RL at all?*
4. **Root cause is the operating point, and it is ours.** Load 0.40 / margin 0.010 was
   selected by measuring projection feasibility. There, greedy already reaches SoC 0.804
   at 6.3 % violations — almost no headroom for a controller to be clever in. The
   operating point was optimised for the safety layer and trivialised the control task.

This is a two-line experiment. A reviewer will run it. It had to be run first.

---

## 1. G0 — run, and it decided the paper

`scripts/operating_point_sweep.py`, heuristics only, load scale × EV penetration, with a
deadline-aware request (`UrgencyAgent`) added so *sequencing* could be measured apart from
raw energy demand.

| load | EVs | idle viol | uncoord+proj viol/SoC | retention | **sequencing gain** |
|---|---|---|---|---|---|
| 0.40 | 30 | 0.0000 | 0.0000 / 0.725 | 0.894 | **−0.1358** |
| 0.40 | 60 | 0.0000 | 0.0000 / 0.186 | 0.847 | **−0.0568** |
| 0.40 | 100 | 0.0000 | 0.0000 / 0.016 | 0.879 | **−0.0141** |
| 0.55 | 30 | **0.1341** | 0.1228 / 0.548 | 0.675 | −0.0842 |
| 0.55 | 100 | **0.1341** | 0.1280 / 0.005 | 0.300 | −0.0048 |
| 0.70 | 30 | **0.3173** | 0.3121 / 0.425 | 0.525 | −0.0094 |

1. **The load axis is closed.** At 0.55 the *idle* feeder violates on 13.4 % of steps and at
   0.70 on 31.7 %, destroying the clean attribution audit A4 exists to protect.
2. **At load 0.40 the projection is near-free** — retention 0.85–0.89 at every penetration,
   infeasible on 0.13–0.35 % of steps.
3. **Sequencing gain is negative everywhere.** Deferring non-urgent stations does *worse*
   than charging everything, because deferred energy is never made up. The binding resource
   is energy over the day, not allocation across stations — **the problem has no scheduling
   structure for a policy to exploit.**

**Verdict: no reachable operating point on this testbed rewards a learner.** The conference
paper is about the safety layer.

### A claim I made and had to withdraw

I first reported that *"a projection carrying the training feeder's model is exactly as
unsafe as no projection at all"*, from `scripts/projection_transfer.py`. **That was wrong,
and the fault was in my script.**

Freezing a `Sensitivities` object freezes **two** things — the Jacobian ∂V/∂P, ∂V/∂Q, and
the operating point it was linearised about. I attributed the whole effect to the first.
Splitting them (`ProjectedAgent.frozen_mode`) reverses the reading:

| deploy Z | raw | full snapshot | **Jacobian frozen, voltages measured** | correct model |
|---|---|---|---|---|
| 6.0 % | 0.0577 | 0.0577 | **0.0000** | 0.0000 |
| 8.0 % | 0.0994 | 0.0994 | **0.0000** | 0.0000 |

A projection carrying a **different feeder's Jacobian** but measuring its own voltages is
**exactly as safe** as one with the correct Jacobian. The network model can be wrong at no
cost.

The tell was visible and I missed it: the forward sweep (model from Z = 0.5 %) and the
reverse (Z = 12 %) returned **byte-identical** numbers. A real transfer effect cannot be
symmetric under reversal. Treat an implausible symmetry as a bug signal, not a curiosity.

Physically it is obvious in hindsight. At the station buses ∂V/∂P is dominated by the
**radial path impedance of the 33-bus feeder**, which does not change when the substation
Thevenin impedance does. Across Z ∈ [0.5 %, 12 %] the Jacobians differ by only **1.16×**.
Substation stiffness moves the *base voltage* (0.9658 → 0.9440), not the sensitivities.

**Consequence: stiffness is a weak model-mismatch axis, and the cross-network transfer
claim is not supported on it.** Do not revive it without an axis that changes the *feeder*
impedances or the topology.

### The claim that is supported

> A sensitivity-based safety projection for EV voltage support is **insensitive to
> network-model error** but **critically sensitive to the currency of its linearisation
> base point** — and the relationship is **non-monotone**. Carrying a different feeder's
> Jacobian costs nothing. Refreshing every 5 minutes is *worse* than every 2 hours: the
> same zero violations, 3 pp less service. Refreshing every 4 hours recovers almost none
> of the protection, and never refreshing reproduces the unprojected violation rate
> exactly. We locate the usable band (≤ 2 h), the hosting-capacity envelope (Z ≤ 8 %),
> and the regime past it where the freeze-to-zero fallback becomes the dominant failure
> mode. Exact Jacobian sensitivities (0.662 ms against 447.6 ms) make every point in the
> band computationally free.

**Category 5 (realistic uncertainty)**, supported by 2. Model error and measurement
staleness are the realistic deployment uncertainties, and nobody reports the second.

### The staleness cliff — `scripts/staleness_sweep.py`, 25 episodes

One feeder, correct model throughout, nothing varying but the refresh interval.
Violation step rate (5-min control step, so 12 = hourly, 288 = never):

| Z | source | raw | 1 | 3 | 12 | **24** | **48** | 288 |
|---|---|---|---|---|---|---|---|---|
| 6 % | uncoordinated | 0.0606 | 0.0000 | 0.0000 | 0.0000 | **0.0000** | **0.0586** | 0.0606 |
| 6 % | urgency | 0.0633 | 0.0000 | 0.0000 | 0.0000 | **0.0000** | **0.0599** | 0.0633 |
| 8 % | uncoordinated | 0.1051 | 0.0000 | 0.0000 | 0.0001 | **0.0069** | **0.0883** | 0.1051 |
| 8 % | urgency | 0.1042 | 0.0000 | 0.0000 | 0.0000 | **0.0051** | **0.0831** | 0.1042 |
| 10 % | uncoordinated | 0.1361 | 0.0408 | 0.0413 | 0.0294 | 0.0217 | 0.1058 | 0.1361 |
| 10 % | urgency | 0.1349 | 0.0408 | 0.0415 | 0.0300 | 0.0164 | 0.1001 | 0.1349 |

Service (SoC targets met) for the same cells, uncoordinated request:

| Z | raw | 1 | 3 | 12 | **24** | 48 | 288 |
|---|---|---|---|---|---|---|---|
| 6 % | 0.840 | 0.742 | 0.747 | 0.738 | **0.764** | 0.793 | 0.840 |
| 8 % | 0.840 | 0.641 | 0.639 | 0.667 | **0.689** | 0.717 | 0.840 |

**1. The cliff sits between 24 and 48 steps (2 h and 4 h).** At or under 2-hourly the layer
is perfect at Z ≤ 6 %; at 4-hourly it recovers only ~3 % of the protection; never-refreshed
reproduces the raw rate *exactly*, for every Z and both request sources. The layer does not
degrade gracefully — it stops being a safety layer.

**2. Faster is not better — there is a sweet spot.** At Z = 6 %, refresh 24 *dominates*
refresh 1: identical zero violations, and **0.764 against 0.742** service. A base point that
tracks every sag curtails harder than necessary; a mildly stale one permits more while still
holding the band. Practical guidance for a DSO is "every two hours", not "as fast as you
can" — and that is a more useful sentence than the usual one.

**3. This exonerates the thesis on B3.** The audit flagged the refresh as hourly while the
text claimed per-step. Hourly is not merely sufficient at Z ≤ 8 %, it is **inside the
optimal band**. B3 is a documentation defect, not a safety defect. Say so.

**4. The hosting-capacity envelope is Z ≤ 8 %.** At Z = 10 % the *idle* feeder already
violates on 5.16 % of steps, so no refresh setting reaches zero — the best is 0.0164.

**5. Past the envelope the method's own fallback becomes the problem.** At Z = 10 % the
projection is infeasible on 0.7–8.6 % of steps, and infeasibility triggers freeze-to-zero —
which removes all V2G support exactly when the feeder needs it. Violation rate stops being
monotone in refresh interval there (0.0408 → 0.0294 → 0.0217 → 0.1058). Report Z = 10 % as
the **boundary of validity** and name the fallback as the suspected cause; the redesign is
journal item **J6**, not an ISGT claim.

Infeasibility is **0.0000 at refresh 288 everywhere** — the signature of the inert case. The
stale base point makes the constraint look satisfied, the pre-check skips the solve, and the
raw request passes through untouched. That is the mechanism, and it is directly measured.

---

## 2. Category placement

| Category | Verdict |
|---|---|
| 1 — completely new algorithm | ✕ we invent no algorithm |
| 2 — existing method + new power-system problem | ◑ honest description; **lowest-scoring tier**, do not lead with it |
| 3 — existing method + new constraint | ✕ the voltage band is not new |
| **4 — existing method + new formulation** | ✅ **the mechanism claim** — the projection must be parametrised on the *deployment* network. Earned by the frozen-sensitivity arm |
| **5 — existing method + realistic uncertainty** | ✅ **lead with this** — deployment-grid mismatch *is* model uncertainty, and becomes literally accurate once the deployment axis is a parametric sweep |
| 6 — improved objective | ✕ |
| 7 — new system architecture | ✕ |
| 8 — new application | ✕ weakest tier — actively avoid this framing |

**Lead #5, prove #4, describe #2.**

---

## 3. TABLE 1 — CONFERENCE (ISGT 2026)

### 3a. Done

| # | Item | Result | Where |
|---|---|---|---|
| D1 | Tested package ported from the notebook | 79 tests, ~3m13s | `safesac/`, `tests/` |
| D2 | Exact reproduction of Table 6.1 | all 6 rows, 2–6 s.f. | `results/table_6_1_reproduction.json` |
| D3 | Analytic radial power flow | 25.75 → **0.103 ms** (249×), matches pandapower to 5e-9 pu | `safesac/powerflow.py` |
| D4 | Analytic Jacobian sensitivities | 447.6 → **0.662 ms** (677×), matches thesis Table 4.1 to 5 s.f. | `tests/test_powerflow.py` |
| D5 | PF + sensitivity per step | 63.05 → **0.159 ms** (398×) | — |
| D6 | Attributable-violation metric (paired zero-injection, 95 % CI) | audit A4 closed | `safesac/evaluate.py` |
| D7 | Cost-critic clamp — λ no longer pinned at floor | baseline J_C 0.2609 with Q_C −0.7434 | audit A2 |
| D8 | Dual-windup fix (realised-cost ascent + λ cap) | λ→1888 with J_C≡0 eliminated | N1 |
| D9 | Entropy-temperature diagnosis + fixed-α sweep | log π +7.49, tanh Jacobian +13.42, 46.2 % of states; α = 0.003 | N2, `results/alpha_sweep.json` |
| D10 | Potential-based reward shaping | SoC at ep 25: 0.043 → 0.388 | N3 |
| D11 | Operating point chosen by measurement | margin 0.010: infeasible 0.0017, realised violations 0.0000 | `results/stage1_operating_point.json` |
| D12 | **Fair ablation, 3 seeds × 200 ep** | published **+0.2921 → −0.1285** (sign reversal) | `results/ablation/ablation.json` |
| D13 | Safety-variance result | σ across seeds **0.027 → 0.000** | same |
| D14 | Budget probe, 500 episodes | flat — the learner is **not** budget-limited | `results/budget_probe.json` |
| D15 | **Projected-heuristic baseline** | uncoord+proj **0.0000 / 0.7094**, 8.0× the learned arm | `results/projected_heuristics.json` |
| D16 | Heuristic mixture frontier | SAC-Lag **beaten** by a coin flip (0.217 vs 0.716); projected arms dominate it | same |
| D17 | A5 infeasibility quantified | 12.50 % of steps at the *published* operating point | audit A5 |
| D18 | Seed derivation, disjoint train/eval bands, resume, checkpoint hashes | bit-exact reproduction verified | `safesac/config.py` |

### 3b. To do

| # | Task | Why it is required | State |
|---|---|---|---|
| **G0** | Operating-point sweep, heuristics only | Decided the framing | ✅ **done** — §1 |
| **T1** | Parametric stiffness axis, `ExperimentConfig.stiffness()` | The deployment axis. Always the weak topology so bus count (34) and obs dim (95) stay constant — a study that changed the obs vector mid-way could not claim zero-shot transfer | ✅ **done, validated** |
| **T2** | Frozen-sensitivity treatment | The mechanism control; earns category 4 | ✅ **done + tested** |
| **T3** | Mixture-line frontier | Pre-empts "a coin flip beats you" | ✅ **done** |
| **T9** | Extended stiffness sweep, both directions | Exposed the confound above; axis retired | ✅ **done — negative** |
| **T11** | **Model-error vs base-point split** (`frozen_mode`) | The correction. Jacobian error is free; base-point staleness is fatal | ✅ **done + pinned by test** |
| **T12** | **Staleness cliff sweep** | The headline | ✅ **done at 12 ep** |
| **T13** | Re-run T12 at 25 episodes, refresh axis {1,3,12,24,48,288} | The non-monotonicity replicated across both request sources; cliff refined to 24-48 steps | ✅ **done** |
| T4 | Train 3–5 seeds, `autotune_alpha=False` | Supporting row: the findings hold for a *learned* request source too | ⬜ ~2 h Kaggle |
| T5 | Learned policy across the **refresh** axis at Z ∈ {6, 8} % | Completes the request-source set | ⬜ ~1 h |
| T6 | CVXPY `Solution may be inaccurate` warnings | Outcomes are measured from AC power flow, not the solver's claim, so results stand — but this must not ship in a released artifact | ⬜ 2 h |
| T7 | Tests for the stiffness axis + staleness invariants | Keeps the suite the credibility anchor | ⬜ 2 h |
| T10 | A5 infeasibility across the refresh axis | The method's own failure mode, with a number | ⬜ free — already collected |

**Axes (identical upstream request; one thing varies at a time):**

| axis | levels | what it establishes |
|---|---|---|
| **refresh interval** | 1, 3, 12, 48, 288 steps | **the cliff — the headline** |
| **model error** | correct Jacobian vs another feeder's | it is free |
| **feeder stiffness** | Z ∈ {0.5 … 12} % | the hosting-capacity envelope (Z ≤ 8 %) |

**Request sources:** uncoordinated · droop · urgency · SAC-Lag (supporting row).
Baselines: zero · **uncoordinated↔droop mixture line**. **No MPC oracle at ISGT.**

**Total remaining: ~1 day of code, ~3 h of compute.** The headline needs no training at all;
Kaggle is only for the supporting learned row.

---

## 4. TABLE 2 — JOURNAL

| # | Item | State | Note |
|---|---|---|---|
| J1 | **C3 network-distance predictor — on a *real* mismatch axis.** T11 showed station-bus ∂V/∂P is set by the radial path impedance, so substation stiffness varies it only 1.16×. The axis must change *feeder* impedances, conductor sizing, or topology (IEEE 123-bus, European LV). Still the journal's 30 %+ delta, but the ISGT work has now ruled out the cheap version of the axis | ⬜ |
| J2 | MPC / multi-period OPF oracle (SOC relaxation of branch flow) | ⬜ | "How far from optimal?" — journal-mandatory, ISGT-optional |
| J3 | Second *real* feeder — IEEE 123-bus and/or European LV (unbalanced 3-phase) | ⬜ | External validity |
| J4 | Kou-style fixed-model ablation, full treatment | 🟨 arm B is the seed of it | ISGT gets one arm; journal gets the sweep |
| J5 | Sensitivity-staleness sweep {1, 12, 288, never} | ⬜ | Genuinely novel and cheap — nobody reports it. Enabled by D4 |
| J6 | **Infeasibility-fallback redesign** | ⬜ | Today the handler *shuts the station down* exactly when voltage support is most needed. Replace with graceful degradation. A real method contribution |
| J7 | A3 high-PV overvoltage / reactive channel | ✅ built | Grid-awareness gap **67.617 kW** vs published 25.865. Off-topic for a transfer paper |
| J8 | Full 5–10 seed statistics, IQM + stratified bootstrap | 🟨 5 seeds at ISGT | |
| J9 | Robustness — sensitivity noise, latency, estimation from measured data, forecast error, topology change | ⬜ | |
| J10 | Measured load data (UK-DALE / REFIT / ELAAD) | ⬜ | Placeholder survivable at ISGT, not at TSG |
| J11 | A5 full failure gallery | 🟨 rate measured | ISGT gets one sentence |
| J12 | N1/N2/N3 full treatment | 🟨 fixed | **N2 is publishable alone** — SAC's entropy target assumes an interior optimum; this task's is on the bounds |
| J13 | Margin / refresh-cadence / cone-vs-linear ablations | 🟨 margin done | |

---

## 5. Cut from both papers — final

| Cut | Reason |
|---|---|
| "+0.292 in-distribution service gain" | Reverses sign under a controlled protocol |
| §6.9 transfer numbers as published (0.447 vs 0.000) | Drawn from the α = 19.402 diverged run |
| Five-gate decision protocol | Gate 1 tautological, Gate 2 a solver failure, Gate 3 a non-test, Gate 4 a diverged run |
| ±80 kW projection demo (Table 5.3 / Fig. 5.2) | Sign inverted; computed at load 0.40 while experiments ran at 0.50; infeasible at 0.50 |
| **"V–P dominance" as a *finding*** | It is a property of `case33bw`'s line impedances, not of the weak-grid modification. Keep the numbers, drop the claim |
| Transformer / thermal constraint | Max loading 0.011 pu against a 1.0 limit — never binds, and there is no transformer in the model |
| Line-loss reward term | Swamped the stated objective (audit B1) |
| Episode-level *p*-values (p = 0.86, p < 10⁻⁸), d = 10.6 | Pseudo-replication — episodes are not independent samples of training. **Seed-level CIs only** |
| Convergence-detector early stopping | Produced the 85–114 episode unequal-budget confound |
| 7-day scenario capability | No experiment exercises it |
| Random-policy rollout · per-episode boxplots · fleet Monte-Carlo as built | Motivational, subsumed, or ignores the binding 80 kVA station cap |
| Ch. 2 background · Ch. 7 societal · appendix code listings | Degree requirements; Listing A.1 does not match the implementation |

---

## 6. Honest acceptance assessment

**Closed** — every standard rejection cause at an ISGT-class venue:

| Objection | Status |
|---|---|
| "unsound / unverifiable" | 79 tests · exact reproduction · physics to 5e-9 pu · bit-exact seeds |
| "no credible baseline" | zero · uncoordinated · droop · **mixture line** · **projected heuristic** |
| "single seed, no statistics" | 5 seeds, seed-level CIs |
| "unclear novelty" | frozen-sensitivity arm isolates the mechanism → category 4/5 |
| "out of scope" | V2G voltage support is core ISGT |
| **"why RL at all?"** | **answered by not claiming it.** G0 found no operating point that rewards a learner, so the paper does not assert one. The learned policy is one request source, and its underperformance is reported |

**Open — one item, and it is now an evidence-breadth question, not a framing one.** The
effect appears at a single deployment point (Z = 6 %); three of four points are
violation-free for every method. T9 extends the range to Z = 12 % to convert a step into a
curve. If the curve does not materialise, the claim narrows from *"degradation grows with
network distance"* to *"there exists a deployment gap at which a carried model becomes
wholly inert"* — weaker, still true, still publishable, and still category 4.

**What would have got this rejected:** submitting a safe-RL claim without running G0, and
meeting a reviewer who runs `projected_heuristics.py` in ten minutes.

---

## 7. Order of work

1. **G0** — operating-point sweep (~1 h). Decides the framing.
2. **T1–T3** — stiffness axis, frozen-sensitivity wiring, mixture line (~1 day). Required
   under either framing.
3. **T4–T5** — train and deploy (~7 h background).
4. **T6–T7** — solver warnings, tests (~half a day).
5. Write.

Nothing here is speculative and nothing is on the critical path twice.
