/**
 * The interactive stepper.
 *
 * The learner drives the feeder one five-minute step at a time, so the simulation has
 * to be advanceable rather than only runnable-to-completion. This class is that: it
 * holds the network, the fleet and the clock, and exposes exactly what the interface
 * needs to draw a moment.
 *
 * It is also the *only* implementation of a step. `runEpisode` drives this same class
 * in a loop rather than keeping its own copy of the physics, so what a learner
 * experiences and what the headless harness verifies can never drift apart.
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
import { DEFAULT_MARGIN_PU, V_LOWER, V_UPPER, projectCommand } from './projection.js';
import {
  DEGRADATION_COST_PER_KWH,
  buildFleet,
  dispatchStation,
  initialFleetState,
  stationCapabilities,
  updateConnections,
  type StationCapability,
  type Vehicle,
  type VehicleState,
} from './fleet.js';
import { STEPS_PER_DAY, clearSkyFraction, loadShape, touPrice } from './profiles.js';
import type { Controller } from './controllers.js';

/** Installed rooftop solar at each PV bus, kW. */
export const PV_CAPACITY_KW = 250;

export interface ScenarioOptions {
  grid?: GridKind;
  /** Fraction of nameplate demand at the evening peak. The reference study studies 0.50. */
  loadScale?: number;
  seed?: number;
  /**
   * Force the safety layer on or off, overriding the controller's own default.
   * Leave undefined for the honest comparison: only Shielded RL is projected.
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
  /** Bus voltages before the command, for the "what did I change" readout. */
  backgroundVoltages: Float64Array;
  vMin: number;
  vMinBus: number;
  /** Buses outside [0.95, 1.05] this step. */
  violations: number;
  lossKw: number;
  price: number;
  costUsd: number;
  connected: number;
  solarKw: number;
  /** True when the margin-tightened band was already breached before any command. */
  relaxed: boolean;
  projectionEnabled: boolean;
}

export interface RunningTotals {
  violationRate: number;
  socMet: number;
  netCostUsd: number;
  vMinPu: number;
  marginBreachedFraction: number;
  totalLossKwh: number;
}

export class LiveSim {
  readonly net: Network;
  readonly grid: GridKind;
  readonly loadScale: number;
  readonly solarScale: number;
  readonly seed: number;
  readonly marginPu: number;
  readonly stationBuses = STATION_BUSES;

  private fleet: Vehicle[];
  private fleetState: VehicleState[];
  private baseP: Float64Array;
  private baseQ: Float64Array;
  private stationP: Float64Array;

  private _step = 0;
  private violationPairs = 0;
  private marginBreachedSteps = 0;
  private netCost = 0;
  private lossKwh = 0;
  private worstV = Infinity;

  /** Sensitivities about the current background operating point. */
  sensitivities: Sensitivities;
  /** Voltages of the background operating point, before any command this step. */
  background: Float64Array;
  capabilities: StationCapability[];
  /** The most recent completed step, or null before the first advance. */
  last: StepRecord | null = null;

  constructor(options: ScenarioOptions = {}) {
    this.grid = options.grid ?? 'weak';
    this.loadScale = options.loadScale ?? 0.5;
    this.solarScale = options.solarScale ?? 1.0;
    this.seed = options.seed ?? 137710;
    this.marginPu = options.marginPu ?? DEFAULT_MARGIN_PU;

    this.net = buildNetwork(sourceImpedanceFor(this.grid));
    this.fleet = buildFleet({ seed: this.seed, stationCount: STATION_BUSES.length });
    this.fleetState = initialFleetState(this.fleet);
    this.baseP = new Float64Array(this.net.nodeCount);
    this.baseQ = new Float64Array(this.net.nodeCount);
    this.stationP = new Float64Array(this.net.nodeCount);

    this.background = new Float64Array(this.net.nodeCount);
    this.capabilities = [];
    this.sensitivities = { stationBuses: STATION_BUSES, dvdp: [], dvdq: [], v0: this.background };
    this.prepareStep();
  }

  get step(): number {
    return this._step;
  }

  get finished(): boolean {
    return this._step >= STEPS_PER_DAY;
  }

  get vehicles(): readonly Vehicle[] {
    return this.fleet;
  }

  get vehicleStates(): readonly VehicleState[] {
    return this.fleetState;
  }

  /** Solar output at this step, kW per PV bus. */
  get solarKw(): number {
    return clearSkyFraction(this._step) * PV_CAPACITY_KW * this.solarScale;
  }

  get price(): number {
    return touPrice(Math.min(this._step, STEPS_PER_DAY - 1));
  }

  /**
   * Establish the background operating point for the step about to be taken, and
   * measure the sensitivities on it. Called before the controller is consulted, so the
   * command is chosen against the feeder as it actually stands.
   */
  private prepareStep(): void {
    const step = Math.min(this._step, STEPS_PER_DAY - 1);
    updateConnections(this.fleet, this.fleetState, step);

    const nominal = nominalLoadPu(loadShape(step) * this.loadScale);
    this.baseP.set(nominal.p);
    this.baseQ.set(nominal.q);

    const solar = clearSkyFraction(step) * PV_CAPACITY_KW * this.solarScale;
    if (solar > 0) {
      for (const bus of PV_BUSES) this.baseP[bus] -= solar / KW_PER_PU;
    }

    this.background = solvePowerFlow(this.net, this.baseP, this.baseQ).vMag;
    this.sensitivities = measureSensitivities(this.net, this.baseP, this.baseQ, STATION_BUSES);
    this.capabilities = stationCapabilities(this.fleet, this.fleetState, STATION_BUSES.length);
  }

  /**
   * Project a command without executing it. The interface calls this on every slider
   * move so the second handle can track what the safety layer would actually allow.
   */
  preview(rawKw: readonly number[]): { safeKw: number[]; relaxed: boolean } {
    const projected = projectCommand(this.sensitivities, rawKw, {
      marginPu: this.marginPu,
      uMinKw: this.capabilities.map((c) => c.maxDrawKw),
      uMaxKw: this.capabilities.map((c) => c.maxInjectKw),
    });
    return { safeKw: projected.safeKw, relaxed: projected.relaxed };
  }

  /** Clamp a command to what the connected vehicles can physically do. */
  clampToFleet(rawKw: readonly number[]): number[] {
    return this.capabilities.map((cap, k) =>
      Math.min(cap.maxInjectKw, Math.max(cap.maxDrawKw, rawKw[k] ?? 0)),
    );
  }

  /** Execute one five-minute step. */
  advance(rawKw: readonly number[], projectionEnabled: boolean): StepRecord {
    if (this.finished) {
      throw new Error('the day is over — call reset() to run it again');
    }
    const step = this._step;
    const backgroundVoltages = this.background;

    let safeKw: number[];
    let relaxed = false;
    if (projectionEnabled) {
      const projected = this.preview(rawKw);
      safeKw = projected.safeKw;
      relaxed = projected.relaxed;
      if (relaxed) this.marginBreachedSteps++;
    } else {
      // Removing the safety layer does not repeal the laws of the fleet.
      safeKw = this.clampToFleet(rawKw);
    }

    this.stationP.set(this.baseP);
    for (let k = 0; k < STATION_BUSES.length; k++) {
      this.stationP[STATION_BUSES[k]] -= safeKw[k] / KW_PER_PU;
    }
    const result = solvePowerFlow(this.net, this.stationP, this.baseQ);
    const { bus: vMinBus, vMin } = minimumVoltage(result);

    let violations = 0;
    for (let bus = 1; bus <= N_BUS; bus++) {
      if (result.vMag[bus] < V_LOWER || result.vMag[bus] > V_UPPER) violations++;
    }

    const price = touPrice(step);
    let costUsd = 0;
    for (let k = 0; k < STATION_BUSES.length; k++) {
      const outcome = dispatchStation(this.fleet, this.fleetState, k, safeKw[k]);
      costUsd += outcome.energyBoughtKwh * price;
      costUsd -= outcome.energySoldKwh * price;
      costUsd += outcome.throughputKwh * DEGRADATION_COST_PER_KWH;
    }

    this.violationPairs += violations;
    this.netCost += costUsd;
    this.lossKwh += (result.lossKw * 5) / 60;
    this.worstV = Math.min(this.worstV, vMin);

    const record: StepRecord = {
      step,
      rawKw: Array.from(rawKw),
      safeKw,
      voltages: result.vMag,
      backgroundVoltages,
      vMin,
      vMinBus,
      violations,
      lossKw: result.lossKw,
      price,
      costUsd,
      connected: this.capabilities.reduce((sum, c) => sum + c.connected, 0),
      solarKw: clearSkyFraction(step) * PV_CAPACITY_KW * this.solarScale,
      relaxed,
      projectionEnabled,
    };

    this.last = record;
    this._step++;
    if (!this.finished) this.prepareStep();
    return record;
  }

  /** Ask a controller for this step's command and take it. */
  advanceWith(controller: Controller, projectionOverride?: boolean): StepRecord {
    const rawKw = controller.command({
      step: Math.min(this._step, STEPS_PER_DAY - 1),
      voltages: this.background,
      capabilities: this.capabilities,
      stationBuses: STATION_BUSES,
      price: this.price,
    });
    return this.advance(rawKw, projectionOverride ?? controller.usesProjection);
  }

  /**
   * Scores as they stand right now. Service is counted over vehicles that have already
   * left, so a mid-day figure answers "of the drivers who have gone home, how many got
   * what they came for" rather than silently counting the ones still plugged in.
   */
  totals(): RunningTotals & { departed: number } {
    let departed = 0;
    let met = 0;
    for (let i = 0; i < this.fleet.length; i++) {
      const soc = this.fleetState[i].departedSoc;
      if (soc === null) continue;
      departed++;
      if (soc >= this.fleet[i].targetSoc - 1e-6) met++;
    }
    const stepsTaken = Math.max(1, this._step);
    return {
      departed,
      violationRate: this.violationPairs / (stepsTaken * N_BUS),
      socMet: departed === 0 ? 0 : met / departed,
      netCostUsd: this.netCost,
      vMinPu: this.worstV === Infinity ? 1 : this.worstV,
      marginBreachedFraction: this.marginBreachedSteps / stepsTaken,
      totalLossKwh: this.lossKwh,
    };
  }

  /** Final scores, counting everyone still plugged in at midnight where they stand. */
  finalTotals(): RunningTotals {
    let met = 0;
    for (let i = 0; i < this.fleet.length; i++) {
      const soc = this.fleetState[i].departedSoc ?? this.fleetState[i].soc;
      if (soc >= this.fleet[i].targetSoc - 1e-6) met++;
    }
    return {
      violationRate: this.violationPairs / (STEPS_PER_DAY * N_BUS),
      socMet: met / this.fleet.length,
      netCostUsd: this.netCost,
      vMinPu: this.worstV === Infinity ? 1 : this.worstV,
      marginBreachedFraction: this.marginBreachedSteps / STEPS_PER_DAY,
      totalLossKwh: this.lossKwh,
    };
  }

  reset(): void {
    this.fleetState = initialFleetState(this.fleet);
    this._step = 0;
    this.violationPairs = 0;
    this.marginBreachedSteps = 0;
    this.netCost = 0;
    this.lossKwh = 0;
    this.worstV = Infinity;
    this.last = null;
    this.prepareStep();
  }
}

export interface EpisodeResult extends RunningTotals {
  controllerId: string;
  label: string;
  provenance: string;
  note?: string;
  grid: GridKind;
  projectionEnabled: boolean;
  steps: StepRecord[];
}

/** Run one controller across a full day and score it. */
export function runEpisode(
  controller: Controller,
  options: ScenarioOptions = {},
): EpisodeResult {
  const sim = new LiveSim(options);
  controller.reset?.();

  const projectionEnabled = options.projectionOverride ?? controller.usesProjection;
  const steps: StepRecord[] = [];
  while (!sim.finished) {
    steps.push(sim.advanceWith(controller, projectionEnabled));
  }

  return {
    controllerId: controller.id,
    label: controller.label,
    provenance: controller.provenance,
    note: controller.note,
    grid: sim.grid,
    projectionEnabled,
    steps,
    ...sim.finalTotals(),
  };
}
