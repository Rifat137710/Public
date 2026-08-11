/**
 * Drive the control room's supervisory console in a real browser.
 *
 * The console duplicates every control the page toolbar carries, which is exactly the
 * arrangement that rots: someone adds a setting to the bar, the room quietly stops
 * being able to run the plant, and nothing fails until a demonstration is halfway
 * through. So each control is exercised from inside the panel and then checked against
 * the state the toolbar reports, and the locks are checked in both directions.
 *
 *   node scripts/threejs/verify.mjs
 */

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import playwright from '/home/user/Public/node_modules/playwright-core/index.js';

const { chromium } = playwright;
const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const page_url = 'file://' + join(root, 'docs', 'feeder33-city.html');

const ok = [];
const bad = [];
const t = (name, cond, extra = '') => (cond ? ok : bad).push({ name, extra });

const browser = await chromium.launch({
  executablePath: process.env.CHROME ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('PAGEERROR ' + e.message));

await page.goto(page_url);
await page.waitForTimeout(4500);
await page.evaluate(() => window.__city.dismissCard());

const sup = () => page.evaluate(() => window.__city.sup());
const state = () => page.evaluate(() => window.__city.state());

/* ---------------------------------------------------------------- reachable */

const kinds = await page.evaluate(() => window.__city.targets.map((x) => x.kind));
t('the console is a walk-up target in the room', kinds.includes('supervisor'));

const goLabels = await page.$$eval('#goSeg button', (bs) => bs.map((b) => b.textContent));
t('and has its own Go to entry', goLabels.includes('Supervisory desk'));

await page.evaluate(() =>
  window.__city.openPanel(window.__city.targets.find((x) => x.kind === 'supervisor')));
await page.waitForTimeout(250);

// The overlay used to sit on top of every panel for anyone driving by keyboard, which
// made the panel visible and unusable. It must be out of the way whenever one is open.
t('the enter overlay steps aside for the panel', await page.isHidden('#enter'));

for (const id of ['supRun', 'supGrid', 'supLoad', 'supTransport', 'supSpeed', 'supScrub', 'supCockpit']) {
  t(`the panel carries #${id}`, (await page.$('#' + id)) !== null);
}

/* ------------------------------------------------------- every control works */

await page.click('#supRun button:nth-child(2)');
await page.waitForTimeout(200);
t('choosing a controller in the room moves the plant', (await state()).runIndex === 1);
t('and the page toolbar follows it',
  (await page.$eval('#runSeg button:nth-child(2)', (b) => b.getAttribute('aria-pressed'))) === 'true');

t('the feeder is locked before the arc is finished', await page.$eval('#supGrid button', (b) => b.disabled));
t('the town size is too', await page.$eval('#supLoad button', (b) => b.disabled));

await page.evaluate(() => window.__city.unlockSandbox());
await page.waitForTimeout(200);
t('finishing the arc unlocks the feeder', !(await page.$eval('#supGrid button', (b) => b.disabled)));

await page.click('#supGrid button:nth-child(2)');
await page.waitForTimeout(500);
t('and it rebuilds the grid from in here', (await sup()).gridKind === 'strong');
await page.click('#supGrid button:nth-child(1)');
await page.waitForTimeout(500);

const wasPlaying = (await sup()).playing;
await page.click('#supTransport button:nth-child(1)');
await page.waitForTimeout(200);
t('the transport toggles the day', (await sup()).playing === !wasPlaying, `was ${wasPlaying}`);

await page.click('#supTransport button:nth-child(2)');
await page.waitForTimeout(200);
const reset = await sup();
t('and resets it to the top', reset.playing === false && reset.clock === '00:00', reset.clock);

await page.click('#supSpeed button:nth-child(4)');
await page.waitForTimeout(200);
t('speed is settable from in here', (await sup()).speed === 64);

await page.evaluate(() => window.__city.scrubTo(228));
await page.waitForTimeout(300);
t('the clock is scrubbable from in here', (await sup()).clock === '19:00');
t('and scrubbing by hand stops the run being scored', (await sup()).scoring === false);

/* -------------------------------------------- the panel survives a running day */

// The other panels rebuild their markup on every HUD tick, which is fine for a slider
// and fatal for a wall of buttons: the element is replaced between mousedown and
// mouseup and the click goes nowhere. This one updates in place, and this is the check
// that says so.
await page.evaluate(() => { window.__city.setSpeed(64); window.__city.togglePlay(); });
await page.waitForTimeout(1400);
await page.click('#supRun button:nth-child(3)');
await page.waitForTimeout(250);
t('the panel is still clickable with the day running', (await state()).runIndex === 2);
await page.evaluate(() => window.__city.resetDay());

/* ------------------------------------------------------------- cockpit mode */

await page.click('#supCockpit');
await page.waitForTimeout(250);
t('cockpit mode hides the page toolbar', await page.isHidden('.bar'));
t('and says so, so nobody is stranded', await page.isVisible('#cockpitTag'));
await page.click('#supCockpit');
await page.waitForTimeout(250);
t('and gives it back', await page.isVisible('.bar'));

/* ----------------------------------------------------------------- hotkeys */

await page.evaluate(() => window.__city.closePanel());
await page.evaluate(() => document.querySelector('canvas').focus());
await page.waitForTimeout(150);
await page.keyboard.press('1');
await page.waitForTimeout(200);
t('hotkey 1 picks the first controller', (await state()).runIndex === 0);
await page.keyboard.press('g');
await page.waitForTimeout(500);
t('hotkey g rebuilds the feeder', (await sup()).gridKind === 'strong');
await page.keyboard.press('g');
await page.waitForTimeout(500);
await page.keyboard.press(']');
await page.waitForTimeout(200);
t('hotkey ] steps the speed up', (await sup()).speed > 1);
await page.keyboard.press('t');
await page.waitForTimeout(200);
t('hotkey t toggles cockpit mode', (await page.evaluate(() => window.__city.cockpit())) === true);
await page.keyboard.press('t');

t('no console errors throughout', errors.length === 0, errors.slice(0, 3).join(' | '));

await browser.close();

console.log('\nsupervisory console');
for (const r of ok) console.log(`  ok   ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
for (const r of bad) console.log(`  FAIL ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
console.log(`\n${ok.length} passed, ${bad.length} failed`);
process.exit(bad.length ? 1 : 0);
