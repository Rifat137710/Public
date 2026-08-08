/**
 * Backward/forward sweep power flow for a radial feeder.
 *
 * A radial network has no loops, so there is nothing to factorise: sum currents from
 * the leaves inward, then push voltages from the source outward, and repeat. It
 * converges in a handful of iterations and costs microseconds, which is what makes
 * it usable for measuring sensitivities by perturbation rather than deriving them.
 *
 * Everything here is per-unit on the network's own bases. Loads are positive for
 * consumption; a discharging EV or a PV array is a negative entry in `p`.
 */

import type { Network } from './network.js';
import { KW_PER_PU } from './network.js';

export interface PowerFlowOptions {
  /** Slack voltage magnitude in pu. The substation regulates to 1.0 by default. */
  slackVoltage?: number;
  tolerance?: number;
  maxIterations?: number;
}

export interface PowerFlowResult {
  /** Voltage magnitude in pu, indexed by node (0 = ideal source). */
  vMag: Float64Array;
  vRe: Float64Array;
  vIm: Float64Array;
  /** Total active loss across all branches, kW. */
  lossKw: number;
  /** Total reactive loss across all branches, kVAr. */
  lossKvar: number;
  iterations: number;
  converged: boolean;
}

const DEFAULT_TOLERANCE = 1e-11;
const DEFAULT_MAX_ITERATIONS = 200;

/**
 * Solve for bus voltages given per-unit nodal load injections.
 *
 * `p` and `q` are indexed by node and are consumed, not mutated. The source node's
 * entries are ignored — it absorbs whatever the feeder needs.
 */
export function solvePowerFlow(
  net: Network,
  p: Float64Array,
  q: Float64Array,
  options: PowerFlowOptions = {},
): PowerFlowResult {
  const slackV = options.slackVoltage ?? 1.0;
  const tol = options.tolerance ?? DEFAULT_TOLERANCE;
  const maxIter = options.maxIterations ?? DEFAULT_MAX_ITERATIONS;

  const n = net.nodeCount;
  const m = net.branchR.length;
  const { order, feedBranch, branchFrom, branchR, branchX } = net;

  const vRe = new Float64Array(n).fill(slackV);
  const vIm = new Float64Array(n);
  // Branch currents, stored against the branch feeding each node.
  const iRe = new Float64Array(m);
  const iIm = new Float64Array(m);

  let iterations = 0;
  let converged = false;

  while (iterations < maxIter) {
    iterations++;
    iRe.fill(0);
    iIm.fill(0);

    // Backward sweep: walk leaves-first so a node's children are already summed.
    for (let k = n - 1; k >= 1; k--) {
      const node = order[k];
      const a = vRe[node];
      const b = vIm[node];
      const v2 = a * a + b * b;
      // I = conj(S / V) = (P - jQ) / (a - jb)
      const loadRe = (p[node] * a + q[node] * b) / v2;
      const loadIm = (p[node] * b - q[node] * a) / v2;

      const branch = feedBranch[node];
      iRe[branch] += loadRe;
      iIm[branch] += loadIm;

      // Push this branch's current up into its parent's feeding branch.
      const parent = branchFrom[branch];
      const parentBranch = feedBranch[parent];
      if (parentBranch >= 0) {
        iRe[parentBranch] += iRe[branch];
        iIm[parentBranch] += iIm[branch];
      }
    }

    // Forward sweep: V_node = V_parent - Z * I
    let maxDelta = 0;
    for (let k = 1; k < n; k++) {
      const node = order[k];
      const branch = feedBranch[node];
      const parent = branchFrom[branch];
      const r = branchR[branch];
      const x = branchX[branch];
      const dropRe = r * iRe[branch] - x * iIm[branch];
      const dropIm = r * iIm[branch] + x * iRe[branch];
      const newRe = vRe[parent] - dropRe;
      const newIm = vIm[parent] - dropIm;
      const delta = Math.abs(newRe - vRe[node]) + Math.abs(newIm - vIm[node]);
      if (delta > maxDelta) maxDelta = delta;
      vRe[node] = newRe;
      vIm[node] = newIm;
    }

    if (maxDelta < tol) {
      converged = true;
      break;
    }
  }

  const vMag = new Float64Array(n);
  for (let node = 0; node < n; node++) {
    vMag[node] = Math.hypot(vRe[node], vIm[node]);
  }

  let lossPu = 0;
  let lossQPu = 0;
  for (let branch = 0; branch < m; branch++) {
    const i2 = iRe[branch] * iRe[branch] + iIm[branch] * iIm[branch];
    lossPu += i2 * branchR[branch];
    lossQPu += i2 * branchX[branch];
  }

  return {
    vMag,
    vRe,
    vIm,
    lossKw: lossPu * KW_PER_PU,
    lossKvar: lossQPu * KW_PER_PU,
    iterations,
    converged,
  };
}

/**
 * Lowest voltage magnitude among the real feeder buses, and where it occurs.
 * The ideal source at node 0 is excluded — it is fixed at the slack voltage by
 * definition and would otherwise always look like the healthiest point on the feeder.
 */
export function minimumVoltage(result: PowerFlowResult): { bus: number; vMin: number } {
  let bus = 1;
  let vMin = Infinity;
  for (let node = 1; node < result.vMag.length; node++) {
    if (result.vMag[node] < vMin) {
      vMin = result.vMag[node];
      bus = node;
    }
  }
  return { bus, vMin };
}
