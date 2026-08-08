/**
 * Drawing the village.
 *
 * Everything here is procedural — poles, spans, houses, chargers and panels are drawn
 * from primitives, so the whole scene costs nothing to download and scales to any
 * canvas size. No sprite sheets, no image assets.
 */

import { PV_BUSES, STATION_BUSES } from '../sim/network.js';
import { brightnessFor, flickerFor, layoutBounds, type BusPlace } from './layout.js';

export interface VillageFrame {
  places: readonly BusPlace[];
  /** Bus voltages, pu, indexed by node. */
  voltages: Float64Array;
  /** Executed station commands, kW, injection positive. */
  stationKw: readonly number[];
  /** Solar output per PV bus, kW. */
  solarKw: number;
  /** Fraction of a day elapsed, for the sky. */
  dayFraction: number;
  timeMs: number;
  /** Bus the console is currently highlighting, if any. */
  focusBus: number | null;
}

const SKY_NIGHT = '#0A0E14';
const SKY_DAY = '#1B2733';
const GROUND_NIGHT = '#0D1219';
const GROUND_DAY = '#17202A';

function mix(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const out = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return `rgb(${out[0]}, ${out[1]}, ${out[2]})`;
}

/** How much daylight there is, 0 at midnight and 1 at noon. */
function daylight(dayFraction: number): number {
  const hour = dayFraction * 24;
  if (hour < 5 || hour > 20) return 0;
  return Math.max(0, Math.sin((Math.PI * (hour - 5)) / 15)) ** 0.7;
}

export function drawVillage(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  frame: VillageFrame,
): void {
  const light = daylight(frame.dayFraction);
  const bounds = layoutBounds(frame.places);

  const padX = 46;
  const padTop = 30;
  const padBottom = 54;
  const spanX = bounds.maxX - bounds.minX || 1;
  const spanY = bounds.maxY - bounds.minY || 1;
  // Scale the axes independently so the feeder fills the panel. A uniform scale
  // letterboxes badly at wide aspect ratios and wastes the space the village needs to
  // read as a place rather than a diagram; the vertical stretch is capped so the
  // laterals never separate into unrelated stripes.
  const scaleX = (width - padX * 2) / spanX;
  const scaleY = Math.min(
    (height - padTop - padBottom) / spanY,
    scaleX * 1.9,
  );
  const offsetX = padX - bounds.minX * scaleX;
  const offsetY = padTop - bounds.minY * scaleY;

  const px = (p: BusPlace): number => offsetX + p.ix * scaleX;
  const py = (p: BusPlace): number => offsetY + p.iy * scaleY;

  // Sky and ground.
  const sky = ctx.createLinearGradient(0, 0, 0, height);
  sky.addColorStop(0, mix(SKY_NIGHT, SKY_DAY, light));
  sky.addColorStop(1, mix(GROUND_NIGHT, GROUND_DAY, light));
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, width, height);

  // Spans first, so poles and houses sit on top of the wires.
  ctx.lineWidth = 1.2;
  for (const place of frame.places) {
    if (place.bus === 1) continue;
    const parent = findParent(frame.places, place);
    if (!parent) continue;
    const v = frame.voltages[place.bus] ?? 1;
    ctx.strokeStyle = v < 0.95 ? 'rgba(190, 90, 74, 0.42)' : 'rgba(120, 148, 160, 0.30)';
    ctx.beginPath();
    ctx.moveTo(px(parent), py(parent) - 20);
    ctx.lineTo(px(place), py(place) - 20);
    ctx.stroke();
  }

  // Draw far rows first so nearer ones overlap correctly.
  const ordered = [...frame.places].sort((a, b) => a.iy - b.iy || a.ix - b.ix);

  for (const place of ordered) {
    const x = px(place);
    const y = py(place);
    const v = frame.voltages[place.bus] ?? 1;
    const isStation = STATION_BUSES.includes(place.bus);
    const isPv = PV_BUSES.includes(place.bus);

    drawHouses(ctx, x, y, place, v, light, frame.timeMs);
    drawPole(ctx, x, y, v);

    if (isPv && frame.solarKw > 0) drawPanel(ctx, x, y, frame.solarKw);
    if (isStation) {
      const k = STATION_BUSES.indexOf(place.bus);
      drawCharger(ctx, x, y, frame.stationKw[k] ?? 0, place.bus === frame.focusBus);
    }
    if (place.bus === 1) drawSubstation(ctx, x, y);
  }

  drawLegend(ctx, width, height);
}

function findParent(places: readonly BusPlace[], place: BusPlace): BusPlace | undefined {
  // The parent is the neighbour one column closer to the substation on a connected lane.
  let best: BusPlace | undefined;
  let bestDistance = Infinity;
  for (const other of places) {
    if (other.col !== place.col - 1) continue;
    const d = Math.abs(other.row - place.row);
    if (d < bestDistance) {
      bestDistance = d;
      best = other;
    }
  }
  return best;
}

function drawPole(ctx: CanvasRenderingContext2D, x: number, y: number, v: number): void {
  ctx.strokeStyle = v < 0.95 ? 'rgba(198, 106, 88, 0.75)' : 'rgba(126, 148, 158, 0.62)';
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x, y - 22);
  ctx.moveTo(x - 5, y - 19);
  ctx.lineTo(x + 5, y - 19);
  ctx.stroke();
}

function drawHouses(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  place: BusPlace,
  v: number,
  light: number,
  timeMs: number,
): void {
  const brightness = Math.max(
    0,
    brightnessFor(v) - flickerFor(v, timeMs, place.bus),
  );

  for (let i = 0; i < place.houses; i++) {
    const hx = x + 9 + i * 11;
    const hy = y + 2 + (i % 2) * 4;
    const w = 8;
    const h = 6;

    // Body, lit a little by daylight so the village is legible at noon.
    ctx.fillStyle = mix('#1A222B', '#3B4854', light * 0.8);
    ctx.fillRect(hx, hy - h, w, h);

    // Roof.
    ctx.fillStyle = mix('#141B22', '#2C3742', light * 0.8);
    ctx.beginPath();
    ctx.moveTo(hx - 1, hy - h);
    ctx.lineTo(hx + w / 2, hy - h - 4);
    ctx.lineTo(hx + w + 1, hy - h);
    ctx.closePath();
    ctx.fill();

    // The window. This is the whole point of the picture.
    if (brightness > 0.02) {
      const glow = 0.25 + brightness * 0.75;
      ctx.fillStyle = `rgba(255, 206, 132, ${glow})`;
      ctx.fillRect(hx + 2, hy - h + 2, 3, 3);
      if (brightness > 0.45) {
        ctx.save();
        ctx.globalAlpha = (brightness - 0.45) * 0.5;
        ctx.fillStyle = '#FFCE84';
        ctx.beginPath();
        ctx.arc(hx + 3.5, hy - h + 3.5, 7, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    } else {
      ctx.fillStyle = 'rgba(38, 30, 24, 0.9)';
      ctx.fillRect(hx + 2, hy - h + 2, 3, 3);
    }
  }
}

function drawPanel(ctx: CanvasRenderingContext2D, x: number, y: number, solarKw: number): void {
  const intensity = Math.min(1, solarKw / 250);
  ctx.save();
  ctx.translate(x - 16, y - 2);
  ctx.fillStyle = `rgba(96, 150, 190, ${0.35 + intensity * 0.5})`;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(9, -4);
  ctx.lineTo(13, -1);
  ctx.lineTo(4, 3);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawCharger(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  commandKw: number,
  focused: boolean,
): void {
  const charging = commandKw < -0.5;
  const discharging = commandKw > 0.5;
  const magnitude = Math.min(1, Math.abs(commandKw) / 200);

  // Pedestal.
  ctx.fillStyle = focused ? '#E4EAEE' : '#8FA3AF';
  ctx.fillRect(x - 3, y - 12, 6, 12);

  if (charging || discharging) {
    const colour = charging ? '80, 170, 255' : '104, 214, 168';
    ctx.save();
    ctx.globalAlpha = 0.18 + magnitude * 0.5;
    const glow = ctx.createRadialGradient(x, y - 8, 1, x, y - 8, 26 + magnitude * 18);
    glow.addColorStop(0, `rgba(${colour}, 0.9)`);
    glow.addColorStop(1, `rgba(${colour}, 0)`);
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y - 8, 26 + magnitude * 18, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  if (focused) {
    ctx.strokeStyle = 'rgba(228, 234, 238, 0.8)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.arc(x, y - 8, 18, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawSubstation(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  ctx.strokeStyle = 'rgba(180, 200, 212, 0.85)';
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  ctx.moveTo(x - 10, y);
  ctx.lineTo(x, y - 30);
  ctx.lineTo(x + 10, y);
  ctx.moveTo(x - 6, y - 12);
  ctx.lineTo(x + 6, y - 12);
  ctx.stroke();
}

function drawLegend(ctx: CanvasRenderingContext2D, width: number, height: number): void {
  ctx.save();
  ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
  ctx.fillStyle = 'rgba(150, 170, 182, 0.85)';
  ctx.textBaseline = 'bottom';

  ctx.fillText('substation', 20, height - 34);
  ctx.textAlign = 'right';
  ctx.fillText('feeder end — bus 18', width - 20, height - 34);
  ctx.textAlign = 'left';

  // The arrow of electrical distance, which is the scene's organising idea.
  ctx.strokeStyle = 'rgba(120, 140, 152, 0.4)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(20, height - 26);
  ctx.lineTo(width - 20, height - 26);
  ctx.stroke();

  ctx.fillStyle = 'rgba(120, 140, 152, 0.75)';
  ctx.fillText('electrical distance from the substation', 20, height - 10);
  ctx.restore();
}
