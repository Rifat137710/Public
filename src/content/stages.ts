/**
 * The six-stage arc.
 *
 * The ordering is the pedagogy and it is not negotiable. The learner drives first and
 * fails first, and their dot lands on the map before they have seen a single controller
 * solve the problem — because you cannot be impressed by a solution to a problem you
 * have not personally felt.
 *
 * Everything a stage says about numbers is computed from the run that just happened
 * rather than written into the copy, so the text cannot drift away from the simulation.
 */

import type { Dot } from '../ui/ParetoMap.js';

/** Controls stay hidden until a stage needs them. */
export type Unlock =
  | 'map'
  | 'projection'
  | 'grid'
  | 'loadScale'
  | 'compare'
  | 'margin';

export interface RevealContext {
  violationRate: number;
  socMet: number;
  netCostUsd: number;
  vMinPu: number;
  /** Energy lost as heat in the lines across the day, kWh. */
  lossKwh: number;
  /** Dots recorded so far, so a stage can compare against earlier ones. */
  dots: readonly Dot[];
}

export type StageMode = 'manual' | 'watch' | 'choose';

export interface Stage {
  n: number;
  eyebrow: string;
  title: string;
  /** Shown before the stage runs. */
  brief: string[];
  /** One line kept in the top bar for the whole stage. */
  task: string;
  mode: StageMode;
  /** For 'watch' stages, which controller drives. */
  controllerId?: string;
  /** Forced safety-layer setting for this stage, if any. */
  projection?: boolean;
  /** Controls that become available from this stage onward. */
  unlocks: Unlock[];
  revealTitle: string;
  reveal: (ctx: RevealContext) => string[];
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function findDot(dots: readonly Dot[], id: string): Dot | undefined {
  return dots.find((d) => d.id === id);
}

export const STAGES: Stage[] = [
  {
    n: 1,
    eyebrow: 'You drive',
    title: 'One day, four charging stations, no help',
    brief: [
      'You are the operator of a rural feeder. Thirty-three streets hang off one substation, and the far end of the line is a long way from it.',
      'Two hundred and eighty-seven electric vehicles will plug in today. Four sliders decide how much power each station draws. Negative charges the cars; positive sends power back to the grid.',
      'Two things can go wrong. Charge too hard and the voltage at the end of the line collapses and the lights go out. Charge too little and people go home with empty batteries. Every vehicle here can be fully charged in the time it is plugged in, so anyone who leaves short left short because of a decision you made.',
      'There is no safety system running. It is just you.',
    ],
    task: 'Run the day. Keep the lights on and the cars charged.',
    mode: 'manual',
    projection: false,
    unlocks: [],
    revealTitle: 'That was harder than it looked',
    reveal: (ctx) => {
      const brokeTheGrid = ctx.violationRate > 0.06;
      const strandedDrivers = ctx.socMet < 0.75;

      const numbers = `Violation rate ${ctx.violationRate.toFixed(3)} — the fraction of the day, across all thirty-three buses, spent outside the legal band of 0.95 to 1.05 per unit. Worst moment ${ctx.vMinPu.toFixed(4)} pu. Service ${ctx.socMet.toFixed(3)} — the share of drivers who left with the charge they came for.`;

      // Name the specific way this run failed. A learner who over-charged and a learner
      // who under-charged have discovered opposite halves of the same trade-off, and
      // telling them both the same thing wastes the moment.
      let verdict: string;
      if (brokeTheGrid && strandedDrivers) {
        verdict =
          'You broke the grid *and* left people stranded. That sounds like the worst outcome, and it is — but it is also the most common one, because the two failures happen at different hours and fixing one at 19:00 causes the other at 23:00.';
      } else if (brokeTheGrid) {
        verdict = `You kept almost everybody charged — and you did it by pushing the feeder end down to ${ctx.vMinPu.toFixed(4)} pu and holding it there. Those houses at the far end of the line went dark on your watch. Service is easy if you are willing to break the grid to get it.`;
      } else if (strandedDrivers) {
        verdict = `You held the voltage. You did it by not charging anyone: ${pct(1 - ctx.socMet)} of drivers went home short. Every one of them could have been fully charged in the time they were plugged in, so that was a decision, not a shortage.`;
      } else {
        verdict =
          'You actually threaded it — which almost nobody does on a first run. Hold on to how much attention that took, because the controllers you are about to meet have to do it every five minutes without you.';
      }

      return [
        numbers,
        verdict,
        'Your run is now a dot on the map at the bottom of the screen. It stays there. Everything you are about to see gets measured against it.',
        'What you just felt is the whole problem: two objectives that pull in opposite directions, on a network where the same command means different things at different buses.',
      ];
    },
  },

  {
    n: 2,
    eyebrow: 'Uncoordinated',
    title: 'What happens today, with no coordination at all',
    brief: [
      'This is the baseline: every vehicle charges at full power the moment it is plugged in. No grid awareness whatsoever. It is what most chargers actually do.',
      'Watch the evening. The load peak, the vehicles arriving home, and the solar disappearing all land in the same two hours.',
    ],
    task: 'Watch. Look at the far end of the village around 19:00.',
    mode: 'watch',
    controllerId: 'uncoordinated',
    unlocks: ['map'],
    revealTitle: 'Service without safety',
    reveal: (ctx) => [
      `Almost everybody got charged: ${ctx.socMet.toFixed(3)}. On that axis it beats you and it beats everything you will see today.`,
      `It also burned ${ctx.lossKwh.toFixed(0)} kWh as heat in the wires getting there. Losses rise with the square of current, so charging everyone at once does not just bend the voltage — it wastes energy that was generated and never delivered to anybody.`,
      `It also spent ${ctx.violationRate.toFixed(3)} of the day illegal, and drove the feeder end down to ${ctx.vMinPu.toFixed(4)} pu. You watched the tail of the line go dark.`,
      'That is the first corner of the trade-off: you can always have perfect service if you are willing to break the grid to get it.',
    ],
  },

  {
    n: 3,
    eyebrow: 'Droop · IEEE 1547',
    title: 'The standard answer, written down in 1547',
    brief: [
      'Every grid-connected inverter sold today implements a volt-watt droop curve. It is simple: each station measures the voltage at its own bus and backs off as that voltage falls. Below a threshold it reverses and pushes power back.',
      'It is a fifty-year-old idea, it needs no model of the network, and it is in the standard.',
      'Watch what it costs.',
    ],
    task: 'Watch. This time keep your eye on the charging stations, not the houses.',
    mode: 'watch',
    controllerId: 'droop',
    unlocks: [],
    revealTitle: 'Safety without service',
    reveal: (ctx) => {
      const uncoordinated = findDot(ctx.dots, 'uncoordinated');
      const lines = [
        `Violations down to ${ctx.violationRate.toFixed(3)}${
          uncoordinated
            ? ` from ${uncoordinated.violationRate.toFixed(3)}` : ''
        }. The lights held.`,
        `Service fell to ${ctx.socMet.toFixed(3)}${
          uncoordinated ? ` from ${uncoordinated.socMet.toFixed(3)}` : ''
        }. The cars went home empty.`,
        'That is the other corner. A rule that only knows its own bus protects the grid by refusing to use it.',
      ];
      lines.push(
        'Two dots, two extremes. The interesting question is whether anything can sit above and to the left of both of them.',
      );
      return lines;
    },
  },

  {
    n: 4,
    eyebrow: 'Deep reinforcement learning',
    title: 'So put a neural network on it',
    brief: [
      'This is Plain RL: a deep reinforcement-learning agent carrying a penalty on constraint violation, trained on this feeder for a full schedule. It sees the whole system state. It has learned from millions of steps of experience.',
      'It is the obvious modern answer, and it is what most papers in this area propose.',
      'Watch where its dot lands relative to the droop curve.',
    ],
    task: 'Watch. Then look at the map.',
    mode: 'watch',
    controllerId: 'sac-lag',
    unlocks: [],
    revealTitle: 'The deep learning agent lost',
    reveal: (ctx) => {
      const droopDot = findDot(ctx.dots, 'droop');
      const lines: string[] = [];
      if (droopDot) {
        const worseSafety = ctx.violationRate > droopDot.violationRate;
        const worseService = ctx.socMet < droopDot.socMet;
        lines.push(
          `Plain RL: ${ctx.violationRate.toFixed(3)} violations, ${ctx.socMet.toFixed(3)} service. Droop: ${droopDot.violationRate.toFixed(3)} violations, ${droopDot.socMet.toFixed(3)} service.`,
        );
        if (worseSafety && worseService) {
          lines.push(
            'Look at where the two dots sit. The neural network is below and to the right of the fifty-year-old rule — it is worse on safety *and* worse on service. There is no axis on which it wins.',
          );
        } else {
          lines.push(
            'Compare the two dots directly. The neural network does not clearly beat the fifty-year-old rule, which is not what anybody expects to find.',
          );
        }
      }
      lines.push(
        'This is the result the underlying research reported and it is the reason this simulator exists. Intelligence was not the missing ingredient. The agent could see everything about the system except how its own actions move voltage through the network.',
        'Which raises the obvious question: what happens if you give it that?',
      );
      return lines;
    },
  },

  {
    n: 5,
    eyebrow: 'Physics restored',
    title: 'The same agent, with the network put back in',
    brief: [
      'Shielded RL is the same backbone, the same training budget, the same reward. One thing is added: at every control step, a safety layer measures how much each station actually moves the voltage at every bus on the live network, and projects the agent\'s request onto the nearest command that keeps the whole feeder legal.',
      'That layer was present while it trained, so this is a different learned policy, not the old one behind a filter.',
      'It is worth knowing what that measurement found. Ask all four stations for 80 kW here and the layer returns 54, 78, 77 and 73 — a real cut, and a different one at each station. Ask for the same 80 kW on a stiff grid and all four pass through untouched. The layer is not a rule. It is a calculation about one particular network, redone every step, and that is the whole reason it has to run on the grid it is deployed to rather than the grid it trained on.',
      'After this run you can switch the layer off and see how hard it was working.',
    ],
    task: 'Watch. Then try the safety projection toggle.',
    mode: 'watch',
    controllerId: 'safesac',
    projection: true,
    unlocks: ['projection'],
    revealTitle: 'Safety and service, at the same time',
    reveal: (ctx) => {
      const sacLag = findDot(ctx.dots, 'sac-lag');
      const lines: string[] = [
        `Shielded RL: ${ctx.violationRate.toFixed(3)} violations, ${ctx.socMet.toFixed(3)} service, worst voltage ${ctx.vMinPu.toFixed(4)} pu.`,
      ];
      if (sacLag) {
        const gained = ctx.socMet - sacLag.socMet;
        lines.push(
          `Against the plain agent, that is ${gained >= 0 ? '+' : ''}${gained.toFixed(3)} on service at ${
            ctx.violationRate <= sacLag.violationRate ? 'no cost in' : 'a modest cost in'
          } safety. Same network, same training, one addition.`,
        );
      }
      lines.push(
        'The safety layer is not a filter bolted on at the end. It changed what the agent was able to learn, because every action it ever tried was one the grid could actually take.',
        'The projection toggle is now unlocked. Turn it off and run again: the raw requests go through unfiltered, and you can see exactly how often and how hard the layer had been intervening.',
      );
      return lines;
    },
  },

  {
    n: 6,
    eyebrow: 'The trap',
    title: 'Now pick one to deploy',
    brief: [
      'You are the engineer on the procurement call. Five controllers, and the evaluation report in front of you has the two columns a manager always asks for: how often does it break the rules, and what does it cost.',
      'These are not this simulator’s numbers. They are the vendor’s: twenty-five episodes per controller on a feeder like yours, same seeds for all of them, measured and published.',
      'One of them has the best safety score in the report and is the only one that makes money.',
      'Choose the one you would put on a real feeder.',
    ],
    task: 'Read the report. Choose one.',
    mode: 'choose',
    unlocks: ['grid', 'loadScale', 'compare', 'margin'],
    revealTitle: 'The third column',
    reveal: () => [
      'The controller with the best violation rate and the only negative cost served nobody. Across twenty-five evaluation episodes, not one departing driver reached the charge they came for.',
      'Look at how it did it. Every other candidate delivered somewhere between 540 and 1130 kilowatt-hours into batteries. This one delivered zero — not a small number, zero — and the throughput on its line in the report is entirely discharge. It made its profit selling the drivers’ own batteries back to the grid, and its perfect safety record by never charging anything.',
      'It is not broken, and it is not lying. It is an agent trained on a stronger grid than the one it was deployed to, doing exactly what it learned: on that grid its caution was affordable, and here the same caution means never acting at all. Nobody wrote that behaviour. It was measured.',
      'This is the failure that never shows up in the field, because reality does not hand you the counterfactual. An operator who deploys it gets a report saying violations are at an all-time low and costs are negative, and no report at all saying nobody could get to work.',
      'Whenever you are shown a safety number, ask what it cost in service. If nobody can tell you, the number means nothing.',
    ],
  },
];

/** Every control unlocked by the time the given stage is being played. */
export function unlockedBy(stageIndex: number): Set<Unlock> {
  const set = new Set<Unlock>();
  for (let i = 0; i <= Math.min(stageIndex, STAGES.length - 1); i++) {
    for (const u of STAGES[i].unlocks) set.add(u);
  }
  return set;
}
