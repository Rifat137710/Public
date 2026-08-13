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

### The claim

> A safety projection that ships with its **training** network's sensitivities silently
> stops being a safety layer when deployed on a feeder of different stiffness — it admits
> *exactly* the unprojected violation rate. One that rebuilds its sensitivities from the
> **deployment** feeder holds the band zero-shot, at ~89 % service retention, independent
> of what controller is upstream of it.

**Category 4 (new formulation), supported by 5 (model uncertainty).** The learned policy
becomes one *request source* among several, and its underperformance against greedy is
reported as a finding rather than hidden.

### First evidence — `scripts/projection_transfer.py`, no training required

Model built at Z = 0.5 %, deployed unchanged (violation step rate):

| deploy Z | source | raw | **frozen model** | **deployment model** |
|---|---|---|---|---|
| 0.5 % | uncoordinated | 0.0000 | 0.0000 | 0.0000 |
| 2.0 % | uncoordinated | 0.0000 | 0.0000 | 0.0000 |
| 4.0 % | uncoordinated | 0.0000 | 0.0000 | 0.0000 |
| **6.0 %** | **uncoordinated** | **0.0561** | **0.0561** | **0.0000** |
| **6.0 %** | **urgency** | **0.0593** | **0.0593** | **0.0000** |
| 6.0 % | droop | 0.0000 | 0.0000 | 0.0000 |

The frozen-model projection is not merely worse — it is **exactly as unsafe as no
projection at all**, to four decimals, for both aggressive sources. At Z = 0.5 % the carried
model believes ∂V/∂P is small, so no constraint binds and the raw request passes untouched.
Rebuilt at deployment: every violating step removed, SoC 0.864 → 0.770.

Droop is the control — never violates at any stiffness, with or without the projection, and
serves 0.019. Safe because it barely charges. It shows the effect is the safety layer, not
conservatism.

**Known weakness, not papered over:** three of four deployment points are violation-free for
every method, so this is a *step*, not a degradation curve. Extended sweep to Z = 12 % and
the reverse direction (weak-feeder model deployed on stiff feeders — expected
over-conservative rather than unsafe) are running.

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
| **T9** | **Extended stiffness sweep, Z → 12 %, both directions** | Turns a step into a degradation curve; the reverse direction tests over-conservatism | 🔵 **running** |
| T4 | Train 5 seeds, `autotune_alpha=False` | Now a *supporting row*, not the headline — the learned policy is one request source | ⬜ ~3 h Kaggle |
| T5 | Deploy learned policy across the stiffness axis | Completes the request-source set | ⬜ ~1 h |
| T6 | CVXPY `Solution may be inaccurate` warnings | Outcomes are measured from AC power flow, not the solver's claim, so results stand — but this must not ship in a released artifact | ⬜ 2 h |
| T7 | Tests for the stiffness axis + transfer invariants | Keeps the suite the credibility anchor | ⬜ 2 h |
| T10 | A5 infeasibility across the stiffness axis | The method's own failure mode, stated with a number | ⬜ 1 h |

**Treatments (identical upstream request; only the projection's physics differs):**

| treatment | projection | sensitivities |
|---|---|---|
| **raw** | none | — |
| **frozen** | yes | **training network** (prior-art parametrisation) |
| **deploy** | yes | **deployment network** (ours) |

**Request sources:** uncoordinated · droop · urgency · SAC-Lag (supporting row).
Baselines: zero · **uncoordinated↔droop mixture line**. **No MPC oracle at ISGT.**

**Total remaining: ~1 day of code, ~4 h of compute** — down from ~2 days and ~7 h, because
the headline result needs no training.

---

## 4. TABLE 2 — JOURNAL

| # | Item | State | Note |
|---|---|---|---|
| J1 | **C3 network-distance predictor** (regress degradation on ‖S_P^i − S_P^j‖_F, SCR, R/X; held-out feeders, R² > 0.7) | ⬜ | **The journal's contribution. Deliberately withheld from ISGT** — this is the 30 %+ delta IEEE requires |
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
