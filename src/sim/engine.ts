/**
 * GridKeeper simulation engine.
 *
 * The model that matters is the swing equation. System frequency is driven by
 * the instantaneous power imbalance, damped by the aggregate inertia of every
 * machine electrically present:
 *
 *     df/dt = (P_gen - P_load) * f_nominal / (2 * Sum(H_i * S_i))
 *
 * While the grid tie is closed the transmission system dominates that sum, so
 * frequency barely moves. When the tie opens, the sum collapses to whatever is
 * left on site — and if the battery is in grid-following mode, that is only the
 * diesel machine. The district then loses frequency faster than the genset can
 * ramp, and the under-frequency relays start shedding blocks.
 *
 * That is the lesson the simulation exists to teach: displacing synchronous
 * generation with inverter-based renewables removes inertia, and the deficit
 * has to be bought back deliberately with grid-forming storage.
 */

import {
  DEFAULT_SCENARIO,
  GRID_EQUIVALENT_KVA,
  ambientTemperature,
  clearSkyFraction,
  hourIndex,
  loadShape,
  thermalMultiplier,
  windFraction,
} from './scenario';
import {
  DT_SECONDS,
  F_NOMINAL,
  SECONDS_PER_DAY,
  type ActionRecord,
  type DispatchCommand,
  type LoadId,
  type LoadState,
  type Scenario,
  type SimState,
  type TelemetryRow,
} from './types';

/** Normal operating band. Outside this the operator is accruing a penalty. */
export const BAND_LOW = 49.8;
export const BAND_HIGH = 50.2;
/** Under-frequency load shedding pickup. Real relays sit around here. */
export const UFLS_THRESHOLD = 49.0;
/**
 * Stage-1 relays are deliberately time-delayed so they ride through transients
 * rather than tripping on the first excursion. Without this the district sheds
 * load every time a cloud crosses the array.
 */
export const UFLS_PICKUP_SECONDS = 2;
export const UFLS_STAGE_INTERVAL_SECONDS = 2;
/**
 * Load damping constant, %/Hz expressed per unit. Motor load draws less power
 * as frequency falls, which partially self-arrests an excursion. 1.5 is a
 * conventional planning value.
 */
export const LOAD_DAMPING = 1.5;
/**
 * Inertia contributed by the rotating load itself — pumps, compressors,
 * industrial drives — referred to connected load. A distribution network is
 * never truly inertia-free while motors are spinning.
 */
export const LOAD_INERTIA_SECONDS = 0.5;
/** Below this the district has collapsed and everything trips. */
export const COLLAPSE_THRESHOLD = 47.5;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export interface RunLog {
  telemetry: TelemetryRow[];
  actions: ActionRecord[];
}

interface Internals {
  uflsPickupSeconds: number;
  lastUflsStageAt: number;
  trippedBlocks: Set<LoadId>;
  collapsed: boolean;
}

const internals = new WeakMap<SimState, Internals>();

export function createInitialState(scenario: Scenario = DEFAULT_SCENARIO): SimState {
  const loads = {} as Record<LoadId, LoadState>;
  for (const spec of scenario.site.loads) {
    loads[spec.id] = {
      id: spec.id,
      demandKw: 0,
      servedKw: 0,
      servedKwh: 0,
      unservedKwh: 0,
      outageSeconds: 0,
      hardFailed: false,
    };
  }

  const state: SimState = {
    t: 0,
    frequencyHz: F_NOMINAL,
    imbalanceKw: 0,
    inertiaSeconds: 0,
    pvKw: 0,
    windKw: 0,
    batteryKw: 0,
    batterySoc: 0.55,
    gensetKw: 0,
    gensetRunning: false,
    gensetStartingSeconds: 0,
    gensetStateSeconds: 0,
    gridKw: 0,
    gridConnected: true,
    loads,
    costUsd: 0,
    co2Kg: 0,
    offBandSeconds: 0,
    underFrequencySeconds: 0,
    uflsTrips: [],
    collapsed: false,
    collapsedAt: null,
    ambientC: 0,
    importPriceUsdPerKwh: 0,
    gridCarbonKgPerKwh: 0,
    activeEvents: [],
    done: false,
  };

  internals.set(state, {
    uflsPickupSeconds: 0,
    lastUflsStageAt: -Infinity,
    trippedBlocks: new Set(),
    collapsed: false,
  });

  return state;
}

export function defaultCommand(scenario: Scenario = DEFAULT_SCENARIO): DispatchCommand {
  const loadAllowance = {} as Record<LoadId, number>;
  for (const spec of scenario.site.loads) loadAllowance[spec.id] = 1;
  return {
    batteryPowerKw: 0,
    batteryGridForming: false,
    gensetRunRequested: false,
    loadAllowance,
  };
}

/** Which scripted events are active at time `t`, and their parameters. */
function activeEvents(scenario: Scenario, t: number) {
  let demandMultiplier = 1;
  let pvFraction = 1;
  let windFractionScale = 1;
  let priceMultiplier = 1;
  let tieOpen = false;
  const kinds: SimState['activeEvents'] = [];

  for (const ev of scenario.events) {
    if (t < ev.at || t >= ev.at + (ev.kind === 'feederFault' ? ev.durationS : ev.durationS)) {
      continue;
    }
    kinds.push(ev.kind);
    switch (ev.kind) {
      case 'heatwave':
        demandMultiplier *= ev.demandMultiplier;
        break;
      case 'cloud':
        pvFraction *= ev.outputFraction;
        break;
      case 'windLull':
        windFractionScale *= ev.outputFraction;
        break;
      case 'priceSpike':
        priceMultiplier *= ev.multiplier;
        break;
      case 'feederFault':
        tieOpen = true;
        break;
    }
  }

  return { demandMultiplier, pvFraction, windFractionScale, priceMultiplier, tieOpen, kinds };
}

/**
 * Aggregate inertia present on the system, expressed as Sum(H_i * S_i) in kW·s.
 * This is the denominator of the swing equation and the single most important
 * number in the simulation.
 */
export function aggregateInertiaKwS(
  state: SimState,
  scenario: Scenario,
  gridForming: boolean,
  connectedLoadKw = 0,
): number {
  const { genset, battery, grid } = scenario.site;
  let total = 0;
  if (state.gridConnected) total += grid.equivalentInertiaSeconds * GRID_EQUIVALENT_KVA;
  if (state.gensetRunning) total += genset.inertiaSeconds * genset.ratedKw;
  // A grid-following inverter contributes nothing. Only grid-forming control
  // synthesises inertia.
  if (gridForming) total += battery.gridFormingInertiaSeconds * battery.maxDischargeKw;
  // Rotating load keeps the denominator finite even in a bare island.
  total += LOAD_INERTIA_SECONDS * connectedLoadKw;
  return Math.max(200, total);
}

export function step(
  state: SimState,
  command: DispatchCommand,
  scenario: Scenario = DEFAULT_SCENARIO,
  log?: RunLog,
): SimState {
  if (state.done) return state;

  const priv = internals.get(state)!;
  const dt = DT_SECONDS;
  const { site } = scenario;
  const ev = activeEvents(scenario, state.t);

  state.gridConnected = !ev.tieOpen;
  state.activeEvents = ev.kinds;

  // --- environment -------------------------------------------------------
  const hour = hourIndex(state.t);
  state.ambientC = ambientTemperature(state.t, scenario.peakTemperatureC) +
    (ev.demandMultiplier > 1 ? 6 : 0);
  state.importPriceUsdPerKwh = scenario.importPriceByHour[hour] * ev.priceMultiplier;
  state.gridCarbonKgPerKwh = scenario.gridCarbonByHour[hour];

  // --- demand ------------------------------------------------------------
  let totalDemandKw = 0;
  let totalServedKw = 0;

  for (const spec of site.loads) {
    const ls = state.loads[spec.id];
    const tripped = priv.trippedBlocks.has(spec.id) || priv.collapsed;

    const base = loadShape(spec.id, state.t) * spec.peakKw;
    const demand = base * thermalMultiplier(state.ambientC, spec.thermalSensitivity);
    ls.demandKw = demand;

    const allowance = tripped ? 0 : clamp(command.loadAllowance[spec.id] ?? 1, 0, 1);
    // A block can never be held below its own floor unless it is fully shed.
    const effective = allowance <= 0 ? 0 : Math.max(allowance, spec.floorFraction);
    ls.servedKw = demand * effective;

    const shortfallKw = demand - ls.servedKw;
    ls.unservedKwh += (shortfallKw * dt) / 3600;
    ls.servedKwh += (ls.servedKw * dt) / 3600;

    if (demand > 1 && ls.servedKw < demand * 0.05) {
      ls.outageSeconds += dt;
      if (ls.outageSeconds > spec.ridethroughSeconds) ls.hardFailed = true;
    } else {
      ls.outageSeconds = 0;
    }

    totalDemandKw += demand;
    totalServedKw += ls.servedKw;
  }

  // --- renewable generation ---------------------------------------------
  state.pvKw = site.pv.ratedKw * clearSkyFraction(state.t) * ev.pvFraction;
  state.windKw =
    site.wind.ratedKw * windFraction(state.t, scenario.seed) * ev.windFractionScale;

  // --- genset state machine ---------------------------------------------
  const g = site.genset;
  state.gensetStateSeconds += dt;

  if (command.gensetRunRequested && !state.gensetRunning) {
    if (state.gensetStartingSeconds === 0 && state.gensetStateSeconds >= g.minDownSeconds) {
      state.gensetStartingSeconds = dt;
    } else if (state.gensetStartingSeconds > 0) {
      state.gensetStartingSeconds += dt;
      if (state.gensetStartingSeconds >= g.startupSeconds) {
        state.gensetRunning = true;
        state.gensetStartingSeconds = 0;
        state.gensetStateSeconds = 0;
        state.gensetKw = g.ratedKw * g.minLoadFraction;
      }
    }
  } else if (!command.gensetRunRequested && state.gensetRunning) {
    if (state.gensetStateSeconds >= g.minUpSeconds) {
      state.gensetRunning = false;
      state.gensetKw = 0;
      state.gensetStateSeconds = 0;
    }
  } else if (!command.gensetRunRequested) {
    state.gensetStartingSeconds = 0;
  }

  // --- battery -----------------------------------------------------------
  const b = site.battery;
  const gridForming = command.batteryGridForming;

  // The distinction the simulation exists to teach.
  //
  // A grid-FOLLOWING inverter is a current source: it measures frequency and
  // then reacts, so its support always arrives a control cycle late and it
  // contributes no inertia at all.
  //
  // A grid-FORMING inverter is a voltage source behind an impedance. It picks
  // up the instantaneous power imbalance without waiting to measure anything,
  // which is why it can hold an island together and a following inverter
  // cannot.
  let supportKw = 0;
  if (gridForming) {
    if (state.gridConnected) {
      // The tie is the slack source, so the inverter only trims on droop.
      const deltaF = F_NOMINAL - state.frequencyHz;
      supportKw = (deltaF / F_NOMINAL / 0.02) * b.maxDischargeKw;
    } else {
      // Islanded: cover whatever the other sources are not carrying. The
      // genset's output from the previous step is used, which is sound because
      // it is ramp-limited and moves very little in one second.
      const carriedKw = state.pvKw + state.windKw + state.gensetKw + command.batteryPowerKw;
      supportKw = totalServedKw - carriedKw;
    }
  }

  let batteryKw = clamp(
    command.batteryPowerKw + supportKw,
    -b.maxChargeKw,
    b.maxDischargeKw,
  );

  // Enforce state-of-charge limits.
  const sqrtEta = Math.sqrt(b.roundTripEfficiency);
  if (batteryKw > 0) {
    const availableKwh = (state.batterySoc - b.minSoc) * b.capacityKwh;
    const maxKw = (availableKwh * 3600 * sqrtEta) / dt;
    batteryKw = Math.min(batteryKw, Math.max(0, maxKw));
  } else if (batteryKw < 0) {
    const headroomKwh = (b.maxSoc - state.batterySoc) * b.capacityKwh;
    const maxKw = (headroomKwh * 3600) / (dt * sqrtEta);
    batteryKw = Math.max(batteryKw, -Math.max(0, maxKw));
  }

  if (batteryKw > 0) {
    state.batterySoc -= (batteryKw * dt) / 3600 / sqrtEta / b.capacityKwh;
  } else if (batteryKw < 0) {
    state.batterySoc += ((-batteryKw * dt) / 3600) * sqrtEta / b.capacityKwh;
  }
  state.batterySoc = clamp(state.batterySoc, 0, 1);
  state.batteryKw = batteryKw;

  // --- genset dispatch ---------------------------------------------------
  // While islanded the diesel machine is the swing unit: it chases the deficit,
  // but only as fast as its ramp allows.
  if (state.gensetRunning) {
    const deficit = totalServedKw - (state.pvKw + state.windKw + batteryKw);
    const droopKw =
      ((F_NOMINAL - state.frequencyHz) / F_NOMINAL / g.droop) * g.ratedKw;
    const target = clamp(
      (state.gridConnected ? state.gensetKw : deficit) + droopKw,
      g.ratedKw * g.minLoadFraction,
      g.ratedKw,
    );
    const maxStep = g.rampKwPerSecond * dt;
    state.gensetKw += clamp(target - state.gensetKw, -maxStep, maxStep);
  } else {
    state.gensetKw = 0;
  }

  // --- grid tie ----------------------------------------------------------
  const localGenKw = state.pvKw + state.windKw + state.batteryKw + state.gensetKw;
  const needKw = totalServedKw - localGenKw;
  state.gridKw = state.gridConnected
    ? clamp(needKw, -site.grid.exportLimitKw, site.grid.importLimitKw)
    : 0;

  // --- swing equation ----------------------------------------------------
  // Motor load draws less as frequency falls, which partially self-arrests an
  // excursion. This is the damping term of the standard swing model.
  const dampingFactor =
    1 + (LOAD_DAMPING * (state.frequencyHz - F_NOMINAL)) / F_NOMINAL;
  const dampedServedKw = totalServedKw * clamp(dampingFactor, 0.6, 1.4);

  const imbalanceKw = localGenKw + state.gridKw - dampedServedKw;
  state.imbalanceKw = imbalanceKw;

  const inertiaKwS = aggregateInertiaKwS(state, scenario, gridForming, totalServedKw);
  state.inertiaSeconds = inertiaKwS / Math.max(1, totalDemandKw);

  const dfdt = (imbalanceKw * F_NOMINAL) / (2 * inertiaKwS);
  state.frequencyHz += dfdt * dt;

  // While the tie is closed the wider system pins frequency to nominal.
  if (state.gridConnected) {
    state.frequencyHz += (F_NOMINAL - state.frequencyHz) * 0.5 * dt;
  }
  state.frequencyHz = clamp(state.frequencyHz, 45, 55);

  // --- protection --------------------------------------------------------
  if (state.frequencyHz < BAND_LOW || state.frequencyHz > BAND_HIGH) {
    state.offBandSeconds += dt;
  }

  if (state.frequencyHz < UFLS_THRESHOLD) {
    state.underFrequencySeconds += dt;
    priv.uflsPickupSeconds += dt;

    const canStage =
      priv.uflsPickupSeconds >= UFLS_PICKUP_SECONDS &&
      state.t - priv.lastUflsStageAt >= UFLS_STAGE_INTERVAL_SECONDS;

    if (canStage) {
      const candidate = [...site.loads]
        .filter((s) => !priv.trippedBlocks.has(s.id) && state.loads[s.id].servedKw > 1)
        .sort((a, b2) => b2.shedPriority - a.shedPriority)[0];
      if (candidate) {
        priv.trippedBlocks.add(candidate.id);
        state.uflsTrips.push(candidate.id);
        priv.lastUflsStageAt = state.t;
        log?.actions.push({
          t: state.t,
          kind: 'shed',
          detail: `Under-frequency relay tripped ${candidate.label} at ${state.frequencyHz.toFixed(2)} Hz`,
        });
      }
    }
  } else {
    priv.uflsPickupSeconds = 0;
  }

  if (state.frequencyHz < COLLAPSE_THRESHOLD && !priv.collapsed) {
    priv.collapsed = true;
    state.collapsed = true;
    state.collapsedAt = state.t;
    for (const spec of site.loads) priv.trippedBlocks.add(spec.id);
    log?.actions.push({
      t: state.t,
      kind: 'shed',
      detail: 'System collapse — every block tripped',
    });
  }

  // --- cost and carbon ---------------------------------------------------
  const hours = dt / 3600;

  if (state.gridKw > 0) {
    state.costUsd += state.gridKw * hours * state.importPriceUsdPerKwh;
    state.co2Kg += state.gridKw * hours * state.gridCarbonKgPerKwh;
  } else if (state.gridKw < 0) {
    // Export earns a fraction of the import price.
    state.costUsd += state.gridKw * hours * state.importPriceUsdPerKwh * 0.4;
  }

  if (state.gensetRunning) {
    const litres = (g.noLoadFuelLph + g.marginalFuelLphPerKw * state.gensetKw) * hours;
    state.costUsd += litres * g.fuelCostPerLitre;
    state.co2Kg += litres * g.co2KgPerLitre;
  }

  state.costUsd += Math.abs(state.batteryKw) * hours * b.degradationCostPerKwh;

  // Calling the industrial demand-response contract is not free.
  const industrialAllowance = command.loadAllowance.industrial ?? 1;
  if (industrialAllowance < 1 && !priv.trippedBlocks.has('industrial')) {
    const curtailedKw = state.loads.industrial.demandKw * (1 - industrialAllowance);
    state.costUsd += curtailedKw * hours * 0.35;
  }

  // --- telemetry ---------------------------------------------------------
  if (log && state.t % 60 === 0) {
    log.telemetry.push({
      t: state.t,
      frequencyHz: state.frequencyHz,
      batterySoc: state.batterySoc,
      pvKw: state.pvKw,
      windKw: state.windKw,
      batteryKw: state.batteryKw,
      gensetKw: state.gensetKw,
      gridKw: state.gridKw,
      totalDemandKw,
      totalServedKw,
      costUsd: state.costUsd,
      co2Kg: state.co2Kg,
    });
  }

  state.t += dt;
  if (state.t >= SECONDS_PER_DAY) state.done = true;

  return state;
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

export interface RunScore {
  unservedKwh: number;
  weightedUnservedKwh: number;
  hospitalMinutesLost: number;
  /** Outage minutes accrued by blocks containing vulnerable occupants. */
  vulnerableOutageMinutes: number;
  vulnerableOccupantsAffected: number;
  co2Kg: number;
  costUsd: number;
  gramsCo2PerKwhServed: number;
  offBandMinutes: number;
  uflsTrips: number;
  collapsed: boolean;
  servedKwh: number;
}

export function scoreRun(state: SimState, scenario: Scenario = DEFAULT_SCENARIO): RunScore {
  let unservedKwh = 0;
  let weighted = 0;
  let vulnerableOutageMinutes = 0;
  let vulnerableOccupantsAffected = 0;
  let servedKwh = 0;

  for (const spec of scenario.site.loads) {
    const ls = state.loads[spec.id];
    unservedKwh += ls.unservedKwh;
    servedKwh += ls.servedKwh;
    weighted += ls.unservedKwh * spec.criticalityWeight;
    if (spec.vulnerableOccupants > 0 && ls.unservedKwh > 0) {
      vulnerableOccupantsAffected += spec.vulnerableOccupants;
      vulnerableOutageMinutes += ls.unservedKwh > 0 ? ls.outageSeconds / 60 : 0;
    }
  }

  const hospital = state.loads.hospital;

  return {
    unservedKwh,
    weightedUnservedKwh: weighted,
    hospitalMinutesLost: hospital.outageSeconds / 60,
    vulnerableOutageMinutes,
    vulnerableOccupantsAffected,
    co2Kg: state.co2Kg,
    costUsd: state.costUsd,
    gramsCo2PerKwhServed: servedKwh > 0 ? (state.co2Kg * 1000) / servedKwh : 0,
    offBandMinutes: state.offBandSeconds / 60,
    uflsTrips: state.uflsTrips.length,
    collapsed: state.collapsed,
    servedKwh,
  };
}
