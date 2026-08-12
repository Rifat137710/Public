const pptxgen = require('pptxgenjs');

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.3 x 7.5
pres.author = 'Md. Rifat Rahman';
pres.title = 'Bus 18 — IEEE Metaverse Grand Challenge 2026';

// The product's own palette. The deck and the video should look like one artifact.
const NIGHT = '0A0E13';
const PANEL = '141C25';
const PANEL2 = '1B2733';
const INK = 'DDE5EA';
const INK2 = '93A6B3';
const INK3 = '6B808F';
const TEAL = '4FB3A2';
const LAMP = 'E3B24F';   // window light — the motif
const LIMIT = 'E4776B';  // the statutory band

const H = 'Cambria';
const B = 'Calibri';

/** The motif: a run of lamps down the feeder, dimming as you get further out. */
function lampRun(slide, x, y, count, size, opts = {}) {
  const step = opts.step || 0.42;
  for (let i = 0; i < count; i++) {
    const t = i / (count - 1);
    slide.addShape(pres.ShapeType.ellipse, {
      x: x + i * step,
      y,
      w: size,
      h: size,
      fill: { color: t > 0.72 ? LIMIT : LAMP, transparency: Math.round(t * 78) },
      line: { type: 'none' },
    });
  }
}

function bg(slide, color) {
  slide.background = { color };
}

/* ------------------------------------------------------------------ 1 */

const s1 = pres.addSlide();
bg(s1, NIGHT);

s1.addText('IEEE METAVERSE GRAND CHALLENGE 2026', {
  x: 0.9, y: 0.72, w: 8, h: 0.3, margin: 0,
  fontFace: B, fontSize: 12, bold: true, color: TEAL, charSpacing: 2.4,
});

s1.addText('Sustainable Smart Cities and Urban Innovation', {
  x: 0.9, y: 1.06, w: 9, h: 0.34, margin: 0,
  fontFace: B, fontSize: 15, color: INK2,
});

s1.addText('Bus 18', {
  x: 0.9, y: 1.72, w: 8.4, h: 1.15, margin: 0,
  fontFace: H, fontSize: 66, bold: true, color: INK,
});

s1.addText(
  'A weak rural feeder, 287 electric cars, and a voltage band you are not allowed to leave.',
  { x: 0.9, y: 2.94, w: 8.4, h: 0.72, margin: 0, fontFace: H, fontSize: 20, color: INK2, italic: true },
);

s1.addText(
  'A browser trainer that teaches operators to distrust a safety number until they have seen what it cost in service.',
  { x: 0.9, y: 3.76, w: 7.9, h: 0.7, margin: 0, fontFace: B, fontSize: 15, color: INK2, lineSpacing: 22 },
);

// The feeder going dark, left to right.
lampRun(s1, 0.9, 5.06, 14, 0.22, { step: 0.44 });
s1.addText('substation', {
  x: 0.86, y: 5.36, w: 1.6, h: 0.26, margin: 0, fontFace: B, fontSize: 10, color: INK3,
});
s1.addText('bus 18 — the far end', {
  x: 5.3, y: 5.36, w: 2.4, h: 0.26, margin: 0, fontFace: B, fontSize: 10, color: LIMIT, align: 'right',
});

s1.addShape(pres.ShapeType.roundRect, {
  x: 9.55, y: 1.72, w: 2.85, h: 2.52, rectRadius: 0.06,
  fill: { color: PANEL }, line: { color: '25323E', width: 1 },
});
s1.addText(
  [
    { text: 'Built on', options: { fontSize: 11, color: INK3, breakLine: true } },
    { text: 'IEEE 33-bus\nBaran–Wu feeder', options: { fontSize: 17, color: INK, bold: true, breakLine: true } },
    { text: '\nLive backward/forward\nsweep power flow —\nnot an animation.', options: { fontSize: 12, color: INK2 } },
  ],
  { x: 9.82, y: 1.98, w: 2.35, h: 2.0, margin: 0, fontFace: B, lineSpacing: 17 },
);

s1.addText('Md. Rifat Rahman  ·  BUET EEE  ·  solo entrant', {
  x: 0.9, y: 6.24, w: 6.5, h: 0.3, margin: 0, fontFace: B, fontSize: 12, color: INK3,
});
s1.addText('rifat137710.github.io/Public', {
  x: 7.4, y: 6.24, w: 5, h: 0.3, margin: 0, fontFace: B, fontSize: 12, color: TEAL, align: 'right',
});
s1.addNotes(
  'Theme: Sustainable Smart Cities and Urban Innovation. Bus 18 is a browser-based ' +
  'simulation trainer built on the IEEE 33-bus benchmark distribution feeder.',
);

/* ------------------------------------------------------------------ 2 */

const s2 = pres.addSlide();
bg(s2, NIGHT);

s2.addText('A neural network lost to a rule from 1547', {
  x: 0.9, y: 0.62, w: 11.5, h: 0.72, margin: 0,
  fontFace: H, fontSize: 38, bold: true, color: INK,
});

s2.addText(
  'Mass EV charging on a weak feeder pulls voltage down hardest where people are furthest from the substation. ' +
  'Two objectives pull against each other: keep the grid legal, and get everybody charged.',
  { x: 0.9, y: 1.52, w: 5.9, h: 1.0, margin: 0, fontFace: B, fontSize: 14, color: INK2, lineSpacing: 21 },
);

const rows = [
  ['Uncoordinated', 'Everyone charges at once.', '0.319 illegal · 0.983 served', LIMIT],
  ['IEEE 1547 droop', 'Each station watches its own bus.', '0.045 illegal · 0.564 served', INK2],
  ['Plain deep RL', 'Full state, millions of steps.', '0.057 illegal · 0.265 served', LIMIT],
  ['Shielded RL', 'Network physics in the loop.', '0.016 illegal · 0.554 served', TEAL],
];

rows.forEach((r, i) => {
  const y = 2.72 + i * 0.86;
  s2.addShape(pres.ShapeType.ellipse, {
    x: 0.9, y: y + 0.14, w: 0.17, h: 0.17,
    fill: { color: r[3] }, line: { type: 'none' },
  });
  s2.addText(r[0], {
    x: 1.24, y, w: 2.3, h: 0.3, margin: 0, fontFace: B, fontSize: 14, bold: true, color: INK,
  });
  s2.addText(r[1], {
    x: 1.24, y: y + 0.3, w: 3.1, h: 0.3, margin: 0, fontFace: B, fontSize: 11.5, color: INK3,
  });
  s2.addText(r[2], {
    x: 4.42, y: y + 0.06, w: 2.4, h: 0.3, margin: 0, fontFace: B, fontSize: 12, color: r[3], align: 'right',
  });
});

// The Pareto plane, drawn as shapes so the geometry is exact.
const PX = 7.55, PY = 2.05, PW = 4.6, PH = 3.35;
s2.addShape(pres.ShapeType.rect, {
  x: PX - 0.35, y: PY - 0.5, w: PW + 0.85, h: PH + 1.35,
  fill: { color: PANEL }, line: { color: '25323E', width: 1 },
});
s2.addText('SAFETY  →  SERVICE', {
  x: PX - 0.12, y: PY - 0.38, w: 3.4, h: 0.26, margin: 0,
  fontFace: B, fontSize: 10, bold: true, color: INK3, charSpacing: 1.6,
});

const px = (v) => PX + (v / 0.35) * PW;
const py = (s) => PY + PH - s * PH;

[0, 0.5, 1].forEach((s) => {
  s2.addShape(pres.ShapeType.line, {
    x: PX, y: py(s), w: PW, h: 0, line: { color: '25323E', width: 1 },
  });
  s2.addText(s.toFixed(1), {
    x: PX - 0.42, y: py(s) - 0.12, w: 0.34, h: 0.24, margin: 0,
    fontFace: B, fontSize: 9, color: INK3, align: 'right',
  });
});

const pts = [
  { v: 0.319, s: 0.983, c: LIMIT, label: 'Uncoordinated', dx: -1.30, dy: 0.10 },
  { v: 0.045, s: 0.564, c: INK2, label: 'Droop', dx: 0.18, dy: 0.12 },
  { v: 0.057, s: 0.265, c: LIMIT, label: 'Plain deep RL', dx: 0.2, dy: 0.02 },
  { v: 0.016, s: 0.554, c: TEAL, label: 'Shielded RL', dx: 0.02, dy: -0.40 },
];

pts.forEach((p) => {
  s2.addShape(pres.ShapeType.ellipse, {
    x: px(p.v) - 0.1, y: py(p.s) - 0.1, w: 0.2, h: 0.2,
    fill: { color: p.c }, line: { type: 'none' },
  });
  s2.addText(p.label, {
    x: px(p.v) + p.dx, y: py(p.s) + p.dy, w: 1.5, h: 0.24, margin: 0,
    fontFace: B, fontSize: 10, color: p.c, align: p.dx < 0 ? 'right' : 'left',
  });
});

s2.addText('violation rate  →', {
  x: PX, y: PY + PH + 0.16, w: 2.2, h: 0.24, margin: 0, fontFace: B, fontSize: 9.5, color: INK3,
});
s2.addText('vehicles served  ↑', {
  x: PX, y: PY + 0.05, w: 2.2, h: 0.24, margin: 0, fontFace: B, fontSize: 9.5, color: INK3,
});
s2.addText(
  'Plain deep RL sits below and to the right of a rule written down in a standards document — beaten on safety and on service at once.',
  { x: PX - 0.3, y: PY + PH + 0.48, w: PW + 0.75, h: 0.5, margin: 0,
    fontFace: B, fontSize: 11, color: INK2, lineSpacing: 15 },
);

s2.addText('Intelligence was not the missing ingredient. The physics was.', {
  x: 0.9, y: 6.5, w: 6.9, h: 0.42, margin: 0,
  fontFace: H, fontSize: 15, italic: true, color: LAMP,
});
s2.addNotes(
  'The credibility beat. This result comes from the underlying research and is ' +
  'reproduced live in the browser on the public benchmark network.',
);

/* ------------------------------------------------------------------ 3 */

const s3 = pres.addSlide();
bg(s3, NIGHT);

s3.addText('Six stages. You fail first.', {
  x: 0.9, y: 0.62, w: 11.5, h: 0.68, margin: 0,
  fontFace: H, fontSize: 38, bold: true, color: INK,
});
s3.addText(
  'The ordering is the pedagogy. Nobody is impressed by a solution to a problem they have not personally felt, so the learner runs the feeder — and fails — before they see a single controller.',
  { x: 0.9, y: 1.42, w: 11.4, h: 0.6, margin: 0, fontFace: B, fontSize: 14, color: INK2, lineSpacing: 20 },
);

const stages = [
  ['1', 'You drive', 'Four stations, no safety layer, 287 cars. Almost nobody threads it.'],
  ['2', 'Uncoordinated', 'Everyone charges on plug-in. Service without safety.'],
  ['3', 'IEEE 1547 droop', 'The standard answer. Safety bought by refusing to operate.'],
  ['4', 'Plain deep RL', 'The obvious modern answer, and it loses. The credibility beat.'],
  ['5', 'Physics restored', 'A projection onto what the live network can survive.'],
  ['6', 'The trap', 'Pick one to deploy — from the two columns a manager gets handed.'],
];

stages.forEach((st, i) => {
  const col = i % 3;
  const row = Math.floor(i / 3);
  const x = 0.9 + col * 3.86;
  const y = 2.28 + row * 1.98;
  s3.addShape(pres.ShapeType.roundRect, {
    x, y, w: 3.5, h: 1.7, rectRadius: 0.05,
    fill: { color: i === 5 ? PANEL2 : PANEL }, line: { color: i === 5 ? LAMP : '25323E', width: 1 },
  });
  s3.addShape(pres.ShapeType.ellipse, {
    x: x + 0.26, y: y + 0.26, w: 0.42, h: 0.42,
    fill: { color: i === 5 ? LAMP : TEAL }, line: { type: 'none' },
  });
  s3.addText(st[0], {
    x: x + 0.26, y: y + 0.29, w: 0.42, h: 0.36, margin: 0,
    fontFace: B, fontSize: 15, bold: true, color: NIGHT, align: 'center',
  });
  s3.addText(st[1], {
    x: x + 0.82, y: y + 0.3, w: 2.5, h: 0.34, margin: 0,
    fontFace: B, fontSize: 15, bold: true, color: INK,
  });
  s3.addText(st[2], {
    x: x + 0.26, y: y + 0.86, w: 3.0, h: 0.68, margin: 0,
    fontFace: B, fontSize: 11.5, color: INK2, lineSpacing: 15,
  });
});

s3.addText(
  'Hands-on means the world itself: grab a charging station where it stands in the village and drag it, and a real power flow re-solves across all 33 buses.',
  { x: 0.9, y: 6.34, w: 11.4, h: 0.5, margin: 0, fontFace: H, fontSize: 14, italic: true, color: LAMP },
);
s3.addNotes('Stage 6 is a procurement table, not a simulation run. It is where the entry lands its argument.');

/* ------------------------------------------------------------------ 4 */

const s4 = pres.addSlide();
bg(s4, NIGHT);

s4.addText('Real physics, in a browser tab', {
  x: 0.9, y: 0.62, w: 11.5, h: 0.68, margin: 0,
  fontFace: H, fontSize: 38, bold: true, color: INK,
});
s4.addText(
  'No server, no install, no headset. Runs on a phone. Every number on screen is computed live from the benchmark network — nothing is pre-rendered.',
  { x: 0.9, y: 1.42, w: 7.5, h: 0.62, margin: 0, fontFace: B, fontSize: 14, color: INK2, lineSpacing: 20 },
);
s4.addText('VERIFIED AGAINST PUBLISHED VALUES\nNOTHING WAS TUNED TO', {
  x: 8.7, y: 1.44, w: 3.7, h: 0.5, margin: 0,
  fontFace: B, fontSize: 9, bold: true, color: INK3, charSpacing: 1.2, align: 'right', lineSpacing: 13,
});

const tech = [
  ['Power flow', 'Backward/forward sweep on the radial IEEE 33-bus feeder. 288 steps per simulated day.'],
  ['Voltage sensitivities', 'dV/dP and dV/dQ re-measured by perturbation on the live network at every control step.'],
  ['The safety layer', "Dykstra projection of the agent's request onto the band polytope. 0.07 ms typical."],
  ['Adaptive gamification', 'Controls stay locked until a stage needs them; every reveal is computed from the run that just happened.'],
  ['Sustainability analytics', 'Line losses surfaced per driver served: 6.0 kWh coordinated against 12.0 uncoordinated.'],
  ['Accessibility', 'Shape-coded charts, flash rate held under the WCAG limit, reduced-motion honoured, keyboard paths throughout.'],
];

tech.forEach((t, i) => {
  const col = i % 2;
  const row = Math.floor(i / 2);
  const x = 0.9 + col * 5.85;
  const y = 2.26 + row * 1.34;
  s4.addShape(pres.ShapeType.ellipse, {
    x, y: y + 0.08, w: 0.16, h: 0.16, fill: { color: TEAL }, line: { type: 'none' },
  });
  s4.addText(t[0], {
    x: x + 0.34, y, w: 5.1, h: 0.3, margin: 0, fontFace: B, fontSize: 14, bold: true, color: INK,
  });
  s4.addText(t[1], {
    x: x + 0.34, y: y + 0.34, w: 5.05, h: 0.72, margin: 0,
    fontFace: B, fontSize: 11.5, color: INK2, lineSpacing: 15,
  });
});

s4.addShape(pres.ShapeType.roundRect, {
  x: 0.9, y: 6.06, w: 11.5, h: 0.86, rectRadius: 0.05,
  fill: { color: PANEL }, line: { color: '25323E', width: 1 },
});
const gates = [
  ['0.9131 pu', 'model Vₘᵢₙ vs 0.913 published'],
  ['202.68 kW', 'model loss vs 202.7 published'],
  ['1.273', 'dominance ratio vs 1.271'],
  ['66', 'assertions on every commit'],
];
gates.forEach((g, i) => {
  const x = 1.2 + i * 2.85;
  s4.addText(g[0], {
    x, y: 6.18, w: 2.6, h: 0.34, margin: 0, fontFace: B, fontSize: 18, bold: true, color: LAMP,
  });
  s4.addText(g[1], {
    x, y: 6.53, w: 2.7, h: 0.28, margin: 0, fontFace: B, fontSize: 10, color: INK3,
  });
});
s4.addNotes('The strong-feeder minimum voltage and loss are published Baran-Wu values that nothing in the model was fitted to.');

/* ------------------------------------------------------------------ 5 */

const s5 = pres.addSlide();
bg(s5, NIGHT);

s5.addText('What it teaches, and how we know', {
  x: 0.9, y: 0.62, w: 11.5, h: 0.68, margin: 0,
  fontFace: H, fontSize: 38, bold: true, color: INK,
});

s5.addShape(pres.ShapeType.roundRect, {
  x: 0.9, y: 1.5, w: 11.5, h: 1.62, rectRadius: 0.06,
  fill: { color: PANEL2 }, line: { color: LAMP, width: 1 },
});
s5.addText('The measurement that matters', {
  x: 1.24, y: 1.72, w: 5, h: 0.3, margin: 0,
  fontFace: B, fontSize: 11, bold: true, color: LAMP, charSpacing: 1.2,
});
s5.addText(
  'Shown only violation rate and cost, engineers deploy the controller with the best safety score on the board — the one that served nobody, all day. It earns that record by never operating, and in the field you never find out, because reality does not hand you the counterfactual.',
  { x: 1.24, y: 2.06, w: 10.8, h: 0.86, margin: 0, fontFace: B, fontSize: 13.5, color: INK, lineSpacing: 19 },
);

const stats = [
  ['__ of __', 'deployed the controller\nthat served nobody'],
  ['__ → __', 'concept score, out of 10\npre and post'],
  ['__', 'System Usability Scale\n(68 is average)'],
  ['~20 min', 'end to end, in a browser,\non any device'],
];
stats.forEach((st, i) => {
  const x = 0.9 + i * 2.95;
  s5.addText(st[0], {
    x, y: 3.48, w: 2.7, h: 0.66, margin: 0, fontFace: B, fontSize: 34, bold: true, color: TEAL,
  });
  s5.addText(st[1], {
    x, y: 4.2, w: 2.7, h: 0.7, margin: 0, fontFace: B, fontSize: 11.5, color: INK2, lineSpacing: 15,
  });
});

s5.addText('Eight stated objectives, each tied to a stage and tested before and after.', {
  x: 0.9, y: 5.06, w: 11.4, h: 0.32, margin: 0, fontFace: B, fontSize: 12.5, color: INK3,
});

lampRun(s5, 0.9, 5.62, 10, 0.16, { step: 0.3 });

s5.addShape(pres.ShapeType.roundRect, {
  x: 0.9, y: 6.06, w: 11.5, h: 0.88, rectRadius: 0.05,
  fill: { color: PANEL }, line: { color: TEAL, width: 1 },
});
s5.addText(
  [
    { text: 'Play it   ', options: { fontSize: 11, color: INK3 } },
    { text: 'rifat137710.github.io/Public', options: { fontSize: 14, color: TEAL, bold: true } },
  ],
  { x: 1.22, y: 6.2, w: 5.4, h: 0.3, margin: 0, fontFace: B },
);
s5.addText(
  [
    { text: 'Source   ', options: { fontSize: 11, color: INK3 } },
    { text: 'github.com/Rifat137710/Public', options: { fontSize: 14, color: TEAL, bold: true } },
  ],
  { x: 6.9, y: 6.2, w: 5.4, h: 0.3, margin: 0, fontFace: B },
);
s5.addText(
  'Prior work: Safe Deep Reinforcement Learning for Vehicle-to-Grid Voltage Support in Weak Distribution Feeders — Md. Rifat Rahman and Sad Sami, BUET EEE, 2026. Cited as prior work, not submitted as the entry.',
  { x: 1.22, y: 6.56, w: 10.9, h: 0.3, margin: 0, fontFace: B, fontSize: 9.5, color: INK3 },
);
s5.addNotes('The blanks are filled from the tester study before submission.');

pres.writeFile({ fileName: '/home/user/Public/docs/bus18-slides.pptx' }).then((f) => {
  console.log('wrote', f);
});
