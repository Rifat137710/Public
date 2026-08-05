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


@dataclass(frozen=True)
class FeederConfig:
    """Everything needed to build one feeder."""

    variant: str = "weak"  # "weak" | "strong"

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


def build_feeder(config: FeederConfig) -> Feeder:
    net = ppn.case33bw()
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

    ev_buses = [_resolve_bus(net, n) for n in config.ev_station_nodes]
    pv_buses = [_resolve_bus(net, n) for n in config.pv_nodes]

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
