# SafeSAC — Verified Knowledge Base

Source material read in full: `SafeSAC_Final.pdf` (64 pp), `thesis11.ipynb` (39 cells,
286 k chars of source + outputs), `thesisbookartifacts21.ipynb` (12 cells),
`trained_models_system_configurations.zip` (4 checkpoints, 4 episode logs, tables, figures).

Everything below is **verified against the code and the saved artifacts**, not against the
thesis prose. Where prose and code disagree, that is recorded in `01-audit-blocking-issues.md`.

---

## 1. What the system actually is

**Task.** Real-time active/reactive set-point control of 4 bidirectional EV charging stations
on a modified IEEE 33-bus (Baran–Wu) radial feeder, formulated as a CMDP, solved with
SAC + augmented Lagrangian + a per-step convex safety projection.

**Testbed**

| Item | Value |
|---|---|
| Network | `pandapower.networks.case33bw` |
| "Weak" variant | + Thevenin bus upstream of slack; Z = 6 % on 10 MVA / 12.66 kV base; R/X = 2.0 → 34 buses |
| "Strong" variant | unmodified case33bw (infinite bus) → 33 buses |
| EV stations | 4, at 0-indexed buses **17, 21, 24, 32** (Baran–Wu 18, 22, 25, 33), 80 kVA each |
| PV | 3 × 100 kW at 0-indexed buses 5, 12, 29 (BW 6, 13, 30) |
| Episode | **1 day = 288 steps × 5 min** (`training_episode_days = 1`) |
| Operating point | `case33bw_load_scale = 0.50` (Patch 1); daily multiplier ∈ [0.40, 1.00] |
| Voltage band | [0.95, 1.05] pu; transformer limit 1.0 pu |
| Master seed | 137710; disjoint train / eval seed bands via BLAKE2b |

**Base power flow (no EV action)**

| | Vmin @ nominal load | Vmin @ scale 0.50, peak mult | Loss |
|---|---|---|---|
| Weak | 0.8816 pu | **0.9441 pu** | 338.6 kW |
| Strong | 0.9131 pu | — | 202.7 kW |

> The weak feeder is **already outside the band at the daily peak with zero EV power**.
> This drives the whole safety story — see audit item A2.

**Measured voltage sensitivities** (finite difference on live network, ±4 kW perturbation)

| Grid | Bus | \|∂V/∂P\| | \|∂V/∂Q\| | P/Q ratio |
|---|---|---|---|---|
| Weak | 17 | 9.077e-5 | 7.104e-5 | 1.278 |
| Weak | 21 | 2.465e-5 | 2.229e-5 | 1.106 |
| Weak | 24 | 2.553e-5 | 1.680e-5 | 1.519 |
| Weak | 32 | 5.710e-5 | 4.458e-5 | 1.281 |
| **Weak mean** | | **4.951e-5** | **3.868e-5** | **1.280** |
| Strong | 17 | 7.988e-5 | 6.459e-5 | 1.237 |
| Strong | 21 | 1.823e-5 | 1.877e-5 | 0.971 |
| Strong | 24 | 1.860e-5 | 1.317e-5 | 1.412 |
| Strong | 32 | 4.774e-5 | 3.891e-5 | 1.227 |

At load scale 0.50 the weak-grid means are 4.512e-5 / 3.550e-5 → ratio **1.271**.

**Sign convention (code is authoritative)**
`p_kw > 0` = **injection into the grid = V2G discharge**; `p_kw < 0` = **charging (G2V)**.
Set by `set_ev_station_power` → `net.sgen.p_mw`, and confirmed in
`distribute_station_power`, `update_ev_soc`, `UncoordinatedAgent` (charges at `p_pu = -1.0`)
and `compute_metrics` (`charge_mask = kwh_signed < 0`).

**Fleet model (after Patch 1)**
capacity N(60, 15) clipped [30, 100] kWh · arrival SoC U[0.15, 0.55] · target SoC U[0.70, 0.90] ·
dwell lognormal(ln 7, 0.45) clipped [2, 12] h · bimodal arrivals (08:30 σ1.0 w=0.55 / 18:00 σ1.5) ·
V2G opt-out 0.20 · no-show 0.05 · early-depart 0.10 (factor U[0.70, 0.95]) ·
per-EV ceiling 22 kW, η = 0.92 · Monte-Carlo feasibility **273/273 = 100 %**.

**Prices.** 3-tier TOU $0.08 / $0.15 / $0.30 per kWh; V2G buyback ρ = 0.70; mean $0.158/kWh.
**Load.** Parametric placeholder (`residential_daily_multiplier`), *not* measured data —
the notebook itself prints a `[WARN] ... replace before publication`.

---

## 2. The controller

**MDP.** obs dim **95**, action dim **8** (P, Q per station, normalised to ±80 kVA).
Obs = 34 bus voltages + trafo loading + 32 bus loads + 4×4 fleet aggregates + 3 PV
+ price + forecast + 6 time encodings + relative load. Welford running normaliser, frozen at eval.

**Networks.** 2×256 ReLU MLP. Actor 94,480 params; each critic 92,673; total trainable 372,499.
Tanh-squashed Gaussian actor; twin reward critics + separate cost critic; target entropy −8.

**Reward — as implemented** (`compute_reward`), *r* = −Σ<sub>k</sub> w<sub>k</sub>·c<sub>k</sub>/s<sub>k</sub>:

| term | raw quantity | w | s |
|---|---|---|---|
| `cost` | TOU purchase − 0.70·TOU resale ($) | 1.0 | 5.0 |
| `user` | Σ (unmet kWh)² at departure | 5.0 | 100.0 |
| `deg` | $0.040 × Σ\|P\|Δt | 0.5 | 1.0 |
| `loss` | **total feeder I²R loss × price ($)** | 1.0 | 1.0 |

Random-policy 1-day decomposition (exactly reproduces reward −1120.39):

| term | raw | weighted | share |
|---|---|---|---|
| cost | 119.28 | 23.86 | 2.1 % |
| user | 9831.85 | 491.59 | 43.9 % |
| deg | 52.63 | 26.32 | 2.3 % |
| **loss** | 578.62 | **578.62** | **51.6 %** |

**Constraint cost.** `c_t = Σ_b [0.95 − V_b]₊ + [V_b − 1.05]₊ + [ℓ − 1.0]₊` (Patch 3's ×100
scaling and Patch 3b's `clamp(y_c, min=0)` were **commented out** in the final run).
Threshold d = 0.01; λ learning rate 1e-3; quadratic penalty warm-up 10 k steps, max 1.0.

**Projection (`SensitivityProjector`).** DPP-parametrised CVXPY QP/SOCP, CLARABEL solver,
8 variables. Constraints: box ±80 on P and Q, ramp ±40 kW/step, linearised
v = v₀ + S_P(P−P₀) + S_Q(Q−Q₀) ∈ [0.95+m, 1.05−m] with m = 0.010 pu, transformer
loading ≤ 1.0 (also linearised), per-station SOC cone ‖(P,Q)‖₂ ≤ 80, and a freeze mask.
On infeasible/solver error → returns **all-zero action**, increments a failure counter,
freezes the station after 3 consecutive failures.

**Sensitivity refresh cadence.** `sensitivity_refresh_steps = 12` → **once per hour
(every 12th step)**, via `SensitivityCache`. *Not* every step.

---

## 3. Baselines

| Method | Action |
|---|---|
| Uncoordinated | `p_pu = −1.0` (full-rate charge) whenever any connected EV is below target; Q = 0 |
| Droop (1547) | TOU P schedule: −1.0 for h<6 or h≥22, **+0.5 for 16≤h<21** (V2G), else −0.3; plus piecewise-linear Q–V droop (V_low 0.92, deadband 0.98–1.02, V_high 1.08) |
| SAC-Lag | SAC + cost critic + λ, raw action applied |
| SafeSAC | SAC-Lag + SOCP projection on the output |

---

## 4. Training runs actually used (from the checkpoints)

| run | grid | eps | viol/ep | cum viol | **final λ** | **final α** | lr_critic | α cap | max eps |
|---|---|---|---|---|---|---|---|---|---|
| `saclag_weak_v2` | weak | 97 | 32.39 | 3142 | **0.000** | 0.847 | 3e-4 | **none** | 150 |
| `safesac_weak_v3` | weak | 85 | 26.96 | 2292 | **17.325** | 0.613 | **1e-4** | **1.0** | 100 |
| `saclag_strong_v2` | strong | 114 | 0.99 | 113 | **0.000** | **19.402** | 3e-4 | **none** | 150 |
| `safesac_strong_v3` | strong | 86 | 0.00 | 0 | **17.847** | 0.418 | **1e-4** | **1.0** | 100 |

λ values read directly out of the `.pt` archives (IEEE-754 big-endian doubles):
`saclag_* → 0.0`, `safesac_weak_v3 → 17.324713228736073`,
`safesac_strong_v3 → 17.847470766631886`.

**One training seed per configuration.** All reported variability is across evaluation
scenarios, not across training runs.

---

## 5. Final evaluation — 25 shared-seed episodes, weak feeder

| Method | Viol. rate | Vmin | SoC met | Net cost $ | Reward | V2G util. | Throughput kWh |
|---|---|---|---|---|---|---|---|
| Uncoordinated | 0.1156 ± 0.0087 | 0.9383 | 0.9955 ± 0.0121 | 230.73 ± 27.56 | −205.60 | 0.0000 | 1128.8 |
| **Droop (1547)** | **0.0521 ± 0.0087** | **0.9474** | 0.3245 ± 0.1130 | 66.27 ± 16.04 | −733.16 | 0.0969 | 1326.7 |
| SAC-Lag (weak) | 0.0904 ± 0.0243 | 0.9425 | 0.2767 ± 0.1166 | 104.29 ± 24.79 | −923.50 | 0.1765 | 1629.0 |
| **SafeSAC (weak)** | 0.0912 ± 0.0023 | 0.9438 | **0.5688 ± 0.1639** | 125.94 ± 23.09 | −505.15 | 0.1027 | 1224.7 |
| SAC-Lag (strong→weak) | 0.0151 ± 0.0136 | 0.9492 | 0.0000 | −38.17 ± 7.61 | −1898.67 | 0.1055 | 262.7 |
| SafeSAC (strong→weak) | 0.1058 ± 0.0031 | 0.9438 | 0.4469 ± 0.0736 | 69.66 ± 14.85 | −1024.12 | 0.0475 | 669.2 |

Paired tests (n = 25, same eval seeds), SafeSAC − SAC-Lag:

| Regime | Metric | Δ | 95 % CI | p (t) | p (W) | d |
|---|---|---|---|---|---|---|
| in-dist | viol rate | +0.00083 | [−0.0081, +0.0114] | 0.865 | 0.580 | 0.061 |
| in-dist | SoC met | +0.2921 | [+0.2324, +0.3519] | 2.20e-9 | 5.96e-8 | 2.041 |
| in-dist | net cost | +21.65 | [+9.54, +34.03] | 1.92e-3 | 2.51e-3 | 0.886 |
| x-deploy | viol rate | +0.09069 | [+0.0846, +0.0957] | 4.14e-21 | 1.18e-5 | 10.60 |
| x-deploy | SoC met | +0.44691 | [+0.4171, +0.4769] | 1.88e-20 | 1.22e-5 | 11.90 |
| x-deploy | net cost | +107.83 | [+101.34, +113.93] | 1.75e-21 | 5.96e-8 | 9.41 |

**Decision gates: 3/5 pass.**
1. V–P dominance ratio 1.271 ≥ 0.90 → PASS
2. Projection gap ‖·‖∞ = 80.00 kW → **FAIL** (weak side `status = infeasible`, returns zeros; strong side passes −80 kW. With the 0.010 margin *both* sides are infeasible and the gap is 0.00 kW.)
3. In-dist safety ratio 1.009 ≤ 1.05 → PASS
4. Cross-deploy safety Δ = +0.0907 (SafeSAC worse) → **FAIL**
5. Service Δ = +0.292 → PASS

**Pareto (viol, SoC met):** uncoord, droop, SafeSAC-weak, SAC-Lag-strong→weak are
non-dominated; SAC-Lag-weak dominated by droop; SafeSAC-strong→weak dominated by SafeSAC-weak.

Reproducibility: the artifacts notebook re-ran evaluation from the checkpoints and
reproduced every aggregate to the printed precision. Environment: Python 3.12,
PyTorch 2.10 + CUDA 12.8, Tesla T4, pandapower 3.2.0, cvxpy 1.5.3, CLARABEL, gymnasium 0.29.1.

**Table 5.3 in the thesis (−80 → −54.13 / −77.95 / −76.85 / −73.30 kW) was produced at
`LOAD_STRESS_MULT = 0.40`**, inside the Block-4 validation cell, *before* Patch 1 raises the
operating point to 0.50. Weak-grid Vmin there is 0.9557, not 0.9441.

---

## 5b. Port reproduction of Table 6.1 — Stage 0 gate, PASSED

`scripts/reproduce_table_6_1.py` loads the four shipped checkpoints with their frozen
normalizers and replays the published eval band (`patch7_weak_eval`, 25 episodes, weak
feeder, `load_scale` 0.50, margin 0.010, 1-day episodes).

| method | metric | published | port | Δ |
|---|---|---|---|---|
| SAC-Lag (weak) | viol / SoC / cost / R | 0.0904 / 0.2767 / 104.29 / −923.50 | **0.0904** / 0.2752 / 104.52 / −923.11 | rates exact |
| SafeSAC (weak) | viol / SoC / cost / R | 0.0912 / 0.5688 / 125.94 / −505.15 | **0.0912** / 0.5704 / 125.82 / −505.37 | rates exact |
| SAC-Lag (strong→weak) | viol / SoC / cost / R | 0.0151 / 0.0000 / −38.17 / −1898.67 | **0.0151 / 0.0000 / −38.1709 / −1898.6735** | 6 s.f. |
| SafeSAC (strong→weak) | viol / SoC / cost / R | 0.1058 / 0.4469 / 69.66 / −1024.12 | **0.1058 / 0.4469 / 69.6595 / −1024.1232** | 6 s.f. |

Vmin reproduces to 4 dp on all four rows. The residuals on the two in-distribution rows
(≤0.25 %) are float32 drift: the reference ran torch 2.10 on a Tesla T4, the port runs torch
2.13 on CPU, and near an action bound the last-bit difference occasionally flips a
charge/idle decision. The two cross-deployment rows matching to 6 significant figures is
what identifies this as arithmetic, not a porting error.

**Two traps found while closing this gate, recorded so they are not re-derived:**

1. `SensitivityCache.needs_refresh` tests `current_step - last_refresh >= refresh_steps`.
   `current_step` restarts at 0 each episode and `last_refresh` does not, so read literally
   the cache can never refresh again after episode 1. It *does* refresh, because a later
   patch cell (`thesis11.ipynb` §"Patched SafeSACLagAgent.select_action") rewires
   `select_action` to clear the cache and the projector freeze latch whenever `env.reset()`
   builds a new network object. Running the unpatched logic instead inflates SoC met by
   +0.117 and net cost by +$60 — so the patch is load-bearing for every published SafeSAC
   number.
2. `compute_grid_sensitivities` runs its **own** power flow at the current network state.
   Handing it the env's cached `_last_pf` linearises one exogenous step behind.

Recorded projector behaviour over the reproduction run (7 200 steps): **900 infeasible
(0.1250)**, **750 steps with a latched-off station (0.1042)**, 600 refreshes. Identical for
both SafeSAC checkpoints. See audit A5.

---

## 6. Compute budget observed

| | ms/step | 1 run (≈100 ep × 288) |
|---|---|---|
| SAC-Lag | 42–58 | ≈ 28 min |
| SafeSAC | 101–118 | ≈ 48 min |
| Eval, 25 ep | — | 5 min (SAC-Lag) / 12 min (SafeSAC) |

Bottleneck is the in-loop pandapower Newton–Raphson solve (`numba=False`), plus 8 extra
solves per sensitivity refresh (2 per station × 4 stations, central differences).
