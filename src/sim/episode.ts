/**
 * One simulated day, start to finish.
 *
 * Each of the 288 steps runs the same sequence:
 *
 *   1. connect and disconnect vehicles
 *   2. build the background operating point: load shape, solar, no EV action yet
 *   3. measure voltage sensitivities on that live network
 *   4. ask the controller for a raw command
 *   5. project it onto the safe set, if the safety layer is enabled
 *   6. apply the command and solve the true power flow
 *   7. move state of charge and money, and record everything
 *
 * Step 3 is the one worth noticing. The sensitivities are re-measured every step from
 * the network as it actually stands, not read from a fixed table — which is the thesis's
 * central design decision, and the reason the same policy behaves differently on the two
 * grids. It costs sixteen power flows, about a third of a millisecond.
 */

import {
  KW_PER_PU,
  N_BUS,
  PV_BUSES,
  STATION_BUSES,
  buildNetwork,
  nominalLoadPu,
  sourceImpedanceFor,
  type GridKind,
  type Network,
} from './network.js';
import { minimumVoltage, solvePowerFlow } from './powerflow.js';
import { measureSensitivities, type Sensitivities } from './sensitivities.js';
import { V_LOWER, V_UPPER, DEFAULT_MARGIN_PU, projectCommand } from './projection.js';
import {
  DEGRADATION_COST_PER_KWH,
  buildFleet,
  dispatchStation,
  initialFleetState,
  stationCapabilities,
  updateConnections,
  type Vehicle,
  type VehicleState,
} from './fleet.js';
import { STEPS_PER_DAY, clearSkyFraction, loadShape, touPrice } from './profiles.js';
import type { Controller } from './controllers.js';

/** Installed rooftop solar at each PV bus, kW. */
export const PV_CAPACITY_KW = 250;

export interface ScenarioOptions {
  grid?: GridKind;
  /** Fraction of nameplate demand at the evening peak. The thesis studies 0.50. */
  loadScale?: number;
  seed?: number;
  /**
   * Force the safety layer on or off, overriding the controller's own default.
   * Leave undefined for the honest comparison: only SafeSAC is projected. Set it
   * explicitly for the stage-5 reveal, where the same agent runs with the physics
   * removed and slides back to the dominated point.
   */
  projectionOverride?: boolean;
  marginPu?: number;
  /** Scales solar output, so a cloudy day is a scenario rather than a code change. */
  solarScale?: number;
}

export interface StepRecord {
  step: number;
  /** What the controller asked for, kW per station, injection positive. */
  rawKw: number[];
  /** What was executed after the safety layer. */
  safeKw: number[];
  /** True bus voltages after the command, pu, indexed by node. */
  voltages: Float64Array;
  vMin: number;
  vMinBus: number;
  /** Buses outside [0.95, 1.05] this step. */
  violations: number;
  lossKw: number;
  price: number;
  costUsd: number;
  connected: number;
  /** True when the operating point was already out of band before any command. */
  relaxed: boolean;
}

export interface EpisodeResult {
  controllerId: string;
  label: string;
  provenance: string;
  note?: string;
  grid: GridKind;
  projectionEnabled: boolean;
  steps: StepRecord[];
  /** Fraction of (bus, step) pairs outside the statutory band. */
  violationRate: number;
  /** Fraction of departing vehicles that reached their target state of charge. */
  socMet: number;
  /** Net cost across the day: energy bought, less V2G revenue, plus battery wear. */
  netCostUsd: number;
  /** Lowest voltage seen anywhere, at any moment. */
  vMinPu: number;
  /**
   * Fraction of the day on which the margin-tightened band was already breached before
   * any command, so the safety layer could only hold the line rather than restore it.
   * Zero when the safety layer is off, because nothing is being asked of it.
   */
  marginBreachedFraction: number;
  totalLossKwh: number;
}

interface Workspace {
  net: Network;
  fleet: Vehicle[];
  state: VehicleState[];
  baseP: Float64Array;
  baseQ: Float64Array;
}

function prepare(options: ScenarioOptions): Workspace {
  const grid = options.grid ?? 'weak';
  const net = buildNetwork(sourceImpedanceFor(grid));
  const fleet = buildFleet({ seed: options.seed ?? 137710, stationCount: STATION_BUSES.length });
  return {
    net,
    fleet,
    state: initialFleetState(fleet),
    baseP: new Float64Array(net.nodeCount),
    baseQ: new Float64Array(net.nodeCount),
  };
}

/**
 * The background operating point for a step: scaled residential demand everywhere, less
 * whatever the rooftop solar is producing. EV action is deliberately excluded — the
 * sensitivities are measured about the feeder the controller is about to act on.
 */
function backgroundLoad(
  step: number,
  loadScale: number,
  solarScale: number,
  p: Float64Array,
  q: Float64Array,
): void {
  const shape = loadShape(step) * loadScale;
  const nominal = nominalLoadPu(shape);
  p.set(nominal.p);
  q.set(nominal.q);

  const solarKw = clearSkyFraction(step) * PV_CAPACITY_KW * solarScale;
  if (solarKw > 0) {
    for (const bus of PV_BUSES) p[bus] -= solarKw / KW_PER_PU;
  }
}

function countViolations(voltages: Float64Array): number {
  let count = 0;
  for (let bus = 1; bus <= N_BUS; bus++) {
    if (voltages[bus] < V_LOWER || voltages[bus] > V_UPPER) count++;
  }
  return count;
}

/** Run one controller across a full day and score it. */
export function runEpisode(
  controller: Controller,
  options: ScenarioOptions = {},
): EpisodeResult {
  const grid = options.grid ?? 'weak';
  const loadScale = options.loadScale ?? 0.5;
  const solarScale = options.solarScale ?? 1.0;
  const projectionEnabled = options.projectionOverride ?? controller.usesProjection;
  const marginPu = options.marginPu ?? DEFAULT_MARGIN_PU;

  const ws = prepare(options);
  controller.reset?.();

  const steps: StepRecord[] = [];
  let violationPairs = 0;
  let marginBreachedSteps = 0;
  let netCost = 0;
  let totalLossKwh = 0;
  let vMinPu = Infinity;

  const stationP = new Float64Array(ws.net.nodeCount);

  for (let step = 0; step < STEPS_PER_DAY; step++) {
    updateConnections(ws.fleet, ws.state, step);
    backgroundLoad(step, loadScale, solarScale, ws.baseP, ws.baseQ);

    const background = solvePowerFlow(ws.net, ws.baseP, ws.baseQ);
    const sens: Sensitivities = measureSensitivities(
      ws.net,
      ws.baseP,
      ws.baseQ,
      STATION_BUSES,
    );

    const capabilities = stationCapabilities(ws.fleet, ws.state, STATION_BUSES.length);
    const price = touPrice(step);

    const rawKw = controller.command({
      step,
      voltages: background.vMag,
      capabilities,
      stationBuses: STATION_BUSES,
      price,
    });

    let safeKw = rawKw.slice();
    let relaxed = false;
    if (projectionEnabled) {
      const projected = projectCommand(sens, rawKw, {
        marginPu,
        uMinKw: capabilities.map((c) => c.maxDrawKw),
        uMaxKw: capabilities.map((c) => c.maxInjectKw),
      });
      safeKw = projected.safeKw;
      relaxed = projected.relaxed;
      if (relaxed) marginBreachedSteps++;
    } else {
      // Without the safety layer the command is still bounded by what the vehicles can
      // physically do — the projection is what is removed, not the laws of the fleet.
      safeKw = rawKw.map((value, k) =>
        Math.min(capabilities[k].maxInjectKw, Math.max(capabilities[k].maxDrawKw, value)),
      );
    }

    // Apply the executed command and solve the feeder for real.
    stationP.set(ws.baseP);
    for (let k = 0; k < STATION_BUSES.length; k++) {
      stationP[STATION_BUSES[k]] -= safeKw[k] / KW_PER_PU;
    }
    const result = solvePowerFlow(ws.net, stationP, ws.baseQ);
    const { bus: vMinBus, vMin } = minimumVoltage(result);
    const violations = countViolations(result.vMag);

    // Move energy and money.
    let stepCost = 0;
    for (let k = 0; k < STATION_BUSES.length; k++) {
      const outcome = dispatchStation(ws.fleet, ws.state, k, safeKw[k]);
      stepCost += outcome.energyBoughtKwh * price;
      stepCost -= outcome.energySoldKwh * price;
      stepCost += outcome.throughputKwh * DEGRADATION_COST_PER_KWH;
    }

    violationPairs += violations;
    netCost += stepCost;
    totalLossKwh += (result.lossKw * 5) / 60;
    vMinPu = Math.min(vMinPu, vMin);

    steps.push({
      step,
      rawKw,
      safeKw,
      voltages: result.vMag,
      vMin,
      vMinBus,
      violations,
      lossKw: result.lossKw,
      price,
      costUsd: stepCost,
      connected: capabilities.reduce((sum, c) => sum + c.connected, 0),
      relaxed,
    });
  }

  // Anyone still plugged in at midnight is scored where they stand.
  for (let i = 0; i < ws.fleet.length; i++) {
    if (ws.state[i].departedSoc === null) ws.state[i].departedSoc = ws.state[i].soc;
  }
  let met = 0;
  for (let i = 0; i < ws.fleet.length; i++) {
    if ((ws.state[i].departedSoc ?? 0) >= ws.fleet[i].targetSoc - 1e-6) met++;
  }

  return {
    controllerId: controller.id,
    label: controller.label,
    provenance: controller.provenance,
    note: controller.note,
    grid,
    projectionEnabled,
    steps,
    violationRate: violationPairs / (STEPS_PER_DAY * N_BUS),
    socMet: met / ws.fleet.length,
    netCostUsd: netCost,
    vMinPu,
    marginBreachedFraction: marginBreachedSteps / STEPS_PER_DAY,
    totalLossKwh,
  };
}
