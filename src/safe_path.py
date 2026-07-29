"""
SAFE-PATH driver: single-hub, the degradation/SOC axis (the guaranteed win).

Compares, on an IDENTICAL feeder/day, two COMPLETE controllers:
  (1) closed-loop droop         -- the paper's proper baseline (damped fixed point)
  (2) residual-over-droop RL    -- P = clip(droop_P + a*P_rated, 0, P_rated), SOC/time-aware

Logs BOTH axes consistently for each:
  * voltage support : violation-hours (feeder-mean AND worst-bus), worst-bus min voltage
  * battery wear    : total energy discharged (kWh), end-of-day mean SOC

The claim we want: residual-RL holds voltage support >= droop while discharging
LESS energy (higher end SOC) -- a capability droop lacks by construction, because
droop discharges greedily on local voltage even for cosmetic (in-band) sags.
"""
import sys, time, numpy as np
import torch
torch.set_num_threads(4)
import v2g_core as core
from v2g_core import Feeder, EVFleet, droop_pq, lam_profile, CFG
from v2g_env_residual import V2GVoltEnvResidual
from stable_baselines3 import SAC

BASE_AVAIL = core.AVAIL.copy()


def set_avail_scale(s):
    core.AVAIL = np.clip(BASE_AVAIL * s, 0.05, 1.0)


def rollout(feeder, peak, mode, policy=None, cfg=CFG):
    """Unified daily rollout. mode in {'droop','residual','zero'}.
    Returns (summary, rec) with consistent energy + worst-bus logging."""
    lam = lam_profile(peak); hours = cfg["active_hours"]
    fleets = {b: EVFleet(cfg) for b in feeder.hub_buses}
    for fl in fleets.values():
        fl.reset()
    rec = {"hour": [], "vmean": [], "vmin": [], "disch": [], "soc": []}
    for h in hours:
        feeder.set_load(lam[h]); feeder.zero_hubs(); feeder.solve()
        vraw = feeder.bus_vpu()
        disch = 0.0
        if mode == "droop":
            # closed-loop droop: damped fixed point with fleet-preview scaling (no commit)
            sp = {b: (0.0, 0.0) for b in feeder.hub_buses}
            damp = 0.6
            for _ in range(25):
                for b in feeder.hub_buses:
                    v = feeder.hub_vpu(b)
                    p, q = droop_pq(v, cfg["P_rated"], cfg["Q_rated"])
                    p0, q0 = sp[b]; sp[b] = ((1 - damp) * p0 + damp * p, (1 - damp) * q0 + damp * q)
                for b, (p, q) in sp.items():
                    s = np.hypot(p, q); pf = s / cfg["eta_inv"]; pa = fleets[b].avail_power(h)
                    rho = min(1.0, pa / pf) if pf > 1e-6 else 1.0
                    feeder.set_hub(b, rho * p, rho * q)
                feeder.solve()
            for b, (p, q) in sp.items():
                p_sup, q_sup, rho, n = fleets[b].apply(p, q, h)
                feeder.set_hub(b, p_sup, q_sup); disch += max(0.0, p_sup)
            feeder.solve()
        else:
            lam_norm = (lam[h] - 0.1) / (4.0 - 0.1)
            hour_norm = (h - hours[0]) / (hours[-1] - hours[0])
            socs = [fleets[b].soc for b in feeder.hub_buses]
            navs = [fleets[b].n_avail(h) / cfg["n_ev"] for b in feeder.hub_buses]
            if mode == "zero":
                act = np.zeros(2 * len(feeder.hub_buses), dtype=np.float32)
            else:
                obs = np.concatenate([vraw, [lam_norm, hour_norm], socs, navs]).astype(np.float32)
                act, _ = policy.predict(obs, deterministic=True)
            for i, b in enumerate(feeder.hub_buses):
                v = feeder.hub_vpu(b)
                p_d, q_d = droop_pq(v, cfg["P_rated"], cfg["Q_rated"])
                p_req = float(np.clip(max(0.0, p_d) + act[2 * i] * cfg["P_rated"], 0.0, cfg["P_rated"]))
                q_req = float(np.clip(q_d + act[2 * i + 1] * cfg["Q_rated"], -cfg["Q_rated"], cfg["Q_rated"]))
                p_sup, q_sup, rho, n = fleets[b].apply(p_req, q_req, h)
                feeder.set_hub(b, p_sup, q_sup); disch += max(0.0, p_sup)
            feeder.solve()
        vpu = feeder.bus_vpu()
        rec["hour"].append(h); rec["vmean"].append(feeder.feeder_mean())
        rec["vmin"].append(float(vpu.min())); rec["disch"].append(disch)
        rec["soc"].append(float(np.mean([fleets[b].soc for b in feeder.hub_buses])))
    vm = np.array(rec["vmean"]); vmn = np.array(rec["vmin"])
    summary = dict(
        ViolMean=int((vm < cfg["v_min"]).sum()),
        ViolBus=int((vmn < cfg["v_min"]).sum()),
        Vmin=round(float(vmn.min()), 3),
        Energy=round(float(sum(rec["disch"])), 1),   # kWh discharged over the day
        SOCend=round(rec["soc"][-1], 3),
    )
    return summary, rec


def train_residual(hub_buses, peak_lo, peak_hi, steps, avail_scale=1.0, soc_cost=0.5, seed=0):
    set_avail_scale(avail_scale)
    env = V2GVoltEnvResidual(hub_buses, peak_range=(peak_lo, peak_hi),
                             soc_cost=soc_cost, seed=seed)
    m = SAC("MlpPolicy", env, learning_rate=3e-4, batch_size=256, gamma=0.99,
            buffer_size=200_000, learning_starts=1000, tau=0.005,
            policy_kwargs=dict(net_arch=[256, 256]), device="cpu", seed=seed, verbose=0)
    t0 = time.time(); C = 5000; done = 0
    while done < steps:
        n = min(C, steps - done)
        m.learn(total_timesteps=n, reset_num_timesteps=(done == 0), progress_bar=False)
        done += n
        print(f"    train {done}/{steps}  {time.time()-t0:.0f}s", flush=True)
    return m


def compare(feeder, peak, policy, name, avail_scale=1.0):
    set_avail_scale(avail_scale)
    z, zrec = rollout(feeder, peak, "zero")       # floor sanity (open-loop droop, a=0)
    dr, drec = rollout(feeder, peak, "droop")     # proper closed-loop droop baseline
    rs, rrec = rollout(feeder, peak, "residual", policy=policy)
    dE = dr["Energy"] - rs["Energy"]
    pct = 100.0 * dE / dr["Energy"] if dr["Energy"] > 1e-6 else 0.0
    vtag = "OK" if rs["ViolBus"] <= dr["ViolBus"] else "WORSE"
    print(f"\n  === {name}  (peak={peak}, avail_scale={avail_scale}) ===")
    print(f"    {'controller':<16}{'ViolMean':>9}{'ViolBus':>9}{'Vmin':>7}{'Energy(kWh)':>13}{'SOCend':>8}")
    for tag, d in [("closed-droop", dr), ("residual-RL", rs), ("(a=0 floor)", z)]:
        print(f"    {tag:<16}{d['ViolMean']:>9}{d['ViolBus']:>9}{d['Vmin']:>7}{d['Energy']:>13}{d['SOCend']:>8}")
    print(f"    --> voltage support: {vtag} (worst-bus viol {rs['ViolBus']} vs droop {dr['ViolBus']})")
    print(f"    --> ENERGY SAVED   : {dE:.1f} kWh ({pct:.1f}% less discharge), "
          f"end-SOC {rs['SOCend']} vs {dr['SOCend']}")
    return dr, rs, drec, rrec


if __name__ == "__main__":
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    hub = CFG["hub_bus_single"]
    print(f"SINGLE-HUB safe-path run | residual SAC steps={steps} | hub={hub}")
    fd = Feeder(hub)
    import json
    dump = {}
    for peak, nm, tag in [(CFG["peak_mild"], "single-hub MILD", "mild"),
                          (CFG["peak_aggr"], "single-hub AGGR", "aggr")]:
        print(f"\n[train residual @ {nm}] ...", flush=True)
        # train across the peak's neighbourhood so the agent generalises around it
        m = train_residual(hub, peak * 0.8, peak * 1.2, steps=steps, avail_scale=1.0)
        m.save(f"sac_residual_single_{tag}.zip")
        dr, rs, drec, rrec = compare(fd, peak, m, nm, avail_scale=1.0)
        dump[tag] = dict(peak=peak, droop=dr, residual=rs,
                         droop_rec=drec, residual_rec=rrec)
    with open("safe_path_single.json", "w") as f:
        json.dump(dump, f, indent=1)
    print("\nsaved: sac_residual_single_{mild,aggr}.zip, safe_path_single.json")
    print("DONE.")
