/**
 * The day the feeder lives through: load shape, solar, and price.
 *
 * One simulated day is 288 steps of five minutes, matching the thesis's control
 * horizon. Every profile here is a pure function of the step index, so any moment of
 * the day can be evaluated without running the ones before it — which is what makes
 * scrubbing backwards and branching cheap.
 */

export const STEPS_PER_DAY = 288;
export const MINUTES_PER_STEP = 5;
export const HOURS_PER_STEP = MINUTES_PER_STEP / 60;

/** Hour of day, fractional, for a step index. */
export function hourOf(step: number): number {
  return (step * MINUTES_PER_STEP) / 60;
}

/** Clock label for a step, e.g. "18:35". */
export function clockOf(step: number): string {
  const minutes = step * MINUTES_PER_STEP;
  const h = Math.floor(minutes / 60) % 24;
  const m = minutes % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/**
 * Deterministic PRNG. A seeded generator means a learner can be handed the exact day
 * that broke their run, and a judge can reproduce any figure in the video.
 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function next(): number {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function interpolateHourly(table: readonly number[], step: number): number {
  const hour = hourOf(step);
  const i = Math.floor(hour) % 24;
  const j = (i + 1) % 24;
  const frac = hour - Math.floor(hour);
  return table[i] * (1 - frac) + table[j] * frac;
}

/**
 * Normalised residential demand: a low overnight base, a modest morning rise, and a
 * pronounced evening peak that lands at 19:00. The peak is normalised to 1.0, so the
 * scenario's load scale is read directly as "fraction of nameplate at the worst moment".
 */
const LOAD_SHAPE_HOURLY: readonly number[] = [
  0.42, 0.38, 0.36, 0.35, 0.36, 0.40, 0.50, 0.62, 0.66, 0.62, 0.58, 0.57,
  0.58, 0.57, 0.55, 0.56, 0.62, 0.74, 0.90, 1.00, 0.96, 0.84, 0.68, 0.52,
];

export function loadShape(step: number): number {
  return interpolateHourly(LOAD_SHAPE_HOURLY, step);
}

/**
 * Clear-sky solar fraction: zero overnight, a bell peaking at 12:30.
 * The evening collision the simulator is built around is structural — this curve is
 * already at zero by the time the load shape reaches its peak.
 */
export function clearSkyFraction(step: number): number {
  const hour = hourOf(step);
  const sunrise = 6.0;
  const sunset = 18.5;
  if (hour <= sunrise || hour >= sunset) return 0;
  const phase = (hour - sunrise) / (sunset - sunrise);
  return Math.sin(Math.PI * phase) ** 1.3;
}

/** Three-tier time-of-use retail price, $/kWh, as used in the thesis. */
export function touPrice(step: number): number {
  const hour = hourOf(step);
  if (hour >= 17 && hour < 22) return 0.30;
  if (hour >= 7 && hour < 17) return 0.15;
  return 0.08;
}

export type PriceTier = 'off-peak' | 'shoulder' | 'peak';

export function priceTier(step: number): PriceTier {
  const price = touPrice(step);
  if (price >= 0.30) return 'peak';
  if (price >= 0.15) return 'shoulder';
  return 'off-peak';
}
