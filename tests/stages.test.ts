/**
 * The six-stage arc only works if the numbers cooperate.
 *
 * Each stage's reveal makes a claim — droop is safer than uncoordinated, plain deep RL
 * is dominated by droop, the trap controller looks best on the two columns a manager
 * sees. Those are not editorial decisions; they either come out of the simulation or
 * they do not, and if they stop coming out, the copy is a lie and the build should fail.
 *
 *   npm run test:stages
 */

import { runEpisode } from '../src/sim/live.js';
import { droop, placeholderController, uncoordinated } from '../src/sim/controllers.js';
import { STAGES } from '../src/content/stages.js';

let passed = 0;
let failed = 0;

function check(name: string, condition: boolean, detail = ''): void {
  if (condition) {
    passed++;
    console.log(`  PASS  ${name}${detail ? `   ${detail}` : ''}`);
  } else {
    failed++;
    console.log(`  FAIL  ${name}${detail ? `   ${detail}` : ''}`);
  }
}

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

const shifted = placeholderController({
  id: 'sac-lag-shift',
  label: 'SAC-Lag (trained on a strong grid)',
  eagerness: 0,
  backoffPu: 0.9,
  arbitrage: true,
  usesProjection: false,
});

const scenario = { grid: 'weak' as const, loadScale: 0.5, seed: 137710 };
const results = {
  uncoordinated: runEpisode(uncoordinated, scenario),
  droop: runEpisode(droop, scenario),
  sacLag: runEpisode(sacLag, scenario),
  safeSac: runEpisode(safeSac, scenario),
  shifted: runEpisode(shifted, scenario),
};

console.log('\nThe arc');
check('six stages', STAGES.length === 6);
check('stage 1 is the learner driving, unaided', STAGES[0].mode === 'manual' && STAGES[0].projection === false);
check(
  'the map is not unlocked before the learner has finished their own day',
  !STAGES[0].unlocks.includes('map') && STAGES[1].unlocks.includes('map'),
);
check(
  'the safety projection toggle appears no earlier than stage 5',
  STAGES.findIndex((s) => s.unlocks.includes('projection')) === 4,
);
check('stage 6 is a choice, not a run', STAGES[5].mode === 'choose');

console.log('\nStage 2 — service without safety');
check(
  'uncoordinated charging serves nearly everyone',
  results.uncoordinated.socMet > 0.85,
  `SoC met ${results.uncoordinated.socMet.toFixed(3)}`,
);
check(
  'and breaks the band badly enough to see it',
  results.uncoordinated.violationRate > 0.1,
  `violations ${results.uncoordinated.violationRate.toFixed(3)}, worst ${results.uncoordinated.vMinPu.toFixed(4)} pu`,
);

console.log('\nStage 3 — safety without service');
check(
  'droop is safer than uncoordinated',
  results.droop.violationRate < results.uncoordinated.violationRate,
  `${results.droop.violationRate.toFixed(3)} vs ${results.uncoordinated.violationRate.toFixed(3)}`,
);
check(
  'droop pays for it in service',
  results.droop.socMet < results.uncoordinated.socMet - 0.15,
  `${results.droop.socMet.toFixed(3)} vs ${results.uncoordinated.socMet.toFixed(3)}`,
);

console.log('\nStage 4 — the credibility beat');
check(
  'plain deep RL is dominated by the droop rule on BOTH axes',
  results.sacLag.violationRate > results.droop.violationRate &&
    results.sacLag.socMet < results.droop.socMet,
  `RL ${results.sacLag.violationRate.toFixed(3)}/${results.sacLag.socMet.toFixed(3)} vs ` +
    `droop ${results.droop.violationRate.toFixed(3)}/${results.droop.socMet.toFixed(3)}`,
);

console.log('\nStage 5 — physics restored');
check(
  'SafeSAC beats the plain agent on service',
  results.safeSac.socMet > results.sacLag.socMet + 0.15,
  `${results.safeSac.socMet.toFixed(3)} vs ${results.sacLag.socMet.toFixed(3)}`,
);
check(
  'without giving up safety to get it',
  results.safeSac.violationRate <= results.sacLag.violationRate,
  `${results.safeSac.violationRate.toFixed(3)} vs ${results.sacLag.violationRate.toFixed(3)}`,
);

console.log('\nStage 6 — the trap');
const trap = results.shifted;
const others = [results.droop, results.sacLag, results.safeSac];
check(
  'the trap controller has the best violation rate on the board',
  others.every((r) => trap.violationRate <= r.violationRate),
  `trap ${trap.violationRate.toFixed(3)} vs ${others.map((r) => r.violationRate.toFixed(3)).join(', ')}`,
);
check(
  'and the lowest cost — the only one that turns a profit',
  trap.netCostUsd < 0 && others.every((r) => trap.netCostUsd < r.netCostUsd),
  `trap $${trap.netCostUsd.toFixed(0)} vs ${others.map((r) => `$${r.netCostUsd.toFixed(0)}`).join(', ')}`,
);
check(
  'while serving essentially nobody',
  trap.socMet < 0.02,
  `SoC met ${trap.socMet.toFixed(3)}`,
);
check(
  'so the trap is genuinely baited — it wins on every column shown',
  others.every((r) => trap.violationRate <= r.violationRate && trap.netCostUsd < r.netCostUsd) &&
    trap.socMet < 0.02,
);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
