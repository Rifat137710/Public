/**
 * The IEEE 33-bus distribution feeder of Baran & Wu (1989).
 *
 * This is a published benchmark, which is exactly why it is used: every number the
 * simulator teaches from can be checked against literature by anyone. The line and
 * load data below reproduce the canonical case — 12.66 kV, 3715 kW + 2300 kVAr of
 * load, radial, 32 branches.
 *
 * Bus numbering follows the publication: buses 1..33, bus 1 being the substation.
 * Internally node 0 is an ideal source and node k is published bus k, so a "weak"
 * grid is modelled by putting a finite impedance on the branch from node 0 to bus 1.
 * The reference study reports its own weak/strong pair; `calibrate.ts` fits that impedance so
 * this file's public data reproduces the reference feeder rather than merely resembling it.
 *
 * Beware of two numbering conventions in play:
 *   - published bus number  b       (Figure 4.2: "EV @ 18")
 *   - pandapower bus index  b - 1   (Table 4.1: "Bus 17")
 * Everything here uses the published number. `PANDAPOWER_INDEX_OFFSET` converts.
 */

export const V_BASE_KV = 12.66;
export const S_BASE_MVA = 10;
/** 12.66^2 / 10 = 16.0276 ohm. */
export const Z_BASE_OHM = (V_BASE_KV * V_BASE_KV) / S_BASE_MVA;
/** 1 pu of power, in kW. */
export const KW_PER_PU = S_BASE_MVA * 1000;

/** Subtract from a published bus number to get the pandapower index used in Table 4.1. */
export const PANDAPOWER_INDEX_OFFSET = 1;

/** Highest published bus number. Node 0 (the ideal source) sits above bus 1. */
export const N_BUS = 33;
/** Node count including the ideal source at index 0. */
export const N_NODE = N_BUS + 1;

export interface Branch {
  /** Published bus number of the upstream end, or 0 for the ideal source. */
  from: number;
  /** Published bus number of the downstream end. */
  to: number;
  rOhm: number;
  xOhm: number;
}

/**
 * The 32 branches of the canonical feeder, in publication order. The source branch
 * (node 0 -> bus 1) is added by `buildNetwork` because its impedance is what
 * distinguishes the weak feeder from the strong one.
 */
export const BRANCHES: readonly Branch[] = [
  { from: 1, to: 2, rOhm: 0.0922, xOhm: 0.0477 },
  { from: 2, to: 3, rOhm: 0.4930, xOhm: 0.2511 },
  { from: 3, to: 4, rOhm: 0.3660, xOhm: 0.1864 },
  { from: 4, to: 5, rOhm: 0.3811, xOhm: 0.1941 },
  { from: 5, to: 6, rOhm: 0.8190, xOhm: 0.7070 },
  { from: 6, to: 7, rOhm: 0.1872, xOhm: 0.6188 },
  { from: 7, to: 8, rOhm: 0.7114, xOhm: 0.2351 },
  { from: 8, to: 9, rOhm: 1.0300, xOhm: 0.7400 },
  { from: 9, to: 10, rOhm: 1.0440, xOhm: 0.7400 },
  { from: 10, to: 11, rOhm: 0.1966, xOhm: 0.0650 },
  { from: 11, to: 12, rOhm: 0.3744, xOhm: 0.1238 },
  { from: 12, to: 13, rOhm: 1.4680, xOhm: 1.1550 },
  { from: 13, to: 14, rOhm: 0.5416, xOhm: 0.7129 },
  { from: 14, to: 15, rOhm: 0.5910, xOhm: 0.5260 },
  { from: 15, to: 16, rOhm: 0.7463, xOhm: 0.5450 },
  { from: 16, to: 17, rOhm: 1.2890, xOhm: 1.7210 },
  { from: 17, to: 18, rOhm: 0.7320, xOhm: 0.5740 },
  { from: 2, to: 19, rOhm: 0.1640, xOhm: 0.1565 },
  { from: 19, to: 20, rOhm: 1.5042, xOhm: 1.3554 },
  { from: 20, to: 21, rOhm: 0.4095, xOhm: 0.4784 },
  { from: 21, to: 22, rOhm: 0.7089, xOhm: 0.9373 },
  { from: 3, to: 23, rOhm: 0.4512, xOhm: 0.3083 },
  { from: 23, to: 24, rOhm: 0.8980, xOhm: 0.7091 },
  { from: 24, to: 25, rOhm: 0.8960, xOhm: 0.7011 },
  { from: 6, to: 26, rOhm: 0.2030, xOhm: 0.1034 },
  { from: 26, to: 27, rOhm: 0.2842, xOhm: 0.1447 },
  { from: 27, to: 28, rOhm: 1.0590, xOhm: 0.9337 },
  { from: 28, to: 29, rOhm: 0.8042, xOhm: 0.7006 },
  { from: 29, to: 30, rOhm: 0.5075, xOhm: 0.2585 },
  { from: 30, to: 31, rOhm: 0.9744, xOhm: 0.9630 },
  { from: 31, to: 32, rOhm: 0.3105, xOhm: 0.3619 },
  { from: 32, to: 33, rOhm: 0.3410, xOhm: 0.5302 },
];

/**
 * Nominal load at each published bus, indexed by bus number (entry 0 is unused,
 * entry 1 is the substation and carries no load). Totals 3715 kW / 2300 kVAr,
 * which is the checksum for this table.
 */
export const NOMINAL_LOAD_KW: readonly number[] = [
  0, 0, 100, 90, 120, 60, 60, 200, 200, 60, 60, 45, 60, 60, 120, 60, 60, 60,
  90, 90, 90, 90, 90, 90, 420, 420, 60, 60, 60, 120, 200, 150, 210, 60,
];

export const NOMINAL_LOAD_KVAR: readonly number[] = [
  0, 0, 60, 40, 80, 30, 20, 100, 100, 20, 20, 30, 35, 35, 80, 10, 20, 20,
  40, 40, 40, 40, 40, 50, 200, 200, 25, 25, 20, 70, 600, 70, 100, 40,
];

/** EV charging stations, published bus numbers. Table 4.1 lists these as 17/21/24/32. */
export const STATION_BUSES: readonly number[] = [18, 22, 25, 33];

/** Rooftop PV, published bus numbers (Figure 4.2). */
export const PV_BUSES: readonly number[] = [6, 13, 30];

/**
 * Substation source impedance. The strong feeder is the canonical benchmark with a
 * stiff source; the weak feeder adds a finite substation impedance, which is the
 * single structural difference between the two grids in the reference study.
 *
 * The weak values here are fitted by `scripts/calibrate.ts` against the reference study’s
 * published base case. Do not hand-edit them — rerun the calibration.
 */
export interface SourceImpedance {
  rOhm: number;
  xOhm: number;
}

export const STRONG_SOURCE: SourceImpedance = { rOhm: 0, xOhm: 0 };
/** Fitted to the reference base case: Vmin 0.882 pu, loss 338.6 kW at full load. */
export const WEAK_SOURCE: SourceImpedance = { rOhm: 0.8604, xOhm: 0.4235 };

export type GridKind = 'weak' | 'strong';

export function sourceImpedanceFor(grid: GridKind): SourceImpedance {
  return grid === 'weak' ? WEAK_SOURCE : STRONG_SOURCE;
}

/** A resolved, solver-ready network: branches in pu, with parent/child structure. */
export interface Network {
  nodeCount: number;
  /** Branch index that feeds each node; -1 for the source. */
  feedBranch: Int32Array;
  branchFrom: Int32Array;
  branchTo: Int32Array;
  branchR: Float64Array;
  branchX: Float64Array;
  /** Nodes ordered so that every parent precedes its children. */
  order: Int32Array;
}

/**
 * Resolve the published data into a solver-ready structure for one grid.
 * The ordering is a breadth-first traversal from the source, which is what lets the
 * backward/forward sweep run in two straight passes with no matrix factorisation.
 */
export function buildNetwork(source: SourceImpedance): Network {
  const branches: Branch[] = [{ from: 0, to: 1, ...source }, ...BRANCHES];
  const n = N_NODE;
  const m = branches.length;

  const branchFrom = new Int32Array(m);
  const branchTo = new Int32Array(m);
  const branchR = new Float64Array(m);
  const branchX = new Float64Array(m);
  const feedBranch = new Int32Array(n).fill(-1);
  const children: number[][] = Array.from({ length: n }, () => []);

  for (let b = 0; b < m; b++) {
    const { from, to, rOhm, xOhm } = branches[b];
    branchFrom[b] = from;
    branchTo[b] = to;
    branchR[b] = rOhm / Z_BASE_OHM;
    branchX[b] = xOhm / Z_BASE_OHM;
    feedBranch[to] = b;
    children[from].push(to);
  }

  const order = new Int32Array(n);
  let head = 0;
  let tail = 0;
  order[tail++] = 0;
  while (head < tail) {
    const node = order[head++];
    for (const child of children[node]) order[tail++] = child;
  }
  if (tail !== n) {
    throw new Error(`network is not a connected radial tree: reached ${tail} of ${n} nodes`);
  }

  return { nodeCount: n, feedBranch, branchFrom, branchTo, branchR, branchX, order };
}

/** Nominal load vectors as pu injections (positive = consumption), indexed by node. */
export function nominalLoadPu(loadScale: number): { p: Float64Array; q: Float64Array } {
  const p = new Float64Array(N_NODE);
  const q = new Float64Array(N_NODE);
  for (let bus = 1; bus <= N_BUS; bus++) {
    p[bus] = (NOMINAL_LOAD_KW[bus] * loadScale) / KW_PER_PU;
    q[bus] = (NOMINAL_LOAD_KVAR[bus] * loadScale) / KW_PER_PU;
  }
  return { p, q };
}
