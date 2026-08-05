# SafeSAC — Phase 0.4: fast radial power flow + analytic sensitivities

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
