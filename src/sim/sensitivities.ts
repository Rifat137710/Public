/**
 * Voltage sensitivities, measured rather than derived.
 *
 * The whole simulator runs on a linearisation of the feeder:
 *
 *     v  ~=  v0  +  S^P . dp  +  S^Q . dq
 *
 * where S^P[i][k] is the change in |V| at bus i caused by injecting one kilowatt at
 * station bus k. Rather than differentiate the power flow analytically, we perturb the
 * network and re-solve — a central difference. That is both simpler and closer to what
 * the reference study does, which recomputes sensitivities on the live network at every control
 * step so the feasible set reflects the deployment grid rather than a nominal model.
 *
 * Units are pu/kW throughout, matching Table 4.1. Injection is positive: pushing power
 * into a bus raises its voltage, so the diagonal entries of S^P are positive.
 */

import type { Network } from './network.js';
import { KW_PER_PU } from './network.js';
import { solvePowerFlow, type PowerFlowOptions } from './powerflow.js';

/** Perturbation size for the central difference, in kW. */
const DEFAULT_DELTA_KW = 10;

export interface Sensitivities {
  /** Bus numbers the columns correspond to, in order. */
  stationBuses: readonly number[];
  /** S^P[i][k]: d|V_i| / dP_k in pu/kW, i indexed by node, k by station. */
  dvdp: Float64Array[];
  /** S^Q[i][k]: d|V_i| / dQ_k in pu/kVAr. */
  dvdq: Float64Array[];
  /** Base voltages the linearisation is taken about, pu, indexed by node. */
  v0: Float64Array;
}

/**
 * Measure the sensitivity matrices about the given operating point.
 *
 * One power flow per station per quantity per direction: with four stations that is
 * sixteen solves, each a few microseconds. Cheap enough to redo whenever the operating
 * point moves.
 */
export function measureSensitivities(
  net: Network,
  p: Float64Array,
  q: Float64Array,
  stationBuses: readonly number[],
  options: PowerFlowOptions = {},
  deltaKw = DEFAULT_DELTA_KW,
): Sensitivities {
  const base = solvePowerFlow(net, p, q, options);
  const n = net.nodeCount;
  const delta = deltaKw / KW_PER_PU;

  const dvdp: Float64Array[] = [];
  const dvdq: Float64Array[] = [];

  const pWork = Float64Array.from(p);
  const qWork = Float64Array.from(q);

  for (const bus of stationBuses) {
    // Active power. Injection is a negative load, so +injection means -p.
    pWork[bus] = p[bus] - delta;
    const pUp = solvePowerFlow(net, pWork, qWork, options);
    pWork[bus] = p[bus] + delta;
    const pDown = solvePowerFlow(net, pWork, qWork, options);
    pWork[bus] = p[bus];

    const columnP = new Float64Array(n);
    for (let node = 0; node < n; node++) {
      columnP[node] = (pUp.vMag[node] - pDown.vMag[node]) / (2 * deltaKw);
    }
    dvdp.push(columnP);

    // Reactive power, same convention.
    qWork[bus] = q[bus] - delta;
    const qUp = solvePowerFlow(net, pWork, qWork, options);
    qWork[bus] = q[bus] + delta;
    const qDown = solvePowerFlow(net, pWork, qWork, options);
    qWork[bus] = q[bus];

    const columnQ = new Float64Array(n);
    for (let node = 0; node < n; node++) {
      columnQ[node] = (qUp.vMag[node] - qDown.vMag[node]) / (2 * deltaKw);
    }
    dvdq.push(columnQ);
  }

  return { stationBuses, dvdp, dvdq, v0: base.vMag };
}

export interface StationSensitivity {
  bus: number;
  /** |dV/dP| at the station's own bus, pu/kW. */
  selfP: number;
  /** |dV/dQ| at the station's own bus, pu/kVAr. */
  selfQ: number;
  /** selfP / selfQ. Above 1 means active power is the stronger voltage lever here. */
  ratio: number;
}

/**
 * The diagonal of the sensitivity matrices — each station's influence over its own
 * bus. This is what Table 4.1 tabulates, and the ratio is what Gate 1 tests.
 */
export function stationSelfSensitivities(s: Sensitivities): StationSensitivity[] {
  return s.stationBuses.map((bus, k) => {
    const selfP = Math.abs(s.dvdp[k][bus]);
    const selfQ = Math.abs(s.dvdq[k][bus]);
    return { bus, selfP, selfQ, ratio: selfP / selfQ };
  });
}

/**
 * The active-over-reactive dominance ratio as the reference study reports it: the ratio of the
 * mean magnitudes, not the mean of the per-station ratios. The two differ (1.280 vs
 * 1.296 on the reference feeder) and the distinction matters when checking Gate 1.
 */
export function dominanceRatio(stations: StationSensitivity[]): number {
  const meanP = stations.reduce((sum, s) => sum + s.selfP, 0) / stations.length;
  const meanQ = stations.reduce((sum, s) => sum + s.selfQ, 0) / stations.length;
  return meanP / meanQ;
}

/**
 * Apply the linearised model: predicted |V| at every node for a station command
 * vector, without solving a power flow. This is the routine that runs every frame.
 *
 * `dpKw` and `dqKvar` are per-station *injections* relative to the operating point
 * the sensitivities were measured about.
 */
export function predictVoltages(
  s: Sensitivities,
  dpKw: readonly number[],
  dqKvar: readonly number[],
): Float64Array {
  const v = Float64Array.from(s.v0);
  for (let k = 0; k < s.stationBuses.length; k++) {
    const dp = dpKw[k];
    const dq = dqKvar[k];
    if (dp === 0 && dq === 0) continue;
    const colP = s.dvdp[k];
    const colQ = s.dvdq[k];
    for (let node = 0; node < v.length; node++) {
      v[node] += colP[node] * dp + colQ[node] * dq;
    }
  }
  return v;
}
