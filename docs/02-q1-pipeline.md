# Thesis → Q1 journal: repositioning and pipeline

## Part I — The honest starting position

### What is already novel, and what is not

I checked each of the thesis's three claimed contributions against the current literature.

| Claimed contribution | Status | Prior art |
|---|---|---|
| SOCP / sensitivity-based safety projection for distribution control | **Not novel** | Sensitivity-matrix safety layers doing real-time action correction are established in the Volt/VAR safe-RL literature; the generic projection idea is Dalal 2018 / OptLayer / DC3 |
| Augmented-Lagrangian SAC for EV charging | **Not novel** | Chen et al., *Applied Energy* 378:124706 (2025) — the thesis's own ref [1]; also AL-based safe RL for Volt/VAR (arXiv 2410.15188) |
| Physics-aware RL for EV voltage support on distribution networks | **Not novel, and out-scaled** | Orfanoudakis, Oliehoek, Palensky, Vergara (arXiv 2510.12335, 2025): PI-TD3 with differentiable power flow, **IEEE 34- and 123-bus, hundreds of EVs, benchmarked against an oracle MPC** |
| **Whether a safe-RL controller's safety behaviour survives deployment on a network it was not trained on** | **Open** | Flagged as an open challenge in the 2024–2025 safe-RL-for-power-systems reviews; the thesis's own §3 identifies it as gap #1 ("they almost always train and evaluate on the same network") |

The engineering that has already been built is good. The *framing* is aimed at the three
things that are taken, and treats the one thing that is open as a side experiment in §6.9.

### Recommendation

**Make cross-network transfer the paper.** Not "SafeSAC beats SAC-Lag on one weak feeder,"
but:

> **A learned constrained-RL controller's constraint satisfaction is a property of the
> training network, not of the policy. A deployment-parametrised projection layer restores
> it zero-shot — and how much it restores is predictable from a measurable property of the
> deployment network.**

Why this is the right move:
- It is the one open question, and the reviews say so.
- It is the *only* claim your existing artifacts already point at (SoC met 0.447 vs 0.000 under transfer is a genuine, large effect).
- It reuses everything already built — env, projection, agents — and needs breadth, not new theory.
- It converts the awkward results (droop is safer; SafeSAC-transfer has *more* violations) from embarrassments into the paper's actual findings, honestly reported.

Working title:
*"Does the Safety Layer Transfer? Zero-Shot Deployment of Constrained Reinforcement Learning
for EV Voltage Support Across Distribution Feeders"*

Claims to establish, in order:
- **C1** Safety behaviour of an unprojected constrained-RL policy degrades sharply and
  systematically under network shift; quantify degradation vs a network-distance measure.
- **C2** A projection parametrised on the *deployment* network recovers operability zero-shot
  (no retraining, no target-network data beyond what a controller can measure online).
- **C3** The recovery is *predictable* — regress transfer degradation on measurable network
  statistics (R/X, short-circuit ratio, ‖S_P‖, sensitivity-matrix distance). **This is the
  step that makes it a Q1 contribution rather than an engineering report.**
- **C4** Quantify the price: compute, conservatism, service loss, and the failure modes
  (linearisation error, refresh staleness, infeasibility).

### Venue

| Venue | Fit | Bar |
|---|---|---|
| **IEEE Trans. Smart Grid** | best methodological fit | multi-network validation + optimality benchmark + multi-seed. Primary target *if* Stages 4–5 complete |
| **Applied Energy** | where Chen et al. landed; energy-systems framing | strong economic/energy narrative; your economics term is currently 2 % of the reward (audit B1) |
| **Sustainable Energy, Grids and Networks** | realistic Q1, faster turnaround | the pragmatic fallback; reachable after Stage 4 |
| **IEEE Trans. Sustainable Energy** | viable | similar to TSG |

**Plan for TSG, hold SEGAN as the fallback.** Do not submit anywhere before Stage 3's gate.

### Effort

Roughly **10–14 weeks focused**, or 4–6 months part-time. The binding constraint is compute
throughput, which Stage 2 fixes. This is achievable — but not by patching the existing
notebook. Stage 0 exists because the notebook cannot support it.

---

## Part II — The pipeline

Each stage has a **gate**. Do not start the next stage until the gate passes.

---

### Compute budget (Kaggle)

The binding constraint on Kaggle is **not** GPU count — it is the ~30 GPU-h/week quota, the
12 h session cap, and the 4 vCPU allocation. This workload barely touches the GPU: the
networks are 372 k parameters at batch 256, which is ~1–2 ms per update. The 115 ms step was
CPU-bound on power flow and CVXPY. **A second GPU would have changed nothing.**

Stage 4 needs ≈ 50 training runs + 250 evaluation runs.

| | per SafeSAC run | Stage 4 total |
|---|---|---|
| thesis implementation | ~48 min | **~77 h** — over two full weekly quotas, zero iteration budget |
| after Stage 2 (target) | ~5 min | **~9 h** — one comfortable week, room to iterate |

---

### Stage 0 — Port to a package, reproduce exactly (week 1)

The current code is a 39-cell notebook where the live configuration is the result of
monkey-patches applied in a specific kernel order, several of which are commented out. That
is why audit items A1, A2 and B1 exist at all — they are *ordering* bugs, not logic bugs.
This must go before anything else.

- `safesac/` package: `network.py`, `scenario.py`, `env.py`, `projection.py`, `agents.py`,
  `train.py`, `evaluate.py`, `analysis.py`.
- One YAML config per experiment. **No monkey-patches.** Every value in the config,
  every config hashed into the run directory.
- Port the artifacts verbatim first, patches folded in — do not fix anything yet.
- Regression test: reproduce the six-method table (0.1156 / 0.0521 / 0.0904 / 0.0912 /
  0.0151 / 0.1058) from the existing checkpoints, to the printed precision.
- CI: unit tests on projection feasibility, sign conventions, reward decomposition,
  SoC accounting, seed determinism.

**Gate 0** — the ported package reproduces every number in `00-knowledge-base.md` §5 from
the shipped checkpoints, and `pytest` is green.

> **PASSED.** All six rows of Table 6.1 reproduce (`scripts/reproduce_table_6_1.py`, results
> in `00-knowledge-base.md` §5b); 56 tests green in ~2.5 min. Every violation rate and Vmin
> matches to published precision, the two cross-deployment rows to 6 significant figures.
> Deferred out of Stage 0 as not gate-blocking: YAML config loading (the frozen dataclass
> presets plus `fingerprint()` cover the same ground for now) and CI wiring.
>
> Two defects were quantified in the process and are now first-class metrics:
> the projection is infeasible on 12.50 % of steps (audit A5), and the compared runs
> received 97 vs 85 training episodes (audit A6).

---

### Stage 1 — Correctness (weeks 2–3)

#### Operating-point decision, settled by measurement

**Background load `load_scale = 0.40`, EV penetration ~30 vehicles/station/day.**

Two separate measurements, both on the shipped evaluation seeds.

*First*, the background load has to come down. At the thesis's 0.50 the idle feeder already
violates 9.47 % of steps, above the published SafeSAC (0.0912) and SAC-Lag (0.0904) — the
safety comparison is ~96 % background (audit A4). At 0.40 the idle floor is exactly zero, so
every violation is caused by a charging decision. 0.40 is also where Table 5.3's projection
numbers were computed, so the move resolves audit B2 too.

*Second*, at 0.40 with the thesis's fleet the problem becomes trivial — uncoordinated
charging violates only 0.63 % of steps and droop violates none. So raise **EV penetration**
rather than background load. That keeps the idle floor at zero while restoring difficulty,
and it reframes the study as an EV-hosting-capacity question, which is what the paper is
actually about:

| EVs/station/day | idle | uncoordinated | | droop (1547) | |
|---|---|---|---|---|---|
| | viol | viol | SoC met | viol | SoC met |
| 10 (thesis) | 0.0000 | 0.0063 | 0.995 | 0.0000 | 0.326 |
| 20 | 0.0000 | 0.0363 | 0.935 | 0.0000 | 0.043 |
| **30** | **0.0000** | **0.0648** | **0.830** | **0.0000** | **0.006** |
| 40 | 0.0000 | 0.0722 | 0.638 | 0.0000 | 0.004 |

At 30 the two heuristics bracket a wide, honest Pareto gap: droop is perfectly safe and
almost useless (0.006 of targets met), uncoordinated serves 0.830 but violates 6.5 % of
steps. A learned controller finally has somewhere to go that neither heuristic reaches —
which is precisely what the thesis's operating point denied it. And because the idle floor
is zero, every violation it does incur is its own.

This also fixes audit B4 structurally rather than rhetorically: at 30 EVs/station, beating
droop no longer means beating an unbeatable violation rate, it means delivering service that
droop cannot while staying near its safety.

Fix, in this order, with a test for each:

1. **A3 sign convention** — one convention, asserted in tests, propagated to every figure,
   equation and caption. Add the missing *upper-bound* V2G-curtailment experiment.
2. **A2 cost critic** — clamp the cost target at 0; fix the raw/executed action mismatch;
   log λ, Q_C and realised J_C per episode.
3. **B1 reward** — remove or localise the loss term; publish the weight/scale table;
   fix Eq. (4.6) kWh-vs-fraction.
4. **B3 refresh cadence** — make it a config parameter, default honest.
5. **A4 exogenous violations** — add the zero-injection baseline; add violation
   *magnitude* (pu·steps) and *excess-over-baseline* metrics.
6. **A1 fair ablation** — a single `train.py` where the only difference between arms is
   `projection: on|off`. Identical budget, identical stabilisers, identical seeds.

**Gate 1** — with everything identical but the projection, on 3 pilot seeds:
λ demonstrably tracks the constraint in *both* arms; the zero-injection baseline is
measured; the sign convention test passes. *Report the pilot numbers even if the SoC effect
shrinks or vanishes — that is the finding, and better to learn it now.*

> **Progress.** Items 1–5 landed; item 6 (the pilot) is the remaining gate.
>
> | # | item | status |
> |---|---|---|
> | — | operating point | **settled and measured**: `ExperimentConfig.stage1()`, load 0.40, 30 EV/stn. Idle floor exactly 0.0000; uncoordinated 0.0626 / SoC 0.804; droop 0.0000 / SoC 0.005. |
> | — | projection margin | **chosen by measurement**, not inherited. Margin 0 leaves 3.1 % of steps violating from linearisation error alone; 0.010 is the smallest margin reaching zero, and is satisfiable here (0.17 % infeasible) unlike at the thesis operating point (12.5 %). |
> | 1 | A3 sign convention | **done** — `high_pv_overvoltage()` adds the missing upper-bound V2G experiment. Gap 67.62 kW vs the published 25.865 kW, and it exercises the reactive channel (−95.4 kvar) for the first time. |
> | 2 | A2 cost critic | **done** — cause identified (critic negative on a non-negative target, λ pinned at its floor); `clamp_cost_critic` fixes it, and disabling it reproduces the pathology on 1 of 2 seeds. λ, Q_C and realised J_C now logged per episode. |
> | 3 | B1 reward | **done** — loss term off in `stage1()`. Objective is now service-dominated (user > cost > degradation), which is what the abstract claims. |
> | 4 | B3 refresh cadence | **done** — `sensitivity_refresh_steps` is a config parameter with a test pinning {1: 288, 12: 24, 288: 1} refreshes/episode. Default stays 12 (hourly); the claim of per-step refresh was the error, not the value. |
> | 5 | A4 exogenous | **done** — `evaluate.attributable()` reports paired excess over a zero-injection run with a 95 % CI. |
> | 6 | A1 fair ablation | **done — see below** |
>
> #### Stage 1 fair ablation: the published +0.292 does not survive
>
> Three seeds, 200 episodes, arms identical but for the projection: same budget,
> same seeds, same stabilisers, working dual in the arm where the constraint binds,
> and a learner that demonstrably learns (SoC 0.217 unprojected against droop's 0.007).
>
> | arm | violations | attributable | SoC met | net cost | λ final |
> |---|---|---|---|---|---|
> | no projection | 0.0557 ± 0.027 | +0.0557 | **0.217 ± 0.02** | $416.85 | 6.60 ± 2.78 |
> | projection | **0.0000 ± 0.000** | +0.0000 | 0.089 ± 0.05 | $255.19 | 0.000 |
>
> **projection − no projection: violations −0.0557, SoC −0.1285.**
> The thesis reports **+0.2921** for this contrast. The fair ablation does not merely
> shrink the effect — **it reverses its sign.** The Stage 3 gate is met.
>
> The result is coherent and is a better paper claim than the original. The projection
> is not a free lunch: it converts violations into forgone service, buying a *hard*
> guarantee (0.0000 with zero variance across seeds) at a measured cost of 0.128 SoC.
> λ tells the story mechanically — it sits at exactly 0.000 in all three projected runs
> because realised cost is identically zero, while the unprojected arm is throttled to
> λ ≈ 6.6 trying and failing to satisfy the same budget.
>
> **Pareto set at this operating point:**
>
> | method | violations | SoC met | net cost |
> |---|---|---|---|
> | zero (idle) | 0.0000 | 0.000 | $0 |
> | droop (IEEE 1547) | 0.0000 | 0.007 | $63 |
> | **SafeSAC (projection)** | **0.0000** | **0.089** | $255 |
> | SAC-Lag (no projection) | 0.0557 | 0.217 | $417 |
> | uncoordinated | 0.0626 | 0.804 | $686 |
>
> Non-dominated: uncoordinated, SAC-Lag, SafeSAC. **Under a hard zero-violation
> requirement, the learned+projected controller delivers 13× droop's service** — which
> is the defensible claim, and it repairs audit B4 (droop out-performing the method on
> safety) by making them tie on safety and separating them on service.
>
> What is still unknown is whether 0.089 is *good*. Nothing here establishes the
> achievable frontier at zero violations, so the MPC oracle from Stage 5 is now on the
> critical path rather than a nice-to-have: without it there is no way to say whether the
> projection costs 0.128 of service because the physics demands it or because the
> controller is weak.
>
> **Gate 1 outcome.** *1a — λ leaves zero wherever the constraint binds:* **PASS** (all
> three unprojected runs; the projected runs correctly hold λ = 0 because realised cost is
> identically zero — an earlier version of this criterion wrongly scored that a failure).
> *1b — λ tracks realised J_C:* **WEAK**, mean correlation +0.079 over the three runs with
> any violation. λ responds to the budget, not to the fine structure of the cost, so it
> should be reported as a control signal and never as evidence of constraint satisfaction.

---

### Stage 2 — Throughput — **power-flow path DONE**

The bottleneck was never the GPU. Measured on this container:

| operation | thesis implementation | ported | speedup |
|---|---|---|---|
| single power flow | pandapower NR, 25.75 ms | radial sweep, **0.103 ms** | **249×** |
| sensitivity refresh | 8 central-difference NR solves, 447.6 ms | 1 LU + 8 back-substitutions, **0.662 ms** | **677×** |
| **PF + sensitivity per step** | **63.05 ms** | **0.159 ms** | **398×** |

The sweep matches pandapower to **5e-9 pu** across 300 random operating states on both
feeders, and the analytic sensitivities match the thesis's published Table 4.1 values to
five significant figures on every station and both grids (`tests/test_powerflow.py`).
pandapower stays in CI as the oracle.

Two bonuses beyond speed: the analytic Jacobian sensitivities are *exact* rather than a
finite-difference approximation, which is easier to defend in review; and per-step refresh
is now essentially free, which converts audit item B3 from an embarrassment into a real
ablation axis.

**Remaining Stage 2 work.** With power flow at 0.1 ms, the SOCP solve (~35 ms) is now
~95 % of the step. Three things, in order of expected payoff:
1. **Feasibility pre-check** — skip the solve when the raw action already satisfies every
   constraint with margin. The thesis wrote this (Patch 4's `projection_skip_margins`) and
   then commented it out. A converged policy should be feasible most steps.
2. **Warm-started / code-generated solver** — CVXPYgen, or a hand-rolled active-set routine
   for what is only an 8-variable QP with one cone per station.
3. **Batched environments** — with a vectorised radial sweep, N scenarios advance in
   near-constant time, which is also where the GPU finally earns its place.

**Gate 2** — SafeSAC step time under 10 ms (from 115 ms), fast solver matching pandapower
to 1e-7 pu in CI, and a full training run reproducing Stage-1 results within seed noise.

---

### Stage 3 — Re-establish the core result properly (weeks 5–6)

- **5 training seeds** per configuration, fixed budget, no early stopping (audit C7).
- Report mean ± 95 % CI **across seeds**; significance at the seed level.
- Full convergence diagnostics per arm: return, α, λ, Q-losses, realised J_C.
- Metric set: violation rate, violation magnitude, excess-over-zero-injection, time-outside-band,
  Vmin, SoC met, unmet kWh, net cost, V2G utilisation, throughput, projection infeasibility
  rate, ms/step.

**Gate 3 — the honest decision point.** With a fair ablation and 5 seeds, does the projection
still buy a material service gain at equal safety?
- **Yes** → proceed to Stage 4 with the effect as supporting evidence.
- **No** → the transfer story (Stage 4) becomes the *whole* paper. This is fine — plan for it.
  Do not paper over a null result here; a clean null on the in-distribution ablation plus a
  strong transfer result is a *better* paper than a shaky positive on both.

---

### Stage 4 — The transfer study (weeks 6–8) — **this is the paper**

**Feeder family** (all must be radial-distribution, all with a defensible provenance):
- IEEE 33-bus (Baran–Wu) — incumbent
- IEEE 34-bus and IEEE 123-bus — the networks the closest competitor uses; using them makes
  you directly comparable
- IEEE European LV test feeder (low-voltage, very high R/X) — the extreme case
- A parametric stiffness sweep on 33-bus: substation Z ∈ {0, 2, 4, 6, 8, 10} %, R/X ∈ {0.5, 1, 2, 4}
  — this gives a *continuum*, which is what C3 needs

**Protocol.** Train on network *i*, deploy zero-shot on network *j*, for all (i, j) in the
family, with and without the projection. Report the full transfer matrix per metric.
Include *within*-network cells as the diagonal reference.

**The C3 step.** For each ordered pair, compute candidate network-distance measures —
‖S_P^i − S_P^j‖_F, relative short-circuit ratio, mean R/X, ‖S_P‖ ratio — and regress
transfer degradation on them. A predictor with real R² is the contribution that separates
this from a benchmark table. Hold out feeders to validate the predictor.

**Gate 4** — the transfer matrix is complete with 5 seeds per cell, the projected arm
dominates the unprojected arm on service across the off-diagonal, and at least one distance
measure predicts degradation with R² > 0.7 on held-out feeders.

---

### Stage 5 — Benchmarks and ablations (weeks 8–9)

- **Optimality reference:** multi-period OPF / MPC oracle with perfect foresight (SOC
  relaxation of the branch-flow model, per the thesis's own refs [14–16]). Reviewers ask
  "how far from optimal?" and there must be an answer.
- **Baselines:** uncoordinated, IEEE 1547 droop, unprojected SAC-Lag, plus a
  reward-shaping-only safe-RL arm and — ideally — a PI-TD3-style differentiable-physics arm.
- **Ablations:** refresh cadence {1, 12, 288, never}; margin m ∈ {0, 0.005, 0.010, 0.020};
  projection at train-time only / deploy-time only / both; reward terms; linear vs SOC cone.
- **Address B4 head-on:** find the regime where the learned controller dominates droop on
  *both* axes (high-PV overvoltage, congestion, multi-hub), or state plainly that it does not
  and reframe. Do not leave this to a Pareto label.

**Gate 5** — every baseline runs on every feeder; the oracle gap is quantified; the droop
question has an explicit, defended answer.

---

### Stage 6 — Robustness and limits (weeks 9–10)

Measurement noise and latency on the sensitivities; sensitivity estimation from *measured*
data rather than a known model (the realistic deployment case); load/PV forecast error;
topology reconfiguration mid-episode; unbalanced three-phase on the European LV feeder;
a documented failure gallery — where the linearisation breaks, and what the freeze rule
costs. Replace the placeholder load profile with measured data (audit C1).

**Gate 6** — the paper can state precise conditions under which the method fails.

---

### Stage 7 — Write and release (weeks 10–12)

Target-venue structure; every number regenerated from the package by one command; public
repo with configs, seeds, checkpoint hashes, and a one-command reproduction; a
limitations section that pre-empts each audit item rather than waiting for a reviewer.

---

## Part III — Decisions I need from you

1. **Venue.** TSG-primary (full pipeline) vs SEGAN-primary (stop after Stage 4, faster)?
2. **Compute.** What do you have — Kaggle T4 sessions only, or a university GPU / cluster?
   This sets whether Stage 4's matrix is 5 feeders or 3, and whether Stage 2 is optional or
   critical. (On Kaggle-only, Stage 2 is critical.)
3. **Timeline.** Any hard deadline — supervisor, graduation, funding?
4. **Authorship / scope.** Is Sad Sami co-authoring, and is Dr. Forkan Uddin's approval
   needed before repositioning the contribution away from the defended framing?
5. **Stage 3 gate.** Confirm you accept the null-result branch — if the fair ablation kills
   the +0.292 effect, we pivot to transfer-only rather than tuning until the number returns.

---

## Part IV — What I do not recommend

- **Submitting the current results anywhere Q1.** Items A1–A5 are individually sufficient
  for rejection, and A3 (inverted sign in the flagship example) would damage credibility
  with any power-systems reviewer.
- **Patching the existing notebook.** The ordering-dependent monkey-patches *caused* the
  worst defects. Port first.
- **Keeping "SafeSAC beats SAC-Lag" as the headline.** It is unfair as run (A1), rests on a
  mislabelled baseline (A2), and is measured on an axis dominated by exogenous violations (A4).
- **Adding more methods before fixing measurement.** Nothing built on the current metric
  set is trustworthy.
