# Research plan — V2G voltage support on IEEE-34

**Two tiers. Read §6 first if you are working on the conference paper.**

| tier | scope | labels | working title |
|---|---|---|---|
| **Conference** (§6–8) | Execute the future work the target paper names; report the behaviour descriptively | **A1–A3** | *Degradation-Aware Multi-Hub V2G Voltage Regulation under Realistic Fleet Constraints* |
| **Journal** (§1–5) | The full research thesis: feasibility characterization, oracle bounds, second feeder | **C1–C5, J1–J8** | *Feasibility Before Learning: A Power–Energy Adequacy Framework for V2G Voltage Support* |

The conference paper deliberately does **not** argue the §1 thesis. It adds the named gaps to
the system, measures what happens, and reports it — the same descriptive mode the target paper
uses. The §1–5 framework is the journal contribution and stays out of the conference version.

Target venues: PES GM 2027 (submission 10 Nov 2026) for the conference paper; Trans. Smart
Grid / Sustainable Energy or Applied Energy for the journal. Recommended conference track:
**Electric Vehicle–Grid Integration and Smart Charging**, *not* the AI track — neither tier
offers a new learning algorithm, and AI-track reviewers score for algorithmic novelty.

---

# Journal program — the research thesis (§1–5)

## 1. The reframe

V2G voltage support is governed by **two independent feasibility constraints**, and the
literature conflates them:

- **Power adequacy (per hour).** Given hub locations and inverter ratings, can *any*
  injection lift the worst bus to `v_min` this hour? If not, stored energy is irrelevant —
  it is a siting/rating problem.
- **Energy adequacy (per day).** Summed over the violation window, does the fleet hold
  enough usable energy to supply what each hour requires?

Crossing them gives four regimes with different answers to "is a smarter controller worth
building?":

| | **Energy ample** | **Energy short** |
|---|---|---|
| **Power feasible** | Droop suffices; a learned policy ties it | **Foresight pays** — rationing across hours is the whole game |
| **Power infeasible** | Siting / rating problem; control is irrelevant | Nothing works |

**This framework explains the reproduction target's own central result.** In
[arXiv:2603.07237](https://arxiv.org/abs/2603.07237) the single hub holds the worst bus at
~0.72 p.u. against a 0.95 limit — bottom-right, power-infeasible *and* energy-short. The
multi-hub case (5 × 500 kW) moves toward feasibility and gains exactly one violation-hour.
RL ties droop throughout that study because every configuration tested sits in a quadrant
where control cannot matter. This is the missing explanation for their result, not a
refutation of it — their abstract claims parity with droop, never superiority.

Our own measurements are consistent: a fully trained, SOC-aware, droop-floored agent moves
the worst bus from 0.722 to 0.741 p.u. (see `RESULTS.md`). That ~2 p.u.-point ceiling is the
signature of power-infeasibility.

## 2. Gaps addressed, ranked

**G1 — The field optimizes control without testing whether control can work.** No paper in
this space computes the injection required to clear violations *before* comparing
controllers. Every null or near-null result is therefore uninterpretable: weak controller,
or impossible task?

**G2 — Reward specifications are never audited, so "battery-aware" claims are confounded.**
The reward form used here, `10·1[all in band] − 100·Σ deviation` against an SOC cost of
`0.5·discharge`, has a dead indicator term whenever the band is never reached, leaving a
penalty:SOC-cost ratio near 100:1. Maximal discharge is the exact optimum of that objective,
so observed "SOC preservation" is not a learned trade-off.

**G3 — Degradation is asserted, not priced.** "Battery-aware" is ubiquitous in abstracts; an
explicit violation-hours vs. throughput Pareto front is nearly absent, which makes the usual
claim unfalsifiable.

**G4 — Nobody maps the crossover.** The published record is uniformly "our RL beats droop."
The regime boundary is unclaimed.

**G5 — Frozen legacy controls remove the real incumbent.** `Set ControlMode=OFF` deletes
IEEE-34's LTC and regulators — the actually deployed voltage solution. Beating
droop-with-regulators-off is not a deployment argument, and RL/regulator interaction (tap
hunting) is underexplored.

Already-occupied ground, deliberately **not** claimed as novelty: residual RL over a droop
prior for distribution voltage control (arXiv 2408.06790, 2506.19353). It is used here as an
instrument — the `a = 0` floor removes "you tuned the RL badly" as an explanation for a null
— not as a contribution.

## 3. Claims

### C1 — Necessary condition (provable)

Let `P_req(h)` be the smallest total hub active-power injection holding all buses ≥ `v_min`
on the full AC power flow at hour `h`, **computed with reactive support already optimally
deployed** so the bound is conservative. With

```
E_req = Σ_h P_req(h)·Δt        over violating hours
E_avl = Σ_hubs Σ_EVs avail_i · C_i · (SOC_i − SOC_min) · η_inv · SOH
α     = E_avl / E_req
```

> **If α < 1, no causal policy — RL, MPC, or clairvoyant — eliminates the violations.**

Energy conservation: per-hour requirements cannot be relaxed by time-shifting, and storage
constraints only tighten them. This claim cannot be obsoleted by a better algorithm.

Separately record **power-infeasible hours** — those where even full inverter rating cannot
reach `v_min`. These are a rating/siting failure, distinct from an energy shortfall.

### C2 — The undertraining artifact

> In the power-infeasible regime, the apparent "same support, less wear" benefit of
> SOC-aware V2G control is an undertraining artifact that vanishes on convergence.

Evidence already in hand: at 3k training steps the agent showed 12.8% energy *savings* at
equal support; at 20k steps the identical setup used 20.2% *more* (`RESULTS.md`). The
benefit inverted as training approached the reward's true optimum — exactly as the G2 reward
audit predicts. Specific, reproducible, and falsifiable.

### C3 — The crossover law

> The advantage of a learned policy over memoryless droop is ≈0 in the power-infeasible and
> energy-ample quadrants, and grows only in the power-feasible / energy-short quadrant.

Cross the boundaries three independent ways — hub count (1→5), fleet size, availability — so
the effect attributes to the regime rather than to one knob. Test the **mechanism**, not only
the scalar: in the paying quadrant the agent should visibly withhold discharge during in-band
hours and hold reserve for deep sags. A shape change in the discharge profile is much harder
to explain away than a violation-hour delta.

### C4 — A planning screen

α and power-feasibility are computable from feeder and fleet specifications *before any
controller exists*. Produce an adequacy map over candidate hub buses (marginal adequacy per
hub sited at bus X). Design rule: below the boundary, spend on siting and capacity; above it,
spend on control.

### C5 — Robustness

Multi-seed (≥10, with confidence intervals), two feeders (IEEE-34 + IEEE-123), regulators
both frozen and active (reporting tap operations), and ≥2 RL algorithms so the null is not
SAC-specific.

## 4. Validation matrix

| Claim | Experiment | Falsifier | Credibility control |
|---|---|---|---|
| C1 | AC power-flow bisection per hour → `P_req`, `E_req`; compare to `E_avl` | Any policy clearing violations at α < 1 | `E_req` computed with Q optimally deployed (conservative direction) |
| C2 | Training-length sweep 3k → 50k steps, ≥10 seeds, energy at matched support | Benefit persists at convergence | Analytical reward-ratio audit presented alongside |
| C3 | Cross the boundary via hub count, fleet size, availability | Advantage appears in power-infeasible cases, or fails to appear in power-feasible/energy-short | **Clairvoyant oracle baseline** (below) |
| C4 | Adequacy map over candidate buses, both feeders | Map fails to predict measured controller gains | Out-of-sample validation on IEEE-123 |
| C5 | Full factorial: 2 feeders × 2 regulator modes × 2 algorithms | Null flips under any variation | Pre-registered metric set; all cells reported |

### The clairvoyant oracle is mandatory

Solve the day offline with perfect foresight — deterministic multi-period optimization over
hub dispatch subject to fleet energy limits — to bound what *any* controller could achieve.
Without it, the reviewer response is "your RL simply was not good enough." With it, "the task
is infeasible" is separated from "the learner underperforms," which is what converts a
negative result into a measurement against a bound. **Do not submit without it.**

## 5. Known weaknesses and mitigations

| Risk | Mitigation |
|---|---|
| Read as "just a negative result" | Lead with C1/C4 (criterion + planning rule); place the null third |
| `E_req` definition contestable | Report both a LinDistFlow bound and the AC bisection so they bracket |
| α over-sold | It is a screening criterion — necessary, not sufficient. Never call it a theorem |
| No new algorithm → track mismatch | Submit to the EV-Grid Integration track, not the AI track |
| Reads as an attack on the target paper | Frame as explaining and generalizing their finding; cite generously; note their own observation that fleet availability, not inverter rating, is the single-hub bottleneck |
| Seed variance (already observed: +20.2% vs −2.0% across two runs) | ≥10 seeds with CIs on every headline number — blocking for any submission |

# Conference paper — what to build now (§6–8)

## 6. Scope and contributions

The conference paper is deliberately narrow: **take the scope limitations the target paper
states about itself, plus the first item of its named future work, add them to the system, and
report the measured behaviour.** It does not argue a thesis and it does not need to beat droop.

**The target paper does not win either, and says so.** Abstract: RL is *"comparable to the
baseline"* and *"within 10% of the baseline"* under aggressive overloading. §IV-B: *"The RL
controller does not match droop performance in this stress case."* Conclusion: *"a local droop
baseline can still outperform it under aggressive stress."* Their Table II reports RL at 15
violation-hours against droop's 2. The accepted currency here is a working system measured
honestly with the regime characterized — not a leaderboard win.

### Their stated scope limitations → our experiments

| # | What they state about their own scope | Where | Our experiment |
|---|---|---|---|
| **L1** | *"assuming sufficient EV capacity at each hub, allowing the analysis to isolate the benefits of multi-hub coordination from availability constraints"* | §III-A | **E2** — multi-hub with the 45–85% availability + SOC/SOH model on |
| **L2** | Phase 1 trains *"in an idealized environment with fixed hub power limits and no explicit fleet constraints"*; Phase 2 deploys with them | §II-D | **E2/E4** — fleet in the training loop, SOC + availability in the state |
| **L3** | *"each episode comprises 100 discrete control steps with randomly sampled load multipliers λ ∈ [0.1, 4.0]"* — i.i.d., no temporal structure | §III | **E4** — day-structured vs paper-style (`iid_lambda`) training |
| **L4** | Droop outperforms RL under aggressive stress | §IV-B, Concl. | **E4** — multi-hub aggressive, both training regimes |

### Their stated future work → our experiments

| # | Future work, verbatim | Conference | Journal |
|---|---|---|---|
| **F1** | *"battery-degradation-aware optimization"* | **E3** — Ah-throughput reward term, weight swept to a violation/wear frontier | Full Pareto, priced |
| **F2** | *"extensions to larger feeders"* | ✗ deferred | IEEE-123, 8500-node |
| **F3** | *"multi-agent coordination"* | ✗ deferred | MARL vs hierarchical |
| **F4** | *"integration of vehicle travel and logistics constraints"* | ✗ deferred | Stochastic availability |

F2–F4 are deliberately held back: they are the journal's new material.

### Added on our own judgement, with justification

| # | Addition | Why it is needed |
|---|---|---|
| **X1** | Per-phase ANSI C84.1 evaluation alongside the feeder mean | Their metric is the feeder **mean**; ANSI limits are per-phase, and IEEE-34 is unbalanced |
| **X2** | Integrated violation magnitude `IntViol` (p.u.·h) | Hour counts saturate at "all 18 violated" and stop discriminating |
| **X3** | Common random numbers + ≥5 seeds with CIs | Single-seed RL results are the most common technical objection in this literature |
| **X4** | Per-hour optimal-dispatch reference (AC power-flow bisection) | The measuring stick: says how far **both** controllers sit from what any controller could do that hour. Droop alone is not a reference |
| **X5** | Open-loop vs closed-loop droop variant | Our droop reaches 10 violation-hours where theirs reaches 2; most likely they evaluate droop open-loop. Report both rather than leave the gap unexplained |
| **X6** | **P/Q allocation at matched apparent power** | Their Eq. (4) drains the battery on apparent power, so a kVAr costs exactly as much stored energy as a kW — and they never explore the consequence. Sweeping the injection angle at fixed S answers where a limited energy budget buys the most voltage |

**Headline framing.** Not "RL vs droop." The paper reports what multi-hub V2G voltage support
actually delivers once fleet availability binds — 9.3% of requested energy — and characterizes
the resulting controller behaviour, including the fact that the unconstrained-case ranking does
not survive the constraint.

Three design rules that make the numbers readable regardless of outcome:

1. **Common random numbers** — every controller sees the identical availability realisation,
   initial SOC and load peak; differences are paired.
2. **Integrated violation magnitude** (`IntViol`, p.u.·h) alongside hour counts, because
   counts saturate at "all 18 hours violated" and stop discriminating.
3. **Per-step floor language only.** `a = 0` reproduces droop at each step; it does **not**
   give a day-level performance guarantee, since discharging early leaves less later.
   Measured evidence: aggressive single-hub gave RL 18 worst-bus violation-hours vs droop 17.

**Journal extension:** J1–J8 from §5 — oracle bound, IEEE-123, LTC interaction, the adequacy
criterion with a formal proposition, coordination architectures, stochastic availability, the
planning bridge. All new relative to A1–A3.

## 7. Verified during environment setup

Established by running the calibration and wiring tests, not assumed:

- **`ControlMode=OFF` is the paper's setting.** No-V2G baseline worst-case feeder-mean voltage
  came out 0.903 (mild) / 0.800 (aggressive) against their reported 0.907 / 0.807 — within
  0.004–0.007 p.u. With regulators active (STATIC) mild gives 0.983, off by 0.076. The
  residual violation-hour gap (10 vs 13, 16 vs 17) is the reconstructed load shape.
- **The mean metric hides violations, quantified.** Multi-hub unconstrained droop at mild
  load reports **ViolMean = 0** — matching the paper's headline — while the same rollout has
  **ViolBus = 4** and **ViolPh = 7**.
- **The fleet constraint is the binding limit, quantified.** Multi-hub mild: unconstrained
  droop wants 14 013 kWh and clears violations (IntViol 0.14); constrained droop delivers
  1 351 kWh (9.6%) and IntViol rises to 41.79. Single-hub mild is starker: 5 475 kWh wanted,
  262 kWh delivered (4.8%). This is the paper's *"availability rather than inverter rating"*
  observation as a number.
- **`IntViol` discriminates where counts tie.** Single-hub mild baseline and constrained droop
  both show ViolMean 10, but IntViol 45.69 vs 45.32.

## 8. Build order

Work runs in two batches. Batch 2 depends on Batch 1 — the reference changes how the trained
results should be read, and the P/Q result determines whether the RL-side allocation study is
worth running at all — so they do not run concurrently.

### Batch 1 — deterministic, no training (`V2G_reference_studies.ipynb`, minutes)

| | Study | Adds |
|---|---|---|
| **E5** | Per-hour achievable ceiling: sweep injection 0 → full rating, record worst-phase voltage | X4 |
| **E6** | Open-loop vs closed-loop droop against their Table II | X5 |
| **E7/E7b** | P/Q allocation at matched apparent power; voltage-optimal split by angle sweep | X6 |

Non-converged power flows are masked. At deep-sag hours the high-injection end of the sweep
sits past the nose of the PV curve; OpenDSS leaves stale voltages in its arrays there, and
reading them produces a spurious ceiling *and* a spurious collapse. Every scan reports the
converged fraction.

### Batch 2 — training runs (depends on Batch 1)

Expanded mild weight sweep `(0,1,3,10,30,100,300)`; ablations (SOC-in-state on/off,
degradation term on/off); the RL-side P/Q study; then the full run at `QUICK = False`
(~26 trainings × 20k steps, roughly 2 hours on CPU) with ≥5 seeds.

## 8a. Pipeline status — production run of 2026-08-18/19

`V2G_RUN_ALL.ipynb`, 5.80 h wall clock, 48 trainings at 20k steps, 3 seeds × 5 paired
scenarios (CRN). **12 of 13 experiments completed.** Every deterministic result reproduced
the earlier reference run exactly.

| | Experiment | Status | Headline number |
|---|---|---|---|
| **E0** | ControlMode calibration | done | `OFF` → 0.903 / 0.800 vs paper 0.907 / 0.807; `STATIC` off by 0.076 |
| **E5/E7** | Achievable ceiling, P/Q at matched S | done | P buys **1.25–1.49×** the uplift of Q per unit battery drain |
| **E8** | Optimized per-hub dispatch | done | multi-mild **18/18** hours clearable, IntViol **0.00**; multi-aggr 4/18, **17.99** |
| **E9** | Droop fixed-point convergence | done | `damp=0.3` converges in all 4 configs; `damp=0.6` limit-cycles in all 4 |
| **E6** | Open- vs closed-loop droop | done | constrained: 42.77 vs 44.08 mild — implementation only matters unconstrained |
| **E2** | Multi-hub, fleet-constrained | done | droop 42.77 vs RL 45.45; paired **+2.03 ± 0.16**, RL wins **0/5** |
| **E12** | Safety projection | done (re-run) | projection is a measured **no-op**: `IntHi 0.00`, `VphMax 1.050` unprojected |
| **E3** | Degradation frontier | done | mild: **−60% throughput for +1.1% violation**; aggressive flat |
| **E4** | Aggressive stress | done | day-structured 169.39 vs paper-style 171.05; droop 165.83 |
| **E1** | Reproduction of Tables I/II | done | direct action overvolts (**VphMax 1.151** mild) where residual does not |
| **E11** | Policy P/Q angle | done | mean \|agent − optimal\| **23.6°** mild / **20.1°** aggr; day mean 29.2° / 41.5° vs rating ratio 38.7° |
| **E13** | Learning curve to 100k | done | aggressive **plateaus**; mild **still improving** at 100k |
| **E10** | Ablations | done | fleet-in-state does **not** beat voltage-only on IntViol; it uses 2.4× more battery |

**E12 crash and retarget.** `paired_delta` differenced 15 RL rows (3 seeds × 5 scenarios)
against 5 droop rows — droop is deterministic and is rolled out once — raising a broadcast
error. It can only raise when `len(seeds) > 1`, so the single-seed smoke test could not see
it. `paired_delta` now tiles the shorter list to restore scenario pairing and rejects ragged
input; the re-run notebook asserts on the exact failing shape before training.

The experiment itself was also retargeted. It was written to project overvoltage out of the
residual agent, but E2 shows that agent never breaks the bound under the fleet constraint
(`VphMax 1.050`, `ViolHi 0.0`, both load levels), so projecting there is a no-op. The
overvoltage lives in the paper's **direct** action — E1 gives `VphMax 1.151` mild and
`1.077` aggressive on the same feeder under the same constraint. E12 now compares direct
raw against both projections, with E2's residual row as the reference (not retrained: same
env, scenarios, seeds and steps, and `train_on` seeds only from `seed`).
`V2G_E12_rerun.ipynb`, 6 trainings, ~50 min.

### E12 result — the projection is a no-op, and overvoltage tracks the training regime

Re-run completed in 52.6 min, 6 trainings, 3 seeds × 5 paired scenarios.

| case | IntViol | ±95% | IntHi | VphMax | Thru |
|---|---|---|---|---|---|
| mild / Droop | 42.77 | 0.32 | 0.00 | 1.050 | 1342 |
| mild / direct raw | 45.56 | 0.42 | **0.00** | **1.050** | 4160 |
| mild / direct + proj (scale) | 45.56 | 0.42 | 0.00 | 1.050 | 4159 |
| mild / direct + proj (shed Q) | 45.55 | 0.43 | 0.00 | 1.050 | 4161 |
| aggr / Droop | 165.83 | 0.60 | 0.00 | 1.050 | 1582 |
| aggr / direct raw | 169.82 | 0.35 | **0.00** | **1.050** | 2262 |
| aggr / direct + proj (scale) | 169.78 | 0.34 | 0.00 | 1.050 | 2261 |
| aggr / direct + proj (shed Q) | 169.19 | 0.46 | 0.00 | 1.050 | 2223 |

**The retarget premise was wrong, and this is the correction.** §8a above attributed E1's
overvoltage to the *direct action*. E12 falsifies that: the same direct action, trained
day-structured with the fleet in the loop, holds 1.050. E1's direct rows were trained
**paper-style** — i.i.d. `λ ∈ [0.1, 4.0]`, no fleet in the loop — and the action mode was
read off a confound.

What the whole study actually shows, across 54 trainings:

| training regime | VphMax | evidence |
|---|---|---|
| day-structured, fleet in loop | **1.050**, `ViolHi 0` | E2 (residual), E12 (direct), E3 (all 10 weights), E4, E10 fleet-in-state — both load levels, 3 seeds |
| day-structured, fleet out of **state** | 1.056 / 1.061 at aggressive | E10 voltage-only (mild stays 1.050) |
| paper-style (i.i.d. λ, no fleet in loop) | 1.072 – **1.229** | E1 (4 rows), E4 paper-style |

So the upper-bound violation is a property of the **training distribution**, not the action
parameterization — and day-structured, fleet-in-loop training removes it without any
projection layer, nothing to tune, no inference cost.

**Why the projection cannot help here.** `feas()` tests the *commanded* setpoints, before
`EVFleet.apply` clips them to available SOC and connected vehicles. It therefore fires on
commands the fleet was never going to deliver, which is exactly what the tiny deltas show
(aggressive: 2262 → 2223 kWh, 169.82 → 169.19). The fleet **energy** constraint binds harder
than the voltage constraint, leaving nothing for a voltage projection to do. `shed_q` is
consistently the better of the two projections (aggressive paired gap to droop +3.36 vs
+3.95 for `scale`), in the direction E7 predicts, but the effect is small.

### E13 result — the 20k budget is converged at aggressive load, NOT at mild

4 trainings to 100k steps, checkpoints every 20k, 2 seeds × 5 paired scenarios, 192.7 min.
Guard passed: checkpointed training with interleaved evaluation reproduces `train_on` to 1e-9.

| steps | mild IntViol | vs droop | RL wins | aggr IntViol | vs droop | RL wins |
|---|---|---|---|---|---|---|
| 20 000 | 45.05 ± 0.23 | +2.27 | 0/10 | 169.20 ± 0.77 | +3.36 | 0/10 |
| 40 000 | 44.74 ± 0.23 | +1.97 | 0/10 | 168.21 ± 0.50 | +2.38 | 0/10 |
| 60 000 | 44.09 ± 0.27 | +1.32 | 0/10 | 168.27 ± 0.38 | +2.44 | 0/10 |
| 80 000 | 44.33 ± 0.39 | +1.55 | 0/10 | 168.25 ± 0.31 | +2.42 | 0/10 |
| 100 000 | **43.56 ± 0.27** | **+0.79** | **2/10** | 168.41 ± 0.36 | +2.57 | 0/10 |

**Aggressive: PLATEAU.** 169.20 → 168.41, change −0.79 against a combined 95% CI of 1.13.
Flat from 40k onward, gap to droop unchanged at ~+2.4, droop wins every paired scenario at
every checkpoint. The undertraining objection is answered here: droop's advantage under
aggressive stress survives 5× the training budget.

**Mild: STILL IMPROVING.** 45.05 → 43.56, change −1.48 against a CI of 0.49 — significant and
not converged at 100k. The gap to droop narrows monotonically (+2.27 → +0.79) and RL takes
**2/10** paired scenarios at 100k, the first wins anywhere in the study.

**Consequences for the manuscript.**

* **E2's mild claim must be requoted.** "Droop wins every paired scenario at mild load" is
  true at 20k and false at 100k. Report the curve, quote mild at 100k (43.56, +0.79, 2/10),
  and state plainly that the mild comparison is unresolved at the budgets tested.
* **E2's aggressive claim is strengthened**, not weakened — the plateau rules out the
  undertraining explanation.
* **C4 (E11, the P/Q angle diagnosis) is now measured on a demonstrably undertrained agent at
  mild** and needs re-running at 100k before it can carry weight. ~1.5 h, 2 trainings.
* **C6 (E12) is reinforced at no extra cost.** Every one of the ten E13 rows reports
  `VphMax 1.050` — the no-overvoltage finding now holds at 5× the training budget.
* **E3 and E10 stay as reported.** E3's finding is the *shape* of the frontier, which a
  uniform shift does not change; E10 compares two arms at an identical budget, so the
  comparison is fair even if both are undertrained. State the budget as a limitation.

**The learning curve strengthens C1 rather than threatening it.** Even the best-trained agent
in the study moves the mild result by 1.48 p.u.·h, and the whole span between droop and RL at
100k is 0.79. Against that, the fleet energy constraint costs 38.62 p.u.·h at mild
(droop unconstrained 4.15 vs constrained 42.77) and 115.69 at aggressive. **The energy
constraint outweighs the controller choice by roughly 45–50× at both load levels**, and that
ratio is now established at a training budget five times the headline one.

**Two production results that reversed the QUICK reading**, and supersede it:

* **E3 mild is a much better result than QUICK showed.** Across a 300× sweep of the
  degradation weight, IntViol stays inside `[44.83, 46.01]` — a 2.6% band — while throughput
  falls from 6188 to 2449 kWh. Cutting battery wear ~60% costs +1.1% violation. The
  intermediate points are non-monotone (one seed per weight), so report the endpoints and
  the band, not the zigzag.
* **E10 flipped sign.** QUICK had fleet-in-state ahead at mild (44.90 vs 47.83). At
  production, voltage-only is marginally ahead (44.91 ± 0.29 vs 45.41 ± 0.36, CIs overlap) —
  a null on IntViol. The real finding is the throughput column: fleet-in-state spends
  6068 kWh against voltage-only's 2497 for no violation benefit, and at aggressive load
  voltage-only breaks the upper bound (1.056 / 1.061) where fleet-in-state holds 1.050. So
  the fleet state buys bound compliance and costs battery, rather than reducing violation.

## 9. Publication status of the reproduction target

As of 2026-08-17, no published version of arXiv:2603.07237 was found — no DOI, no journal
reference, no conference venue surfaced by search. It appears to be an arXiv-only preprint,
likely under review. **Caveat:** arXiv, IEEE Xplore and Semantic Scholar were all
unreachable from the environment used for that check, so this is "no evidence of
publication," not a verified negative. Confirm manually on IEEE Xplore and Google Scholar
before building on it.
