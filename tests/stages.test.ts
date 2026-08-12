/**
 * The six-stage arc only works if the numbers cooperate.
 *
 * Each stage's reveal makes a claim — droop is safer than uncoordinated, unshielded RL
 * is dominated by droop, the trap controller looks best on the two columns a manager
 * sees. Those are not editorial decisions; they either come out of the simulation or
 * they do not, and if they stop coming out, the copy is a lie and the build should fail.
 *
 *   npm run test:stages
 */

import { runEpisode } from '../src/sim/live.js';
import { droop, placeholderController, uncoordinated } from '../src/sim/controllers.js';
import { STAGES } from '../src/content/stages.js';
import {
  OBJECTIVES,
  buildFindings,
  onePagerHtml,
  pickVerdict,
} from '../src/content/debrief.js';
import {
  PROJECTION_CHECK,
  SENSITIVITIES,
  SHORTLIST,
  TRAP_ID,
  byEvaluationId,
} from '../src/content/evaluation.js';

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
  label: 'Plain RL',
  eagerness: 0.85,
  backoffPu: 0.952,
  arbitrage: true,
  usesProjection: false,
});

const safeSac = placeholderController({
  id: 'safesac',
  label: 'Shielded RL',
  eagerness: 0.95,
  backoffPu: 0.948,
  arbitrage: false,
  usesProjection: true,
});

const shifted = placeholderController({
  id: 'sac-lag-shift',
  label: 'Plain RL (trained on a stiff feeder)',
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
  'unshielded RL is dominated by the droop rule on BOTH axes',
  results.sacLag.violationRate > results.droop.violationRate &&
    results.sacLag.socMet < results.droop.socMet,
  `RL ${results.sacLag.violationRate.toFixed(3)}/${results.sacLag.socMet.toFixed(3)} vs ` +
    `droop ${results.droop.violationRate.toFixed(3)}/${results.droop.socMet.toFixed(3)}`,
);

console.log('\nStage 5 — physics restored');
check(
  'Shielded RL beats the plain agent on service',
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

console.log('\nThe debrief');

type EpisodeResult = (typeof results)['droop'];

const dot = (id: string, label: string, r: EpisodeResult, mine = false) => ({
  id,
  label,
  violationRate: r.violationRate,
  socMet: r.socMet,
  lossKwh: r.totalLossKwh,
  provenance: r.provenance,
  mine,
});

const candidate = (id: string, label: string, r: EpisodeResult) => ({
  id,
  label,
  violationRate: r.violationRate,
  netCostUsd: r.netCostUsd,
  socMet: r.socMet,
  provenance: r.provenance,
});

const dots = [
  dot('manual', 'You', results.uncoordinated, true),
  dot('uncoordinated', 'Uncoordinated', results.uncoordinated),
  dot('droop', 'Droop (IEEE 1547)', results.droop),
  dot('sac-lag', 'Plain RL', results.sacLag),
  dot('safesac', 'Shielded RL', results.safeSac),
];

const trapCandidates = [
  candidate('droop', 'Droop (IEEE 1547)', results.droop),
  candidate('safesac', 'Shielded RL', results.safeSac),
  candidate('sac-lag-shift', 'Plain RL (trained on a stiff feeder)', results.shifted),
];

check(
  'the eight objectives are all present and in order',
  OBJECTIVES.length === 8 &&
    OBJECTIVES.every((o, i) => o.id === `L${i + 1}`) &&
    OBJECTIVES.every((o) => o.text.length > 40 && o.stage.startsWith('Stage')),
);

const debriefFindings = buildFindings(dots);
check(
  'a full run produces a finding for every beat of the arc',
  debriefFindings.length === 6,
  debriefFindings.map((f) => f.key).join(', '),
);
check(
  'the stage 4 finding claims domination only when the run actually showed it',
  (results.sacLag.violationRate > results.droop.violationRate &&
    results.sacLag.socMet < results.droop.socMet) ===
    (debriefFindings.find((f) => f.key === 'sac-lag')?.headline ===
      'Intelligence was not the missing ingredient'),
);

// A learner who skipped stages must not be told about findings they never saw.
check(
  'findings that did not happen are absent rather than asserted',
  buildFindings(dots.filter((d) => d.id === 'manual')).length === 1 &&
    buildFindings([]).length === 0,
);

const trapVerdict = pickVerdict(trapCandidates, 'sac-lag-shift');
check(
  'picking the trap is named as serving nobody',
  trapVerdict !== null && trapVerdict.headline.endsWith('served nobody'),
  trapVerdict?.headline,
);
const safeVerdict = pickVerdict(trapCandidates, 'safesac');
check(
  'picking Shielded RL gets the other verdict, not the same scolding',
  safeVerdict !== null && !safeVerdict.headline.endsWith('served nobody'),
  safeVerdict?.headline,
);
check('no pick yields no verdict', pickVerdict(trapCandidates, null) === null);

const onePager = onePagerHtml(dots, debriefFindings, trapVerdict, 'weak', 0.5, '2026-01-01 00:00');
check(
  'the one-page export carries the numbers rather than a template',
  onePager.includes(results.droop.violationRate.toFixed(3)) &&
    onePager.includes(results.safeSac.socMet.toFixed(3)) &&
    onePager.includes('<!doctype html>'),
);
check(
  'and flags the provisional figures, since it leaves the building',
  onePager.includes('reference implementations'),
);

console.log('\nSustainability — the track asks for energy-efficiency analytics');
const perDriver = (r: EpisodeResult) => r.totalLossKwh / Math.max(1e-9, r.socMet * 287);
check(
  'coordination cuts energy wasted in the lines, per driver served',
  perDriver(results.safeSac) < perDriver(results.uncoordinated) / 2,
  `Shielded RL ${perDriver(results.safeSac).toFixed(1)} kWh vs uncoordinated ${perDriver(results.uncoordinated).toFixed(1)} kWh`,
);
check(
  'unshielded RL is wasteful as well as dominated',
  perDriver(results.sacLag) > perDriver(results.droop),
  `RL ${perDriver(results.sacLag).toFixed(1)} vs droop ${perDriver(results.droop).toFixed(1)}`,
);
check(
  'the debrief only claims the energy finding when the losses are actually recorded',
  buildFindings(dots.map((d) => ({ ...d, lossKwh: undefined }))).every((f) => f.key !== 'energy'),
);

/**
 * Stage 6 is now driven by the source evaluation rather than by this simulator, so
 * the trap has to be checked where it actually lives. If the export is ever regenerated
 * and the shifted agent stops being the bait, the stage's copy becomes a lie and this
 * build should stop rather than ship it.
 */
console.log('\nStage 6 — the trap, as measured');
const measuredTrap = SHORTLIST.find((r) => r.id === TRAP_ID)!;
const rivals = SHORTLIST.filter((r) => r.id !== TRAP_ID);

check('the shortlist is the five coordinated candidates', SHORTLIST.length === 5, `${SHORTLIST.length} rows`);
check(
  'the trap has the best violation rate in the report',
  rivals.every((r) => measuredTrap.violationRate < r.violationRate),
  `${measuredTrap.violationRate.toFixed(4)} vs ${rivals.map((r) => r.violationRate.toFixed(4)).join(', ')}`,
);
check(
  'and the only negative net cost',
  measuredTrap.netCostUsd < 0 && rivals.every((r) => r.netCostUsd > 0),
  `$${measuredTrap.netCostUsd.toFixed(0)}`,
);
check(
  'while serving nobody at all',
  measuredTrap.socMet === 0,
  `socMet ${measuredTrap.socMet}`,
);
check(
  'and delivering zero energy into batteries, which is the sting the reveal uses',
  measuredTrap.chargeKwh === 0 && rivals.every((r) => r.chargeKwh > 500),
  `trap ${measuredTrap.chargeKwh} kWh vs ${rivals.map((r) => Math.round(r.chargeKwh)).join(', ')}`,
);
check(
  'Shielded RL serves materially more than unshielded, which is what stage 5 claims',
  byEvaluationId('safesac')!.socMet > byEvaluationId('sac-lag')!.socMet * 1.9,
  `${byEvaluationId('safesac')!.socMet.toFixed(3)} vs ${byEvaluationId('sac-lag')!.socMet.toFixed(3)}`,
);
check(
  'the projection cuts a request on the weak grid and passes it on the stiff one',
  PROJECTION_CHECK.stations.every(
    (s) => s.weakKw > PROJECTION_CHECK.requestKw && Math.abs(s.strongKw - PROJECTION_CHECK.requestKw) < 0.001,
  ),
  `weak ${PROJECTION_CHECK.stations.map((s) => s.weakKw.toFixed(0)).join('/')} kW`,
);
check(
  'every station is less sensitive on the stiff grid, which is why the safe set cannot be reused',
  SENSITIVITIES.every((s) => s.strongP < s.weakP),
);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
