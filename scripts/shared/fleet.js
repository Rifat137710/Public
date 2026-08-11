/**
 * The fleet, and the accounting that decides whether a driver went home satisfied.
 *
 * This is a direct port of `src/sim/fleet.ts`. It exists so a learner's own run can be
 * scored the way the engine scores one — counting vehicles that reached their target
 * state of charge — rather than by some proxy that happens to be computable from the
 * data already exported. A dot on the map has to sit on the same axes as the reference
 * dots beside it or the map is a lie.
 *
 * The vehicles themselves are exported rather than regenerated, so there is no second
 * random number generator to keep in step with the first.
 *
 * Two things are deliberately faithful and easy to get wrong:
 *
 *   - Charging is shared by remaining *deficit*, not equally. Nobody is topped off
 *     while another vehicle leaves empty.
 *   - Violation rate counts bus-steps, not steps. The engine divides by
 *     `steps × 33`, so a day with one bus down all evening scores far lower than a
 *     day with all thirty-three down for an hour.
 */

import { WORLD, N_BUS, solveAt, setGrid } from './grid.js';

const C = WORLD.fleetConstants;
export const STEPS_PER_DAY = WORLD.day.length;

/** The exported vehicles, unpacked into the shape the accounting reads. */
const ALL_VEHICLES = WORLD.fleet.map((v) => ({
  station: v.s,
  capacityKwh: v.cap,
  arrivalStep: v.a,
  departureStep: v.d,
  arrivalSoc: v.soc0,
  targetSoc: v.tgt,
  v2g: v.v2g === 1,
}));

export const FLEET_SIZE = ALL_VEHICLES.length;

/**
 * Take `n` of the fleet, spread evenly through the list rather than sliced off the
 * front. The vehicles are ordered as they were generated, so a slice would bias the
 * sample towards whichever stations and arrival times happen to sit at the start; a
 * Bresenham pick keeps the four stations and the arrival spread in proportion, which is
 * what makes "half as many cars" mean half as many everywhere.
 */
function subset(n) {
  const total = ALL_VEHICLES.length;
  if (n >= total) return ALL_VEHICLES;
  if (n <= 0) return [];
  const out = [];
  for (let i = 0; i < total; i++) {
    if (Math.floor((i * n) / total) !== Math.floor(((i + 1) * n) / total)) out.push(ALL_VEHICLES[i]);
  }
  return out;
}

export class FleetRun {
  /** `size` lets a lesson ask what the same day looks like with fewer cars on it. */
  constructor(size = ALL_VEHICLES.length) {
    this.vehicles = subset(size);
    this.reset();
  }

  reset() {
    this.state = this.vehicles.map((v) => ({
      soc: v.arrivalSoc,
      throughputKwh: 0,
      connected: false,
      departedSoc: null,
    }));
    this.violationPairs = 0;
    this.lossKwh = 0;
    this.worstV = Infinity;
    this.steps = 0;
  }

  /** Plug in whoever has arrived; record the charge of anyone leaving. */
  updateConnections(step) {
    for (let i = 0; i < this.vehicles.length; i++) {
      const v = this.vehicles[i];
      const s = this.state[i];
      const isConnected = step >= v.arrivalStep && step < v.departureStep;
      if (s.connected && !isConnected && s.departedSoc === null) s.departedSoc = s.soc;
      s.connected = isConnected;
    }
  }

  /** What the connected vehicles can physically absorb or supply, per station. */
  capabilities() {
    const caps = Array.from({ length: 4 }, () => ({ maxInjectKw: 0, maxDrawKw: 0, connected: 0, deficitKwh: 0 }));
    for (let i = 0; i < this.vehicles.length; i++) {
      const s = this.state[i];
      if (!s.connected) continue;
      const v = this.vehicles[i];
      const cap = caps[v.station];
      cap.connected++;
      if (s.soc < 0.995) cap.maxDrawKw -= C.maxChargeKw;
      if (v.v2g && s.soc > C.socFloorDischarge) cap.maxInjectKw += C.maxDischargeKw;
      const deficit = (v.targetSoc - s.soc) * v.capacityKwh;
      if (deficit > 0) cap.deficitKwh += deficit;
    }
    return caps;
  }

  /** Removing the safety layer does not repeal the laws of the fleet. */
  clampToFleet(rawKw) {
    const caps = this.capabilities();
    return caps.map((cap, k) => Math.min(cap.maxInjectKw, Math.max(cap.maxDrawKw, rawKw[k] ?? 0)));
  }

  /** Move energy for one station over one step, and report what it cost the grid. */
  dispatchStation(station, commandKw) {
    const members = [];
    for (let i = 0; i < this.vehicles.length; i++) {
      if (this.state[i].connected && this.vehicles[i].station === station) members.push(i);
    }
    const out = { energyBoughtKwh: 0, energySoldKwh: 0, throughputKwh: 0 };
    if (members.length === 0 || commandKw === 0) return out;

    if (commandKw < 0) {
      // Charging, weighted by remaining deficit.
      let totalDeficit = 0;
      const deficits = members.map((i) => {
        const d = Math.max(0, (this.vehicles[i].targetSoc - this.state[i].soc) * this.vehicles[i].capacityKwh);
        totalDeficit += d;
        return d;
      });
      if (totalDeficit <= 0) return out;

      const drawKw = -commandKw;
      for (let m = 0; m < members.length; m++) {
        const i = members[m];
        const s = this.state[i], v = this.vehicles[i];
        const perVehicle = Math.min((deficits[m] / totalDeficit) * drawKw, C.maxChargeKw);
        const fromGridKwh = perVehicle * C.hoursPerStep;
        const intoBatteryKwh = Math.min(
          fromGridKwh * C.chargerEfficiency,
          Math.max(0, (1 - s.soc) * v.capacityKwh),
        );
        s.soc += intoBatteryKwh / v.capacityKwh;
        s.throughputKwh += intoBatteryKwh;
        out.energyBoughtKwh += intoBatteryKwh / C.chargerEfficiency;
        out.throughputKwh += intoBatteryKwh;
      }
      return out;
    }

    // Discharging to the grid.
    const eligible = members.filter((i) => this.vehicles[i].v2g && this.state[i].soc > C.socFloorDischarge);
    if (eligible.length === 0) return out;
    const perVehicleKw = Math.min(commandKw / eligible.length, C.maxDischargeKw);
    for (const i of eligible) {
      const s = this.state[i], v = this.vehicles[i];
      const toGridKwh = perVehicleKw * C.hoursPerStep;
      const fromBatteryKwh = Math.min(
        toGridKwh / C.chargerEfficiency,
        Math.max(0, (s.soc - C.socFloorDischarge) * v.capacityKwh),
      );
      s.soc -= fromBatteryKwh / v.capacityKwh;
      s.throughputKwh += fromBatteryKwh;
      out.energySoldKwh += fromBatteryKwh * C.chargerEfficiency;
      out.throughputKwh += fromBatteryKwh;
    }
    return out;
  }

  /**
   * Fold one solved step into the running score. `solution.violations` is already the
   * engine's count — buses outside [0.95, 1.05] at this step — so it is used directly
   * rather than recounted from the voltage array against the same two constants.
   */
  record(solution) {
    this.violationPairs += solution.violations;
    this.lossKwh += (solution.lossKw * 5) / 60;
    this.worstV = Math.min(this.worstV, solution.vMin);
    this.steps++;
  }

  /**
   * Final score, counting everyone still plugged in at midnight where they stand —
   * the same rule `finalTotals()` uses, so this dot is comparable with the recorded ones.
   */
  totals() {
    let met = 0;
    for (let i = 0; i < this.vehicles.length; i++) {
      const soc = this.state[i].departedSoc ?? this.state[i].soc;
      if (soc >= this.vehicles[i].targetSoc - 1e-6) met++;
    }
    return {
      violationRate: this.violationPairs / (STEPS_PER_DAY * N_BUS),
      socMet: met / this.vehicles.length,
      totalLossKwh: this.lossKwh,
      vMinPu: this.worstV === Infinity ? 1 : this.worstV,
      driversMet: met,
      fleetSize: this.vehicles.length,
    };
  }

  /** Replay a recorded command series through this fleet, one step at a time. */
  replay(frames, day) {
    this.reset();
    for (let step = 0; step < frames.length; step++) {
      this.updateConnections(step);
      const kw = frames[step].kw;
      this.record(solveAt(day[step], kw));
      for (let k = 0; k < 4; k++) this.dispatchStation(k, kw[k]);
    }
    return this.totals();
  }

  /** Per-station state of charge, for the cars parked under the canopies. */
  socAt(station, limit) {
    const out = [];
    for (let i = 0; i < this.vehicles.length && out.length < limit; i++) {
      if (this.state[i].connected && this.vehicles[i].station === station) out.push(this.state[i].soc);
    }
    return out;
  }
}

/**
 * Replay every recorded run through this port and compare with the totals the engine
 * wrote. This is the same discipline as the solver's own self-check: a port that
 * reproduces four controllers' service scores to four decimals is a port, and one that
 * is merely believed would put invented dots on the map beside real ones.
 */
export const fleetCheck = (() => {
  let worstSoc = 0, worstViol = 0, worstLoss = 0, n = 0;
  const run = new FleetRun();
  const sweep = (runs, kind) => {
    setGrid(kind);
    for (const r of runs) {
      const t = run.replay(r.frames, WORLD.day);
      worstSoc = Math.max(worstSoc, Math.abs(t.socMet - r.socMet));
      worstViol = Math.max(worstViol, Math.abs(t.violationRate - r.violationRate));
      worstLoss = Math.max(worstLoss, Math.abs(t.totalLossKwh - r.totalLossKwh));
      n++;
    }
  };
  sweep(WORLD.runs, 'weak');
  sweep(WORLD.runsStrong, 'strong');
  setGrid('weak');
  return { worstSoc, worstViol, worstLoss, n, ok: worstSoc < 5e-4 && worstViol < 5e-4 };
})();
