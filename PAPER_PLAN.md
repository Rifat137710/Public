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

The conference paper is deliberately narrow: **execute the future work the paper names, and
report the behaviour**, in the descriptive mode the original uses. It does not argue a thesis.

| # | Conference contribution | Source in the target paper |
|---|---|---|
| **A1** | Multi-hub coordination **with realistic fleet constraints** (45–85% availability, SOC/SOH dynamics) | §III-A: *"assuming sufficient EV capacity at each hub"* — never tested |
| **A2** | **Degradation-aware objective** — Ah-throughput term in the reward, weight swept to a violation/wear frontier | Conclusion: *"battery-degradation-aware optimization"* |
| **A3** | **Multi-hub aggressive stress**, day-structured vs paper-style training | Table II: droop **2** viol-hours vs RL **15**; conclusion concedes it |

Added because the literature expects them, not as novelty claims: per-phase ANSI C84.1
evaluation alongside the feeder mean; weighted-Ah cost in the reward with rainflow depth as
an evaluation-only metric; a per-hour optimal-dispatch reference so droop is not the sole
baseline; ≥10 seeds with CIs.

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

## 8. Immediate next step

Run `V2G_gaps_study.ipynb` with `QUICK = True` to confirm wiring on the target machine, then
`QUICK = False` for the real numbers (~26 trainings × 20k steps, roughly 2 hours on CPU).

## 9. Publication status of the reproduction target

As of 2026-08-17, no published version of arXiv:2603.07237 was found — no DOI, no journal
reference, no conference venue surfaced by search. It appears to be an arXiv-only preprint,
likely under review. **Caveat:** arXiv, IEEE Xplore and Semantic Scholar were all
unreachable from the environment used for that check, so this is "no evidence of
publication," not a verified negative. Confirm manually on IEEE Xplore and Google Scholar
before building on it.
