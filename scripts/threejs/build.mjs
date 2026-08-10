/**
 * Bundle the city into one self-contained page.
 *
 * Three.js is inlined rather than fetched: the published artifact runs under a CSP
 * that blocks external hosts, so a CDN script tag silently yields a blank canvas.
 *
 *   node scripts/threejs/build.mjs
 */

import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, '..', '..', 'docs', 'feeder33-city.html');

const result = await build({
  entryPoints: [join(here, 'src', 'main.js')],
  bundle: true,
  format: 'iife',
  minify: true,
  target: 'es2020',
  loader: { '.json': 'json' },
  write: false,
  legalComments: 'none',
});

const js = result.outputFiles[0].text;
const shell = await readFile(join(here, 'shell.html'), 'utf8');

if (!shell.includes('/*BUNDLE*/')) throw new Error('shell.html has lost its /*BUNDLE*/ marker');

// The bundle goes in verbatim. A </script> inside a string literal would end the tag
// early, so the only escaping needed is that one sequence.
const page = shell.replace('/*BUNDLE*/', () => js.replaceAll('</script', '<\\/script'));

await writeFile(OUT, page);
console.log(`${OUT}  ${(Buffer.byteLength(page) / 1024).toFixed(0)} KB`);
