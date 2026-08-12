/**
 * Does the energy wasted in the lines actually separate the controllers?
 *
 * Losses are quadratic in current, so how the fleet is dispatched should change them --
 * but "should" is not evidence. If the spread is small, the sustainability readout is
 * decoration and does not belong on the scorecard.
 */

import { runEpisode } from '../src/sim/live.js';
import { droop, placeholderController, uncoordinated } from '../src/sim/controllers.js';

const safeSac = placeholderController({ id: 'safesac', label: 'Shielded RL', eagerness: 0.95, backoffPu: 0.948, arbitrage: false, usesProjection: true });
const sacLag = placeholderController({ id: 'sac-lag', label: 'Plain RL', eagerness: 0.85, backoffPu: 0.952, arbitrage: true, usesProjection: false });
const idle = placeholderController({ id: 'idle', label: 'Nobody charges', eagerness: 0, backoffPu: 0.9, arbitrage: false, usesProjection: false });

const scenario = { grid: 'weak' as const, loadScale: 0.5, seed: 137710 };
const base = runEpisode(idle, scenario);

console.log('\n              controller      loss kWh   vs idle    viol    soc');
for (const c of [idle, uncoordinated, droop, sacLag, safeSac]) {
  const r = runEpisode(c, scenario);
  const extra = r.totalLossKwh - base.totalLossKwh;
  console.log(
    c.label.padEnd(24),
    r.totalLossKwh.toFixed(1).padStart(8),
    (extra >= 0 ? '+' : '') + extra.toFixed(1).padStart(7),
    r.violationRate.toFixed(3).padStart(8),
    r.socMet.toFixed(3).padStart(7),
  );
}
