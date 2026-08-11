/**
 * Assemble the three parts of Bus 18 into one deployable site.
 *
 * The workflow publishes `dist` and nothing else, so a page that only exists in `docs`
 * is a page nobody can reach. This runs after `vite build` and lays the pieces out at
 * the URLs the navigation between them assumes:
 *
 *     /Public/            the lesson          — the front door, and the shortest path
 *                                               to the point the entry is making
 *     /Public/trainer/    the React console   — the six-stage arc
 *     /Public/city/       the walkable town   — the same feeder in three dimensions
 *     /Public/pack/       the facilitator pack for running a tester session
 *
 * The lesson goes first because it is the only one of the three that explains itself to
 * somebody who has never heard of a per-unit voltage. The other two are better, and both
 * of them assume you already know what you are looking at.
 *
 *   node scripts/assemble.mjs
 */

import { readFile, writeFile, mkdir, rename, readdir, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'dist');
const docs = join(root, 'docs');

const put = async (from, to) => {
  await mkdir(dirname(to), { recursive: true });
  await copyFile(from, to);
};

// The console was built to dist/index.html by vite. Move it aside before the lesson
// takes that name, or the copy below silently overwrites the app.
await mkdir(join(dist, 'trainer'), { recursive: true });
await rename(join(dist, 'index.html'), join(dist, 'trainer', 'index.html'));

await put(join(docs, 'learn.html'), join(dist, 'index.html'));
await put(join(docs, 'feeder33-city.html'), join(dist, 'city', 'index.html'));
await put(join(docs, 'tester-pack.html'), join(dist, 'pack', 'index.html'));
await put(join(docs, 'video-script.html'), join(dist, 'script', 'index.html'));
await put(join(docs, 'blueprint.html'), join(dist, 'blueprint', 'index.html'));

// The slides are a download rather than a page.
await put(join(docs, 'bus18-slides.pptx'), join(dist, 'bus18-slides.pptx'));

/**
 * Every internal link, checked. A relative href that resolves to nothing is the single
 * most likely way this layout breaks — the pages are built independently and none of
 * them can see the others at build time.
 */
const pages = [
  ['', join(dist, 'index.html')],
  ['trainer/', join(dist, 'trainer', 'index.html')],
  ['city/', join(dist, 'city', 'index.html')],
];

const exists = new Set();
const walk = async (dir, prefix = '') => {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) await walk(join(dir, entry.name), `${prefix}${entry.name}/`);
    else exists.add(`${prefix}${entry.name}`);
  }
};
await walk(dist);

// Vite emits its asset URLs absolute under the deploy base, so `dist/` is the base
// rather than the server root. Both kinds of href resolve against that.
const BASE = process.env.BASE_PATH ?? '/Public/';

let broken = 0;
for (const [base, file] of pages) {
  const html = await readFile(file, 'utf8');
  for (const m of html.matchAll(/(?:href|src)="(?!https?:|#|data:|mailto:)([^"]+)"/g)) {
    const resolved = new URL(m[1], `https://x${BASE}${base}`).pathname;
    if (!resolved.startsWith(BASE)) {
      console.error(`  escapes the site root: ${base || '/'} -> ${m[1]}`);
      broken++;
      continue;
    }
    const target = resolved.slice(BASE.length);
    const candidates = [target, `${target}index.html`, target.replace(/\/$/, '')];
    if (candidates.some((c) => exists.has(c))) continue;
    console.error(`  broken link: ${base || '/'} -> ${m[1]}`);
    broken++;
  }
}
if (broken) throw new Error(`${broken} internal links resolve to nothing`);

console.log(`assembled dist/ — ${exists.size} files, every internal link resolves`);
for (const [base] of pages) console.log(`  /Public/${base}`);
