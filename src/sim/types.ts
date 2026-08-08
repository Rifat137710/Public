/**
 * GridKeeper simulation types.
 *
 * Units are kept consistent and explicit throughout:
 *   power      kW
 *   energy     kWh
 *   frequency  Hz
 *   inertia    seconds (constant H, referred to machine rating)
 *   cost       USD
 *   carbon     kg CO2
 *
 * The simulation runs at a fixed 1-second timestep so the swing equation
 * resolves frequency transients properly. A 24-hour scenario is 86,400 steps,
 * which runs headless in well under a second.
 */

export const DT_SECONDS = 1;
export const F_NOMINAL = 50.0;
export const SECONDS_PER_DAY = 86_400;

/** Load blocks, in descending order of how critical they are to keep energised. */
export type LoadId =
  | 'hospital'
  | 'water'
  | 'residential'
  | 'datacenter'
  | 'school'
  | 'industrial';

export type AssetId = 'pv' | 'wind' | 'battery' | 'genset' | 'grid';

/**
 * How a load may be reduced.
 *  - `firm`        cannot be reduced at all without an outage
 *  - `curtailable` can be throttled to a floor fraction (e.g. workload migration)
 *  - `deferrable`  can be shifted in time (e.g. pumping into stored head)
 *  - `contracted`  demand-response contract; sheds a fixed fraction, incurs a penalty
 */
export type LoadFlexibility = 'firm' | 'curtailable' | 'deferrable' | 'contracted';

export interface LoadSpec {
  id: LoadId;
  label: string;
  /** Higher number sheds first. Under-frequency relays walk this order. */
  shedPriority: number;
  peakKw: number;
  flexibility: LoadFlexibility;
  /** Lowest fraction of nominal demand this block can be run at. */
  floorFraction: number;
  /** Backup runtime in seconds before an outage becomes a hard failure. */
  ridethroughSeconds: number;
  /**
   * Residents or occupants whose safety depends on continuity of supply.
   * Deliberately not surfaced on the main dispatch view — the operator has to
   * open the block's detail panel to see it. This is the ethical tradeoff the
   * debrief reports on.
   */
  vulnerableOccupants: number;
  /** Multiplier applied to unserved energy when scoring. */
  criticalityWeight: number;
  /** Fraction of the block's demand that is temperature-driven (cooling). */
  thermalSensitivity: number;
}

export interface BatterySpec {
  capacityKwh: number;
  maxChargeKw: number;
  maxDischargeKw: number;
  /** Round-trip efficiency; the square root is applied on each leg. */
  roundTripEfficiency: number;
  minSoc: number;
  maxSoc: number;
  /** Marginal cost of cycling, USD per kWh of throughput. */
  degradationCostPerKwh: number;
  /**
   * In grid-forming mode the inverter contributes synthetic inertia and fast
   * frequency response. In grid-following mode it does neither — which is the
   * whole point of the lesson.
   */
  gridFormingInertiaSeconds: number;
}

export interface GensetSpec {
  ratedKw: number;
  minLoadFraction: number;
  /** Seconds from a start command to the unit being able to carry load. */
  startupSeconds: number;
  /** Ramp limit once running, kW per second. */
  rampKwPerSecond: number;
  /** Minimum time the unit must stay running / stay off once switched. */
  minUpSeconds: number;
  minDownSeconds: number;
  /** Fuel curve intercept and slope, litres/hour at zero load and per kW. */
  noLoadFuelLph: number;
  marginalFuelLphPerKw: number;
  fuelCostPerLitre: number;
  co2KgPerLitre: number;
  /** Inertia constant of the synchronous machine, referred to its own rating. */
  inertiaSeconds: number;
  /** Governor droop, per unit (0.05 = 5%). */
  droop: number;
}

export interface GridTieSpec {
  importLimitKw: number;
  exportLimitKw: number;
  /**
   * Effective inertia the transmission system contributes to this district
   * while the tie is closed. Large, and its disappearance on islanding is what
   * makes the 18:40 fault dangerous.
   */
  equivalentInertiaSeconds: number;
}

export interface RenewableSpec {
  ratedKw: number;
}

export interface SiteSpec {
  loads: LoadSpec[];
  pv: RenewableSpec;
  wind: RenewableSpec;
  battery: BatterySpec;
  genset: GensetSpec;
  grid: GridTieSpec;
}

/** A scripted disturbance. `at` is seconds from midnight. */
export type SimEvent =
  | { kind: 'heatwave'; at: number; durationS: number; demandMultiplier: number }
  | { kind: 'cloud'; at: number; durationS: number; outputFraction: number }
  | { kind: 'windLull'; at: number; durationS: number; outputFraction: number }
  | { kind: 'feederFault'; at: number; durationS: number }
  | { kind: 'priceSpike'; at: number; durationS: number; multiplier: number };

export interface Scenario {
  id: string;
  label: string;
  seed: number;
  site: SiteSpec;
  events: SimEvent[];
  /** Import price in USD/kWh, sampled hourly (24 entries). */
  importPriceByHour: number[];
  /** Grid carbon intensity in kg CO2/kWh, sampled hourly (24 entries). */
  gridCarbonByHour: number[];
  /** Peak ambient temperature in °C, used to drive cooling load. */
  peakTemperatureC: number;
}

/** Operator commands. The UI writes these; the engine reads them each step. */
export interface DispatchCommand {
  /** Positive discharges, negative charges, kW. Clamped to the battery's limits. */
  batteryPowerKw: number;
  batteryGridForming: boolean;
  gensetRunRequested: boolean;
  /** Per-load fraction of nominal demand the operator is allowing, 0..1. */
  loadAllowance: Record<LoadId, number>;
}

export interface LoadState {
  id: LoadId;
  /** What the block would draw if unconstrained, kW. */
  demandKw: number;
  /** What it is actually being served, kW. */
  servedKw: number;
  /** Cumulative energy actually delivered to the block, kWh. */
  servedKwh: number;
  /** Cumulative energy the block asked for but did not receive, kWh. */
  unservedKwh: number;
  /** Seconds this block has been below its ride-through threshold. */
  outageSeconds: number;
  /** True once an outage has exceeded the block's ride-through. */
  hardFailed: boolean;
}

export interface SimState {
  /** Seconds since midnight. */
  t: number;
  frequencyHz: number;
  /** Net power imbalance driving the swing equation, kW. */
  imbalanceKw: number;
  /** Aggregate system inertia constant referred to total rating, seconds. */
  inertiaSeconds: number;

  pvKw: number;
  windKw: number;
  batteryKw: number;
  batterySoc: number;
  gensetKw: number;
  gensetRunning: boolean;
  gensetStartingSeconds: number;
  gensetStateSeconds: number;
  gridKw: number;
  gridConnected: boolean;

  loads: Record<LoadId, LoadState>;

  costUsd: number;
  co2Kg: number;
  /** Minutes spent outside the 49.8–50.2 Hz normal band. */
  offBandSeconds: number;
  /** Seconds spent below the 49.0 Hz UFLS threshold. */
  underFrequencySeconds: number;
  /** Blocks tripped automatically by the under-frequency relay this run. */
  uflsTrips: LoadId[];
  /** Set once frequency fell far enough to take the whole district down. */
  collapsed: boolean;
  /** Time of collapse, seconds since midnight, or null if it never happened. */
  collapsedAt: number | null;

  ambientC: number;
  importPriceUsdPerKwh: number;
  gridCarbonKgPerKwh: number;

  activeEvents: SimEvent['kind'][];
  done: boolean;
}

/** One row of the run log, recorded once per simulated minute. */
export interface TelemetryRow {
  t: number;
  frequencyHz: number;
  batterySoc: number;
  pvKw: number;
  windKw: number;
  batteryKw: number;
  gensetKw: number;
  gridKw: number;
  totalDemandKw: number;
  totalServedKw: number;
  costUsd: number;
  co2Kg: number;
}

/** An operator action, recorded for the after-action debrief. */
export interface ActionRecord {
  t: number;
  kind: 'battery' | 'genset' | 'shed' | 'restore' | 'gridForming';
  detail: string;
}
