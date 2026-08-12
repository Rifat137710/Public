/**
 * Run every controller across the same day and print the comparison table.
 *
 * This is the headless version of what the learner assembles by hand across the six
 * stages, and it is the harness that tells us whether the scenario is teaching the
 * lesson it is supposed to teach. What we need to see is a genuine trade-off: the
 * uncoordinated baseline serving everybody while breaking the band, droop holding the
 * band while serving nobody, and the safety layer buying service back at equal safety.
 *
 *   npm run compare
 */

import { STATION_BUSES } from '../src/sim/network.js';
import { checkDeliverability, buildFleet } from '../src/sim/fleet.js';
import { runEpisode, type EpisodeResult, type ScenarioOptions } from '../src/sim/live.js';
import {
  droop,
  placeholderController,
  uncoordinated,
  type Controller,
} from '../src/sim/controllers.js';
import { STEPS_PER_DAY, clockOf } from '../src/sim/profiles.js';

const BASE: ScenarioOptions = { grid: 'weak', loadScale: 0.5, seed: 137710 };

const sacLagStandIn = placeholderController({
  id: 'sac-lag',
  label: 'Plain RL',
  eagerness: 0.85,
  backoffPu: 0.952,
  arbitrage: true,
  usesProjection: false,
});

const safeSacStandIn = placeholderController({
  id: 'safesac',
  label: 'Shielded RL',
  eagerness: 0.95,
  backoffPu: 0.948,
  arbitrage: false,
  usesProjection: true,
});

function row(r: EpisodeResult): string {
  const flag = r.provenance === 'placeholder' ? ' *' : '  ';
  return (
    `  ${(r.label + flag).padEnd(30)}` +
    `${r.violationRate.toFixed(3).padStart(8)}` +
    `${r.socMet.toFixed(3).padStart(9)}` +
    `${r.netCostUsd.toFixed(1).padStart(11)}` +
    `${r.vMinPu.toFixed(4).padStart(9)}` +
    `${r.projectionEnabled ? 'on' : 'off'}`.padStart(9)
  );
}

function header(title: string): void {
  console.log(`\n${title}`);
  console.log(
    `  ${'controller'.padEnd(30)}${'viol.'.padStart(8)}${'SoC met'.padStart(9)}` +
      `${'net cost'.padStart(11)}${'Vmin'.padStart(9)}${'safety'.padStart(9)}`,
  );
}

// ---------------------------------------------------------------------------

console.log('Bus 18 — controller comparison');
console.log('='.repeat(78));

const fleet = buildFleet({ seed: BASE.seed, stationCount: STATION_BUSES.length });
const deliverability = checkDeliverability(fleet);
console.log(`\nFleet: ${deliverability.total} vehicles, seed ${BASE.seed}`);
console.log(
  `  energy requests deliverable within dwell: ${deliverability.deliverable}/${deliverability.total}` +
    ` (${((deliverability.deliverable / deliverability.total) * 100).toFixed(1)}%)`,
);
if (deliverability.deliverable < deliverability.total) {
  console.log(
    `  worst shortfall ${deliverability.worstShortfallKwh.toFixed(1)} kWh —` +
      ` unmet service can no longer be blamed solely on the controller`,
  );
}

const controllers: Controller[] = [uncoordinated, droop, sacLagStandIn, safeSacStandIn];

header('Weak feeder, load scale 0.50 — each controller, compared like for like');
const asPublished = controllers.map((c) => runEpisode(c, BASE));
for (const r of asPublished) console.log(row(r));

header('Weak feeder — the stage 5 reveal: safety layer forced OFF for everyone');
const withoutProjection = controllers.map((c) =>
  runEpisode(c, { ...BASE, projectionOverride: false }),
);
for (const r of withoutProjection) console.log(row(r));

header('Strong feeder, load scale 0.50 — same controllers, stiffer network');
const strong = controllers.map((c) => runEpisode(c, { ...BASE, grid: 'strong' }));
for (const r of strong) console.log(row(r));

console.log('\n  * reference implementation, not the trained agent — figures provisional');

// ---------------------------------------------------------------------------

console.log('\n\nWhat the safety layer bought Shielded RL, weak feeder');
console.log(
  `  ${'controller'.padEnd(30)}${'viol. off'.padStart(11)}${'viol. on'.padStart(10)}` +
    `${'SoC off'.padStart(9)}${'SoC on'.padStart(8)}`,
);
for (let i = 0; i < controllers.length; i++) {
  const off = withoutProjection[i];
  const on = asPublished[i];
  console.log(
    `  ${off.label.padEnd(30)}${off.violationRate.toFixed(3).padStart(11)}` +
      `${on.violationRate.toFixed(3).padStart(10)}` +
      `${off.socMet.toFixed(3).padStart(9)}${on.socMet.toFixed(3).padStart(8)}`,
  );
}

// ---------------------------------------------------------------------------

console.log('\n\nThe evening, minute by minute (uncoordinated, projection off)');
const evening = withoutProjection[0];
console.log(`  ${'time'.padEnd(8)}${'Vmin'.padStart(8)}${'bus'.padStart(5)}${'buses out'.padStart(11)}${'connected'.padStart(11)}${'command kW'.padStart(12)}`);
for (let step = 0; step < STEPS_PER_DAY; step += 6) {
  const s = evening.steps[step];
  if (s.step < 180 || s.step > 264) continue;
  const total = s.safeKw.reduce((a, b) => a + b, 0);
  console.log(
    `  ${clockOf(s.step).padEnd(8)}${s.vMin.toFixed(4).padStart(8)}${String(s.vMinBus).padStart(5)}` +
      `${String(s.violations).padStart(11)}${String(s.connected).padStart(11)}${total.toFixed(0).padStart(12)}`,
  );
}

// ---------------------------------------------------------------------------

console.log('\n\nDoes the scenario teach the lesson?');
const uncoord = asPublished[0];
const droopResult = asPublished[1];

const checks: [string, boolean, string][] = [
  [
    'uncoordinated charging serves nearly everyone',
    uncoord.socMet > 0.85,
    `SoC met ${uncoord.socMet.toFixed(3)}`,
  ],
  [
    'droop holds the band better than uncoordinated',
    droopResult.violationRate < uncoord.violationRate,
    `${droopResult.violationRate.toFixed(3)} vs ${uncoord.violationRate.toFixed(3)}`,
  ],
  [
    'droop pays for it in service',
    droopResult.socMet < uncoord.socMet - 0.1,
    `SoC met ${droopResult.socMet.toFixed(3)} vs ${uncoord.socMet.toFixed(3)}`,
  ],
  [
    'there is a real trade-off to discover, not a dominant answer',
    droopResult.violationRate < uncoord.violationRate && droopResult.socMet < uncoord.socMet,
    'neither controller dominates the other',
  ],
  [
    'the feeder actually goes out of band without help',
    withoutProjection[0].violationRate > 0.02,
    `violation rate ${withoutProjection[0].violationRate.toFixed(3)} with the safety layer off`,
  ],
];

let failed = 0;
for (const [name, ok, detail] of checks) {
  if (!ok) failed++;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}   ${detail}`);
}
console.log(`\n${checks.length - failed} of ${checks.length} scenario checks pass`);
process.exit(failed === 0 ? 0 : 1);
