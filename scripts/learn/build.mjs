/**
 * Bundle the lesson into one self-contained page.
 *
 *   node scripts/learn/build.mjs
 */

import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, '..', '..', 'docs', 'learn.html');

const result = await build({
  entryPoints: [join(here, 'src', 'app.js')],
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
// early, so that one sequence is the only escaping needed.
const page = shell.replace('/*BUNDLE*/', () => js.replaceAll('</script', '<\\/script'));

await writeFile(OUT, page);
console.log(`${OUT}  ${(Buffer.byteLength(page) / 1024).toFixed(0)} KB`);
