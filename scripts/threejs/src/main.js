/**
 * Bootstrap: renderer, the two places (city and control room), the mission runner,
 * and the loop that keeps them agreeing with each other.
 *
 * The one rule this file enforces is that there is a single source of truth. Every
 * instrument, lamp, car and readout is redrawn from one `solution` object produced by
 * one call to the solver. Nothing gets to cache a number and drift.
 */

import * as THREE from 'three';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

import {
  WORLD, N_BUS, BAND_LO, BAND_HI, EYE, ROOM, SUB, ROAD_W, place, solids, maxX, check,
  solveAt, setGrid, vMag, branchLossKw, STATION_SET, PALETTE,
} from './core.js';
import { buildCity } from './city.js';
import { buildRoom } from './room.js';
import { buildSky } from './sky.js';
import { STAGES, Progress } from './mission.js';
import { FleetRun, fleetCheck } from '../../shared/fleet.js';
import { OBJECTIVES, findings, coverage } from './debrief.js';

const el = (id) => document.getElementById(id);

/* ================================================================== */
/*  Renderer                                                          */
/* ================================================================== */

const canvas = el('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x070a0e);
scene.fog = new THREE.FogExp2(0x0a0e13, 0.0042);

const camera = new THREE.PerspectiveCamera(68, 16 / 9, 0.1, 1200);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
// Bloom is low-frequency by nature, so it runs at half resolution: five blur mips at
// full size cost real milliseconds and buy nothing the eye can find.
const bloom = new UnrealBloomPass(new THREE.Vector2(640, 360), 0.62, 0.72, 0.62);
composer.addPass(bloom);
composer.addPass(new OutputPass());

let renderScale = 1;
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

/* ================================================================== */
/*  World                                                             */
/* ================================================================== */

const city = buildCity(scene);
const room = buildRoom(scene);

const sky = buildSky(scene);

// A small pool of real lights follows the camera. Thirty-three shadow-casting point
// lights is not something a browser will do; seven that move is indistinguishable.
const POOL = 7;
let poolLimit = POOL;
const pool = Array.from({ length: POOL }, (_, i) => {
  const l = new THREE.PointLight(PALETTE.warm, 0, 78, 2);
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

/** How far up the sun is, 0 to 1. Kept here so the lamp pool can fade against it. */
let daylight = 0;

function assignPool() {
  const near = city.lamps
    .map((l) => ({ l, d: l.pos.distanceToSquared(camera.position) }))
    .sort((a, b) => a.d - b.d)
    .slice(0, POOL);
  // Street lighting stops mattering once the sun is up — a 1550-candela point light at
  // noon only washes out the face it lands on. It is dimmed rather than switched, so
  // dusk brings the lamps up gradually instead of snapping them on.
  const throw_ = 1 - 0.8 * daylight;
  pool.forEach((light, i) => {
    const hit = i < poolLimit ? near[i] : null;
    if (!hit) { light.intensity = 0; return; }
    light.position.copy(hit.l.pos);
    light.color.copy(hit.l.colour);
    light.intensity = 1550 * hit.l.flux * throw_;
  });
}

/* ================================================================== */
/*  State                                                             */
/* ================================================================== */

let runIndex = 0;
let frameIndex = 0;
let playing = false;
let solution = null;
let panelTarget = null;
const manual = [null, null, null, null];

/**
 * Which feeder the town is on. The stiff grid is not a re-solve of the weak grid's
 * commands — droop reacts to its own local voltage, so on a stiffer source it issues
 * genuinely different commands. Switching swaps both the source impedance and the
 * recorded episodes, so what you see is what those controllers actually did there.
 */
let gridKind = 'weak';
let cfCache = { key: null, rows: null };
const runSet = () => (gridKind === 'strong' ? WORLD.runsStrong : WORLD.runs);
const candidateSet = () => (gridKind === 'strong' ? WORLD.candidatesStrong : WORLD.candidates);

const run = () => runSet()[runIndex];
const frame = () => run().frames[frameIndex];
const commands = () => frame().kw.map((k, i) => (manual[i] === null ? k : manual[i]));
const insideRoom = () => room.inside(camera.position.x, camera.position.z);

const api = {
  setRun(i) { runIndex = i; syncRunButtons(); },
  setFrame(i) { frameIndex = i; el('scrub').value = String(i); },
  clearManual() { manual.fill(null); },
  // Every stage is set on the weak feeder. The stiff one is a thing you go and look at
  // after the arc, not a difficulty setting you can leave on by accident.
  setGrid(kind) { applyGrid(kind); },
  /**
   * Start a stage at midnight with a fresh fleet. Stages used to open at the evening
   * peak to get to the interesting part quickly, but a run can only be scored if it is
   * played from the beginning — a state of charge is the integral of the whole day —
   * and a stage that cannot be scored never leaves a dot on the map.
   */
  startDay() {
    frameIndex = 0;
    el('scrub').value = '0';
    startRun();
  },
};

function applyGrid(kind) {
  gridKind = kind === 'strong' ? 'strong' : 'weak';
  if (gridKind === 'strong') gridSeen = true;
  setGrid(gridKind);
  cfCache.key = null;
  syncGridButtons();
  renderTotals();
  renderDebrief();
  room.invalidate();
  resolveNow();
  updateHud();
}

const progress = new Progress(api);

let feederTableDue = true;

/* ------------------------------------------------------- load scale */

/**
 * How big the town is, as a multiple of the exported base.
 *
 * Rooftop solar is baked into the exported injection at the PV buses, and a town
 * growing does not put more panels on its roofs — so the generation is lifted out, the
 * load scaled, and the generation put back. Scaling the injection directly would
 * quietly grow the sun along with the demand.
 */
const BASE_SCALE = WORLD.scenario.loadScale;
const PV_BUS = new Set(WORLD.pv);
let loadScale = BASE_SCALE;

const scaledP = new Float64Array(N_BUS + 1);
const scaledQ = new Float64Array(N_BUS + 1);

function dayFrame() {
  const f = WORLD.day[frameIndex];
  if (loadScale === BASE_SCALE) return f;
  const k = loadScale / BASE_SCALE;
  const solarPu = (f.solar ?? 0) / WORLD.kwPerPu;
  for (let b = 0; b <= N_BUS; b++) {
    const pv = PV_BUS.has(b) ? solarPu : 0;
    scaledP[b] = (f.p[b] + pv) * k - pv;
    scaledQ[b] = f.q[b] * k;
  }
  return { p: scaledP, q: scaledQ, clock: f.clock, solar: f.solar };
}

/**
 * Whether changing the load would still be showing the truth.
 *
 * Uncoordinated charging pulls whatever the cars can take regardless of voltage, so
 * its recorded commands are the same commands at any load. Droop and the two agents
 * back off as their local voltage falls, so replaying their recorded commands at a
 * different load shows a controller that would never have issued them. In that case
 * the control is refused rather than quietly lying.
 */
function loadScaleHonest() {
  if (manual.every((m) => m !== null)) return true;
  return runIndex === 0 && manual.every((m) => m === null);
}

/* ------------------------------------------------------------ the map */

const DOT_COLOURS = ['#e3b24f', '#5aa9d6', '#e4776b', '#4fb3a2'];

/**
 * A run counts when the day is played from the beginning to the end. Scrubbing the
 * clock ends it: a fleet's state of charge is the integral of everything that happened
 * before now, and you cannot skip the middle of a day and still score it.
 */
const fleetRun = new FleetRun();
let runLive = false;
const myDots = [];

function referenceDots() {
  return runSet().map((r, i) => ({
    label: r.label,
    violationRate: r.violationRate,
    socMet: r.socMet,
    colour: DOT_COLOURS[i % DOT_COLOURS.length],
    mine: false,
    provenance: r.provenance,
  }));
}

const allDots = () => [...referenceDots(), ...myDots];
const dotsKey = () => `${gridKind}|${myDots.length}`;

function startRun() {
  fleetRun.reset();
  runLive = true;
}

function endRunIfComplete() {
  if (!runLive) return;
  runLive = false;
  const t = fleetRun.totals();
  myDots.push({
    label: `Your run ${myDots.length + 1}` + (loadScale !== BASE_SCALE ? ` (town ×${(loadScale / BASE_SCALE).toFixed(1)})` : ''),
    violationRate: t.violationRate,
    socMet: t.socMet,
    totalLossKwh: t.totalLossKwh,
    vMinPu: t.vMinPu,
    driversMet: t.driversMet,
    colour: '#e8ecf2',
    mine: true,
  });
  room.logEvent('23:55', `run scored — ${t.driversMet} of ${t.fleetSize} served, ${(t.violationRate * 100).toFixed(2)}% bus-steps out of band`, 'good');
  renderDotList();
  renderDebrief();
  redrawInstruments();
}

function resolveNow() {
  const kw = commands();
  solution = solveAt(dayFrame(), kw);
  // The sky is a function of the clock, so it moves on exactly the same beat as the
  // solve. Cheap — a handful of colour lerps — and it keeps the light and the numbers
  // from ever disagreeing about what time it is.
  daylight = sky.apply(frameIndex).daylight;
  city.applyVoltages(kw, manual, daylight);
  redrawInstruments();
  feederTableDue = true;
}

let instrumentsDue = true;
function redrawInstruments() { instrumentsDue = true; }

/**
 * The control room is enclosed, so from anywhere out in the town its screens are not
 * merely small — they are behind a wall. Past this radius the redraw is skipped
 * entirely and the dirty flag left standing, so walking back through the door
 * repaints once rather than the town having paid for a board nobody could see.
 */
const ROOM_VIEW_RANGE = 45;
let wasNearRoom = true;
function nearRoom() {
  const dx = camera.position.x - ROOM.x;
  const dz = camera.position.z - ROOM.z;
  return dx * dx + dz * dz < ROOM_VIEW_RANGE * ROOM_VIEW_RANGE;
}

function flushInstruments() {
  if (!instrumentsDue) return;
  const near = nearRoom();
  if (!near) { wasNearRoom = false; return; }
  if (!wasNearRoom) { room.invalidate(); wasNearRoom = true; }
  instrumentsDue = false;
  const f = frame();
  room.redraw({
    clock: f.clock,
    runLabel: run().label.replace(/ \(.*\)/, ''),
    frames: run().frames,
    frameIndex,
    branchLoss: branchLossKw,
    vMin: solution.vMin,
    vMinBus: solution.vMinBus,
    violations: solution.violations,
    lossKw: solution.lossKw,
    stationKw: commands(),
    plugged: f.plugged,
    manual,
    picked: progress.picked,
    youBus: nearestBus(),
    inside: insideRoom(),
    dots: allDots(),
    dotsKey: dotsKey(),
    sup: supState(),
  });
}

/* ================================================================== */
/*  Interaction targets                                               */
/* ================================================================== */

const TARGETS = [];
for (const p of place.values()) {
  if (p.bus === 1) TARGETS.push({ kind: 'substation', bus: 1, x: SUB.x, z: SUB.z + 14, label: 'Read the substation board' });
  else TARGETS.push({ kind: 'meter', bus: p.bus, x: p.x, z: p.z - ROAD_W / 2 - 0.6, label: `Read the meter at bus ${p.bus}` });
}
WORLD.stations.forEach((bus, si) => {
  const s = { x: place.get(bus).x, z: place.get(bus).z + ROAD_W / 2 + 12 };
  TARGETS.push({ kind: 'station', bus, si, x: s.x - 12.5, z: s.z - 4, label: `Operate the station at bus ${bus}` });
});
room.consoles.forEach((c) => {
  TARGETS.push({ kind: 'console', bus: c.bus, si: c.si, x: room.desk.x - 1.2, z: c.z, label: `Station ${c.si + 1} console — bus ${c.bus}` });
});
TARGETS.push({ kind: 'terminal', x: ROOM.east - 2.6, z: ROOM.z - 6.0, label: 'Read the procurement terminal' });
TARGETS.push({
  kind: 'supervisor', x: room.supervisorSpot.x, z: room.supervisorSpot.z,
  label: 'Supervisory control — run the plant from here',
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
    const reach = it.kind === 'console' || it.kind === 'terminal' || it.kind === 'supervisor' ? 3.4 : 11;
    if (dist > reach) continue;
    const dot = (dx * (fx / fl) + dz * (fz / fl)) / (dist || 1);
    if (dot < 0.55) continue;
    const score = dist * (2 - dot);
    if (score < bestScore) { bestScore = score; best = it; }
  }
  return best;
}

function nearestBus() {
  let best = 1, bestD = Infinity;
  for (const p of place.values()) {
    const d = Math.hypot(p.x - camera.position.x, p.z - camera.position.z);
    if (d < bestD) { bestD = d; best = p.bus; }
  }
  return best;
}

/* ================================================================== */
/*  Panels                                                            */
/* ================================================================== */

/**
 * What this bus would read, this minute, under each of the other controllers.
 *
 * The page holds every controller's recorded commands, so the counterfactual is not a
 * remembered number from an earlier visit — it is solved here, now, on the same day and
 * the same fleet. That is what makes stage 3's comparison an observation rather than a
 * feat of memory.
 *
 * `solveAt` writes into the shared voltage buffer, so the active scenario is re-solved
 * afterwards to put the world back exactly as it was.
 */
function counterfactuals(bus) {
  const key = `${bus}|${frameIndex}|${gridKind}|${loadScale}|${manual.join(',')}`;
  if (cfCache.key === key) return cfCache.rows;
  const rows = runSet().map((r, i) => {
    solveAt(dayFrame(), r.frames[frameIndex].kw);
    return { label: r.label.replace(/ \(.*\)/, ''), v: vMag[bus], standIn: r.provenance === 'placeholder', index: i };
  });
  resolveNow();
  cfCache = { key, rows };
  return rows;
}

function counterfactualHtml(bus) {
  const rows = counterfactuals(bus);
  const mine = manual.some((m) => m !== null);
  const body = rows.map((r) => {
    const live = r.index === runIndex && !mine;
    return `<div class="cfrow${live ? ' live' : ''}">
      <span>${r.label}${r.standIn ? ' <em>*</em>' : ''}</span>
      <span class="${r.v < BAND_LO ? 'warn' : 'ok'}">${r.v.toFixed(4)}</span></div>`;
  }).join('');
  return `<div class="cf"><div class="cfhead">this bus, this minute, under each controller</div>${body}
    ${mine ? '<div class="cfnote">You have a station in manual, so none of these is what you are seeing.</div>' : ''}</div>`;
}

const rowOf = (k, v) => `<div class="row"><span>${k}</span><span>${v}</span></div>`;
const fmtKw = (kw) => (Math.abs(kw) < 1 ? 'idle' : kw < 0 ? Math.abs(kw).toFixed(0) + ' kW drawn' : kw.toFixed(0) + ' kW returned');

function profileSvg(markBus) {
  const w = 300, h = 62, pad = 4;
  const xs = (i) => pad + (i / 32) * (w - pad * 2);
  const ys = (v) => h - pad - ((v - 0.82) / 0.2) * (h - pad * 2);
  let d = '';
  for (let bus = 1; bus <= N_BUS; bus++) d += (bus === 1 ? 'M' : 'L') + xs(bus - 1).toFixed(1) + ' ' + ys(vMag[bus]).toFixed(1);
  const bandY = ys(BAND_LO);
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="Voltage along the feeder">
    <line x1="${pad}" y1="${bandY}" x2="${w - pad}" y2="${bandY}" stroke="#E4776B" stroke-dasharray="3 3"/>
    <path d="${d}" fill="none" stroke="#4FB3A2" stroke-width="1.6"/>
    <circle cx="${xs(markBus - 1).toFixed(1)}" cy="${ys(vMag[markBus]).toFixed(1)}" r="3.6" fill="#E3B24F"/>
    <text x="${w - pad}" y="${bandY - 3}" fill="#E4776B" font-size="8" text-anchor="end">0.95 floor</text>
  </svg>`;
}

function stationPanelHtml(si, bus, kicker, title) {
  const f = frame();
  const value = manual[si] === null ? f.kw[si] : manual[si];
  return `<button class="close" id="panelClose" aria-label="Close">×</button>
    <div class="kicker">${kicker}</div><h3>${title}</h3>
    ${rowOf('plugged in now', f.plugged[si] + ' vehicles')}
    ${rowOf('controller wants', fmtKw(f.kw[si]))}
    ${rowOf('voltage at this bus', vMag[bus].toFixed(4) + ' pu')}
    <label class="slider" for="stationKw">Your setting</label>
    <input id="stationKw" type="range" min="-900" max="400" step="10" value="${value}" />
    <div class="readout" id="stationRead">${fmtKw(value)}</div>
    <button class="act" id="handBack">${manual[si] === null ? 'Take this station off the controller' : 'Give it back to the controller'}</button>
    <div class="profile">${profileSvg(bus)}</div>
    <p class="hint">Drag left to charge harder. Every lamp on the feeder is lit by the answer.</p>`;
}

function wireStationPanel(si) {
  const slider = el('stationKw');
  slider.oninput = () => {
    manual[si] = Number(slider.value);
    resolveNow();
    el('stationRead').textContent = fmtKw(manual[si]);
    updateHud();
  };
  el('handBack').onclick = () => {
    manual[si] = manual[si] === null ? Number(slider.value) : null;
    syncLoadHonesty();
    resolveNow();
    renderPanel();
    updateHud();
  };
}

/**
 * The supervisory panel: every setting the plant has, reachable from inside the room.
 *
 * It is built once and then updated in place. The other panels can afford to rebuild
 * their markup on every HUD tick because their only live control is a slider, which
 * `refreshPanel` exempts — but this one is a wall of buttons, and rebuilding it under a
 * running clock would replace the element between mousedown and mouseup and swallow the
 * click. So: `renderPanel` builds it, `syncSupervisorPanel` keeps it honest.
 */
function supervisorPanelHtml() {
  const seg = (id, items) =>
    `<div class="seg supseg" id="${id}">` + items.map(
      ([label, value, title]) =>
        `<button data-value="${value}"${title ? ` title="${title}"` : ''}>${label}</button>`,
    ).join('') + '</div>';

  return `<button class="close" id="panelClose" aria-label="Close">×</button>
    <div class="kicker">Supervisory control · everything the plant has</div>
    <h3>Run it from in here</h3>

    <label class="slider">Who is driving</label>
    ${seg('supRun', WORLD.runs.map((r, i) => [r.label.replace(/ \(.*\)/, '').replace('IEEE 1547', '1547'), i, r.label]))}

    <label class="slider">The feeder itself</label>
    ${seg('supGrid', [['Weak', 'weak'], ['Stiff', 'strong']])}
    <p class="hint" id="supGridNote"></p>

    <label class="slider">How big the town is</label>
    ${seg('supLoad', LOAD_MULTS.map((m) => [`${m}×`, m]))}
    <p class="hint" id="supLoadNote"></p>

    <label class="slider">The day</label>
    <div class="seg supseg" id="supTransport">
      <button data-value="play" id="supPlay">Play</button>
      <button data-value="reset">Reset to 00:00</button>
    </div>
    ${seg('supSpeed', [['×1', 1], ['×4', 4], ['×16', 16], ['×64', 64]])}
    <input id="supScrub" type="range" min="0" max="${WORLD.day.length - 1}" step="1"
      value="${frameIndex}" aria-label="Time of day" />
    <div class="readout" id="supClock"></div>
    <p class="hint" id="supScoreNote"></p>

    <button class="act" id="supCockpit"></button>`;
}

function wireSupervisorPanel() {
  const pick = (id, fn) => {
    el(id).querySelectorAll('button').forEach((b) => {
      b.onclick = () => fn(b.dataset.value);
    });
  };
  pick('supRun', (v) => setController(Number(v)));
  pick('supGrid', (v) => setFeeder(v));
  pick('supLoad', (v) => setTownSize(Number(v)));
  pick('supSpeed', (v) => setSpeed(Number(v)));
  pick('supTransport', (v) => (v === 'play' ? togglePlay() : resetDay()));
  el('supScrub').oninput = () => scrubTo(Number(el('supScrub').value));
  el('supCockpit').onclick = () => setCockpit(!cockpit);
  syncSupervisorPanel();
}

function syncSupervisorPanel() {
  if (el('panel').hidden || !el('supRun')) return;
  const s = supState();
  const mark = (id, match, disabled = false) => {
    el(id).querySelectorAll('button').forEach((b) => {
      b.setAttribute('aria-pressed', String(match(b.dataset.value)));
      b.disabled = disabled;
    });
  };
  mark('supRun', (v) => Number(v) === s.runIndex);
  mark('supGrid', (v) => v === s.gridKind, !s.gridUnlocked);
  mark('supLoad', (v) => LOAD_MULTS.indexOf(Number(v)) === s.loadIndex, !s.loadUsable);
  mark('supSpeed', (v) => Number(v) === s.speed);

  el('supGridNote').textContent = s.gridUnlocked
    ? 'Same day, same fleet, same controllers — only the substation impedance changes.'
    : 'Unlocks when you finish the six stages.';
  el('supLoadNote').textContent = s.loadUsable
    ? 'Rooftop solar does not grow with the town.'
    : s.gridUnlocked
      ? 'Droop and the agents back off as their own voltage falls, so their recorded commands are not what they would have issued at another load. Take the stations manual, or switch to Uncoordinated.'
      : 'Unlocks when you finish the six stages.';

  el('supPlay').textContent = s.playing ? 'Pause' : 'Play';
  const scrubEl = el('supScrub');
  if (document.activeElement !== scrubEl) scrubEl.value = String(frameIndex);
  el('supClock').textContent = s.clock;
  el('supScoreNote').textContent = s.scoring
    ? 'Scoring — this run will leave a dot on the map.'
    : 'Not scored. Reset and play from 00:00 for a dot on the map.';
  el('supCockpit').textContent = cockpit
    ? 'Show the page controls again'
    : 'Hide the page controls — run it all from in here';
}

function renderPanel() {
  const panel = el('panel');
  const t = panelTarget;
  if (!t) { panel.hidden = true; return; }
  panel.hidden = false;

  if (t.kind === 'substation') {
    panel.innerHTML = `<button class="close" id="panelClose" aria-label="Close">×</button>
      <div class="kicker">Bus 1 · where the town meets the grid</div><h3>Substation</h3>
      ${rowOf('grid behind the transformer', vMag[0].toFixed(4) + ' pu — assumed')}
      ${rowOf('this busbar right now', vMag[1].toFixed(4) + ' pu')}
      ${rowOf('already lost, here', ((vMag[0] - vMag[1]) * 100).toFixed(1) + ' % of nominal')}
      <p>Only the first of those is an assumption. The busbar is already below the grid before the
      town begins — because this feeder is <em>weak</em>: there is real impedance between here and
      the grid, so even the substation moves when the town pulls.</p>
      <div class="profile">${profileSvg(1)}</div>`;
  } else if (t.kind === 'meter') {
    const p = place.get(t.bus);
    const v = vMag[t.bus];
    panel.innerHTML = `<button class="close" id="panelClose" aria-label="Close">×</button>
      <div class="kicker">Bus ${t.bus} · ${p.row === 0 ? 'main road' : 'lateral ' + Math.abs(p.row)}</div>
      <h3>Street meter</h3>
      ${rowOf('voltage now', v.toFixed(4) + ' pu')}
      ${rowOf('status', v < BAND_LO ? '<span class="warn">below the 0.95 floor</span>' : '<span class="ok">inside the band</span>')}
      ${rowOf('load here', p.kw + ' kW / ' + p.kvar + ' kVAr')}
      ${rowOf('hops from the substation', p.col)}
      <div class="profile">${profileSvg(t.bus)}</div>
      <p class="hint">The whole feeder, left to right by bus number. You are the amber dot.</p>
      ${counterfactualHtml(t.bus)}`;
    progress.observeMeter(t.bus, { runIndex, frameIndex, solution });
  } else if (t.kind === 'station') {
    panel.innerHTML = stationPanelHtml(t.si, t.bus, `Bus ${t.bus} · charging station`, 'Station console');
    wireStationPanel(t.si);
    progress.observeConsole(t.si);
  } else if (t.kind === 'console') {
    panel.innerHTML = stationPanelHtml(t.si, t.bus, `Desk position ${t.si + 1} · bus ${t.bus}`, 'Dispatch console');
    wireStationPanel(t.si);
    progress.observeConsole(t.si);
  } else if (t.kind === 'supervisor') {
    panel.innerHTML = supervisorPanelHtml();
    wireSupervisorPanel();
  } else if (t.kind === 'terminal') {
    progress.observeTerminal();
    const rows = candidateSet().map((c, i) => `
      <button class="cand${progress.picked === i ? ' picked' : ''}" data-pick="${i}">
        <span class="cname">${c.label}${c.provenance === 'placeholder' ? ' <em>*</em>' : ''}</span>
        <span class="cnum">${c.violationRate.toFixed(3)}</span>
        <span class="cnum">$${c.netCostUsd}</span>
      </button>`).join('');
    panel.innerHTML = `<button class="close" id="panelClose" aria-label="Close">×</button>
      <div class="kicker">Procurement · four candidates</div><h3>Same feeder, same day, same fleet</h3>
      <div class="candhead"><span>Controller</span><span>Violations</span><span>Net cost</span></div>
      ${rows}
      <p class="hint">* labelled stand-in, not the trained agent — its recorded episodes are still
      to be exported from the thesis notebook.</p>`;
    panel.querySelectorAll('[data-pick]').forEach((b) => {
      b.onclick = () => {
        progress.picked = Number(b.dataset.pick);
        room.logEvent(frame().clock, `deployed ${candidateSet()[progress.picked].label}`, 'info');
        redrawInstruments();
        renderPanel();
        checkObjectives();
      };
    });
  }
  const close = el('panelClose');
  if (close) close.onclick = closePanel;
  checkObjectives();
}

function openPanel(t) {
  panelTarget = t;
  controls.unlock();
  // Hide the "click to enter" overlay here rather than leaving it to the pointer-lock
  // event. Someone driving by keyboard — canvas focused, never locked — never fires an
  // unlock, so the overlay stayed up across the whole panel and swallowed every click
  // on it. The panel opened, looked right, and could not be used.
  el('enter').hidden = true;
  renderPanel();
  // Pointer lock has just been released, so focus is nowhere useful. Put it on the
  // first thing in the panel; Escape closes and hands it back to the view.
  const first = el('panel').querySelector('input, button:not(.close), .close');
  if (first) first.focus();
}

function closePanel() {
  const wasOpen = panelTarget !== null;
  panelTarget = null;
  el('panel').hidden = true;
  el('enter').hidden = controls.isLocked || !el('card').hidden;
  if (wasOpen) canvas.focus();
}

/* ================================================================== */
/*  Mission UI                                                        */
/* ================================================================== */

function liveState() {
  return { runIndex, frameIndex, manual, solution, inside: insideRoom(), picked: progress.picked };
}

function renderObjectives() {
  const list = progress.status(liveState());
  const st = progress.stage;
  el('stageTag').textContent = `Stage ${st.n} of ${STAGES.length} · ${st.eyebrow}`;
  el('stageTitle').textContent = st.title;
  el('objList').innerHTML = list.map((o) =>
    `<li class="${o.done ? 'done' : ''}"><span class="tick">${o.done ? '✓' : '○'}</span>
     <span>${o.text}${o.progress && !o.done ? ` <em>(${o.progress})</em>` : ''}</span></li>`).join('');
}

let cardMode = null;
function showCard(mode) {
  cardMode = mode;
  const st = progress.stage;
  const body = mode === 'brief' ? st.brief : st.debrief(progress.snapshot(liveState()));
  el('cardTag').textContent = `Stage ${st.n} of ${STAGES.length} · ${st.eyebrow}`;
  el('cardTitle').textContent = mode === 'brief' ? st.title : 'What that showed';
  el('cardBody').innerHTML = body.map((p) => `<p>${p}</p>`).join('');
  const isLast = progress.stageIndex === STAGES.length - 1;
  el('cardGo').textContent = mode === 'brief'
    ? (st.n === 1 ? 'Take the desk' : 'Begin')
    : (isLast ? 'Finish' : 'Next stage');
  el('card').hidden = false;
  controls.unlock();
}

function dismissCard() {
  el('card').hidden = true;
  if (cardMode === 'brief') {
    progress.phase = 'running';
    playing = true;
    el('play').textContent = 'Pause';
  } else if (progress.next()) {
    showCard('brief');
  } else {
    el('card').hidden = true;
    unlockGrid();
    el('objList').innerHTML =
      '<li class="done"><span class="tick">✓</span><span>All six stages complete.</span></li>' +
      '<li><span class="tick">→</span><span>The <b>feeder switch</b> is now unlocked. Rebuild the town on a stiff source and walk it again.</span></li>';
    el('stageTag').textContent = 'Free play';
    el('stageTitle').textContent = 'What the network itself is worth';
    return;
  }
  renderObjectives();
  renderDebrief();
  resolveNow();
  updateHud();
}

let lastComplete = false;
function checkObjectives() {
  if (progress.phase !== 'running') return;
  renderObjectives();
  const done = progress.complete(liveState());
  if (done && !lastComplete) {
    lastComplete = true;
    playing = false;
    el('play').textContent = 'Play';
    room.logEvent(frame().clock, `stage ${progress.stage.n} objectives met`, 'good');
    progress.phase = 'debrief';
    showCard('debrief');
  }
  if (!done) lastComplete = false;
}

/* ================================================================== */
/*  HUD                                                               */
/* ================================================================== */

function setMetric(node, label, value, tone) {
  node.className = 'metric' + (tone ? ' ' + tone : '');
  node.innerHTML = label + ' <b>' + value + '</b>';
}

/**
 * Spoken position. Announced on arrival at a new bus or on crossing the band, never
 * per frame — a live region that fires continuously is noise, not information.
 */
let spoken = '';
function announce(text) {
  if (text === spoken) return;
  spoken = text;
  el('announce').textContent = text;
}

/**
 * The debrief: what the entry claims to teach, and what your runs showed. Written into
 * the page rather than a modal so it can be read, scrolled and screen-read after the
 * arc is over, which is what the website does with it.
 */
let gridSeen = false;
function renderDebrief() {
  const stagesDone = progress.phase === 'finished' ? 6 : progress.stage.n - 1;
  el('objBody').innerHTML = coverage(stagesDone).map((o) =>
    `<tr data-covered="${o.covered}">
      <td class="k">${o.id}</td><td>${o.text}</td>
      <td class="s">${o.stage}</td>
      <td class="s">${o.covered ? 'reached' : 'not yet'}</td></tr>`).join('');

  el('findings').innerHTML = findings({ myDots, picked: progress.picked, gridSeen })
    .map((f) => `<div class="finding"><h3>${f.headline}</h3><p>${f.body}</p></div>`).join('');
}

/** The map, as a table. Same dots, readable without walking to the wall. */
function renderDotList() {
  const rows = allDots().map((d) => {
    const stand = d.provenance === 'placeholder' ? ' <em>*</em>' : '';
    return `<tr${d.mine ? ' class="mine"' : ''}>
      <td><span class="swatch" style="background:${d.colour}"></span>${d.label}${stand}</td>
      <td class="num">${d.violationRate.toFixed(4)}</td>
      <td class="num">${Math.round(d.socMet * 287)} of 287</td>
      <td class="num">${d.totalLossKwh ? d.totalLossKwh.toFixed(0) + ' kWh' : '—'}</td></tr>`;
  }).join('');
  el('dotBody').innerHTML = rows;
  el('runState').textContent = runLive
    ? 'Run in progress — play it to midnight to score it.'
    : myDots.length
      ? `${myDots.length} of your own run${myDots.length === 1 ? '' : 's'} scored.`
      : 'Press Play from the start of the day to score a run of your own.';
}

/** The mimic board as a table, for reading rather than walking. */
const feederRows = [...place.values()].map((p) => {
  const tr = document.createElement('tr');
  tr.innerHTML = `<th scope="row">${p.bus}</th><td class="v"></td><td class="s"></td>` +
    `<td class="v">${p.col}</td><td class="v">${p.kw} kW</td>`;
  el('feederBody').appendChild(tr);
  return { bus: p.bus, tr, v: tr.children[1], s: tr.children[2], last: null };
});

function updateFeederTable() {
  for (const row of feederRows) {
    const v = vMag[row.bus];
    const shown = v.toFixed(4);
    if (shown === row.last) continue;
    row.last = shown;
    row.v.textContent = shown + ' pu';
    const out = v < BAND_LO || v > BAND_HI;
    row.s.textContent = out ? 'outside the band' : 'inside the band';
    row.tr.dataset.band = out ? 'out' : 'in';
  }
}

function updateHud() {
  const inside = insideRoom();
  const bus = nearestBus();
  const v = vMag[bus];
  const p = place.get(bus);

  el('where').innerHTML = inside ? 'in the <em>control room</em>'
    : bus === 1 ? 'at the <em>substation</em>'
    : `at <em>bus</em> ${bus}` + (STATION_SET.has(bus) ? ' <em>· charging station</em>' : '');
  const here = el('here');
  here.textContent = inside ? solution.vMin.toFixed(3) + ' pu' : v.toFixed(3) + ' pu';
  here.className = 'here ' + ((inside ? solution.vMin : v) < BAND_LO ? 'bad' : 'good');
  el('walked').textContent = inside
    ? `worst bus on the feeder · bus ${solution.vMinBus}`
    : `${Math.round(Math.hypot(camera.position.x, camera.position.z))} m from the substation · ${p.col} hops`;

  const f = frame();
  setMetric(el('mClock'), 'time', f.clock);
  setMetric(el('mRun'), 'driving', run().label.replace(/ \(.*\)/, ''));
  const chip = el('runChip');
  const anyManual = manual.some((m) => m !== null);
  const standIn = run().provenance === 'placeholder';
  chip.textContent = anyManual ? 'you have taken over' : standIn ? 'labelled stand-in' : 'real controller';
  chip.className = 'chip ' + (anyManual ? 'mine' : standIn ? 'stand-in' : 'real');
  setMetric(el('mViol'), 'out of band', solution.violations + (solution.violations === 1 ? ' bus' : ' buses'), solution.violations > 0 ? 'bad' : 'good');
  setMetric(el('mLoss'), 'burnt in lines', solution.lossKw.toFixed(0) + ' kW');
  const pending = room.alarmsPending();
  const alarmEl = el('mAlarm');
  alarmEl.hidden = pending === 0;
  if (pending) setMetric(alarmEl, 'alarms', pending + ' unacknowledged · F', 'bad');

  announce(inside
    ? `In the control room. Worst bus on the feeder is ${solution.vMinBus} at ${solution.vMin.toFixed(3)} per unit, ${solution.violations} outside the band.`
    : `At bus ${bus}, ${v.toFixed(3)} per unit, ${v < BAND_LO ? 'below the floor' : 'inside the band'}. ${p.col} hops from the substation.`);

  if (panelTarget) refreshPanel();
}

/**
 * Keep an open panel current as the day advances, without yanking the keyboard out of
 * the visitor's hands. Rebuilding innerHTML destroys focus and interrupts a drag, so a
 * panel whose controls are in use is left alone until they are not.
 */
function refreshPanel() {
  const panel = el('panel');
  // The supervisory panel updates in place rather than being rebuilt — see above.
  if (panelTarget?.kind === 'supervisor') { syncSupervisorPanel(); return; }
  const active = document.activeElement;
  if (panel.contains(active) && active.tagName === 'INPUT') return;
  const activeId = panel.contains(active) ? active.id : null;
  renderPanel();
  if (activeId) {
    const again = panel.querySelector('#' + CSS.escape(activeId));
    if (again) again.focus();
  }
}

/* ================================================================== */
/*  Input                                                             */
/* ================================================================== */

const controls = new PointerLockControls(camera, renderer.domElement);
const held = new Set();

renderer.domElement.addEventListener('click', () => {
  if (!panelTarget && el('card').hidden) controls.lock();
});
el('enter').addEventListener('click', () => controls.lock());
controls.addEventListener('lock', () => { el('enter').hidden = true; });
controls.addEventListener('unlock', () => {
  el('enter').hidden = !!panelTarget || !el('card').hidden;
  held.clear();
});

/**
 * The city has to be playable without a mouse.
 *
 * Pointer lock is the nicer way to look around and it stays the default, but it is
 * also a hard requirement for a device nobody has. So the canvas is focusable, and
 * while it holds focus the arrow keys turn, WASD walks, and E and F do what they do
 * under lock. Anyone who cannot use pointer lock can still reach every objective.
 */
const driving = () => controls.isLocked || document.activeElement === canvas;
const TURN = 2.2;    // radians per second
const PITCH_LIMIT = 1.2;
const turn = new Set();
const TURN_KEYS = { arrowleft: 'l', arrowright: 'r', arrowup: 'u', arrowdown: 'd' };

function applyTurn(dt) {
  if (!turn.size) return;
  const e = camera.rotation;
  if (turn.has('l')) e.y += TURN * dt;
  if (turn.has('r')) e.y -= TURN * dt;
  if (turn.has('u')) e.x = Math.min(PITCH_LIMIT, e.x + TURN * dt);
  if (turn.has('d')) e.x = Math.max(-PITCH_LIMIT, e.x - TURN * dt);
}

addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (TURN_KEYS[k] && driving()) { turn.add(TURN_KEYS[k]); e.preventDefault(); }
  if (['w', 'a', 's', 'd', 'shift'].includes(k)) { held.add(k); if (driving()) e.preventDefault(); }
  if (k === 'e' && driving()) { const t = focused(); if (t) { openPanel(t); e.preventDefault(); } }
  if (k === 'f') {
    const n = room.ackAlarms();
    if (n) {
      progress.observeAck(n);
      room.logEvent(frame().clock, `${n} alarm${n === 1 ? '' : 's'} acknowledged`, 'info');
      updateHud();
      checkObjectives();
    }
  }
  if (k === 'escape' && panelTarget) closePanel();

  // Plant hotkeys. Every one of these is a control the supervisory console also carries;
  // they exist so a demonstrator never has to reach back out to the page to change gear
  // mid-walk. Suppressed while a panel is open, where the same keys belong to its fields.
  if (panelTarget || !driving()) return;
  if (k >= '1' && k <= String(WORLD.runs.length)) { setController(Number(k) - 1); e.preventDefault(); }
  else if (k === ' ') { togglePlay(); e.preventDefault(); }
  else if (k === 'r') { resetDay(); e.preventDefault(); }
  else if (k === 'g') { setFeeder(gridKind === 'weak' ? 'strong' : 'weak'); e.preventDefault(); }
  else if (k === '[' || k === ']') {
    const speeds = [1, 4, 16, 64];
    const at = speeds.indexOf(stepsPerTick);
    setSpeed(speeds[Math.max(0, Math.min(speeds.length - 1, at + (k === ']' ? 1 : -1)))]);
    e.preventDefault();
  } else if (k === ',' || k === '.') {
    scrubTo(frameIndex + (k === '.' ? 6 : -6));
    e.preventDefault();
  } else if (k === 't') { setCockpit(!cockpit); e.preventDefault(); }
});
addEventListener('keyup', (e) => {
  const k = e.key.toLowerCase();
  held.delete(k);
  if (TURN_KEYS[k]) turn.delete(TURN_KEYS[k]);
});

function collide(nx, nz) {
  const R = 0.9;
  let x = nx, z = nz;
  for (const s of solids) {
    const minX = s.x - s.w / 2 - R, maxX2 = s.x + s.w / 2 + R;
    const minZ = s.z - s.d / 2 - R, maxZ = s.z + s.d / 2 + R;
    if (x > minX && x < maxX2 && z > minZ && z < maxZ) {
      const dl = x - minX, dr = maxX2 - x, du = z - minZ, dd = maxZ - z;
      const m = Math.min(dl, dr, du, dd);
      if (m === dl) x = minX; else if (m === dr) x = maxX2;
      else if (m === du) z = minZ; else z = maxZ;
    }
  }
  return { x, z };
}

const dirF = new THREE.Vector3();
const dirR = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);

function move(dt) {
  if (!driving()) return;
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
  const out = collide(
    camera.position.x + (dirF.x * f + dirR.x * s) * speed,
    camera.position.z + (dirF.z * f + dirR.z * s) * speed,
  );
  camera.position.x = Math.max(-120, Math.min(maxX + 90, out.x));
  camera.position.z = Math.max(-130, Math.min(170, out.z));
  camera.position.y = EYE;
}

/* ================================================================== */
/*  Page chrome                                                       */
/* ================================================================== */

/**
 * Every setting the plant has, as one function each.
 *
 * These exist because the same decision can now be taken from two places — the page
 * toolbar and the supervisory console inside the room — and a setting that is applied
 * two different ways is a setting that will eventually be applied two different ways.
 * The buttons in both places are views onto these; none of them carries logic of its
 * own beyond deciding whether it is allowed to call.
 */
const LOAD_MULTS = [0.5, 1, 1.4, 1.8];

/**
 * Cockpit mode hides the page's own toolbar, leaving the world as the only interface.
 * The toolbar is not deleted — an operator who wants both can have both, and a visitor
 * who has not found the supervisory console yet must not be stranded — but a
 * demonstration reads very differently when the only way to change the plant is to
 * walk to the desk that changes it.
 */
let cockpit = false;
function setCockpit(on) {
  cockpit = on;
  document.body.classList.toggle('cockpit', cockpit);
  syncSupervisor();
}

function setController(i) {
  if (i === runIndex) return;
  runIndex = i;
  syncRunButtons();
  room.logEvent(frame().clock, `feeder switched to ${WORLD.runs[i].label.replace(/ \(.*\)/, '')}`, 'info');
  syncLoadHonesty();
  resolveNow(); updateHud(); checkObjectives(); syncSupervisor();
}

function setFeeder(kind) {
  if (!gridUnlocked || kind === gridKind) return;
  applyGrid(kind);
  room.logEvent(frame().clock, `feeder rebuilt as the ${kind === 'strong' ? 'stiff' : 'weak'} grid`, 'info');
  checkObjectives(); syncSupervisor();
}

function setTownSize(mult) {
  if (!gridUnlocked || !loadScaleHonest()) return;
  loadScale = BASE_SCALE * mult;
  cfCache.key = null;
  syncLoadButtons();
  resolveNow();
  updateHud();
  syncSupervisor();
}

function setSpeed(n) {
  stepsPerTick = n;
  syncSpeedButtons();
  syncSupervisor();
}

function togglePlay() {
  if (!playing && frameIndex >= WORLD.day.length - 1) {
    frameIndex = 0;
    el('scrub').value = '0';
    resolveNow();
    updateHud();
  }
  playing = !playing;
  // Playing from the top starts a scoreable run; resuming from the middle does not.
  if (playing && frameIndex === 0) startRun();
  el('play').textContent = playing ? 'Pause' : 'Play';
  renderDotList();
  syncSupervisor();
}

function resetDay() {
  playing = false;
  frameIndex = 0;
  el('scrub').value = '0';
  el('play').textContent = 'Play';
  runLive = false;
  resolveNow();
  updateHud();
  renderDotList();
  syncSupervisor();
}

function scrubTo(i) {
  frameIndex = Math.max(0, Math.min(WORLD.day.length - 1, i));
  playing = false;
  el('scrub').value = String(frameIndex);
  el('play').textContent = 'Play';
  // A state of charge is the integral of everything before now. You cannot skip the
  // middle of a day and still score it, so scrubbing ends the run rather than
  // producing a dot that quietly leaves a few hours out.
  if (runLive) { runLive = false; room.logEvent(frame().clock, 'clock moved by hand — run not scored', 'info'); }
  resolveNow(); updateHud(); renderDotList(); syncSupervisor();
}

/** What the supervisory console's face is showing. Flat, so the redraw gate can key off it. */
function supState() {
  return {
    runLabels: WORLD.runs.map((r) => r.label.replace(/ \(.*\)/, '').replace('IEEE 1547', '1547')),
    runIndex,
    gridKind,
    gridUnlocked,
    loadIndex: LOAD_MULTS.indexOf(Number((loadScale / BASE_SCALE).toFixed(4))),
    loadUsable: gridUnlocked && loadScaleHonest(),
    clock: frame().clock,
    playing,
    speed: stepsPerTick,
    scoring: runLive,
    open: panelTarget?.kind === 'supervisor',
  };
}

/** Repaint the console face, and the walk-up panel if somebody is standing at it. */
function syncSupervisor() {
  redrawInstruments();
  if (panelTarget?.kind === 'supervisor') syncSupervisorPanel();
}

const runSeg = el('runSeg');
WORLD.runs.forEach((r, i) => {
  const b = document.createElement('button');
  b.textContent = r.label.replace(/ \(.*\)/, '').replace('IEEE 1547', '1547');
  b.title = r.label;
  b.onclick = () => setController(i);
  runSeg.appendChild(b);
});
function syncRunButtons() {
  [...runSeg.children].forEach((c, j) => c.setAttribute('aria-pressed', String(j === runIndex)));
}

/**
 * The feeder switch. Locked until the arc is finished, because a learner who stiffens
 * the source during stage 2 is not being shown the problem the other five stages are
 * about — they have quietly removed it.
 */
let gridUnlocked = false;
const gridSeg = el('gridSeg');
[['Weak feeder', 'weak'], ['Stiff feeder', 'strong']].forEach(([label, kind]) => {
  const b = document.createElement('button');
  b.textContent = label;
  b.dataset.grid = kind;
  b.onclick = () => setFeeder(kind);
  gridSeg.appendChild(b);
});

/**
 * Disabling the control is not enough. A learner who grows the town to 1.8× and then
 * switches to droop would be left looking at droop's recorded commands under a load
 * they were never issued for, with the buttons merely greyed out. So the town returns
 * to its base size whenever scaling stops being truthful.
 */
function syncLoadHonesty() {
  if (!loadScaleHonest() && loadScale !== BASE_SCALE) {
    loadScale = BASE_SCALE;
    cfCache.key = null;
    room.logEvent(frame().clock, 'town size returned to base — this controller reacts to voltage', 'info');
    resolveNow();
    updateHud();
  }
  syncLoadButtons();
}

function syncGridButtons() {
  [...gridSeg.children].forEach((c) => {
    c.setAttribute('aria-pressed', String(c.dataset.grid === gridKind));
    c.disabled = !gridUnlocked;
    c.title = gridUnlocked
      ? 'Same day, same fleet, same controllers — only the substation impedance changes'
      : 'Unlocks when you finish the six stages';
  });
  el('gridNote').hidden = !gridUnlocked;
}

function unlockGrid() {
  if (gridUnlocked) return;
  gridUnlocked = true;
  syncGridButtons();
  syncLoadButtons();
  syncSupervisor();
}

const goSeg = el('goSeg');
[['Control room', room.spawn.x, room.spawn.z, room.spawn.yaw],
 // Yaw here is an offset from facing east, which is the convention the handler below
 // applies to every entry except the control room. Zero puts the console dead ahead.
 ['Supervisory desk', room.supervisorSpot.x - 1.2, room.supervisorSpot.z, 0],
 ['Substation gate', -20, -12, -0.5],
 ['Bus 9, midway', place.get(9).x - 34, 2, 0],
 ['Bus 18, the far end', place.get(18).x - 40, 2, 0],
 ['The long lateral', place.get(30).x - 34, place.get(30).z + 2, 0]].forEach(([label, x, z, yaw]) => {
  const b = document.createElement('button');
  b.textContent = label;
  b.onclick = () => {
    camera.position.set(x, EYE, z);
    camera.rotation.set(0, label === 'Control room' ? yaw : -yaw - Math.PI / 2, 0, 'YXZ');
    closePanel(); updateHud();
  };
  goSeg.appendChild(b);
});

const scrub = el('scrub');
scrub.max = String(WORLD.day.length - 1);
scrub.oninput = () => scrubTo(Number(scrub.value));
el('play').onclick = togglePlay;

const speedSeg = el('speedSeg');
[['×1', 1], ['×4', 4], ['×16', 16], ['×64', 64]].forEach(([label, n]) => {
  const b = document.createElement('button');
  b.textContent = label;
  b.dataset.speed = String(n);
  b.title = `${(WORLD.day.length * 110 / n / 1000).toFixed(0)} seconds a day`;
  b.onclick = () => setSpeed(n);
  speedSeg.appendChild(b);
});
function syncSpeedButtons() {
  [...speedSeg.children].forEach((c) => c.setAttribute('aria-pressed', String(Number(c.dataset.speed) === stepsPerTick)));
}

const loadSeg = el('loadSeg');
LOAD_MULTS.forEach((mult) => {
  const b = document.createElement('button');
  b.textContent = `${mult}×`;
  b.dataset.load = String(BASE_SCALE * mult);
  b.onclick = () => setTownSize(mult);
  loadSeg.appendChild(b);
});

function syncLoadButtons() {
  const honest = loadScaleHonest();
  const usable = gridUnlocked && honest;
  [...loadSeg.children].forEach((c) => {
    c.setAttribute('aria-pressed', String(Number(c.dataset.load) === loadScale));
    c.disabled = !usable;
  });
  const note = el('loadNote');
  note.hidden = !gridUnlocked;
  note.textContent = honest
    ? 'How big the town is. Rooftop solar does not grow with it.'
    : 'Droop and the agents back off as their own voltage falls, so their recorded commands are not what they would have issued at another load. Take the stations manual, or switch to Uncoordinated, to change this.';
  note.className = honest ? '' : 'warnNote';
}
el('cardGo').onclick = dismissCard;

el('fleetVerdict').textContent = fleetCheck.ok
  ? `${fleetCheck.n} recorded runs replayed through the fleet, worst drivers-served disagreement ${fleetCheck.worstSoc.toExponential(1)}, worst violation-rate disagreement ${fleetCheck.worstViol.toExponential(1)}.`
  : `MISMATCH — service off by ${fleetCheck.worstSoc.toExponential(2)}. Do not trust the map.`;

el('verdict').textContent = check.ok
  ? `${check.n} recorded control steps re-solved in the browser, worst voltage disagreement ${check.worstV.toExponential(1)} pu, violation counts identical.`
  : `MISMATCH — ${check.worstV.toExponential(2)} pu. Do not trust these numbers.`;

const totals = el('totals');
function renderTotals() {
  totals.innerHTML = candidateSet().map((r) =>
    `<tr><td>${r.label}</td><td class="num">${r.violationRate.toFixed(3)}</td>` +
    `<td class="num">${Math.round(r.socMet * 287)} of 287</td>` +
    `<td class="num">${r.totalLossKwh.toFixed(0)} kWh</td>` +
    `<td class="num">$${r.netCostUsd}</td>` +
    `<td>${r.provenance === 'placeholder' ? 'labelled stand-in' : 'production controller'}</td></tr>`).join('');
  el('totalsGrid').textContent = gridKind === 'strong' ? 'the stiff feeder' : 'the weak feeder';
}

/* ================================================================== */
/*  Quality ladder                                                    */
/* ================================================================== */

const TIER_NAMES = ['reduced resolution', 'no bloom', 'no shadows', 'full quality'];
let tier = 3;
let autoQuality = true;

function setTier(next) {
  next = Math.max(0, Math.min(3, next));
  if (next === tier) return;
  tier = next;
  renderer.shadowMap.enabled = tier >= 3;
  const wantBloom = tier >= 2;
  const hasBloom = composer.passes.includes(bloom);
  if (wantBloom && !hasBloom) composer.insertPass(bloom, 1);
  if (!wantBloom && hasBloom) composer.removePass(bloom);
  renderScale = tier >= 1 ? 1 : 0.6;
  scene.traverse((o) => { if (o.material) o.material.needsUpdate = true; });
  resize();
}

/* ================================================================== */
/*  Loop                                                              */
/* ================================================================== */

let lastT = 0, lastTick = 0, frames = 0, fpsT = 0, slowSeconds = 0, flashT = 0;

/**
 * How fast the day runs, in five-minute steps per tick.
 *
 * The fleet sees every step at every speed — only the render and the instruments skip
 * the intermediate ones — so a run scored at ×64 is scored identically to one at ×1.
 * The default is one step a tick, which puts a whole day at about half a minute: long
 * enough to walk out to the far end of the feeder while it happens.
 */
let stepsPerTick = 1;
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

function loop(t) {
  requestAnimationFrame(loop);
  const dt = Math.min(0.05, (t - lastT) / 1000);
  lastT = t;

  if (playing && t - lastTick > 110) {
    lastTick = t;
    // The day ends rather than wrapping. A stage that asks you to run through the
    // evening peak has to mean something, and a clock that silently rolls over
    // midnight would satisfy it by doing nothing.
    if (frameIndex >= WORLD.day.length - 1) {
      playing = false;
      el('play').textContent = 'Replay the day';
      room.logEvent('23:55', 'day complete', 'info');
    } else {
      // Two five-minute steps per tick. The export is now every step so a run can be
      // scored the way the engine scores one, but a 288-step day at one step per tick
      // would take twice as long to watch. The fleet still sees every step; only the
      // instruments and the render skip the intermediate one.
      for (let s = 0; s < stepsPerTick && frameIndex < WORLD.day.length - 1; s++) {
        frameIndex++;
        // The fleet plugs in and unplugs before the step is dispatched, exactly as the
        // engine orders it: connections, then solve, then move the energy.
        if (runLive) fleetRun.updateConnections(frameIndex);
        resolveNow();
        if (runLive) {
          fleetRun.record(solution);
          const kw = commands();
          for (let k = 0; k < 4; k++) fleetRun.dispatchStation(k, kw[k]);
        }
      }
      scrub.value = String(frameIndex);
      if (runLive && frameIndex >= WORLD.day.length - 1) endRunIfComplete();

      const raised = room.updateAlarms({
        violations: solution.violations,
        lossKw: solution.lossKw,
        anyManual: manual.some((m) => m !== null),
        standIn: run().provenance === 'placeholder',
        solar: WORLD.day[frameIndex].solar ?? 0,
      });
      if (raised) room.logEvent(frame().clock, raised.text.replace('\n', ' ').toLowerCase(), 'alarm');

      progress.observeStep({ frameIndex, solution, inside: insideRoom() });
      updateHud();
      checkObjectives();
    }
  }

  applyTurn(dt);
  move(dt);
  assignPool();
  city.updateVehicles(dt, { plugged: frame().plugged, stationKw: commands(), running: playing });

  // Annunciator flash, held well under the WCAG 2.3.1 three-per-second threshold,
  // suppressed entirely for anyone who has asked for reduced motion, and not repainted
  // at all from out in the town where the panel is behind a wall.
  if (!reduceMotion && nearRoom() && t - flashT > 700) {
    flashT = t;
    room.setFlash(!(Math.floor(t / 700) % 2));
  }

  const target = driving() ? focused() : null;
  const prompt = el('prompt');
  el('reticle').className = 'reticle' + (target ? ' hot' : '');
  if (target && !panelTarget) { prompt.hidden = false; prompt.innerHTML = '<kbd>E</kbd>' + target.label; }
  else prompt.hidden = true;

  if (driving()) updateHud();
  flushInstruments();
  // The text readout is the non-visual equivalent of the mimic board, so it updates
  // whenever the solution moves — but from the solution, not from the frame clock, so
  // dragging a station slider shows up in it too.
  if (feederTableDue) { feederTableDue = false; updateFeederTable(); }
  composer.render();

  frames++;
  if (t - fpsT > 1000) {
    const fps = frames;
    el('fps').textContent = fps + ' fps · ' + TIER_NAMES[tier];
    frames = 0; fpsT = t;
    // Two slow seconds in a row drops a tier. It never climbs back on its own: a
    // display that oscillates between quality levels is worse than a lower one.
    if (autoQuality && t > 4000 && fps < 24) { if (++slowSeconds >= 2) { setTier(tier - 1); slowSeconds = 0; } }
    else slowSeconds = 0;
  }
}

/* ------------------------------------------------------------- start */

resize();
addEventListener('resize', resize);

camera.position.set(room.spawn.x, EYE, room.spawn.z);
camera.rotation.set(0, room.spawn.yaw, 0, 'YXZ');

progress.beginStage();
syncRunButtons();
syncGridButtons();
syncSpeedButtons();
syncLoadButtons();
renderTotals();
renderDotList();
renderDebrief();
resolveNow();
room.logEvent('00:00', 'control room staffed · day begins', 'info');
updateHud();
renderObjectives();
showCard('brief');
requestAnimationFrame(loop);

window.__city = {
  camera, controls, focused, openPanel, closePanel, check, progress, room, city,
  updateHud, resolveNow,
  solution: () => solution,
  // These are the real controls, not copies of them — a hook that reimplements what a
  // button does lets a test pass a state the interface could not have reached.
  setRun: setController,
  setFrame: (i) => { frameIndex = i; resolveNow(); updateHud(); checkObjectives(); },
  targets: TARGETS,
  setTownSize,
  togglePlay,
  resetDay,
  scrubTo,
  setCockpit,
  cockpit: () => cockpit,
  sup: supState,
  sky: () => ({
    daylight,
    elev: sky.apply(frameIndex).elev,
    sunIntensity: sky.sun.intensity,
    hemiIntensity: sky.hemi.intensity,
    background: scene.background.getHexString(),
    fogDensity: scene.fog.density,
    solarHours: sky.solarHours,
  }),
  ackAlarms: () => {
    const n = room.ackAlarms();
    if (n) { progress.observeAck(n); updateHud(); checkObjectives(); }
    return n;
  },
  setFeeder: applyGrid,
  gridUnlocked: () => gridUnlocked,
  unlockSandbox: () => unlockGrid(),
  myDots: () => myDots,
  refDots: referenceDots,
  fleetCheck,
  setSpeed,
  pause: () => { playing = false; el('play').textContent = 'Play'; },
  dismissCard,
  state: () => ({ runIndex, frameIndex, manual: [...manual], inside: insideRoom(), picked: progress.picked }),
  objectives: () => progress.status(liveState()),
  lockQuality() { autoQuality = false; setTier(3); },
  setPoolSize(n) { poolLimit = n; },
};
