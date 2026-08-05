# SafeSAC → Q1 journal

Working repository for taking the BUET EEE 400 thesis *"Safe Deep Reinforcement Learning
for Vehicle-to-Grid Voltage Support in Weak Distribution Feeders: A Physics-Aware Approach"*
(Md. Rifat Rahman, Sad Sami; supervisor Dr. Md. Forkan Uddin) to a Q1 journal submission.

## Documents

| File | Purpose |
|---|---|
| [`docs/00-knowledge-base.md`](docs/00-knowledge-base.md) | Verified ground truth: system, controller, hyperparameters, every result number, read out of the code and checkpoints rather than the prose |
| [`docs/01-audit-blocking-issues.md`](docs/01-audit-blocking-issues.md) | Pre-submission audit — the defects a Q1 reviewer will find, ranked, each with its evidence |
| [`docs/02-q1-pipeline.md`](docs/02-q1-pipeline.md) | Novelty assessment, repositioning, venue targets, and the staged plan with gates |

## Package

```
safesac/
  config.py       frozen dataclass configs + BLAKE2b seed derivation
  network.py      IEEE 33-bus weak/strong feeder construction
  powerflow.py    pandapower oracle, fast radial sweep, analytic Jacobian sensitivities
  scenario.py     load / PV / price / EV-fleet sampling
  env.py          the charging-feeder environment and reward
  projection.py   DPP-parametrised SOCP safety projection
  agents.py       zero, uncoordinated, IEEE 1547 droop
  evaluate.py     rollout, metrics, shared-seed evaluation
  learned.py      SAC-Lagrangian and SafeSAC, checkpoint-compatible
  train.py        training loop, convergence detector, fixed-budget mode
```

Run the tests with `python -m pytest tests/ -q` from the repository root (56 tests, ~2.5 min).

Reproduce the published learned results from the shipped checkpoints:

```
python scripts/reproduce_table_6_1.py --checkpoints artifacts/checkpoints
```

## Status — Stage 0 complete

**Full reproduction verified.** The port reproduces all six rows of thesis Table 6.1. This
exercises seed derivation, scenario and fleet sampling, environment dynamics, reward,
metrics, the SOCP projection, and the actor networks end to end.

| method | violation rate | SoC met | net cost | source |
|---|---|---|---|---|
| Uncoordinated | 0.1156 / **0.1156** | 0.9955 / **0.9955** | $230.7311 / **$230.7311** | published / port |
| Droop (1547) | 0.0521 / **0.0521** | 0.3245 / **0.3245** | $66.2656 / **$66.2656** | published / port |
| SAC-Lag (weak) | 0.0904 / **0.0904** | 0.2767 / 0.2752 | $104.29 / $104.52 | published / port |
| SafeSAC (weak) | 0.0912 / **0.0912** | 0.5688 / 0.5704 | $125.94 / $125.82 | published / port |
| SAC-Lag (strong→weak) | 0.0151 / **0.0151** | 0.0000 / **0.0000** | −$38.17 / **−$38.1709** | published / port |
| SafeSAC (strong→weak) | 0.1058 / **0.1058** | 0.4469 / **0.4469** | $69.66 / **$69.6595** | published / port |

Every violation rate and Vmin matches to the published precision. The two cross-deployment
rows match to six significant figures; the ≤0.25 % residual on the in-distribution rows is
float32 drift between torch 2.10/T4 and torch 2.13/CPU.

**Physics path rewritten** (Stage 2, landed early):

| operation | thesis | ported | speedup |
|---|---|---|---|
| power flow | pandapower NR, 25.75 ms | radial sweep, 0.103 ms | 249× |
| sensitivities | 8 central-difference solves, 447.6 ms | 1 LU + 8 back-substitutions, 0.662 ms | 677× |
| whole evaluation step | ~50 ms | 0.87 ms | ~57× |

The sweep matches pandapower to 5e-9 pu; the analytic sensitivities match published
Table 4.1 to five significant figures. pandapower stays in CI as the oracle.

**Two findings the reproduction establishes**, both invisible in the thesis because neither
quantity was logged:

- The safety layer is **infeasible on 12.50 % of steps** at the published operating point
  (900 of 7 200), and latches a station off on 10.42 %. Its effective lower bound of 0.960 pu
  sits below the idle feeder's 0.9441 Vmin, so near the evening peak no station command can
  satisfy it and the layer emits an all-zero command instead. Both SafeSAC checkpoints give
  identical counts — infeasibility is set by the feeder, not by the policy. (Audit A5.)
- The compared runs had **unequal training budgets**: 97 episodes for SAC-Lag (weak) against
  85 for SafeSAC (weak), and 114 against 86 cross-deployment, because training stopped on a
  convergence detector rather than a fixed budget. (Audit A6.)

**Next:** Stage 1 — correctness fixes and the fair ablation at the settled operating point
(`load_scale` 0.40, 30 EVs/station/day).
