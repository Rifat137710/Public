/**
 * The feeder and the solver that answers it.
 *
 * This is the one copy of the physics. The walkable city and the lesson pages both
 * import it, so a change to the network is a change to every build at once and the two
 * can never drift into disagreeing about what the town does.
 *
 * The solver is a backward/forward sweep, the same method as `src/sim/powerflow.ts`.
 * Radial networks do not need matrix factorisation: sum currents from the leaves back to
 * the source, then push voltages from the source back out to the leaves, and repeat.
 * It settles in eight to fourteen passes.
 *
 * Nothing here is trusted for being a port. `check` below re-solves every recorded
 * control step on both feeders and compares against the engine that produced them.
 */

import WORLD from './world.json';

export { WORLD };

export const N_BUS = 33;
export const N_NODE = N_BUS + 1;
export const KW_PER_PU = WORLD.kwPerPu;
export const BAND_LO = 0.95;
export const BAND_HI = 1.05;
export const STATION_BUSES = WORLD.stations;

/* ================================================================== */
/*  The network                                                       */
/* ================================================================== */

const net = (() => {
  // Branch 0 is the source impedance. It is why bus 1 sags before the town starts.
  const branches = [{ from: 0, to: 1, rPu: WORLD.source.rPu, xPu: WORLD.source.xPu }, ...WORLD.branches];
  const m = branches.length;
  const branchFrom = new Int32Array(m);
  const branchR = new Float64Array(m);
  const branchX = new Float64Array(m);
  const feedBranch = new Int32Array(N_NODE).fill(-1);
  const children = Array.from({ length: N_NODE }, () => []);
  branches.forEach((b, i) => {
    branchFrom[i] = b.from; branchR[i] = b.rPu; branchX[i] = b.xPu;
    feedBranch[b.to] = i; children[b.from].push(b.to);
  });
  // Breadth-first from the source gives an ordering where every node appears after
  // its parent, which is what makes a single forward pass correct.
  const order = new Int32Array(N_NODE);
  let head = 0, tail = 0;
  order[tail++] = 0;
  while (head < tail) for (const c of children[order[head++]]) order[tail++] = c;
  return { m, branchFrom, branchR, branchX, feedBranch, order };
})();

const vRe = new Float64Array(N_NODE);
const vIm = new Float64Array(N_NODE);
const iRe = new Float64Array(net.m);
const iIm = new Float64Array(net.m);

export const vMag = new Float64Array(N_NODE);
export const branchLossKw = new Float64Array(net.m);

export function solve(p, q) {
  vRe.fill(1); vIm.fill(0);
  for (let it = 0; it < 200; it++) {
    iRe.fill(0); iIm.fill(0);
    // Backward: leaves first, so a node's children are already summed into it.
    for (let k = N_NODE - 1; k >= 1; k--) {
      const node = net.order[k];
      const a = vRe[node], b = vIm[node];
      const v2 = a * a + b * b;
      const br = net.feedBranch[node];
      iRe[br] += (p[node] * a + q[node] * b) / v2;
      iIm[br] += (p[node] * b - q[node] * a) / v2;
      const pb = net.feedBranch[net.branchFrom[br]];
      if (pb >= 0) { iRe[pb] += iRe[br]; iIm[pb] += iIm[br]; }
    }
    // Forward: V_node = V_parent - Z I
    let maxDelta = 0;
    for (let k = 1; k < N_NODE; k++) {
      const node = net.order[k];
      const br = net.feedBranch[node];
      const parent = net.branchFrom[br];
      const r = net.branchR[br], x = net.branchX[br];
      const nRe = vRe[parent] - (r * iRe[br] - x * iIm[br]);
      const nIm = vIm[parent] - (r * iIm[br] + x * iRe[br]);
      maxDelta = Math.max(maxDelta, Math.abs(nRe - vRe[node]) + Math.abs(nIm - vIm[node]));
      vRe[node] = nRe; vIm[node] = nIm;
    }
    if (maxDelta < 1e-11) break;
  }
  let lossPu = 0;
  for (let b = 0; b < net.m; b++) {
    const i2 = iRe[b] * iRe[b] + iIm[b] * iIm[b];
    branchLossKw[b] = i2 * net.branchR[b] * KW_PER_PU;
    lossPu += i2 * net.branchR[b];
  }
  for (let n = 0; n < N_NODE; n++) vMag[n] = Math.hypot(vRe[n], vIm[n]);
  let vMin = Infinity, vMinBus = 1, violations = 0;
  for (let bus = 1; bus <= N_BUS; bus++) {
    if (vMag[bus] < vMin) { vMin = vMag[bus]; vMinBus = bus; }
    if (vMag[bus] < BAND_LO || vMag[bus] > BAND_HI) violations++;
  }
  return { lossKw: lossPu * KW_PER_PU, vMin, vMinBus, violations };
}

const pBuf = new Float64Array(N_NODE);
const qBuf = new Float64Array(N_NODE);

/** Solve one step of the day with the four stations commanded to `stationKw`. */
export function solveAt(day, stationKw) {
  for (let b = 0; b <= N_BUS; b++) { pBuf[b] = day.p[b]; qBuf[b] = day.q[b]; }
  WORLD.stations.forEach((bus, i) => { pBuf[bus] -= stationKw[i] / KW_PER_PU; });
  return solve(pBuf, qBuf);
}

/**
 * Voltage sensitivities at the current operating point, measured by perturbation.
 *
 * dvdp[k][bus] is the change in |V| at `bus` per kW injected at station `k`. The safety
 * projection is built from these, and they are re-measured every step because the
 * feeder's stiffness changes with its loading — which is the entire reason a policy
 * trained on one grid misjudges another.
 */
const DELTA_KW = 10;
export function sensitivitiesAt(day, stationKw) {
  const base = solveAt(day, stationKw);
  const v0 = Float64Array.from(vMag);
  const dvdp = [];
  const probe = stationKw.slice();
  for (let k = 0; k < STATION_BUSES.length; k++) {
    const original = probe[k];
    probe[k] = original + DELTA_KW;
    solveAt(day, probe);
    const up = Float64Array.from(vMag);
    probe[k] = original - DELTA_KW;
    solveAt(day, probe);
    const down = Float64Array.from(vMag);
    probe[k] = original;
    const col = new Float64Array(N_NODE);
    for (let n = 0; n < N_NODE; n++) col[n] = (up[n] - down[n]) / (2 * DELTA_KW);
    dvdp.push(col);
  }
  solveAt(day, stationKw);   // leave the world where we found it
  // `u0` travels with the measurement. The linear model is only meaningful relative to
  // the command it was taken about, and every user of it needs to know which one.
  return { v0, dvdp, base, u0: stationKw.slice() };
}

/**
 * Switch between the weak feeder and the canonical stiff one.
 *
 * Branch 0 is the substation source impedance, and it is the single structural
 * difference between the two grids. Setting it to zero is the whole change — which is
 * why a town that behaves completely differently is one line of arithmetic away.
 */
export let grid = 'weak';
export function setGrid(kind) {
  grid = kind === 'strong' ? 'strong' : 'weak';
  net.branchR[0] = grid === 'strong' ? 0 : WORLD.source.rPu;
  net.branchX[0] = grid === 'strong' ? 0 : WORLD.source.xPu;
}

/**
 * Re-solve every recorded step, on both grids, and compare with the engine that
 * recorded it. A port that agrees to 1e-4 pu across 2304 steps is a port; one that is
 * merely believed is a liability, because everything these pages teach sits downstream
 * of this.
 */
export const check = (() => {
  let worstV = 0, worstViol = 0, n = 0;
  const sweep = (runs) => {
    for (const run of runs) run.frames.forEach((f, i) => {
      const r = solveAt(WORLD.day[i], f.kw);
      worstV = Math.max(worstV, Math.abs(r.vMin - f.vmin));
      worstViol = Math.max(worstViol, Math.abs(r.violations - f.viol));
      n++;
    });
  };
  setGrid('weak');
  sweep(WORLD.runs);
  setGrid('strong');
  sweep(WORLD.runsStrong);
  setGrid('weak');
  return { worstV, worstViol, n, ok: worstV < 5e-4 && worstViol === 0 };
})();
