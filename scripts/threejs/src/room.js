/**
 * The control centre.
 *
 * Every instrument in here is one a distribution control room actually has, and every
 * one of them is driven by the solver rather than decorated: the mimic board is the
 * live one-line, the annunciator latches on real band violations and has to be
 * acknowledged, the trend wall plots the day that is actually running, and the
 * sequence-of-events log records things as they happen rather than replaying a script.
 *
 * The displays are 2D canvases mapped onto planes. That is the cheap and sharp way to
 * put a chart on a wall in a 3D scene — a texture upload beats rebuilding geometry,
 * and text stays legible because it is drawn at native resolution.
 */

import * as THREE from 'three';
import {
  WORLD, N_BUS, BAND_LO, ROOM, EYE, place, mat, PALETTE, vMag, solids, STATION_SET,
  maxAnisotropy,
} from './core.js';

const CSS = {
  ink: '#e8ecf2',
  dim: '#8b97a6',
  faint: '#4a5563',
  panel: '#10161d',
  panelLine: '#1d2731',
  ok: '#4fb3a2',
  warn: '#e4776b',
  amber: '#e3b24f',
  cool: '#5aa9d6',
};

const MONO = '"SF Mono", "JetBrains Mono", Menlo, Consolas, monospace';

/** A canvas mapped onto a plane, with the texture flagged only when it is redrawn. */
class Screen {
  constructor(scene, { w, h, px = 110, pos, rotY = 0, tiltX = 0 }) {
    this.canvas = document.createElement('canvas');
    this.canvas.width = Math.round(w * px);
    this.canvas.height = Math.round(h * px);
    this.ctx = this.canvas.getContext('2d');
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.anisotropy = maxAnisotropy;
    const material = new THREE.MeshBasicMaterial({ map: this.texture, toneMapped: false });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), material);
    this.mesh.position.set(pos.x, pos.y, pos.z);
    this.mesh.rotation.set(tiltX, rotY, 0, 'YXZ');
    scene.add(this.mesh);

    // A bezel, so a screen reads as hardware bolted to a wall rather than a decal.
    const bezel = new THREE.Mesh(new THREE.BoxGeometry(w + 0.22, h + 0.22, 0.12), mat.cabinet);
    bezel.position.copy(this.mesh.position);
    bezel.rotation.copy(this.mesh.rotation);
    bezel.translateZ(-0.08);
    scene.add(bezel);
  }

  get width() { return this.canvas.width; }
  get height() { return this.canvas.height; }

  clear(fill = CSS.panel) {
    const { ctx } = this;
    ctx.fillStyle = fill;
    ctx.fillRect(0, 0, this.width, this.height);
  }

  label(text, x, y, { size = 15, colour = CSS.dim, align = 'left', weight = '' } = {}) {
    const { ctx } = this;
    ctx.font = `${weight} ${size}px ${MONO}`.trim();
    ctx.fillStyle = colour;
    ctx.textAlign = align;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(text, x, y);
  }

  /** Drawn width of a string, for laying columns out against the type rather than guessing. */
  measure(text, size, weight = '') {
    this.ctx.font = `${weight} ${size}px ${MONO}`.trim();
    return this.ctx.measureText(text).width;
  }

  done() { this.texture.needsUpdate = true; }
}

const busColour = (v) => (v < BAND_LO ? CSS.warn : v < 0.97 ? CSS.amber : CSS.ok);

/** Height of the mimic board's two-row footer, in canvas pixels. */
const FOOT_H = 104;

export function buildRoom(scene) {
  const group = new THREE.Group();

  /* ------------------------------------------------------------ shell */

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(ROOM.w, ROOM.d), mat.roomFloor);
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(ROOM.x, 0.02, ROOM.z);
  floor.receiveShadow = true;
  group.add(floor);

  const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(ROOM.w, ROOM.d), mat.roomWall);
  ceiling.rotation.x = Math.PI / 2;
  ceiling.position.set(ROOM.x, ROOM.h, ROOM.z);
  group.add(ceiling);

  const wall = (x, z, w, d) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, ROOM.h, d), mat.roomWall);
    m.position.set(x, ROOM.h / 2, z);
    m.castShadow = m.receiveShadow = true;
    group.add(m);
    solids.push({ x, z, w, d });
  };
  wall(ROOM.x, ROOM.north, ROOM.w, 0.4);
  wall(ROOM.x, ROOM.south, ROOM.w, 0.4);
  wall(ROOM.west, ROOM.z, 0.4, ROOM.d);
  // East wall in two pieces; the gap between them is the door.
  const doorLo = ROOM.doorZ - ROOM.doorW / 2;
  const doorHi = ROOM.doorZ + ROOM.doorW / 2;
  wall(ROOM.east, (ROOM.north + doorLo) / 2, 0.4, doorLo - ROOM.north);
  wall(ROOM.east, (doorHi + ROOM.south) / 2, 0.4, ROOM.south - doorHi);

  // Room lighting. Fluorescent-cool, unlike the sodium street outside — the contrast
  // is what makes stepping out of the door feel like leaving the instruments behind.
  // Intensity is candela and falls as 1/d². A ceiling fitting is ~4.5 m from the eye
  // where a street lamp is ~13 m, so it needs roughly a twentieth of the street lamp's
  // 1550 — not the same number. Using street values in here rendered a white-out.
  //
  // Raising the ceiling from 4.6 m to 6.2 m moved the fittings from 3 m above the eye to
  // 4.5 m, which is (3/4.5)² = 0.44 of the light at the desk. The intensity is scaled to
  // match, so the taller room is not a darker one. Two extra fittings run north and south
  // of the centre line, because a single row down the middle of a 6.2 m room leaves the
  // wall boards — which is the whole reason to be in here — lit only by their own glow.
  for (const dz of [-5.5, 0, 5.5]) {
    for (const dx of [-7, 0, 7]) {
      const panel = new THREE.Mesh(
        new THREE.BoxGeometry(4.4, 0.1, 1.1),
        new THREE.MeshBasicMaterial({ color: 0x9db2c4, toneMapped: false }),
      );
      panel.position.set(ROOM.x + dx, ROOM.h - 0.12, ROOM.z + dz);
      group.add(panel);
      // Nine fittings where there were three, so each carries roughly a third of the
      // flux it would need alone. Matching the old room's 90 candela per fitting here
      // rendered a white-out: three rows of them add up.
      const l = new THREE.PointLight(0xdce8f4, dz === 0 ? 120 : 78, 24, 2);
      l.position.set(ROOM.x + dx, ROOM.h - 0.6, ROOM.z + dz);
      group.add(l);
    }
  }

  /* ------------------------------------------------------- mimic board */

  /**
   * Sized and hung to be readable from the dispatch desk.
   *
   * The bottom edge sits at 1.95 m because that is what clears the console lids in front
   * of it — below that the footer readouts are behind a monitor from the one position an
   * operator actually occupies. Everything else follows from that: the board grew upward,
   * and the ceiling grew to take it.
   */
  const mimic = new Screen(scene, {
    w: 15, h: 4.1, px: 112,
    pos: { x: ROOM.west + 0.28, y: 4.0, z: ROOM.z },
    rotY: Math.PI / 2,
  });

  function drawMimic(state) {
    const s = mimic;
    const W = s.width, H = s.height;
    s.clear('#0b1116');
    const ctx = s.ctx;

    // Header strip.
    ctx.fillStyle = '#131c25';
    ctx.fillRect(0, 0, W, 72);
    s.label('FEEDER 33  ·  ONE-LINE MIMIC', 22, 46, { size: 26, colour: CSS.ink });
    s.label(state.clock, W - 22, 46, { size: 30, colour: CSS.amber, align: 'right' });
    s.label(state.runLabel.toUpperCase(), W / 2, 32, { size: 22, colour: CSS.cool, align: 'center' });
    s.label(state.source.toUpperCase(), W / 2, 58, { size: 16, colour: CSS.faint, align: 'center' });

    // Four rows of buses: the trunk and three laterals. The row spacing is derived from
    // the plot area rather than fixed, because a fixed 78 px put the third lateral 3 px
    // below the bottom edge of the old board — eight buses drawn where nobody could see
    // them, on the one instrument that claims to show the whole feeder.
    const TOP = 100, BOT = H - FOOT_H - 30;
    const xOf = (col) => 90 + (col / 17) * (W - 190);
    const yOf = (row) => TOP + ((row + 1) / 3) * (BOT - TOP);

    // Branches first, coloured by the loss they are carrying.
    ctx.lineWidth = 4;
    for (let i = 0; i < WORLD.branches.length; i++) {
      const br = WORLD.branches[i];
      const a = place.get(br.from), b = place.get(br.to);
      const heat = Math.min(1, state.branchLoss[i + 1] / 4);
      ctx.strokeStyle = heat > 0.15
        ? `rgb(${Math.round(90 + heat * 150)},${Math.round(70 - heat * 30)},${Math.round(70 - heat * 30)})`
        : '#2b3a47';
      ctx.beginPath();
      ctx.moveTo(xOf(a.col), yOf(a.row));
      ctx.lineTo(xOf(b.col), yOf(b.row));
      ctx.stroke();
    }

    // The source, drawn as the grid tie it is.
    ctx.strokeStyle = CSS.cool;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(38, yOf(0));
    ctx.lineTo(xOf(0), yOf(0));
    ctx.stroke();
    s.label('GRID', 38, yOf(0) - 16, { size: 16, colour: CSS.cool });

    // Buses.
    for (const p of place.values()) {
      const v = vMag[p.bus];
      const x = xOf(p.col), y = yOf(p.row);
      ctx.fillStyle = busColour(v);
      ctx.beginPath();
      ctx.arc(x, y, STATION_SET.has(p.bus) ? 11 : 7, 0, Math.PI * 2);
      ctx.fill();
      if (STATION_SET.has(p.bus)) {
        ctx.strokeStyle = CSS.ok;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(x, y, 17, 0, Math.PI * 2);
        ctx.stroke();
      }
      if (v < BAND_LO) {
        s.label(v.toFixed(3), x, y - 20, { size: 14, colour: CSS.warn, align: 'center' });
      }
      s.label(String(p.bus), x, y + 30, { size: 13, colour: CSS.faint, align: 'center' });
    }

    // You, on the board, if you are out in the town.
    if (state.youBus && !state.inside) {
      const p = place.get(state.youBus);
      const x = xOf(p.col), y = yOf(p.row);
      ctx.strokeStyle = CSS.ink;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.arc(x, y, 24, 0, Math.PI * 2);
      ctx.stroke();
      s.label('YOU', x, y - 32, { size: 14, colour: CSS.ink, align: 'center' });
    }

    // Footer readouts, in two rows.
    //
    // The top row is the feeder's health and the bottom row is the service it is buying,
    // which is the whole argument of the project laid out on one instrument. A viewer who
    // reads only the top row can be told a controller is doing well by one that has simply
    // stopped charging anybody; the second row is what makes that impossible to claim.
    ctx.fillStyle = '#131c25';
    ctx.fillRect(0, H - FOOT_H, W, FOOT_H);
    const r1 = H - FOOT_H + 36;
    const r2 = H - 22;
    const cols = [22, W * 0.28, W * 0.56];
    const svc = [22, W * 0.27, W * 0.53, W * 0.77];

    s.label(`WORST  ${state.vMin.toFixed(4)} pu @ BUS ${state.vMinBus}`, cols[0], r1,
      { size: 22, colour: state.vMin < BAND_LO ? CSS.warn : CSS.ok });
    s.label(`OUT OF BAND  ${state.violations} / ${N_BUS}`, cols[1], r1,
      { size: 22, colour: state.violations ? CSS.warn : CSS.ok });
    s.label(`LINE LOSS  ${state.lossKw.toFixed(0)} kW`, cols[2], r1, { size: 22, colour: CSS.amber });
    s.label(`POWER  $${state.price.toFixed(2)} · ${state.tier.toUpperCase()}`, W - 22, r1,
      { size: 22, colour: state.tier === 'peak' ? CSS.warn : CSS.dim, align: 'right' });

    // LEFT SHORT is the counterweight to CHARGED: vehicles that have already unplugged and
    // driven away below the charge they came for. A controller can hold the top row of this
    // board perfectly by refusing everybody, and this is the number that shows it doing so.
    // It counts departures only — a car still on the cable has not failed yet.
    s.label(`PLUGGED IN  ${state.pluggedTotal}`, svc[0], r2, { size: 20, colour: CSS.cool });
    s.label(`CHARGED  ${state.served} / ${state.fleetSize}`, svc[1], r2, { size: 20, colour: CSS.cool });
    s.label(`LEFT SHORT  ${state.short}`, svc[2], r2,
      { size: 20, colour: state.short ? CSS.amber : CSS.cool });
    s.label(`DRAWING  ${state.drawKw.toFixed(0)} kW`, svc[3], r2, { size: 20, colour: CSS.cool });
    s.done();
  }

  /* ------------------------------------------------------- annunciator */

  const ALARMS = [
    { id: 'uv', text: 'UNDER\nVOLTAGE', test: (s) => s.violations > 0 },
    { id: 'end', text: 'FEEDER END\nLOW', test: () => vMag[18] < BAND_LO },
    { id: 'lat', text: 'LATERAL\nLOW', test: () => [26, 27, 28, 29, 30, 31, 32, 33].some((b) => vMag[b] < BAND_LO) },
    { id: 'loss', text: 'HIGH LINE\nLOSS', test: (s) => s.lossKw > 200 },
    { id: 'man', text: 'STATION IN\nMANUAL', test: (s) => s.anyManual },
    { id: 'sub', text: 'SOURCE\nSAG', test: () => vMag[1] < 0.97 },
    { id: 'pv', text: 'PV ARRAY\nOFFLINE', test: (s) => s.solar <= 0 },
    { id: 'std', text: 'STAND-IN\nCONTROLLER', test: (s) => s.standIn },
  ];

  // South wall, above the relay cabinets. The cabinets stand 2.2 m and the board's bottom
  // edge is at 2.6 m, which is the whole reason it is up here: at its old height the row
  // of tiles a visitor most needs to read was behind a cubicle.
  const annun = new Screen(scene, {
    w: 6.4, h: 2.4, px: 130,
    pos: { x: ROOM.x - 6.0, y: 3.8, z: ROOM.south - 0.28 },
    rotY: Math.PI,
  });

  // Annunciator behaviour, as built: a new alarm flashes until acknowledged, then
  // burns steady while the condition persists, then goes dark when it clears.
  const alarmState = new Map(ALARMS.map((a) => [a.id, { active: false, acked: false }]));
  let alarmFlash = false;

  function drawAnnunciator() {
    const s = annun;
    const W = s.width, H = s.height;
    s.clear('#0d1319');
    s.label('ALARM ANNUNCIATOR', 16, 30, { size: 18, colour: CSS.dim });
    const anyUnacked = ALARMS.some((a) => alarmState.get(a.id).active && !alarmState.get(a.id).acked);
    s.label(anyUnacked ? 'PRESS  F  TO ACKNOWLEDGE' : 'ALL ACKNOWLEDGED', W - 16, 30,
      { size: 18, colour: anyUnacked ? CSS.amber : CSS.faint, align: 'right' });

    const cols = 4, rows = 2;
    const padX = 14, padY = 44;
    const tw = (W - padX * (cols + 1)) / cols;
    const th = (H - padY - padX * rows) / rows;
    ALARMS.forEach((a, i) => {
      const cx = padX + (i % cols) * (tw + padX);
      const cy = padY + Math.floor(i / cols) * (th + padX);
      const st = alarmState.get(a.id);
      const lit = st.active && (st.acked || alarmFlash);
      s.ctx.fillStyle = lit ? (st.acked ? '#3a1f1c' : '#5c2b25') : '#151d25';
      s.ctx.fillRect(cx, cy, tw, th);
      s.ctx.strokeStyle = st.active ? CSS.warn : '#212b35';
      s.ctx.lineWidth = 3;
      s.ctx.strokeRect(cx, cy, tw, th);
      const lines = a.text.split('\n');
      lines.forEach((ln, j) => {
        s.label(ln, cx + tw / 2, cy + th / 2 + (j - (lines.length - 1) / 2) * 24 + 8,
          { size: 20, colour: st.active ? (lit ? '#ffd9d2' : CSS.warn) : CSS.faint, align: 'center' });
      });
    });
    s.done();
  }

  function updateAlarms(state) {
    let raised = null;
    for (const a of ALARMS) {
      const st = alarmState.get(a.id);
      const now = a.test(state);
      if (now && !st.active) { st.active = true; st.acked = false; raised = a; }
      if (!now && st.active) { st.active = false; st.acked = false; }
    }
    return raised;
  }

  function ackAlarms() {
    let n = 0;
    for (const [, st] of alarmState) if (st.active && !st.acked) { st.acked = true; n++; }
    return n;
  }

  const alarmsPending = () => ALARMS.filter((a) => {
    const st = alarmState.get(a.id);
    return st.active && !st.acked;
  }).length;

  /* -------------------------------------------------------- trend wall */

  const trend = new Screen(scene, {
    w: 7, h: 2.6, px: 130,
    pos: { x: ROOM.x + 6.4, y: 3.0, z: ROOM.north + 0.28 },
  });

  function drawTrend(state) {
    const s = trend;
    const W = s.width, H = s.height;
    s.clear('#0d1319');
    s.label('TRENDS · 24 HOURS', 16, 30, { size: 18, colour: CSS.dim });
    s.label(state.runLabel.toUpperCase(), W - 16, 30, { size: 18, colour: CSS.cool, align: 'right' });

    const frames = state.frames;
    const n = frames.length;
    const plot = (y0, y1, get, lo, hi, colour, title, fmt) => {
      const ctx = s.ctx;
      ctx.strokeStyle = '#1d2731';
      ctx.lineWidth = 1;
      ctx.strokeRect(56, y0, W - 76, y1 - y0);
      s.label(title, 56, y0 - 8, { size: 16, colour: CSS.dim });
      const xs = (i) => 56 + (i / (n - 1)) * (W - 76);
      const ys = (v) => y1 - ((v - lo) / (hi - lo)) * (y1 - y0);
      if (title.startsWith('WORST')) {
        ctx.strokeStyle = CSS.warn;
        ctx.setLineDash([6, 5]);
        ctx.beginPath();
        ctx.moveTo(56, ys(BAND_LO));
        ctx.lineTo(W - 20, ys(BAND_LO));
        ctx.stroke();
        ctx.setLineDash([]);
        s.label('0.95', 50, ys(BAND_LO) + 5, { size: 13, colour: CSS.warn, align: 'right' });
      }
      ctx.strokeStyle = colour;
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      frames.forEach((f, i) => {
        const v = Math.max(lo, Math.min(hi, get(f)));
        i ? ctx.lineTo(xs(i), ys(v)) : ctx.moveTo(xs(i), ys(v));
      });
      ctx.stroke();
      // Where the day currently is.
      const cx = xs(state.frameIndex);
      ctx.strokeStyle = CSS.ink;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.moveTo(cx, y0); ctx.lineTo(cx, y1);
      ctx.stroke();
      s.label(fmt(get(frames[state.frameIndex])), W - 22, y0 + 20, { size: 20, colour, align: 'right' });
    };

    plot(64, 168, (f) => f.vmin, 0.82, 1.01, CSS.ok, 'WORST BUS VOLTAGE (pu)', (v) => v.toFixed(3));
    plot(216, 314, (f) => f.loss, 0, 520, CSS.amber, 'LINE LOSS (kW)', (v) => v.toFixed(0) + ' kW');
    s.done();
  }

  /* ------------------------------------------------ sequence of events */

  const soe = new Screen(scene, {
    w: 7, h: 2.4, px: 130,
    pos: { x: ROOM.x + 5.6, y: 3.8, z: ROOM.south - 0.28 },
    rotY: Math.PI,
  });

  const events = [];
  function logEvent(clock, text, tone = 'info') {
    events.push({ clock, text, tone });
    if (events.length > 200) events.shift();
    drawSoe();
  }

  function drawSoe() {
    const s = soe;
    s.clear('#0d1319');
    s.label('SEQUENCE OF EVENTS', 16, 30, { size: 18, colour: CSS.dim });
    const rows = 11;
    const shown = events.slice(-rows);
    shown.forEach((e, i) => {
      const y = 62 + i * 24;
      s.label(e.clock, 16, y, { size: 17, colour: CSS.faint });
      s.label(e.text, 92, y, {
        size: 17,
        colour: e.tone === 'alarm' ? CSS.warn : e.tone === 'good' ? CSS.ok : CSS.ink,
      });
    });
    if (!events.length) s.label('no events logged', 16, 62, { size: 17, colour: CSS.faint });
    s.done();
  }

  /* ------------------------------------------------------- the map wall */

  // On the east side, on the cabinet the supervisory console used to stand on. It is the
  // one board you read on the way out rather than while working, which is what a kiosk in
  // the middle of the floor is for.
  const mapScreen = new Screen(scene, {
    w: 5.0, h: 3.0, px: 150,
    pos: { x: ROOM.east - 1.5, y: 2.7, z: ROOM.z + 5.6 },
    rotY: -Math.PI / 2,
  });
  {
    const stand = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.05, 2.6), mat.cabinet);
    stand.position.set(ROOM.east - 1.3, 0.52, ROOM.z + 5.6);
    stand.castShadow = true;
    group.add(stand);
    solids.push({ x: ROOM.east - 1.3, z: ROOM.z + 5.6, w: 1.2, d: 2.6 });

    const l = new THREE.PointLight(0xdce8f4, 30, 10, 2);
    l.position.set(ROOM.east - 2.6, 4.4, ROOM.z + 5.6);
    group.add(l);
  }

  /**
   * The Pareto map: every finished run leaves a dot. Safety on one axis, service on
   * the other, because a controller comparison with only the first column cannot tell
   * a good controller from one that does nothing.
   */
  function drawMap(dots) {
    const s = mapScreen;
    const W = s.width, H = s.height;
    s.clear('#0d1319');
    s.label('EVERY RUN YOU FINISH LEAVES A DOT', 16, 30, { size: 20, colour: CSS.dim });

    const L = 74, R = W - 24, T = 56, B = H - 52;
    // Clamped a dot's radius inside the frame, so a controller that serves everybody is
    // a circle at the top rather than a half-circle bleeding off the board.
    const xs = (v) => L + 9 + Math.min(1, v / 0.36) * (R - L - 18);
    const ys = (v) => B - 9 - Math.min(1, v) * (B - T - 18);

    s.ctx.strokeStyle = '#1d2731';
    s.ctx.lineWidth = 1;
    s.ctx.strokeRect(L, T, R - L, B - T);
    for (let g = 1; g < 4; g++) {
      const y = T + (g / 4) * (B - T);
      s.ctx.beginPath(); s.ctx.moveTo(L, y); s.ctx.lineTo(R, y); s.ctx.stroke();
    }
    s.label('← safer', L + 6, B + 26, { size: 15, colour: CSS.faint });
    s.label('violation rate', (L + R) / 2, B + 26, { size: 15, colour: CSS.faint, align: 'center' });
    s.label('more', 62, T + 14, { size: 15, colour: CSS.faint, align: 'right' });
    s.label('served', 62, T + 32, { size: 15, colour: CSS.faint, align: 'right' });
    s.label('↑', 62, T - 6, { size: 15, colour: CSS.faint, align: 'right' });

    for (const d of dots) {
      const x = xs(d.violationRate), y = ys(d.socMet);
      s.ctx.fillStyle = d.mine ? CSS.ink : d.colour;
      s.ctx.strokeStyle = d.mine ? CSS.ink : d.colour;
      s.ctx.lineWidth = 2.5;
      s.ctx.beginPath();
      if (d.mine) {
        // The learner's own runs are hollow, so a crowd of them stays legible against
        // the four reference controllers.
        s.ctx.arc(x, y, 8, 0, Math.PI * 2);
        s.ctx.stroke();
      } else {
        s.ctx.arc(x, y, 7, 0, Math.PI * 2);
        s.ctx.fill();
      }
    }

    // Legend down the right, inside the plot, since the room wall has no margin.
    let ly = T + 18;
    const lx = R - 220;
    for (const d of dots.filter((x) => !x.mine)) {
      s.ctx.fillStyle = d.colour;
      s.ctx.beginPath(); s.ctx.arc(lx, ly - 5, 5, 0, Math.PI * 2); s.ctx.fill();
      s.label(d.label.replace(/ \(.*\)/, ''), lx + 12, ly, { size: 15, colour: CSS.dim });
      ly += 22;
    }
    const mine = dots.filter((d) => d.mine).length;
    s.label(mine ? `${mine} of your own` : 'none of your own yet', lx, ly + 4,
      { size: 15, colour: mine ? CSS.ink : CSS.faint });
    s.done();
  }

  /* -------------------------------------------------------- dispatch desk */

  const DESK = { x: ROOM.x - 2.6, z: ROOM.z };
  {
    const top = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.12, 7.2), mat.desk);
    top.position.set(DESK.x, 0.98, DESK.z);
    top.castShadow = top.receiveShadow = true;
    group.add(top);
    const front = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.9, 7.0), mat.cabinet);
    front.position.set(DESK.x, 0.47, DESK.z);
    group.add(front);
    solids.push({ x: DESK.x, z: DESK.z, w: 1.9, d: 7.2 });

    const chair = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.34, 0.5, 10), mat.cabinet);
    chair.position.set(DESK.x + 1.7, 0.6, DESK.z);
    group.add(chair);
  }

  // Four station consoles, one per charging station, angled up toward the operator.
  // They sit at desk height rather than eye height: a monitor you have to look over is
  // a monitor that hides the mimic board, which is the one thing that must stay visible.
  // Sized and placed to sit on the desk surface (y 1.04) without reaching high enough
  // to cover the laterals on the mimic board behind them.
  const consoles = WORLD.stations.map((bus, si) => {
    const z = DESK.z - 2.55 + si * 1.7;
    const screen = new Screen(scene, {
      w: 1.15, h: 0.68, px: 300,
      pos: { x: DESK.x - 0.3, y: 1.36, z },
      rotY: Math.PI / 2, tiltX: -0.45,
    });
    return { bus, si, screen, z };
  });

  function drawConsole(c, state) {
    const s = c.screen;
    const W = s.width, H = s.height;
    const taken = state.manual[c.si] !== null;
    s.clear(taken ? '#1b1710' : '#0d1319');
    s.label(`STATION ${c.si + 1} · BUS ${c.bus}`, 14, 32, { size: 22, colour: CSS.ink });
    s.label(taken ? 'MANUAL' : 'AUTO', W - 14, 32, { size: 18, colour: taken ? CSS.amber : CSS.ok, align: 'right' });

    const kw = state.stationKw[c.si];
    const v = vMag[c.bus];
    s.label(kw < -1 ? `${Math.abs(kw).toFixed(0)} kW DRAWN` : kw > 1 ? `${kw.toFixed(0)} kW RETURNED` : 'IDLE',
      14, 82, { size: 34, colour: CSS.amber });
    s.label(`${state.plugged[c.si]} plugged`, 14, 118, { size: 20, colour: CSS.dim });
    s.label(`${v.toFixed(4)} pu`, W - 14, 118, { size: 20, colour: busColour(v), align: 'right' });

    // Power bar: full scale is the 900 kW the console can command either way.
    const bx = 14, by = 138, bw = W - 28, bh = 22;
    s.ctx.fillStyle = '#1a232c';
    s.ctx.fillRect(bx, by, bw, bh);
    const frac = Math.min(1, Math.abs(kw) / 900);
    s.ctx.fillStyle = kw > 0 ? CSS.cool : CSS.amber;
    s.ctx.fillRect(bx + bw / 2, by, (kw > 0 ? 1 : -1) * frac * (bw / 2), bh);
    s.ctx.fillStyle = CSS.faint;
    s.ctx.fillRect(bx + bw / 2 - 1, by - 3, 2, bh + 6);
    s.done();
  }

  /* ------------------------------------------------ procurement terminal */

  // 190 px/m gave a 418×285 canvas carrying type sized for something twice that. Every
  // column ran into the next: the two headings overlapped by 40 px, each row's name ran
  // through its own violation figure, and the footnote was drawn seven pixels above the
  // last row's baseline. The panel is small on purpose, so the fix is resolution.
  const terminal = new Screen(scene, {
    w: 2.2, h: 1.5, px: 420,
    pos: { x: ROOM.east - 1.5, y: 1.75, z: ROOM.z - 6.0 },
    rotY: -Math.PI / 2 + 0.5,
  });
  {
    const stand = new THREE.Mesh(new THREE.BoxGeometry(1.1, 1.05, 1.6), mat.cabinet);
    stand.position.set(ROOM.east - 1.35, 0.52, ROOM.z - 6.0);
    stand.castShadow = true;
    group.add(stand);
    solids.push({ x: ROOM.east - 1.35, z: ROOM.z - 6.0, w: 1.1, d: 1.6 });
  }

  /**
   * The board carries the two columns a procurement table carries, and no others. That
   * omission is the stage: drivers served is exactly the column that would expose the
   * candidate trained on a stiff feeder, and it is not here, because it is not there.
   * Nothing else belongs on this panel.
   */
  const TERM = { pad: 40, rowTop: 214, rowStep: 96, name: 28, qual: 16, head: 17 };

  /** Split 'Droop (IEEE 1547)' into its name and its qualifier, for a two-line row. */
  const splitLabel = (label) => {
    const m = /^(.*?) \((.*)\)$/.exec(label);
    return m ? { name: m[1], qual: m[2] } : { name: label, qual: '' };
  };

  function terminalRows(state) {
    const list = state.candidates ?? WORLD.candidates;
    return list.map((r, i) => {
      const { name, qual } = splitLabel(r.label);
      return {
        i,
        name,
        qual: r.provenance === 'placeholder' ? [qual, 'reference implementation'].filter(Boolean).join(' · ') : qual,
        viol: r.violationRate.toFixed(3),
        cost: '$' + Math.round(r.netCostUsd ?? 0),
        picked: state.picked === i,
      };
    });
  }

  function drawTerminal(state) {
    const s = terminal;
    const W = s.width, H = s.height;
    const { pad, rowTop, rowStep } = TERM;
    const rows = terminalRows(state);

    s.clear('#0d1319');
    s.label('PROCUREMENT', pad, 66, { size: 34, colour: CSS.ink });
    s.label('SAME FEEDER · SAME DAY · SAME FLEET', pad, 98, { size: 17, colour: CSS.faint });

    const rule = (y) => { s.ctx.fillStyle = '#1e2830'; s.ctx.fillRect(pad, y, W - pad * 2, 2); };
    rule(120);

    // Columns are placed against the widest figure actually drawn, not against a guess.
    const costW = Math.max(...rows.map((r) => s.measure(r.cost, TERM.name)));
    const violW = Math.max(...rows.map((r) => s.measure(r.viol, TERM.name)));
    const costX = W - pad;
    const violX = costX - costW - 64;
    s.label('CONTROLLER', pad, 168, { size: TERM.head, colour: CSS.dim });
    s.label('VIOLATIONS', violX, 168, { size: TERM.head, colour: CSS.dim, align: 'right' });
    s.label('NET COST', costX, 168, { size: TERM.head, colour: CSS.dim, align: 'right' });
    rule(184);

    rows.forEach((r) => {
      const y = rowTop + r.i * rowStep;
      if (r.picked) {
        s.ctx.fillStyle = '#16261f';
        s.ctx.fillRect(pad - 14, y - 36, W - pad * 2 + 28, rowStep - 18);
      }
      const ink = r.picked ? CSS.ok : CSS.ink;
      s.label(r.name, pad, y, { size: TERM.name, colour: ink });
      if (r.qual) s.label(r.qual, pad, y + 26, { size: TERM.qual, colour: CSS.faint });
      s.label(r.viol, violX, y, { size: TERM.name, colour: ink, align: 'right' });
      s.label(r.cost, costX, y, { size: TERM.name, colour: ink, align: 'right' });
    });

    s.label(state.picked === null ? 'PRESS  ENTER  TO CHOOSE' : 'DEPLOYED',
      pad, H - 34, { size: 22, colour: state.picked === null ? CSS.amber : CSS.ok });
    s.done();

    // Exposed so the layout can be asserted rather than re-eyeballed. Every extent here
    // is measured from the same context that drew it.
    terminal.layout = {
      width: W,
      height: H,
      violX,
      costX,
      headEnd: pad + s.measure('CONTROLLER', TERM.head),
      violStart: violX - s.measure('VIOLATIONS', TERM.head),
      costStart: costX - s.measure('NET COST', TERM.head),
      lastRowBottom: rowTop + (rows.length - 1) * rowStep + 26,
      footTop: H - 34 - 22,
      rows: rows.map((r) => ({
        name: r.name,
        nameEnd: pad + s.measure(r.name, TERM.name),
        violStart: violX - s.measure(r.viol, TERM.name),
        costStart: costX - s.measure(r.cost, TERM.name),
      })),
    };
  }

  /* ------------------------------------------------ supervisory console */

  /**
   * Everything that used to live in the page's toolbar, put where an operator would
   * actually reach it.
   *
   * The toolbar version worked, but it taught the wrong thing: it let you rebuild the
   * feeder and re-time the day from outside the world, as though the town were a
   * document you were editing rather than a plant you were running. A control room is
   * the place those decisions get made from, so this is where they are made from. The
   * face here is a live mimic of the settings — it never asks a question, it only shows
   * what the plant is set to — and `E` opens the panel that changes them.
   */
  // On the north wall, where the alarm board used to be — the largest uninterrupted face
  // in the room, and now the busiest board in it. It carries every setting the plant has,
  // so it needs the space the old kiosk did not have and the clear approach a wall gives.
  //
  // Square to the room, unlike the procurement terminal's angled kiosk. That one is read
  // once and walked away from; this one is operated, and a face you have to stand
  // off-normal to reach is a face you misread.
  const supervisor = new Screen(scene, {
    w: 6.4, h: 3.0, px: 150,
    // Low enough that the whole face is inside a standing 68° frame from the spot the
    // Go-to shortcut drops you on. A board you have to crane at is one you operate from
    // memory, which defeats the reason it was moved off the page in the first place.
    pos: { x: ROOM.x - 6.2, y: 2.8, z: ROOM.north + 0.28 },
    rotY: 0,
  });
  {
    // A lamp over it, because the one thing a visitor must find is the one thing the
    // room was not previously lighting.
    const l = new THREE.PointLight(0xdce8f4, 40, 12, 2);
    l.position.set(ROOM.x - 6.2, 4.9, ROOM.north + 2.0);
    group.add(l);
  }

  /** A row of pills, one lit. Returns nothing; it is drawn for reading, not for hit-testing. */
  function pills(s, items, active, x, y, { h = 30, gap = 7, size = 15, locked = false } = {}) {
    const ctx = s.ctx;
    let cx = x;
    items.forEach((label, i) => {
      ctx.font = `${size}px ${MONO}`;
      const w = ctx.measureText(label).width + 20;
      const on = i === active;
      ctx.fillStyle = on ? (locked ? '#2b2620' : '#1d3a34') : '#151d25';
      ctx.fillRect(cx, y, w, h);
      ctx.strokeStyle = on ? (locked ? CSS.faint : CSS.ok) : '#212b35';
      ctx.lineWidth = 2;
      ctx.strokeRect(cx, y, w, h);
      s.label(label, cx + w / 2, y + h / 2 + 5, {
        size,
        colour: on ? (locked ? CSS.dim : CSS.ink) : CSS.faint,
        align: 'center',
      });
      cx += w + gap;
    });
    return cx;
  }

  /** A labelled dial: a number, its units, and a bar showing where it sits in its range. */
  function dial(s, { x, y, w, label, value, unit, frac, note, locked }) {
    s.label(label, x, y, { size: 15, colour: CSS.dim });
    s.label(value, x, y + 44, { size: 34, colour: locked ? CSS.faint : CSS.ink });
    s.ctx.font = `34px ${MONO}`;
    s.label(unit, x + s.ctx.measureText(value).width + 10, y + 44, { size: 16, colour: CSS.dim });

    const by = y + 60;
    s.ctx.fillStyle = '#151d25';
    s.ctx.fillRect(x, by, w, 12);
    s.ctx.fillStyle = locked ? CSS.faint : CSS.ok;
    s.ctx.fillRect(x, by, Math.max(3, w * frac), 12);
    if (note) s.label(note, x, by + 32, { size: 13, colour: CSS.faint });
  }

  function drawSupervisor(state) {
    const s = supervisor;
    const sup = state.sup;
    const W = s.width, H = s.height;
    s.clear('#0d1319');

    s.ctx.fillStyle = '#131c25';
    s.ctx.fillRect(0, 0, W, 52);
    s.label('SUPERVISORY CONTROL', 18, 34, { size: 22, colour: CSS.ink });
    s.label(sup.open ? 'IN USE' : 'PRESS  ENTER', W - 18, 34,
      { size: 19, colour: sup.open ? CSS.ok : CSS.amber, align: 'right' });

    // Two columns: what is running the plant on the left, what the plant is made of on
    // the right. Notes sit on their own line under the row they qualify, not beside it —
    // beside it they ran into the last pill at exactly the settings a learner is most
    // likely to be reading, which is the worst place for two pieces of text to touch.
    const L = 18, R = 500;

    s.label('WHO IS DRIVING', L, 88, { size: 15, colour: CSS.dim });
    pills(s, sup.runLabels, sup.runIndex, L, 100);

    s.label('THE FEEDER', L, 176, { size: 15, colour: CSS.dim });
    pills(s, ['WEAK', 'STIFF'], sup.gridKind === 'strong' ? 1 : 0, L, 188,
      { locked: !sup.gridUnlocked });
    if (!sup.gridUnlocked) s.label('locked until the six stages are done', L, 236, { size: 13, colour: CSS.faint });

    s.label('HOW BIG THE TOWN IS', L, 268, { size: 15, colour: CSS.dim });
    pills(s, ['0.5x', '1x', '1.4x', '1.8x'], sup.loadIndex, L, 280,
      { locked: !sup.loadUsable });
    if (!sup.loadUsable) {
      s.label(sup.gridUnlocked ? 'take the stations manual to change this' : 'locked until the six stages are done',
        L, 328, { size: 13, colour: CSS.faint });
    }

    dial(s, {
      x: R, y: 88, w: 400,
      label: 'ELECTRIC CARS IN TOWN',
      value: String(sup.fleetSize), unit: `of ${sup.fleetMax}`,
      frac: sup.fleetSize / sup.fleetMax,
      locked: !sup.sandbox,
      note: sup.sandbox ? null : 'locked until the six stages are done',
    });

    dial(s, {
      x: R, y: 190, w: 400,
      label: 'HOW HARD THE SAFETY LAYER TRIES',
      value: sup.marginPu.toFixed(3), unit: 'pu of band',
      frac: sup.marginPu / sup.marginMax,
      locked: !sup.sandbox || !sup.marginApplies,
      note: sup.marginApplies ? null : 'only Shielded RL has a safety layer to tighten',
    });

    // What the numbers on the board are, said plainly. A viewer who cannot tell a
    // replayed export from something computed in front of them has no way to weigh either.
    s.label(sup.live ? 'COMPUTED LIVE, HERE, AT THESE SETTINGS' : 'REPLAYING THE RECORDED EPISODES',
      R, 322, { size: 16, colour: sup.live ? CSS.amber : CSS.dim });
    s.label(sup.live ? 'the four controllers, re-decided every five minutes'
      : 'recorded episodes at 287 vehicles',
      R, 346, { size: 13, colour: CSS.faint });

    // The transport strip, given its own ground so the clock reads as an instrument
    // rather than as another setting.
    const ty = H - 74;
    s.ctx.fillStyle = '#131c25';
    s.ctx.fillRect(0, ty, W, 74);
    s.label(sup.clock, 18, ty + 44, { size: 38, colour: CSS.amber });
    s.label(sup.playing ? '▶ RUNNING' : '‖ HELD', 150, ty + 30, { size: 17, colour: sup.playing ? CSS.ok : CSS.dim });
    s.label(`SPEED  x${sup.speed}`, 150, ty + 56, { size: 17, colour: CSS.dim });
    s.label('/  HOLDS THE DAY', 330, ty + 30, { size: 15, colour: CSS.faint });
    s.label('SPACE RUNS IT · R RESETS', 330, ty + 56, { size: 15, colour: CSS.faint });
    s.label(sup.scoring ? 'SCORING THIS RUN' : 'NOT SCORED', W - 18, ty + 30,
      { size: 17, colour: sup.scoring ? CSS.ok : CSS.faint, align: 'right' });
    s.label(sup.scoring ? 'a dot will land on the map' : 'reset and play from 00:00 to score',
      W - 18, ty + 56, { size: 14, colour: CSS.faint, align: 'right' });
    s.done();
  }

  /* --------------------------------------------------- relay cabinets */

  const relayLeds = [];
  {
    for (let i = 0; i < 5; i++) {
      const x = ROOM.west + 1.6 + i * 1.5;
      const cab = new THREE.Mesh(new THREE.BoxGeometry(1.3, 2.2, 0.7), mat.cabinet);
      cab.position.set(x, 1.1, ROOM.south - 0.6);
      cab.castShadow = cab.receiveShadow = true;
      group.add(cab);
      solids.push({ x, z: ROOM.south - 0.6, w: 1.3, d: 0.7 });
      for (let j = 0; j < 3; j++) {
        const led = new THREE.Mesh(
          new THREE.SphereGeometry(0.045, 6, 5),
          new THREE.MeshBasicMaterial({ color: PALETTE.cool, toneMapped: false }),
        );
        led.position.set(x - 0.4 + j * 0.4, 1.75, ROOM.south - 0.96);
        group.add(led);
        relayLeds.push(led);
      }
    }
  }

  scene.add(group);

  /* ------------------------------------------------------------ redraw */

  const OK = new THREE.Color(PALETTE.cool);
  const BAD = new THREE.Color(PALETTE.sick);

  /**
   * Redrawing every screen on every simulated step costs about 1.1 million canvas
   * pixels and eight texture uploads, nine times a second — most of it discarded,
   * because the trend wall does not change when you nudge a slider and the terminal
   * only changes when somebody picks. Each screen carries a cheap signature of the
   * state it actually draws, and redraws only when that signature moves.
   *
   * The annunciator is not in here at all: it repaints from its own state changes
   * (a raised alarm, an acknowledgement, the flash tick) and nothing else touches it.
   */
  const sig = {};
  const changed = (key, value) => {
    if (sig[key] === value) return false;
    sig[key] = value;
    return true;
  };

  function redraw(state) {
    // Voltages move every step, so the board and consoles key off the step itself
    // plus anything a learner can change between steps.
    const step = `${state.frameIndex}|${state.runLabel}|${state.stationKw.join(',')}`;
    if (changed('mimic', `${step}|${state.source}|${state.served}|${state.short}|${state.youBus}|${state.inside}`)) drawMimic(state);
    if (changed('trend', `${state.frameIndex}|${state.runLabel}`)) drawTrend(state);
    // Keyed on the shortlist too: the stiff feeder swaps in a different set of candidates.
    if (changed('term', `${state.picked}|${(state.candidates ?? []).map((c) => c.label).join(',')}`)) drawTerminal(state);
    if (changed('sup', Object.values(state.sup).join('|'))) drawSupervisor(state);
    if (changed('map', state.dotsKey)) drawMap(state.dots);
    consoles.forEach((c) => {
      const own = `${state.stationKw[c.si]}|${state.manual[c.si]}|${state.plugged[c.si]}|${vMag[c.bus].toFixed(4)}`;
      if (changed('c' + c.si, own)) drawConsole(c, state);
    });

    // Relay panel LEDs: one per bus, red where the protection would be seeing an
    // undervoltage. Colour assignment is cheap enough not to be worth gating.
    relayLeds.forEach((led, i) => {
      const bus = i + 2;
      led.material.color.copy(bus <= N_BUS && vMag[bus] < BAND_LO ? BAD : OK);
    });
  }

  /** Forget the signatures, so the next redraw repaints everything. */
  function invalidate() { for (const k of Object.keys(sig)) delete sig[k]; }

  function setFlash(on) {
    if (alarmFlash === on) return;
    alarmFlash = on;
    drawAnnunciator();
  }

  const inside = (x, z) =>
    x > ROOM.west && x < ROOM.east && z > ROOM.north && z < ROOM.south;

  /** Where the day starts: standing back from the desk, facing the mimic board. */
  const spawn = { x: DESK.x + 3.4, y: EYE, z: DESK.z, yaw: Math.PI / 2 };

  return {
    redraw, invalidate, logEvent, ackAlarms, updateAlarms, alarmsPending, setFlash, drawSoe, drawMap,
    inside, spawn, consoles, desk: DESK, terminal, supervisor,
    terminalLayout: () => terminal.layout,
    // Every board, so the checks can assert where they hang. Two of the complaints this
    // room has attracted were sight-line complaints — the mimic's footer behind the
    // console lids, the annunciator's bottom row behind the relay cabinets — and a
    // sight line is a number, so it can be tested rather than re-eyeballed.
    screens: { mimic, annun, trend, soe, map: mapScreen, supervisor },
    // Two points on the console's normal: the face you have to be near to reach it, and
    // the spot to stand on, far enough back that the whole board is in view at once.
    supervisorFace: { x: ROOM.x - 6.2, z: ROOM.north + 2.0 },
    supervisorSpot: { x: ROOM.x - 6.2, z: ROOM.north + 4.6 },
    events,
  };
}
