"""
Per-episode training telemetry and a post-hoc health report.

The multiplier defect in the shipped SafeSAC runs (``lambda = 0.0`` in both
SAC-Lag checkpoints, ~17.3 in both SafeSAC ones) went unnoticed for one
reason: the episode log recorded reward, violations, PF failures and step time,
but never ``lambda``. There was nothing to look at.

:class:`EpisodeTelemetry` records the quantities needed to catch that class of
failure, and :func:`health_report` turns a finished run's CSV into a list of
explicit findings. The report is deliberately usable on the *old* logs too — it
reports missing columns as findings rather than crashing, so it doubles as a
regression check against the existing artifacts.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

__all__ = ["EpisodeTelemetry", "Finding", "health_report", "format_report"]

# Columns written per episode. Everything after `timestamp` is new relative to
# the thesis logs.
COLUMNS = [
    "episode_idx", "seed", "total_reward", "n_steps",
    "n_violation_steps", "pf_failures", "mean_step_ms", "timestamp",
    # constraint machinery
    "lam", "alpha", "mean_qc", "mean_cost_excess", "cost_sum", "d_return",
    # projection
    "proj_active_frac", "proj_clip_mean_kw",
    "proj_infeasible_steps", "proj_exception_steps", "proj_frozen_steps",
    # outcome
    "vmin_pu", "worst_bus",
]


@dataclass
class EpisodeTelemetry:
    """Accumulates per-step diagnostics into one episode row.

    Usage inside the training loop::

        tel = EpisodeTelemetry(episode_idx=ep, seed=seed, d_return=ctrl.d_return)
        for t in range(n_steps):
            ...
            tel.step(cost=info["constraint_cost"],
                     vm_pu=info["vm_pu"],
                     step_ms=dt_ms,
                     pf_converged=info["pf_converged"],
                     proj_delta_kw=agent.last_projection_delta_kw,
                     proj_infeasible=agent.last_projection_infeasible,
                     proj_exception=agent.last_projection_exception,
                     proj_frozen=agent.last_projection_frozen)
        tel.finish(total_reward=R, lam=ctrl.lam, alpha=agent.alpha,
                   mean_qc=qc_mean, d_return=ctrl.d_return)
        writer.writerow(tel.row())
    """

    episode_idx: int
    seed: int
    d_return: float = float("nan")

    n_steps: int = 0
    n_violation_steps: int = 0
    pf_failures: int = 0
    cost_sum: float = 0.0
    _step_ms: list = field(default_factory=list, repr=False)
    _vmin: float = float("inf")
    _worst_bus: int = -1

    proj_active_steps: int = 0
    proj_clip_kw_sum: float = 0.0
    proj_infeasible_steps: int = 0
    proj_exception_steps: int = 0
    proj_frozen_steps: int = 0

    total_reward: float = 0.0
    lam: float = float("nan")
    alpha: float = float("nan")
    mean_qc: float = float("nan")
    mean_cost_excess: float = float("nan")

    def step(
        self,
        *,
        cost: float,
        vm_pu: Optional[np.ndarray] = None,
        step_ms: float = 0.0,
        pf_converged: bool = True,
        proj_delta_kw: float = 0.0,
        proj_infeasible: bool = False,
        proj_exception: bool = False,
        proj_frozen: bool = False,
        violation_tol: float = 1e-4,
    ) -> None:
        self.n_steps += 1
        self.cost_sum += float(cost)
        if cost > violation_tol:
            self.n_violation_steps += 1
        if not pf_converged:
            self.pf_failures += 1
        self._step_ms.append(float(step_ms))

        if vm_pu is not None:
            vm = np.asarray(vm_pu, float)
            i = int(np.argmin(vm))
            if vm[i] < self._vmin:
                self._vmin, self._worst_bus = float(vm[i]), i

        if proj_delta_kw > 1e-6:
            self.proj_active_steps += 1
            self.proj_clip_kw_sum += float(proj_delta_kw)
        self.proj_infeasible_steps += int(proj_infeasible)
        self.proj_exception_steps += int(proj_exception)
        self.proj_frozen_steps += int(proj_frozen)

    def finish(self, *, total_reward: float, lam: float, alpha: float,
               mean_qc: float, d_return: Optional[float] = None) -> None:
        self.total_reward = float(total_reward)
        self.lam = float(lam)
        self.alpha = float(alpha)
        self.mean_qc = float(mean_qc)
        if d_return is not None:
            self.d_return = float(d_return)
        self.mean_cost_excess = self.mean_qc - self.d_return

    def row(self) -> dict:
        n = max(1, self.n_steps)
        return {
            "episode_idx": self.episode_idx,
            "seed": self.seed,
            "total_reward": self.total_reward,
            "n_steps": self.n_steps,
            "n_violation_steps": self.n_violation_steps,
            "pf_failures": self.pf_failures,
            "mean_step_ms": float(np.mean(self._step_ms)) if self._step_ms else 0.0,
            "timestamp": "",
            "lam": self.lam,
            "alpha": self.alpha,
            "mean_qc": self.mean_qc,
            "mean_cost_excess": self.mean_cost_excess,
            "cost_sum": self.cost_sum,
            "d_return": self.d_return,
            "proj_active_frac": self.proj_active_steps / n,
            "proj_clip_mean_kw": (self.proj_clip_kw_sum / self.proj_active_steps
                                  if self.proj_active_steps else 0.0),
            "proj_infeasible_steps": self.proj_infeasible_steps,
            "proj_exception_steps": self.proj_exception_steps,
            "proj_frozen_steps": self.proj_frozen_steps,
            "vmin_pu": self._vmin if math.isfinite(self._vmin) else float("nan"),
            "worst_bus": self._worst_bus,
        }


# ---------------------------------------------------------------------------
@dataclass
class Finding:
    severity: str      # "FAIL" | "WARN" | "INFO"
    code: str
    detail: str


def _col(rows: list[dict], name: str) -> Optional[np.ndarray]:
    if not rows or name not in rows[0]:
        return None
    out = []
    for r in rows:
        try:
            out.append(float(r[name]))
        except (TypeError, ValueError):
            out.append(np.nan)
    return np.asarray(out, float)


def health_report(csv_path: str | Path, *, converged_claim: Optional[bool] = None
                  ) -> list[Finding]:
    """Analyse a finished training run's episode log.

    Works on the thesis-era logs (which lack the constraint columns) — the
    missing columns become findings in their own right.
    """
    path = Path(csv_path)
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    findings: list[Finding] = []

    if not rows:
        return [Finding("FAIL", "EMPTY_LOG", f"{path.name} has no episodes")]

    n_ep = len(rows)
    steps = _col(rows, "n_steps")
    total_steps = int(np.nansum(steps)) if steps is not None else 0
    findings.append(Finding(
        "INFO", "BUDGET",
        f"{n_ep} episodes, {total_steps} environment steps"))

    # -- 1. was the constraint ever active? --------------------------------
    lam = _col(rows, "lam")
    if lam is None:
        findings.append(Finding(
            "FAIL", "LAMBDA_NOT_LOGGED",
            "no 'lam' column: it is impossible to verify from this log that the "
            "CMDP constraint was ever active. This is exactly how the shipped "
            "SAC-Lag runs hid lambda = 0.0."))
    else:
        excess = _col(rows, "mean_cost_excess")
        over = excess is not None and np.nanmean(excess) > 0
        if np.nanmax(lam) <= 0.0:
            findings.append(Finding(
                "FAIL", "LAMBDA_DEGENERATE",
                f"lambda never left 0 across {n_ep} episodes"
                + (" while mean cost exceeded the budget" if over else "")
                + ": the constraint term contributed nothing to the actor loss."))
        elif lam[-1] <= 0.0 and over:
            findings.append(Finding(
                "WARN", "LAMBDA_COLLAPSED",
                f"lambda ended at 0 with mean cost excess "
                f"{np.nanmean(excess):+.4g}"))
        else:
            findings.append(Finding(
                "INFO", "LAMBDA_OK",
                f"lambda: start {lam[0]:.4g}, peak {np.nanmax(lam):.4g}, "
                f"final {lam[-1]:.4g}"))

    # -- 2. training budget -------------------------------------------------
    if total_steps and total_steps < 100_000:
        findings.append(Finding(
            "WARN", "UNDER_TRAINED",
            f"{total_steps} steps is well short of the 1e5-1e6 typical for SAC "
            f"at this observation/action dimensionality"))

    # -- 3. spurious convergence -------------------------------------------
    rew = _col(rows, "total_reward")
    if rew is not None and n_ep >= 20:
        tail = rew[-20:]
        cv = float(np.nanstd(tail) / max(abs(np.nanmean(tail)), 1e-9))
        if cv > 0.15:
            sev = "FAIL" if converged_claim else "WARN"
            findings.append(Finding(
                sev, "NOISY_CONVERGENCE",
                f"last-20-episode reward CV = {cv * 100:.0f}%"
                + ("; a 'converged' flag on a signal this noisy is not "
                   "meaningful" if converged_claim else "")))

    # -- 4. structural violation floor -------------------------------------
    viol = _col(rows, "n_violation_steps")
    if viol is not None and n_ep >= 5:
        tail = viol[-5:]
        if np.all(tail == tail[0]) and tail[0] > 0:
            findings.append(Finding(
                "WARN", "VIOLATION_FLOOR",
                f"last 5 episodes all had exactly {int(tail[0])} violation "
                f"steps despite different scenario seeds: these violations are "
                f"structural (background load), not policy-driven"))

    # -- 5. safety-layer integrity -----------------------------------------
    exc = _col(rows, "proj_exception_steps")
    if exc is not None and np.nansum(exc) > 0:
        findings.append(Finding(
            "FAIL", "PROJECTION_BYPASSED",
            f"{int(np.nansum(exc))} steps ran with the safety projection "
            f"silently disabled by an exception"))
    infeas = _col(rows, "proj_infeasible_steps")
    if infeas is not None and steps is not None:
        frac = float(np.nansum(infeas) / max(1.0, np.nansum(steps)))
        if frac > 0.5:
            findings.append(Finding(
                "WARN", "PROJECTION_INFEASIBLE",
                f"the SOCP was infeasible on {frac * 100:.0f}% of steps; the "
                f"projection is running in its fallback, not its designed "
                f"regime. Check the operating point against the feasibility "
                f"boundary, or add slack variables."))

    pf = _col(rows, "pf_failures")
    if pf is not None and np.nansum(pf) > 0:
        findings.append(Finding(
            "WARN", "PF_FAILURES",
            f"{int(np.nansum(pf))} power-flow failures"))

    return findings


def format_report(name: str, findings: Iterable[Finding]) -> str:
    order = {"FAIL": 0, "WARN": 1, "INFO": 2}
    fs = sorted(findings, key=lambda f: order.get(f.severity, 3))
    lines = [f"--- {name} ---"]
    for f in fs:
        lines.append(f"  [{f.severity:4s}] {f.code}: {f.detail}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import sys
    for p in sys.argv[1:]:
        print(format_report(Path(p).name, health_report(p)))
        print()
