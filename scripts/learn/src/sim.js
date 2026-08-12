/**
 * One simulated day, and everything the page needs to draw it.
 *
 * A controller is asked for a command at every five-minute step, the fleet is dispatched
 * at whatever it commanded, and the feeder is solved. Nothing is scripted: change the
 * number of cars or the strength of the line and every controller genuinely re-decides.
 *
 * The whole day is run up front rather than stepped in the animation loop. It costs
 * about forty milliseconds, and it means scrubbing the time slider is instant and the
 * scoreboard can show all four controllers on the day you are actually looking at.
 */

import { WORLD, setGrid, solveAt, sensitivitiesAt, vMag, N_NODE } from '../../shared/grid.js';
import { FleetRun, FLEET_SIZE } from '../../shared/fleet.js';
import { CONTROLLERS, byId, safeSacWithMargin, MARGIN_PU } from '../../shared/control.js';
import { priceAt, priceTier } from '../../shared/price.js';

export { CONTROLLERS, byId, FLEET_SIZE, WORLD, MARGIN_PU, priceAt, priceTier };

export const STEPS = WORLD.day.length;

/**
 * The margins the sweep reports, in per unit.
 *
 * Chosen to straddle the turn rather than to sample evenly: nothing interesting happens
 * between 0.030 and 0.045 except the end state, and the two steps either side of the
 * thesis's 0.010 are where the curve stops being monotonic and starts costing on both
 * axes at once. The last entry is there because it is the one a reader remembers.
 */
export const MARGINS = [0, 0.005, 0.010, 0.015, 0.020, 0.030, 0.045];

const marginCache = new Map();

/**
 * SafeSAC's whole day at each margin, for a given town.
 *
 * Computed on demand and never as part of `sync`. The scoreboard already runs four full
 * days on every slider move; adding seven more to the same path turned dragging the
 * fleet size into a slideshow, and this is a thing a reader chooses to look at rather
 * than something that has to be true before the page can be drawn.
 */
export function marginSweep(size = FLEET_SIZE, grid = 'weak') {
  const key = `${size}|${grid}`;
  const hit = marginCache.get(key);
  if (hit) return hit;

  const rows = MARGINS.map((marginPu) => {
    const t = runDay(safeSacWithMargin(marginPu), { size, grid }).totals;
    return {
      marginPu,
      driversMet: t.driversMet,
      fleetSize: t.fleetSize,
      violationRate: t.violationRate,
      vMinPu: t.vMinPu,
    };
  });
  marginCache.set(key, rows);
  return rows;
}

export function runDay(controller, { size = FLEET_SIZE, grid = 'weak' } = {}) {
  setGrid(grid);
  const fleet = new FleetRun(size);
  const steps = [];
  let last = [0, 0, 0, 0];

  for (let step = 0; step < STEPS; step++) {
    fleet.updateConnections(step);
    const day = WORLD.day[step];

    // The voltages a controller reads are the ones standing before it acts, which is
    // what a real one has: last step's command, this step's load.
    solveAt(day, last);
    const seen = Float64Array.from(vMag);
    const caps = fleet.capabilities();

    const ctx = { step, voltages: seen, caps, price: priceAt(step), day };
    // Measured about last step's command, and the projection is told so — the linear
    // model only means anything relative to the point it was taken about. Re-measuring
    // about the new command and projecting again was tried and moves the day's result
    // by 0.01 percentage points for twice the power flows, so it is not done.
    if (controller.projection) ctx.sens = sensitivitiesAt(day, last);

    // Whatever the controller asks for, the cars still cannot take more than they can.
    const kw = fleet.clampToFleet(controller.command(ctx));
    const solution = solveAt(day, kw);
    fleet.record(solution);
    for (let k = 0; k < 4; k++) fleet.dispatchStation(k, kw[k]);
    last = kw;

    const v = new Float32Array(N_NODE);
    for (let n = 0; n < N_NODE; n++) v[n] = vMag[n];

    let met = 0, plugged = 0;
    for (let i = 0; i < fleet.vehicles.length; i++) {
      const s = fleet.state[i];
      if (s.connected) plugged++;
      if ((s.departedSoc ?? s.soc) >= fleet.vehicles[i].targetSoc - 1e-6) met++;
    }

    steps.push({
      clock: day.clock,
      v,
      kw: kw.slice(),
      drawKw: kw.reduce((a, b) => a + Math.max(0, -b), 0),
      injectKw: kw.reduce((a, b) => a + Math.max(0, b), 0),
      viol: solution.violations,
      vMin: solution.vMin,
      vMinBus: solution.vMinBus,
      lossKw: solution.lossKw,
      met,
      plugged,
    });
  }

  setGrid('weak');
  return { steps, totals: fleet.totals(), controller };
}

/**
 * Runs are cached by everything that can change one. Four controllers over a full day
 * is roughly a sixth of a second, so a slider drag would otherwise redo it far more
 * often than a person can read the result.
 */
const cache = new Map();

export function dayFor(controllerId, size, grid) {
  const key = `${controllerId}|${size}|${grid}`;
  let hit = cache.get(key);
  if (!hit) {
    hit = runDay(byId(controllerId), { size, grid });
    if (cache.size > 60) cache.clear();
    cache.set(key, hit);
  }
  return hit;
}

export function allFor(size, grid) {
  return CONTROLLERS.map((c) => dayFor(c.id, size, grid));
}
