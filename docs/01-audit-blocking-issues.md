# Pre-submission audit — what a Q1 reviewer will find

Ranked by how likely each is to end the review. Every item cites the code or artifact
that establishes it. **A-items must be fixed before any Q1 submission.**
**B-items must be fixed before the paper is competitive.** C-items are polish.

---

## A1 — "SafeSAC = SAC-Lag + projection" is not what was run

The thesis states (§5.6, Table 5.1, §5.7): *"SafeSAC adds only the projection on top of
SAC-Lag. Holding everything else fixed in this way is what allows the experiments to
attribute any safety/service difference between the last two rows specifically to the
projection."*

Four things differ between the two arms:

| | SAC-Lag | SafeSAC |
|---|---|---|
| critic learning rate | 3e-4 | **1e-4** (`SAFESAC_V3_HPARAMS = {"lr_critic": 1e-4}`) |
| entropy temperature cap | **none** | **α ≤ 1.0** |
| training budget | 150 max (ran 97 / 114) | 100 max (ran 85 / 86) |
| final λ | **0.000** | 17.3 / 17.8 |

The α cap was introduced by Patch 6, which ran *after* Patch 5b trained the SAC-Lag
checkpoints in that kernel session — the cell-29 comment claiming the cap was "deliberately
kept active for SAC-Lag training too" is contradicted by its own output
(`saclag_strong_v2 ... alpha=19.402`, far above the 1.0 ceiling).

**Consequence.** The headline +0.292 SoC-met effect cannot be attributed to the projection.
**Fix.** Retrain both arms under one identical configuration, one script, same budget,
same stabilisers, ≥5 seeds. This is non-negotiable.

---

## A2 — The "SAC-Lag" baseline has an inert constraint mechanism

Read directly from the checkpoint archives:

```
saclag_weak_v2_model.pt   lambda = 0.0
saclag_strong_v2_model.pt lambda = 0.0
safesac_weak_v3_model.pt  lambda = 17.324713228736073
safesac_strong_v3_model.pt lambda = 17.847470766631886
```

λ ≡ 0 for the whole of both SAC-Lag runs. The augmented-Lagrangian term
`λ·(Q_C − d)` contributed nothing; the quadratic penalty only activates on
`clamp(cost_excess, min=0)`, and the Block-5 smoke test already shows the cost critic
predicting **negative** cost-to-go (`mean_qc: -0.177`) — impossible for a non-negative
per-step cost. Patch 3b's `y_c = clamp(y_c_raw, min=0)` fix is **commented out** in the
final notebook.

So the paper's "state-of-the-art learned baseline, precisely the AL-SAC formulation of
Chen et al." is, as executed, **plain SAC**. Every comparison to the AL-SAC literature is
mislabelled.

Why does SafeSAC's λ rise instead? Its replay stores `action_exec` = the *projected*
action, and the cost critic is trained on that — but the actor update queries
`Q_C(s, a_raw)` at the *unprojected* sample. The cost critic is evaluated off its own
training distribution. λ = 17.3 is an artefact of that mismatch, not evidence the
constraint is being tracked.

**Fix.** (i) clamp the cost target at 0; (ii) decide and document one consistent
convention — either train and query the cost critic on raw actions (the projection is then
an environment property) or on executed actions (and update the actor through the
projection); (iii) log λ, Q_C, and realised J_C per episode and *show* the constraint being
tracked. Then re-verify that SAC-Lag actually behaves like AL-SAC.

---

## A3 — The sign convention in the paper is inverted, and the flagship example is mislabelled

Code (authoritative): `p_kw > 0` = injection = **V2G**; `p_kw < 0` = **charging**.

Thesis §4.6: *"Positive active power denotes charging (G2V); negative denotes discharging
(V2G)."* — inverted. Eq. (4.4) charges the purchase price to `[p]₊`, which in the code is
the *export* branch — inverted. Figure 4.8, reproduced straight from the notebook, is
captioned *"Realised station active power (>0 = V2G injection)"* — i.e. the thesis
contradicts itself on the same convention within one chapter.

The damage lands on the paper's showcase result. Table 5.3 / §5.8 / the abstract describe
*"an identical aggressive V2G request of −80 kW"* curtailed to −54 kW on the weak feeder.
In the code, `stress_raw_p = np.full(n_st, -S_RATED)` is a **full-rate charging request**.
The projection curtails charging from 80 kW to 54 kW to hold V ≥ 0.95 — correct physics,
wrong story. The stated story is not even physically coherent: curtailing a *V2G injection*
would push the weak feeder's voltage *down*, not protect it.

**Consequence.** The single most-cited number in the abstract ("curtails a −80 kW V2G
request to −54 kW") demonstrates charging curtailment, not V2G voltage support. A power
systems reviewer sees this immediately.

**Fix.** Correct the convention everywhere, and add the experiment the paper actually
claims: an over-injection request on a *lightly loaded / high-PV* feeder that the projection
curtails against the **upper** 1.05 pu bound. That is the true V2G-support demonstration
and it is currently missing.

**Now confirmed by measurement** (A4 table, `+80 kW` column): full-rate V2G injection at
every station produces **zero** violations at every load scale tested, 0.35 through 0.50.
On this testbed V2G literally cannot cause a lower-bound violation — so the projection is
never exercised on a V2G request anywhere in the paper. Without a high-PV / light-load
overvoltage case, the V2G-safety claim has no supporting experiment at all.

---

## A4 — The reported violations are mostly exogenous — now measured

This was an estimate in the first pass. It is now **measured** (`tests/test_powerflow.py`),
by sweeping a full 288-step weekday over the thesis's own load shape with the stations held
at fixed power:

| weak feeder, weekday | 0 kW (idle) | −40 kW | −80 kW (full charge) | +80 kW (full V2G) |
|---|---|---|---|---|
| load scale 0.35 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| **load scale 0.40** | **0.0000** | **0.0000** | **0.0868** | 0.0000 |
| load scale 0.45 | 0.0104 | 0.0938 | 0.1424 | 0.0000 |
| **load scale 0.50 (thesis)** | **0.1007** | 0.1424 | 0.2500 | 0.0000 |

At the thesis operating point, **10.07 % of steps violate with the chargers switched off**
(11.46 % at weekends).

**Measured properly**: running a `ZeroAgent` (chargers idle) over the *exact 25 evaluation
seeds* used for Table 6.1 gives an idle floor of **0.0947 ± paired**, Vmin 0.9438:

| method | reported rate | **relief vs the 0.0947 idle floor** |
|---|---|---|
| Uncoordinated | 0.1156 | **+0.0208** (± 0.0018 SE, paired) |
| SafeSAC (weak) | 0.0912 | −0.0035 |
| SAC-Lag (weak) | 0.0904 | −0.0043 |
| **Droop (1547)** | **0.0521** | **−0.0426** (± 0.0019 SE, paired) |

Two consequences, both severe:

1. The entire between-method spread rides on a background the controller did not cause.
   The published "SafeSAC matches SAC-Lag on safety, 0.0912 vs 0.0904" compares two numbers
   that are ~96 % identical idle background. Both learned agents move the violation rate by
   about **0.4 percentage points** relative to doing nothing.
2. Measured as relief below the idle floor, **droop delivers roughly ten times more voltage
   relief than either learned controller** (−0.0426 vs −0.0035/−0.0043). The current framing
   hides this behind a Pareto label. See B4.

**The fix is clean, and the right operating point is 0.40.** It is the only scale in the
family where the idle feeder is fully compliant (0/288 steps) *and* full-rate charging
genuinely violates (8.68 % of steps). Every violation at 0.40 is therefore attributable to
the controller's own decisions — which is exactly what the safety metric needs to mean.
0.45 is already contaminated (0.0104) and 0.50 is swamped.

Note this is the operating point Table 5.3's projection numbers were computed at (audit B2),
so moving there also removes that inconsistency.

**Also do:** report violation *magnitude* (pu·steps) and time-outside-band alongside the
step rate, and keep the zero-injection run as a permanent reference row in every results
table.

---

## A5 — At the published operating point the safety layer *fails* on ~1 step in 8

Found while porting the projection, and not visible anywhere in the thesis because the
infeasibility rate was never logged.

The projection tightens the voltage band by the safety margin, so its effective lower bound
is `0.95 + 0.010 = 0.960 pu`. At `load_scale = 0.50` the idle feeder sits at **Vmin =
0.9441** — already 0.016 pu below that bound. No command the four 80 kVA stations can issue
lifts the deepest buses back over 0.960 (the summed sensitivity at the worst bus is about
1.8e-4 pu/kW, so full injection at every station buys ~0.014 pu). The program is therefore
*infeasible by construction* whenever the feeder is near its evening peak.

Measured over a full day with a representative −40 kW request at every station:

| load scale | margin | idle Vmin | infeasible | command zeroed |
|---|---|---|---|---|
| **0.50 (thesis)** | **0.010 (thesis)** | 0.9441 | **0.125** | **0.125** |
| 0.50 | 0.005 | 0.9441 | 0.045 | 0.045 |
| 0.50 | 0.000 | 0.9434 | 0.000 | 0.000 |
| **0.40 (proposed)** | 0.010 | 0.9543 | **0.000** | 0.000 |

On infeasibility the layer returns an **all-zero command** and, after three consecutive
failures, freezes the station. So for roughly an eighth of every episode — concentrated in
the evening peak, exactly when charging decisions matter — SafeSAC was not being *projected*,
it was being *switched off*.

That reframes three published results:

- SafeSAC's remarkably tight violation-rate spread (std 0.002 vs SAC-Lag's 0.024) is what
  you would expect if the controller is pinned to a deterministic zero command during the
  binding window, not evidence of "much more consistent safety behaviour" (§6.3).
- Its lower V2G utilisation (0.103 vs SAC-Lag's 0.176) follows for the same reason.
- The service gain is then partly attributable to the *fallback*, not the projection —
  which compounds A1: the ablation cannot separate them.

**Fix.** Log the projection status distribution — ok / infeasible / frozen / skipped — for
every step of every run, and report it as a first-class metric. Move to `load_scale = 0.40`,
where the margin-tightened bound is satisfiable and the measured infeasibility rate is zero.
Choose the margin against the operating point rather than fixing it at 0.010, and add margin
∈ {0, 0.005, 0.010, 0.020} to the ablation grid. A safety layer whose fallback fires an
eighth of the time needs that fallback characterised, not hidden.

---

## A6 — n = 1 training seed, but the paper reports d = 10.6 and p = 4e-21

Every learned arm was trained once. The 25 evaluation episodes vary the *scenario*, not the
*policy*. The paired tests therefore estimate scenario variance with the policy held fixed,
and the resulting effect sizes (Cohen's d up to 11.9) and p-values (down to 1.7e-21) are not
statements about the method.

The thesis states this honestly in §6.11. That does not save it: for a Q1 RL paper it is
the single most common rejection reason.

**Fix.** ≥5 training seeds per configuration; report mean ± 95 % CI **across seeds**;
run the significance tests at the seed level, or use a hierarchical/bootstrap scheme that
respects both levels. Drop the language of "statistically tied / decisive" until then.

---

## B1 — The stated objective is not the implemented objective

Abstract: *"a reward combining time-of-use energy cost, V2G revenue, and battery
degradation."* Eq. (4.7): `r = −c_econ − c_deg − w_s Σ d_j`.

The implemented reward has a **fourth term — total feeder I²R loss priced at the retail
tariff — with weight 1.0 and scale 1.0**, and it is the *largest* term. Under a random
rollout it is 51.6 % of the reward magnitude while the economic term is 2.1 %
(verified: the four weighted terms sum to exactly the logged −1120.39).

Worse, that loss is *total feeder loss*, mostly driven by background load, so it injects a
large uncontrollable offset and variance into the learning signal — a plausible contributor
to the flat, noisy training curves.

Two smaller mismatches: Eq. (4.6) defines the service penalty on the SoC *fraction*
squared; the code uses `(shortfall × capacity_kWh)²`. Eq. (4.7) omits all weights and scales.

**Fix.** Either delete the loss term or restrict it to the incremental loss attributable to
station injections, then state the full reward with its weights and normalisation, and
add a reward-ablation table.

---

## B2 — Gate 2's "80 kW" is a solver failure, not a measurement

Patch 7 v2 output, with the margin temporarily zeroed:

```
weak   safe_P (kW): [0. 0. 0. 0.]  status=infeasible
strong safe_P (kW): [-80. -80. -80. -80.]  status=ok
||safe_weak - safe_strong||_inf = 80.00 kW
```

The 80 kW is the distance between *the infeasibility fallback* (all zeros) and the strong
grid's answer. With the actual 0.010 pu margin in place both sides are infeasible and the
gap is **0.00 kW**. §6.10 presents the 80 kW as *"stronger evidence of grid-awareness than
the > 1 kW the gate sought"*. It is the opposite: at the paper's own operating point the
projection has **no feasible action** for that probe.

And Table 5.3's clean −54.13 kW numbers come from a different operating point
(`LOAD_STRESS_MULT = 0.40`, Vmin 0.9557) than every reported experiment (0.50, Vmin 0.9441).
This is not disclosed.

**Fix.** Re-run the grid-awareness probe at the reported operating point with a feasible
request magnitude, sweep the request from 0 to rated and plot the weak/strong response
curves. Report the projection's infeasibility rate during evaluation — currently unlogged.

---

## B3 — The claimed per-step sensitivity refresh is hourly

`sensitivity_refresh_steps = 12` → `SensitivityCache` refreshes **once per hour**.
The thesis asserts per-step refresh in the abstract, §5.4 (*"recomputed on the live network
at every step"*), Table 5.2 (*"Sensitivity refresh — every step (live network)"*) and
Algorithm 1 line 4. The SOCP is re-solved every step; its physics parameters are up to
55 minutes stale.

**Fix.** State the real cadence, and add the ablation this invites: refresh ∈ {1, 12, 288,
never} vs violations and vs compute. That ablation is genuinely interesting — it quantifies
how much "live physics" the method actually needs, which is the paper's core question.

---

## B4 — The proposed method loses to a 2018 droop standard on the headline safety metric

Droop: **0.0521** violation rate, Vmin **0.9474**. SafeSAC: 0.0912, Vmin 0.9438 —
1.75× more violations than the industry baseline. And SafeSAC uses *less* V2G than the
unprojected agent (utilisation 0.103 vs 0.176), on a paper whose title is about V2G
voltage support.

The thesis resolves this by declaring droop "Pareto-optimal (extreme safety)". A reviewer
will not accept that: the obvious question is why deploy a learned controller that is
measurably less safe than the standard it is supposed to improve on.

**Fix.** Either (i) show a regime where the learned controller dominates droop on both axes
— high-PV overvoltage, unbalanced feeders, congestion, multi-hub coordination — or
(ii) reframe the contribution away from beating droop on violation rate. Related: droop's
advantage comes from **reactive** support, which cuts against the paper's V–P-dominance
premise. That tension needs an explicit answer, not a Pareto label.

---

## B5 — Cross-deployment "collapse" rests on a diverged baseline

`saclag_strong_v2` finished with **α = 19.402** — the entropy temperature ran away by
~20×, with no cap (A1). Its policy is not a converged constrained-RL policy. The paper's
most dramatic claim — *"the SAC-Lag policy collapses to a non-charging, drain-and-sell
behaviour (targets met = 0.000)"* — is drawn from that run.

Note also the direction: SafeSAC-strong→weak has a **higher** violation rate (0.1058) than
SafeSAC-weak (0.0912) and than SAC-Lag-strong→weak (0.0151). The projection did not make
transfer safer on the metric the paper leads with; it made it *useful* (SoC met 0.447 vs 0).
That is a defensible and interesting claim — but it is a claim about **service preservation
under transfer**, not about safety, and it must be stated that way.

**Fix.** Retrain with the cap, verify convergence diagnostics (α, λ, Q-loss, return) for
every arm, and re-run the transfer study over a *family* of feeders rather than one pair.

---

## C — Smaller items

- **C1** Load profile is a parametric placeholder; the notebook prints its own
  "replace before publication" warning. Q1 wants measured data (UK-DALE / REFIT /
  Pecan Street / ELAAD for EV sessions).
- **C2** Cumulative training-violation curves compare 97 vs 85 and 114 vs 86 episodes;
  normalise per episode (32.4 vs 27.0 and 0.99 vs 0.00) or truncate to a common budget.
- **C3** No MPC / multi-period OPF oracle. The closest competitor benchmarks against one;
  without it "how far from optimal?" is unanswerable.
- **C4** Transformer constraint never binds — max loading 0.011 pu across all runs. Either
  size it to bind or drop it from the constraint set and the narrative.
- **C5** Single feeder, 4 stations. The nearest published work runs IEEE 34- and 123-bus
  with hundreds of EVs.
- **C6** `1e-6` inside `log(1 − tanh²)` and no `enforce_q_lims` in the power flow: minor,
  worth cleaning before release.
- **C7** Convergence detection is a moving-average plateau test; on these noisy returns it
  stops runs at arbitrary points (85–114 episodes). Use a fixed budget for all arms.
