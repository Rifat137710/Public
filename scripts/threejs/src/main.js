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
  WORLD, N_BUS, BAND_LO, EYE, ROOM, SUB, ROAD_W, place, solids, maxX, check,
  solveAt, vMag, branchLossKw, STATION_SET, PALETTE,
} from './core.js';
import { buildCity } from './city.js';
import { buildRoom } from './room.js';
import { STAGES, Progress } from './mission.js';

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

scene.add(new THREE.HemisphereLight(0x33455c, 0x0b1016, 1.7));

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

function assignPool() {
  const near = city.lamps
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
/*  State                                                             */
/* ================================================================== */

let runIndex = 0;
let frameIndex = 0;
let playing = false;
let solution = null;
let panelTarget = null;
const manual = [null, null, null, null];

const run = () => WORLD.runs[runIndex];
const frame = () => run().frames[frameIndex];
const commands = () => frame().kw.map((k, i) => (manual[i] === null ? k : manual[i]));
const insideRoom = () => room.inside(camera.position.x, camera.position.z);

const api = {
  setRun(i) { runIndex = i; syncRunButtons(); },
  setFrame(i) { frameIndex = i; el('scrub').value = String(i); },
  clearManual() { manual.fill(null); },
};

const progress = new Progress(api);

function resolveNow() {
  const kw = commands();
  solution = solveAt(WORLD.day[frameIndex], kw);
  city.applyVoltages(kw, manual);
  redrawInstruments();
}

let instrumentsDue = true;
function redrawInstruments() { instrumentsDue = true; }

function flushInstruments() {
  if (!instrumentsDue) return;
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

const fwdTmp = new THREE.Vector3();
function focused() {
  camera.getWorldDirection(fwdTmp);
  const fx = fwdTmp.x, fz = fwdTmp.z;
  const fl = Math.hypot(fx, fz) || 1;
  let best = null, bestScore = Infinity;
  for (const it of TARGETS) {
    const dx = it.x - camera.position.x, dz = it.z - camera.position.z;
    const dist = Math.hypot(dx, dz);
    const reach = it.kind === 'console' || it.kind === 'terminal' ? 3.4 : 11;
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
    resolveNow();
    renderPanel();
    updateHud();
  };
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
      <p class="hint">The whole feeder, left to right by bus number. You are the amber dot.</p>`;
    progress.observeMeter(t.bus, { runIndex, frameIndex, solution });
  } else if (t.kind === 'station') {
    panel.innerHTML = stationPanelHtml(t.si, t.bus, `Bus ${t.bus} · charging station`, 'Station console');
    wireStationPanel(t.si);
    progress.observeConsole(t.si);
  } else if (t.kind === 'console') {
    panel.innerHTML = stationPanelHtml(t.si, t.bus, `Desk position ${t.si + 1} · bus ${t.bus}`, 'Dispatch console');
    wireStationPanel(t.si);
    progress.observeConsole(t.si);
  } else if (t.kind === 'terminal') {
    progress.observeTerminal();
    const rows = WORLD.candidates.map((c, i) => `
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
        room.logEvent(frame().clock, `deployed ${WORLD.candidates[progress.picked].label}`, 'info');
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

function openPanel(t) { panelTarget = t; controls.unlock(); renderPanel(); }
function closePanel() { panelTarget = null; el('panel').hidden = true; }

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
    el('objList').innerHTML = '<li class="done"><span class="tick">✓</span><span>All six stages complete. The city is yours to walk.</span></li>';
    el('stageTag').textContent = 'Free play';
    el('stageTitle').textContent = 'Walk the feeder';
    return;
  }
  renderObjectives();
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

  if (panelTarget) renderPanel();
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

addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (['w', 'a', 's', 'd', 'shift'].includes(k)) { held.add(k); if (controls.isLocked) e.preventDefault(); }
  if (k === 'e' && controls.isLocked) { const t = focused(); if (t) { openPanel(t); e.preventDefault(); } }
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
});
addEventListener('keyup', (e) => held.delete(e.key.toLowerCase()));

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

const runSeg = el('runSeg');
WORLD.runs.forEach((r, i) => {
  const b = document.createElement('button');
  b.textContent = r.label.replace(/ \(.*\)/, '').replace('IEEE 1547', '1547');
  b.title = r.label;
  b.onclick = () => {
    runIndex = i;
    syncRunButtons();
    room.logEvent(frame().clock, `feeder switched to ${r.label.replace(/ \(.*\)/, '')}`, 'info');
    resolveNow(); updateHud(); checkObjectives();
  };
  runSeg.appendChild(b);
});
function syncRunButtons() {
  [...runSeg.children].forEach((c, j) => c.setAttribute('aria-pressed', String(j === runIndex)));
}

const goSeg = el('goSeg');
[['Control room', room.spawn.x, room.spawn.z, room.spawn.yaw],
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
scrub.oninput = () => {
  frameIndex = Number(scrub.value);
  playing = false;
  el('play').textContent = 'Play';
  resolveNow(); updateHud();
};
el('play').onclick = () => {
  if (!playing && frameIndex >= WORLD.day.length - 1) {
    frameIndex = 0;
    scrub.value = '0';
    resolveNow();
    updateHud();
  }
  playing = !playing;
  el('play').textContent = playing ? 'Pause' : 'Play';
};
el('cardGo').onclick = dismissCard;

el('verdict').textContent = check.ok
  ? `${check.n} recorded control steps re-solved in the browser, worst voltage disagreement ${check.worstV.toExponential(1)} pu, violation counts identical.`
  : `MISMATCH — ${check.worstV.toExponential(2)} pu. Do not trust these numbers.`;

const totals = el('totals');
WORLD.candidates.forEach((r) => {
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${r.label}</td><td class="num">${r.violationRate.toFixed(3)}</td>` +
    `<td class="num">${Math.round(r.socMet * 287)} of 287</td>` +
    `<td class="num">${r.totalLossKwh.toFixed(0)} kWh</td>` +
    `<td class="num">$${r.netCostUsd}</td>` +
    `<td>${r.provenance === 'placeholder' ? 'labelled stand-in' : 'production controller'}</td>`;
  totals.appendChild(tr);
});

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
      frameIndex++;
      scrub.value = String(frameIndex);
      resolveNow();

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

  move(dt);
  assignPool();
  city.updateVehicles(dt, { plugged: frame().plugged, stationKw: commands(), running: playing });

  // Annunciator flash, held well under the WCAG 2.3.1 three-per-second threshold, and
  // suppressed entirely for anyone who has asked for reduced motion.
  if (!reduceMotion && t - flashT > 700) { flashT = t; room.setFlash(!(Math.floor(t / 700) % 2)); }

  const target = controls.isLocked ? focused() : null;
  const prompt = el('prompt');
  el('reticle').className = 'reticle' + (target ? ' hot' : '');
  if (target && !panelTarget) { prompt.hidden = false; prompt.innerHTML = '<kbd>E</kbd>' + target.label; }
  else prompt.hidden = true;

  if (controls.isLocked) updateHud();
  flushInstruments();
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
  setRun: (i) => { runIndex = i; syncRunButtons(); resolveNow(); updateHud(); },
  setFrame: (i) => { frameIndex = i; resolveNow(); updateHud(); },
  dismissCard,
  state: () => ({ runIndex, frameIndex, manual: [...manual], inside: insideRoom(), picked: progress.picked }),
  objectives: () => progress.status(liveState()),
  lockQuality() { autoQuality = false; setTier(3); },
  setPoolSize(n) { poolLimit = n; },
};
