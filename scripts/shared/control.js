/**
 * The four controllers the lesson compares, each computed live so that changing the
 * number of cars or the strength of the grid actually changes what they do.
 *
 * Two are published rules and are exact:
 *
 *   - `uncoordinated` is what a feeder gets today: everybody charges on arrival.
 *   - `droop` is the IEEE 1547-2018 volt-watt curve, applied at each station's own bus.
 *
 * Two stand for the thesis's learned agents. Their *policy* — what the network would
 * ask for — is a simple stand-in here, because a trained actor needs its observation
 * vector rebuilt to run. Their *difference* is not a stand-in: SafeSAC is the same raw
 * request as SAC-Lag with the safety projection in front of it, and that projection is
 * the real algorithm, solved against sensitivities measured on the live feeder every
 * step. So the thing the lesson claims to show — what the safety layer buys — is the
 * thing that is really computed.
 */

import { BAND_LO, BAND_HI, STATION_BUSES } from './grid.js';

/* ================================================================== */
/*  The rules                                                         */
/* ================================================================== */

export const uncoordinated = {
  id: 'uncoordinated',
  label: 'No control',
  blurb: 'Every car charges the moment it plugs in, as fast as the charger allows.',
  command: (ctx) => ctx.caps.map((cap) => cap.maxDrawKw),
};

/** Volt-watt breakpoints, per unit. Full service above V1, nothing below V2. */
export const DROOP_V1 = 0.995;
export const DROOP_V2 = 0.968;
export const DROOP_V3 = 0.950;

/**
 * IEEE 1547-2018 volt-watt droop.
 *
 * Each station reads the voltage at its own bus and derates: full charge above V1,
 * tapering to nothing at V2, then reversing into discharge down to V3. What it cannot
 * see is the rest of the feeder — so it has no way to know that easing off at bus 18
 * would let bus 33 charge. That blindness is the standard, not a bug in this code, and
 * it is most of why it serves so few drivers.
 */
export const droop = {
  id: 'droop',
  label: 'Droop (the standard)',
  blurb: 'Each charger watches its own voltage and slows down when it sags.',
  command: (ctx) => ctx.caps.map((cap, k) => {
    const v = ctx.voltages[STATION_BUSES[k]];
    if (v >= DROOP_V1) return cap.maxDrawKw;
    if (v >= DROOP_V2) return cap.maxDrawKw * ((v - DROOP_V2) / (DROOP_V1 - DROOP_V2));
    return cap.maxInjectKw * Math.min(1, (DROOP_V2 - v) / (DROOP_V2 - DROOP_V3));
  }),
};

/* ================================================================== */
/*  What a learned policy asks for                                    */
/* ================================================================== */

/**
 * The raw request both learned controllers make before anything is done about safety.
 *
 * An agent paid for cheap energy learns to wait for the cheap hour, and to sell back
 * while the price is high. Both are real things to learn and both are worth money. But
 * a price signal is the same for every station at once, so what the agent actually
 * learns is to synchronise: it starves the evening, then puts the entire fleet on
 * charge the moment the tariff drops at 22:00, while the town's own load is still high.
 *
 * The result is a second peak of the agent's own making. That is the failure the lesson
 * is about, and it is why "it learned to save money" and "it learned to run the grid"
 * are not the same sentence.
 */
function learnedRequest(ctx) {
  return ctx.caps.map((cap) => {
    if (ctx.price >= 0.30) {
      // Peak tariff: sell if this station has vehicles willing, otherwise trickle.
      if (cap.maxInjectKw > 0) return cap.maxInjectKw * 0.3;
      return cap.maxDrawKw * 0.15;
    }
    return cap.maxDrawKw * (ctx.price <= 0.10 ? 1.0 : 0.7);
  });
}

export const plainRl = {
  id: 'sac-lag',
  label: 'Plain RL (SAC-Lag)',
  blurb: 'A trained agent that learned to charge when power is cheap. Nothing stops it.',
  learned: true,
  command: (ctx) => learnedRequest(ctx),
};

/**
 * SafeSAC is trained with the safety layer already in the loop, so its policy is not
 * the same policy as SAC-Lag's. It never had to learn to be careful with voltage —
 * something else was guaranteeing that — so what it learned instead was to take every
 * kilowatt it could get and let the projection decide how much that is.
 *
 * That is why it is modelled here as "ask for everything, keep what is safe" rather
 * than as SAC-Lag's request with a filter bolted on. An agent that trains against a
 * constraint stops spending its capacity avoiding the constraint.
 */
/**
 * SafeSAC with the band tightening left as a parameter.
 *
 * A factory rather than a constant because the margin is the one number worth sweeping:
 * it is where a learner discovers that safety has an optimum rather than a direction.
 * `safeSac` below is this, at the value the thesis used, so the controller the lesson
 * runs and the controller the sweep runs are the same object built twice — there is no
 * second implementation to fall out of step.
 *
 * `marginPu` defaults rather than being required because `MARGIN_PU` is declared further
 * down the module, and a default is read at call time where an argument would be read at
 * definition time and find it still in its temporal dead zone.
 */
export function safeSacWithMargin(marginPu) {
  return {
    id: marginPu === undefined ? 'safesac' : `safesac@${marginPu}`,
    label: 'SafeSAC',
    blurb: 'Asks for everything, and a safety layer trims it to the most the grid can take.',
    learned: true,
    projection: true,
    marginPu,
    command: (ctx) => {
      const request = ctx.caps.map((cap) => cap.maxDrawKw);
      const limits = ctx.caps.map((cap) => ({ lo: cap.maxDrawKw, hi: cap.maxInjectKw }));
      return projectCommand(ctx.sens, request, limits, marginPu ?? MARGIN_PU).safeKw;
    },
  };
}

export const safeSac = safeSacWithMargin();

/** Everything above, in the order the lesson introduces it. */

export const CONTROLLERS = [uncoordinated, droop, plainRl, safeSac];
export const byId = (id) => CONTROLLERS.find((c) => c.id === id) ?? uncoordinated;

/* ================================================================== */
/*  The safety projection                                             */
/* ================================================================== */

/** The band is tightened by this much before projecting, as the thesis does. */
export const MARGIN_PU = 0.010;

/**
 * The smallest change to a requested command that keeps every bus inside the band.
 *
 * The voltage model is linear *about an operating point*:
 *
 *     v(u)  ~=  v0  +  S . (u - u0)
 *
 * where `u0` is the command the sensitivities were measured at and `v0` the voltages
 * that command produced. Getting that offset wrong is not a rounding error — measure
 * about a busy operating point and then treat `v0` as the idle voltage, and the safe
 * set shrinks by the entire effect of `u0`, so the layer curtails about twice as hard as
 * it needs to and the controller looks far more timid than it is.
 *
 * Folding the offset in gives the voltage this bus would sit at with the stations doing
 * nothing at all,
 *
 *     vIdle  =  v0  -  S . u0        and then       v(u)  ~=  vIdle  +  S . u
 *
 * which is worth writing out because it is also the right reference for the degenerate
 * case. When a bus is already outside the band with no charging on it, no command can
 * bring it back, and the constraint has to degrade from "restore it" to "do not make it
 * worse". Worse than *idle* — not worse than whatever the layer happened to allow last
 * step, which would let it ratchet down and call each new low the new normal.
 *
 * With that in hand the safe set
 *
 *     { u : lo <= vIdle + S.u <= hi,  uMin <= u <= uMax }
 *
 * is an intersection of half-spaces and a box — a polytope. Dykstra's alternating
 * projection cycles through them, each with a closed-form projection, and converges to
 * the true Euclidean projection onto the intersection rather than to merely any
 * feasible point. That distinction is what makes this "the least curtailment that is
 * safe" instead of "some curtailment that is safe".
 *
 * The thesis solves the same program as a second-order cone problem with CVXPY. That is
 * the right tool on a GPU over days of training; in a browser, with four stations and
 * about seventy constraints, this is the right one and runs in tens of microseconds.
 */
export function projectCommand(sens, requestKw, limits, marginPu = MARGIN_PU) {
  const n = requestKw.length;
  const lower = BAND_LO + marginPu;
  const upper = BAND_HI - marginPu;
  const u0 = sens.u0 ?? new Array(n).fill(0);

  // Build one ceiling and one floor constraint per bus the stations can move.
  const rows = [];
  for (let bus = 1; bus < sens.v0.length; bus++) {
    const a = new Float64Array(n);
    let scale = 0;
    for (let k = 0; k < n; k++) { a[k] = sens.dvdp[k][bus]; scale += Math.abs(a[k]); }
    if (scale < 1e-12) continue;

    // Voltage here with the stations idle, which is what the constraints are written
    // against. `max(0, ...)` is the degenerate case: already out of band before anyone
    // charged, so hold at idle rather than pretend it can be fixed from here.
    const vIdle = sens.v0[bus] - dotArr(a, u0);
    rows.push({ a, b: Math.max(0, upper - vIdle), aa: dot(a, a) });

    const neg = new Float64Array(n);
    for (let k = 0; k < n; k++) neg[k] = -a[k];
    rows.push({ a: neg, b: Math.max(0, vIdle - lower), aa: dot(neg, neg) });
  }

  const setCount = rows.length + 1;          // set 0 is the box
  const x = Array.from(requestKw);
  const corr = Array.from({ length: setCount }, () => new Array(n).fill(0));
  const y = new Array(n).fill(0);
  const cycleStart = new Array(n).fill(0);

  for (let iter = 0; iter < 2000; iter++) {
    for (let k = 0; k < n; k++) cycleStart[k] = x[k];

    for (let set = 0; set < setCount; set++) {
      const c = corr[set];
      for (let k = 0; k < n; k++) y[k] = x[k] + c[k];

      if (set === 0) {
        for (let k = 0; k < n; k++) {
          const clamped = Math.min(limits[k].hi, Math.max(limits[k].lo, y[k]));
          c[k] = y[k] - clamped;
          x[k] = clamped;
        }
        continue;
      }

      const row = rows[set - 1];
      const excess = dotArr(row.a, y) - row.b;
      if (excess > 0) {
        const step = excess / row.aa;
        for (let k = 0; k < n; k++) {
          const projected = y[k] - step * row.a[k];
          c[k] = y[k] - projected;
          x[k] = projected;
        }
      } else {
        for (let k = 0; k < n; k++) { c[k] = 0; x[k] = y[k]; }
      }
    }

    // Dykstra's iterate keeps moving inside a cycle even once settled, because each set
    // hands its correction to the next. Convergence is displacement across a whole
    // cycle, not distance travelled within one.
    let shift = 0;
    for (let k = 0; k < n; k++) shift = Math.max(shift, Math.abs(x[k] - cycleStart[k]));
    if (shift < 1e-6) break;
  }

  const safeKw = x.map((v) => (Math.abs(v) < 1e-9 ? 0 : v));
  return { safeKw, curtailedKw: safeKw.map((v, k) => requestKw[k] - v) };
}

function dot(a, b) { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; }
function dotArr(a, b) { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; }
