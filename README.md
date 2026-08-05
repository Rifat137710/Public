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
```

Run the tests with `python -m pytest tests/ -q` from the repository root.

## Status — Stage 0 in progress

**Reproduction verified.** The port reproduces both heuristic rows of thesis Table 6.1 to
the published precision, which exercises seed derivation, scenario and fleet sampling,
environment dynamics, reward, and metrics end to end:

| method | violation rate | SoC met | net cost |
|---|---|---|---|
| Uncoordinated — published | 0.1156 | 0.9955 | $230.7311 |
| Uncoordinated — port | 0.1156 | 0.9955 | $230.7311 |
| Droop (1547) — published | 0.0521 | 0.3245 | $66.2656 |
| Droop (1547) — port | 0.0521 | 0.3245 | $66.2656 |

**Physics path rewritten** (Stage 2, landed early):

| operation | thesis | ported | speedup |
|---|---|---|---|
| power flow | pandapower NR, 25.75 ms | radial sweep, 0.103 ms | 249× |
| sensitivities | 8 central-difference solves, 447.6 ms | 1 LU + 8 back-substitutions, 0.662 ms | 677× |
| whole evaluation step | ~50 ms | 0.87 ms | ~57× |

The sweep matches pandapower to 5e-9 pu; the analytic sensitivities match published
Table 4.1 to five significant figures. pandapower stays in CI as the oracle.

**Next:** port the learned agents and the training loop, then Stage 1.
