"""
Validation harness for :mod:`radial_pf`.

Checks the fast radial solver and the analytic sensitivities against
pandapower on the exact weak/strong feeders used in the SafeSAC thesis, then
benchmarks both.

Run:  python validate_radial_pf.py
"""

from __future__ import annotations

import math
import time

import numpy as np
import pandapower as pp
import pandapower.networks as ppn

from radial_pf import (
    RadialPowerFlow,
    build_topology,
    injections_from_pandapower,
)

# --- thesis constants (Block 1 of the notebook) ----------------------------
BASE_KV_MV = 12.66
BASE_MVA = 10.0
WEAK_SUBSTATION_ZBASE_PCT = 6.0
WEAK_SUBSTATION_RX_RATIO = 2.0
EV_STATION_NODES = [18, 22, 25, 33]
PV_NODES = [6, 13, 30]
EV_STATION_S_RATED_KVA = 80.0
PV_RATED_KW = [100.0, 100.0, 100.0]

S_BASE_MVA = 1.0  # per-unit base for the fast solver


def _resolve_bus_index(net, node_number: int) -> int:
    """Mirror of the thesis notebook's bus-name resolver."""
    for idx, row in net.bus.iterrows():
        if str(row.get("name", "")).endswith(str(node_number)):
            return int(idx)
        if int(idx) + 1 == node_number:
            return int(idx)
    return int(node_number - 1)


def build_network(config: str = "weak"):
    """Reconstruction of the thesis `build_network`."""
    if config not in ("weak", "strong"):
        raise ValueError(config)
    net = ppn.case33bw()
    slack_bus = int(net.ext_grid.bus.values[0])

    if config == "weak":
        base_z_ohm = (BASE_KV_MV**2) / BASE_MVA
        z_ohm = (WEAK_SUBSTATION_ZBASE_PCT / 100.0) * base_z_ohm
        rx = WEAK_SUBSTATION_RX_RATIO
        x_ohm = z_ohm / math.sqrt(1.0 + rx * rx)
        r_ohm = rx * x_ohm
        upstream = pp.create_bus(net, vn_kv=BASE_KV_MV, name="transmission_thevenin", type="b")
        net.ext_grid.at[0, "bus"] = upstream
        pp.create_line_from_parameters(
            net, from_bus=upstream, to_bus=slack_bus, length_km=1.0,
            r_ohm_per_km=r_ohm, x_ohm_per_km=x_ohm,
            c_nf_per_km=0.0, max_i_ka=10.0, name="substation_thevenin",
        )

    ev_buses = [_resolve_bus_index(net, n) for n in EV_STATION_NODES]
    pv_buses = [_resolve_bus_index(net, n) for n in PV_NODES]

    ev_sgen_idx = [
        int(pp.create_sgen(net, bus=b, p_mw=0.0, q_mvar=0.0,
                           sn_mva=EV_STATION_S_RATED_KVA / 1000.0,
                           name=f"ev_station_bus{b}", controllable=False))
        for b in ev_buses
    ]
    pv_sgen_idx = [
        int(pp.create_sgen(net, bus=b, p_mw=0.0, q_mvar=0.0, sn_mva=kw / 1000.0,
                           name=f"pv_bus{b}", controllable=False))
        for b, kw in zip(pv_buses, PV_RATED_KW)
    ]
    return net, ev_buses, pv_buses, ev_sgen_idx, pv_sgen_idx


# ---------------------------------------------------------------------------
def _pp_solve(net):
    pp.runpp(net, numba=False, tolerance_mva=1e-10, max_iteration=50)
    return net.res_bus.vm_pu.to_numpy(float).copy()


def check_voltages(config: str, n_scenarios: int = 200, seed: int = 137710):
    """Compare fast-solver voltages against pandapower over random scenarios."""
    net, ev_buses, pv_buses, ev_idx, pv_idx = build_network(config)
    topo = build_topology(net, s_base_mva=S_BASE_MVA)
    solver = RadialPowerFlow(topo, v_slack=complex(net.ext_grid.vm_pu.iloc[0], 0.0))

    base_p = net.load.p_mw.to_numpy(float).copy()
    base_q = net.load.q_mvar.to_numpy(float).copy()
    rng = np.random.default_rng(seed)

    errs, iters = [], []
    for _ in range(n_scenarios):
        scale = rng.uniform(0.3, 1.2)
        jitter = rng.uniform(0.85, 1.15, size=base_p.size)
        net.load.loc[:, "p_mw"] = base_p * scale * jitter
        net.load.loc[:, "q_mvar"] = base_q * scale * jitter
        # EV stations anywhere in [-80, +80] kW with reactive support
        net.sgen.loc[ev_idx, "p_mw"] = rng.uniform(-0.08, 0.08, len(ev_idx))
        net.sgen.loc[ev_idx, "q_mvar"] = rng.uniform(-0.04, 0.04, len(ev_idx))
        net.sgen.loc[pv_idx, "p_mw"] = rng.uniform(0.0, 0.10, len(pv_idx))

        vm_pp = _pp_solve(net)
        p, q = injections_from_pandapower(net, topo.n_bus, S_BASE_MVA)
        res = solver.solve(p, q, tol=1e-12, max_iter=100)
        assert res.converged, "fast solver failed to converge"
        errs.append(np.max(np.abs(res.vm_pu - vm_pp)))
        iters.append(res.iterations)

    return np.array(errs), np.array(iters)


def check_sensitivities(config: str, delta_kw: float = 1.0, load_scale: float = 0.5,
                        seed: int = 137710):
    """Compare analytic sensitivities against pandapower finite differences."""
    net, ev_buses, pv_buses, ev_idx, pv_idx = build_network(config)
    topo = build_topology(net, s_base_mva=S_BASE_MVA)
    solver = RadialPowerFlow(topo, v_slack=complex(net.ext_grid.vm_pu.iloc[0], 0.0))

    net.load.loc[:, "p_mw"] = net.load.p_mw.to_numpy(float) * load_scale
    net.load.loc[:, "q_mvar"] = net.load.q_mvar.to_numpy(float) * load_scale

    vm0 = _pp_solve(net)
    p0, q0 = injections_from_pandapower(net, topo.n_bus, S_BASE_MVA)
    solver.solve(p0, q0, tol=1e-12, max_iter=100)

    d_mw = delta_kw / 1000.0
    fd_p = np.zeros((topo.n_bus, len(ev_idx)))
    fd_q = np.zeros((topo.n_bus, len(ev_idx)))
    for k, sg in enumerate(ev_idx):
        for tgt, store in (("p_mw", fd_p), ("q_mvar", fd_q)):
            orig = float(net.sgen.at[sg, tgt])
            net.sgen.at[sg, tgt] = orig + d_mw
            vp = _pp_solve(net)
            net.sgen.at[sg, tgt] = orig - d_mw
            vm = _pp_solve(net)
            net.sgen.at[sg, tgt] = orig
            store[:, k] = (vp - vm) / (2.0 * d_mw)  # pu per MW
    _pp_solve(net)

    an_p, an_q = solver.sensitivities(buses=ev_buses)  # pu per pu on S_BASE
    an_p = an_p / S_BASE_MVA
    an_q = an_q / S_BASE_MVA

    return {
        "ev_buses": ev_buses,
        "fd_p": fd_p, "fd_q": fd_q,
        "an_p": an_p, "an_q": an_q,
        "vm0": vm0,
    }


def benchmark(config: str = "weak", n: int = 300):
    net, ev_buses, pv_buses, ev_idx, pv_idx = build_network(config)
    topo = build_topology(net, s_base_mva=S_BASE_MVA)
    solver = RadialPowerFlow(topo, v_slack=complex(net.ext_grid.vm_pu.iloc[0], 0.0))
    p, q = injections_from_pandapower(net, topo.n_bus, S_BASE_MVA)

    solver.solve(p, q)  # warm
    t0 = time.perf_counter()
    for _ in range(n):
        solver.solve(p, q, tol=1e-10)
    t_fast = (time.perf_counter() - t0) / n

    pp.runpp(net, numba=False)  # warm
    t0 = time.perf_counter()
    for _ in range(n):
        pp.runpp(net, numba=False)
    t_pp = (time.perf_counter() - t0) / n

    # analytic sensitivities (all four stations, every bus)
    t0 = time.perf_counter()
    for _ in range(n):
        solver.sensitivities(buses=ev_buses)
    t_sens = (time.perf_counter() - t0) / n

    return t_fast, t_pp, t_sens


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 72)
    print("radial_pf validation  —  SafeSAC weak/strong feeders")
    print("=" * 72)

    for config in ("weak", "strong"):
        net, ev_buses, *_ = build_network(config)
        topo = build_topology(net, s_base_mva=S_BASE_MVA)
        print(f"\n[{config}] buses={topo.n_bus} slack={topo.slack} "
              f"EV buses={ev_buses} z_base={topo.z_base_ohm:.4f} ohm")

        errs, iters = check_voltages(config, n_scenarios=200)
        print(f"  voltage vs pandapower  : max={errs.max():.3e} pu  "
              f"mean={errs.mean():.3e} pu")
        print(f"  fixed-point iterations : mean={iters.mean():.1f}  max={iters.max()}")

        s = check_sensitivities(config)
        for kind in ("p", "q"):
            fd, an = s[f"fd_{kind}"], s[f"an_{kind}"]
            denom = np.maximum(np.abs(fd), 1e-12)
            rel = np.abs(an - fd) / denom
            print(f"  d|V|/d{kind.upper()} vs finite-diff : "
                  f"max abs={np.abs(an - fd).max():.3e} pu/MW   "
                  f"median rel={np.median(rel) * 100:.2f}%   "
                  f"max rel={rel.max() * 100:.2f}%")

        # Thesis Table 4.1 reproduction: station-bus diagonal, pu/kW
        print("  Table 4.1 check (pu/kW at station buses):")
        print(f"    {'bus':>5} {'|dV/dP| an':>12} {'|dV/dP| fd':>12} "
              f"{'|dV/dQ| an':>12} {'ratio P/Q':>10}")
        for k, b in enumerate(s["ev_buses"]):
            ap = abs(s["an_p"][b, k]) / 1000.0
            fp = abs(s["fd_p"][b, k]) / 1000.0
            aq = abs(s["an_q"][b, k]) / 1000.0
            print(f"    {b:>5} {ap:>12.3e} {fp:>12.3e} {aq:>12.3e} {ap / aq:>10.3f}")

        t_fast, t_pp, t_sens = benchmark(config)
        print(f"  timing: fast PF={t_fast * 1e6:8.1f} us   "
              f"pandapower={t_pp * 1e6:9.1f} us   speedup={t_pp / t_fast:6.1f}x")
        print(f"          analytic sensitivities={t_sens * 1e6:.1f} us  "
              f"(finite-diff equivalent = 8 x PF = {8 * t_pp * 1e6:.0f} us)")


if __name__ == "__main__":
    main()
