/**
 * The safety projection: the smallest change to a requested command that keeps the
 * feeder inside its voltage band.
 *
 * The thesis solves this as an eight-variable second-order cone program with CVXPY and
 * CLARABEL. That is the right tool when you are training an agent for days on a GPU.
 * In a browser it is the wrong tool, and unnecessary — because the voltage model is
 * *linear* in the command, the feasible set
 *
 *     { u : vLow <= v0 + S.u <= vHigh,  uMin <= u <= uMax }
 *
 * is a polytope, and projecting a point onto a polytope is what Dykstra's alternating
 * projection method does. Each constraint is a half-space with a closed-form
 * projection; cycling through them with Dykstra's correction terms converges to the
 * true Euclidean projection onto the intersection, not merely to some feasible point.
 *
 * With four stations and roughly seventy constraints this runs in tens of microseconds,
 * against the same band and the same margin the thesis uses.
 */

import type { Sensitivities } from './sensitivities.js';

/** Statutory voltage band, per unit. Not a difficulty setting. */
export const V_LOWER = 0.95;
export const V_UPPER = 1.05;
/** The thesis tightens the band by this much before projecting. */
export const DEFAULT_MARGIN_PU = 0.010;

export interface ProjectionOptions {
  /** Band tightening, pu. Larger is more conservative and serves fewer vehicles. */
  marginPu?: number;
  /** Per-station command limits in kW; injection positive. */
  uMinKw?: readonly number[];
  uMaxKw?: readonly number[];
  maxIterations?: number;
  tolerance?: number;
  /**
   * Buses whose voltage the projection defends. Defaults to every bus.
   * Restricting this to metered buses models a utility that cannot see the whole feeder.
   */
  monitoredBuses?: readonly number[];
}

export interface ProjectionResult {
  /** The command actually executed, kW per station, injection positive. */
  safeKw: number[];
  /** Per-station curtailment: how much of the request the safety layer removed. */
  curtailmentKw: number[];
  /** True when the requested command was already feasible and passed through. */
  passthrough: boolean;
  /**
   * True when the operating point was already outside the band before any command.
   * The band is then relaxed to "do not make it worse" rather than "restore it",
   * matching the thesis's graceful degradation on an infeasible program.
   */
  relaxed: boolean;
  iterations: number;
  converged: boolean;
}

/**
 * A feasible request settles in one or two cycles. The slow case is a degenerate one:
 * when the feeder is already out of band, the relaxed constraints can pin the feasible
 * set down to a single point, and Dykstra crawls into that vertex. Measured worst case
 * is 665 cycles / 1.7 ms, against roughly 0.05 ms for an ordinary step.
 */
const DEFAULT_MAX_ITERATIONS = 2000;
/** One milliwatt. Finer than any charger can act on, so this is exact in practice. */
const DEFAULT_TOLERANCE = 1e-6;

interface HalfSpace {
  /** Coefficients on the command vector. */
  a: Float64Array;
  /** Right-hand side: a.u <= b. */
  b: number;
  /** Squared norm of `a`, precomputed. */
  aa: number;
}

/**
 * Build the half-space constraints for one operating point.
 *
 * Each monitored bus contributes two: one for the ceiling and one for the floor.
 * Buses the stations cannot measurably influence are dropped — their rows would be
 * numerically degenerate and they cannot bind in any case.
 */
function buildConstraints(
  s: Sensitivities,
  marginPu: number,
  monitoredBuses: readonly number[],
): { constraints: HalfSpace[]; relaxed: boolean } {
  const nStations = s.stationBuses.length;
  const constraints: HalfSpace[] = [];
  let relaxed = false;

  const lower = V_LOWER + marginPu;
  const upper = V_UPPER - marginPu;

  for (const bus of monitoredBuses) {
    const row = new Float64Array(nStations);
    let scale = 0;
    for (let k = 0; k < nStations; k++) {
      // Total sensitivity of this bus to station k's active power.
      row[k] = s.dvdp[k][bus];
      scale += Math.abs(row[k]);
    }
    if (scale < 1e-12) continue;

    const v0 = s.v0[bus];

    // Ceiling:  v0 + row.u <= upper   ->   row.u <= upper - v0
    // If the bus already sits above the ceiling, requiring the command to fix it is
    // infeasible, so the constraint becomes "do not push it any higher".
    let headroom = upper - v0;
    if (headroom < 0) {
      headroom = 0;
      relaxed = true;
    }
    constraints.push({ a: row, b: headroom, aa: dot(row, row) });

    // Floor:  v0 + row.u >= lower   ->   -row.u <= v0 - lower
    let footroom = v0 - lower;
    if (footroom < 0) {
      footroom = 0;
      relaxed = true;
    }
    const negRow = new Float64Array(nStations);
    for (let k = 0; k < nStations; k++) negRow[k] = -row[k];
    constraints.push({ a: negRow, b: footroom, aa: dot(negRow, negRow) });
  }

  return { constraints, relaxed };
}

function dot(a: Float64Array, b: Float64Array): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
  return sum;
}

function dotArr(a: Float64Array, b: number[]): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
  return sum;
}

/**
 * Project a requested station command onto the safe set.
 *
 * `requestKw` is the raw command, injection positive: a V2G discharge is a positive
 * entry, a charging draw is negative. This is the opposite of the load convention used
 * inside the power flow, and matches how an operator thinks about a charger.
 */
export function projectCommand(
  s: Sensitivities,
  requestKw: readonly number[],
  options: ProjectionOptions = {},
): ProjectionResult {
  const nStations = s.stationBuses.length;
  const margin = options.marginPu ?? DEFAULT_MARGIN_PU;
  const maxIter = options.maxIterations ?? DEFAULT_MAX_ITERATIONS;
  const tol = options.tolerance ?? DEFAULT_TOLERANCE;
  const uMin = options.uMinKw ?? new Array(nStations).fill(-Infinity);
  const uMax = options.uMaxKw ?? new Array(nStations).fill(Infinity);
  const monitored =
    options.monitoredBuses ?? Array.from({ length: s.v0.length - 1 }, (_, i) => i + 1);

  const { constraints, relaxed } = buildConstraints(s, margin, monitored);

  // Set 0 is the box; sets 1..n are the half-spaces.
  const setCount = constraints.length + 1;
  const x = Array.from(requestKw);
  const corrections: number[][] = Array.from({ length: setCount }, () =>
    new Array(nStations).fill(0),
  );

  const y = new Array(nStations).fill(0);
  const cycleStart = new Array(nStations).fill(0);
  let iterations = 0;
  let converged = false;

  while (iterations < maxIter) {
    iterations++;
    for (let k = 0; k < nStations; k++) cycleStart[k] = x[k];

    for (let set = 0; set < setCount; set++) {
      const correction = corrections[set];
      for (let k = 0; k < nStations; k++) y[k] = x[k] + correction[k];

      if (set === 0) {
        for (let k = 0; k < nStations; k++) {
          const clamped = Math.min(uMax[k], Math.max(uMin[k], y[k]));
          correction[k] = y[k] - clamped;
          x[k] = clamped;
        }
        continue;
      }

      const c = constraints[set - 1];
      const violation = dotArr(c.a, y) - c.b;
      if (violation > 0) {
        const step = violation / c.aa;
        for (let k = 0; k < nStations; k++) {
          const projected = y[k] - step * c.a[k];
          correction[k] = y[k] - projected;
          x[k] = projected;
        }
      } else {
        for (let k = 0; k < nStations; k++) {
          correction[k] = 0;
          x[k] = y[k];
        }
      }
    }

    // Dykstra's iterate moves within a cycle even when it has settled, because each
    // set hands its correction to the next. Convergence is the displacement across a
    // whole cycle, not the distance travelled inside one.
    let shift = 0;
    for (let k = 0; k < nStations; k++) {
      shift = Math.max(shift, Math.abs(x[k] - cycleStart[k]));
    }
    if (shift < tol) {
      converged = true;
      break;
    }
  }

  const safeKw = x.map((value) => (Math.abs(value) < 1e-9 ? 0 : value));
  const curtailmentKw = safeKw.map((value, k) => requestKw[k] - value);
  const passthrough = curtailmentKw.every((value) => Math.abs(value) < 1e-6);

  return { safeKw, curtailmentKw, passthrough, relaxed, iterations, converged };
}
