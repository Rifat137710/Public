/**
 * Serve the assembled `dist` at the path GitHub Pages will serve it from, and drive all
 * three parts of the site in a real browser.
 *
 * Opening the files directly does not test this. Vite writes its asset URLs absolute
 * under `/Public/`, so a `file://` load resolves them against the filesystem root and
 * the console comes up unstyled and empty — which looks like a broken build and is not
 * one, and would look like a working build if the paths were wrong the other way.
 *
 *   node scripts/verify-site.mjs
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';
import playwright from '/home/user/Public/node_modules/playwright-core/index.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'dist');
const BASE = '/Public/';
const SHOTS = process.env.SHOT_DIR ?? '/tmp/claude-0/-home-user-Public/e7002dc9-9fa4-55e6-af4a-2b37b9d88d33/scratchpad/shots';

const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
};

const server = createServer(async (req, res) => {
  let path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (!path.startsWith(BASE)) return void res.writeHead(404).end('outside base');
  path = path.slice(BASE.length);
  if (path === '' || path.endsWith('/')) path += 'index.html';
  try {
    const body = await readFile(join(dist, path));
    res.writeHead(200, { 'content-type': TYPES[extname(path)] ?? 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end('not found');
  }
});
await new Promise((r) => server.listen(0, r));
const origin = `http://127.0.0.1:${server.address().port}${BASE}`;

let pass = 0, fail = 0;
const ok = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}${extra ? ' — ' + extra : ''}`); }
  else { fail++; console.log(`  FAIL ${name}${extra ? ' — ' + extra : ''}`); }
};

const browser = await playwright.chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
});

async function open(path) {
  const page = await browser.newPage({ viewport: { width: 1180, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('requestfailed', (r) => errors.push(`request failed: ${r.url()}`));
  page.on('response', (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
  await page.goto(origin + path, { waitUntil: 'load' });
  return { page, errors };
}

console.log('\nthe lesson  /Public/');
{
  const { page, errors } = await open('');
  await page.waitForFunction(() => window.__learn !== undefined, { timeout: 20000 });
  ok('loads clean', errors.length === 0, errors.slice(0, 2).join(' | '));
  const chk = await page.evaluate(() => window.__learn.check);
  ok('self-check passes', chk.ok, `${chk.n} steps, worst ${chk.worstV.toExponential(1)} pu`);
  const links = await page.locator('.next a').evaluateAll((a) => a.map((x) => x.getAttribute('href')));
  ok('links on to both other parts', links.includes('trainer/') && links.includes('city/'), links.join(' '));
  await page.screenshot({ path: `${SHOTS}/site-lesson.png` });
  await page.close();
}

console.log('\nthe console  /Public/trainer/');
{
  const { page, errors } = await open('trainer/');
  await page.waitForSelector('#root *', { timeout: 20000 });
  ok('loads clean', errors.length === 0, errors.slice(0, 2).join(' | '));
  const styled = await page.evaluate(() =>
    getComputedStyle(document.body).backgroundColor);
  ok('stylesheet actually applied', styled !== 'rgba(0, 0, 0, 0)' && styled !== '', styled);
  const back = await page.locator('.site-back').getAttribute('href');
  ok('has a way back to the lesson', back === '../', String(back));
  const noScroll = await page.evaluate(() =>
    document.documentElement.scrollHeight - document.documentElement.clientHeight);
  ok('back link did not make the console scroll', noScroll <= 1, `${noScroll}px`);
  await page.screenshot({ path: `${SHOTS}/site-trainer.png` });
  await page.close();
}

console.log('\nthe city  /Public/city/');
{
  const { page, errors } = await open('city/');
  await page.waitForFunction(() => window.__city !== undefined, { timeout: 60000 });
  const c = await page.evaluate(() => ({ check: window.__city.check, fleet: window.__city.fleetCheck }));
  ok('loads clean', errors.length === 0, errors.slice(0, 2).join(' | '));
  ok('solver self-check passes', c.check.ok, `${c.check.n} steps, worst ${c.check.worstV.toExponential(1)} pu`);
  ok('fleet self-check passes', c.fleet.ok, `${c.fleet.n} runs, worst ${c.fleet.worstSoc.toExponential(1)}`);
  const hrefs = await page.locator('a[href^=".."]').evaluateAll((a) => a.map((x) => x.getAttribute('href')));
  ok('links back to the lesson and the console',
    hrefs.includes('../') && hrefs.includes('../trainer/'), hrefs.join(' '));
  await page.screenshot({ path: `${SHOTS}/site-city.png` });
  await page.close();
}

console.log('\nnavigation actually works');
{
  const { page } = await open('');
  await page.waitForFunction(() => window.__learn !== undefined);
  await page.locator('.next a[href="trainer/"]').click();
  await page.waitForSelector('#root *', { timeout: 20000 });
  ok('lesson → console', page.url().endsWith('/trainer/'), page.url());
  await page.locator('.site-back').click();
  await page.waitForFunction(() => window.__learn !== undefined, { timeout: 20000 });
  ok('console → lesson', page.url().endsWith(BASE), page.url());
  await page.close();
}

console.log(`\n${pass} passed, ${fail} failed`);
await browser.close();
server.close();
process.exit(fail === 0 ? 0 : 1);
