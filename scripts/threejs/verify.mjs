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

for (const id of ['supRun', 'supGrid', 'supLoad', 'supCars', 'supMargin',
  'supTransport', 'supSpeed', 'supScrub', 'supCockpit']) {
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
t('and so are the fleet and the margin',
  (await page.$eval('#supCars', (b) => b.disabled)) && (await page.$eval('#supMargin', (b) => b.disabled)));

// A demonstrator has five minutes and cannot walk six stages on camera. The way out is
// offered here rather than as a hidden hook — and it deliberately does not mark the
// stages as taught, which the objectives table would otherwise be made to claim.
t('a demonstrator is offered a way past the arc', await page.isVisible('#supUnlock'));
await page.click('#supUnlock');
await page.waitForTimeout(250);
t('finishing the arc unlocks the feeder', !(await page.$eval('#supGrid button', (b) => b.disabled)));
t('and the offer withdraws once it is taken', await page.isHidden('#supUnlock'));

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

await page.click('#supSpeed button:nth-child(6)');
await page.waitForTimeout(200);
t('speed is settable from in here', (await sup()).speed === 64);

// Two settings below real time, because a presenter narrating the evening peak at x1 is
// talking over a day that finishes in half a minute.
await page.click('#supSpeed button:nth-child(1)');
await page.waitForTimeout(200);
t('and it goes below ×1, which is what a narrated demo needs', (await sup()).speed === 0.25);
await page.click('#supSpeed button:nth-child(3)');

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
await page.waitForTimeout(150);

// The presenter's key. Space already did this, but space is not where a hand is when it
// has been walking with WASD and looking with the arrows.
await page.evaluate(() => window.__city.resetDay());
const beforeSlash = (await sup()).playing;
await page.keyboard.press('/');
await page.waitForTimeout(200);
t('slash holds and releases the day, so a demo can stop to explain itself',
  (await sup()).playing === !beforeSlash);
await page.evaluate(() => window.__city.resetDay());

/* -------------------------------------------------------- reaching things */

// Enter is what every prompt names now, so Enter has to be what opens things.
await page.evaluate(() => {
  const spot = window.__city.room.supervisorSpot;
  window.__city.camera.position.set(spot.x, 1.7, spot.z);
  window.__city.camera.rotation.set(0, 0, 0, 'YXZ');   // yaw 0 faces north
});
await page.waitForTimeout(250);
t('the console is in reach from the spot Go to drops you on',
  (await page.evaluate(() => window.__city.focused()?.kind)) === 'supervisor');
await page.keyboard.press('Enter');
await page.waitForTimeout(300);
t('and Enter opens it', (await page.$('#supRun')) !== null);
await page.evaluate(() => window.__city.closePanel());

/* ----------------------------------------------------------- sight lines */

// Both of these were reported from inside the room: the mimic's footer readouts sat
// behind the console lids at the one place an operator stands, and the annunciator's
// bottom row sat behind the relay cabinets. A sight line is a number, so it is asserted
// here rather than re-eyeballed every time somebody moves a board.
const boards = await page.evaluate(() => window.__city.boards());
const room3d = await page.evaluate(() => window.__city.room3d);

const CONSOLE_TOP = 1.70;     // desk-mounted station screens, tilted, at eye height
const CABINET_TOP = 2.20;     // relay cubicles along the south wall

t('the mimic board clears the console lids, so its readouts are visible from the desk',
  boards.mimic.bottom > CONSOLE_TOP, `bottom at ${boards.mimic.bottom.toFixed(2)} m`);
t('the alarm board clears the relay cabinets it now hangs above',
  boards.annun.bottom > CABINET_TOP, `bottom at ${boards.annun.bottom.toFixed(2)} m`);
t('the sequence-of-events board clears them too', boards.soe.bottom > CABINET_TOP,
  `bottom at ${boards.soe.bottom.toFixed(2)} m`);
t('every board is inside the room', Object.values(boards).every((b) => b.y + b.h / 2 < room3d.h),
  `ceiling ${room3d.h} m`);
t('the supervisory console took the alarm board’s wall',
  Math.abs(boards.supervisor.z - (room3d.north + 0.28)) < 0.01
  && boards.supervisor.w > 6, `${boards.supervisor.w} m wide on the north wall`);
t('the alarm board took the sequence-of-events wall',
  Math.abs(boards.annun.z - (room3d.south - 0.28)) < 0.01);
t('and the map took the console’s old stand',
  Math.abs(boards.map.x - (room3d.east - 1.5)) < 0.01);

/* ------------------------------------------------- the fleet and the margin */

// The two settings the lesson page has and the control room did not. They are the reason
// the room can compute rather than only replay, and the checks are about that switch
// happening honestly: replaying droop's recorded commands to a hundred cars would show a
// controller that never existed, so the day has to be recomputed and the board has to say
// so — and putting both settings back has to return to the published episodes exactly.
const nightAt = async (frame) => {
  await page.evaluate((f) => window.__city.setFrame(f), frame);
  await page.waitForTimeout(120);
  return page.evaluate(() => window.__city.night());
};

t('the city starts on the recorded episodes', (await sup()).live === false);

await page.evaluate(() => window.__city.setFleetSize(120));
await page.waitForTimeout(800);
const small = await sup();
t('shrinking the fleet switches the day to being computed here',
  small.live === true && small.fleetSize === 120, `${small.fleetSize} cars, live ${small.live}`);

const atSize = (id) => page.evaluate((i) => {
  const r = window.__city.liveRun(i);
  return { prov: r.provenance, met: r.driversMet, of: r.fleetSize, viol: r.violationRate };
}, id);

const droop120 = await atSize('droop');
t('and every controller genuinely re-decides at the new size',
  droop120.prov === 'live' && droop120.of === 120,
  `droop serves ${droop120.met} of ${droop120.of}`);

// The turn in the margin curve is the one counter-intuitive result the project carries,
// and the room can now be walked through it. If a change ever made it monotonic the
// console would be quietly teaching that safety is a direction, so it is asserted.
const marginAt = (pu) => page.evaluate((m) => {
  window.__city.setMargin(m);
  const r = window.__city.liveRun('safesac');
  return { met: r.driversMet, viol: r.violationRate };
}, pu);
const loose = await marginAt(0);
const chosen = await marginAt(0.01);
const tight = await marginAt(0.045);
t('no tightening at all is the least safe setting', loose.viol > chosen.viol,
  `${(loose.viol * 100).toFixed(2)}% vs ${(chosen.viol * 100).toFixed(2)}%`);
t('over-tightening costs drivers and does NOT buy safety — the curve turns',
  tight.met < chosen.met && tight.viol > chosen.viol,
  `0.045 → ${tight.met} served at ${(tight.viol * 100).toFixed(2)}%, 0.010 → ${chosen.met} at ${(chosen.viol * 100).toFixed(2)}%`);

await page.evaluate(() => { window.__city.setMargin(0.01); window.__city.setFleetSize(287); });
await page.waitForTimeout(600);
t('putting both back returns to the published episodes', (await sup()).live === false);

/* --------------------------------------------------------------- the night */

// The town is held at night on purpose: a streetlight's brightness is the readout for the
// voltage at its bus, and daylight floods the same surfaces and swallows it. The one thing
// that must never be tuned away is the moonlit floor — without it the feeder end at
// 0.866 pu renders as a wholly black frame, indistinguishable on a recording from a page
// that failed to load.
const midnight = await nightAt(0);
const noon = await nightAt(144);
const evening = await nightAt(228);

t('noon and midnight are the same night, so nothing but voltage moves the lamps',
  noon.hemiIntensity === midnight.hemiIntensity && noon.background === midnight.background,
  `${noon.background} at both, hemisphere ${noon.hemiIntensity}`);

t('the moonlight floor holds, so a browned-out street is still a street',
  evening.hemiIntensity >= 3.0, `hemisphere ${evening.hemiIntensity.toFixed(2)} at 19:00`);

t('no console errors throughout', errors.length === 0, errors.slice(0, 3).join(' | '));

await browser.close();

console.log('\nsupervisory console');
for (const r of ok) console.log(`  ok   ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
for (const r of bad) console.log(`  FAIL ${r.name}${r.extra ? ` — ${r.extra}` : ''}`);
console.log(`\n${ok.length} passed, ${bad.length} failed`);
process.exit(bad.length ? 1 : 0);
