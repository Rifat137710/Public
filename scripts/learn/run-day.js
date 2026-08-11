/**
 * Run the day for every controller under node and print the scoreboard.
 *
 * This is the lesson's central claim under test. If SafeSAC does not actually serve more
 * drivers at fewer violations than the alternatives, the page must not say that it does
 * — so this runs before the page is built, not after.
 *
 *   node scripts/learn/check.mjs
 */

import { runDay, CONTROLLERS, FLEET_SIZE } from './src/sim.js';
import { check } from '../shared/grid.js';
import { fleetCheck } from '../shared/fleet.js';

export function report() {
  console.log(
    `solver self-check: ${check.n} recorded steps re-solved, worst voltage gap ` +
    `${check.worstV.toExponential(1)} pu, violation counts ${check.worstViol === 0 ? 'identical' : 'DIFFER'}`,
  );
  console.log(
    `fleet self-check:  ${fleetCheck.n} recorded runs replayed, worst drivers-served gap ` +
    `${fleetCheck.worstSoc.toExponential(1)}`,
  );

  for (const grid of ['weak', 'strong']) {
    console.log(`\n=== ${grid} feeder, ${FLEET_SIZE} cars ===`);
    console.log('controller             viol%      served    worst V   loss kWh');
    for (const c of CONTROLLERS) {
      const { totals: t } = runDay(c, { grid });
      console.log(
        c.label.padEnd(22),
        (t.violationRate * 100).toFixed(2).padStart(6),
        `${String(t.driversMet).padStart(4)}/${t.fleetSize}`.padStart(11),
        t.vMinPu.toFixed(4).padStart(10),
        t.totalLossKwh.toFixed(0).padStart(9),
      );
    }
  }

  console.log('\n=== fleet size sweep, weak feeder — served (viol%) ===');
  const sizes = [40, 100, 160, 200, 240, FLEET_SIZE];
  console.log('controller          ' + sizes.map((s) => String(s).padStart(14)).join(''));
  for (const c of CONTROLLERS) {
    const cells = sizes.map((size) => {
      const { totals: t } = runDay(c, { size });
      return `${t.driversMet}/${t.fleetSize} (${(t.violationRate * 100).toFixed(1)})`.padStart(14);
    });
    console.log(c.label.padEnd(20) + cells.join(''));
  }
}
