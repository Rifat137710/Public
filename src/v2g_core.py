"""
V2G voltage-regulation reproduction — CORE (deterministic parts).
Tests everything except SAC (feeder wrapper, EV fleet, droop baseline, daily eval).
"""
import os, numpy as np

MASTER = os.path.abspath("ieee34_master.dss")

# ----------------------------- CONFIG -----------------------------
CFG = dict(
    v_min=0.95, v_max=1.05,
    hub_buses_multi=["890", "844", "832", "830", "860"],
    hub_bus_single=["890"],
    P_rated=500.0, Q_rated=400.0,          # kW, kVAr per hub
    ev_capacity=75.0, soc_init=0.7, soc_min=0.2, soc_max=0.9,
    soh=0.95, eta_inv=0.96, c_rate=0.5, n_ev=15,
    active_hours=list(range(6, 24)),       # 6:00 .. 23:00
    peak_mild=1.5, peak_aggr=3.0,
)

# normalized daily load shape (peak=1.0 at ~18:00) and EV availability
LOAD_SHAPE = np.array([0.24,0.22,0.20,0.20,0.22,0.26,0.30,0.42,0.55,0.63,
                       0.70,0.74,0.77,0.79,0.82,0.86,0.92,0.97,1.00,0.96,
                       0.86,0.66,0.44,0.30])
AVAIL = np.array([0.85,0.85,0.85,0.85,0.80,0.75,0.65,0.55,0.50,0.47,
                  0.45,0.45,0.48,0.50,0.55,0.60,0.65,0.72,0.78,0.82,
                  0.85,0.85,0.85,0.85])

def lam_profile(peak):  return LOAD_SHAPE * peak

# ----------------------------- FEEDER -----------------------------
import opendssdirect as dss

# IEEE-34 line-to-line voltage bases (kV). Bus 890 (and 888) sit on the 4.16 kV
# transformer secondary; every other hub bus is on the 24.9 kV main feeder.
# Used as a fallback because some opendssdirect builds (e.g. the NumPy-2.0 wheel
# on Kaggle) report Bus.kVBase()=0 right after compile, which would create
# malformed kv=0 generators and corrupt the multi-hub results.
BASE_LL_KV = {"890": 4.16, "888": 4.16}

class Feeder:
    def __init__(self, hub_buses):
        self.hub_buses = hub_buses
        dss.Command("Clear"); dss.Command(f'Compile "{MASTER}"')
        dss.Command("Set ControlMode=OFF")          # regulators frozen (matches paper)
        dss.Command("Set MaxIterations=100")        # help PF converge under heavy PQ injection
        dss.Command("CalcVoltageBases")             # compute per-unit bases before we read them
        dss.Command("Solve")
        self.buses = [b for b in dss.Circuit.AllBusNames() if b.lower() != "sourcebus"]
        # add a controllable 3-phase generator at each hub bus (kv = bus base LL)
        self.hub_kv = {}
        for b in hub_buses:
            dss.Circuit.SetActiveBus(b)
            kvb = dss.Bus.kVBase()
            kv = round(kvb * np.sqrt(3), 3) if kvb > 0.1 else BASE_LL_KV.get(b.lower(), 24.9)
            self.hub_kv[b] = kv
            dss.Command(f"New Generator.hub{b} bus1={b}.1.2.3 phases=3 kv={kv} "
                        f"kw=0 kvar=0 model=1 Vminpu=0.5 Vmaxpu=1.5 status=fixed")
        dss.Command("Solve")

    def set_load(self, lam):
        dss.Command(f"Set LoadMult={lam}")

    def set_hub(self, bus, p_kw, q_kvar):
        dss.Command(f"Generator.hub{bus}.kW={p_kw}")
        dss.Command(f"Generator.hub{bus}.kvar={q_kvar}")

    def zero_hubs(self):
        for b in self.hub_buses: self.set_hub(b, 0.0, 0.0)

    def solve(self):
        dss.Command("Solve")
        return dss.Solution.Converged()

    def bus_vpu(self):
        """per-bus mean p.u. voltage over energized phases, ordered like self.buses"""
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

def reward_from_v(vpu, vmin=0.95, vmax=1.05):
    inb = np.all((vpu >= vmin) & (vpu <= vmax))
    Rvb = 10.0 if inb else 0.0
    pen = np.where(vpu < vmin, (vmin - vpu) * 100,
          np.where(vpu > vmax, (vpu - vmax) * 100, 0.0)).sum()
    return Rvb - pen

# ----------------------------- EV FLEET -----------------------------
class EVFleet:
    """Aggregate per-hub fleet with SOC/availability-limited dischargeable power."""
    def __init__(self, cfg):
        self.c = cfg; self.soc = cfg["soc_init"]; self.soh = cfg["soh"]
    def reset(self): self.soc = self.c["soc_init"]
    def n_avail(self, hour):
        return max(1, int(round(self.c["n_ev"] * AVAIL[hour])))
    def avail_power(self, hour):
        """max discharge power (kW) this 1-h step, limited by C-rate and usable SOC energy"""
        n = self.n_avail(hour); cap, soh = self.c["ev_capacity"], self.soh
        p_crate = n * self.c["c_rate"] * cap                       # kW
        e_usable = n * max(0.0, self.soc - self.c["soc_min"]) * cap * soh  # kWh over 1h -> kW
        return min(p_crate, e_usable)
    def apply(self, p_grid, q_grid, hour):
        """scale requested (p,q) to fleet capability; update SOC. Returns (p_sup,q_sup,rho,n)."""
        s_req = np.hypot(p_grid, q_grid)
        p_fleet = s_req / self.c["eta_inv"]
        p_avail = self.avail_power(hour)
        rho = min(1.0, p_avail / p_fleet) if p_fleet > 1e-6 else 1.0
        p_sup, q_sup = rho * p_grid, rho * q_grid
        # SOC update from active battery energy (discharge drains). dt = 1 h
        n = self.n_avail(hour); cap_tot = n * self.c["ev_capacity"] * self.soh
        p_batt = abs(p_sup) / self.c["eta_inv"] if p_sup >= 0 else abs(p_sup) * self.c["eta_inv"]
        dsoc = -(p_batt * 1.0) / cap_tot if p_sup >= 0 else (p_batt * 1.0) / cap_tot
        self.soc = float(np.clip(self.soc + dsoc, self.c["soc_min"], self.c["soc_max"]))
        return p_sup, q_sup, rho, n

# ----------------------------- DROOP -----------------------------
def droop_pq(v, P_rated, Q_rated, db=0.02, sat_lo=0.94, sat_hi=1.06):
    """symmetric Volt-Watt / Volt-Var: discharge+inject Q when low, charge+absorb Q when high."""
    def frac(v):
        if v < 1 - db:  return min(1.0, (1 - db - v) / (1 - db - sat_lo))   # support (positive)
        if v > 1 + db:  return -min(1.0, (v - (1 + db)) / (sat_hi - (1 + db)))  # curtail/charge
        return 0.0
    f = frac(v)
    return f * P_rated, f * Q_rated

# ----------------------------- DAILY EVALUATION -----------------------------
def evaluate_day(feeder, peak, controller, ev_constrained=False, fleets=None,
                 policy=None, cfg=CFG):
    """controller in {'baseline','droop','rl'}; returns dict of hourly series + stats."""
    lam = lam_profile(peak)
    hours = cfg["active_hours"]
    rec = {"hour": [], "vmean": [], "soc": [], "n_ev": [], "rho": []}
    if fleets is not None:
        for fl in fleets.values(): fl.reset()
    for h in hours:
        feeder.set_load(lam[h]); feeder.zero_hubs(); feeder.solve()
        obs_v = feeder.bus_vpu()
        # ---- compute per-hub setpoints ----
        setpoints = {}
        if controller == "baseline":
            for b in feeder.hub_buses: setpoints[b] = (0.0, 0.0)
        elif controller == "droop":
            setpoints = {b: (0.0, 0.0) for b in feeder.hub_buses}
            damp = 0.6
            for _ in range(25):  # damped fixed-point iterations for stable droop equilibrium
                for b in feeder.hub_buses:
                    v = feeder.hub_vpu(b)
                    p, q = droop_pq(v, cfg["P_rated"], cfg["Q_rated"])
                    p0, q0 = setpoints[b]
                    setpoints[b] = ((1-damp)*p0 + damp*p, (1-damp)*q0 + damp*q)
                _apply_setpoints(feeder, setpoints, ev_constrained, fleets, h, commit=False)
                feeder.solve()
        elif controller == "rl":
            lam_norm = (lam[h] - 0.1) / (4.0 - 0.1)
            obs = np.concatenate([obs_v, [lam_norm]]).astype(np.float32)
            act, _ = policy.predict(obs, deterministic=True)
            for i, b in enumerate(feeder.hub_buses):
                setpoints[b] = (float(act[2*i]) * cfg["P_rated"],
                                float(act[2*i+1]) * cfg["Q_rated"])
        # ---- apply (with fleet scaling + SOC commit) and solve ----
        info = _apply_setpoints(feeder, setpoints, ev_constrained, fleets, h, commit=True)
        feeder.solve()
        vmean = feeder.feeder_mean()
        rec["hour"].append(h); rec["vmean"].append(vmean)
        rec["soc"].append(np.mean([fleets[b].soc for b in feeder.hub_buses]) if fleets else np.nan)
        rec["n_ev"].append(info.get("n", np.nan)); rec["rho"].append(info.get("rho", 1.0))
    vm = np.array(rec["vmean"])
    stats = dict(Mean=round(vm.mean(),3), Min=round(vm.min(),3), Max=round(vm.max(),3),
                 Viol=int((vm < cfg["v_min"]).sum()))
    return stats, rec

def _apply_setpoints(feeder, setpoints, ev_constrained, fleets, hour, commit):
    n_last, rho_last = np.nan, 1.0
    for b, (p, q) in setpoints.items():
        if ev_constrained and fleets is not None:
            if commit:
                p, q, rho, n = fleets[b].apply(p, q, hour); rho_last, n_last = rho, n
            else:
                # preview scaling without committing SOC (for droop iterations)
                s = np.hypot(p, q); pf = s / feeder_eta(); pa = fleets[b].avail_power(hour)
                rho = min(1.0, pa/pf) if pf > 1e-6 else 1.0; p, q = rho*p, rho*q
        feeder.set_hub(b, p, q)
    return {"n": n_last, "rho": rho_last}

def feeder_eta(): return CFG["eta_inv"]
