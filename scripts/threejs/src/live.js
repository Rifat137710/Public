/**
 * The day, computed here instead of replayed.
 *
 * The city ships with four recorded episodes — one per controller, exported from the
 * source evaluation at 287 vehicles. Replaying them is the right thing for the six stages,
 * because a stage that asks you to compare controllers has to compare the published ones.
 *
 * But a recording cannot answer a question it was not asked. "What happens with a hundred
 * cars?" and "what if the safety layer tried harder?" are exactly the two questions the
 * lesson page lets a reader put to the simulator, and the control room could not put them
 * at all: droop backs off as its own voltage falls, so its recorded commands are not the
 * commands it would issue to a smaller fleet. Replaying them at another fleet size does
 * not show a smaller town — it shows a controller that never existed.
 *
 * So when a setting moves off what was recorded, the day is computed. Not by a second
 * implementation: `shared/control.js` is the same module the lesson runs, so the four
 * controllers in here are the four controllers there, and the safety projection is the
 * real one solved against sensitivities measured on the live feeder every step.
 *
 * A whole day costs about 40 ms for a rule and about 190 ms for Shielded RL, which pays for
 * ten power flows a step — one to see, eight to measure the sensitivities, one to
 * dispatch. That is why the caller caches, and why only the controller actually driving
 * is built until something asks for the others.
 */

import { WORLD, solveAt, sensitivitiesAt, vMag } from '../../shared/grid.js';
import { FleetRun } from '../../shared/fleet.js';
import { byId, safeSacWithMargin, MARGIN_PU } from '../../shared/control.js';
import { priceAt } from '../../shared/price.js';

export const CONTROLLER_IDS = ['uncoordinated', 'droop', 'sac-lag', 'safesac'];

/**
 * Service, counted two ways.
 *
 * `met` is every vehicle at or above the charge it came for, whether it has left or is
 * still on the cable. `short` is the harder number: vehicles that have already unplugged
 * and driven off below target. It counts departures only, because a car still charging
 * has not failed yet — and once it has gone, the outcome is final and cannot improve.
 *
 * The two do not sum to the fleet until the last vehicle leaves at 23:55. In between,
 * the remainder is the cars still plugged in with work left to do.
 */
export function tally(fleet) {
  let met = 0;
  let short = 0;
  for (let i = 0; i < fleet.vehicles.length; i++) {
    const s = fleet.state[i];
    const target = fleet.vehicles[i].targetSoc - 1e-6;
    if ((s.departedSoc ?? s.soc) >= target) met++;
    else if (s.departedSoc !== null) short++;
  }
  return { met, short };
}

/**
 * One controller's whole day, in the frame shape the city's instruments already read.
 *
 * `dayAt(step)` is supplied by the caller rather than read from `WORLD` directly, because
 * the town can be scaled and the scaling has to reach the controller: a droop curve that
 * saw the unscaled load would issue commands for a town that is not the one on screen.
 *
 * The grid must already be set by the caller. Switching it in here would leave the shared
 * solver on whichever feeder happened to be built last, which is the kind of bug that
 * shows up three interactions later as a voltage nobody can account for.
 */
export function buildLiveDay(controllerId, { size, dayAt, marginPu = MARGIN_PU }) {
  const controller = controllerId === 'safesac' ? safeSacWithMargin(marginPu) : byId(controllerId);
  const fleet = new FleetRun(size);
  const frames = [];
  let last = [0, 0, 0, 0];

  for (let step = 0; step < WORLD.day.length; step++) {
    fleet.updateConnections(step);
    const day = dayAt(step);

    // The voltages a controller reads are the ones standing before it acts — last step's
    // command, this step's load — which is what a real one has to work with.
    solveAt(day, last);
    const seen = Float64Array.from(vMag);
    const caps = fleet.capabilities();

    const ctx = { step, voltages: seen, caps, price: priceAt(step), day };
    if (controller.projection) ctx.sens = sensitivitiesAt(day, last);

    // Whatever the controller asks for, the cars still cannot take more than they can.
    const kw = fleet.clampToFleet(controller.command(ctx));
    const solution = solveAt(day, kw);
    fleet.record(solution);
    for (let k = 0; k < 4; k++) fleet.dispatchStation(k, kw[k]);
    last = kw;

    const { met, short } = tally(fleet);

    frames.push({
      t: step,
      clock: day.clock,
      kw: kw.slice(),
      plugged: caps.map((c) => c.connected),
      loss: solution.lossKw,
      viol: solution.violations,
      vmin: solution.vMin,
      vminBus: solution.vMinBus,
      met,
      short,
      drawKw: kw.reduce((a, b) => a + Math.max(0, -b), 0),
    });
  }

  const totals = fleet.totals();
  return {
    id: controllerId,
    label: byId(controllerId).label,
    // Not `placeholder` and not `rule`: computed here, now, at settings no export covers.
    // The instruments say so, because a number a viewer cannot source is a number they
    // are entitled to distrust.
    provenance: 'live',
    frames,
    fleetSize: totals.fleetSize,
    driversMet: totals.driversMet,
    socMet: totals.socMet,
    violationRate: totals.violationRate,
    totalLossKwh: totals.totalLossKwh,
    vMinPu: totals.vMinPu,
  };
}

/**
 * How many of the fleet had reached their target charge at each step of a *recorded* day.
 *
 * The exported frames carry voltages, commands and plugged counts but not service, and
 * the mimic board now shows service. Rather than re-export, the recorded commands are
 * pushed through the same fleet accounting the live path uses — which needs no power flow
 * at all, because moving energy into a battery does not depend on the voltage that
 * delivered it. That makes this about two milliseconds rather than two hundred.
 */
export function metSeries(frames, size) {
  const fleet = new FleetRun(size);
  const met = new Int16Array(frames.length);
  const short = new Int16Array(frames.length);
  for (let step = 0; step < frames.length; step++) {
    fleet.updateConnections(step);
    const kw = frames[step].kw;
    for (let k = 0; k < 4; k++) fleet.dispatchStation(k, kw[k]);
    const t = tally(fleet);
    met[step] = t.met;
    short[step] = t.short;
  }
  return { met, short };
}
