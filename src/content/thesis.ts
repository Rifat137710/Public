/**
 * What the trained agents actually did, measured in the thesis notebook.
 *
 * Everything in this file is transcribed from `thesis_outputs/` — `patch7_main_results.csv`,
 * `validation/patch7_summary.json`, `tables/sensitivity_comparison.csv` and
 * `tables/projection_validation.csv`. Nothing here is computed by this simulator and
 * nothing here is invented. Values are carried at full precision and rounded only for
 * display, so a number on screen can always be traced back to a row in the export.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 *  These numbers are NOT interchangeable with the simulator's own.
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * Two definitions differ, and mixing them would be exactly the error the entry spends
 * six stages teaching people to catch:
 *
 *   - `violationRate` here is the fraction of the day's 288 five-minute steps in which
 *     *at least one* bus was outside the band. The simulator counts bus-steps: the same
 *     total divided by 288 x 33. A day with one bus down all evening scores far lower
 *     on the simulator's measure than on this one.
 *
 *   - `socMet` here is over the vehicles that *departed* during the episode, about 27 of
 *     them. The simulator scores all 287, counting whoever is still plugged in at
 *     midnight where they stand.
 *
 * So this data drives the stage-6 procurement table — which is a vendor's evaluation
 * report, the thing a real engineer is handed — and it never goes on the Pareto map,
 * which plots runs this simulator performed on axes it defines. Two sources, kept apart
 * on purpose. The learner is told which is which.
 */

export const EVALUATION = {
  episodes: 25,
  label: 'patch7_weak_eval',
  loadScale: 0.5,
  /** Band tightening the projection was given, pu. */
  projectionMargin: 0.01,
  /** Mean |dV/dP| over mean |dV/dQ| at the four station buses. Above 1 means active power is the stronger lever. */
  activeOverReactive: 1.2711971653282037,
  steps: 288,
  /** Vehicles departing per episode, which is the denominator of `socMet`. */
  departures: 26.72,
} as const;

export interface ThesisRow {
  id: string;
  label: string;
  /** Fraction of the 288 steps with at least one bus outside [0.95, 1.05]. */
  violationRate: number;
  /** Fraction of departing vehicles that left with the charge they came for. */
  socMet: number;
  netCostUsd: number;
  vMinPu: number;
  lineLossKwh: number;
  /** Energy actually put into batteries, kWh. Zero is not a rounding artefact. */
  chargeKwh: number;
  /** Charge plus discharge. A controller can post throughput while charging nobody. */
  throughputKwh: number;
  note: string;
}

/** Every method in the evaluation, in the order the table reports them. */
export const RESULTS: readonly ThesisRow[] = [
  {
    id: 'uncoord',
    label: 'No control',
    violationRate: 0.11555555555555555,
    socMet: 0.9955282051282052,
    netCostUsd: 230.7311333333333,
    vMinPu: 0.9382854090571102,
    lineLossKwh: 665.2938125063738,
    chargeKwh: 1128.8,
    throughputKwh: 1128.8,
    note: 'Charges essentially everybody, and is out of band more often than anything else on the list.',
  },
  {
    id: 'droop',
    label: 'Droop (IEEE 1547)',
    violationRate: 0.05208333333333334,
    socMet: 0.3245026263513062,
    netCostUsd: 66.26558659764311,
    vMinPu: 0.947449873783414,
    lineLossKwh: 613.3373856989655,
    chargeKwh: 1026.4256453992152,
    throughputKwh: 1326.6789786944014,
    note: 'Halves the violations by turning away two drivers in three.',
  },
  {
    id: 'sac-lag',
    label: 'SAC-Lag (plain deep RL)',
    violationRate: 0.09041666666666666,
    socMet: 0.2767055759244176,
    netCostUsd: 104.28994266292173,
    vMinPu: 0.9424786267424037,
    lineLossKwh: 626.8360808452629,
    chargeKwh: 1069.8505706887452,
    throughputKwh: 1629.0092599749173,
    note: 'Dominated by the standard on both counts: worse safety and worse service than droop.',
  },
  {
    id: 'safesac',
    label: 'SafeSAC',
    violationRate: 0.09125,
    socMet: 0.5688287387695697,
    netCostUsd: 125.93776515528798,
    vMinPu: 0.9438149799398725,
    lineLossKwh: 623.7796679295756,
    chargeKwh: 914.1289889531304,
    throughputKwh: 1224.730463106958,
    note: 'Twice SAC-Lag’s drivers served at the same violation rate, and the most service of any coordinated method.',
  },
  {
    id: 'safesac-shift',
    label: 'SafeSAC (trained on a strong grid)',
    violationRate: 0.10583333333333333,
    socMet: 0.44691158308257206,
    netCostUsd: 69.65949409913563,
    vMinPu: 0.9438149799398725,
    lineLossKwh: 654.967736677747,
    chargeKwh: 542.144600945744,
    throughputKwh: 669.1569729362418,
    note: 'Moved to a grid it never trained on: safety degrades, and it carries on serving.',
  },
  {
    id: 'sac-lag-shift',
    label: 'SAC-Lag (trained on a strong grid)',
    violationRate: 0.015138888888888891,
    socMet: 0.0,
    netCostUsd: -38.17086747795728,
    vMinPu: 0.9492212147916403,
    lineLossKwh: 540.8558983772327,
    chargeKwh: 0.0,
    throughputKwh: 262.657979468285,
    note: 'The best safety score in the evaluation, the only method that turns a profit, and it puts zero kilowatt-hours into a battery all day.',
  },
];

export const byThesisId = (id: string): ThesisRow | undefined =>
  RESULTS.find((r) => r.id === id);

/**
 * The five rows put in front of the learner at stage 6.
 *
 * Uncoordinated charging is left off deliberately — it is not a product anybody is
 * selling, and leaving it in gives away the answer by making the service column's
 * absence obvious. What remains is four coordinated controllers and one that is only
 * coordinated in the sense that a closed shop is orderly.
 */
export const SHORTLIST: readonly ThesisRow[] = RESULTS.filter((r) => r.id !== 'uncoord');

/** The row the trap is built on. Nothing keys off its position in the list. */
export const TRAP_ID = 'sac-lag-shift';

/**
 * Voltage sensitivity at each station's own bus, pu per kW, from
 * `tables/sensitivity_comparison.csv`. This is what the safety projection is built from,
 * and the reason it has to be rebuilt on the deployment grid: every one of these numbers
 * is smaller on the stiff feeder, so a safe set computed there is too generous here.
 */
export const SENSITIVITIES = [
  { station: 1, bus: 17, weakP: 9.077178087700533e-5, strongP: 7.988072665991719e-5, weakQ: 7.103815534699465e-5 },
  { station: 2, bus: 21, weakP: 2.4648499852286676e-5, strongP: 1.8229777598785524e-5, weakQ: 2.2285401993837883e-5 },
  { station: 3, bus: 24, weakP: 2.5527150341889127e-5, strongP: 1.8595377534291746e-5, weakQ: 1.680393174695316e-5 },
  { station: 4, bus: 32, weakP: 5.710103477497841e-5, strongP: 4.7740523142700275e-5, weakQ: 4.45780697871101e-5 },
] as const;

/**
 * The same request put through the projection on each grid, from
 * `tables/projection_validation.csv`. A −80 kW charge is cut to −54 kW on the weak
 * feeder and passes untouched on the stiff one: the safety layer is not a fixed rule,
 * it is a computation about a particular network.
 */
export const PROJECTION_CHECK = {
  requestKw: -80,
  stations: [
    { station: 1, weakKw: -54.13488135878748, strongKw: -79.999987784807 },
    { station: 2, weakKw: -77.94798926646276, strongKw: -79.99998724013135 },
    { station: 3, weakKw: -76.85003965354511, strongKw: -79.9999860536022 },
    { station: 4, weakKw: -73.30299156025704, strongKw: -79.99998718775755 },
  ],
} as const;

/**
 * The notebook's own acceptance gates, three of six passing. Reported as they stand.
 * The two failures are the honest part of the result: cross-deployment safety is not
 * achieved, and that is the finding rather than an embarrassment to be tidied away.
 */
export const GATES = [
  { id: 'vp_dominance', pass: true, text: 'Active power moves voltage more than reactive power at every station' },
  { id: 'projection_gap', pass: false, text: 'The projection changes the command by a measurable margin' },
  { id: 'in_dist_safety', pass: true, text: 'On the grid it trained on, the safe agent stays within tolerance' },
  { id: 'xdeploy_safety', pass: false, text: 'Moved to another grid, safety holds' },
  { id: 'service_quality', pass: true, text: 'The safe agent serves materially more drivers than plain deep RL' },
] as const;
