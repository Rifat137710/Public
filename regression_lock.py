"""
Phase 0.1 — regression lock.

Freezes the thesis results as they were produced, so any pipeline change can be
checked against them before it is trusted. ``golden/`` holds the two tables the
thesis reports numerically:

* ``patch7_v2_main_results.csv``  — Table 6.1 (six controllers x 25 episodes)
* ``projection_validation.csv``   — Table 5.3 (the -80 kW projection probe)

Order of operations matters. Re-evaluate from the *existing* checkpoints with
the patches applied and compare against golden **before** retraining anything:

    python regression_lock.py --check results/patch7_v2_main_results.csv

A pass means the faster power flow and analytic sensitivities did not move the
published numbers, so any later change in results is attributable to the
retraining rather than to the swap.

Expect small, explainable movement rather than bit-equality:

* the analytic sensitivity kernel carries ~3% median linearisation error
  against the shipped finite difference, which shifts the projection slightly;
* run with ``--fd`` (``patch_sensitivities(analytic_dv=False)``) for a
  machine-exact comparison that isolates the power-flow swap alone.

Tolerances below are deliberately loose on service/economic metrics and tight
on safety metrics, because the safety metrics are the ones a silent regression
would hide.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent / "golden"

# metric -> (absolute tolerance, relative tolerance)
TOLERANCES = {
    "viol_rate_mean": (0.005, 0.10),
    "vmin_pu_mean": (0.002, 0.01),
    "soc_met_mean": (0.05, 0.15),
    "net_cost_usd_mean": (5.0, 0.15),
    "total_reward_mean": (50.0, 0.20),
    "v2g_util_rate_mean": (0.02, 0.20),
    "throughput_kwh_mean": (100.0, 0.15),
}
KEY = "method"


def _load(path: Path) -> dict[str, dict[str, str]]:
    with path.open() as fh:
        return {r[KEY]: r for r in csv.DictReader(fh)}


def compare(golden_path: Path, candidate_path: Path) -> list[str]:
    """Return a list of failure strings; empty means the lock holds."""
    golden = _load(golden_path)
    cand = _load(candidate_path)
    failures: list[str] = []

    missing = set(golden) - set(cand)
    if missing:
        failures.append(f"missing methods: {sorted(missing)}")

    for method, g in golden.items():
        c = cand.get(method)
        if c is None:
            continue
        for metric, (atol, rtol) in TOLERANCES.items():
            if metric not in g or metric not in c:
                continue
            try:
                gv, cv = float(g[metric]), float(c[metric])
            except (TypeError, ValueError):
                continue
            diff = abs(cv - gv)
            if diff > atol + rtol * abs(gv):
                failures.append(
                    f"{method}.{metric}: golden {gv:.6g} -> candidate {cv:.6g} "
                    f"(delta {diff:.3g}, allowed {atol + rtol * abs(gv):.3g})")
    return failures


def summarise(golden_path: Path, candidate_path: Path) -> str:
    golden, cand = _load(golden_path), _load(candidate_path)
    lines = [f"{'method':<28} {'viol_rate':>20} {'soc_met':>20}"]
    for m, g in golden.items():
        c = cand.get(m, {})
        def cell(k):
            if k not in g:
                return " " * 20
            gv = float(g[k])
            if k not in c:
                return f"{gv:>9.4f} ->     n/a"
            return f"{gv:>9.4f} -> {float(c[k]):>7.4f}"
        lines.append(f"{m:<28} {cell('viol_rate_mean')} {cell('soc_met_mean')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", type=Path, required=True,
                    help="candidate main-results CSV to compare against golden")
    ap.add_argument("--golden", type=Path,
                    default=GOLDEN_DIR / "patch7_v2_main_results.csv")
    args = ap.parse_args()

    if not args.golden.exists():
        print(f"golden file missing: {args.golden}", file=sys.stderr)
        return 2
    if not args.check.exists():
        print(f"candidate file missing: {args.check}", file=sys.stderr)
        return 2

    print(summarise(args.golden, args.check))
    print()

    failures = compare(args.golden, args.check)
    if failures:
        print(f"REGRESSION LOCK FAILED ({len(failures)} deviations)")
        for f in failures:
            print(f"  {f}")
        print("\nIf this is expected (e.g. you changed the operating point),")
        print("record why, then re-baseline deliberately — do not widen the")
        print("tolerances to make it pass.")
        return 1

    print("REGRESSION LOCK HELD — the pipeline swap did not move the "
          "published numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
