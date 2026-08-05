"""
Phase 1.1 / 1.2 — violation attribution and the load sweep.

Answers Gate A: *is there an operating point where the choice of controller can
actually move the voltage-violation metric?*

The method needs no policy and no training. For a given background condition it
brackets what **any** controller could do, by running the true AC power flow at
three station commands:

    floor   all stations idle                      -> violations nothing can fix
    best    all stations at the voltage-optimal
            point on their 80 kVA circle           -> the best achievable
    worst   the opposite direction                 -> the worst achievable

An hour is *controllable* if it violates at ``floor`` but not at ``best``: some
controller could have fixed it. An hour that violates at ``best`` is structural
— background load alone puts the feeder outside the band and no station command
reaches it.

The best-case command is not a guess. Maximising the first-order voltage rise
``dV/dP * P + dV/dQ * Q`` subject to ``P^2 + Q^2 <= S^2`` puts the command on
the 80 kVA circle in the direction of the sensitivity vector at the worst bus;
the resulting voltage is then measured with the full nonlinear power flow, not
the linearisation.

This is the quantitative form of the observation that ``safesac_weak`` logged
exactly 26 violation steps in five consecutive episodes with different seeds,
and that ``vmin_pu_mean`` was bit-identical across two different policies.

Run:  python phase1_controllability.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from radial_pf import RadialPowerFlow, build_topology
from validate_radial_pf import build_network

V_LOWER, V_UPPER = 0.95, 1.05
MARGIN = 0.010          # the projection's safety margin (thesis Table 5.2)
S_RATED_KVA = 80.0
PV_RATED_KW = [100.0, 100.0, 100.0]
S_BASE_MVA = 1.0
OUT = Path("results/phase1")


def residential_daily_multiplier(hour: float, is_weekend: bool = False) -> float:
    """Verbatim from the thesis scenario generator (Block 2)."""
    if is_weekend:
        morn_h, morn_a, morn_w = 10.0, 0.25, 1.8
        even_h, even_a, even_w = 19.5, 0.55, 2.2
        baseline = 0.45
    else:
        morn_h, morn_a, morn_w = 7.5, 0.40, 1.5
        even_h, even_a, even_w = 19.0, 0.60, 2.0
        baseline = 0.40
    morn = morn_a * math.exp(-0.5 * ((hour - morn_h) / morn_w) ** 2)
    even = even_a * math.exp(-0.5 * ((hour - even_h) / even_w) ** 2)
    return baseline + morn + even


def clear_sky_fraction(hour: float) -> float:
    """Simple clear-sky proxy; the thesis uses a solar-elevation model.

    Only the daytime shape matters here, and violations occur in the evening
    peak when this is zero either way.
    """
    if not 6.0 <= hour <= 18.0:
        return 0.0
    return max(0.0, math.sin(math.pi * (hour - 6.0) / 12.0))


class Feeder:
    """Thin wrapper: set conditions, solve, report."""

    def __init__(self, config: str = "weak"):
        net, ev_buses, pv_buses, ev_idx, pv_idx = build_network(config)
        self.net, self.config = net, config
        self.ev_buses, self.pv_buses = ev_buses, pv_buses
        self.topo = build_topology(net, s_base_mva=S_BASE_MVA)
        self.solver = RadialPowerFlow(
            self.topo, v_slack=complex(float(net.ext_grid.vm_pu.iloc[0]), 0.0))
        self.base_p = net.load.p_mw.to_numpy(float).copy()
        self.base_q = net.load.q_mvar.to_numpy(float).copy()
        self.load_bus = net.load.bus.to_numpy(int)
        self.n_bus = self.topo.n_bus

    def injections(self, load_mult: float, pv_frac: float,
                   station_p_kw: np.ndarray, station_q_kvar: np.ndarray):
        p = np.zeros(self.n_bus)
        q = np.zeros(self.n_bus)
        np.add.at(p, self.load_bus, -self.base_p * load_mult)
        np.add.at(q, self.load_bus, -self.base_q * load_mult)
        for b, kw in zip(self.pv_buses, PV_RATED_KW):
            p[b] += pv_frac * kw / 1000.0
        for b, kw, kvar in zip(self.ev_buses, station_p_kw, station_q_kvar):
            p[b] += kw / 1000.0
            q[b] += kvar / 1000.0
        return p, q

    def solve(self, load_mult, pv_frac, sp_kw, sq_kvar):
        p, q = self.injections(load_mult, pv_frac, sp_kw, sq_kvar)
        res = self.solver.solve(p, q, tol=1e-11, max_iter=80)
        return res, p, q

    def best_command(self, load_mult, pv_frac, sign: float = +1.0):
        """Voltage-optimal station command on the S-rating circle.

        ``sign=+1`` maximises the voltage at the worst bus, ``-1`` minimises it.
        """
        zero = np.zeros(len(self.ev_buses))
        res, _, _ = self.solve(load_mult, pv_frac, zero, zero)
        worst = int(np.argmin(res.vm_pu))
        dvp, dvq = self.solver.sensitivities(v=res.v, buses=self.ev_buses)
        gp, gq = dvp[worst], dvq[worst]           # pu per pu-injection
        norm = np.hypot(gp, gq)
        norm[norm < 1e-15] = 1.0
        s_pu = S_RATED_KVA / 1000.0 / S_BASE_MVA
        return sign * s_pu * gp / norm * 1000.0, sign * s_pu * gq / norm * 1000.0


def sweep(config: str = "weak", load_scales=None, hours=None) -> dict:
    if load_scales is None:
        load_scales = [0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.75, 1.00]
    if hours is None:
        hours = [h / 2.0 for h in range(48)]      # every 30 min

    f = Feeder(config)
    zero = np.zeros(len(f.ev_buses))
    rows = []
    for ls in load_scales:
        n_floor = n_best = n_worst = n_best_margin = 0
        vmin_floor = vmin_best = 9.9
        worst_buses: dict[int, int] = {}
        for h in hours:
            mult = ls * residential_daily_multiplier(h)
            pv = clear_sky_fraction(h)

            r0, _, _ = f.solve(mult, pv, zero, zero)
            sp, sq = f.best_command(mult, pv, +1.0)
            rb, _, _ = f.solve(mult, pv, sp, sq)
            sp_w, sq_w = f.best_command(mult, pv, -1.0)
            rw, _, _ = f.solve(mult, pv, sp_w, sq_w)

            v0, vb, vw = r0.vm_pu.min(), rb.vm_pu.min(), rw.vm_pu.min()
            n_floor += v0 < V_LOWER
            n_best += vb < V_LOWER
            n_worst += vw < V_LOWER
            n_best_margin += vb < V_LOWER + MARGIN
            vmin_floor = min(vmin_floor, v0)
            vmin_best = min(vmin_best, vb)
            if v0 < V_LOWER:
                b = int(np.argmin(r0.vm_pu))
                worst_buses[b] = worst_buses.get(b, 0) + 1

        n = len(hours)
        rows.append({
            "load_scale": ls,
            "viol_floor": n_floor / n,
            "viol_best": n_best / n,
            "viol_worst": n_worst / n,
            "controllable": (n_floor - n_best) / n,
            "structural": n_best / n,
            "viol_best_margin": n_best_margin / n,
            "spread": (n_worst - n_best) / n,
            "vmin_floor": float(vmin_floor),
            "vmin_best": float(vmin_best),
            "worst_buses": {str(k): v for k, v in sorted(
                worst_buses.items(), key=lambda kv: -kv[1])},
        })
    return {"config": config, "rows": rows,
            "ev_buses": f.ev_buses, "hours": len(hours)}


def margin_sweep(config: str = "weak", load_scale: float = 0.50,
                 margins=(0.0, 0.001, 0.002, 0.003, 0.004, 0.005, 0.010)) -> dict:
    """How much of the day the projection can reach, as a function of its margin.

    The projection tightens the band by ``m`` on both sides (thesis Eq. 5.6b) to
    absorb linearisation error. If ``m`` exceeds the headroom the stations can
    actually supply, the SOCP is infeasible at exactly the hours that matter and
    the controller falls through to its freeze rule.
    """
    f = Feeder(config)
    hours = [h / 2.0 for h in range(48)]
    best_vmin = []
    for h in hours:
        mult = load_scale * residential_daily_multiplier(h)
        pv = clear_sky_fraction(h)
        sp, sq = f.best_command(mult, pv, +1.0)
        best_vmin.append(f.solve(mult, pv, sp, sq)[0].vm_pu.min())
    best_vmin = np.array(best_vmin)
    headroom = float((best_vmin - V_LOWER).min())
    return {
        "load_scale": load_scale,
        "tightest_headroom_pu": headroom,
        "reachable": {f"{m:.3f}": float((best_vmin >= V_LOWER + m).mean())
                      for m in margins},
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("Phase 1.1/1.2 — controllability envelope")
    print("=" * 78)

    results = {}
    for config in ("weak", "strong"):
        res = sweep(config)
        results[config] = res
        print(f"\n[{config}]  EV stations at buses {res['ev_buses']}, "
              f"{res['hours']} half-hourly points over a weekday")
        print(f"  {'load':>5} {'Vmin idle':>10} {'Vmin best':>10} "
              f"{'viol idle':>10} {'viol best':>10} {'controllable':>13} "
              f"{'spread':>8}")
        for r in res["rows"]:
            print(f"  {r['load_scale']:>5.2f} {r['vmin_floor']:>10.4f} "
                  f"{r['vmin_best']:>10.4f} {r['viol_floor'] * 100:>9.1f}% "
                  f"{r['viol_best'] * 100:>9.1f}% {r['controllable'] * 100:>12.1f}% "
                  f"{r['spread'] * 100:>7.1f}%")

    ms = margin_sweep("weak", 0.50)
    results["margin_sweep"] = ms
    print(f"\n[projection margin]  weak feeder, load 0.50")
    print(f"  tightest headroom above 0.95 at the ideal command: "
          f"{ms['tightest_headroom_pu'] * 1000:.2f} milli-pu")
    print(f"  thesis margin (Table 5.2)                        : 10.00 milli-pu")
    print(f"  {'margin':>10} {'reachable hours':>16}")
    for k, v in ms["reachable"].items():
        print(f"  {float(k) * 1000:>7.1f} m-pu {v * 100:>13.1f}%")

    (OUT / "controllability.json").write_text(json.dumps(results, indent=2))

    # -- Gate A ---------------------------------------------------------------
    weak = results["weak"]["rows"]
    # The useful operating point maximises what a controller can fix while
    # leaving little that it cannot: authority, not raw violation count.
    feasible = [r for r in weak if r["structural"] <= 1e-9 and r["controllable"] > 0]
    best = (max(feasible, key=lambda r: r["controllable"]) if feasible
            else max(weak, key=lambda r: r["controllable"] - r["structural"]))
    thesis = next(r for r in weak if abs(r["load_scale"] - 0.50) < 1e-9)

    print("\n" + "=" * 78)
    print("GATE A — is there an operating point where the controller matters?")
    print("=" * 78)
    print(f"  thesis operating point (load 0.50):")
    print(f"    violations no controller can fix : {thesis['structural'] * 100:.1f}%")
    print(f"    violations a controller could fix: {thesis['controllable'] * 100:.1f}%")
    print(f"    worst-bus histogram              : {thesis['worst_buses']}")
    print(f"    same, with the 0.010 pu projection margin applied:")
    print(f"      unreachable even at the best command : "
          f"{thesis['viol_best_margin'] * 100:.1f}%")
    print(f"  best operating point (load {best['load_scale']:.2f}):")
    print(f"    violations no controller can fix : {best['structural'] * 100:.1f}%")
    print(f"    violations a controller could fix: {best['controllable'] * 100:.1f}%")

    verdict = "PASS" if best["controllable"] >= 0.05 else "FAIL"
    print(f"\n  verdict: {verdict}")
    if verdict == "PASS":
        print(f"  -> load scale {best['load_scale']:.2f} gives the controller full "
              f"authority: an ideal command clears every violation.")
    else:
        print("  -> no operating point gives the controller meaningful authority "
              "over the voltage metric; pivot the objective (transformer "
              "loading or economics) before spending compute on retraining.")

    print(f"\n  written to {OUT / 'controllability.json'}")


if __name__ == "__main__":
    main()
