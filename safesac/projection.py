"""Physics-aware safety projection.

Ported from `thesis11.ipynb` Block 4 §10.3. The optimisation is unchanged: an
8-variable Euclidean projection onto a linearised feasible set, written in DPP
form so CVXPY compiles it once and CLARABEL re-solves it each step.

What *is* changed is where the physics comes from. The thesis rebuilt the
voltage sensitivities by central differences -- 8 extra Newton solves, 447 ms --
and cached them for 12 steps. Here they come from one Jacobian factorisation
(0.66 ms, and exact), which makes a per-step refresh affordable and turns the
refresh cadence into an ablation axis rather than an unstated approximation.
See docs/01-audit item B3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .config import ExperimentConfig
from .network import Feeder
from .powerflow import (
    FeederTopology,
    JacobianSensitivities,
    PFResult,
    RadialPowerFlow,
    Sensitivities,
)


@dataclass
class ProjectionResult:
    p_kw: np.ndarray
    q_kvar: np.ndarray
    status: str
    frozen: np.ndarray
    all_frozen: bool
    solved: bool  # False when the feasibility pre-check let the raw action through

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class LoadingSensitivities:
    dl_dp: np.ndarray
    dl_dq: np.ndarray
    l_base: float


def compute_loading_sensitivities(
    feeder: Feeder, solver: RadialPowerFlow, perturb_kw: float = 4.0
) -> LoadingSensitivities:
    """Central differences for substation loading, using the fast solver.

    Kept as finite differences because the transformer constraint has never
    once bound in any run (max loading 0.011 pu against a 1.0 pu limit -- audit
    item C4). At 0.1 ms per solve the whole thing costs under a millisecond.
    """
    net = feeder.net
    base_p = net.sgen.loc[feeder.ev_sgen_idx, "p_mw"].to_numpy().copy()
    base_q = net.sgen.loc[feeder.ev_sgen_idx, "q_mvar"].to_numpy().copy()
    l_base = solver.solve().transformer_loading_pu

    n = len(feeder.ev_sgen_idx)
    dl_dp, dl_dq = np.zeros(n), np.zeros(n)
    delta = perturb_kw / 1000.0

    for j, sgen in enumerate(feeder.ev_sgen_idx):
        for col, base_vals, out in (("p_mw", base_p, dl_dp), ("q_mvar", base_q, dl_dq)):
            net.sgen.at[sgen, col] = base_vals[j] + delta
            plus = solver.solve().transformer_loading_pu
            net.sgen.at[sgen, col] = base_vals[j] - delta
            minus = solver.solve().transformer_loading_pu
            net.sgen.at[sgen, col] = base_vals[j]
            out[j] = (plus - minus) / (2.0 * perturb_kw)

    return LoadingSensitivities(dl_dp, dl_dq, l_base)


class SensitivityCache:
    """Refresh the physics every `refresh_steps` control steps."""

    def __init__(self, cfg: ExperimentConfig, feeder: Feeder, solver: RadialPowerFlow):
        self.cfg = cfg
        self.feeder = feeder
        self.solver = solver
        self.topo = FeederTopology(feeder)
        self._jacobian = JacobianSensitivities(feeder, self.topo)
        self.refresh_steps = cfg.safety.sensitivity_refresh_steps
        self.last_refresh = -10**9
        self.sens: Optional[Sensitivities] = None
        self.loading: Optional[LoadingSensitivities] = None
        self.n_refreshes = 0

    def maybe_refresh(self, current_step: int, pf: PFResult) -> bool:
        if self.sens is not None and (current_step - self.last_refresh) < self.refresh_steps:
            return False
        self.sens = self._jacobian.compute(pf)
        self.loading = compute_loading_sensitivities(self.feeder, self.solver)
        self.last_refresh = current_step
        self.n_refreshes += 1
        return True

    def invalidate(self) -> None:
        self.sens = None
        self.last_refresh = -10**9


class SensitivityProjector:
    """Euclidean projection onto the linearised network-feasible set."""

    def __init__(
        self,
        cfg: ExperimentConfig,
        n_stations: int,
        n_bus: int,
        enforce_loading: bool = True,
    ):
        import cvxpy as cp

        self.cfg = cfg
        self.n = int(n_stations)
        self.n_bus = int(n_bus)
        self.enforce_loading = enforce_loading
        self.consecutive_failures = np.zeros(self.n, dtype=int)
        self.frozen = np.zeros(self.n, dtype=bool)

        s = cfg.safety
        rated = cfg.feeder.ev_station_kva
        ramp = s.station_ramp_per_step_pu * rated
        v_lo = s.voltage_lower_pu + s.projection_margin_pu
        v_hi = s.voltage_upper_pu - s.projection_margin_pu

        self.P = cp.Variable(self.n, name="P_safe")
        self.Q = cp.Variable(self.n, name="Q_safe")

        self.par = {
            "p_raw": cp.Parameter(self.n),
            "q_raw": cp.Parameter(self.n),
            "p_prev": cp.Parameter(self.n),
            "q_prev": cp.Parameter(self.n),
            "v_offset": cp.Parameter(self.n_bus),
            "dv_dp": cp.Parameter((self.n_bus, self.n)),
            "dv_dq": cp.Parameter((self.n_bus, self.n)),
            "l_offset": cp.Parameter(),
            "dl_dp": cp.Parameter(self.n),
            "dl_dq": cp.Parameter(self.n),
            "frozen": cp.Parameter(self.n, nonneg=True),
        }
        p = self.par

        # Only parameter-times-variable products, so the problem stays DPP and
        # CVXPY can reuse the compiled form across solves.
        v_pred = p["v_offset"] + p["dv_dp"] @ self.P + p["dv_dq"] @ self.Q

        constraints = [
            self.P >= -rated,
            self.P <= rated,
            self.Q >= -rated,
            self.Q <= rated,
            self.P - p["p_prev"] >= -ramp,
            self.P - p["p_prev"] <= ramp,
            self.Q - p["q_prev"] >= -ramp,
            self.Q - p["q_prev"] <= ramp,
            v_pred >= v_lo,
            v_pred <= v_hi,
            cp.multiply(p["frozen"], self.P) == 0,
            cp.multiply(p["frozen"], self.Q) == 0,
        ]
        if enforce_loading:
            l_pred = p["l_offset"] + p["dl_dp"] @ self.P + p["dl_dq"] @ self.Q
            constraints.append(l_pred <= s.transformer_loading_limit_pu)
        for j in range(self.n):
            constraints.append(cp.norm(cp.hstack([self.P[j], self.Q[j]]), 2) <= rated)

        self.problem = cp.Problem(
            cp.Minimize(cp.sum_squares(self.P - p["p_raw"]) + cp.sum_squares(self.Q - p["q_raw"])),
            constraints,
        )
        assert self.problem.is_dcp(dpp=True), "projection must stay DPP for warm compilation"

    def on_refresh(self) -> None:
        self.frozen[:] = False
        self.consecutive_failures[:] = 0

    # -- feasibility pre-check (audit B2 / Stage 2 item 1) -----------------

    def _already_feasible(
        self, p_raw, q_raw, p_prev, q_prev, sens: Sensitivities, loading, tol: float = 1e-9
    ) -> bool:
        """Skip the solve when the raw command already satisfies everything.

        The thesis wrote this (Patch 4's `projection_skip_margins`) and then
        commented it out. A converged policy is feasible most steps, so this is
        the single biggest remaining saving in the control loop.
        """
        s = self.cfg.safety
        rated = self.cfg.feeder.ev_station_kva
        ramp = s.station_ramp_per_step_pu * rated

        if np.any(np.abs(p_raw) > rated + tol) or np.any(np.abs(q_raw) > rated + tol):
            return False
        if np.any(np.abs(p_raw - p_prev) > ramp + tol) or np.any(np.abs(q_raw - q_prev) > ramp + tol):
            return False
        if np.any(p_raw**2 + q_raw**2 > rated**2 + tol):
            return False

        v = (
            sens.v_base
            + sens.dv_dp @ (p_raw - sens.p_base_kw)
            + sens.dv_dq @ (q_raw - sens.q_base_kvar)
        )
        if v.min() < s.voltage_lower_pu + s.projection_margin_pu - tol:
            return False
        if v.max() > s.voltage_upper_pu - s.projection_margin_pu + tol:
            return False

        if self.enforce_loading and loading is not None:
            l_pred = (
                loading.l_base
                + loading.dl_dp @ (p_raw - sens.p_base_kw)
                + loading.dl_dq @ (q_raw - sens.q_base_kvar)
            )
            if l_pred > s.transformer_loading_limit_pu + tol:
                return False
        return True

    def project(
        self,
        p_raw,
        q_raw,
        p_prev,
        q_prev,
        sens: Sensitivities,
        loading: Optional[LoadingSensitivities] = None,
        skip_when_feasible: bool = True,
    ) -> ProjectionResult:
        import cvxpy as cp

        p_raw = np.asarray(p_raw, dtype=float)
        q_raw = np.asarray(q_raw, dtype=float)

        if (
            skip_when_feasible
            and not self.frozen.any()
            and self._already_feasible(p_raw, q_raw, p_prev, q_prev, sens, loading)
        ):
            return ProjectionResult(
                p_raw.copy(), q_raw.copy(), "ok", self.frozen.copy(), False, solved=False
            )

        par = self.par
        par["p_raw"].value = p_raw
        par["q_raw"].value = q_raw
        par["p_prev"].value = np.asarray(p_prev, dtype=float)
        par["q_prev"].value = np.asarray(q_prev, dtype=float)

        v = self._pad(sens.v_base, fill=1.0)
        dv_dp = self._pad_matrix(sens.dv_dp)
        dv_dq = self._pad_matrix(sens.dv_dq)
        par["dv_dp"].value = dv_dp
        par["dv_dq"].value = dv_dq
        # Offsets are precomputed so the linear model stays parameter-affine.
        par["v_offset"].value = v - dv_dp @ sens.p_base_kw - dv_dq @ sens.q_base_kvar

        if self.enforce_loading:
            ld = loading or LoadingSensitivities(np.zeros(self.n), np.zeros(self.n), 0.0)
            par["dl_dp"].value = ld.dl_dp
            par["dl_dq"].value = ld.dl_dq
            par["l_offset"].value = float(
                ld.l_base - ld.dl_dp @ sens.p_base_kw - ld.dl_dq @ sens.q_base_kvar
            )
        else:
            par["dl_dp"].value = np.zeros(self.n)
            par["dl_dq"].value = np.zeros(self.n)
            par["l_offset"].value = 0.0

        par["frozen"].value = self.frozen.astype(float)

        try:
            self.problem.solve(solver=cp.CLARABEL, verbose=False)
            status = str(self.problem.status)
        except Exception as exc:  # solver blow-up is a failure, not a crash
            status = f"solver_exception:{type(exc).__name__}"

        if status in ("optimal", "optimal_inaccurate"):
            self.consecutive_failures[~self.frozen] = 0
            p = np.asarray(self.P.value, dtype=float)
            q = np.asarray(self.Q.value, dtype=float)
            p[self.frozen] = 0.0
            q[self.frozen] = 0.0
            return ProjectionResult(p, q, "ok", self.frozen.copy(), False, solved=True)

        self.consecutive_failures += 1
        newly_frozen = (self.consecutive_failures >= self.cfg.safety.max_consecutive_failures) & (
            ~self.frozen
        )
        self.frozen |= newly_frozen
        return ProjectionResult(
            np.zeros(self.n),
            np.zeros(self.n),
            status,
            self.frozen.copy(),
            bool(self.frozen.all()),
            solved=True,
        )

    # -- padding, so weak (34 bus) and strong (33 bus) share one compiled problem

    def _pad(self, v, fill: float):
        if len(v) < self.n_bus:
            return np.concatenate([v, np.full(self.n_bus - len(v), fill)])
        return v[: self.n_bus]

    def _pad_matrix(self, m):
        if m.shape[0] < self.n_bus:
            return np.vstack([m, np.zeros((self.n_bus - m.shape[0], m.shape[1]))])
        return m[: self.n_bus]
