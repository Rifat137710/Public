# SafeSAC — Implementation Review

Review of *"Safe Deep Reinforcement Learning for Vehicle-to-Grid Voltage Support in Weak
Distribution Feeders: A Physics-Aware Approach"* (64 pp., dated 11 June 2026).

Findings are ordered by how much damage they do to the thesis's claims. Every number quoted
below is taken from the thesis's own tables and figures.

---

## TIER 1 — The safety projection does not work, and your own Table 6.1 proves it

This is the finding. Everything else is secondary.

### 1.1 The bug

`Listing A.1`, last line of `project()`:

```python
return np.zeros_like(p_request), np.zeros_like(q_request), "infeasible"
```

When the SOCP is infeasible, you command **zero power at every station**. On an
undervoltage-limited feeder, zero injection is not the safe fallback — it is close to the
*worst* available action. The safe fallback is maximum V2G injection (`p < 0`), which is
exactly what lifts the voltage.

And the infeasible branch does not fire rarely. It fires **precisely at the steps where a
violation is occurring**, which is the only time the projection matters. Mechanism:

- The SOCP requires `v ≥ v_lower + margin = 0.95 + 0.010 = 0.960 pu` (Eq. 5.6b, `margin` in
  Table 5.2).
- Table 4.1 gives `∂V/∂P = 9.08e-5 pu/kW` at station 1 (bus 17), the critical bus.
- Table 6.1 gives realised `Vmin = 0.9438 pu` for SafeSAC (weak). Lifting bus 17 from 0.9438
  to 0.960 needs `0.0162 / 9.08e-5 ≈ 178 kW` of injection at that station. The station is rated
  **80 kVA**, and constraint (5.6d) boxes `p` accordingly.
- So at the evening peak the feasible set of (5.6) is **empty**, deterministically, for
  structural reasons. → `"infeasible"` → `p = q = 0` → no charging, no V2G, no voltage support,
  maximum sag.
- Three consecutive such steps and Section 5.4's rule *freezes the station*, which locks in the
  failure for the rest of the peak.

### 1.2 The proof from your own numbers

Four independent pieces of evidence in the thesis, all consistent with the above and with
nothing else:

| Evidence | Location | What it means |
|---|---|---|
| SafeSAC (weak) `Vmin = 0.9438 pu` | Table 6.1 | **1.62 pu-% below the 0.960 pu bound the projection nominally certifies.** A first-order model error cannot be 1.62 pu-% when the whole fleet only moves the bus by ~0.02 pu. The constraint is not being enforced at all. |
| Violation rate 0.091 vs 0.090 (SAC-Lag) | Table 6.1 | A working per-step projection should drive this toward zero, not leave it bit-for-bit unchanged. "Statistically tied on safety" is not a neutral result — for a safety filter it is a **null result**. |
| SAC-Lag (strong→weak) achieves **0.015** | Table 6.1 | A policy with *no projection at all*, that simply discharges hard, is **6× safer than SafeSAC**. This alone falsifies the claim that the projection provides safety. It also proves the constraint is largely *satisfiable* with the available actuators — so the failure is the projection's, not the feeder's. |
| SafeSAC V2G utilisation 0.103 < SAC-Lag 0.176 | Table 6.1 | Adding the "V2G voltage support" layer **reduces V2G usage by 41%**. Exactly what zeroing-out-on-infeasible predicts. The thesis never comments on this column. |
| SafeSAC (weak) training violations flat at ~28 steps/ep, never improving | Fig. 6.1(b) panel (b) | 28/288 = 0.097. The agent never learns its way out because the projection removes its ability to act at the violating steps. |

Section 6.11 explains the 9–12% away as a *"structural violation floor driven by the load
profile"*. **Your own Table 6.1 contradicts this**: the six methods span 0.015 → 0.116, a 7×
range. There is no floor at 9%. The floor is 1.5%, and SafeSAC is sitting six times above it.

### 1.3 The fix — reformulate (5.6) with slack so it is always feasible

This is standard practice for safety layers (Dalal et al. [25], OptLayer [26], and the CBF-QP
literature): a hard state constraint in a projection QP/SOCP **must** carry a slack variable,
otherwise the filter deadlocks at exactly the boundary it was built to defend.

```python
def build_projection(n_mon, n_station, v_lower, v_upper, margin):
    p     = cp.Variable(n_station)
    q     = cp.Variable(n_station)
    s_lo  = cp.Variable(n_mon, nonneg=True)   # under-voltage slack
    s_hi  = cp.Variable(n_mon, nonneg=True)   # over-voltage slack
    t_tx  = cp.Variable(nonneg=True)          # transformer slack  (see 3.7)

    S_P   = cp.Parameter((n_mon, n_station))  # ALL monitored buses, not just stations (3.6)
    S_Q   = cp.Parameter((n_mon, n_station))
    v0    = cp.Parameter(n_mon)
    g_tx  = cp.Parameter(n_station)           # d(loading)/dP
    ell0  = cp.Parameter()
    # ... p0, q0, p_raw, q_raw, s_rated, p_lo, p_hi as before

    v = v0 + S_P @ (p - p0) + S_Q @ (q - q0)

    cons = [
        v >= v_lower + margin - s_lo,         # RELAXED, not hard
        v <= v_upper - margin + s_hi,
        p >= p_lo, p <= p_hi,
        ell0 + g_tx @ (p - p0) <= 1.0 + t_tx,
    ]
    for i in range(n_station):
        cons.append(cp.norm(cp.hstack([p[i], q[i]]), 2) <= s_rated[i])

    W = 1e4                                    # W >> 1 ⇒ near-lexicographic
    obj = cp.Minimize(
        W * (cp.sum(s_lo) + cp.sum(s_hi) + t_tx)      # 1st: minimise violation
        + cp.sum_squares(p - p_raw)                    # 2nd: track the policy
        + cp.sum_squares(q - q_raw)
    )
    return cp.Problem(obj, cons), {...}
```

Properties you get for free:

- **Always feasible** — `p = q = 0` with large slacks is always in the set, so the solver never
  returns `infeasible`. The `except SolverError → zeros` path and the 3-failure freeze rule both
  become dead code and should be deleted.
- **Correct behaviour at the boundary** — when 0.960 pu is unreachable, stage-1 minimises the
  residual violation, which *automatically* yields maximum V2G injection at the sensitive
  stations. That is the physically right answer and the opposite of what you do now.
- The margin now lives inside the slack, so it stops *causing* infeasibility.

If you want a strict lexicographic guarantee instead of big-`W`, do two DPP solves: (1) minimise
`Σs`, (2) minimise `‖p−p_raw‖²` subject to `Σs ≤ Σs* + ε`. One extra ~1 ms solve.

**Expected effect after the fix:** SafeSAC's violation rate should drop from 0.091 toward the
~0.015 that unprojected hard-discharge already achieves, while *keeping* SoC-met near 0.569.
That would be the result the thesis is actually claiming. Right now you are reporting the
projection's failure as a success ("matches safety").

---

## TIER 2 — Experimental design problems that make the reported comparison non-inferential

### 2.1 The headline ablation is confounded three ways

Section 5.6: *"SafeSAC adds **only** the projection on top of SAC-Lag. Holding everything else
fixed in this way is what allows the experiments to attribute any safety/service difference
between the last two rows specifically to the projection."*

Table 5.2 says otherwise. SafeSAC (v3) also differs in:

| | SAC-Lag | SafeSAC (v3) |
|---|---|---|
| Critic learning rate | 3e-4 | **1e-4** |
| Temperature ceiling ᾱ | none | **1.0** |
| Training episodes | **150** | **100** |

Three simultaneous changes. The `+0.292` SoC-met difference — the thesis's headline result —
**cannot be attributed to the projection**. Lowering the critic LR by 3× and capping α are both
known to change SAC's exploration/exploitation balance substantially, and either could produce a
large service swing on its own.

**Fix:** run the 2×2. SAC-Lag with (critic LR 1e-4, ᾱ=1.0, 100 eps) is the only legitimate
baseline for the projection ablation. Also run SafeSAC at 150 episodes. Report both. If the
+0.292 survives, you have your result; if it shrinks, you have learned something more
interesting than what is currently written.

### 2.2 Single training seed + paired t-tests = pseudo-replication

Section 6.11 admits *"each learned controller is trained once."* Chapter 6 then reports
`p = 2.2e-9`, `d = 2.04`, and bootstrap CIs over **25 evaluation episodes**, and Chapter 7 calls
this ethical rigour.

The 25 episodes are not independent replicates of the treatment. They are 25 scenarios evaluated
against **one** SafeSAC network and **one** SAC-Lag network. The inferential unit for a claim
about *methods* is the training run, so your effective n for the method-level claim is **1**.
The p-value answers "did this checkpoint beat that checkpoint on these 25 days" — not "does
SafeSAC beat SAC-Lag." This is the single most-cited failure mode in the DRL reproducibility
literature (Henderson et al., *Deep RL That Matters*; Agarwal et al., *rliable*; Colas et al.,
*How Many Random Seeds?*).

An external examiner will find this in five minutes, and it undercuts the CO2/PO(d) claim.

**Fix:** ≥5 training seeds per configuration (10 if compute allows). Report the interquartile
mean with stratified bootstrap CIs across seeds (rliable), and run the paired test **across
seeds**, not across evaluation episodes. Keep the 25 shared-seed episodes as the within-seed
averaging device. With 4 configs × 5 seeds × ~100 episodes at ~110 ms/step × 288 steps, this is
roughly 5 GPU-days on the T4 — feasible if you start now.

### 2.3 Gate 3, correctly analysed, does **not** pass

Gate 3 is a non-inferiority test: `viol(SafeSAC) ≤ 1.05 × viol(SAC-Lag)`. You evaluated it by
comparing point estimates (ratio 1.009 → PASS). Non-inferiority is established by the
**confidence bound**, not the point estimate.

From Table 6.3: `Δ = +0.0008`, 95% CI `[−0.008, 0.011]`, on a base of 0.090.
Upper bound on the ratio = `1 + 0.011/0.090 =` **1.122 > 1.05**.

The data are **consistent with SafeSAC being 12% worse on violations**. Gate 3 is
indeterminate, not a pass. Same error underlies the abstract's *"holds the voltage-violation
rate statistically constant"* — that is a failure to reject, not evidence of equivalence.

**Fix:** run TOST with the pre-registered 1.05 margin and report the ratio CI. State honestly
that the current n is underpowered for it (n=25 with SD 0.024 detects about d≈0.58 at 80%
power).

### 2.4 SAC-Lag's evaluation number contradicts its own training curve

Fig. 6.1(a) panel (b): SAC-Lag (weak) per-episode violations **fall to ~5 steps** by end of
training (rate ≈ 0.017). Table 6.1 reports SAC-Lag (weak) at **0.090** in evaluation
(≈ 26 steps). That is a **5× discrepancy for the same agent** on the same distribution —
training and evaluation seed bands are disjoint but are drawn from the same generator, so this
cannot be scenario difficulty.

Something is wrong in the checkpoint→evaluation path. The most likely culprit is 2.5 below.
Whatever it is, the headline comparison is being made against a SAC-Lag that is **not** the
agent the training curve shows, and the direction of the resulting bias is unknown.

**Fix:** re-evaluate the final and best checkpoints on the *training* seed band and confirm you
reproduce ~5 violation steps. If you cannot, the eval harness is broken and every number in
Chapter 6 is suspect.

### 2.5 Observation normalisation is the prime suspect — and it likely also explains your flagship "collapse" result

Section 4.6: *"All components are running-normalised."* The thesis never states whether the
running mean/variance statistics are **frozen and saved with the checkpoint**. This is one of the
most common silent bugs in RL pipelines, and it has two consequences here:

**(a)** If the normaliser is re-initialised or keeps updating at evaluation, the policy sees a
different input distribution than it trained on. That would produce exactly the 2.4 discrepancy.
Note that SHA-256-fingerprinting the *weights* (Section 6.1) does **not** cover the normaliser
state — your reproducibility claim has a hole in it.

**(b) The cross-deployment result may be an artefact.** Section 6.9 claims the strong-trained
SAC-Lag *"having learned that the strong grid tolerated aggressive V2G, collapses"* on the weak
feeder. There is a much more parsimonious explanation: the strong grid's voltages live in a
different range (Fig. 4.3: `Vmin` 0.913 vs 0.882 at base load). Normalising weak-grid voltages
with **strong-grid statistics** pushes the observation far outside the trained range, the
tanh-squashed Gaussian saturates, and the policy emits a near-constant extreme action — which
presents as "discharge always, never charge, SoC met = 0.000."

You are attributing a **numerical artefact of input normalisation** to a scientific finding
about policy robustness. This is the thesis's flagship robustness claim (abstract, Ch. 6.9,
Ch. 8.1) and it is currently not established.

**Fix, in order:**
1. Confirm the normaliser stats are saved with the checkpoint and frozen at eval. Add them to the
   SHA-256 manifest.
2. Log the raw and normalised observation ranges under the strong→weak shift. If normalised
   inputs exceed ~±5σ, you have your artefact.
3. Re-run the cross-deployment study with **analytic, grid-independent normalisation** (voltage
   in pu is already ~unit-scale; price by its known max; SoC in [0,1]; power by station rating).
   Nothing in this observation space actually needs running statistics.
4. Log the action distribution. If SAC-Lag strong→weak emits `tanh` outputs pinned at −1, it is
   saturation, not learned behaviour.

Until (3) is done, delete "the SAC-Lag policy collapses" from the abstract and Chapter 8.

---

## TIER 3 — Formulation and implementation errors

### 3.1 The Lagrange multiplier update has a units mismatch and will diverge

`Listing A.2`:
```python
cost_estimate = q_c.mean().item()
lambda_ = max(0.0, lambda_ + lr_lambda * (cost_estimate - cost_threshold))
```

`q_c` is the **cost critic**, i.e. an estimate of `E[Σ γ^t c_t]` — a *discounted cumulative*
quantity. With γ=0.99 its scale is up to `(1−γ^288)/(1−γ) ≈ 95×` the per-step cost.
`cost_threshold = d = 0.01` is described in Table 5.2 as a **per-step** threshold.

You are subtracting a per-step budget from a cumulative value. The residual is therefore
essentially always large and positive, and λ ascends monotonically at 1e-3 per update across
~43,000 updates (150 eps × 288 steps). λ ends up in the hundreds, at which point the actor
objective `Q_r − λQ_c` is **pure cost minimisation** and the reward term is numerically
irrelevant. That is a mechanism — independent of everything else — for the low SoC-met of the
weak SAC-Lag agent (0.277, worse than a droop controller).

**Fix — pick one and state it:**
```python
# Option A: undiscounted episodic budget (recommended; matches a physical safety budget)
d_ep   = d_per_step * T                       # 0.01 * 288 = 2.88
J_C    = ema_of_episode_cost_sums             # measured from rollouts, NOT the critic
lambda_ = max(0.0, lambda_ + lr_lambda * (J_C - d_ep))

# Option B: keep the critic, put d on the same footing
d_disc = d_per_step * (1 - gamma**T) / (1 - gamma)   # ≈ 0.95
lambda_ = max(0.0, lambda_ + lr_lambda * (q_c.mean().item() - d_disc))
```
Option A is what Stooke et al. [22] — which you cite — actually does; the multiplier is driven by
the *measured episodic* cost, not by an off-policy critic evaluated on a replay batch. Using a
replay-batch critic mean also makes the dual variable respond to stale off-policy data.

Also: log λ over training. Its absence from Chapter 6 is conspicuous — a λ trace would have
surfaced this immediately, and a reviewer will ask for it.

### 3.2 It is not an augmented Lagrangian

The method is called "augmented-Lagrangian SAC" throughout (title of Alg. 1, §5.3, Ch. 8, and
the CO-mapping table), and is claimed to be *"precisely the augmented-Lagrangian soft actor-critic
(AL-SAC) formulation proposed for EV charging by Chen et al. [1]."*

Eq. (5.4) is `α log π − (min_k Q_k − λ Q_C)` and Eq. (5.5) is `λ ← [λ + η(Ĵ_C − d)]₊`.
That is **plain Lagrangian dual ascent**. An augmented Lagrangian requires the quadratic
penalty term:

```
L_ρ = f + λ·g + (ρ/2)·[g]₊²          and      λ ← [λ + ρ·g]₊
```

There is no `ρ` anywhere in Table 5.2 and no quadratic term in (5.4) or in Listing A.2. So you
have implemented vanilla SAC-Lag and named it AL-SAC — which also means your "state-of-the-art
learned baseline" is **not** a reproduction of [1].

**Fix — either** implement it properly:
```python
resid = J_C - d_ep
actor_loss = (alpha*logp - (q_r - (lambda_ + rho*max(0.0, resid)) * q_c)).mean()
lambda_    = max(0.0, lambda_ + rho * resid)     # AL: multiplier step size == ρ
```
**or** rename the method to "Lagrangian SAC (SAC-Lag)" everywhere and soften the [1] claim to
"following the CMDP formulation of Chen et al." Do not leave it as-is; this is a
misattribution an examiner familiar with [1] will catch.

### 3.3 γ = 0.99 systematically destroys the service objective

Episode is `T = 288` steps. `γ = 0.99` → effective horizon `1/(1−γ) = 100 steps ≈ 8.3 h`. Mean
dwell time is **7 h ≈ 84 steps** (§4.3). The service penalty `d_j` in Eq. (4.6) is incurred
**only at departure** (Eq. 4.7: `Σ_{j∈D_t} d_j`).

So the cost of charging is paid **now, undiscounted**, while the penalty for not charging is
discounted by `0.99^84 ≈ 0.43`. The agent is structurally biased toward "don't charge, the bill
arrives later at half price." This is a second, independent mechanism producing SoC-met = 0.277.

**Fix (two parts):**
- Use `γ = 1.0` for this fixed-horizon 288-step episode (or 0.999). There is no reason to
  discount inside a single day. Use `γ_c = 1.0` for the cost critic regardless — a safety budget
  should not weight 08:00 violations 100× more than 20:00 violations.
- Make the service signal **dense** via potential-based shaping, which provably preserves the
  optimal policy:
  ```python
  Phi = -w_s * sum((max(0.0, soc_tgt[j] - soc[j]))**2 for j in connected)
  r_shaped = r + gamma*Phi_next - Phi          # Ng et al., potential-based shaping
  ```
  This gives per-step credit for charging progress without changing what is optimal.

### 3.4 `w_s` is never reported, and the squared-SoC form makes under-serving rational

`w_s` appears in Eq. (4.7) and **nowhere else in the thesis** — not in Table 5.2, not in
Chapter 6. It is the single most consequential hyperparameter for your headline metric.

Worse, the functional form is wrong. Back-of-envelope for a 60 kWh vehicle, arrival SoC 0.35,
target 0.80:
- Charging 27 kWh at TOU ≈ $0.15 + degradation $0.04 → **≈ $5.13 cost**.
- Not charging, draining to 0.20 and selling 9 kWh at `ρπ − κ = 0.7(0.30) − 0.04 = $0.17/kWh`
  → **+$1.53 revenue**.
- Penalty avoided by charging: `w_s · (0.80−0.20)² = 0.36 w_s`.

Charging only pays if `w_s > (5.13 + 1.53)/0.36 ≈ 18.5`. If `w_s` is O(1) — the natural choice
when every other term is in dollars — **the reward-optimal policy is drain-and-sell**, and your
agents are behaving correctly for the objective you gave them. The "collapse" is then a reward
bug, not an RL failure.

Two further problems with Eq. (4.6):
- It is quadratic in the SoC *deficit*, so the marginal value of the last kWh → 0. The agent is
  explicitly disincentivised from finishing a charge.
- It is in SoC-**fraction** units, so a 100 kWh vehicle and a 30 kWh vehicle with the same
  fractional deficit incur the same penalty for 3.3× the energy. The text calls it an
  *"unmet-energy penalty"* and Fig. 4.8's legend labels it **kWh²** — neither matches the
  equation.

**Fix:** price unmet service linearly in energy, at a rate that dominates the arbitrage margin:
```
d_j = max(0, SoC_tgt_j − SoC_dep_j) · C_j        # kWh
r_service = − c_unmet · d_j,   with c_unmet ≈ $1.0/kWh   (>> the $0.19/kWh energy+degradation)
```
Constant marginal incentive, correct units, and defensible as a customer-inconvenience tariff.
**Report the value in Table 5.2 and run a sensitivity sweep over it** — a reviewer will ask
whether the SoC-met result is a `w_s` artefact, and right now you cannot answer.

### 3.5 Charger efficiency η = 0.92 is declared and never used

Section 4.3 states `η = 0.92`. It appears in neither Eq. (4.4) (economics), Eq. (4.5)
(degradation), nor the SoC transition in §4.6. Round-trip efficiency is `0.92² = 0.846` — a
**15% penalty on V2G arbitrage** that you are currently giving away for free. This makes
drain-and-sell look ~15% more profitable than it is, compounding 3.4.

**Fix:**
```
SoC update (charge):    ΔE_batt = +η · p · Δt          grid draws p·Δt
SoC update (discharge): ΔE_batt = −|p|·Δt / η          grid receives |p|·Δt
c_econ = Σ_i [ π_t [p_i]₊ Δt − ρ π_t [−p_i]₊ Δt ]     (grid-side, as written — now correct
                                                        because the losses land in the SoC)
```

### 3.6 The projection monitors only the 4 station buses, but the cost is summed over all 33

Eq. (5.6b) says `∀b`. Eq. (4.8) sums `∀b ∈ B`. But `Listing A.1` declares:
```python
S_P = cp.Parameter((n_station, n_station))     # 4 × 4
v0  = cp.Parameter(n_station)                  # 4
```
The constraint set covers **4 buses**, the metric covers **33**. The math in the thesis and the
code do not describe the same program.

In your topology the four stations happen to sit at the four radial extremities (18, 22, 25, 33),
which is a *defensible* choice — but it is never stated or justified, and it breaks the moment
PV injection or heavy V2G creates an **over**-voltage at an intermediate bus, which the
projection cannot see.

**Fix:** either (a) monitor all buses — `S_P` becomes 33×4, still trivial for the solver — or
(b) state explicitly that monitored buses = radial leaf buses, prove they bound the min/max, and
change Eq. (5.6b) from `∀b` to `∀b ∈ B_mon` with `B_mon` defined.

### 3.7 The transformer constraint is in the cost but not in the projection

Eq. (4.8) includes `[ℓ_t − ℓ̄]₊`. Objective 1 (§1.4) promises *"explicit voltage **and thermal**
safety constraints."* Program (5.6) contains **no thermal constraint**. The projection provably
cannot enforce half of what it is claimed to enforce.

**Fix:** add one linear row (already in the 1.3 snippet):
`ℓ0 + g_tx·(p − p0) ≤ 1.0 + t_tx`, with `g_tx = ∂ℓ/∂P` obtained from the same
sensitivity pass. One extra row, negligible solve cost.

### 3.8 The safety cost adds two incommensurate quantities

`c_t = Σ_b ([V−V_b]₊ + [V_b−V̄]₊) + [ℓ_t − ℓ̄]₊`

First term: pu-volts **summed over 33 buses**. Second: pu transformer loading, **one scalar**.
A uniform 0.01 pu dip across 33 buses contributes 0.33; a 33% transformer overload also
contributes 0.33. That relative weighting is arbitrary and undocumented.

**Fix:** normalise each term to a [0,1]-ish scale and weight explicitly:
```
c_t = w_V · (1/|B|) Σ_b ([V−V_b]₊ + [V_b−V̄]₊)/V_tol  +  w_T · [ℓ_t − ℓ̄]₊ / ℓ_tol
```
with `w_V, w_T` reported in Table 5.2. This also makes `d` interpretable, which it currently
is not.

### 3.9 Sensitivities: 9 power flows per step, by finite difference, when the Jacobian is free

Section 4.5 computes `S_P`, `S_Q` *"by perturbation on the live pandapower network"*, refreshed
every step (Table 5.2). That is 4 stations × 2 (P, Q) + 1 base = **9 Newton–Raphson solves per
control step**. Table 6.1(d) confirms it: 42–58 ms → 102–118 ms, i.e. **+60 ms of pure overhead**.

Two problems:
- **It doesn't scale.** Cost is `O(2·n_station)` power flows/step. Section 8.3 lists scalability
  as future work without identifying this as the bottleneck. At 40 stations this is 81 solves
  per 5-minute interval.
- **It's less accurate than the free alternative.** `∂|V|/∂P` is exactly the lower-left block of
  `J⁻¹` from the Newton–Raphson solve **you have already performed**. One back-substitution on
  the existing factorisation gives you *analytic* sensitivities at ~zero marginal cost, with no
  finite-difference truncation error. You also never report the perturbation step size, which is
  the classic source of error in this approach.

**Fix (recommended):**
```python
# after net converges, from the ppc internals
J = pandapower.pypower.makeJac.makeJac(net)     # or build from Ybus at the solved point
# [Δθ; Δ|V|] = J⁻¹ [ΔP; ΔQ]  →  ∂|V|/∂P is the (V, P) block of J⁻¹
Jinv_VP = scipy.sparse.linalg.spsolve(J.tocsc(), e_P_columns)   # only the station columns
```
Solve only for the station columns — that's 8 back-substitutions on **one** factorisation, not
8 full nonlinear solves.

**Even better, and more on-message for a "physics-aware" thesis:** for a *radial* feeder the
LinDistFlow model of Baran–Wu [12] / Farivar–Low [14] — both of which you already cite — gives
the sensitivities in **closed form**: `v ≈ v0 + 2(R p + X q)` where `R`, `X` are the
path-overlap resistance/reactance matrices `R_ij = Σ_{l ∈ P_i ∩ P_j} r_l`. Zero power flows,
exact for the linearisation, and it makes the "physics-aware" framing much stronger than
numerical probing does. Report the linearisation error against the true AC solve — that
validates your 0.010 pu margin, which is currently asserted without evidence.

### 3.10 SoC/dwell power envelopes are missing from the projection

Constraint (5.6d) boxes `p` at the station rating. Nothing ties `p_i` to the **energy actually
available** at station `i`: how many vehicles are plugged in, their SoC, their remaining dwell,
their V2G opt-in status.

If the environment clips the projected command afterwards to physical limits, then **the applied
power ≠ the power the SOCP certified as safe**, and the entire safety argument collapses — you
have certified a command you did not execute. The thesis does not say which order these happen in.

**Fix:** make `p_lo`, `p_hi` **time-varying per station** and computed *before* the solve:
```python
p_hi[i] = min(P_rate_i, Σ_j∈conn(i) min(22 kW, (SoC_tgt_j − SoC_j)·C_j / (η·Δt)))
p_lo[i] = -min(P_rate_i, Σ_j∈conn(i), v2g_opt_in min(22 kW, (SoC_j − SoC_floor)·C_j·η / Δt))
```
Then nothing clips after the projection, and the certificate is real. State explicitly in §5.4
that no post-projection clipping occurs.

### 3.11 Reactive power is never reported — the safety result may be coming from Q, not P

The whole thesis argues active power is the dominant lever. Yet the action space is 8-D
(4 P + 4 Q), and reactive power is **free** in your model: Eq. (4.4) prices only `p`, Eq. (4.5)
degrades only `|p|`. Meanwhile `|∂V/∂Q| = 3.87e-5` is only **28% weaker** than `|∂V/∂P|`
(Table 4.1).

So the reward-optimal behaviour is to slam `q` to the apparent-power boundary at all times and
get voltage support for nothing. **Not a single figure or table in the thesis reports a `q`
set-point.** If that is what the agents learned, the safety numbers are being produced by
reactive support while the narrative credits active-power physics.

**Fix:** (a) plot the per-station `q_i` trajectories alongside Fig. 6.7(b); (b) run a **P-only
ablation** (`q ≡ 0`) — this is the ablation that actually tests the thesis's central physical
claim, and it is currently missing; (c) add a small `|q|` cost or an inverter-loss term so `q` is
not free.

### 3.12 Algorithm 1 and Listing A.2 contradict each other on what goes in the buffer

- Algorithm 1, line 6: `store (s_t, a_t, r_t, c_t, s_{t+1})` — the **raw** action. §5.5 states
  this explicitly: *"the policy gradient is taken with respect to the unprojected action."*
- Listing A.2, `select_safe_action`: `return env.to_action(p_safe, q_safe), status` — returns the
  **projected** action.

These are different algorithms with different fixed points. Pick one and make the text, the
algorithm block, and the listing agree.

For what it's worth, the raw-action choice is *defensible* (it makes SAC correct on the composed
MDP `env ∘ Proj`, and train/deploy stay consistent), but it has a known pathology you should
name: `Proj` is many-to-one, so `Q(s,·)` is **flat** over the whole pre-image of a clipped
command, `∂Q/∂a ≈ 0` there, and the actor can drift arbitrarily deep into infeasible territory
with no gradient pulling it back. Mitigations, cheapest first: add `β‖a_raw − ã‖²` to the actor
loss; or store the projected action; or differentiate through the projection with cvxpylayers
[36] (your listed future work).

### 3.13 Two smaller code issues in the listings

**α windup.** Listing A.2:
```python
agent.alpha = min(agent.log_alpha.exp().item(), alpha_ceiling)
```
The clamp applies to the *value used downstream*, but `log_alpha` itself keeps receiving
gradient and ratchets upward without bound. When the sign of the residual eventually flips, α
takes an enormous number of steps to come back down. Clamp the parameter, not the readout:
```python
with torch.no_grad():
    agent.log_alpha.clamp_(max=math.log(alpha_ceiling))
```
Also note `agent.alpha` is updated *after* the actor step, so the actor uses the previous
iteration's α. And the need for a ceiling at all ("to prevent entropy-driven divergence",
§5.7) is a **symptom** — with the sparse, large departure-penalty spikes of 3.3/3.4, α tuning is
being driven by reward-scale pathology. Fixing 3.3/3.4 will likely remove the need for the
ceiling, which in turn removes one of the three confounds in 2.1.

**Failure counter absent.** §5.4 and Table 5.2 describe *"after three consecutive failures the
station is frozen."* There is no counter anywhere in Listing A.1. Either it's missing from the
listing (say so) or it's missing from the code. After the 1.3 fix it should be deleted entirely.

---

## TIER 4 — The physical premise is not actually instantiated in the testbed

### 4.1 Your "strong grid" is not a strong grid — it is the same R/X feeder with an infinite bus

The thesis's core physical argument (§1.1, §2.3, Fig. 2.2) is:

> *"On a strong, transmission-like network X ≫ R and reactive power dominates voltage; on a weak
> feeder R and X are comparable, so active power becomes the dominant voltage lever."*

Fig. 2.2 puts numbers on it: distribution `R/X ≈ 2.8`, transmission `R/X ≈ 0.1`.

But the "strong" testbed (Fig. 4.3) is *the same IEEE 33-bus feeder with an infinite substation
bus* — `"same topology, different substation stiffness."` The line R/X is unchanged. And
Table 4.1 confirms the consequence:

| | mean \|∂V/∂P\| | mean \|∂V/∂Q\| | **P/Q ratio** |
|---|---|---|---|
| Weak | 4.95e-5 | 3.87e-5 | **1.28** |
| Strong | 4.11e-5 | 3.39e-5 | **1.21** |

**Both grids are active-power dominant.** The strong grid's ratio is 1.21, essentially the same
as the weak grid's 1.28. Your two arms differ in *source impedance*, not in the R/X regime the
thesis says matters. The central physical contrast is asserted in Chapters 1–2 and **never
instantiated in Chapter 4**.

This weakens (a) the motivation, (b) Gate 1, and (c) the "grid-awareness" claim, which is really
"substation-stiffness-awareness."

**Fix — one of:**
- Build the strong arm by **actually changing R/X** (scale line R down by ~5×, or X up), so
  `R/X` goes from ~2.8 to <0.5 and the strong arm becomes genuinely Q-dominant. Then Table 4.1's
  contrast is real and Gate 2 means something. This is a small change to the network builder and
  is the highest-value single experiment you can still run.
- Or rename the arms honestly ("stiff-source" vs "weak-source") and rewrite §1.1/§2.3 so the
  thesis does not promise a contrast it never tests.

### 4.2 Gate 1 is not a discriminating test

Gate 1: `ratio ≥ 0.90` on the weak grid, reported 1.271 → PASS. But the **strong** grid also
scores 1.21, so it would pass the same gate. A threshold both arms clear tests nothing.
Set the gate as a *contrast* (`ratio_weak / ratio_strong ≥ some margin`) once 4.1 is fixed.

### 4.3 Numeric inconsistency in the dominance ratio

Table 4.1 reports the weak mean ratio as **1.280**; the mean of the four per-station ratios is
**1.296**; Table 6.2 Gate 1 reports **1.271**. Three different numbers for one quantity. Pick a
definition (ratio-of-means vs mean-of-ratios), state it, and make all three agree.

### 4.4 Gate 2's reported value (80.0 kW) contradicts Table 5.3 (25.87 kW)

Table 5.3 gives `‖·‖∞ = 25.87 kW`; Fig. 5.2's title also says 25.87 kW; Table 6.2 Gate 2 reports
**80.0 kW**. §6.10 explains these are different probing states, but the thesis presents both as
"the" grid-awareness measurement. Fix the gate's feasibility guard (which is the same
infeasible-→-degenerate-value bug as Tier 1), re-run it at the *same* state as Table 5.3, and
report one number.

---

## TIER 5 — Things an examiner will notice immediately

1. **Fig. 4.5's title reads, in the submitted document:**
   `"Residential load profile — placeholder parametric model (replace before publication)"`.
   Regenerate that figure before submission. (§4.4 and §6.11 already flag the parametric model
   honestly — the fix is just the figure title.)

2. **Post-hoc reinterpretation of pre-registered gates.** §6.10 argues both failed gates
   *"actually argue for the method"* and Ch. 8 repeats it. Pre-registration's entire purpose is to
   prevent exactly this move; explaining away failures after seeing the data forfeits the
   rigour claim you make in §7.3. The honest framing: Gate 2 failed **because the gate
   implementation is buggy** (fix it and re-run — do not argue around it); Gate 4 failed
   **because the gate was mis-specified** (a single-axis safety test rewards a non-operating
   controller — say "the gate was badly designed, here is the joint-objective analysis instead",
   and do not claim the failure supports you).

3. **§6.2 misreads its own figures.** *"the SafeSAC violation curves are smoother and lower than
   the corresponding SAC-Lag curves."* Fig. 6.1: SAC-Lag (weak) **converges to ~5** violation
   steps/episode; SafeSAC (weak) sits **flat at ~28** and never improves. At convergence SafeSAC
   is 5× worse. The cumulative comparison in Fig. 6.3 favours SafeSAC only because it front-loads
   SAC-Lag's untrained exploration **and** because the budgets differ (150 vs 100 episodes) —
   comparing cumulative counts across unequal budgets is not a valid comparison. Either
   normalise per-episode or equalise the budgets (2.1).

4. **The "structural violation floor" claim is contradicted by Table 6.1** (§6.11 says all
   methods cluster at 9–12%; the table spans 0.015–0.116). Remove or restate.

5. **Uncoordinated and droop each beat SafeSAC on one headline axis** (service 0.996 vs 0.569;
   safety 0.052 vs 0.091). The Pareto framing in §6.8 is technically correct but the frontier is
   defined by two trivial heuristics, and SafeSAC's only claim to the frontier is that it is
   between them. Do not hide from this in the viva — after fixing Tier 1 and 3.3/3.4 the picture
   should change materially, and that is the honest version of the story.

6. **Reference [29]:** Gymnasium is cited as Brockman et al., *"OpenAI Gym"*, 2016. Gymnasium is
   Towers et al. (Farama Foundation). Cite the right one, or say you use `gym` 0.26-era API.

7. **Bus labelling flips conventions** between Fig. 4.2 (Baran–Wu 18/22/25/33), Table 4.1
   (internal 17/21/24/32), and Table 5.3 (mixes both). Pick one and add a footnote.

---

## What to do, in order

If you have limited time before submission, this is the priority order:

| # | Action | Cost | Impact |
|---|---|---|---|
| 1 | **Slack-reformulate the SOCP (1.3)** and re-run all weak-feeder evaluations | ~1 day | Fixes the central claim. Without this the thesis's main contribution does not function. |
| 2 | **Fix the λ units (3.1) and γ/service reward (3.3, 3.4, 3.5)**, retrain | ~2 days | Removes the mechanisms causing the degenerate drain-and-sell behaviour. |
| 3 | **Check the observation normaliser (2.5)** | ~2 hours | May invalidate or rescue your flagship cross-deployment result. Do this *before* rewriting Ch. 6.9. |
| 4 | **De-confound the ablation (2.1)** — matched hyperparameters and episode budgets | ~1 day | Without it the +0.292 headline cannot be attributed to the projection. |
| 5 | **≥5 training seeds (2.2)**, rliable-style reporting | ~5 GPU-days | Converts Chapter 6 from pseudo-replication into real inference. |
| 6 | **Add the thermal row + all-bus monitoring + SoC envelopes to the SOCP (3.6, 3.7, 3.10)** | ~half day | Makes the projection enforce what §1.4 promises. |
| 7 | **Report `q` and run the P-only ablation (3.11)** | ~half day | Tests the thesis's actual physical claim. |
| 8 | **Rebuild the "strong" arm with a genuinely different R/X (4.1)** | ~1 day | Makes the motivating physics real rather than asserted. |
| 9 | Rename AL-SAC → SAC-Lag or implement the augmentation (3.2); fix Tier 5 presentation items | ~half day | Removes misattributions. |
| 10 | Switch sensitivities to inverse-Jacobian or LinDistFlow closed form (3.9) | ~half day | 10× faster, exact, scalable, and strengthens "physics-aware". |

Items 1–4 are the ones that determine whether the thesis's claims are supported. Items 5–10 are
what turn it into publishable work.

---

## Sources consulted

- [Dalal et al., *Safe Exploration in Continuous Action Spaces* (safety layer)](https://arxiv.org/abs/1801.08757) — slack/feasibility in projection layers
- [A Survey of Safe RL and Constrained MDPs](https://arxiv.org/html/2505.17342v1) — QP-filter deadlock at constraint boundaries, slack relaxation
- [Review on Safe RL using Lyapunov and Barrier Functions](https://arxiv.org/html/2508.09128v3) — slack variables to avoid deadlock when no safe action exists
- [Stooke, Achiam & Abbeel, *PID Lagrangian Methods*](https://arxiv.org/abs/2007.03964) — multiplier driven by measured episodic cost
- [An Empirical Study of Lagrangian Methods in Safe RL](https://arxiv.org/pdf/2510.17564) — cost-critic underestimation in SAC-Lag
- [Henderson et al., *Deep RL That Matters*](https://www.emergentmind.com/papers/1709.06560) — seed variance, significance testing
- [Agarwal et al., *rliable* / Statistical Precipice](https://agarwl.github.io/rliable/) — aggregate statistics with few runs
- [Colas et al., *How Many Random Seeds?*](https://arxiv.org/pdf/1806.08295) — power analysis for DRL comparisons
- [A Generalized LinDistFlow Model for Power Flow Analysis](https://arxiv.org/pdf/2104.02118) — closed-form radial linearisation
- [Conditions for Estimation of Sensitivities of Voltage Magnitudes to Complex Power Injections](https://arxiv.org/pdf/2212.01471) — inverse-Jacobian sensitivity computation
- [Efficient Computation of Sensitivity Coefficients in Radial Distribution Networks](https://www.academia.edu/17518551/) — analytic alternatives to perturbation
