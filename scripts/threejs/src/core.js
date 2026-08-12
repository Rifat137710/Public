/**
 * The city's foundation: the ground plan every other module lays things out on, and
 * the shared materials it draws with.
 *
 * The physics is not here. The network, the solver and the self-check live in
 * `scripts/shared/grid.js`, which the lesson pages import too — one copy, so the two
 * builds cannot drift into disagreeing about what the town does. This module
 * re-exports them so the rest of the city keeps its single import.
 */

import * as THREE from 'three';
import {
  WORLD, N_BUS, N_NODE, KW_PER_PU, BAND_LO, BAND_HI,
  vMag, branchLossKw, solve, solveAt, sensitivitiesAt, setGrid, grid, check,
} from '../../shared/grid.js';

export {
  WORLD, N_BUS, N_NODE, KW_PER_PU, BAND_LO, BAND_HI,
  vMag, branchLossKw, solve, solveAt, sensitivitiesAt, setGrid, grid, check,
};

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
 *
 * The ceiling is 6.2 m rather than a domestic 4.6 for a reason found by standing in the
 * room: at the dispatch desk your eye is 1.7 m up and the console lids in front of you
 * top out at 1.7 m too, so the sight line to the far wall is horizontal and everything
 * below it on the mimic board — which is where the footer readouts live — is behind a
 * monitor. The board has to start above 1.9 m to be read from the desk, and a board that
 * starts at 1.9 m and is tall enough to be a mimic needs a wall this high to hang on.
 */
export const ROOM = {
  x: -54, z: -14,
  w: 26, d: 18, h: 6.2,
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
  car: new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.34, metalness: 0.45 }),
  tyre: new THREE.MeshStandardMaterial({ color: 0x14181d, roughness: 0.9 }),
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
  tex.anisotropy = maxAnisotropy;
  return new THREE.MeshBasicMaterial({ map: tex, toneMapped: false });
}

/**
 * Board text is read from across the room, at an angle — precisely the case trilinear
 * filtering handles worst, because the mip it picks is sized for the steep axis and the
 * shallow one goes with it. A guessed anisotropy of 4 left the mimic's small type soft
 * from the doorway on hardware that would happily have done 16. The renderer knows what
 * the GPU will actually honour, so ask it instead of guessing. Called once, before any
 * screen is built; the binding is live, so every texture made after picks it up.
 */
export let maxAnisotropy = 4;
export function useAnisotropy(n) {
  maxAnisotropy = Math.max(1, Math.floor(n) || 1);
}

/** The incandescent law, mapped onto the range this feeder actually reaches. */
export function lampBrightness(v) {
  const flux = Math.pow(Math.max(0.01, v), 3.4);
  return Math.min(1, Math.max(0, (flux - 0.5) / 0.47));
}

export const clamp01 = (x) => Math.min(1, Math.max(0, x));
