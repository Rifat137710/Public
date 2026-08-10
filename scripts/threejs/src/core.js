/**
 * Shared foundation for the city: the network, the solver that answers it, and the
 * ground plan every other module lays things out on.
 *
 * The solver is the same backward/forward sweep as `src/sim/powerflow.ts`, ported so
 * the world can answer when somebody changes something. It is not trusted on the
 * strength of being a port — `check` below re-solves every recorded control step and
 * compares against the engine that produced them.
 */

import * as THREE from 'three';
import WORLD from '../world.json';

export { WORLD };

export const N_BUS = 33;
export const N_NODE = N_BUS + 1;
export const KW_PER_PU = WORLD.kwPerPu;
export const BAND_LO = 0.95;
export const BAND_HI = 1.05;

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
 * recorded it. A port that agrees to 1e-4 pu across 1152 steps is a port; one that is
 * merely believed is a liability, because everything the city teaches is downstream
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

/* ================================================================== */
/*  Ground plan                                                       */
/* ================================================================== */

export const COL = 30;      // metres of road per electrical hop
export const LANE = 40;     // lateral spacing
export const POLE_H = 13;
export const ROAD_W = 13;
export const EYE = 1.7;

export const SUB = { x: 2, z: -31 };

/**
 * The control centre. It sits west of the substation, so you start the day inside it
 * and the walk out to the feeder is the first thing the city asks of you.
 * Interior is 26 x 18, door on the east wall.
 */
export const ROOM = {
  x: -54, z: -14,
  w: 26, d: 18, h: 4.6,
  doorZ: -14, doorW: 4.4,
  get west() { return this.x - this.w / 2; },
  get east() { return this.x + this.w / 2; },
  get north() { return this.z - this.d / 2; },
  get south() { return this.z + this.d / 2; },
};

export function rng(seed) {
  let a = seed * 1103515245 + 12345;
  return () => { a = (a * 1103515245 + 12345) & 0x7fffffff; return a / 0x7fffffff; };
}

export const place = new Map();
for (const p of WORLD.places) place.set(p.bus, { ...p, x: p.col * COL, z: p.row * LANE });

export const STATION_SET = new Set(WORLD.stations);
export const PV_SET = new Set(WORLD.pv);
export const maxX = Math.max(...[...place.values()].map((p) => p.x));

export function stationSpot(bus) {
  const p = place.get(bus);
  return { x: p.x, z: p.z + ROAD_W / 2 + 12 };
}

/** Axis-aligned blockers. Walls go in as separate segments so doorways are just gaps. */
export const solids = [{ x: SUB.x, z: SUB.z, w: 44, d: 28 }];

export const buildings = [];
for (const p of place.values()) {
  if (p.bus === 1) continue;
  const r = rng(p.bus * 977 + 13);
  const perSide = Math.ceil(p.houses / 2);
  const kwEach = p.kw / Math.max(1, p.houses);
  for (let i = 0; i < p.houses; i++) {
    const side = i % 2 === 0 ? 1 : -1;
    const slot = Math.floor(i / 2);
    const along = (slot - (perSide - 1) / 2) * 12 + (r() - 0.5) * 3;
    const off = side * (ROAD_W / 2 + 8 + r() * 3.5);
    const w = 7 + r() * 3.6, d = 7 + r() * 3.6;
    const h = 8 + Math.sqrt(kwEach) * 1.75 + r() * 4;
    const b = { bus: p.bus, x: p.x + along, z: p.z + off, w, d, h, floors: Math.max(1, Math.round(h / 5.5)), r };
    buildings.push(b);
    solids.push({ x: b.x, z: b.z, w, d });
  }
}

/* ================================================================== */
/*  Shared materials and palette                                      */
/* ================================================================== */

export const PALETTE = {
  warm: 0xe3b24f,   // healthy sodium
  sick: 0xe4776b,   // browned out
  cool: 0x4fb3a2,   // charging infrastructure
  ice:  0xcfe2f0,   // grid-side floodlight
  alarm: 0xe4776b,
};

export const mat = {
  asphalt: new THREE.MeshStandardMaterial({ color: 0x2c343d, roughness: 0.78, metalness: 0.02 }),
  ground: new THREE.MeshStandardMaterial({ color: 0x141a21, roughness: 0.95 }),
  wall: new THREE.MeshStandardMaterial({ color: 0x3c4756, roughness: 0.85 }),
  roof: new THREE.MeshStandardMaterial({ color: 0x2a323c, roughness: 0.95 }),
  steel: new THREE.MeshStandardMaterial({ color: 0x39434e, roughness: 0.55, metalness: 0.65 }),
  car: new THREE.MeshStandardMaterial({ color: 0x2c3742, roughness: 0.35, metalness: 0.5 }),
  glass: new THREE.MeshStandardMaterial({ color: 0x14202b, roughness: 0.18, metalness: 0.3 }),
  roomFloor: new THREE.MeshStandardMaterial({ color: 0x232a33, roughness: 0.72 }),
  roomWall: new THREE.MeshStandardMaterial({ color: 0x323b46, roughness: 0.9 }),
  cabinet: new THREE.MeshStandardMaterial({ color: 0x2b333d, roughness: 0.6, metalness: 0.35 }),
  desk: new THREE.MeshStandardMaterial({ color: 0x2a323b, roughness: 0.65, metalness: 0.2 }),
};

/**
 * A screen face. Emissive-by-basic so the panel reads at its drawn brightness rather
 * than being relit by the room, which is how a real backlit display behaves.
 */
export function screenMaterial(canvas) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return new THREE.MeshBasicMaterial({ map: tex, toneMapped: false });
}

/** The incandescent law, mapped onto the range this feeder actually reaches. */
export function lampBrightness(v) {
  const flux = Math.pow(Math.max(0.01, v), 3.4);
  return Math.min(1, Math.max(0, (flux - 0.5) / 0.47));
}

export const clamp01 = (x) => Math.min(1, Math.max(0, x));
