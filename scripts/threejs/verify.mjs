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

/* --------------------------------------------------------------- the sky */

// The city was lit by a single fixed hemisphere light, which made noon and midnight
// identical and left the feeder end at 19:00 rendering as a wholly black frame — the
// one moment the whole build is about, arriving as something indistinguishable from a
// page that failed to load. These check that the sun exists, that it is the solar
// series and not a second opinion, and that the night never bottoms out again.
const skyAt = async (frame) => {
  await page.evaluate((f) => window.__city.setFrame(f), frame);
  await page.waitForTimeout(120);
  return page.evaluate(() => window.__city.sky());
};

const midnight = await skyAt(0);
const dawn = await skyAt(84);      // 07:00
const noon = await skyAt(144);     // 12:00
const dusk = await skyAt(216);     // 18:00
const evening = await skyAt(228);  // 19:00

t('the sun is up at noon and down at midnight',
  noon.daylight > 0.95 && midnight.daylight === 0,
  `noon ${noon.daylight.toFixed(2)}, midnight ${midnight.daylight.toFixed(2)}`);

t('sunrise and sunset are read off the solar series, not invented',
  Math.abs(dawn.solarHours.rise - 6.083) < 0.1 && Math.abs(dawn.solarHours.set - 18.417) < 0.1,
  `${dawn.solarHours.rise.toFixed(2)}h to ${dawn.solarHours.set.toFixed(2)}h`);

t('noon and midnight are not the same sky', noon.background !== midnight.background,
  `${noon.background} vs ${midnight.background}`);

t('dusk is its own sky too, between the other two',
  dusk.background !== noon.background && dusk.background !== midnight.background,
  dusk.background);

t('the sun is switched off below the horizon, never dimmed onto the town from beneath',
  midnight.sunIntensity === 0 && evening.sunIntensity === 0 && noon.sunIntensity > 1,
  `midnight ${midnight.sunIntensity}, 19:00 ${evening.sunIntensity}, noon ${noon.sunIntensity.toFixed(1)}`);

// The floor is the fix for the black frame. If someone ever tunes it to zero the
// feeder end goes back to being invisible, so it is asserted rather than trusted.
t('night keeps a moonlight floor, so a browned-out street is still a street',
  evening.hemiIntensity >= 3.0,
  `hemisphere ${evening.hemiIntensity.toFixed(2)} at 19:00`);

t('fog thins in daylight so the feeder is visible down its length',
  noon.fogDensity < midnight.fogDensity,
  `${noon.fogDensity.toFixed(5)} vs ${midnight.fogDensity.toFixed(5)}`);

t('no console errors throughout', errors.length === 0, errors.slice(0, 3).join(' | '));

await browser.close();

console.log('\nsupervisory console');
for (const r of ok) console.log(`  ok   ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
for (const r of bad) console.log(`  FAIL ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
console.log(`\n${ok.length} passed, ${bad.length} failed`);
process.exit(bad.length ? 1 : 0);
