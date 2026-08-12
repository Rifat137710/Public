/**
 * Calibrate the public Baran-Wu benchmark against the reference study feeder, and report
 * honestly how well it matches.
 *
 * The reference study's strong grid should be the canonical benchmark as published. Its weak
 * grid is the same feeder behind a finite substation impedance. This script checks the
 * first claim, fits the impedance implied by the second, then holds the fitted network
 * up against Table 4.1 — sensitivities that were never used in the fit — so the match
 * is a genuine prediction rather than a restatement of what we tuned to.
 *
 *   npm run calibrate
 */

import {
  BRANCHES,
  NOMINAL_LOAD_KW,
  NOMINAL_LOAD_KVAR,
  PANDAPOWER_INDEX_OFFSET,
  STATION_BUSES,
  STRONG_SOURCE,
  WEAK_SOURCE,
  buildNetwork,
  nominalLoadPu,
  type SourceImpedance,
} from '../src/sim/network.js';
import { minimumVoltage, solvePowerFlow } from '../src/sim/powerflow.js';
import {
  dominanceRatio,
  measureSensitivities,
  stationSelfSensitivities,
} from '../src/sim/sensitivities.js';

/** The reference study's published base case, read from Figure 4.3 and Table 4.1. */
const REFERENCE = {
  strong: { vMin: 0.913, lossKw: 202.7 },
  weak: { vMin: 0.882, lossKw: 338.6 },
  /** Table 4.1, keyed by pandapower index. |dV/dP| and |dV/dQ| in pu/kW. */
  weakSensitivity: [
    { index: 17, p: 9.08e-5, q: 7.1e-5, ratio: 1.278 },
    { index: 21, p: 2.46e-5, q: 2.23e-5, ratio: 1.106 },
    { index: 24, p: 2.55e-5, q: 1.68e-5, ratio: 1.519 },
    { index: 32, p: 5.71e-5, q: 4.46e-5, ratio: 1.281 },
  ],
  weakMeanRatio: 1.28,
  strongSensitivity: [
    { index: 17, p: 7.99e-5, q: 6.46e-5, ratio: 1.237 },
    { index: 21, p: 1.82e-5, q: 1.88e-5, ratio: 0.971 },
    { index: 24, p: 1.86e-5, q: 1.32e-5, ratio: 1.412 },
    { index: 32, p: 4.77e-5, q: 3.89e-5, ratio: 1.227 },
  ],
} as const;

/** The reference study runs its experiments here; the base case above is at full load. */
const FULL_LOAD = 1.0;

function baseCase(source: SourceImpedance, loadScale = FULL_LOAD) {
  const net = buildNetwork(source);
  const { p, q } = nominalLoadPu(loadScale);
  const result = solvePowerFlow(net, p, q);
  const { bus, vMin } = minimumVoltage(result);
  return { net, p, q, result, vMinBus: bus, vMin, lossKw: result.lossKw };
}

function fmt(value: number, digits = 4): string {
  return value.toFixed(digits).padStart(digits + 4);
}

function sci(value: number): string {
  return value.toExponential(2);
}

function pct(actual: number, target: number): string {
  const error = ((actual - target) / target) * 100;
  const sign = error >= 0 ? '+' : '';
  return `${sign}${error.toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// 1. Does the published data reproduce the canonical benchmark at all?
// ---------------------------------------------------------------------------

console.log('IEEE 33-bus Baran-Wu calibration');
console.log('='.repeat(72));

const totalKw = NOMINAL_LOAD_KW.reduce((a, b) => a + b, 0);
const totalKvar = NOMINAL_LOAD_KVAR.reduce((a, b) => a + b, 0);
console.log(`\nData checksum`);
console.log(`  branches            ${BRANCHES.length}          expected 32`);
console.log(`  total load          ${totalKw} kW    expected 3715 kW`);
console.log(`  total load          ${totalKvar} kVAr  expected 2300 kVAr`);
if (BRANCHES.length !== 32 || totalKw !== 3715 || totalKvar !== 2300) {
  console.error('\n  FAIL: benchmark data does not match the published totals.');
  process.exit(1);
}
console.log('  OK');

const strong = baseCase(STRONG_SOURCE);
console.log(`\nStrong feeder (stiff source, canonical benchmark)`);
console.log(`  converged           ${strong.result.converged} in ${strong.result.iterations} iterations`);
console.log(`  Vmin                ${fmt(strong.vMin)} pu at bus ${strong.vMinBus}`);
console.log(`  reference Vmin         ${fmt(REFERENCE.strong.vMin)} pu            ${pct(strong.vMin, REFERENCE.strong.vMin)}`);
console.log(`  loss                ${strong.lossKw.toFixed(1)} kW`);
console.log(`  reference loss         ${REFERENCE.strong.lossKw.toFixed(1)} kW              ${pct(strong.lossKw, REFERENCE.strong.lossKw)}`);

// ---------------------------------------------------------------------------
// 2. Fit the substation impedance that turns the benchmark into the weak feeder.
// ---------------------------------------------------------------------------

function weakMisfit(rOhm: number, xOhm: number): number {
  const { vMin, lossKw } = baseCase({ rOhm, xOhm });
  const dv = (vMin - REFERENCE.weak.vMin) / 0.0005;
  const dl = (lossKw - REFERENCE.weak.lossKw) / 0.05;
  return dv * dv + dl * dl;
}

/** Coarse grid, then successive refinement around the incumbent. */
function fitWeakSource(): SourceImpedance {
  let bestR = 0.5;
  let bestX = 0.3;
  let best = weakMisfit(bestR, bestX);
  let span = 1.0;

  for (let pass = 0; pass < 40; pass++) {
    const step = span / 8;
    let improved = false;
    for (let i = -8; i <= 8; i++) {
      for (let j = -8; j <= 8; j++) {
        const r = bestR + i * step;
        const x = bestX + j * step;
        if (r < 0 || x < 0) continue;
        const value = weakMisfit(r, x);
        if (value < best) {
          best = value;
          bestR = r;
          bestX = x;
          improved = true;
        }
      }
    }
    if (!improved) span /= 2;
    if (span < 1e-7) break;
  }
  return { rOhm: bestR, xOhm: bestX };
}

const fitted = fitWeakSource();
const weak = baseCase(fitted);

console.log(`\nWeak feeder (finite substation, fitted)`);
console.log(`  fitted source       R = ${fitted.rOhm.toFixed(4)} ohm, X = ${fitted.xOhm.toFixed(4)} ohm`);
console.log(`  X/R                 ${(fitted.xOhm / fitted.rOhm).toFixed(3)}`);
console.log(`  Vmin                ${fmt(weak.vMin)} pu at bus ${weak.vMinBus}`);
console.log(`  reference Vmin         ${fmt(REFERENCE.weak.vMin)} pu            ${pct(weak.vMin, REFERENCE.weak.vMin)}`);
console.log(`  loss                ${weak.lossKw.toFixed(1)} kW`);
console.log(`  reference loss         ${REFERENCE.weak.lossKw.toFixed(1)} kW              ${pct(weak.lossKw, REFERENCE.weak.lossKw)}`);

if (Math.abs(fitted.rOhm - WEAK_SOURCE.rOhm) > 5e-4 || Math.abs(fitted.xOhm - WEAK_SOURCE.xOhm) > 5e-4) {
  console.log(`\n  NOTE: WEAK_SOURCE in network.ts is { rOhm: ${WEAK_SOURCE.rOhm}, xOhm: ${WEAK_SOURCE.xOhm} }.`);
  console.log(`        The fit says   { rOhm: ${fitted.rOhm.toFixed(4)}, xOhm: ${fitted.xOhm.toFixed(4)} }. Update it.`);
}

// ---------------------------------------------------------------------------
// 3. The real test: sensitivities were not used in the fit. Do they land?
// ---------------------------------------------------------------------------

/**
 * The reference study measures sensitivities at its operating point, load scale 0.50, because
 * the full-load case is already infeasible within [0.95, 1.05] pu.
 */
const OPERATING_LOAD_SCALE = 0.5;

function sensitivityReport(label: string, source: SourceImpedance, expected: readonly { index: number; p: number; q: number; ratio: number }[]) {
  const net = buildNetwork(source);
  const { p, q } = nominalLoadPu(OPERATING_LOAD_SCALE);
  const s = measureSensitivities(net, p, q, STATION_BUSES);
  const stations = stationSelfSensitivities(s);

  console.log(`\n${label} sensitivities at load scale ${OPERATING_LOAD_SCALE} (not fitted)`);
  console.log('  bus   |dV/dP| model   reference  err     |dV/dQ| model   reference  err     ratio   reference');
  for (let k = 0; k < stations.length; k++) {
    const station = stations[k];
    const want = expected[k];
    const index = station.bus - PANDAPOWER_INDEX_OFFSET;
    console.log(
      `  ${String(index).padStart(3)}   ${sci(station.selfP)}        ${sci(want.p)}   ${pct(station.selfP, want.p).padStart(7)}` +
        `    ${sci(station.selfQ)}        ${sci(want.q)}   ${pct(station.selfQ, want.q).padStart(7)}` +
        `    ${station.ratio.toFixed(3)}   ${want.ratio.toFixed(3)}`,
    );
  }
  const ratio = dominanceRatio(stations);
  console.log(`  dominance ratio (mean P / mean Q):  ${ratio.toFixed(3)}`);
  return { stations, ratio };
}

const weakSens = sensitivityReport('Weak', fitted, REFERENCE.weakSensitivity);
sensitivityReport('Strong', STRONG_SOURCE, REFERENCE.strongSensitivity);

console.log(`\nGate 1 — V-P dominance ratio >= 0.90`);
console.log(`  model  ${weakSens.ratio.toFixed(3)}`);
console.log(`  reference ${REFERENCE.weakMeanRatio.toFixed(3)} (Table 4.1), 1.271 (Gate 1 protocol)`);
console.log(`  ${weakSens.ratio >= 0.9 ? 'PASS' : 'FAIL'} — active power is the dominant voltage lever on the weak feeder`);

console.log(`\nOperating point, load scale ${OPERATING_LOAD_SCALE}`);
for (const [label, source] of [['weak', fitted], ['strong', STRONG_SOURCE]] as const) {
  const c = baseCase(source, OPERATING_LOAD_SCALE);
  const inBand = c.vMin >= 0.95;
  console.log(`  ${label.padEnd(7)} Vmin ${fmt(c.vMin)} pu at bus ${String(c.vMinBus).padStart(2)}   loss ${c.lossKw.toFixed(1).padStart(6)} kW   ${inBand ? 'inside [0.95, 1.05]' : 'BELOW 0.95'}`);
}
