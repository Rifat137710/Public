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

---

### Stage 1 — Correctness (weeks 2–3)

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

---

### Stage 2 — Throughput (weeks 3–4)

Current: 42–118 ms/step, ~48 min per SafeSAC run. Stage 4 needs ~5 feeders × 5 seeds ×
2 methods × 2 training grids ≈ 100 runs. At today's speed that is ~80 GPU-hours of pure
power flow. Two changes:

1. **Analytic sensitivities from the power-flow Jacobian.** Today: 8 extra NR solves per
   refresh via central differences. Replace with one LU back-substitution against the
   converged Jacobian — exact, ~50× cheaper, and *more defensible in the paper* than finite
   differences. This also makes per-step refresh affordable, which turns B3's ablation into
   a real result.
2. **Fast radial power flow.** Backward–forward sweep specialised to the radial topology,
   vectorised; 20–100× faster than `pandapower` NR with `numba=False`. Validate against
   pandapower to 1e-8 pu on every bus across 10⁴ random operating points, and keep
   pandapower as the checked reference in CI.

Optionally vectorise across parallel environments.

**Gate 2** — ≥20× end-to-end step-throughput improvement, with the fast solver matching
pandapower to 1e-8 pu and a full training run reproducing Stage-1 results within seed noise.

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
