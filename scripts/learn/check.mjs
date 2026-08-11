/**
 * Bundle the lesson's simulation and run it under node, so the numbers the page will
 * claim can be checked before the page exists.
 *
 *   node scripts/learn/check.mjs
 */

import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

const result = await build({
  entryPoints: [join(here, 'run-day.js')],
  bundle: true,
  format: 'esm',
  platform: 'node',
  loader: { '.json': 'json' },
  write: false,
});

const mod = await import(
  `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`
);
mod.report();
