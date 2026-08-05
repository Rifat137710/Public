"""
Integration tests for :mod:`safesac_patch`.

Builds a minimal stand-in for the notebook namespace (``PFResult``,
``GridSensitivities``, ``NetworkContext``, ``CFG``) and checks that the patched
``run_pf`` and ``compute_grid_sensitivities`` reproduce the originals on the
thesis weak and strong feeders.

The torch-side patches (``patch_lagrangian``, ``patch_projection_telemetry``)
are not exercised here — they need the full training stack. Their check is the
first instrumented run.

Run:  python test_integration.py
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandapower as pp

import safesac_patch
from validate_radial_pf import build_network

CONFIG = {
    "sensitivity_perturbation_kw": 1.0,
    "ev_station_S_rated_kva": 80.0,
}


def CFG(key):
    return CONFIG[key]


@dataclass
class PFResult:
    converged: bool
    v_pu: np.ndarray
    v_angle_deg: np.ndarray
    p_load_mw_total: float
    q_load_mvar_total: float
    p_ext_mw: float
    p_loss_mw: float
    transformer_loading_pu: float


@dataclass
class GridSensitivities:
    dV_dP: np.ndarray
    dV_dQ: np.ndarray
    dL_dP: np.ndarray
    dL_dQ: np.ndarray
    v_base: np.ndarray
    L_base: float
    p_base_kw: np.ndarray
    q_base_kvar: np.ndarray
    operating_point: dict


@dataclass
class NetworkContext:
    net: Any
    config: str
    ev_station_buses: list
    ev_sgen_idx: list
    pv_buses: list = field(default_factory=list)


def reference_run_pf(nc, *, max_iter: int = 30) -> PFResult:
    """The shipped run_pf, verbatim enough for comparison."""
    try:
        pp.runpp(nc.net, algorithm="nr", numba=False, max_iteration=max_iter,
                 init="auto", enforce_q_lims=False, calculate_voltage_angles=True)
        converged = True
    except pp.LoadflowNotConverged:
        converged = False
    n_bus = len(nc.net.bus)
    if not converged:
        nan = float("nan")
        return PFResult(False, np.full(n_bus, nan), np.full(n_bus, nan),
                        nan, nan, nan, nan, nan)
    loading = 0.0
    if nc.config == "weak":
        mask = nc.net.line["name"] == "substation_thevenin"
        if mask.any():
            loading = float(
                nc.net.res_line.loc[mask, "loading_percent"].iloc[0]) / 100.0
    return PFResult(
        converged=True,
        v_pu=nc.net.res_bus["vm_pu"].to_numpy(),
        v_angle_deg=nc.net.res_bus["va_degree"].to_numpy(),
        p_load_mw_total=float(nc.net.res_load["p_mw"].sum()),
        q_load_mvar_total=float(nc.net.res_load["q_mvar"].sum()),
        p_ext_mw=float(nc.net.res_ext_grid["p_mw"].iloc[0]),
        p_loss_mw=float(nc.net.res_line["pl_mw"].sum()),
        transformer_loading_pu=loading,
    )


def make_ns() -> dict:
    return {"PFResult": PFResult, "GridSensitivities": GridSensitivities,
            "CFG": CFG, "run_pf": reference_run_pf}


def make_nc(config: str) -> NetworkContext:
    net, ev_buses, pv_buses, ev_idx, _ = build_network(config)
    return NetworkContext(net=net, config=config, ev_station_buses=ev_buses,
                          ev_sgen_idx=ev_idx, pv_buses=pv_buses)


# ---------------------------------------------------------------------------
def check_power_flow(config: str, n: int = 150, seed: int = 137710) -> dict:
    nc = make_nc(config)
    ns = make_ns()
    safesac_patch.clear_cache()
    safesac_patch.patch_power_flow(ns)
    fast = ns["run_pf"]

    base_p = nc.net.load.p_mw.to_numpy(float).copy()
    base_q = nc.net.load.q_mvar.to_numpy(float).copy()
    rng = np.random.default_rng(seed)

    err = {k: [] for k in ("v_pu", "loss", "loading", "p_ext", "angle")}
    for _ in range(n):
        sc = rng.uniform(0.3, 1.2)
        jit = rng.uniform(0.85, 1.15, base_p.size)
        nc.net.load.loc[:, "p_mw"] = base_p * sc * jit
        nc.net.load.loc[:, "q_mvar"] = base_q * sc * jit
        nc.net.sgen.loc[nc.ev_sgen_idx, "p_mw"] = rng.uniform(-0.08, 0.08, 4)
        nc.net.sgen.loc[nc.ev_sgen_idx, "q_mvar"] = rng.uniform(-0.04, 0.04, 4)

        a, b = reference_run_pf(nc), fast(nc)
        assert b.converged, "fast solver failed"
        err["v_pu"].append(np.max(np.abs(a.v_pu - b.v_pu)))
        err["angle"].append(np.max(np.abs(a.v_angle_deg - b.v_angle_deg)))
        err["loss"].append(abs(a.p_loss_mw - b.p_loss_mw))
        err["loading"].append(abs(a.transformer_loading_pu - b.transformer_loading_pu))
        err["p_ext"].append(abs(a.p_ext_mw - b.p_ext_mw))
    return {k: float(np.max(v)) for k, v in err.items()}


def check_sensitivities(config: str, load_scale: float = 0.5) -> dict:
    nc = make_nc(config)
    nc.net.load.loc[:, "p_mw"] *= load_scale
    nc.net.load.loc[:, "q_mvar"] *= load_scale

    # Reference: shipped finite difference on pandapower.
    ref_ns = make_ns()
    n_bus, n_st = len(nc.net.bus), len(nc.ev_sgen_idx)
    dV_dP = np.zeros((n_bus, n_st)); dV_dQ = np.zeros((n_bus, n_st))
    dL_dP = np.zeros(n_st); dL_dQ = np.zeros(n_st)
    pk = CONFIG["sensitivity_perturbation_kw"]; d_mw = pk / 1000.0
    for j, sg in enumerate(nc.ev_sgen_idx):
        for col, dv, dl in (("p_mw", dV_dP, dL_dP), ("q_mvar", dV_dQ, dL_dQ)):
            base = float(nc.net.sgen.at[sg, col])
            nc.net.sgen.at[sg, col] = base + d_mw; hi = reference_run_pf(nc)
            nc.net.sgen.at[sg, col] = base - d_mw; lo = reference_run_pf(nc)
            nc.net.sgen.at[sg, col] = base
            dv[:, j] = (hi.v_pu - lo.v_pu) / (2.0 * pk)
            dl[j] = (hi.transformer_loading_pu - lo.transformer_loading_pu) / (2.0 * pk)

    out = {}
    for mode in (True, False):
        ns = make_ns()
        safesac_patch.clear_cache()
        safesac_patch.patch_power_flow(ns)
        safesac_patch.patch_sensitivities(ns, analytic_dv=mode)
        sm = ns["compute_grid_sensitivities"](nc)
        key = "analytic" if mode else "fd_fast"
        rel = np.abs(sm.dV_dP - dV_dP) / np.maximum(np.abs(dV_dP), 1e-14)
        out[key] = {
            "dV_dP_abs": float(np.max(np.abs(sm.dV_dP - dV_dP))),
            "dV_dP_relmed": float(np.median(rel)),
            "dV_dQ_abs": float(np.max(np.abs(sm.dV_dQ - dV_dQ))),
            "dL_dP_abs": float(np.max(np.abs(sm.dL_dP - dL_dP))),
            "dL_dQ_abs": float(np.max(np.abs(sm.dL_dQ - dL_dQ))),
            "L_base": float(sm.L_base),
        }
    return out


def bench(config: str, n: int = 60) -> dict:
    nc = make_nc(config)
    ns = make_ns()
    safesac_patch.clear_cache()
    safesac_patch.patch_power_flow(ns)
    safesac_patch.patch_sensitivities(ns)
    fast_pf, fast_sm = ns["run_pf"], ns["compute_grid_sensitivities"]

    ref_ns = make_ns()

    fast_pf(nc); reference_run_pf(nc)
    t0 = time.perf_counter()
    for _ in range(n): fast_pf(nc)
    t_fast = (time.perf_counter() - t0) / n
    t0 = time.perf_counter()
    for _ in range(n): reference_run_pf(nc)
    t_ref = (time.perf_counter() - t0) / n
    t0 = time.perf_counter()
    for _ in range(n): fast_sm(nc)
    t_sm = (time.perf_counter() - t0) / n
    return {"pf_fast": t_fast, "pf_ref": t_ref, "sm_fast": t_sm,
            "sm_ref_est": 9 * t_ref}


def main() -> None:
    print("=" * 72)
    print("safesac_patch integration tests")
    print("=" * 72)

    for config in ("weak", "strong"):
        print(f"\n[{config}]")
        e = check_power_flow(config)
        print("  run_pf vs pandapower (150 scenarios):")
        print(f"    v_pu     max err {e['v_pu']:.3e} pu")
        print(f"    angle    max err {e['angle']:.3e} deg")
        print(f"    p_loss   max err {e['loss']:.3e} MW")
        print(f"    loading  max err {e['loading']:.3e} pu")
        print(f"    p_ext    max err {e['p_ext']:.3e} MW")
        # Thresholds are set by the *reference's* accuracy, not ours: the
        # shipped run_pf calls pp.runpp with default tolerance_mva=1e-8, so
        # ~1e-8 pu of disagreement is pandapower's own convergence slop.
        # (validate_radial_pf.py pins pandapower to 1e-10 and gets 3e-11 pu.)
        # In physical terms the worst residual below is 0.02 W of loss.
        assert e["v_pu"] < 1e-7, e
        assert e["angle"] < 1e-5, e
        assert e["loss"] < 1e-6, e
        assert e["loading"] < 1e-7, e
        assert e["p_ext"] < 1e-5, e

        s = check_sensitivities(config)
        print("  compute_grid_sensitivities vs shipped finite difference:")
        for k, v in s.items():
            print(f"    {k:9s} dV/dP max {v['dV_dP_abs']:.3e} pu/kW "
                  f"(median rel {v['dV_dP_relmed'] * 100:5.2f}%)   "
                  f"dL/dP max {v['dL_dP_abs']:.3e}")
        assert s["fd_fast"]["dV_dP_abs"] < 1e-12, s["fd_fast"]
        assert s["fd_fast"]["dL_dP_abs"] < 1e-12, s["fd_fast"]
        assert s["analytic"]["dV_dP_relmed"] < 0.10, s["analytic"]

        b = bench(config)
        print(f"  timing: run_pf {b['pf_fast'] * 1e6:8.1f} us "
              f"(was {b['pf_ref'] * 1e6:9.1f} us, {b['pf_ref'] / b['pf_fast']:6.0f}x)")
        print(f"          sensitivities {b['sm_fast'] * 1e6:8.1f} us "
              f"(was ~{b['sm_ref_est'] * 1e6:9.1f} us, "
              f"{b['sm_ref_est'] / b['sm_fast']:6.0f}x)")

    print("\nAll integration checks passed.")
    print("NOT covered here (needs torch + full training stack):")
    print("  patch_lagrangian, patch_projection_telemetry")


if __name__ == "__main__":
    main()
