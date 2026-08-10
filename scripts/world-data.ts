/**
 * Export the town, and enough of the network for the viewer to solve it itself.
 *
 * Two kinds of thing come out of here. The geometry and the day — bus positions from
 * walking the feeder tree, and the background load and solar at each captured step.
 * And the record — what each of four controllers actually commanded, step by step,
 * living through that same day.
 *
 * What is deliberately *not* exported is the bus voltages. A walkable world has to
 * answer when somebody changes something, and a table of recorded voltages cannot.
 * So the branch impedances go out instead and the viewer runs the same
 * backward/forward sweep, with the recorded scalars carried along so its answers can
 * be checked against the engine rather than trusted.
 *
 *   npx tsx scripts/world-data.ts > world.json
 */

import {
  BRANCHES,
  KW_PER_PU,
  NOMINAL_LOAD_KVAR,
  NOMINAL_LOAD_KW,
  N_BUS,
  PV_BUSES,
  STATION_BUSES,
  WEAK_SOURCE,
  Z_BASE_OHM,
  nominalLoadPu,
} from '../src/sim/network.js';
import type { GridKind } from '../src/sim/network.js';
import { LiveSim, PV_CAPACITY_KW } from '../src/sim/live.js';
import { droop, placeholderController, uncoordinated } from '../src/sim/controllers.js';
import type { Controller } from '../src/sim/controllers.js';
import { STEPS_PER_DAY, HOURS_PER_STEP, clockOf, clearSkyFraction, loadShape } from '../src/sim/profiles.js';
import {
  buildFleet, MAX_CHARGE_KW, MAX_DISCHARGE_KW, CHARGER_EFFICIENCY, SOC_FLOOR_DISCHARGE,
} from '../src/sim/fleet.js';
import { PLACES } from '../src/ui/layout.js';

const SCENARIO = { grid: 'weak' as const, loadScale: 0.5, seed: 137710 };

/**
 * The same day on the canonical stiff feeder — identical loads, identical fleet, zero
 * substation impedance.
 *
 * This has to be run, not replayed. Droop reacts to its own local voltage, so its
 * commands on a stiff grid are genuinely different commands; taking the weak-grid
 * record and re-solving it against a stiffer source would show you a controller that
 * never existed. Only the loads are shared between the two, because loads do not care
 * what is upstream of them.
 */
const SCENARIO_STRONG = { ...SCENARIO, grid: 'strong' as const };

/** The same fleet LiveSim builds, from the same seed. Deterministic, so this matches. */
const FLEET = buildFleet({ seed: SCENARIO.seed, stationCount: STATION_BUSES.length });
/**
 * Every step, not every other one.
 *
 * The display only needs 144 frames a day to look smooth, and that is what this used
 * to export. But the viewer now scores a learner's own run by walking the fleet, and
 * the engine walks it 288 times; scoring at half resolution would put an approximate
 * dot on the same chart as exact ones. The viewer advances two frames per tick so the
 * day still takes about the same wall-clock time.
 */
const FRAME_STRIDE = 1;

const sacLag = placeholderController({
  id: 'sac-lag',
  label: 'SAC-Lag (plain deep RL)',
  eagerness: 0.85,
  backoffPu: 0.952,
  arbitrage: true,
  usesProjection: false,
});

const safeSac = placeholderController({
  id: 'safesac',
  label: 'SafeSAC',
  eagerness: 0.95,
  backoffPu: 0.948,
  arbitrage: false,
  usesProjection: true,
});

/**
 * The stage-6 trap, matching `sacLagShifted` in the app: an agent trained on a stiff
 * grid and deployed on this one. It posts the best safety score on the board and is
 * the only candidate that turns a profit, because it declines to charge anybody.
 *
 * It is exported so the walkable build can put the same procurement decision in front
 * of a learner. It is a candidate on the terminal, never a run you can drive — the
 * whole lesson is that its numbers look best right up until you read the second column.
 */
const sacLagShifted = placeholderController({
  id: 'sac-lag-shift',
  label: 'SAC-Lag (trained on a strong grid)',
  eagerness: 0,
  backoffPu: 0.9,
  arbitrage: true,
  usesProjection: false,
});


/**
 * The background the feeder sits on at each captured step: base load times the day's
 * shape, less whatever the rooftop solar is making. Exported once rather than per
 * controller, because it does not depend on who is driving — and exported at all so
 * the viewer can re-solve the network itself when a learner changes something,
 * instead of being limited to replaying what was recorded.
 */
function captureDay() {
  const frames: unknown[] = [];
  for (let step = 0; step < STEPS_PER_DAY; step += FRAME_STRIDE) {
    const { p, q } = nominalLoadPu(loadShape(step) * SCENARIO.loadScale);
    const solar = clearSkyFraction(step) * PV_CAPACITY_KW;
    for (const bus of PV_BUSES) p[bus] -= solar / KW_PER_PU;
    frames.push({
      t: step,
      clock: clockOf(step),
      p: Array.from(p.slice(0, N_BUS + 1), (x) => Number(x.toFixed(7))),
      q: Array.from(q.slice(0, N_BUS + 1), (x) => Number(x.toFixed(7))),
      solar: Number(solar.toFixed(1)),
    });
  }
  return frames;
}

/** Widened past the literal type of SCENARIO so the stiff-grid scenario also fits. */
type Scenario = { grid: GridKind; loadScale: number; seed: number };

function capture(controller: Controller, projection: boolean, scenario: Scenario = SCENARIO) {
  const sim = new LiveSim(scenario);
  controller.reset?.();
  const frames: unknown[] = [];

  while (!sim.finished) {
    const step = sim.step;
    const plugged = sim.capabilities.map((c) => c.connected);
    const record = sim.advanceWith(controller, projection);
    if (step % FRAME_STRIDE !== 0) continue;

    frames.push({
      t: step,
      clock: clockOf(step),
      // Three decimals, not one: these commands are replayed through the fleet to score
      // a run, and a tenth of a kilowatt per station per step accumulates.
      kw: record.safeKw.map((k) => Number(k.toFixed(3))),
      plugged,
      // Recorded scalars, kept so the viewer's own solver can be checked against
      // the engine that produced them rather than trusted.
      loss: Number(record.lossKw.toFixed(2)),
      viol: record.violations,
      vmin: Number(record.vMin.toFixed(4)),
      vminBus: record.vMinBus,
    });
  }

  const totals = sim.finalTotals();
  return {
    id: controller.id,
    label: controller.label,
    provenance: controller.provenance,
    projection,
    violationRate: Number(totals.violationRate.toFixed(4)),
    socMet: Number(totals.socMet.toFixed(4)),
    totalLossKwh: Number(totals.totalLossKwh.toFixed(1)),
    netCostUsd: Number(totals.netCostUsd.toFixed(0)),
    vMinPu: Number(totals.vMinPu.toFixed(4)),
    frames,
  };
}

const world = {
  note: 'Generated by scripts/world-data.ts from the IEEE 33-bus weak feeder. Do not hand-edit.',
  scenario: SCENARIO,
  stepsPerDay: STEPS_PER_DAY,
  frameStride: FRAME_STRIDE,
  places: PLACES.map((p) => ({
    bus: p.bus,
    col: p.col,
    row: p.row,
    houses: p.houses,
    kw: NOMINAL_LOAD_KW[p.bus],
    kvar: NOMINAL_LOAD_KVAR[p.bus],
  })),
  // Resistance travels with the branch so the viewer can turn a current into the
  // heat actually going into that conductor, which is the quantity the
  // sustainability story is about.
  branches: BRANCHES.map((b) => ({
    from: b.from,
    to: b.to,
    rPu: Number((b.rOhm / Z_BASE_OHM).toFixed(7)),
    xPu: Number((b.xOhm / Z_BASE_OHM).toFixed(7)),
  })),
  /** Substation source impedance, so the viewer builds the same weak feeder. */
  source: {
    rPu: Number((WEAK_SOURCE.rOhm / Z_BASE_OHM).toFixed(7)),
    xPu: Number((WEAK_SOURCE.xOhm / Z_BASE_OHM).toFixed(7)),
  },
  kwPerPu: KW_PER_PU,
  /**
   * The fleet itself, and the constants that govern it.
   *
   * Exported so the viewer can score a learner's own run the way the engine scores
   * one — counting vehicles that reached their target state of charge — instead of
   * inventing a service metric that happens to be computable from what was already
   * here. Two hundred and eighty-seven vehicles is a few kilobytes; a fabricated
   * denominator would cost the entry its credibility.
   */
  // Full precision, deliberately. Service is scored by `soc >= targetSoc - 1e-6`, so a
  // target rounded to four decimals carries an error fifty times the tolerance it is
  // compared against, and one vehicle in 287 lands on the wrong side of it.
  fleet: FLEET.map((v) => ({
    s: v.station,
    cap: v.capacityKwh,
    a: v.arrivalStep,
    d: v.departureStep,
    soc0: v.arrivalSoc,
    tgt: v.targetSoc,
    v2g: v.v2gEnabled ? 1 : 0,
  })),
  fleetConstants: {
    maxChargeKw: MAX_CHARGE_KW,
    maxDischargeKw: MAX_DISCHARGE_KW,
    chargerEfficiency: CHARGER_EFFICIENCY,
    socFloorDischarge: SOC_FLOOR_DISCHARGE,
    hoursPerStep: HOURS_PER_STEP,
  },
  day: captureDay(),
  stations: STATION_BUSES,
  pv: PV_BUSES,
  runs: [
    capture(uncoordinated, false),
    capture(droop, false),
    capture(sacLag, false),
    capture(safeSac, true),
  ],
  /**
   * The same four controllers living through the same day on the stiff feeder. The
   * viewer switches to these when the grid is switched, and drops the source impedance
   * to zero to match — so what it shows is what those controllers actually did there.
   */
  runsStrong: [
    capture(uncoordinated, false, SCENARIO_STRONG),
    capture(droop, false, SCENARIO_STRONG),
    capture(sacLag, false, SCENARIO_STRONG),
    capture(safeSac, true, SCENARIO_STRONG),
  ],
  /** The stage-6 shortlist, rerun on the grid the shifted agent was trained for. */
  candidatesStrong: [droop, sacLag, safeSac, sacLagShifted].map((c) => {
    const r = capture(c, c.id === 'safesac', SCENARIO_STRONG);
    return {
      id: r.id, label: r.label, provenance: r.provenance,
      violationRate: r.violationRate, socMet: r.socMet,
      totalLossKwh: r.totalLossKwh, netCostUsd: r.netCostUsd, vMinPu: r.vMinPu,
    };
  }),
  /**
   * The stage-6 shortlist. Uncoordinated is not on it — nobody procures "no
   * controller" — and the shifted agent is, which is what makes the table a trap.
   * Totals only: this one is read, not driven.
   */
  candidates: [droop, sacLag, safeSac, sacLagShifted].map((c) => {
    const r = capture(c, c.id === 'safesac');
    return {
      id: r.id, label: r.label, provenance: r.provenance,
      violationRate: r.violationRate, socMet: r.socMet,
      totalLossKwh: r.totalLossKwh, netCostUsd: r.netCostUsd, vMinPu: r.vMinPu,
    };
  }),
};

console.log(JSON.stringify(world));
