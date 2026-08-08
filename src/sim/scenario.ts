/**
 * The default GridKeeper scenario: a mixed-use city district on a hot summer
 * day, with an evening feeder fault that islands the microgrid at peak demand.
 *
 * Numbers are chosen to be plausible for a ~5 MW peak district rather than to
 * model any specific real site.
 */

import type { LoadId, LoadSpec, Scenario, SiteSpec } from './types';
import { SECONDS_PER_DAY } from './types';

/** Deterministic PRNG so every run of a given seed is byte-identical. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const LOADS: LoadSpec[] = [
  {
    id: 'hospital',
    label: 'Regional hospital',
    shedPriority: 1,
    peakKw: 800,
    flexibility: 'firm',
    floorFraction: 1.0,
    ridethroughSeconds: 900, // 15 minutes of UPS and standby
    vulnerableOccupants: 120,
    criticalityWeight: 10,
    thermalSensitivity: 0.15,
  },
  {
    id: 'residential',
    label: 'Residential tower',
    shedPriority: 2,
    peakKw: 900,
    flexibility: 'firm',
    floorFraction: 0.0,
    ridethroughSeconds: 0,
    // Home dialysis and oxygen concentrators. Visible only in the block detail
    // panel — the operator has to go looking.
    vulnerableOccupants: 40,
    criticalityWeight: 6,
    thermalSensitivity: 0.35,
  },
  {
    id: 'water',
    label: 'Water pumping station',
    shedPriority: 3,
    peakKw: 600,
    flexibility: 'deferrable',
    floorFraction: 0.0,
    ridethroughSeconds: 5400, // reservoir head buys ninety minutes
    vulnerableOccupants: 0,
    criticalityWeight: 4,
    thermalSensitivity: 0.0,
  },
  {
    id: 'datacenter',
    label: 'Edge data centre',
    shedPriority: 4,
    peakKw: 1200,
    flexibility: 'curtailable',
    floorFraction: 0.6, // workload migrates off-site below this
    ridethroughSeconds: 300,
    vulnerableOccupants: 0,
    criticalityWeight: 2,
    thermalSensitivity: 0.25,
  },
  {
    id: 'industrial',
    label: 'Industrial park',
    shedPriority: 5,
    peakKw: 1000,
    flexibility: 'contracted', // demand-response contract, penalty on call
    floorFraction: 0.6,
    ridethroughSeconds: 0,
    vulnerableOccupants: 0,
    criticalityWeight: 2,
    thermalSensitivity: 0.1,
  },
  {
    id: 'school',
    label: 'Secondary school',
    shedPriority: 6, // sheds first
    peakKw: 400,
    flexibility: 'firm',
    floorFraction: 0.0,
    ridethroughSeconds: 0,
    vulnerableOccupants: 0,
    criticalityWeight: 1,
    thermalSensitivity: 0.2,
  },
];

export const SITE: SiteSpec = {
  loads: LOADS,
  pv: { ratedKw: 1800 },
  wind: { ratedKw: 900 },
  battery: {
    capacityKwh: 2000,
    maxChargeKw: 1000,
    maxDischargeKw: 2000,
    roundTripEfficiency: 0.90,
    minSoc: 0.10,
    maxSoc: 0.95,
    degradationCostPerKwh: 0.04,
    // Referred to the inverter's 2 MW rating. Only counts in grid-forming mode.
    gridFormingInertiaSeconds: 8.0,
  },
  genset: {
    ratedKw: 1500,
    minLoadFraction: 0.30,
    startupSeconds: 120,
    rampKwPerSecond: 12,
    minUpSeconds: 600,
    minDownSeconds: 300,
    noLoadFuelLph: 18,
    marginalFuelLphPerKw: 0.26,
    fuelCostPerLitre: 1.35,
    co2KgPerLitre: 2.68,
    inertiaSeconds: 1.5,
    droop: 0.05,
  },
  grid: {
    importLimitKw: 3500,
    exportLimitKw: 1500,
    // The transmission system behind the tie behaves like a very large machine.
    // Losing it is what makes the 18:40 fault dangerous.
    equivalentInertiaSeconds: 5.0,
  },
};

/** Equivalent apparent power of the transmission system seen at the tie, kVA. */
export const GRID_EQUIVALENT_KVA = 15_000;

const H = 3600;

/** Time-of-use import price, USD/kWh, indexed by hour. */
const IMPORT_PRICE_BY_HOUR = [
  0.06, 0.06, 0.05, 0.05, 0.05, 0.06, 0.09, 0.13, 0.15, 0.13, 0.10, 0.08,
  0.07, 0.06, 0.06, 0.08, 0.12, 0.18, 0.24, 0.26, 0.22, 0.16, 0.11, 0.08,
];

/** Grid carbon intensity, kg CO2/kWh, indexed by hour. */
const GRID_CARBON_BY_HOUR = [
  0.38, 0.38, 0.37, 0.37, 0.36, 0.36, 0.34, 0.30, 0.26, 0.22, 0.19, 0.17,
  0.16, 0.16, 0.17, 0.20, 0.26, 0.33, 0.42, 0.45, 0.44, 0.42, 0.40, 0.39,
];

export const DEFAULT_SCENARIO: Scenario = {
  id: 'summer-peak-island',
  label: 'Summer peak — evening islanding',
  seed: 20260815,
  site: SITE,
  peakTemperatureC: 34,
  importPriceByHour: IMPORT_PRICE_BY_HOUR,
  gridCarbonByHour: GRID_CARBON_BY_HOUR,
  events: [
    // Afternoon heatwave drives cooling load across every thermally sensitive block.
    { kind: 'heatwave', at: 13 * H, durationS: 4 * H, demandMultiplier: 1.35 },
    // A cloud bank crosses the PV array. Short, sharp, and easy to miss.
    { kind: 'cloud', at: 14 * H + 10 * 60, durationS: 8 * 60, outputFraction: 0.2 },
    // Evening wind lull, right as demand climbs.
    { kind: 'windLull', at: 17 * H, durationS: 90 * 60, outputFraction: 0.15 },
    // The main event: the grid tie opens at the evening peak and the district
    // is on its own for twenty-five minutes.
    { kind: 'feederFault', at: 18 * H + 40 * 60, durationS: 25 * 60 },
    // Scarcity pricing once the tie recloses.
    { kind: 'priceSpike', at: 21 * H, durationS: 1 * H, multiplier: 6 },
  ],
};

// ---------------------------------------------------------------------------
// Profiles
// ---------------------------------------------------------------------------

/** Ambient temperature, °C. Minimum around 05:00, maximum around 15:00. */
export function ambientTemperature(t: number, peakC: number): number {
  const minC = peakC - 12;
  const phase = ((t - 5 * H) / SECONDS_PER_DAY) * 2 * Math.PI;
  return minC + ((peakC - minC) * (1 - Math.cos(phase))) / 2;
}

/** Clear-sky PV output as a fraction of rating. */
export function clearSkyFraction(t: number): number {
  const sunrise = 5.5 * H;
  const sunset = 20.5 * H;
  if (t < sunrise || t > sunset) return 0;
  const x = (t - sunrise) / (sunset - sunrise);
  return Math.pow(Math.sin(Math.PI * x), 1.2);
}

/**
 * Wind output as a fraction of rating. Smooth pseudo-random walk so it looks
 * like weather rather than noise, but stays deterministic for a given seed.
 */
export function windFraction(t: number, seed: number): number {
  const octave = (period: number, phase: number) =>
    Math.sin((2 * Math.PI * t) / period + phase);
  const rnd = mulberry32(seed);
  const p1 = rnd() * 2 * Math.PI;
  const p2 = rnd() * 2 * Math.PI;
  const p3 = rnd() * 2 * Math.PI;
  const raw =
    0.5 +
    0.22 * octave(9 * H, p1) +
    0.14 * octave(3.5 * H, p2) +
    0.07 * octave(1.2 * H, p3);
  return Math.min(1, Math.max(0.02, raw));
}

/** Base demand shape per block, as a fraction of the block's peak. */
export function loadShape(id: LoadId, t: number): number {
  const hour = t / H;
  const bump = (centre: number, width: number) =>
    Math.exp(-Math.pow((hour - centre) / width, 2));

  switch (id) {
    case 'hospital':
      // Near-flat with a daytime theatre and imaging bump.
      return 0.72 + 0.22 * bump(13, 4.5);

    case 'residential':
      // Small morning peak, dominant evening peak.
      return 0.28 + 0.30 * bump(7.5, 1.6) + 0.68 * bump(19.5, 2.4);

    case 'water':
      // Overnight fill plus a morning top-up.
      return 0.15 + 0.70 * bump(3, 2.5) + 0.45 * bump(9, 1.5);

    case 'datacenter':
      // Flat baseload with a modest business-hours rise.
      return 0.78 + 0.16 * bump(14, 5);

    case 'industrial':
      // Single day shift.
      return hour >= 6 && hour <= 18 ? 0.85 + 0.12 * bump(11, 3) : 0.12;

    case 'school':
      // Term-time weekday, empty overnight.
      return hour >= 7 && hour <= 16 ? 0.55 + 0.42 * bump(11.5, 2.6) : 0.04;
  }
}

/**
 * Cooling load multiplier. Blocks draw more as ambient rises above 24 °C, in
 * proportion to how thermally sensitive they are.
 */
export function thermalMultiplier(ambientC: number, sensitivity: number): number {
  if (sensitivity <= 0) return 1;
  const excess = Math.max(0, ambientC - 24);
  return 1 + sensitivity * (excess / 10);
}

export function hourIndex(t: number): number {
  return Math.min(23, Math.max(0, Math.floor(t / H)));
}
