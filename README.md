# SafeSAC — Phase 0 pipeline fixes

| File | Phase | Purpose |
|---|---|---|
| `radial_pf.py` | 0.4 | Fast radial power flow + analytic voltage sensitivities |
| `validate_radial_pf.py` | 0.4 | Validation against pandapower on the thesis feeders |
| `lagrangian.py` | 0.2 | Corrected CMDP dual-variable controller |
| `test_lagrangian.py` | 0.2 | Reproduces the multiplier defect; validates the fix |
| `telemetry.py` | 0.3 | Per-episode instrumentation + post-hoc health report |
| `safesac_patch.py` | — | Drop-in patches wiring all of the above into the notebook |
| `test_integration.py` | — | Patched `run_pf` / sensitivities vs pandapower |
| `regression_lock.py`, `golden/` | 0.1 | Freezes the published numbers before anything changes |

## How to apply

```python
import safesac_patch
safesac_patch.apply_all(globals(), d_step=0.01)   # after all definition blocks
CONFIG["sensitivity_refresh_steps"] = 1           # per-step refresh is now cheap
```

Then, **before retraining**, re-evaluate from the existing checkpoints and:

```bash
python regression_lock.py --check results/patch7_v2_main_results.csv
```

A pass means the solver swap did not move the published numbers, so any later
change is attributable to retraining rather than to the swap. Use
`patch_sensitivities(analytic_dv=False)` for a machine-exact comparison that
isolates the power-flow swap from the ~3% linearisation error.

### Integration test results

```
run_pf vs pandapower, 150 scenarios x 2 feeders
  v_pu     max err 4.7e-09 pu     p_loss   max err 1.9e-08 MW
  angle    max err 1.8e-07 deg    loading  max err 6.4e-10 pu
  p_ext    max err 1.2e-07 MW
    (bounded by pandapower's own default tolerance_mva=1e-8, not by the solver)

compute_grid_sensitivities vs shipped finite difference
  analytic   dV/dP median rel  3.6% / 2.6%   dL/dP max 5e-14
  fd_fast    dV/dP max 4.7e-13 pu/kW         dL/dP max 5e-14

run_pf 122-143 us (was 32-35 ms, ~250x)
```

`patch_lagrangian` and `patch_projection_telemetry` are **not** covered by
these tests — they touch torch code that needs the full training stack. Their
check is the first instrumented run: assert `agent.lag.health().ok` and read
the new `lam` column.

---

## Phase 0.2 — the multiplier defect

The shipped checkpoints ended at

```
saclag_weak_v2     lambda = 0.0        saclag_strong_v2   lambda = 0.0
safesac_weak_v3    lambda = 17.32      safesac_strong_v3  lambda = 17.85
```

With `lambda = 0` the constraint term contributes **nothing** to the actor
loss, so the SAC-Lag baseline the thesis calls "precisely the AL-SAC
formulation of Chen et al." trained as an unconstrained agent.

The root defect is dimensional. `qc_new` estimates the discounted *return*
`E[Σ γᵗ cₜ]`, but `constraint_threshold = 0.01` is documented as a *per-step*
budget. At `γ = 0.99` those differ by `1/(1-γ) = 100`.

`test_lagrangian.py` demonstrates the consequence in closed loop:

```
[satisfied constraint] J_C=0.219 vs budget d_return=1  -> met with 4.6x margin
  legacy lambda = 5.23 (and still climbing)
  fixed  lambda = 0    (correctly inactive)
```

A policy comfortably *inside* its documented budget is penalised harder and
harder, without bound. When the budget sits below the structural cost floor —
which it does on the weak feeder — there is no equilibrium at all: λ grows
linearly forever and the shipped code has no cap, no health check, and no log.

`LagrangeController` fixes the scale, normalises the dual error so `lr` is
scale-free, caps λ, and exposes `health()` so a degenerate or saturated
multiplier fails the run instead of passing silently. Use
`from_measured_floor()` to set the budget above the floor measured in Phase 1.

**One result contradicted the plan.** I recommended PID damping (Stooke et al.).
Under a 300-update policy lag:

```
plain lr=2e-2 : 13.0% undershoot
+ kp=0.5      : 11.8%   (small real gain)
+ kd=4.0      : 13.0%   (inert — the derivative fires only on rising cost,
                         and the approach to budget is monotone)
lr=5e-3       :  0.0%   (the integral gain is the dominant knob)
```

So tune `lr` conservatively first; `kd` should only be expected to help where
cost is noisy or non-monotone. The gains are exposed, not recommended by default.

**Still open:** *why* the two arms landed on opposite sides. The scale error is
definite and dimensionally wrong regardless, but attributing 0-vs-17 to a
specific mechanism needs the instrumented rerun — which is what 0.3 provides.

## Phase 0.3 — instrumentation

`telemetry.py` records λ, α, `mean_qc`, cost excess, projection-active fraction,
SOCP-infeasible steps, **projection-exception steps** (the silent bypass), and
worst-bus voltage per episode. `health_report()` turns a finished run into
findings, and works on the old logs too. Run against the thesis artifacts it
recovers the audit independently:

```
--- safesac_weak_v3 ---
  [FAIL] LAMBDA_NOT_LOGGED: impossible to verify the constraint was ever active
  [FAIL] NOISY_CONVERGENCE: last-20-episode reward CV = 47%; a 'converged' flag
         on a signal this noisy is not meaningful
  [WARN] UNDER_TRAINED: 24480 steps, vs 1e5-1e6 typical for SAC here
  [WARN] VIOLATION_FLOOR: last 5 episodes all had exactly 26 violation steps
         despite different seeds: structural, not policy-driven
```

Reward CV across the four runs: 22%, 47%, 36%, 28% — all flagged `converged`.

---

## Phase 1.1/1.2 — controllability envelope (Gate A: **PASS**)

`phase1_controllability.py` brackets what *any* controller could do, by running
the true AC power flow at three station commands per half-hour of a weekday:
stations idle, stations at the voltage-optimal point on their 80 kVA circle,
and the opposite direction. No policy, no training.

```
weak feeder      load  Vmin idle  Vmin best  viol idle  viol best  controllable
                 0.40     0.9557     0.9652       0.0%       0.0%         0.0%
                 0.45     0.9499     0.9597       2.1%       0.0%         2.1%
                 0.50     0.9441     0.9541      10.4%       0.0%        10.4%
                 0.75     0.9138     0.9253      35.4%      25.0%        10.4%
                 1.00     0.8816     0.8946      56.2%      43.8%        12.5%
```

**This corrects an earlier conclusion in this repo.** At load 0.50 the ideal
command reaches `Vmin = 0.9541 > 0.95`, so **every** violation is fixable and
none is structural. The violations are not a physical floor.

What actually causes them is the projection's own safety margin:

```
tightest headroom above 0.95 at the ideal command : 4.10 milli-pu
thesis margin (Table 5.2)                         : 10.00 milli-pu

margin 0-4 m-pu -> 100% of the day reachable
margin   5 m-pu ->  97.9%
margin  10 m-pu ->  89.6%    <- the thesis setting; 10.4% unreachable
```

The margin tightens the target band to [0.96, 1.04], and the stations can only
reach 0.9541. So the SOCP is infeasible at exactly the hours that matter, the
3-consecutive-failure rule freezes the stations, and the violation count lands
on the same value every episode regardless of seed. That is the full chain
behind the 26/288 count, the bit-identical `vmin_pu_mean`, and the null safety
result — and it is a two-character fix, not a physics limit.

Set `margin = 0.002`: the analytic sensitivities carry ~3% median error, which
on a 5 milli-pu excursion is ~0.15 milli-pu, so 2 milli-pu is >10x the headroom
needed.

---

## Phase 0.4: fast radial power flow + analytic sensitivities

Replaces the `pandapower.runpp` call and the finite-difference sensitivity
refresh in the SafeSAC training loop. Both are derived from one precomputed
path-impedance matrix `Zpath = A diag(z) Aᵀ`, where `A[b, l] = 1` iff branch `l`
lies on the slack-to-`b` path.

* Power flow: fixed point `V = V_slack + Zpath conj(S/V)` — the current-injection
  form used by RL-ADN and PI-TD3 (Giraldo et al., *EPSR* 211:108326).
* Sensitivities: `dV/dP = Re(Zpath)/|V|`, `dV/dQ = Im(Zpath)/|V|` (LinDistFlow),
  available as a slice of a matrix that is already resident.

## Files

| File | Purpose |
|---|---|
| `radial_pf.py` | `build_topology`, `RadialPowerFlow`, `injections_from_pandapower` |
| `validate_radial_pf.py` | Validation against pandapower on the thesis weak/strong feeders |

## Validation (IEEE 33-bus Baran–Wu, thesis weak & strong variants)

```
voltage vs pandapower   max 3.2e-11 pu   (200 random load/EV/PV scenarios each)
fixed-point iterations  mean 10.5, max 14
fast PF                 20-21 us   vs pandapower 29-32 ms   -> ~1400x
analytic sensitivities  8.5 us     vs 8 x runpp = ~245 ms   -> ~29000x
exact FD sensitivities  ~1.0 ms    (sensitivities_fd, matches pandapower to 3.6e-11)
```

Network reconstruction is faithful to the thesis: strong-grid `Vmin = 0.9131 pu`,
`loss = 202.7 kW`; weak-grid `Vmin = 0.8816 pu` at nominal load — both match
Fig. 4.3 exactly.

### Table 4.1 reproduction

P/Q dominance ratios reproduce the thesis to three decimals, including the
sub-unity value at strong-grid bus 21:

| bus | ratio (this code) | ratio (thesis) |
|---|---|---|
| weak 17 | 1.246 | 1.278 |
| weak 21 | 1.098 | 1.106 |
| weak 24 | 1.508 | 1.519 |
| weak 32 | 1.290 | 1.281 |
| strong 21 | 0.968 | 0.971 |

Magnitudes are load-dependent (`|dV/dP|` at weak bus 17: 7.88e-5 pu/kW at load
0.50, 8.44e-5 at 1.00). The thesis's 9.08e-5 corresponds to nominal load, so
**Table 4.1 should state the load scale it was measured at.**

## Sensitivity accuracy

`sensitivities()` (analytic, 8.5 us) carries the LinDistFlow linearisation
error: median 2.6-3.6%, max 12.6% relative. On an 80 kW command that is
~1.4e-4 pu of predicted voltage error, well inside the projection's 0.010 pu
margin. Use `sensitivities_fd()` (~1.0 ms, machine-exact) when that error must
be eliminated; it is still ~30x cheaper than a single `runpp`.

## Two findings that affect the experiment design

**1. The hard SOCP is infeasible at the thesis operating point.** With the
tightened band `[0.96, 1.04]`, no station command can lift the weak feeder into
the band once load ≥ 0.5, because background load alone puts buses below it:

| load scale | Vmin (pu) | hard SOCP |
|---|---|---|
| 0.30 | 0.9671 | feasible |
| 0.40 | 0.9557 | feasible |
| **0.50** | 0.9441 | **infeasible** |
| 0.60 | 0.9322 | infeasible |
| 1.00 | 0.8816 | infeasible |

The thesis runs at 0.50, so the projection spends the whole episode in its
`3-consecutive-failures -> freeze station` fallback rather than in its designed
regime. This is the same structural floor that pins the violation count at 26
and makes `vmin_pu_mean` bit-identical across policies. Fix either by moving the
operating point below ~0.45 or by adopting the soft formulation below.

**2. Slack variables restore graceful degradation.** Penalised slacks on the
voltage band (`+1e6 * sum(slack)`) keep the program feasible everywhere and
degrade smoothly instead of freezing. Cost: 2.06 ms per solve.

## End-to-end step cost

```
PF 21 us  +  analytic sensitivities 9 us  +  soft SOCP 2058 us  =  2.09 ms/step
thesis pipeline                                                 =  118   ms/step
                                                                   -> 57x
```

Phase 3 (40 runs x 250k steps) environment cost drops from ~123 h to **5.8 h**.

The SOCP is now 98% of the step. Calling Clarabel directly with a prebuilt
sparse matrix — bypassing CVXPY's per-solve Python overhead — would cut it to
roughly 100-200 us if the budget ever needs it.

## Usage

```python
from radial_pf import build_topology, RadialPowerFlow, injections_from_pandapower

topo   = build_topology(net, s_base_mva=1.0)          # once per topology
solver = RadialPowerFlow(topo, v_slack=1.0)

# per control step
p, q = injections_from_pandapower(net, topo.n_bus, 1.0)
res  = solver.solve(p, q)                              # res.vm_pu, res.converged
dvdp, dvdq = solver.sensitivities(buses=ev_station_buses)   # every step, ~9 us
solver.reset()                                         # on env.reset()
```

Sign convention: injections are positive **into** the network. The thesis RL
action uses the opposite sign for EV stations (positive = charging = absorbing),
so negate when crossing the boundary.
