/**
 * Feeder 33 in Three.js.
 *
 * Same town, same data, same solver as the canvas build — the difference is that
 * every lamp here is a real photometric light, so the falloff on the road, the bloom
 * around the bulb and the shadow off the pole are computed rather than painted.
 */

import * as THREE from 'three';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import WORLD from './world.json';

/* ================================================================== */
/*  The network, and the sweep that solves it (from src/sim)          */
/* ================================================================== */

const N_BUS = 33;
const N_NODE = N_BUS + 1;
const KW_PER_PU = WORLD.kwPerPu;
const BAND_LO = 0.95;
const BAND_HI = 1.05;

const net = (() => {
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
const vMag = new Float64Array(N_NODE);
const branchLossKw = new Float64Array(net.m);

function solve(p, q) {
  vRe.fill(1); vIm.fill(0);
  for (let it = 0; it < 200; it++) {
    iRe.fill(0); iIm.fill(0);
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

function solveAt(day, stationKw) {
  for (let b = 0; b <= N_BUS; b++) { pBuf[b] = day.p[b]; qBuf[b] = day.q[b]; }
  WORLD.stations.forEach((bus, i) => { pBuf[bus] -= stationKw[i] / KW_PER_PU; });
  return solve(pBuf, qBuf);
}

// Same self-check as the canvas build: re-solve every recorded step.
const check = (() => {
  let worstV = 0, worstViol = 0, n = 0;
  for (const run of WORLD.runs) run.frames.forEach((f, i) => {
    const r = solveAt(WORLD.day[i], f.kw);
    worstV = Math.max(worstV, Math.abs(r.vMin - f.vmin));
    worstViol = Math.max(worstViol, Math.abs(r.violations - f.viol));
    n++;
  });
  return { worstV, worstViol, n };
})();

/* ================================================================== */
/*  Town geometry                                                     */
/* ================================================================== */

const COL = 30, LANE = 40, POLE_H = 13, ROAD_W = 13, EYE = 1.7;
const SUB = { x: 2, z: -31 };

const place = new Map();
for (const p of WORLD.places) place.set(p.bus, { ...p, x: p.col * COL, z: p.row * LANE });
const STATION_SET = new Set(WORLD.stations);
const maxX = Math.max(...[...place.values()].map((p) => p.x));

function rng(seed) {
  let a = seed * 1103515245 + 12345;
  return () => { a = (a * 1103515245 + 12345) & 0x7fffffff; return a / 0x7fffffff; };
}

const buildings = [];
const solids = [{ x: SUB.x, z: SUB.z, w: 44, d: 28 }];
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

function stationSpot(bus) {
  const p = place.get(bus);
  return { x: p.x, z: p.z + ROAD_W / 2 + 12 };
}

/* ================================================================== */
/*  Renderer                                                          */
/* ================================================================== */

const canvas = document.getElementById('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x070a0e);
scene.fog = new THREE.FogExp2(0x0a0e13, 0.0042);

const camera = new THREE.PerspectiveCamera(68, 16 / 9, 0.1, 1200);
camera.position.set(-20, EYE, -12);
// A camera with no rotation looks down -Z; the feeder runs along +X. Without this
// you spawn facing an empty field with the whole town behind your shoulder.
camera.rotation.set(0, -Math.PI / 2 + 0.5, 0, 'YXZ');

function resize() {
  const css = canvas.clientWidth || 1280;
  const w = Math.round(css * renderScale);
  const h = Math.round((w * 9) / 16);
  renderer.setPixelRatio(Math.min(devicePixelRatio, renderScale < 1 ? 1 : 1.5));
  renderer.setSize(w, h, false);
  canvas.style.width = '100%';
  camera.aspect = 16 / 9;
  camera.updateProjectionMatrix();
  composer.setSize(w, h);
}

/* -------------------------------------------------------- materials */

const asphalt = new THREE.MeshStandardMaterial({ color: 0x2c343d, roughness: 0.78, metalness: 0.02 });
const ground = new THREE.MeshStandardMaterial({ color: 0x141a21, roughness: 0.95 });
const wallMat = new THREE.MeshStandardMaterial({ color: 0x3c4756, roughness: 0.85 });
const roofMat = new THREE.MeshStandardMaterial({ color: 0x2a323c, roughness: 0.95 });
const steelMat = new THREE.MeshStandardMaterial({ color: 0x39434e, roughness: 0.55, metalness: 0.65 });
const carMat = new THREE.MeshStandardMaterial({ color: 0x2c3742, roughness: 0.35, metalness: 0.5 });
const windowMat = new THREE.MeshBasicMaterial({ toneMapped: false });
const bulbMat = new THREE.MeshBasicMaterial({ toneMapped: false });

/* ------------------------------------------------------------ world */

const groundMesh = new THREE.Mesh(new THREE.PlaneGeometry(2400, 900), ground);
groundMesh.rotation.x = -Math.PI / 2;
groundMesh.position.set(maxX / 2, 0, 8);
groundMesh.receiveShadow = true;
scene.add(groundMesh);

// Roads, one slab per branch plus a stub past each dead end.
{
  const segs = [];
  for (const br of WORLD.branches) {
    const a = place.get(br.from), b = place.get(br.to);
    segs.push([a.x, a.z, b.x, b.z]);
  }
  for (const p of place.values()) {
    if (![...place.values()].some((q) => q.row === p.row && q.col === p.col + 1)) {
      segs.push([p.x, p.z, p.x + COL * 1.4, p.z]);
    }
  }
  const road = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 0.12, 1), asphalt, segs.length);
  road.receiveShadow = true;
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  segs.forEach(([ax, az, bx, bz], i) => {
    const len = Math.hypot(bx - ax, bz - az);
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), -Math.atan2(bz - az, bx - ax));
    m.compose(new THREE.Vector3((ax + bx) / 2, 0.06, (az + bz) / 2), q, new THREE.Vector3(len, 1, ROAD_W));
    road.setMatrixAt(i, m);
  });
  scene.add(road);
}

// Buildings, one draw call.
const town = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), wallMat, buildings.length);
town.castShadow = town.receiveShadow = true;
{
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  buildings.forEach((b, i) => {
    m.compose(new THREE.Vector3(b.x, b.h / 2, b.z), q, new THREE.Vector3(b.w, b.h, b.d));
    town.setMatrixAt(i, m);
  });
}
scene.add(town);

// Roofs, so the tops read as a different material from above.
const roofs = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), roofMat, buildings.length);
{
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  buildings.forEach((b, i) => {
    m.compose(new THREE.Vector3(b.x, b.h + 0.18, b.z), q, new THREE.Vector3(b.w * 1.04, 0.36, b.d * 1.04));
    roofs.setMatrixAt(i, m);
  });
}
roofs.castShadow = true;
scene.add(roofs);

// Windows, emissive quads on the two long faces. One draw call for the town.
const windows = [];
for (const b of buildings) {
  const rows = Math.min(b.floors, 6);
  for (const face of [-1, 1]) {
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < 3; c++) {
        if (b.r() > 0.62) continue;
        windows.push({
          bus: b.bus,
          x: b.x + (c - 1) * (b.w / 3.4),
          y: 1.6 + (r + 0.5) * ((b.h - 2.2) / rows),
          z: b.z + face * (b.d / 2 + 0.06),
          face,
        });
      }
    }
  }
}
const winMesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1.5, 1.9), windowMat, windows.length);
{
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const one = new THREE.Vector3(1, 1, 1);
  windows.forEach((w, i) => {
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), w.face > 0 ? 0 : Math.PI);
    m.compose(new THREE.Vector3(w.x, w.y, w.z), q, one);
    winMesh.setMatrixAt(i, m);
    winMesh.setColorAt(i, new THREE.Color(0x111820));
  });
}
scene.add(winMesh);

// Poles and lamp bulbs.
const poles = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.16, 0.22, POLE_H, 8), steelMat, place.size);
poles.castShadow = true;
const bulbs = new THREE.InstancedMesh(new THREE.SphereGeometry(0.42, 12, 10), bulbMat, place.size);
const cones = new THREE.InstancedMesh(
  new THREE.ConeGeometry(4.0, POLE_H, 18, 1, true),
  new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.07, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false, toneMapped: false }),
  place.size,
);

const lamps = [];
{
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const one = new THREE.Vector3(1, 1, 1);
  let i = 0;
  for (const p of place.values()) {
    const px = p.x, pz = p.z - ROAD_W / 2 - 1.4;
    m.compose(new THREE.Vector3(px, POLE_H / 2, pz), q, one);
    poles.setMatrixAt(i, m);
    m.compose(new THREE.Vector3(px, POLE_H + 0.5, pz), q, one);
    bulbs.setMatrixAt(i, m);
    m.compose(new THREE.Vector3(px, POLE_H / 2 + 0.4, pz), q, one);
    cones.setMatrixAt(i, m);
    lamps.push({ bus: p.bus, index: i, pos: new THREE.Vector3(px, POLE_H + 0.5, pz), flux: 1, colour: new THREE.Color() });
    i++;
  }
}
// The light cones are gone: an additively-blended cone mesh reads as a hard
// silhouette rather than a shaft, and a convincing volumetric needs raymarching
// through the light's own falloff, which is a different piece of work.
scene.add(poles, bulbs);

// Conductors, hanging in a catenary, one mesh each so heat can be set per branch.
const conductors = WORLD.branches.map((br) => {
  const a = place.get(br.from), b = place.get(br.to);
  const p1 = new THREE.Vector3(a.x, POLE_H, a.z - ROAD_W / 2 - 1.4);
  const p2 = new THREE.Vector3(b.x, POLE_H, b.z - ROAD_W / 2 - 1.4);
  const mid = p1.clone().lerp(p2, 0.5);
  mid.y -= 1.1 + p1.distanceTo(p2) * 0.012;
  const curve = new THREE.CatmullRomCurve3([p1, mid, p2]);
  const mat = new THREE.MeshStandardMaterial({ color: 0x2b3540, roughness: 0.6, emissive: new THREE.Color(0x000000) });
  const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 10, 0.07, 5, false), mat);
  scene.add(mesh);
  return mesh;
});

/* ------------------------------------------------------ substation */

{
  const g = new THREE.Group();
  const fence = (x, z, w, d) => {
    const mm = new THREE.Mesh(new THREE.BoxGeometry(w, 3.2, d), steelMat);
    mm.position.set(x, 1.6, z);
    mm.castShadow = mm.receiveShadow = true;
    g.add(mm);
  };
  fence(SUB.x, SUB.z - 13, 42, 0.5);
  fence(SUB.x, SUB.z + 13, 42, 0.5);
  fence(SUB.x - 21, SUB.z, 0.5, 26);
  fence(SUB.x + 21, SUB.z, 0.5, 26);

  const tank = new THREE.Mesh(new THREE.BoxGeometry(11, 7.5, 9), steelMat);
  tank.position.set(SUB.x - 8, 3.75, SUB.z - 2);
  tank.castShadow = true;
  g.add(tank);

  const tank2 = new THREE.Mesh(new THREE.CylinderGeometry(3.4, 3.4, 6, 14), steelMat);
  tank2.position.set(SUB.x + 8, 3, SUB.z - 1);
  tank2.castShadow = true;
  g.add(tank2);

  for (const dx of [-6, 4]) {
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.9, 15, 0.9), steelMat);
    post.position.set(SUB.x + dx, 7.5, SUB.z + 7);
    post.castShadow = true;
    g.add(post);
  }
  const beam = new THREE.Mesh(new THREE.BoxGeometry(12, 0.6, 0.6), steelMat);
  beam.position.set(SUB.x - 1, 14.7, SUB.z + 7);
  g.add(beam);

  // Yard floodlights: the substation is fed from the grid side and does not sag
  // with the town, so these are the one constant light source in the scene.
  for (const dx of [-15, 15]) {
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.2, 12, 8), steelMat);
    mast.position.set(SUB.x + dx, 6, SUB.z + 9);
    g.add(mast);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.5, 10, 8), new THREE.MeshBasicMaterial({ color: 0xd8e6f0, toneMapped: false }));
    head.position.set(SUB.x + dx, 12.4, SUB.z + 9);
    g.add(head);
    const l = new THREE.PointLight(0xcfe2f0, 2400, 110, 2);
    l.position.set(SUB.x + dx, 12.4, SUB.z + 9);
    g.add(l);
  }
  scene.add(g);
}

/* --------------------------------------------------------- stations */

const stationGroups = WORLD.stations.map((bus) => {
  const s = stationSpot(bus);
  const g = new THREE.Group();
  const canopy = new THREE.Mesh(new THREE.BoxGeometry(22, 0.7, 12), steelMat);
  canopy.position.set(s.x, 6.6, s.z);
  canopy.castShadow = true;
  g.add(canopy);
  const strip = new THREE.Mesh(new THREE.BoxGeometry(21, 0.22, 11), new THREE.MeshBasicMaterial({ color: 0x4fb3a2, toneMapped: false }));
  strip.position.set(s.x, 6.18, s.z);
  g.add(strip);
  for (const dx of [-9, 9]) {
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.8, 6.6, 0.8), steelMat);
    post.position.set(s.x + dx, 3.3, s.z);
    post.castShadow = true;
    g.add(post);
  }
  const console_ = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.3, 2.1), steelMat);
  console_.position.set(s.x - 12.5, 0.65, s.z - 4);
  g.add(console_);
  const light = new THREE.PointLight(0x4fb3a2, 700, 52, 2);
  light.position.set(s.x, 6, s.z);
  g.add(light);
  scene.add(g);
  return { bus, spot: s, strip, light };
});

// Cars.
const cars = new THREE.InstancedMesh(new THREE.BoxGeometry(2.4, 1.45, 4.4), carMat, 48);
cars.castShadow = true;
scene.add(cars);

/* ------------------------------------------------------ light pool */

const POOL = 7;
let poolLimit = 7;
const pool = Array.from({ length: POOL }, (_, i) => {
  const l = new THREE.PointLight(0xe3b24f, 0, 78, 2);
  // Only the two nearest cast shadows: a shadow-casting point light is six render
  // passes, and thirty-three of them is not a thing any browser will do.
  if (i < 1) {
    l.castShadow = true;
    l.shadow.mapSize.set(512, 512);
    l.shadow.camera.near = 0.6;
    l.shadow.camera.far = 70;
    l.shadow.bias = -0.006;
  }
  scene.add(l);
  return l;
});

scene.add(new THREE.HemisphereLight(0x33455c, 0x0b1016, 1.7));

/* ---------------------------------------------------------- passes */

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
// Bloom is low-frequency by nature, so it is computed at half resolution: five blur
// mips at full size cost real milliseconds and buy nothing you can see.
const bloom = new UnrealBloomPass(new THREE.Vector2(640, 360), 0.62, 0.72, 0.62);
composer.addPass(bloom);
const outputPass = new OutputPass();
composer.addPass(outputPass);

/**
 * Quality falls back on its own rather than asking the visitor to diagnose it.
 *
 * Measured on this scene, frame cost is dominated by fragments, not by draw calls or
 * by the number of lights: halving the render size roughly triples the frame rate,
 * while emptying the light pool changes nothing. So the ladder ends in resolution,
 * which is the lever that actually moves.
 */
let tier = 3;
let renderScale = 1;
let autoQuality = true;

function setTier(next) {
  next = Math.max(0, Math.min(3, next));
  if (next === tier) return;
  tier = next;
  renderer.shadowMap.enabled = tier >= 3;
  const toggle = el('shadowsToggle');
  toggle.checked = tier >= 3;
  toggle.disabled = tier < 3;
  const wantBloom = tier >= 2;
  const hasBloom = composer.passes.includes(bloom);
  if (wantBloom && !hasBloom) composer.insertPass(bloom, 1);
  if (!wantBloom && hasBloom) composer.removePass(bloom);
  renderScale = tier >= 1 ? 1 : 0.6;
  scene.traverse((o) => { if (o.material) o.material.needsUpdate = true; });
  resize();
  el('tier').textContent = TIER_NAMES[tier];
}

const TIER_NAMES = ['reduced resolution', 'no bloom', 'no shadows', 'full quality'];

resize();
addEventListener('resize', resize);

/* ================================================================== */
/*  Voltage -> light                                                  */
/* ================================================================== */

const WARM = new THREE.Color(0xe3b24f);
const SICK = new THREE.Color(0xe4776b);
const scratch = new THREE.Color();

function applyVoltages() {
  lamps.forEach((lamp) => {
    const v = vMag[lamp.bus];
    // The same V^3.4 incandescent law the canvas build uses, stretched across the
    // range this feeder actually reaches so the eye can read it.
    const flux = Math.pow(Math.max(0.01, v), 3.4);
    const b = Math.min(1, Math.max(0, (flux - 0.5) / 0.47));
    const health = Math.min(1, Math.max(0, (v - 0.84) / 0.11));
    lamp.flux = 0.1 + 0.9 * b;
    lamp.colour.copy(v >= BAND_LO ? WARM : scratch.copy(SICK).lerp(WARM, health));
    bulbs.setColorAt(lamp.index, scratch.copy(lamp.colour).multiplyScalar(0.35 + 2.6 * lamp.flux));
    });
  bulbs.instanceColor.needsUpdate = true;

  windows.forEach((w, i) => {
    const v = vMag[w.bus];
    const flux = Math.pow(Math.max(0.01, v), 3.4);
    const b = Math.min(1, Math.max(0, (flux - 0.5) / 0.47));
    const health = Math.min(1, Math.max(0, (v - 0.84) / 0.11));
    scratch.copy(v >= BAND_LO ? WARM : SICK.clone().lerp(WARM, health)).multiplyScalar(0.16 + 1.5 * b);
    winMesh.setColorAt(i, scratch);
  });
  winMesh.instanceColor.needsUpdate = true;

  conductors.forEach((mesh, i) => {
    const heat = Math.min(1, branchLossKw[i + 1] / 4);
    mesh.material.emissive.setRGB(heat * 0.85, heat * 0.24, heat * 0.2);
  });
}

function assignPool() {
  const near = lamps
    .map((l) => ({ l, d: l.pos.distanceToSquared(camera.position) }))
    .sort((a, b) => a.d - b.d)
    .slice(0, POOL);
  pool.forEach((light, i) => {
    const hit = i < poolLimit ? near[i] : null;
    if (!hit) { light.intensity = 0; return; }
    light.position.copy(hit.l.pos);
    light.color.copy(hit.l.colour);
    light.intensity = 1550 * hit.l.flux;
  });
}

/* ================================================================== */
/*  State + HUD                                                       */
/* ================================================================== */

let runIndex = 0, frameIndex = 0, playing = true, solution = null;
const manual = [null, null, null, null];
let panelTarget = null;

const el = (id) => document.getElementById(id);
const run = () => WORLD.runs[runIndex];
const commands = () => run().frames[frameIndex].kw.map((k, i) => (manual[i] === null ? k : manual[i]));

function resolveNow() {
  solution = solveAt(WORLD.day[frameIndex], commands());
  applyVoltages();
  updateCars();
  stationGroups.forEach((s, i) => {
    const kw = commands()[i];
    const c = manual[i] !== null || kw > 1 ? WARM : new THREE.Color(0x4fb3a2);
    s.strip.material.color.copy(c);
    s.light.color.copy(c);
    s.light.intensity = 420 + Math.min(1, Math.abs(kw) / 700) * 900;
  });
}

function updateCars() {
  const f = run().frames[frameIndex];
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const one = new THREE.Vector3(1, 1, 1);
  let n = 0;
  WORLD.stations.forEach((bus, si) => {
    const s = stationSpot(bus);
    const shown = Math.min(12, f.plugged[si]);
    for (let i = 0; i < shown && n < 48; i++) {
      const col = Math.floor(i / 2);
      m.compose(new THREE.Vector3(s.x - 8 + col * 3.4, 0.75, s.z - 3 + (i % 2) * 6), q, one);
      cars.setMatrixAt(n++, m);
    }
  });
  const hide = new THREE.Matrix4().makeScale(0.0001, 0.0001, 0.0001);
  for (; n < 48; n++) cars.setMatrixAt(n, hide);
  cars.instanceMatrix.needsUpdate = true;
  cars.count = 48;
}

function nearestBus() {
  let best = 1, bestD = Infinity;
  for (const p of place.values()) {
    const d = Math.hypot(p.x - camera.position.x, p.z - camera.position.z);
    if (d < bestD) { bestD = d; best = p.bus; }
  }
  return best;
}

function setMetric(node, label, value, tone) {
  node.className = 'metric' + (tone ? ' ' + tone : '');
  node.innerHTML = label + ' <b>' + value + '</b>';
}

function updateHud() {
  const bus = nearestBus();
  const v = vMag[bus];
  const p = place.get(bus);
  el('where').innerHTML = bus === 1 ? 'at the <em>substation</em>'
    : `at <em>bus</em> ${bus}` + (STATION_SET.has(bus) ? ' <em>· charging station</em>' : '');
  const here = el('here');
  here.textContent = v.toFixed(3) + ' pu';
  here.className = 'here ' + (v < BAND_LO ? 'bad' : 'good');
  el('walked').textContent =
    `${Math.round(Math.hypot(camera.position.x, camera.position.z))} m from the substation · ${p.col} hops`;

  const f = run().frames[frameIndex];
  setMetric(el('mClock'), 'time', f.clock);
  setMetric(el('mRun'), 'driving', run().label.replace(/ \(.*\)/, ''));
  const chip = el('runChip');
  const anyManual = manual.some((m) => m !== null);
  const standIn = run().provenance === 'placeholder';
  chip.textContent = anyManual ? 'you have taken over' : standIn ? 'labelled stand-in' : 'real controller';
  chip.className = 'chip ' + (anyManual ? 'mine' : standIn ? 'stand-in' : 'real');
  setMetric(el('mViol'), 'out of band', solution.violations + (solution.violations === 1 ? ' bus' : ' buses'), solution.violations > 0 ? 'bad' : 'good');
  setMetric(el('mLoss'), 'burnt in lines', solution.lossKw.toFixed(0) + ' kW');
  if (panelTarget) renderPanel();
}

/* ------------------------------------------------------ interaction */

const TARGETS = [];
for (const p of place.values()) {
  if (p.bus === 1) TARGETS.push({ kind: 'substation', bus: 1, x: SUB.x, z: SUB.z + 14, label: 'Read the substation board' });
  else TARGETS.push({ kind: 'meter', bus: p.bus, x: p.x, z: p.z - ROAD_W / 2 - 0.6, label: `Read the meter at bus ${p.bus}` });
}
WORLD.stations.forEach((bus, si) => {
  const s = stationSpot(bus);
  TARGETS.push({ kind: 'station', bus, si, x: s.x - 12.5, z: s.z - 4, label: `Operate the charging station at bus ${bus}` });
});

const fwdTmp = new THREE.Vector3();

function focused() {
  camera.getWorldDirection(fwdTmp);
  const fx = fwdTmp.x, fz = fwdTmp.z;
  const fl = Math.hypot(fx, fz) || 1;
  let best = null, bestScore = Infinity;
  for (const it of TARGETS) {
    const dx = it.x - camera.position.x, dz = it.z - camera.position.z;
    const dist = Math.hypot(dx, dz);
    if (dist > 11) continue;
    const dot = (dx * (fx / fl) + dz * (fz / fl)) / (dist || 1);
    if (dot < 0.55) continue;
    const score = dist * (2 - dot);
    if (score < bestScore) { bestScore = score; best = it; }
  }
  return best;
}

function profileSvg(markBus) {
  const w = 300, h = 62, pad = 4;
  const xs = (i) => pad + (i / 32) * (w - pad * 2);
  const ys = (v) => h - pad - ((v - 0.82) / 0.2) * (h - pad * 2);
  let d = '';
  for (let bus = 1; bus <= N_BUS; bus++) d += (bus === 1 ? 'M' : 'L') + xs(bus - 1).toFixed(1) + ' ' + ys(vMag[bus]).toFixed(1);
  const bandY = ys(BAND_LO);
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">
    <line x1="${pad}" y1="${bandY}" x2="${w - pad}" y2="${bandY}" stroke="#E4776B" stroke-dasharray="3 3"/>
    <path d="${d}" fill="none" stroke="#4FB3A2" stroke-width="1.6"/>
    <circle cx="${xs(markBus - 1).toFixed(1)}" cy="${ys(vMag[markBus]).toFixed(1)}" r="3.6" fill="#E3B24F"/>
    <text x="${w - pad}" y="${bandY - 3}" fill="#E4776B" font-size="8" text-anchor="end">0.95 floor</text>
  </svg>`;
}

const rowOf = (k, v) => `<div class="row"><span>${k}</span><span>${v}</span></div>`;
const fmtKw = (kw) => (Math.abs(kw) < 1 ? 'idle' : kw < 0 ? Math.abs(kw).toFixed(0) + ' kW drawn' : kw.toFixed(0) + ' kW returned');

function renderPanel() {
  const panel = el('panel');
  const t = panelTarget;
  if (!t) { panel.hidden = true; return; }
  panel.hidden = false;
  if (t.kind === 'substation') {
    panel.innerHTML = `<button class="close" id="panelClose">×</button>
      <div class="kicker">Bus 1 · where the town meets the grid</div><h3>Substation</h3>
      ${rowOf('grid behind the transformer', vMag[0].toFixed(4) + ' pu — assumed')}
      ${rowOf('this busbar right now', vMag[1].toFixed(4) + ' pu')}
      ${rowOf('already lost, here', ((vMag[0] - vMag[1]) * 100).toFixed(1) + ' % of nominal')}
      <p>Only the first is an assumption. The busbar is already below the grid before the town
      begins — because this feeder is <em>weak</em>: there is real impedance between here and the
      grid, so even the substation moves when the town pulls.</p>
      <div class="profile">${profileSvg(1)}</div>`;
  } else if (t.kind === 'meter') {
    const p = place.get(t.bus);
    const v = vMag[t.bus];
    panel.innerHTML = `<button class="close" id="panelClose">×</button>
      <div class="kicker">Bus ${t.bus} · ${p.row === 0 ? 'main road' : 'lateral ' + Math.abs(p.row)}</div>
      <h3>Street meter</h3>
      ${rowOf('voltage now', v.toFixed(4) + ' pu')}
      ${rowOf('status', v < BAND_LO ? '<span class="warn">below the 0.95 floor</span>' : '<span class="ok">inside the band</span>')}
      ${rowOf('load here', p.kw + ' kW / ' + p.kvar + ' kVAr')}
      ${rowOf('hops from substation', p.col)}
      <div class="profile">${profileSvg(t.bus)}</div>
      <p class="hint">The whole feeder, left to right by bus number. You are the amber dot.</p>`;
  } else {
    const f = run().frames[frameIndex];
    const value = manual[t.si] === null ? f.kw[t.si] : manual[t.si];
    panel.innerHTML = `<button class="close" id="panelClose">×</button>
      <div class="kicker">Bus ${t.bus} · charging station</div><h3>Station console</h3>
      ${rowOf('plugged in now', f.plugged[t.si] + ' vehicles')}
      ${rowOf('controller wants', fmtKw(f.kw[t.si]))}
      ${rowOf('voltage here', vMag[t.bus].toFixed(4) + ' pu')}
      <label class="slider" for="stationKw">Your setting</label>
      <input id="stationKw" type="range" min="-900" max="400" step="10" value="${value}" />
      <div class="readout" id="stationRead">${fmtKw(value)}</div>
      <button class="act" id="handBack">${manual[t.si] === null ? 'Take this station off the controller' : 'Give it back to the controller'}</button>
      <div class="profile">${profileSvg(t.bus)}</div>
      <p class="hint">Drag left to charge harder. Every lamp you can see is lit by the answer.</p>`;
    const slider = el('stationKw');
    slider.oninput = () => {
      manual[t.si] = Number(slider.value);
      resolveNow();
      el('stationRead').textContent = fmtKw(manual[t.si]);
      updateHud();
    };
    el('handBack').onclick = () => {
      manual[t.si] = manual[t.si] === null ? Number(slider.value) : null;
      resolveNow();
      updateHud();
    };
  }
  el('panelClose').onclick = closePanel;
}

function openPanel(t) { panelTarget = t; controls.unlock(); renderPanel(); }
function closePanel() { panelTarget = null; el('panel').hidden = true; }

/* ------------------------------------------------------------ input */

const controls = new PointerLockControls(camera, renderer.domElement);
const held = new Set();

renderer.domElement.addEventListener('click', () => { if (!panelTarget) controls.lock(); });
el('enter').addEventListener('click', () => controls.lock());
controls.addEventListener('lock', () => { el('enter').hidden = true; });
controls.addEventListener('unlock', () => { el('enter').hidden = !!panelTarget; held.clear(); });

addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (['w', 'a', 's', 'd', 'shift'].includes(k)) { held.add(k); if (controls.isLocked) e.preventDefault(); }
  if (k === 'e' && controls.isLocked) { const t = focused(); if (t) { openPanel(t); e.preventDefault(); } }
  if (k === 'escape' && panelTarget) closePanel();
});
addEventListener('keyup', (e) => held.delete(e.key.toLowerCase()));

function collide(nx, nz) {
  const R = 0.9;
  let x = nx, z = nz;
  for (const s of solids) {
    const minX = s.x - s.w / 2 - R, maxX = s.x + s.w / 2 + R;
    const minZ = s.z - s.d / 2 - R, maxZ = s.z + s.d / 2 + R;
    if (x > minX && x < maxX && z > minZ && z < maxZ) {
      const dl = x - minX, dr = maxX - x, du = z - minZ, dd = maxZ - z;
      const m = Math.min(dl, dr, du, dd);
      if (m === dl) x = minX; else if (m === dr) x = maxX;
      else if (m === du) z = minZ; else z = maxZ;
    }
  }
  return { x, z };
}

const dirF = new THREE.Vector3();
const dirR = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);

function move(dt) {
  if (!controls.isLocked) return;
  let f = 0, s = 0;
  if (held.has('w')) f += 1;
  if (held.has('s')) f -= 1;
  if (held.has('d')) s += 1;
  if (held.has('a')) s -= 1;
  if (!f && !s) return;
  const len = Math.hypot(f, s);
  f /= len; s /= len;
  camera.getWorldDirection(dirF);
  dirF.y = 0; dirF.normalize();
  dirR.crossVectors(dirF, UP).normalize().multiplyScalar(-1);
  const speed = (held.has('shift') ? 34 : 14) * dt;
  const nx = camera.position.x + (dirF.x * f + dirR.x * s) * speed;
  const nz = camera.position.z + (dirF.z * f + dirR.z * s) * speed;
  const out = collide(nx, nz);
  camera.position.x = Math.max(-90, Math.min(maxX + 90, out.x));
  camera.position.z = Math.max(-130, Math.min(170, out.z));
  camera.position.y = EYE;
}

/* ------------------------------------------------------- page chrome */

const runSeg = el('runSeg');
WORLD.runs.forEach((r, i) => {
  const b = document.createElement('button');
  b.textContent = r.label.replace(/ \(.*\)/, '').replace('IEEE 1547', '1547');
  b.title = r.label;
  b.setAttribute('aria-pressed', String(i === 0));
  b.onclick = () => {
    runIndex = i;
    [...runSeg.children].forEach((c, j) => c.setAttribute('aria-pressed', String(j === i)));
    resolveNow(); updateHud();
  };
  runSeg.appendChild(b);
});

const goSeg = el('goSeg');
[['Substation gate', -20, -12, -0.5],
 ['Bus 18, the far end', place.get(18).x - 40, 2, 0],
 ['The long lateral', place.get(30).x - 34, place.get(30).z + 2, 0],
 ['The 420 kW loads', place.get(24).x - 28, place.get(24).z + 2, 0]].forEach(([label, x, z, yaw]) => {
  const b = document.createElement('button');
  b.textContent = label;
  b.onclick = () => {
    camera.position.set(x, EYE, z);
    camera.rotation.set(0, -yaw - Math.PI / 2, 0, 'YXZ');
    closePanel(); updateHud();
  };
  goSeg.appendChild(b);
});

const scrub = el('scrub');
scrub.max = String(WORLD.day.length - 1);
scrub.oninput = () => {
  frameIndex = Number(scrub.value);
  playing = false;
  el('play').textContent = 'Play';
  resolveNow(); updateHud();
};
el('play').onclick = () => {
  playing = !playing;
  el('play').textContent = playing ? 'Pause' : 'Play';
};
el('bloomRange').oninput = (e) => { bloom.strength = Number(e.target.value); };
el('shadowsToggle').onchange = (e) => {
  renderer.shadowMap.enabled = e.target.checked;
  scene.traverse((o) => { if (o.material) o.material.needsUpdate = true; });
};
el('tier').textContent = TIER_NAMES[tier];

const totals = el('totals');
WORLD.runs.forEach((r) => {
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${r.label}</td><td class="num">${r.violationRate.toFixed(3)}</td>` +
    `<td class="num">${Math.round(r.socMet * 287)} of 287</td>` +
    `<td class="num">${r.totalLossKwh.toFixed(0)} kWh</td>` +
    `<td class="num">${r.vMinPu.toFixed(3)} pu</td>` +
    `<td>${r.provenance === 'placeholder' ? 'labelled stand-in' : 'production controller'}</td>`;
  totals.appendChild(tr);
});

el('verdict').textContent = check.worstV < 5e-4 && check.worstViol === 0
  ? `${check.n} steps re-solved in the browser, worst voltage disagreement ${check.worstV.toExponential(1)} pu, violation counts identical.`
  : `MISMATCH — ${check.worstV.toExponential(2)} pu. Do not trust these numbers.`;

/* ------------------------------------------------------------- loop */

let lastT = 0, lastTick = 0, frames = 0, fpsT = 0, slowSeconds = 0;

function loop(t) {
  requestAnimationFrame(loop);
  const dt = Math.min(0.05, (t - lastT) / 1000);
  lastT = t;

  if (playing && t - lastTick > 110) {
    lastTick = t;
    frameIndex = (frameIndex + 1) % WORLD.day.length;
    scrub.value = String(frameIndex);
    resolveNow();
    updateHud();
  }

  move(dt);
  assignPool();

  const target = controls.isLocked ? focused() : null;
  const prompt = el('prompt');
  el('reticle').className = 'reticle' + (target ? ' hot' : '');
  if (target && !panelTarget) { prompt.hidden = false; prompt.innerHTML = '<kbd>E</kbd>' + target.label; }
  else prompt.hidden = true;

  if (controls.isLocked) updateHud();

  composer.render();

  frames++;
  if (t - fpsT > 1000) {
    const fps = frames;
    el('fps').textContent = fps + ' fps · ' + TIER_NAMES[tier];
    frames = 0; fpsT = t;
    // Give the scene a couple of seconds to warm up, then drop a tier per second
    // for as long as it is running badly. It never climbs back on its own — a
    // display that oscillates between quality levels is worse than a lower one.
    if (autoQuality && t > 4000 && fps < 24) { if (++slowSeconds >= 2) { setTier(tier - 1); slowSeconds = 0; } }
    else slowSeconds = 0;
  }
}

resolveNow();
updateHud();
requestAnimationFrame(loop);

window.__scene = { camera, controls, focused, openPanel, check, updateHud, solution: () => solution, renderer, composer, setPoolSize(n) { poolLimit = n; }, lockQuality() { autoQuality = false; setTier(3); } };
