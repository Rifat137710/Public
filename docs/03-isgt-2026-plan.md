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

## 1. What the conference paper is

The framing is decided by **G0** below, not assumed.

| | If G0 finds a non-trivial regime | If it does not |
|---|---|---|
| **Claim** | Where network physics enters the controller determines whether constraint satisfaction survives deployment on an unseen feeder. A projection rebuilt from *deployment-side* sensitivities restores it zero-shot; the same projection frozen at training-side values does not. | A deployment-parametrised sensitivity projection converts an unsafe charging schedule into a strictly safe one at 88 % service retention and 3 ms/step, zero-shot across feeder stiffness — and it, not the learner, is what delivers safe service. |
| **Category** | 5 (realistic uncertainty) · mechanism 4 (new formulation) | 4 (new formulation) · fallback 2 |
| **Risk** | requires the regime to exist | none — supported by data already in hand |

Both keep the same experimental skeleton, so **G0 does not change what we build**, only
what the abstract claims. That is deliberate.

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

| # | Task | Why it is required | Est. |
|---|---|---|---|
| **G0** | **Operating-point sweep, heuristics only** — raise load scale and EV count until greedy + projection stops saturating | Decides the paper's framing. No training needed | **~1 h** |
| T1 | Parametric stiffness axis in `FeederConfig`: Z ∈ {0, 2, 4, 6} % at R/X = 2 | The deployment axis. Cheaper and more convincing than a second real feeder — and it is what makes category 5 literal | 4 h |
| T2 | Frozen-sensitivity deployment mode | **Already built** in `ProjectedAgent(frozen_sensitivities=…)`; needs wiring + a test | 2 h |
| T3 | Mixture-line frontier reported for every arm | **Already built** in `projected_heuristics.py`; needs lifting into the main results path | 1 h |
| T4 | Train 5 seeds, `autotune_alpha=False`, at the training stiffness point | 5 seeds, not 3 — the σ claim needs it | ~3 h compute |
| T5 | Deploy 4 stiffness points × arms × 5 seeds | The transfer matrix | ~3 h compute |
| T6 | Silence / diagnose CVXPY `Solution may be inaccurate` warnings | Currently emitted on a minority of solves. Outcomes are measured from AC power flow, not the solver's claim, so results stand — but it must not appear in a released artifact | 2 h |
| T7 | Tests for `ProjectedAgent` and the stiffness axis | Keeps the suite the credibility anchor it is | 2 h |

**Arms (one trained policy, three deployment treatments — no training confound):**

| arm | policy | projection | sensitivities |
|---|---|---|---|
| **A** | SAC-Lag | none | — |
| **B** | SAC-Lag | yes | **frozen at training network** (prior-art style) |
| **C** | SAC-Lag | yes | **deployment network** (ours) |
| **H** | uncoordinated | yes | deployment network — *the honest upper reference* |

Baselines throughout: zero · uncoordinated · droop · **uncoordinated↔droop mixture line**.
Reference: the diagonal (train = deploy) cell. **No MPC oracle at ISGT.**

**Total remaining: ~2 days of code, ~7 h of background compute.**

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
| **"why RL at all?"** | **the question D15 forces — G0 decides whether we answer it or drop the RL claim** |

**Open** — one item, and it is the framing, not the execution. The projected-heuristic
result is strong enough to carry a paper on its own; what G0 determines is whether the
paper is *about safe RL* or *about the safety layer*. Either is publishable. Only the
first is at risk.

**What would get this rejected:** submitting a safe-RL claim without having run G0, and
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
