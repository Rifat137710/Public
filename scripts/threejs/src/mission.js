/**
 * The six-stage arc, translated from the website into things you do with your legs.
 *
 * The website could teach a stage with a card and a chart. A walkable city has no
 * business doing that — if the lesson can be read sitting still, the 3D build has not
 * earned its existence. So every objective here requires being somewhere: at the desk,
 * out past bus 9 at the evening peak, standing under a lamp while it browns out.
 *
 * The stages force a controller and a moment; what they never do is tell you what you
 * are about to see. Stage 2 does not say "the far end is worse" — it asks you to read
 * three meters on the way out, and lets the gradient say it.
 */

import { WORLD, BAND_LO, place, vMag } from './core.js';

const runById = (id) => WORLD.runs.findIndex((r) => r.id === id);
const RUN = {
  uncoordinated: runById('uncoordinated'),
  droop: runById('droop'),
  sacLag: runById('sac-lag'),
  safeSac: runById('safesac'),
};

/** Frames either side of the evening peak, where the day actually hurts. */
const PEAK_LO = 108;   // 18:00
const PEAK_HI = 143;   // 23:55
const isPeak = (i) => i >= PEAK_LO && i <= PEAK_HI;

/** Buses far enough out that the drop has had room to accumulate. */
const isFarBus = (bus) => (place.get(bus)?.col ?? 0) >= 8;

const kwh = (n) => n.toFixed(0) + ' kWh';
const pct = (n) => (n * 100).toFixed(1) + '%';
const drivers = (soc) => Math.round(soc * 287);

export const STAGES = [
  {
    n: 1,
    eyebrow: 'You drive',
    title: 'One evening, four stations, no help',
    brief: [
      'You are the operator on duty. Thirty-three streets hang off one substation, and the far end of the line is a long way from it.',
      'Two hundred and eighty-seven vehicles will plug in tonight. The four consoles on the desk in front of you decide how hard each station pulls. Negative charges the cars; positive sends power back.',
      'There is no safety system running. It is just you. Take all four consoles off the controller, get the town through the evening peak, and then go outside and look at what you did.',
    ],
    setup: (api) => { api.setRun(RUN.uncoordinated); api.setFrame(60); api.clearManual(); },
    objectives: [
      { id: 'take', text: 'Take all four station consoles off the controller', done: (s) => s.manual.every((m) => m !== null) },
      { id: 'peak', text: 'Run the day through the evening peak (21:00)', done: (s) => s.reachedPeak },
      { id: 'look', text: 'Walk out to bus 18 and read the street meter', done: (s) => s.metersRead.has(18) },
    ],
    debrief: (s) => [
      `Your worst moment was ${s.worstV.toFixed(4)} pu, and ${s.violSteps} of the steps you ran had at least one bus outside the legal band.`,
      s.worstV < BAND_LO
        ? 'So the far end went under. That is the ordinary outcome: you charged hard enough to be worth plugging into, and the voltage at the end of the line paid for it. The same command is mild at bus 2 and unlivable at bus 18, and four sliders give you no way to say that.'
        : 'You kept every bus inside the band all evening. Now check what it cost: the only dependable way to do that with four sliders is to charge nobody, and a station that never draws is a car park full of people who go home with the charge they arrived with.',
      'That tension is the whole problem. Everything you are about to watch is an attempt to resolve it.',
    ],
  },

  {
    n: 2,
    eyebrow: 'No coordination',
    title: 'What happens when nobody is steering',
    brief: [
      'Hand the consoles back. Every station now charges whatever is plugged in, as fast as it can, the moment it arrives — which is what actually happens on a feeder with no control scheme at all.',
      'Then walk. Start at the substation gate and follow the line out past bus 9, reading meters as you go. Three of them, past the ninth pole.',
      'Do it during the evening peak, while the town is pulling hardest.',
    ],
    // Deliberately does *not* clear the manual settings: stage 1 required taking all
    // four consoles, so handing them back is a real action the learner performs. A
    // setup that cleared them would tick its own first objective before you arrived.
    setup: (api) => { api.setRun(RUN.uncoordinated); api.setFrame(120); },
    objectives: [
      { id: 'auto', text: 'Give all four stations back to the controller', done: (s) => s.manual.every((m) => m === null) },
      {
        id: 'walk',
        text: 'Read three meters past bus 9, at the evening peak',
        done: (s) => s.peakFarReads.size >= 3,
        progress: (s) => `${s.peakFarReads.size} of 3`,
      },
      { id: 'ack', text: 'Acknowledge the alarms on the annunciator', done: (s) => s.ackedInStage > 0 },
    ],
    debrief: () => {
      const u = WORLD.runs[RUN.uncoordinated];
      return [
        `Across the day this costs ${kwh(u.totalLossKwh)} burnt in the lines and puts a bus outside the band ${pct(u.violationRate)} of the time. Worst point on the feeder: ${u.vMinPu.toFixed(4)} pu.`,
        'You did not have to be told the far end was worse — you watched it get worse with every pole you passed. The drop accumulates along the line, so the same fleet behaviour is harmless at bus 2 and unlivable at bus 18.',
        'It also served almost everybody: ' + drivers(u.socMet) + ' of 287 drivers left with the charge they came for. Uncoordinated charging is not stupid. It is one-sided.',
      ];
    },
  },

  {
    n: 3,
    eyebrow: 'The standard answer',
    title: 'Written down in IEEE 1547',
    brief: [
      'Droop control is the answer the industry already agreed on. Every station watches its own local voltage and backs off in proportion as that voltage falls. No communication, no model, no training — a straight line on a graph, implemented in a box on a pole.',
      'Put the feeder on droop and go back to the two buses you just read. Bus 9 and bus 18, the same evening, the same fleet.',
    ],
    setup: (api) => { api.setRun(RUN.droop); api.setFrame(127); api.clearManual(); },
    objectives: [
      { id: 'sel', text: 'Put the feeder on Droop (IEEE 1547)', done: (s) => s.runIndex === RUN.droop },
      { id: 'b9', text: 'Read bus 9 under droop', done: (s) => s.readUnder(RUN.droop, 9) },
      { id: 'b18', text: 'Read bus 18 under droop', done: (s) => s.readUnder(RUN.droop, 18) },
    ],
    debrief: () => {
      const u = WORLD.runs[RUN.uncoordinated], d = WORLD.runs[RUN.droop];
      return [
        `Same day, same cars: worst bus goes from ${u.vMinPu.toFixed(4)} pu to ${d.vMinPu.toFixed(4)} pu, violations from ${pct(u.violationRate)} to ${pct(d.violationRate)}, and line losses from ${kwh(u.totalLossKwh)} to ${kwh(d.totalLossKwh)}.`,
        `Now the other column. Drivers served falls from ${drivers(u.socMet)} to ${drivers(d.socMet)} out of 287. Droop bought safety by refusing service, and it refused it hardest exactly where the voltage was lowest — which is the far end, which is where the people who most need a charge live.`,
        'It is a good answer. It is not a free one, and it distributes its cost unevenly.',
      ];
    },
  },

  {
    n: 4,
    eyebrow: 'So put a neural network on it',
    title: 'The agent that wins on the average',
    brief: [
      'A soft actor-critic agent with a Lagrangian penalty on constraint violation. It sees the whole feeder, not just one bus, and it optimises the trade-off droop had to hard-code.',
      'It scores well. Go and find the moment it does not — stay on the feeder until a bus drops below the floor, and read the meter where it hurts most.',
    ],
    setup: (api) => { api.setRun(RUN.sacLag); api.setFrame(112); },
    objectives: [
      { id: 'sel', text: 'Put the feeder on SAC-Lag', done: (s) => s.runIndex === RUN.sacLag },
      { id: 'catch', text: 'Be outside when a bus falls below 0.95 pu', done: (s) => s.caughtViolation },
      { id: 'worst', text: 'Read the meter at the worst bus while it is sagging', done: (s) => s.readWorstDuringViolation },
    ],
    debrief: () => {
      const a = WORLD.runs[RUN.sacLag], d = WORLD.runs[RUN.droop];
      return [
        `Averaged over the day it looks respectable. Step by step it is not: violations ${pct(a.violationRate)} against droop's ${pct(d.violationRate)}, and a worst point of ${a.vMinPu.toFixed(4)} pu.`,
        `And it served ${drivers(a.socMet)} of 287 — fewer than droop, while breaking the band more often. A penalty term is a preference, not a constraint: the agent is free to trade a violation for reward whenever the arithmetic favours it, and at the evening peak it does.`,
        'This is the failure mode that makes people distrust learned controllers, and they are right to. The fix is not a bigger network.',
      ];
    },
  },

  {
    n: 5,
    eyebrow: 'Safety put back in',
    title: 'The same agent, with the network in the loop',
    brief: [
      'Same policy. The difference is that before any command reaches a station, it is checked against a power-flow projection of what it would do to the feeder, and clipped if it would push a bus out of band.',
      'The guarantee no longer comes from the reward function. It comes from the network model.',
      'Check both halves of the claim: that the cars are still being served, and that the far end still holds.',
    ],
    setup: (api) => { api.setRun(RUN.safeSac); api.setFrame(127); },
    objectives: [
      { id: 'sel', text: 'Put the feeder on SafeSAC', done: (s) => s.runIndex === RUN.safeSac },
      { id: 'svc', text: 'Open a station console and check cars are still charging', done: (s) => s.consolesOpened.size > 0 },
      { id: 'hold', text: 'Read bus 18 and confirm it holds the band', done: (s) => s.readUnder(RUN.safeSac, 18) },
    ],
    debrief: () => {
      const s5 = WORLD.runs[RUN.safeSac], d = WORLD.runs[RUN.droop], a = WORLD.runs[RUN.sacLag];
      return [
        `Violations ${pct(s5.violationRate)} — lower than droop's ${pct(d.violationRate)} and a third of SAC-Lag's ${pct(a.violationRate)}. Worst bus ${s5.vMinPu.toFixed(4)} pu.`,
        `Drivers served ${drivers(s5.socMet)} of 287, against droop's ${drivers(d.socMet)}. Roughly the same service, materially better safety, and ${kwh(d.totalLossKwh - s5.totalLossKwh)} less burnt in the lines across the day.`,
        'Both objectives at once, which is what the projection buys. It is also the only one of these four whose safety claim survives a step you have never seen before.',
      ];
    },
  },

  {
    n: 6,
    eyebrow: 'The procurement call',
    title: 'Now pick one to deploy',
    brief: [
      'You are the engineer on the procurement call. Four candidates, and the table has the two columns a manager always asks for: how often does it break the rules, and what does it cost.',
      'The terminal is by the door of the control room. Read it and choose the one you would put on a real feeder.',
    ],
    setup: () => {},
    objectives: [
      { id: 'term', text: 'Go to the procurement terminal in the control room', done: (s) => s.atTerminal || s.picked !== null },
      { id: 'pick', text: 'Choose a controller to deploy', done: (s) => s.picked !== null },
    ],
    debrief: (s) => {
      const c = WORLD.candidates[s.picked] ?? WORLD.candidates[0];
      const trap = WORLD.candidates.findIndex((x) => x.id === 'sac-lag-shift');
      const best = WORLD.candidates[trap];
      const lines = [];
      if (s.picked === trap) {
        lines.push(
          `You deployed ${best.label}. It has the best safety score on the board — ${best.violationRate.toFixed(3)} — and it is the only candidate that makes money, at $${Math.abs(best.netCostUsd)} of profit.`,
          `It also served ${drivers(best.socMet)} drivers out of 287. Not few. None.`,
          'It was trained on a stiff grid where charging hard was almost free. Deployed here, the only policy it knows that satisfies its learned constraint is to refuse everybody — and refusing everybody is perfectly safe, perfectly cheap, and perfectly useless. Both columns you were shown reward it for that.',
          'This is distribution shift, and this is why the two columns on a procurement table are not enough. The column that would have caught it — drivers served — was not on the table.',
        );
      } else {
        lines.push(
          `You deployed ${c.label}: violations ${c.violationRate.toFixed(3)}, ${drivers(c.socMet)} of 287 drivers served, $${c.netCostUsd} net.`,
          `You passed over ${best.label}, which posted the best safety score on the board (${best.violationRate.toFixed(3)}) and the only profit. Look at what it actually did: ${drivers(best.socMet)} drivers served out of 287.`,
          'It was trained on a stiff grid. Deployed here, the only way it knows to satisfy its learned constraint is to charge nobody — which scores perfectly on both columns it was judged by, and fails at the job.',
          'Whether you avoided it deliberately or by luck, the point stands: a table with a safety column and a cost column cannot distinguish a good controller from one that does nothing.',
        );
      }
      return lines;
    },
  },
];

/**
 * Tracks what the learner has actually done. Objectives read this and nothing else,
 * so a stage can never be completed by a state the player did not reach themselves.
 */
export class Progress {
  constructor(api) {
    this.api = api;
    this.stageIndex = 0;
    this.phase = 'brief';           // brief -> running -> debrief
    this.reset();
    this.picked = null;
  }

  reset() {
    this.metersRead = new Set();
    this.readsByRun = new Map();    // runIndex -> Set(bus)
    this.peakFarReads = new Set();
    this.consolesOpened = new Set();
    this.ackedInStage = 0;
    this.maxFrame = 0;
    this.reachedPeak = false;
    this.worstV = 1;
    this.violSteps = 0;
    this.caughtViolation = false;
    this.readWorstDuringViolation = false;
    this.atTerminal = false;
  }

  get stage() { return STAGES[this.stageIndex]; }

  /** The snapshot objectives are tested against. */
  snapshot(live) {
    return {
      ...live,
      metersRead: this.metersRead,
      peakFarReads: this.peakFarReads,
      consolesOpened: this.consolesOpened,
      ackedInStage: this.ackedInStage,
      maxFrame: this.maxFrame,
      reachedPeak: this.reachedPeak,
      worstV: this.worstV,
      violSteps: this.violSteps,
      caughtViolation: this.caughtViolation,
      readWorstDuringViolation: this.readWorstDuringViolation,
      atTerminal: this.atTerminal,
      picked: this.picked,
      readUnder: (runIndex, bus) => this.readsByRun.get(runIndex)?.has(bus) ?? false,
    };
  }

  /** Called every simulated step, so "you were there when it happened" is literal. */
  observeStep({ frameIndex, solution, inside }) {
    this.maxFrame = Math.max(this.maxFrame, frameIndex);
    // Reached, not passed: the day no longer wraps, so a flag set while standing in
    // the peak window cannot be satisfied by letting the clock roll over midnight.
    if (isPeak(frameIndex)) this.reachedPeak = true;
    this.worstV = Math.min(this.worstV, solution.vMin);
    if (solution.violations > 0) {
      this.violSteps++;
      if (!inside) this.caughtViolation = true;
    }
  }

  /** Called when a street meter panel is opened. */
  observeMeter(bus, { runIndex, frameIndex, solution }) {
    this.metersRead.add(bus);
    if (!this.readsByRun.has(runIndex)) this.readsByRun.set(runIndex, new Set());
    this.readsByRun.get(runIndex).add(bus);
    if (isPeak(frameIndex) && isFarBus(bus)) this.peakFarReads.add(bus);
    if (solution.violations > 0 && bus === solution.vMinBus) this.readWorstDuringViolation = true;
  }

  observeConsole(si) { this.consolesOpened.add(si); }
  observeAck(n) { this.ackedInStage += n; }
  observeTerminal() { this.atTerminal = true; }

  /** Objectives with their current pass/fail, in order. */
  status(live) {
    const s = this.snapshot(live);
    return this.stage.objectives.map((o) => ({
      id: o.id,
      text: o.text,
      done: !!o.done(s),
      progress: o.progress ? o.progress(s) : null,
    }));
  }

  complete(live) {
    return this.status(live).every((o) => o.done);
  }

  beginStage() {
    this.reset();
    this.phase = 'brief';
    this.stage.setup(this.api);
  }

  next() {
    if (this.stageIndex < STAGES.length - 1) {
      this.stageIndex++;
      this.beginStage();
      return true;
    }
    this.phase = 'finished';
    return false;
  }
}

export { RUN, isPeak, isFarBus };
