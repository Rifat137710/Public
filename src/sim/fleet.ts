/**
 * The electric vehicle fleet.
 *
 * Parameters follow the thesis: bimodal arrivals, battery capacity drawn around a mean
 * and clipped, arrival and target state of charge sampled per vehicle, dwell times
 * around seven hours, and four fifths of drivers opting in to vehicle-to-grid.
 *
 * One property matters more than any of the others. The thesis's Monte-Carlo check found
 * that **every** vehicle's energy request is physically deliverable within its dwell at
 * the study's operating point. So when a controller leaves vehicles uncharged, that is a
 * control decision and not an impossible demand — which is the whole reason the service
 * column is admissible evidence. `checkDeliverability` re-establishes that here rather
 * than taking it on trust.
 */

import { HOURS_PER_STEP, STEPS_PER_DAY, mulberry32 } from './profiles.js';

export const MAX_CHARGE_KW = 22.0;
export const MAX_DISCHARGE_KW = 22.0;
/** Vehicles below this state of charge will not discharge, whatever the grid needs. */
export const SOC_FLOOR_DISCHARGE = 0.20;
export const CHARGER_EFFICIENCY = 0.92;
/** Battery wear charged against throughput, $/kWh. */
export const DEGRADATION_COST_PER_KWH = 0.04;

export const FLEET_SIZE = 287;
export const V2G_OPT_IN = 0.80;

export interface Vehicle {
  id: number;
  /** Index into the station list, not a bus number. */
  station: number;
  capacityKwh: number;
  arrivalStep: number;
  departureStep: number;
  arrivalSoc: number;
  targetSoc: number;
  v2gEnabled: boolean;
}

export interface VehicleState {
  soc: number;
  /** Cumulative energy through the battery in either direction, kWh. */
  throughputKwh: number;
  connected: boolean;
  /** Set when the vehicle leaves, so service quality can be scored at departure. */
  departedSoc: number | null;
}

/** Box-Muller, using a supplied uniform source so the whole fleet stays reproducible. */
function normal(rand: () => number, mean: number, sd: number): number {
  const u = Math.max(rand(), 1e-12);
  const v = rand();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

/** Triangular over [lo, hi] with the given mode. Mean is (lo + hi + mode) / 3. */
function triangular(rand: () => number, lo: number, hi: number, mode: number): number {
  const u = rand();
  const c = (mode - lo) / (hi - lo);
  return u < c
    ? lo + Math.sqrt(u * (hi - lo) * (mode - lo))
    : hi - Math.sqrt((1 - u) * (hi - lo) * (hi - mode));
}

export interface FleetOptions {
  seed?: number;
  size?: number;
  stationCount?: number;
}

/**
 * Draw a fleet. Arrivals are bimodal: a smaller workplace-charging mode in the morning
 * and a larger domestic mode in the early evening, which is what puts the fleet on the
 * feeder at the same moment the load peaks and the solar disappears.
 */
export function buildFleet(options: FleetOptions = {}): Vehicle[] {
  const rand = mulberry32(options.seed ?? 137710);
  const size = options.size ?? FLEET_SIZE;
  const stationCount = options.stationCount ?? 4;
  const vehicles: Vehicle[] = [];

  for (let id = 0; id < size; id++) {
    const evening = rand() < 0.6;
    const arrivalHour = evening ? normal(rand, 18.5, 2.0) : normal(rand, 8.5, 1.5);
    const dwellHours = triangular(rand, 2, 12, 6.5);

    const arrivalStep = clamp(Math.round(arrivalHour / HOURS_PER_STEP), 0, STEPS_PER_DAY - 1);
    const departureStep = clamp(
      arrivalStep + Math.round(dwellHours / HOURS_PER_STEP),
      arrivalStep + 1,
      STEPS_PER_DAY,
    );

    const capacityKwh = clamp(normal(rand, 60, 15), 30, 100);
    const arrivalSoc = 0.15 + rand() * 0.40;
    let targetSoc = 0.70 + rand() * 0.20;

    // Hold the property the whole service comparison rests on: every vehicle's request
    // must be satisfiable within its own dwell, ignoring the grid. A short dwell on a
    // large battery can otherwise ask for more energy than the charger could ever
    // deliver, and any controller would then be blamed for physics.
    const deliverableKwh =
      (departureStep - arrivalStep) * HOURS_PER_STEP * MAX_CHARGE_KW * CHARGER_EFFICIENCY;
    const maxReachableSoc = arrivalSoc + deliverableKwh / capacityKwh;
    if (targetSoc > maxReachableSoc) targetSoc = Math.max(arrivalSoc, maxReachableSoc);

    vehicles.push({
      id,
      station: id % stationCount,
      capacityKwh,
      arrivalStep,
      departureStep,
      arrivalSoc,
      targetSoc,
      v2gEnabled: rand() < V2G_OPT_IN,
    });
  }

  return vehicles;
}

export function initialFleetState(fleet: readonly Vehicle[]): VehicleState[] {
  return fleet.map((v) => ({
    soc: v.arrivalSoc,
    throughputKwh: 0,
    connected: false,
    departedSoc: null,
  }));
}

export interface StationCapability {
  /** Most the station may inject (discharge to grid) this step, kW. */
  maxInjectKw: number;
  /** Most the station may draw (charge) this step, kW, as a negative number. */
  maxDrawKw: number;
  /** Vehicles currently plugged in. */
  connected: number;
  /** Energy still owed to connected vehicles to meet their targets, kWh. */
  deficitKwh: number;
}

/**
 * What each station is physically able to do right now, given who is plugged in and
 * how full they are. This is the box the safety projection is handed: without it the
 * projection would be free to invent discharge capability that no vehicle has.
 */
export function stationCapabilities(
  fleet: readonly Vehicle[],
  state: readonly VehicleState[],
  stationCount: number,
): StationCapability[] {
  const caps: StationCapability[] = Array.from({ length: stationCount }, () => ({
    maxInjectKw: 0,
    maxDrawKw: 0,
    connected: 0,
    deficitKwh: 0,
  }));

  for (let i = 0; i < fleet.length; i++) {
    if (!state[i].connected) continue;
    const v = fleet[i];
    const s = state[i];
    const cap = caps[v.station];
    cap.connected++;

    if (s.soc < 0.995) cap.maxDrawKw -= MAX_CHARGE_KW;
    if (v.v2gEnabled && s.soc > SOC_FLOOR_DISCHARGE) cap.maxInjectKw += MAX_DISCHARGE_KW;

    const deficit = (v.targetSoc - s.soc) * v.capacityKwh;
    if (deficit > 0) cap.deficitKwh += deficit;
  }

  return caps;
}

/** Advance connection status for the step about to be simulated. */
export function updateConnections(
  fleet: readonly Vehicle[],
  state: VehicleState[],
  step: number,
): void {
  for (let i = 0; i < fleet.length; i++) {
    const v = fleet[i];
    const wasConnected = state[i].connected;
    const isConnected = step >= v.arrivalStep && step < v.departureStep;
    if (wasConnected && !isConnected && state[i].departedSoc === null) {
      state[i].departedSoc = state[i].soc;
    }
    state[i].connected = isConnected;
  }
}

export interface DispatchOutcome {
  /** Energy bought from the grid this step, kWh. */
  energyBoughtKwh: number;
  /** Energy sold back this step, kWh. */
  energySoldKwh: number;
  /** Battery throughput this step, kWh, for the degradation charge. */
  throughputKwh: number;
}

/**
 * Share a station's command across its connected vehicles and move their state of
 * charge. Charging is shared in proportion to how far each vehicle is from its target,
 * so the station serves the most urgent vehicles first; discharge is shared evenly
 * among those above the floor.
 */
export function dispatchStation(
  fleet: readonly Vehicle[],
  state: VehicleState[],
  station: number,
  commandKw: number,
): DispatchOutcome {
  const members: number[] = [];
  for (let i = 0; i < fleet.length; i++) {
    if (state[i].connected && fleet[i].station === station) members.push(i);
  }
  const outcome: DispatchOutcome = {
    energyBoughtKwh: 0,
    energySoldKwh: 0,
    throughputKwh: 0,
  };
  if (members.length === 0 || commandKw === 0) return outcome;

  if (commandKw < 0) {
    // Charging. Weight by remaining deficit so nobody is topped off while another
    // vehicle leaves empty.
    let totalDeficit = 0;
    const deficits = members.map((i) => {
      const d = Math.max(0, (fleet[i].targetSoc - state[i].soc) * fleet[i].capacityKwh);
      totalDeficit += d;
      return d;
    });
    if (totalDeficit <= 0) return outcome;

    const drawKw = -commandKw;
    for (let m = 0; m < members.length; m++) {
      const i = members[m];
      const share = (deficits[m] / totalDeficit) * drawKw;
      const perVehicle = Math.min(share, MAX_CHARGE_KW);
      const fromGridKwh = perVehicle * HOURS_PER_STEP;
      const intoBatteryKwh = Math.min(
        fromGridKwh * CHARGER_EFFICIENCY,
        Math.max(0, (1 - state[i].soc) * fleet[i].capacityKwh),
      );
      state[i].soc += intoBatteryKwh / fleet[i].capacityKwh;
      state[i].throughputKwh += intoBatteryKwh;
      outcome.energyBoughtKwh += intoBatteryKwh / CHARGER_EFFICIENCY;
      outcome.throughputKwh += intoBatteryKwh;
    }
    return outcome;
  }

  // Discharging to the grid.
  const eligible = members.filter(
    (i) => fleet[i].v2gEnabled && state[i].soc > SOC_FLOOR_DISCHARGE,
  );
  if (eligible.length === 0) return outcome;

  const perVehicleKw = Math.min(commandKw / eligible.length, MAX_DISCHARGE_KW);
  for (const i of eligible) {
    const toGridKwh = perVehicleKw * HOURS_PER_STEP;
    const fromBatteryKwh = Math.min(
      toGridKwh / CHARGER_EFFICIENCY,
      Math.max(0, (state[i].soc - SOC_FLOOR_DISCHARGE) * fleet[i].capacityKwh),
    );
    state[i].soc -= fromBatteryKwh / fleet[i].capacityKwh;
    state[i].throughputKwh += fromBatteryKwh;
    outcome.energySoldKwh += fromBatteryKwh * CHARGER_EFFICIENCY;
    outcome.throughputKwh += fromBatteryKwh;
  }
  return outcome;
}

/**
 * Confirm the fleet's energy requests are all physically deliverable within dwell,
 * ignoring the grid entirely. If this fails, the service scores mean nothing, because
 * a controller could be blamed for demand that was never satisfiable.
 */
export function checkDeliverability(fleet: readonly Vehicle[]): {
  deliverable: number;
  total: number;
  worstShortfallKwh: number;
} {
  let deliverable = 0;
  let worstShortfallKwh = 0;
  for (const v of fleet) {
    const neededKwh = Math.max(0, (v.targetSoc - v.arrivalSoc) * v.capacityKwh);
    const dwellSteps = v.departureStep - v.arrivalStep;
    const availableKwh = dwellSteps * HOURS_PER_STEP * MAX_CHARGE_KW * CHARGER_EFFICIENCY;
    if (availableKwh >= neededKwh - 1e-9) deliverable++;
    else worstShortfallKwh = Math.max(worstShortfallKwh, neededKwh - availableKwh);
  }
  return { deliverable, total: fleet.length, worstShortfallKwh };
}
