/**
 * The ending: what the entry claims to teach, and what your own runs actually showed.
 *
 * The eight objectives are copied verbatim from `src/content/debrief.ts` so the two
 * builds claim exactly the same thing. Divergence here would be worse than having no
 * debrief at all — a learner who does the 3D version and a judge reading the website's
 * stated objectives have to be looking at one set of promises, not two.
 *
 * What is *not* copied is any claim about whether an objective was met. The website
 * marks an objective as covered when the learner reached the stage that teaches it,
 * and so does this: coverage means the material was put in front of you, never that
 * you understood it. Only a tester's pre/post can say the latter, and the entry does
 * not pretend otherwise.
 */

import { WORLD } from './core.js';

/** Verbatim from `src/content/debrief.ts`. Do not paraphrase — see the note above. */
export const OBJECTIVES = [
  { id: 'L1', stage: 'Stage 1', taught: 1, text: 'Predict the direction and rough size of a voltage change from a power change: ΔV ≈ (R·ΔP + X·ΔQ) / V₀' },
  { id: 'L2', stage: 'Stages 1–2', taught: 2, text: 'Explain why active power dominates voltage on a weak feeder where R ≈ X, while reactive dominates on transmission where X ≫ R' },
  { id: 'L3', stage: 'Stage 1', taught: 1, text: 'Read a voltage profile and identify the electrically weakest bus — and say why it is weakest' },
  { id: 'L4', stage: 'Stage 3', taught: 3, text: 'State the [0.95, 1.05] pu statutory band, and explain what a safety margin buys and costs' },
  { id: 'L5', stage: 'Stage 6', taught: 6, text: 'Distinguish a constraint satisfied by operating safely from one satisfied by not operating at all' },
  { id: 'L6', stage: 'Stages 4, 6', taught: 4, text: 'Critique any controller comparison by demanding the service column beside the safety column' },
  { id: 'L7', stage: 'Stage 6', taught: 6, text: 'Explain deployment shift: why a policy trained on a strong grid can fail on a weak one' },
  { id: 'L8', stage: 'Stage 5', taught: 5, text: 'Describe what a safety projection does, and why it must be rebuilt from live sensitivities each step' },
];

const drivers = (soc) => Math.round(soc * 287);

/**
 * What the learner's own runs showed, stated only where the runs actually support it.
 * Every finding here is guarded: no run, no claim.
 */
export function findings({ myDots, picked, gridSeen }) {
  const out = [];
  const best = myDots.length
    ? myDots.reduce((a, b) => (a.violationRate <= b.violationRate ? a : b))
    : null;
  const u = WORLD.runs.find((r) => r.id === 'uncoordinated');
  const d = WORLD.runs.find((r) => r.id === 'droop');
  const s = WORLD.runs.find((r) => r.id === 'safesac');

  if (best) {
    out.push({
      headline: `Your best run held ${(best.violationRate * 100).toFixed(2)}% of bus-steps outside the band and served ${best.driversMet} of 287.`,
      body: `Droop managed ${(d.violationRate * 100).toFixed(2)}% and ${drivers(d.socMet)} served; Shielded RL ${(s.violationRate * 100).toFixed(2)}% and ${drivers(s.socMet)}. `
        + (best.violationRate <= d.violationRate
          ? 'You beat the standard on safety. Check the second column before you celebrate.'
          : 'Both of them beat you on safety, and one of them beat you on service too.'),
    });
  } else {
    out.push({
      headline: 'You have not finished a run of your own yet.',
      body: 'Press Play from the start of a day and let it reach midnight. The map scores it the way it scores the four reference controllers — by counting the drivers who left with the charge they came for.',
    });
  }

  out.push({
    headline: `Coordination is worth ${(u.totalLossKwh - s.totalLossKwh).toFixed(0)} kWh a day in heat alone.`,
    body: `Uncoordinated charging burns ${u.totalLossKwh.toFixed(0)} kWh in the lines across this day; Shielded RL burns ${s.totalLossKwh.toFixed(0)} kWh and still serves ${drivers(s.socMet)} of 287. Losses are resistive, so they scale with the square of current — which is why the same energy delivered less peakily costs the town less to deliver.`,
  });

  if (picked !== null) {
    const c = WORLD.candidates[picked];
    const trap = WORLD.candidates.findIndex((x) => x.id === 'sac-lag-shift');
    out.push({
      headline: picked === trap
        ? 'You deployed the controller that serves nobody.'
        : `You deployed ${c.label}.`,
      body: picked === trap
        ? 'It posts the best safety score on the board and the only profit, and it charges zero of 287 drivers. A procurement table with a safety column and a cost column cannot tell that apart from a good controller.'
        : `Violations ${c.violationRate.toFixed(3)}, ${drivers(c.socMet)} of 287 served, $${c.netCostUsd} net. You passed over the row with the best safety score, which serves nobody at all.`,
    });
  }

  if (gridSeen) {
    out.push({
      headline: 'You saw what the network itself is worth.',
      body: `On a stiff source the same droop controller breaks the band ${(WORLD.candidatesStrong[0].violationRate * 100).toFixed(2)}% of the time instead of ${(WORLD.candidates[0].violationRate * 100).toFixed(2)}%, and serves ${drivers(WORLD.candidatesStrong[0].socMet)} instead of ${drivers(WORLD.candidates[0].socMet)}. Safety can be bought with control or with copper; the choice between them is the engineering decision, and only one of the two shows up on a controller comparison.`,
    });
  }

  return out;
}

/** Objectives the learner has been shown, by how far through the arc they got. */
export function coverage(stagesCompleted) {
  return OBJECTIVES.map((o) => ({ ...o, covered: stagesCompleted >= o.taught }));
}
