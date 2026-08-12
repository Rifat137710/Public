/**
 * The lesson page: one live simulation, six things it is used to show, and a scoreboard
 * that recomputes on whatever town the reader has built with the sliders.
 *
 * Every number on screen comes out of `sim.js`, which solves the feeder. There is no
 * scripted animation and no pre-baked result — set the controls to something nobody
 * anticipated and the page still answers honestly, including when the answer is
 * inconvenient for the story it is telling.
 */

import { WORLD, N_BUS } from '../../shared/grid.js';
import { check } from '../../shared/grid.js';
import {
  CONTROLLERS, byId, FLEET_SIZE, STEPS, dayFor, allFor, priceTier, priceAt,
  marginSweep, MARGIN_PU,
} from './sim.js';
import { RESULTS, EVALUATION } from '../../../src/content/evaluation.ts';

const $ = (id) => document.getElementById(id);
const svgns = 'http://www.w3.org/2000/svg';

const el = (name, attrs = {}, text) => {
  const node = document.createElementNS(svgns, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
};

/* ================================================================== */
/*  State                                                             */
/* ================================================================== */

const state = {
  controller: 'uncoordinated',
  size: 200,
  grid: 'weak',
  step: 228,          // 19:00, when the town is at its worst
  playing: false,
};

let timer = null;

/* ================================================================== */
/*  The lessons                                                       */
/* ================================================================== */

const LESSONS = [
  {
    title: 'A town on one wire',
    set: { controller: 'uncoordinated', size: 20, grid: 'weak', step: 228 },
    body: [
      `Thirty-three streets hang off a single line out of one substation. Electricity
       behaves like water in a long pipe: the further along you are, the lower the
       pressure, because every stretch of wire between you and the source drops a little
       of it on the way.`,
      `With almost no electric cars in town, look at the shape anyway. The far end already
       sits lower than the near end. That slope is the whole story of everything that
       follows — it is what a few hundred cars are about to push over the edge.`,
    ],
    ask: 'Which street is the weakest, and why is it that one?',
  },
  {
    title: 'Now put the cars in',
    set: { controller: 'uncoordinated', size: 200, grid: 'weak', step: 228 },
    body: [
      `Two hundred cars, each pulling up to 22 kW, and almost all of them plugged in
       between six and eight in the evening — exactly when the town's own demand peaks.
       Nobody coordinates anything. Everyone charges the moment they arrive.`,
      `Streets turn red. Red means the voltage there is outside the range the utility is
       legally required to keep it inside: lights dim, motors run hot, and equipment ages
       faster than it should. This is not a simulation artefact. It is the reason nobody
       can simply let a neighbourhood full of EVs charge whenever it likes.`,
    ],
    ask: 'Press Play and watch the evening. When does the town break?',
  },
  {
    title: 'The standard answer: droop',
    set: { controller: 'droop', size: 200, grid: 'weak', step: 228 },
    body: [
      `IEEE 1547 is the interconnection standard, and its answer is a rule so simple you
       could build it out of a spring: each charger measures the voltage at its own pole
       and slows down as that voltage falls. No communication, no model, no training.`,
      `It works — the red mostly goes away. Now read the second number. Look at how many
       drivers actually left with the charge they came for. Each station can only see its
       own pole, so it has no way to know that easing off here would let another station
       carry on. When the town is really strained it does something worse than refuse:
       it starts pulling energy back out of the cars.`,
    ],
    ask: 'Compare drivers charged against no control at all. What did safety cost?',
  },
  {
    title: 'Teach a controller instead',
    set: { controller: 'sac-lag', size: 200, grid: 'weak', step: 264 },
    body: [
      `Reinforcement learning replaces the rule with experience. The agent sees the state
       of the grid — voltages, how full each car is, the price — and picks an action: how
       many kilowatts each station should draw. It gets a reward for charging cars cheaply
       and a penalty for breaking the voltage range, and it plays the day over and over
       until it has a policy.`,
      `What it learns is real, and it is not what you asked for. Electricity is expensive
       from five until ten, so the agent waits. At 22:00 the tariff drops and it puts the
       entire fleet on charge in the same instant — building a second peak the town never
       had before. It found the cheap hour. Nobody told it the cheap hour is not the safe
       hour.`,
    ],
    ask: 'Slide time to 22:00. Where did the new peak come from?',
    key: true,
  },
  {
    title: 'Shielded RL: the same agent, with a floor under it',
    set: { controller: 'safesac', size: 200, grid: 'weak', step: 264 },
    body: [
      `A penalty is something an agent can decide to pay. Shielded RL does not use one. At
       every step it measures how much each street's voltage moves per kilowatt at each
       station — the real sensitivity of this feeder, right now, at this loading — and
       from that builds the set of commands that keep every street inside the range.`,
      `Then it takes what the agent asked for and finds the nearest point in that set.
       Not a safe command: the <em>closest</em> safe command, so the agent gives up as
       little as it possibly can. The request goes through untouched when it is already
       fine, and is trimmed exactly as much as necessary when it is not.`,
      `This is why it beats the standard on both counts at once. Droop keeps the town safe
       by refusing to serve; Shielded RL works out how much it can serve, so it charges hard
       whenever there is room and eases off only where the physics says it must.`,
      `It is not perfect, and the scoreboard will not pretend it is. The safe set is built
       from a straight-line approximation of a curved system, so at the very worst moment
       of the evening a street can still slip a thousandth of a volt under the line. What
       it does not do is spend hours out of range, which is what everything above it on
       this page does.`,
    ],
    ask: 'Read both numbers against droop. Better safety and more drivers, at the same time.',
    key: true,
  },
  {
    title: 'Or you could just build a thicker wire',
    set: { controller: 'safesac', size: 287, grid: 'strong', step: 264 },
    body: [
      `The line into town is the one thing here that is not about control at all. Switch it
       from thin to thick and the substation stops sagging under its own load. Every
       controller improves, because the problem itself got smaller.`,
      `That is the engineering decision underneath all of this. Safety can be bought with
       control or bought with copper, and they cost money in completely different places —
       one is software on a substation computer, the other is a construction project. A
       comparison of controllers alone will never show you that choice, which is exactly
       why it is worth making sure you can see it.`,
    ],
    ask: 'Try every controller on the thick line, then switch back to thin.',
  },
];

/* ================================================================== */
/*  The measured evaluation of the trained agents                     */
/* ================================================================== */

/**
 * Imported from the trainer's copy rather than re-typed here. These numbers appear on
 * two builds and in a paper; three transcriptions of the same CSV is two too many, and
 * the one that drifts will be the one nobody re-checks.
 */
const EVAL_NOTE = {
  uncoord: 'charges nearly everyone, and breaks the range most often',
  droop: 'safe by turning away two drivers in three',
  'sac-lag': 'dominated by the standard — worse on both counts',
  safesac: 'twice Plain RL’s drivers at the same violation rate',
  'safesac-shift': 'moved to a grid it never trained on: degrades, keeps serving',
  'sac-lag-shift': 'best safety score in the report, and zero kWh into any battery',
};

/* ================================================================== */
/*  Controls                                                          */
/* ================================================================== */

function buildControllerButtons() {
  const seg = $('ctrlSeg');
  for (const c of CONTROLLERS) {
    const b = document.createElement('button');
    b.textContent = c.label;
    b.dataset.id = c.id;
    b.title = c.blurb;
    b.setAttribute('aria-pressed', String(c.id === state.controller));
    b.addEventListener('click', () => { state.controller = c.id; sync(); });
    seg.appendChild(b);
  }
}

function sync({ recompute = true } = {}) {
  for (const b of $('ctrlSeg').children) {
    b.setAttribute('aria-pressed', String(b.dataset.id === state.controller));
  }
  for (const b of $('gridSeg').children) {
    b.setAttribute('aria-pressed', String(b.dataset.grid === state.grid));
  }
  $('cars').value = String(state.size);
  $('carsVal').textContent = state.size;
  $('clock').value = String(state.step);
  $('playBtn').textContent = state.playing ? '❚❚ Pause' : '▶ Play';

  const day = dayFor(state.controller, state.size, state.grid);
  const now = day.steps[state.step];
  $('clockVal').textContent = now.clock;

  drawTown(now);
  drawProfile(now);
  drawReadouts(day, now);
  if (recompute) drawBoard();
}

/* ================================================================== */
/*  Drawing                                                           */
/* ================================================================== */

const PLACE = new Map(WORLD.places.map((p) => [p.bus, p]));
const PARENT = new Map(WORLD.branches.map((b) => [b.to, b.from]));
const STATION_BUSES = WORLD.stations;
const X = (col) => 34 + col * (556 / 17);
const Y = (row) => 150 + row * 62;

function colourFor(v) {
  if (v >= 0.95) return 'var(--ok)';
  if (v >= 0.93) return 'var(--amber)';
  return 'var(--warn)';
}

function drawTown(now) {
  const svg = $('town');
  svg.replaceChildren();

  // Branches first, so the buses sit on top of them.
  for (const b of WORLD.branches) {
    const a = PLACE.get(b.from), c = PLACE.get(b.to);
    if (!a || !c) continue;
    svg.appendChild(el('line', {
      x1: X(a.col), y1: Y(a.row), x2: X(c.col), y2: Y(c.row),
      stroke: 'var(--line)', 'stroke-width': 2.5, 'stroke-linecap': 'round',
    }));
  }

  // The substation, and the line in from it — thick or thin, as chosen.
  const first = PLACE.get(1);
  svg.appendChild(el('line', {
    x1: 8, y1: Y(0), x2: X(first.col), y2: Y(first.row),
    stroke: 'var(--dim)', 'stroke-width': state.grid === 'strong' ? 7 : 2,
    'stroke-linecap': 'round',
  }));
  svg.appendChild(el('rect', { x: 0, y: Y(0) - 11, width: 15, height: 22, rx: 3, fill: 'var(--dim)' }));
  svg.appendChild(el('text', {
    x: 7, y: Y(0) + 30, 'text-anchor': 'middle', fill: 'var(--dim)', 'font-size': 10,
  }, 'grid'));

  for (const p of WORLD.places) {
    const v = now.v[p.bus];
    const station = STATION_BUSES.indexOf(p.bus);
    const x = X(p.col), y = Y(p.row);

    if (station >= 0) {
      svg.appendChild(el('rect', {
        x: x - 7, y: y - 7, width: 14, height: 14, rx: 2.5,
        fill: colourFor(v), stroke: 'var(--panel)', 'stroke-width': 1.5,
      }));
      // How hard this station is being driven, as a bar under it.
      const kw = now.kw[station];
      const mag = Math.min(1, Math.abs(kw) / 900);
      if (mag > 0.01) {
        svg.appendChild(el('rect', {
          x: x - 7, y: y + 10, width: 14 * mag, height: 3.5, rx: 1.5,
          fill: kw < 0 ? 'var(--cool)' : 'var(--accent)',
        }));
      }
      svg.appendChild(el('text', {
        x, y: y - 12, 'text-anchor': 'middle', fill: 'var(--dim)', 'font-size': 9.5,
      }, `S${station + 1}`));
    } else {
      svg.appendChild(el('circle', {
        cx: x, cy: y, r: p.bus === 1 ? 6 : 4.5, fill: colourFor(v),
      }));
    }
  }

  // Name only the worst street, so the eye has one thing to find.
  const worst = PLACE.get(now.vMinBus);
  if (worst) {
    svg.appendChild(el('text', {
      x: X(worst.col), y: Y(worst.row) + 20, 'text-anchor': 'middle',
      fill: 'var(--warn)', 'font-size': 10, 'font-weight': 600,
    }, `${now.vMin.toFixed(3)}`));
  }
}

const P_LO = 0.82, P_HI = 1.03;
function drawProfile(now) {
  const svg = $('profile');
  svg.replaceChildren();
  const L = 44, R = 372, T = 12, B = 186;
  const px = (i) => L + ((i - 1) / (N_BUS - 1)) * (R - L);
  const py = (v) => B - ((v - P_LO) / (P_HI - P_LO)) * (B - T);

  // The legal band, drawn as ground rather than as a pair of lines.
  svg.appendChild(el('rect', {
    x: L, y: py(1.05), width: R - L, height: Math.max(0, py(0.95) - py(1.05)),
    fill: 'var(--ok)', opacity: 0.12,
  }));
  svg.appendChild(el('line', {
    x1: L, y1: py(0.95), x2: R, y2: py(0.95),
    stroke: 'var(--ok)', 'stroke-width': 1.5, 'stroke-dasharray': '4 3',
  }));
  svg.appendChild(el('text', { x: L - 6, y: py(0.95) + 4, 'text-anchor': 'end', fill: 'var(--ok)', 'font-size': 10 }, '0.95'));
  svg.appendChild(el('text', { x: L - 6, y: py(1.0) + 4, 'text-anchor': 'end', fill: 'var(--dim)', 'font-size': 10 }, '1.00'));
  svg.appendChild(el('text', { x: L - 6, y: py(0.86) + 4, 'text-anchor': 'end', fill: 'var(--dim)', 'font-size': 10 }, '0.86'));

  // The feeder is a tree, not a line. Bus 19 hangs off bus 2, so joining it to bus 18
  // would draw a cliff that does not exist and invite the reader to explain it. Each
  // lateral is drawn as its own run, which is also what makes the real shape legible:
  // four chains, each sagging away from wherever it leaves the trunk.
  let d = '';
  for (let bus = 1; bus <= N_BUS; bus++) {
    const startsRun = bus === 1 || PARENT.get(bus) !== bus - 1;
    d += `${startsRun ? 'M' : 'L'}${px(bus).toFixed(1)},${py(now.v[bus]).toFixed(1)}`;
  }
  svg.appendChild(el('path', { d, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 2, 'stroke-linejoin': 'round' }));

  // Mark where each lateral leaves the trunk, so the breaks read as branches. The three
  // marks land within forty units of each other, so the labels are stepped down rather
  // than written on the same line, where they would overlap into noise.
  let lateral = 0;
  for (let bus = 2; bus <= N_BUS; bus++) {
    if (PARENT.get(bus) === bus - 1) continue;
    const x = px(bus) - 5.5;
    svg.appendChild(el('line', {
      x1: x, y1: T, x2: x, y2: B, stroke: 'var(--line)', 'stroke-width': 1, 'stroke-dasharray': '2 3',
    }));
    svg.appendChild(el('text', {
      x: x + 3, y: T + 9 + lateral * 11, fill: 'var(--dim)', 'font-size': 9,
    }, `off ${PARENT.get(bus)}`));
    lateral++;
  }

  for (let bus = 1; bus <= N_BUS; bus++) {
    if (now.v[bus] >= 0.95) continue;
    svg.appendChild(el('circle', { cx: px(bus), cy: py(now.v[bus]), r: 2.6, fill: 'var(--warn)' }));
  }
  for (const bus of STATION_BUSES) {
    svg.appendChild(el('circle', {
      cx: px(bus), cy: py(now.v[bus]), r: 4, fill: 'none',
      stroke: 'var(--cool)', 'stroke-width': 1.8,
    }));
  }

  svg.appendChild(el('text', { x: L, y: 202, fill: 'var(--dim)', 'font-size': 10 }, 'street 1 (nearest)'));
  svg.appendChild(el('text', { x: R, y: 202, 'text-anchor': 'end', fill: 'var(--dim)', 'font-size': 10 }, 'street 33 (furthest)'));
}

function ro(k, v, cls = '') {
  return `<div class="ro ${cls}"><div class="k">${k}</div><div class="v">${v}</div></div>`;
}

function drawReadouts(day, now) {
  const tier = { cheap: 'cheap', day: 'daytime', peak: 'peak' }[priceTier(state.step)];
  $('readouts').innerHTML = [
    ro('Time', now.clock),
    ro(`Electricity (${tier})`, `$${priceAt(state.step).toFixed(2)}`),
    ro('Lowest street', now.vMin.toFixed(3), now.vMin < 0.95 ? 'bad' : 'good'),
    ro('Streets out of range', `${now.viol} / ${N_BUS}`, now.viol > 0 ? 'bad' : 'good'),
    ro('Cars plugged in', now.plugged),
    ro('Drivers charged', `${now.met} / ${day.totals.fleetSize}`),
    ro('Charging now', `${Math.round(now.drawKw)} kW`),
  ].join('');

  $('live').textContent =
    `${now.clock}. Lowest street ${now.vMin.toFixed(3)}, ${now.viol} out of range, ${now.met} drivers charged.`;
}

/* ================================================================== */
/*  Scoreboard                                                        */
/* ================================================================== */

function drawBoard() {
  const runs = allFor(state.size, state.grid);
  const best = {
    viol: Math.min(...runs.map((r) => r.totals.violationRate)),
    met: Math.max(...runs.map((r) => r.totals.driversMet)),
  };

  const head = `<thead><tr>
    <th>Controller</th>
    <th>Streets out of range</th>
    <th>Drivers charged</th>
    <th>Lowest voltage</th>
    <th>Energy wasted as heat</th>
  </tr></thead>`;

  const body = runs.map((r) => {
    const t = r.totals;
    // A row is highlighted when nothing else beats it on both counts at once.
    const dominated = runs.some((o) =>
      o !== r && o.totals.violationRate <= t.violationRate && o.totals.driversMet >= t.driversMet
      && (o.totals.violationRate < t.violationRate || o.totals.driversMet > t.driversMet));
    return `<tr class="${dominated ? '' : 'win'}">
      <td>${r.controller.label}${r.controller.id === state.controller ? ' ←' : ''}</td>
      <td class="num-cell">${(t.violationRate * 100).toFixed(2)}%</td>
      <td class="num-cell">${t.driversMet} / ${t.fleetSize}</td>
      <td class="num-cell">${t.vMinPu.toFixed(3)}</td>
      <td class="num-cell">${Math.round(t.totalLossKwh)} kWh</td>
    </tr>`;
  }).join('');

  $('board').innerHTML = head + `<tbody>${body}</tbody>`;

  const safe = runs.find((r) => r.controller.id === 'safesac').totals;
  const drp = runs.find((r) => r.controller.id === 'droop').totals;
  const rl = runs.find((r) => r.controller.id === 'sac-lag').totals;

  const vs = (a, b) => (a.driversMet > b.driversMet && a.violationRate < b.violationRate);
  const parts = [];
  if (vs(safe, drp)) {
    parts.push(`Shielded RL charges ${safe.driversMet} drivers against droop's ${drp.driversMet},
      and is out of range ${(drp.violationRate / Math.max(safe.violationRate, 1e-9)).toFixed(1)}× less often.`);
  }
  if (vs(safe, rl)) {
    parts.push(`It beats plain RL on both counts too.`);
  } else if (rl.driversMet > safe.driversMet) {
    parts.push(`Plain RL charges more drivers here (${rl.driversMet}) — by breaking the range
      ${(rl.violationRate / Math.max(safe.violationRate, 1e-9)).toFixed(0)}× more often. With this many
      cars on a thin line there is not enough room to serve everybody safely; that is a wire
      problem, and lesson 6 is about it.`);
  }
  // "No control" is genuinely un-beaten on service and will keep being highlighted, which
  // is worth saying out loud rather than quietly excluding: topping the service column by
  // breaking the range a fifth of the time is the whole reason the other column exists.
  const unco = runs.find((r) => r.controller.id === 'uncoordinated').totals;
  parts.push(`Highlighted rows are the ones nothing else beats on both counts at once —
    which includes no control at all, because nothing charges more cars than letting
    everyone charge. It does it while ${(unco.violationRate * 100).toFixed(0)}% of street-hours
    sit outside the legal range, so read the two columns together or not at all.`);
  $('boardNote').innerHTML = parts.join(' ');
}

/* ================================================================== */
/*  Lessons and the evaluation table                                  */
/* ================================================================== */

function buildLessons() {
  const host = $('lessons');
  LESSONS.forEach((l, i) => {
    const sec = document.createElement('section');
    sec.className = 'panel';
    sec.innerHTML = `<div class="lesson ${l.key ? 'key' : ''}">
      <div class="num">${i + 1}</div>
      <div>
        <h2>${l.title}</h2>
        ${l.body.map((p) => `<p>${p}</p>`).join('')}
        <p class="small muted"><strong>Try it:</strong> ${l.ask}</p>
        <button class="try">Set the simulator to this</button>
      </div>
    </div>`;
    sec.querySelector('.try').addEventListener('click', () => {
      Object.assign(state, l.set);
      stop();
      sync();
      $('sim').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    host.appendChild(sec);
  });
}

/* ================================================================== */
/*  What the safety margin buys                                       */
/* ================================================================== */

/**
 * The one control in the whole model that has an optimum rather than a direction.
 *
 * Everything else on this page trades along a line: more cars is worse, a thicker wire
 * is better. The margin does not. Winding it past the value the reference study chose costs
 * drivers *and* lets violations back in, because a safety layer whose own tightened band
 * is already breached stops steering and starts merely refusing. At the far end it is
 * the stage-six trap rebuilt from the inside — a spotless-looking violation rate,
 * achieved by serving nobody.
 *
 * It is a button rather than a slider because seven full days is a second of arithmetic,
 * and because a reader who has pressed for this is a reader who wanted it.
 */
function buildMargin() {
  const btn = $('marginRun');
  btn.addEventListener('click', () => {
    btn.disabled = true;
    btn.textContent = 'Running seven days…';
    // Yielded to the browser so the button's own disabled state paints before the
    // arithmetic locks the thread. Without it the label never changes and a reader on a
    // slow machine believes the click was dropped.
    setTimeout(() => {
      drawMargin(marginSweep(state.size, state.grid));
      btn.disabled = false;
      btn.textContent = 'Run it again on this town';
    }, 16);
  });
}

function drawMargin(rows) {
  const bestServed = Math.max(...rows.map((r) => r.driversMet));
  const bestViol = Math.min(...rows.map((r) => r.violationRate));

  $('marginTable').innerHTML = `<thead><tr>
      <th>Safety margin</th><th>Drivers charged</th><th>Streets out of range</th><th>Lowest voltage</th><th></th>
    </tr></thead><tbody>` +
    rows.map((r) => {
      const note = r.marginPu === MARGIN_PU ? 'the reference setting'
        : r.driversMet === 0 ? 'serves nobody, all day'
        : r.driversMet === bestServed ? 'most drivers'
        : r.violationRate === bestViol ? 'fewest violations' : '';
      return `<tr class="${r.marginPu === MARGIN_PU ? 'win' : ''}">
        <td class="num-cell">${r.marginPu.toFixed(3)} pu</td>
        <td class="num-cell">${r.driversMet === 0 ? '<b>0</b>' : r.driversMet} / ${r.fleetSize}</td>
        <td class="num-cell">${(r.violationRate * 100).toFixed(2)}%</td>
        <td class="num-cell">${r.vMinPu.toFixed(3)}</td>
        <td class="small muted" style="text-align:left">${note}</td>
      </tr>`;
    }).join('') + '</tbody>';

  const turn = rows.find((r) => r.marginPu === MARGIN_PU);
  const worst = rows[rows.length - 1];
  $('marginNote').innerHTML =
    `Read the second and third columns together, down the table. Up to
     ${MARGIN_PU.toFixed(3)} pu, buying safety works: violations fall and the cost is a few
     drivers. Past it both columns get worse at once — tightening the band the layer aims
     for does not make the grid safer, it makes the layer give up sooner. At
     ${worst.marginPu.toFixed(3)} pu it charges
     ${worst.driversMet === 0 ? '<b>nobody at all</b>' : `only ${worst.driversMet}`} and is
     <em>still</em> outside the range ${(worst.violationRate * 100).toFixed(2)}% of the time,
     against ${(turn.violationRate * 100).toFixed(2)}% at the setting that serves
     ${turn.driversMet}. A controller can look flawless on a safety report purely by
     refusing to operate, which is the whole of the last lesson on this page.`;

  $('marginOut').hidden = false;
}

function buildEvaluation() {
  $('evalTable').innerHTML = `<thead><tr>
      <th>Method</th><th>Out of range</th><th>Drivers charged</th><th>Into batteries</th><th>Net cost</th><th></th>
    </tr></thead><tbody>` +
    RESULTS.map((r) => `<tr class="${r.id === 'safesac' ? 'win' : ''}">
      <td>${r.label}</td>
      <td class="num-cell">${(r.violationRate * 100).toFixed(2)}%</td>
      <td class="num-cell">${(r.socMet * 100).toFixed(1)}%</td>
      <td class="num-cell">${r.chargeKwh === 0 ? '<b>0</b>' : Math.round(r.chargeKwh)} kWh</td>
      <td class="num-cell">${r.netCostUsd < 0 ? '−' : ''}$${Math.abs(r.netCostUsd).toFixed(0)}</td>
      <td class="small muted" style="text-align:left">${EVAL_NOTE[r.id] ?? ''}</td>
    </tr>`).join('') + '</tbody>';

  $('evalCaption').textContent =
    `${EVALUATION.episodes} evaluation episodes per method on the weak feeder, shared seeds, `
    + `load scale ${EVALUATION.loadScale.toFixed(2)}.`;
}

/* ================================================================== */
/*  Playback and wiring                                               */
/* ================================================================== */

function stop() {
  state.playing = false;
  if (timer) { clearInterval(timer); timer = null; }
  $('playBtn').textContent = '▶ Play';
}

function play() {
  state.playing = true;
  $('playBtn').textContent = '❚❚ Pause';
  timer = setInterval(() => {
    state.step += 2;
    if (state.step >= STEPS) { state.step = STEPS - 1; stop(); }
    sync({ recompute: false });
  }, 55);
}

function init() {
  buildControllerButtons();
  buildLessons();
  buildMargin();
  buildEvaluation();

  $('cars').addEventListener('input', () => {
    state.size = Number($('cars').value);
    $('carsVal').textContent = state.size;
    sync();
  });
  $('clock').addEventListener('input', () => {
    state.step = Number($('clock').value);
    stop();
    sync({ recompute: false });
  });
  for (const b of $('gridSeg').children) {
    b.addEventListener('click', () => { state.grid = b.dataset.grid; sync(); });
  }
  $('playBtn').addEventListener('click', () => (state.playing ? stop() : play()));
  $('restartBtn').addEventListener('click', () => { stop(); state.step = 0; sync({ recompute: false }); });

  $('selfcheck').textContent =
    `Self-check on load: ${check.n} recorded control steps re-solved in this page, ` +
    `worst disagreement ${check.worstV.toExponential(1)} pu.`;

  sync();
}

init();

// A small surface for the headless check that drives this page.
window.__learn = { state, sync, stop, dayFor, allFor, check, LESSONS, marginSweep };
