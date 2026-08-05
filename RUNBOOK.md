# Runbook — what to run, in what order

Everything here runs in your Kaggle/Colab notebook against the real training
stack. I cannot execute torch in this environment, so these are the steps only
you can do. Each has a pass condition; **do not proceed past a failed step.**

---

## Step 1 — Regression lock (30 min, no training)

Freeze the published numbers before anything changes.

```python
# after all definition blocks have run, BEFORE applying any patch
RESULT_BASELINE = {}
for label, grid in [("saclag_weak_v2","weak"), ("safesac_weak_v3","weak"),
                    ("saclag_strong_v2","strong"), ("safesac_strong_v3","strong")]:
    # load checkpoint, evaluate 25 shared-seed episodes exactly as Patch 7 did
    ...
# write results to results/patch7_v2_main_results.csv
```

```bash
python regression_lock.py --check results/patch7_v2_main_results.csv
```

**Pass:** `REGRESSION LOCK HELD`. This confirms your re-evaluation harness
reproduces the thesis before you change the pipeline.

---

## Step 2 — Apply patches, re-lock (1 h)

```python
import safesac_patch
safesac_patch.apply_all(globals(), d_step=0.01)
CONFIG["sensitivity_refresh_steps"] = 1     # now ~9 us, was 12 steps = 1 hour
CONFIG["projection_margin_pu"] = 0.002      # see Step 3 — was 0.010
```

Re-evaluate from the same checkpoints and re-run the lock.

**Pass:** lock holds, or deviations are explained by the margin change alone.
Run once with `safesac_patch.patch_sensitivities(ns, analytic_dv=False)` to
isolate the power-flow swap from the ~3% linearisation error.

**Also check:** wall-clock per step should drop from ~118 ms to ~2 ms. If it
doesn't, the patches didn't take — check for a stale `run_pf` reference
captured inside a closure.

---

## Step 3 — Fix the projection margin (do this before any retraining)

`phase1_controllability.py` (already run, results below) shows the 0.010 pu
margin is what makes your SOCP infeasible:

```
weak feeder, load 0.50
  tightest headroom above 0.95 at the ideal command : 4.10 milli-pu
  thesis margin                                     : 10.00 milli-pu

  margin  0-4 m-pu -> 100% of the day reachable
  margin    5 m-pu ->  97.9%
  margin   10 m-pu ->  89.6%   <- the thesis setting
```

Set `margin = 0.002`. Justification: the analytic sensitivities carry ~3%
median error, and on a 5 milli-pu excursion that is ~0.15 milli-pu — 2 milli-pu
is more than ten times the headroom needed.

**Also add slack variables** to the SOCP so it degrades smoothly instead of
freezing when it *is* infeasible (costs ~2 ms/solve; see README).

**Pass:** log `proj_infeasible_steps` over an evaluation episode. It should
drop from near-100% to near-zero.

---

## Step 4 — Gate B: projection without learning (2 h, no training)

The one result that could kill the paper. Run `phase1_ablation.py` as a
notebook cell.

```python
exec(open("phase1_ablation.py").read())
run_gate_b(globals())
```

It evaluates six controllers on the same 25 shared eval seeds:
`uncoord`, `uncoord+SOCP`, `droop`, `droop+SOCP`, and your two trained agents.

**Interpretation:**

| Outcome | Meaning |
|---|---|
| `droop+SOCP` ≈ `SafeSAC` | The projection carries the benefit, not the learning. Reframe honestly — still publishable, different claim. |
| `SafeSAC` clearly ahead | The RL adds foresight (TOU arbitrage, pre-peak charging). Show *that* explicitly. |
| `uncoord+SOCP` best on both axes | The whole control stack is unnecessary at this operating point. Change the operating point or the objective. |

---

## Step 5 — Matched-arm retrain (1 h compute)

Retrain **SAC-Lag** with SafeSAC's v3 settings so the arms differ only by the
projection:

```python
SACLAG_V3_HPARAMS = {"lr_critic": 1e-4}      # was 3e-4
CONFIG["alpha_ceiling"] = 1.0                # v2 was trained without this
N_EPISODES = 100                             # match, don't early-stop
```

**Pass:** at the end of training,

```python
assert agent.lag.health().ok, agent.lag.health()
```

If it reports `DEGENERATE`, λ is still dead — stop and diagnose, do not
proceed. If `SATURATED`, the budget is below the achievable cost; use
`LagrangeController.from_measured_floor()` with the floor measured in Step 4.

---

## Step 6 — Health report on every run

```python
from telemetry import health_report, format_report
print(format_report(label, health_report(f"logs/{label}_episodes.csv",
                                         converged_claim=state["converged"])))
```

**Pass:** no `[FAIL]` findings. Expect `LAMBDA_NOT_LOGGED` to disappear and
`NOISY_CONVERGENCE` to persist until Step 7.

---

## Step 7 — Full runs (10 h compute)

Only after Steps 1–6 pass.

- 10 training seeds × {SAC-Lag, SafeSAC} × {weak, strong} = 40 runs
- ≥250k steps each, **fixed budget** — delete the convergence detector
- Evaluate every checkpoint on the same 25 shared eval seeds
- Primary statistics across *training seeds* (n=10) with bootstrap CI; keep the
  paired 25-episode analysis as a within-seed secondary

At ~2 ms/step this is ~10 h total. Gate C is decided here.

---

## Quick reference

| Command | Runs where | Cost |
|---|---|---|
| `python validate_radial_pf.py` | anywhere | 1 min |
| `python test_lagrangian.py` | anywhere | 1 min |
| `python test_integration.py` | anywhere | 2 min |
| `python phase1_controllability.py` | anywhere | 2 min |
| `python regression_lock.py --check <csv>` | anywhere | instant |
| `run_gate_b(globals())` | notebook | ~2 h |
| Steps 5, 7 | notebook + GPU | ~11 h |
