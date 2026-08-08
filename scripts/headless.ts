/**
 * Headless validation harness.
 *
 * Runs three operator strategies through the default scenario and prints the
 * outcome of each. This exists to answer two questions before any UI is built:
 *
 *   1. Are the physics sane? (frequency, energy balance, cost, carbon)
 *   2. Does the simulation actually reward the behaviour it means to teach?
 *
 * If the careless strategy survives the 18:40 islanding, the lesson is broken
 * and the scenario needs retuning.
 */

import { createInitialState, defaultCommand, scoreRun, step } from '../src/sim/engine';
import { DEFAULT_SCENARIO } from '../src/sim/scenario';
import { SECONDS_PER_DAY, type DispatchCommand, type SimState } from '../src/sim/types';

type Policy = (state: SimState, cmd: DispatchCommand) => void;

const H = 3600;
const hhmm = (t: number) =>
  `${String(Math.floor(t / H)).padStart(2, '0')}:${String(Math.floor((t % H) / 60)).padStart(2, '0')}`;

/** A: no intervention at all. The battery idles and the genset never starts. */
const doNothing: Policy = () => {};

/**
 * B: plausible but shallow. Uses the battery for evening peak shaving to save
 * money, but leaves it grid-following and never starts the diesel machine.
 */
const naive: Policy = (state, cmd) => {
  const hour = state.t / H;
  if (hour >= 10 && hour < 15) cmd.batteryPowerKw = -600; // soak up midday solar
  else if (hour >= 18 && hour < 22) cmd.batteryPowerKw = 1400; // shave the peak
  else cmd.batteryPowerKw = 0;
  cmd.batteryGridForming = false;
  cmd.gensetRunRequested = false;
};

/**
 * C: what the simulation is trying to teach. Charge on cheap overnight and
 * midday solar, hold reserve into the evening, put the inverter in grid-forming
 * mode before the peak, and carry the diesel as spinning reserve so it is
 * already synchronised when the tie opens.
 */
const prepared: Policy = (state, cmd) => {
  const hour = state.t / H;

  if (hour < 5) cmd.batteryPowerKw = -700;
  else if (hour >= 10 && hour < 15) cmd.batteryPowerKw = -800;
  else if (hour >= 17 && hour < 18.5) cmd.batteryPowerKw = 0; // hold reserve
  else if (hour >= 18.5 && hour < 22) cmd.batteryPowerKw = 900;
  else cmd.batteryPowerKw = 0;

  // Grid-forming from late afternoon, so synthetic inertia is present when the
  // tie opens at 18:40.
  cmd.batteryGridForming = hour >= 17;

  // Diesel synchronised from 18:00 — the 120 s start plus 12 kW/s ramp means
  // calling for it at the moment of the fault would be far too late.
  cmd.gensetRunRequested = hour >= 18 && hour < 21;

  // Shed discretionary load through the island, protecting the residential
  // block because that is where the medical-device users live.
  const islanded = !state.gridConnected;
  cmd.loadAllowance.school = islanded ? 0 : 1;
  cmd.loadAllowance.industrial = islanded ? 0.6 : 1;
  cmd.loadAllowance.datacenter = islanded ? 0.6 : 1;
  cmd.loadAllowance.water = islanded ? 0 : 1;
};

function run(name: string, policy: Policy) {
  const scenario = DEFAULT_SCENARIO;
  const state = createInitialState(scenario);
  const cmd = defaultCommand(scenario);
  const log = { telemetry: [], actions: [] as any[] };

  let minF = Infinity;
  let minFAt = 0;
  let maxF = -Infinity;

  for (let i = 0; i < SECONDS_PER_DAY; i++) {
    policy(state, cmd);
    step(state, cmd, scenario, log);
    if (state.frequencyHz < minF) {
      minF = state.frequencyHz;
      minFAt = state.t;
    }
    if (state.frequencyHz > maxF) maxF = state.frequencyHz;
  }

  const s = scoreRun(state, scenario);

  console.log(`\n${'='.repeat(72)}`);
  console.log(name);
  console.log('='.repeat(72));
  console.log(`  served energy          ${s.servedKwh.toFixed(0).padStart(9)} kWh`);
  console.log(`  unserved energy        ${s.unservedKwh.toFixed(0).padStart(9)} kWh`);
  console.log(`  weighted unserved      ${s.weightedUnservedKwh.toFixed(0).padStart(9)} kWh-eq`);
  console.log(`  cost                   ${s.costUsd.toFixed(0).padStart(9)} USD`);
  console.log(`  carbon                 ${s.co2Kg.toFixed(0).padStart(9)} kg CO2`);
  console.log(`  carbon intensity       ${s.gramsCo2PerKwhServed.toFixed(0).padStart(9)} g/kWh`);
  console.log(`  minimum frequency      ${minF.toFixed(2).padStart(9)} Hz at ${hhmm(minFAt)}`);
  console.log(`  maximum frequency      ${maxF.toFixed(2).padStart(9)} Hz`);
  console.log(`  time outside band      ${s.offBandMinutes.toFixed(1).padStart(9)} min`);
  console.log(`  UFLS trips             ${String(s.uflsTrips).padStart(9)}`);
  console.log(`  hospital outage        ${s.hospitalMinutesLost.toFixed(1).padStart(9)} min`);
  console.log(`  vulnerable occupants   ${String(s.vulnerableOccupantsAffected).padStart(9)} affected`);
  console.log(`  final battery SOC      ${(state.batterySoc * 100).toFixed(0).padStart(9)} %`);

  if (log.actions.length) {
    console.log('  protection log:');
    for (const a of log.actions.slice(0, 8)) {
      console.log(`    ${hhmm(a.t)}  ${a.detail}`);
    }
  }

  return { s, minF };
}

console.log('GridKeeper — scenario validation');
console.log(`Scenario: ${DEFAULT_SCENARIO.label} (seed ${DEFAULT_SCENARIO.seed})`);

/**
 * D: understands grid-forming, but manages reserve badly — runs the battery
 * hard through the evening to chase the price peak and arrives at the fault
 * with almost nothing left. The most instructive middle case.
 */
const drained: Policy = (state, cmd) => {
  const hour = state.t / H;
  if (hour < 5) cmd.batteryPowerKw = -700;
  else if (hour >= 10 && hour < 15) cmd.batteryPowerKw = -800;
  else if (hour >= 18) cmd.batteryPowerKw = 1200; // starts drawing down at the peak
  else cmd.batteryPowerKw = 0;
  cmd.batteryGridForming = hour >= 17;
  // Calls for the diesel only once the lights are already flickering. The 120 s
  // start plus a 12 kW/s ramp means it arrives far too late to matter.
  cmd.gensetRunRequested = hour >= 18.75;
};

const a = run('A · No intervention', doNothing);
const b = run('B · Peak shaving only, grid-following, no spinning reserve', naive);
const d = run('D · Grid-forming, but battery drained chasing the price peak', drained);
const c = run('C · Prepared operator (grid-forming + spinning reserve + triage)', prepared);

console.log(`\n${'='.repeat(72)}`);
console.log('Pedagogy check');
console.log('='.repeat(72));
const check = (label: string, pass: boolean) =>
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${label}`);

check('Careless operator collapses the island', a.s.collapsed);
check('Peak-shaving-only operator also collapses the island', b.s.collapsed);
check('Prepared operator survives the island intact', !c.s.collapsed && c.s.uflsTrips === 0);
check('Prepared operator holds frequency above the UFLS threshold', c.minF >= 49.0);
check(
  'Preparation cuts weighted unserved energy by at least 10x',
  c.s.weightedUnservedKwh * 10 < b.s.weightedUnservedKwh,
);
check('Prepared operator keeps the hospital energised', c.s.hospitalMinutesLost === 0);
check(
  'Prepared operator protects the block with vulnerable occupants',
  c.s.vulnerableOccupantsAffected === 0,
);
// The model's own finding, which was not the one assumed when the scenario was
// written: a 25-minute island at this deficit needs only ~250 kWh, so poor
// reserve management is survivable. What actually separates A/B from C/D is the
// inverter control mode. Reserve management shows up instead as frequency
// quality and carbon intensity — which is why the score must weight those and
// not unserved energy alone.
check(
  'Poor reserve management survives the island on stored energy alone',
  !d.s.collapsed && d.s.unservedKwh === 0,
);
check(
  'But it is visibly punished on frequency quality and carbon',
  d.s.offBandMinutes > c.s.offBandMinutes &&
    d.s.gramsCo2PerKwhServed > c.s.gramsCo2PerKwhServed,
);
