/**
 * Drive the built page in headless Chromium.
 *
 * The screenshots are the point. Every serious visual defect in this project — an
 * upside-down world, a white-out control room, console screens buried in a desk — was
 * found by looking at an image, and none of them by reading code.
 *
 *   node scripts/learn/verify.mjs
 */

import playwright from '/home/user/Public/node_modules/playwright-core/index.js';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const PAGE = 'file://' + join(here, '..', '..', 'docs', 'learn.html');
const SHOTS = process.env.SHOT_DIR ?? '/tmp/claude-0/-home-user-Public/e7002dc9-9fa4-55e6-af4a-2b37b9d88d33/scratchpad/shots';

let pass = 0, fail = 0;
const ok = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}${extra ? ' — ' + extra : ''}`); }
  else { fail++; console.log(`  FAIL ${name}${extra ? ' — ' + extra : ''}`); }
};

const { chromium } = playwright;
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ viewport: { width: 1180, height: 900 } });

const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push(String(e)));

await page.goto(PAGE, { waitUntil: 'load' });
await page.waitForFunction(() => window.__learn !== undefined, { timeout: 20000 });

console.log('\nload');
ok('no console errors', errors.length === 0, errors.join(' | '));
const chk = await page.evaluate(() => window.__learn.check);
ok('solver self-check passes', chk.ok, `${chk.n} steps, worst ${chk.worstV.toExponential(1)} pu`);

console.log('\nlessons');
const lessonCount = await page.locator('#lessons .panel').count();
ok('six lessons rendered', lessonCount === 6, `${lessonCount} found`);

for (let i = 0; i < lessonCount; i++) {
  await page.locator('#lessons .try').nth(i).click();
  await page.waitForTimeout(220);
  const s = await page.evaluate(() => ({ ...window.__learn.state }));
  const expected = await page.evaluate((n) => window.__learn.LESSONS[n].set, i);
  const matched = Object.entries(expected).every(([k, v]) => s[k] === v);
  ok(`lesson ${i + 1} sets the simulator`, matched, JSON.stringify(s));
  await page.screenshot({ path: `${SHOTS}/lesson-${i + 1}.png` });
}

console.log('\nthe claim');
const claim = await page.evaluate(() => {
  const out = {};
  for (const size of [100, 160, 200, 240]) {
    const runs = window.__learn.allFor(size, 'weak');
    const get = (id) => runs.find((r) => r.controller.id === id).totals;
    out[size] = {
      safe: [get('safesac').driversMet, +(get('safesac').violationRate * 100).toFixed(2)],
      droop: [get('droop').driversMet, +(get('droop').violationRate * 100).toFixed(2)],
      rl: [get('sac-lag').driversMet, +(get('sac-lag').violationRate * 100).toFixed(2)],
    };
  }
  return out;
});
for (const [size, r] of Object.entries(claim)) {
  const beatsDroop = r.safe[0] > r.droop[0] && r.safe[1] < r.droop[1];
  ok(`at ${size} cars SafeSAC beats droop on both counts`, beatsDroop,
    `safe ${r.safe[0]}@${r.safe[1]}%  droop ${r.droop[0]}@${r.droop[1]}%  rl ${r.rl[0]}@${r.rl[1]}%`);
}

console.log('\ninteraction');
await page.evaluate(() => {
  Object.assign(window.__learn.state, { controller: 'uncoordinated', size: 200, grid: 'weak', step: 228 });
  window.__learn.sync();
});
const bad = await page.locator('#readouts .ro.bad').count();
ok('uncoordinated at 19:00 shows streets out of range', bad > 0, `${bad} alarm readouts`);

const unco = await page.evaluate(() => {
  const d = window.__learn.dayFor('uncoordinated', 200, 'weak');
  return { viol: d.steps[228].viol, day: d.steps.filter((s) => s.viol > 0).length };
});
await page.evaluate(() => {
  window.__learn.state.controller = 'safesac';
  window.__learn.sync();
});
const safe = await page.evaluate(() => {
  const d = window.__learn.dayFor('safesac', 200, 'weak');
  return { viol: d.steps[228].viol, day: d.steps.filter((s) => s.viol > 0).length };
});
ok('SafeSAC spends far less of the day out of range', safe.day * 4 < unco.day,
  `${safe.day} steps against ${unco.day} uncontrolled`);

await page.click('#playBtn');
await page.waitForTimeout(700);
const moved = await page.evaluate(() => window.__learn.state.step);
ok('play advances the day', moved > 228, `step ${moved}`);
await page.click('#playBtn');

/* ------------------------------------------------------- the safety margin */

// The claim the margin panel makes is that safety has an optimum rather than a
// direction. It is the one counter-intuitive result on the page, so it is asserted
// rather than trusted: if a change to the projection ever made the curve monotonic, the
// panel would be quietly telling readers something untrue.
ok('the margin panel starts hidden', await page.isHidden('#marginOut'));
await page.click('#marginRun');
await page.waitForFunction(() => !document.getElementById('marginOut').hidden, { timeout: 20000 });
const sweep = await page.evaluate(() => window.__learn.marginSweep(200, 'weak'));

const at = (m) => sweep.find((r) => Math.abs(r.marginPu - m) < 1e-9);
ok('the sweep covers zero through 0.045', at(0) && at(0.045), `${sweep.length} rows`);
ok('no tightening at all is the least safe setting',
  at(0).violationRate > at(0.010).violationRate,
  `${(at(0).violationRate * 100).toFixed(2)}% vs ${(at(0.010).violationRate * 100).toFixed(2)}%`);
ok('over-tightening costs drivers',
  at(0.045).driversMet < at(0.010).driversMet,
  `${at(0.045).driversMet} vs ${at(0.010).driversMet} served`);
ok('and does NOT buy safety — the curve turns, which is the whole lesson',
  at(0.045).violationRate > at(0.010).violationRate,
  `${(at(0.045).violationRate * 100).toFixed(2)}% at 0.045 against ${(at(0.010).violationRate * 100).toFixed(2)}% at 0.010`);
ok('the thesis’s own value is the best of the swept set on violations',
  sweep.every((r) => r.violationRate >= at(0.010).violationRate - 1e-12),
  `best ${(Math.min(...sweep.map((r) => r.violationRate)) * 100).toFixed(2)}%`);
await page.screenshot({ path: `${SHOTS}/margin.png` });

await page.screenshot({ path: `${SHOTS}/full.png`, fullPage: true });
await page.setViewportSize({ width: 420, height: 900 });
await page.waitForTimeout(250);
await page.screenshot({ path: `${SHOTS}/mobile.png` });
const overflow = await page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);
ok('no horizontal overflow at 420px', overflow <= 1, `${overflow}px`);

ok('still no console errors', errors.length === 0, errors.join(' | '));

console.log(`\n${pass} passed, ${fail} failed`);
await browser.close();
process.exit(fail === 0 ? 0 : 1);
