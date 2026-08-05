"""Power flow and voltage sensitivities.

Three solvers, in increasing order of speed and decreasing order of generality:

``run_pf_reference``
    pandapower Newton-Raphson. The oracle. Used in CI to check the others and
    available as a drop-in for any experiment where speed does not matter.

``RadialPowerFlow``
    Backward-forward sweep specialised to a radial, single-voltage-level,
    shunt-free feeder. Same answer to ~1e-10 pu, roughly two orders of
    magnitude faster, because it never assembles or factorises a Jacobian.

``JacobianSensitivities``
    Analytic dV/dP and dV/dQ from one LU factorisation of the power-flow
    Jacobian at the converged point. Replaces the thesis's 8 extra Newton
    solves per refresh (central differences over 4 stations x {P, Q}) with 8
    back-substitutions -- and is exact rather than a finite-difference
    approximation.

Together these are what make the Stage 4 transfer matrix affordable; see
docs/02-q1-pipeline.md Stage 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandapower as pp

from .network import Feeder

S_BASE_MVA = 1.0  # per-unit power base; V base is the feeder's vn_kv


@dataclass
class PFResult:
    converged: bool
    v_pu: np.ndarray
    v_angle_rad: np.ndarray
    p_loss_mw: float
    p_slack_mw: float
    transformer_loading_pu: float


# --------------------------------------------------------------------------
# Reference solver
# --------------------------------------------------------------------------


def run_pf_reference(feeder: Feeder, max_iter: int = 30) -> PFResult:
    net = feeder.net
    try:
        pp.runpp(
            net,
            algorithm="nr",
            numba=False,
            max_iteration=max_iter,
            init="auto",
            enforce_q_lims=False,
            calculate_voltage_angles=True,
        )
    except pp.LoadflowNotConverged:
        n = len(net.bus)
        nan = np.full(n, np.nan)
        return PFResult(False, nan, nan, float("nan"), float("nan"), float("nan"))

    loading = 0.0
    if feeder.config.variant == "weak":
        mask = net.line["name"] == "substation_thevenin"
        if mask.any():
            loading = float(net.res_line.loc[mask, "loading_percent"].iloc[0]) / 100.0

    return PFResult(
        converged=True,
        v_pu=net.res_bus["vm_pu"].to_numpy().copy(),
        v_angle_rad=np.deg2rad(net.res_bus["va_degree"].to_numpy()),
        p_loss_mw=float(net.res_line["pl_mw"].sum()),
        p_slack_mw=float(net.res_ext_grid["p_mw"].iloc[0]),
        transformer_loading_pu=loading,
    )


# --------------------------------------------------------------------------
# Topology, shared by the fast solver and the sensitivity engine
# --------------------------------------------------------------------------


class FeederTopology:
    """Static electrical description of a radial feeder, extracted once."""

    def __init__(self, feeder: Feeder):
        net = feeder.net
        self.n_bus = len(net.bus)
        self.slack = int(net.ext_grid.bus.values[0])
        self.v_slack = float(net.ext_grid.vm_pu.iloc[0])

        lines = net.line[net.line.in_service]
        if len(net.trafo) or len(net.shunt) or len(net.impedance):
            raise NotImplementedError(
                "RadialPowerFlow supports line-only, single-voltage-level feeders"
            )
        if (lines.c_nf_per_km != 0).any():
            raise NotImplementedError("line shunt capacitance is not modelled")

        vn = float(net.bus.vn_kv.iloc[0])
        z_base = vn**2 / S_BASE_MVA

        par = lines["parallel"].to_numpy() if "parallel" in lines else np.ones(len(lines))
        r = lines.r_ohm_per_km.to_numpy() * lines.length_km.to_numpy() / par
        x = lines.x_ohm_per_km.to_numpy() * lines.length_km.to_numpy() / par

        self.edge_from = lines.from_bus.to_numpy().astype(int)
        self.edge_to = lines.to_bus.to_numpy().astype(int)
        self.edge_z = (r + 1j * x) / z_base
        self.edge_r_pu = r / z_base
        self.n_edge = len(self.edge_z)

        self._build_tree()
        self._build_ybus()

        self.thevenin_edge: Optional[int] = None
        if feeder.config.variant == "weak":
            names = lines["name"].to_numpy()
            hits = np.where(names == "substation_thevenin")[0]
            if len(hits):
                self.thevenin_edge = int(hits[0])
                # Rating used by the thesis for the "transformer loading" signal.
                i_ka = float(lines.max_i_ka.iloc[self.thevenin_edge])
                self.thevenin_rating_mva = float(np.sqrt(3) * vn * i_ka)

    def _build_tree(self):
        """Root the graph at the slack; record each bus's parent edge and depth."""
        adj = [[] for _ in range(self.n_bus)]
        for k in range(self.n_edge):
            adj[self.edge_from[k]].append((self.edge_to[k], k))
            adj[self.edge_to[k]].append((self.edge_from[k], k))

        parent_bus = np.full(self.n_bus, -1, dtype=int)
        parent_edge = np.full(self.n_bus, -1, dtype=int)
        depth = np.full(self.n_bus, -1, dtype=int)
        order = []

        depth[self.slack] = 0
        queue = [self.slack]
        while queue:
            b = queue.pop(0)
            order.append(b)
            for nb, ek in adj[b]:
                if depth[nb] < 0:
                    depth[nb] = depth[b] + 1
                    parent_bus[nb] = b
                    parent_edge[nb] = ek
                    queue.append(nb)

        if (depth < 0).any():
            raise ValueError("feeder is not connected; radial sweep needs a spanning tree")
        if self.n_edge != self.n_bus - 1:
            raise ValueError(
                f"feeder is not radial: {self.n_edge} in-service lines for {self.n_bus} buses"
            )

        self.parent_bus = parent_bus
        self.parent_edge = parent_edge
        self.depth = depth
        # Buses deepest-first, for the backward accumulation sweep.
        self.backward_order = np.array(sorted(range(self.n_bus), key=lambda b: -depth[b]))
        self.backward_order = self.backward_order[self.backward_order != self.slack]
        # Buses shallowest-first, for the forward voltage sweep.
        self.forward_order = np.array([b for b in order if b != self.slack])

        # Orientation of each edge relative to the tree: current flows
        # parent -> child, so a "downstream" current is positive when the
        # edge's `to_bus` is the child.
        self.edge_child = np.empty(self.n_edge, dtype=int)
        for b in range(self.n_bus):
            if self.parent_edge[b] >= 0:
                self.edge_child[self.parent_edge[b]] = b

    def _build_ybus(self):
        y = 1.0 / self.edge_z
        Y = np.zeros((self.n_bus, self.n_bus), dtype=complex)
        for k in range(self.n_edge):
            i, j = self.edge_from[k], self.edge_to[k]
            Y[i, i] += y[k]
            Y[j, j] += y[k]
            Y[i, j] -= y[k]
            Y[j, i] -= y[k]
        self.ybus = Y
        self.non_slack = np.array([b for b in range(self.n_bus) if b != self.slack])


# --------------------------------------------------------------------------
# Fast radial solver
# --------------------------------------------------------------------------


class RadialPowerFlow:
    """Backward-forward sweep. Topology is cached; only injections change."""

    def __init__(self, feeder: Feeder, tol: float = 1e-10, max_iter: int = 100):
        self.feeder = feeder
        self.topo = FeederTopology(feeder)
        self.tol = tol
        self.max_iter = max_iter
        self._v = np.full(self.topo.n_bus, self.topo.v_slack, dtype=complex)

    def bus_injections_mva(self) -> np.ndarray:
        """Net complex power *drawn* at each bus (load minus generation), MVA."""
        net = self.feeder.net
        s = np.zeros(self.topo.n_bus, dtype=complex)
        if len(net.load):
            np.add.at(
                s,
                net.load.bus.to_numpy().astype(int),
                net.load.p_mw.to_numpy() + 1j * net.load.q_mvar.to_numpy(),
            )
        if len(net.sgen):
            np.subtract.at(
                s,
                net.sgen.bus.to_numpy().astype(int),
                net.sgen.p_mw.to_numpy() + 1j * net.sgen.q_mvar.to_numpy(),
            )
        return s

    def solve(self, warm_start: bool = True) -> PFResult:
        t = self.topo
        s_pu = self.bus_injections_mva() / S_BASE_MVA

        v = self._v if warm_start else np.full(t.n_bus, t.v_slack, dtype=complex)
        v = v.copy()
        v[t.slack] = t.v_slack

        i_edge = np.zeros(t.n_edge, dtype=complex)
        converged = False

        for _ in range(self.max_iter):
            v_prev = v.copy()

            # Backward: current drawn at each bus, accumulated toward the root.
            i_bus = np.conj(s_pu / v)
            i_bus[t.slack] = 0.0
            i_acc = i_bus.copy()
            for b in t.backward_order:
                k = t.parent_edge[b]
                i_edge[k] = i_acc[b]
                i_acc[t.parent_bus[b]] += i_acc[b]

            # Forward: propagate voltage drops away from the root.
            for b in t.forward_order:
                k = t.parent_edge[b]
                v[b] = v[t.parent_bus[b]] - t.edge_z[k] * i_edge[k]

            if np.max(np.abs(v - v_prev)) < self.tol:
                converged = True
                break

        self._v = v

        loss_pu = float(np.sum(np.abs(i_edge) ** 2 * t.edge_r_pu))
        s_slack = v[t.slack] * np.conj(i_acc[t.slack]) if t.n_edge else 0.0

        loading = 0.0
        if t.thevenin_edge is not None:
            k = t.thevenin_edge
            s_branch = np.abs(v[t.edge_child[k]] * np.conj(i_edge[k])) * S_BASE_MVA
            loading = float(s_branch / t.thevenin_rating_mva)

        return PFResult(
            converged=converged,
            v_pu=np.abs(v),
            v_angle_rad=np.angle(v),
            p_loss_mw=loss_pu * S_BASE_MVA,
            p_slack_mw=float(np.real(s_slack)) * S_BASE_MVA,
            transformer_loading_pu=loading,
        )


# --------------------------------------------------------------------------
# Analytic sensitivities
# --------------------------------------------------------------------------


@dataclass
class Sensitivities:
    """dV/dP and dV/dQ in pu per kW, shape (n_bus, n_station)."""

    dv_dp: np.ndarray
    dv_dq: np.ndarray
    v_base: np.ndarray
    p_base_kw: np.ndarray
    q_base_kvar: np.ndarray


class JacobianSensitivities:
    """Exact voltage sensitivities from the power-flow Jacobian.

    ``J [dtheta; dV] = [dP; dQ]`` at the converged operating point. One LU
    factorisation serves every station and both injection types, so the cost is
    one factorisation plus ``2 * n_station`` back-substitutions instead of
    ``4 * n_station`` full Newton solves.
    """

    def __init__(self, feeder: Feeder, topo: Optional[FeederTopology] = None):
        self.feeder = feeder
        self.topo = topo or FeederTopology(feeder)

    def _jacobian(self, v_mag: np.ndarray, theta: np.ndarray) -> np.ndarray:
        t = self.topo
        G, B = t.ybus.real, t.ybus.imag
        n = t.n_bus

        dth = theta[:, None] - theta[None, :]
        cos, sin = np.cos(dth), np.sin(dth)
        vv = v_mag[:, None] * v_mag[None, :]

        # Net injections implied by the operating point.
        p = v_mag * ((v_mag[None, :] * (G * cos + B * sin)).sum(axis=1))
        q = v_mag * ((v_mag[None, :] * (G * sin - B * cos)).sum(axis=1))

        dp_dth = vv * (G * sin - B * cos)
        dp_dv = v_mag[:, None] * (G * cos + B * sin)
        dq_dth = -vv * (G * cos + B * sin)
        dq_dv = v_mag[:, None] * (G * sin - B * cos)

        diag = np.arange(n)
        dp_dth[diag, diag] = -q - B[diag, diag] * v_mag**2
        dp_dv[diag, diag] = p / v_mag + G[diag, diag] * v_mag
        dq_dth[diag, diag] = p - G[diag, diag] * v_mag**2
        dq_dv[diag, diag] = q / v_mag - B[diag, diag] * v_mag

        ns = t.non_slack
        return np.block(
            [
                [dp_dth[np.ix_(ns, ns)], dp_dv[np.ix_(ns, ns)]],
                [dq_dth[np.ix_(ns, ns)], dq_dv[np.ix_(ns, ns)]],
            ]
        )

    def compute(self, pf: PFResult) -> Sensitivities:
        from scipy.linalg import lu_factor, lu_solve

        t = self.topo
        ns = t.non_slack
        m = len(ns)
        pos = {b: i for i, b in enumerate(ns)}

        lu = lu_factor(self._jacobian(pf.v_pu, pf.v_angle_rad))

        stations = self.feeder.ev_buses
        dv_dp = np.zeros((t.n_bus, len(stations)))
        dv_dq = np.zeros((t.n_bus, len(stations)))

        # One unit-injection right-hand side per station per injection type.
        # 1 kW = 1e-3 MW = 1e-3 / S_BASE_MVA per unit.
        scale = 1e-3 / S_BASE_MVA
        for j, bus in enumerate(stations):
            row = pos[bus]
            for block, out in ((0, dv_dp), (m, dv_dq)):
                rhs = np.zeros(2 * m)
                rhs[block + row] = scale
                out[ns, j] = lu_solve(lu, rhs)[m:]

        sgen = self.feeder.net.sgen
        return Sensitivities(
            dv_dp=dv_dp,
            dv_dq=dv_dq,
            v_base=pf.v_pu.copy(),
            p_base_kw=sgen.loc[self.feeder.ev_sgen_idx, "p_mw"].to_numpy() * 1000.0,
            q_base_kvar=sgen.loc[self.feeder.ev_sgen_idx, "q_mvar"].to_numpy() * 1000.0,
        )


def finite_difference_sensitivities(feeder: Feeder, perturb_kw: float = 4.0) -> Sensitivities:
    """The thesis's central-difference estimator. Kept as the CI reference."""
    net = feeder.net
    base_p = net.sgen.loc[feeder.ev_sgen_idx, "p_mw"].to_numpy().copy()
    base_q = net.sgen.loc[feeder.ev_sgen_idx, "q_mvar"].to_numpy().copy()

    base = run_pf_reference(feeder)
    if not base.converged:
        raise RuntimeError("base power flow did not converge")

    n_bus, n_st = len(net.bus), len(feeder.ev_sgen_idx)
    dv_dp = np.zeros((n_bus, n_st))
    dv_dq = np.zeros((n_bus, n_st))
    delta = perturb_kw / 1000.0

    for j, sgen in enumerate(feeder.ev_sgen_idx):
        for col, out in (("p_mw", dv_dp), ("q_mvar", dv_dq)):
            base_val = base_p[j] if col == "p_mw" else base_q[j]
            net.sgen.at[sgen, col] = base_val + delta
            plus = run_pf_reference(feeder)
            net.sgen.at[sgen, col] = base_val - delta
            minus = run_pf_reference(feeder)
            net.sgen.at[sgen, col] = base_val
            if not (plus.converged and minus.converged):
                raise RuntimeError(f"finite-difference column {col}/{j} failed")
            out[:, j] = (plus.v_pu - minus.v_pu) / (2.0 * perturb_kw)

    return Sensitivities(dv_dp, dv_dq, base.v_pu.copy(), base_p * 1000.0, base_q * 1000.0)
