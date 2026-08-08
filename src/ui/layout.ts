/**
 * Where each bus sits on screen.
 *
 * The village is not a decorative map — its geometry is the feeder's. Distance across
 * the screen is electrical distance from the substation, so the fact that the lights
 * fail at the far end is something the learner reads off the picture before anyone
 * explains a voltage profile to them.
 *
 * Positions come from walking the network tree: depth becomes the column, and every
 * time the trunk branches, the new lateral gets its own lane.
 */

import { BRANCHES, N_BUS } from '../sim/network.js';

export interface BusPlace {
  bus: number;
  /** Electrical depth from the substation. */
  col: number;
  /** Lateral lane. Zero is the main trunk. */
  row: number;
  /** Isometric screen position in abstract units, before fitting to the canvas. */
  ix: number;
  iy: number;
  /** How many dwellings to draw at this pole, from its nominal load. */
  houses: number;
}

const TILE_W = 2;
const TILE_H = 1;

/**
 * Lanes are handed out alternating either side of the trunk, so laterals fan out
 * symmetrically instead of all stacking below it.
 */
function laneSequence(): () => number {
  let n = 0;
  return () => {
    n++;
    const magnitude = Math.ceil(n / 2);
    return n % 2 === 1 ? magnitude : -magnitude;
  };
}

export function buildLayout(nominalLoadKw: readonly number[]): BusPlace[] {
  const children = new Map<number, number[]>();
  for (const branch of BRANCHES) {
    const list = children.get(branch.from) ?? [];
    list.push(branch.to);
    children.set(branch.from, list);
  }

  const places: BusPlace[] = [];
  const nextLane = laneSequence();

  // Iterative depth-first walk from bus 1, so the trunk is laid down before laterals.
  const stack: { bus: number; col: number; row: number }[] = [{ bus: 1, col: 0, row: 0 }];
  while (stack.length > 0) {
    const node = stack.pop()!;
    const load = nominalLoadKw[node.bus] ?? 0;
    places.push({
      bus: node.bus,
      col: node.col,
      row: node.row,
      ix: (node.col - node.row) * (TILE_W / 2),
      iy: (node.col + node.row) * (TILE_H / 2),
      houses: load <= 0 ? 0 : Math.max(1, Math.min(4, Math.round(load / 60))),
    });

    const kids = children.get(node.bus) ?? [];
    // Push in reverse so the first child is processed first and keeps the trunk lane.
    for (let i = kids.length - 1; i >= 0; i--) {
      const row = i === 0 ? node.row : nextLane();
      stack.push({ bus: kids[i], col: node.col + 1, row });
    }
  }

  places.sort((a, b) => a.bus - b.bus);
  if (places.length !== N_BUS) {
    throw new Error(`laid out ${places.length} buses, expected ${N_BUS}`);
  }
  return places;
}

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export function layoutBounds(places: readonly BusPlace[]): Bounds {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of places) {
    minX = Math.min(minX, p.ix);
    maxX = Math.max(maxX, p.ix);
    minY = Math.min(minY, p.iy);
    maxY = Math.max(maxY, p.iy);
  }
  return { minX, maxX, minY, maxY };
}

/**
 * Voltage rendered as light.
 *
 * Nothing about "0.9425 pu" is legible to most people. A street going dark is legible
 * to everyone, so the village carries the stakes and lets the console carry the
 * precision. The mapping is deliberately steep across the statutory limit: the drop
 * from 0.95 to 0.93 has to *look* like something going wrong.
 */
export function brightnessFor(vPu: number): number {
  const lo = 0.86;
  const hi = 0.99;
  const t = (vPu - lo) / (hi - lo);
  return Math.max(0, Math.min(1, t)) ** 1.6;
}

/** Below the statutory floor, lamps start to flicker. Deeper sags flicker harder. */
export function flickerFor(vPu: number, timeMs: number, bus: number): number {
  if (vPu >= 0.95) return 0;
  const severity = Math.min(1, (0.95 - vPu) / 0.05);
  const phase = timeMs / 90 + bus * 1.7;
  const noise = Math.sin(phase) * Math.sin(phase * 2.3 + 1.1) * Math.sin(phase * 0.7);
  return severity * Math.max(0, noise) * 0.55;
}
