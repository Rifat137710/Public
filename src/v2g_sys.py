"""
System layer for the V2G gap study — paper-faithful corrections over v2g_core.py.

Differences from the original reproduction, all deliberate:
  * Feeder(control_mode=...)   : regulators can be STATIC (OpenDSS default, they act)
                                 or OFF (frozen). The paper never states which; E0 decides
                                 it empirically from their reported baseline fingerprint.
  * droop_pq(sat=0.90/1.10)    : matches the paper's stated saturation. The earlier code
                                 used 0.94/1.06, which made droop noticeably stronger.
  * per-PHASE voltages          : ANSI C84.1 limits are per-phase. We keep every energized
                                 node voltage instead of averaging phases per bus.
  * stochastic availability     : n_avail is a binomial draw around the mean profile, so
                                 scenario variance is explicit (and can be paired away).
  * throughput accounting       : cumulative battery kWh, for the degradation objective.
"""
import os
import numpy as np
import opendssdirect as dss

MASTER = os.path.abspath("ieee34_master.dss")

CFG = dict(
    v_min=0.95, v_max=1.05,
    hub_buses_multi=["890", "844", "832", "830", "860"],
    hub_bus_single=["890"],
    P_rated=500.0, Q_rated=400.0,               # kW / kVAr per hub
    ev_capacity=75.0, soc_init=0.7, soc_min=0.2, soc_max=0.9,
    soh=0.95, eta_inv=0.96, c_rate=0.5, n_ev=15,
    active_hours=list(range(6, 24)),            # 06:00 .. 23:00
    peak_mild=1.5, peak_aggr=3.0,
)

# Normalised daily load shape (peak 1.0 near 18:00).
LOAD_SHAPE = np.array([0.24, 0.22, 0.20, 0.20, 0.22, 0.26, 0.30, 0.42, 0.55, 0.63,
                       0.70, 0.74, 0.77, 0.79, 0.82, 0.86, 0.92, 0.97, 1.00, 0.96,
                       0.86, 0.66, 0.44, 0.30])

# Mean EV participation. Paper states 45-85% for the single-hub fleet.
AVAIL_MEAN = np.array([0.85, 0.85, 0.85, 0.85, 0.80, 0.75, 0.65, 0.55, 0.50, 0.47,
                       0.45, 0.45, 0.48, 0.50, 0.55, 0.60, 0.65, 0.72, 0.78, 0.82,
                       0.85, 0.85, 0.85, 0.85])

BASE_LL_KV = {"890": 4.16, "888": 4.16}   # 4.16 kV transformer secondary


def lam_profile(peak):
    return LOAD_SHAPE * peak


# --------------------------------------------------------------------------- #
# Feeder
# --------------------------------------------------------------------------- #
class Feeder:
    """IEEE-34 wrapper exposing per-bus and per-phase voltages."""

    def __init__(self, hub_buses, control_mode="OFF"):
        self.hub_buses = list(hub_buses)
        self.control_mode = control_mode
        dss.Command("Clear")
        dss.Command(f'Compile "{MASTER}"')
        dss.Command(f"Set ControlMode={control_mode}")
        dss.Command("Set MaxIterations=100")
        dss.Command("CalcVoltageBases")
        dss.Command("Solve")
        self.buses = [b for b in dss.Circuit.AllBusNames() if b.lower() != "sourcebus"]
        self.hub_kv = {}
        for b in self.hub_buses:
            dss.Circuit.SetActiveBus(b)
            kvb = dss.Bus.kVBase()
            kv = round(kvb * np.sqrt(3), 3) if kvb > 0.1 else BASE_LL_KV.get(b.lower(), 24.9)
            self.hub_kv[b] = kv
            dss.Command(f"New Generator.hub{b} bus1={b}.1.2.3 phases=3 kv={kv} "
                        f"kw=0 kvar=0 model=1 Vminpu=0.5 Vmaxpu=1.5 status=fixed")
        dss.Command("Solve")

    # ---- actuation ----
    def set_load(self, lam):
        dss.Command(f"Set LoadMult={lam}")

    def set_hub(self, bus, p_kw, q_kvar):
        dss.Command(f"Generator.hub{bus}.kW={p_kw}")
        dss.Command(f"Generator.hub{bus}.kvar={q_kvar}")

    def zero_hubs(self):
        for b in self.hub_buses:
            self.set_hub(b, 0.0, 0.0)

    def solve(self):
        dss.Command("Solve")
        return dss.Solution.Converged()

    # ---- measurement ----
    def phase_vpu(self):
        """Every energized node (per-phase) voltage in p.u. — the ANSI-relevant set."""
        out = []
        for b in self.buses:
            dss.Circuit.SetActiveBus(b)
            out.extend(v for v in dss.Bus.puVmagAngle()[0::2] if v > 0.01)
        return np.asarray(out)

    def bus_vpu(self):
        """Per-bus voltage, averaged over that bus's energized phases."""
        out = np.empty(len(self.buses))
        for i, b in enumerate(self.buses):
            dss.Circuit.SetActiveBus(b)
            vs = [v for v in dss.Bus.puVmagAngle()[0::2] if v > 0.01]
            out[i] = np.mean(vs) if vs else 1.0
        return out

    def hub_vpu(self, bus):
        dss.Circuit.SetActiveBus(bus)
        vs = [v for v in dss.Bus.puVmagAngle()[0::2] if v > 0.01]
        return float(np.mean(vs)) if vs else 1.0

    def feeder_mean(self):
        return float(np.mean(self.bus_vpu()))

    def tap_positions(self):
        """Regulator tap positions — non-trivial only when control_mode=STATIC."""
        taps = []
        names = dss.RegControls.AllNames()
        if not names or names == ['NONE']:
            return taps
        for n in names:
            dss.RegControls.Name(n)
            taps.append(dss.RegControls.TapNumber())
        return taps


# --------------------------------------------------------------------------- #
# Droop baseline — paper-stated deadband and saturation
# --------------------------------------------------------------------------- #
def droop_pq(v, P_rated, Q_rated, db=0.02, sat_lo=0.90, sat_hi=1.10):
    """Piecewise-linear Volt-Watt / Volt-Var. Positive P = discharge (support)."""
    if v < 1 - db:
        f = min(1.0, (1 - db - v) / (1 - db - sat_lo))
    elif v > 1 + db:
        f = -min(1.0, (v - (1 + db)) / (sat_hi - (1 + db)))
    else:
        f = 0.0
    return f * P_rated, f * Q_rated


# --------------------------------------------------------------------------- #
# EV fleet
# --------------------------------------------------------------------------- #
class EVFleet:
    """Aggregate hub fleet: availability-limited power, SOC state, throughput log."""

    def __init__(self, cfg=CFG, avail_scale=1.0, soc_on="S"):
        """soc_on: "S" drains the battery on APPARENT power, per the paper's Eq. (4)
        (P_fleet = S_req / eta_inv). "P" drains on real power only -- which leaves
        reactive support free and unlimited, and lets a learned policy hold voltage
        with Q at zero SOC cost. Kept as a switch so the sensitivity can be reported."""
        self.c = cfg
        self.avail_scale = avail_scale
        self.soc_on = soc_on
        self.reset()

    def reset(self, n_avail_day=None, soc_init=None):
        """n_avail_day: length-24 int array of available EVs (paired scenario draw)."""
        self.soc = self.c["soc_init"] if soc_init is None else float(soc_init)
        self.soh = self.c["soh"]
        self.throughput = 0.0          # cumulative battery kWh moved
        self.soc_series = [self.soc]
        self._n_day = n_avail_day

    def n_avail(self, hour):
        if self._n_day is not None:
            return int(self._n_day[hour])
        frac = np.clip(AVAIL_MEAN[hour] * self.avail_scale, 0.05, 1.0)
        return max(1, int(round(self.c["n_ev"] * frac)))

    def avail_power(self, hour):
        """Max discharge power this 1-h step: min(C-rate limit, usable-energy limit)."""
        n = self.n_avail(hour)
        cap, soh = self.c["ev_capacity"], self.soh
        p_crate = n * self.c["c_rate"] * cap
        e_usable = n * max(0.0, self.soc - self.c["soc_min"]) * cap * soh
        return min(p_crate, e_usable)

    def apply(self, p_grid, q_grid, hour, commit=True):
        """Scale requested (p, q) to fleet capability. Returns (p_sup, q_sup, rho, n)."""
        s_req = float(np.hypot(p_grid, q_grid))
        p_fleet = s_req / self.c["eta_inv"]
        p_avail = self.avail_power(hour)
        rho = min(1.0, p_avail / p_fleet) if p_fleet > 1e-6 else 1.0
        p_sup, q_sup = rho * p_grid, rho * q_grid
        if not commit:
            return p_sup, q_sup, rho, self.n_avail(hour)

        n = self.n_avail(hour)
        cap_tot = n * self.c["ev_capacity"] * self.soh
        eta = self.c["eta_inv"]
        s_sup = float(np.hypot(p_sup, q_sup))
        if p_sup >= 0:                       # net real-power export -> discharging
            e_out = (s_sup if self.soc_on == "S" else abs(p_sup)) / eta
            e_in = 0.0
        else:                                # charging; reactive support still costs
            e_in = abs(p_sup) * eta
            e_out = (abs(q_sup) / eta) if self.soc_on == "S" else 0.0
        dsoc = (e_in - e_out) / cap_tot
        self.throughput += (e_in + e_out) * 1.0            # battery kWh moved this hour
        self.soc = float(np.clip(self.soc + dsoc, self.c["soc_min"], self.c["soc_max"]))
        self.soc_series.append(self.soc)
        return p_sup, q_sup, rho, n


def draw_availability(rng, n_ev, avail_scale=1.0):
    """Binomial availability realisation for one day — the paired scenario primitive."""
    p = np.clip(AVAIL_MEAN * avail_scale, 0.02, 1.0)
    return np.maximum(1, rng.binomial(n_ev, p))


# --------------------------------------------------------------------------- #
# Voltage reward (paper Eqs. 8-10) — unchanged, so the baseline is comparable
# --------------------------------------------------------------------------- #
def reward_from_v(vpu, vmin=0.95, vmax=1.05):
    inb = bool(np.all((vpu >= vmin) & (vpu <= vmax)))
    Rvb = 10.0 if inb else 0.0
    pen = float(np.where(vpu < vmin, (vmin - vpu) * 100,
                np.where(vpu > vmax, (vpu - vmax) * 100, 0.0)).sum())
    return Rvb - pen
