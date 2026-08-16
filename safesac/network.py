"""Feeder construction.

Ported verbatim from `thesis11.ipynb` Block 1 §2.1 so that the weak and strong
variants reproduce the thesis baselines exactly:

    weak    34 buses  Vmin 0.8816 pu  loss 338.6 kW   (nominal load)
    strong  33 buses  Vmin 0.9131 pu  loss 202.7 kW

The one behavioural change is that every magic number now arrives from a
`FeederConfig` instead of a module-level ``CONFIG`` dict, so a run's network is
fully determined by its config file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, List

import numpy as np
import pandapower as pp
import pandapower.networks as ppn


NETWORKS = ("case33bw", "kerber_dorfnetz")


@dataclass(frozen=True)
class FeederConfig:
    """Everything needed to build one feeder."""

    variant: str = "weak"  # "weak" | "strong"

    # Which base network to build on. `case33bw` is the thesis testbed. The
    # second entry exists so a finding measured here can be shown not to be a
    # property of one arbitrary set of line impedances -- see
    # docs/08-retroactive-risk.md, the one risk that wording cannot cover.
    network: str = "case33bw"

    # Multiplies every line's R and X. At 1.0 this is the real feeder; at
    # anything else it is a *wrong model* of it. Substation stiffness turned out
    # to be a weak model-mismatch axis -- station-bus Jacobians move only 1.16x
    # across Z in [0.5 %, 12 %], because dV/dP there is set by the radial path
    # impedance, which the Thevenin does not touch. This scales that path
    # impedance directly, which is the quantity a utility is actually uncertain
    # about: conductor type, run length, temperature.
    line_z_scale: float = 1.0

    base_kv: float = 12.66
    base_mva: float = 10.0

    # Thevenin equivalent inserted upstream of the slack for the weak variant.
    # R/X = 2 keeps the added impedance R-dominant, which is what makes dV/dP
    # exceed dV/dQ at the station buses.
    substation_z_pct: float = 6.0
    substation_rx_ratio: float = 2.0

    # Baran-Wu node numbers (1-indexed in the literature).
    ev_station_nodes: tuple = (18, 22, 25, 33)
    pv_nodes: tuple = (6, 13, 30)

    ev_station_kva: float = 80.0
    pv_rated_kw: tuple = (100.0, 100.0, 100.0)

    def __post_init__(self):
        if self.variant not in ("weak", "strong"):
            raise ValueError(f"unknown feeder variant {self.variant!r}")
        if self.network not in NETWORKS:
            raise ValueError(
                f"unknown network {self.network!r}; expected one of {NETWORKS}"
            )


@dataclass
class Feeder:
    """A built pandapower network plus the indices we keep reaching for."""

    net: Any
    config: FeederConfig
    slack_bus: int
    ev_buses: List[int]
    pv_buses: List[int]
    ev_sgen_idx: List[int]
    pv_sgen_idx: List[int]
    base_load_p_mw: np.ndarray
    base_load_q_mvar: np.ndarray
    load_bus_idx: List[int] = field(default_factory=list)

    @property
    def n_stations(self) -> int:
        return len(self.ev_buses)

    @property
    def n_bus(self) -> int:
        return len(self.net.bus)


def _resolve_bus(net, node_number: int) -> int:
    """Map a Baran-Wu node number onto a pandapower bus index."""
    for idx, row in net.bus.iterrows():
        if str(row.get("name", "")).endswith(str(node_number)):
            return int(idx)
        if int(idx) + 1 == node_number:
            return int(idx)
    return int(node_number - 1)


def _build_kerber_dorfnetz():
    """A 116-bus German village LV feeder, flattened to one voltage level.

    `RadialPowerFlow` is line-only and single-voltage-level, so the distribution
    transformer cannot survive as a `trafo` element. Folding it into a series
    line is exact for a fixed-tap transformer: it is a series impedance plus an
    ideal turns ratio, and the ratio vanishes once both sides are expressed in
    per-unit on their own base. Bus 0 -- the transformer's HV terminal, with
    nothing else attached to it -- is re-used as the source terminal referred to
    the LV side, so the bus count and every downstream index are untouched.
    """
    net = ppn.create_kerber_dorfnetz()
    t = net.trafo.iloc[0]
    hv, lv = int(t.hv_bus), int(t.lv_bus)

    z_base = float(t.vn_lv_kv) ** 2 / float(t.sn_mva)
    z_ohm = float(t.vk_percent) / 100.0 * z_base
    r_ohm = float(t.vkr_percent) / 100.0 * z_base
    x_ohm = math.sqrt(max(z_ohm * z_ohm - r_ohm * r_ohm, 0.0))

    net.trafo.drop(net.trafo.index, inplace=True)
    net.bus.at[hv, "vn_kv"] = float(t.vn_lv_kv)
    net.bus.at[hv, "name"] = "transformer_source"

    # Kerber's LV cables carry up to 830 nF/km, which the radial solver does not
    # model. Measured rather than assumed: dropping it moves Vmin by 2.16e-05 pu
    # and total loss by 1.2 mW, against a 0.010 pu projection margin -- three
    # orders of magnitude below anything this study resolves. The lines are short
    # and the voltage is low, so the charging current is negligible.
    net.line["c_nf_per_km"] = 0.0
    pp.create_line_from_parameters(
        net,
        from_bus=hv,
        to_bus=lv,
        length_km=1.0,
        r_ohm_per_km=r_ohm,
        x_ohm_per_km=x_ohm,
        c_nf_per_km=0.0,
        max_i_ka=10.0,
        name="substation_transformer",
    )
    return net


def build_feeder(config: FeederConfig) -> Feeder:
    if config.network == "case33bw":
        net = ppn.case33bw()
        resolve = _resolve_bus
    else:
        net = _build_kerber_dorfnetz()
        # Kerber bus names ("loadbus_3_16") end in digits that collide across
        # laterals, so name matching would silently pick the wrong bus. These
        # node numbers are pandapower bus indices already.
        resolve = lambda _net, n: int(n)  # noqa: E731

    slack_bus = int(net.ext_grid.bus.values[0])

    if config.variant == "weak":
        z_base = (config.base_kv**2) / config.base_mva
        z_ohm = (config.substation_z_pct / 100.0) * z_base
        rx = config.substation_rx_ratio
        x_ohm = z_ohm / math.sqrt(1.0 + rx * rx)
        r_ohm = rx * x_ohm

        upstream = pp.create_bus(
            net, vn_kv=config.base_kv, name="transmission_thevenin", type="b"
        )
        net.ext_grid.at[0, "bus"] = upstream
        pp.create_line_from_parameters(
            net,
            from_bus=upstream,
            to_bus=slack_bus,
            length_km=1.0,
            r_ohm_per_km=r_ohm,
            x_ohm_per_km=x_ohm,
            c_nf_per_km=0.0,
            max_i_ka=10.0,
            name="substation_thevenin",
        )

    if config.line_z_scale != 1.0:
        # Applied after the Thevenin so the whole series path is scaled: the
        # error is "this controller's impedance data is wrong by a factor k",
        # not "wrong about the feeder but right about the substation".
        net.line["r_ohm_per_km"] *= config.line_z_scale
        net.line["x_ohm_per_km"] *= config.line_z_scale

    ev_buses = [resolve(net, n) for n in config.ev_station_nodes]
    pv_buses = [resolve(net, n) for n in config.pv_nodes]

    ev_sgen_idx = [
        int(
            pp.create_sgen(
                net,
                bus=bus,
                p_mw=0.0,
                q_mvar=0.0,
                sn_mva=config.ev_station_kva / 1000.0,
                name=f"ev_station_bus{bus}",
                controllable=False,
            )
        )
        for bus in ev_buses
    ]
    pv_sgen_idx = [
        int(
            pp.create_sgen(
                net,
                bus=bus,
                p_mw=0.0,
                q_mvar=0.0,
                sn_mva=kw / 1000.0,
                name=f"pv_bus{bus}",
                controllable=False,
            )
        )
        for bus, kw in zip(pv_buses, config.pv_rated_kw)
    ]

    return Feeder(
        net=net,
        config=config,
        slack_bus=slack_bus,
        ev_buses=ev_buses,
        pv_buses=pv_buses,
        ev_sgen_idx=ev_sgen_idx,
        pv_sgen_idx=pv_sgen_idx,
        base_load_p_mw=net.load["p_mw"].to_numpy().copy(),
        base_load_q_mvar=net.load["q_mvar"].to_numpy().copy(),
        load_bus_idx=net.load["bus"].astype(int).tolist(),
    )


# --------------------------------------------------------------------------
# Element setters. Sign convention, fixed once and asserted in the tests:
#
#     p_kw > 0  ->  injection into the bus  ->  V2G discharge
#     p_kw < 0  ->  absorption from the bus ->  charging (G2V)
#
# This matches pandapower's sgen convention and the thesis *code*. The thesis
# *prose* (Section 4.6) states the opposite; see docs/01-audit item A3.
# --------------------------------------------------------------------------


def set_station_power(feeder: Feeder, p_kw, q_kvar) -> None:
    for i, sgen in enumerate(feeder.ev_sgen_idx):
        feeder.net.sgen.at[sgen, "p_mw"] = p_kw[i] / 1000.0
        feeder.net.sgen.at[sgen, "q_mvar"] = q_kvar[i] / 1000.0


def set_pv_power(feeder: Feeder, p_kw, q_kvar=None) -> None:
    if q_kvar is None:
        q_kvar = np.zeros(len(p_kw))
    for i, sgen in enumerate(feeder.pv_sgen_idx):
        feeder.net.sgen.at[sgen, "p_mw"] = p_kw[i] / 1000.0
        feeder.net.sgen.at[sgen, "q_mvar"] = q_kvar[i] / 1000.0


def set_loads(feeder: Feeder, p_mw, q_mvar) -> None:
    feeder.net.load["p_mw"] = np.asarray(p_mw)
    feeder.net.load["q_mvar"] = np.asarray(q_mvar)


def scale_loads(feeder: Feeder, scale: float) -> None:
    set_loads(feeder, feeder.base_load_p_mw * scale, feeder.base_load_q_mvar * scale)
