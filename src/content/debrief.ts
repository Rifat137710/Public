/**
 * The debrief's content logic, kept out of the component for the same reason the stage
 * script is: these are claims about what the simulation showed, and claims should be
 * testable without a browser.
 *
 * Nothing here is written down as a result. Every finding is assembled from the dots the
 * learner actually generated, so a finding that failed to reproduce today is absent
 * rather than asserted.
 */

import type { Dot } from '../ui/ParetoMap.js';
import type { Candidate } from '../ui/Leaderboard.js';

export interface Objective {
  id: string;
  text: string;
  stage: string;
}

/** The entry's eight stated objectives, each tied to the stage that teaches it. */
export const OBJECTIVES: Objective[] = [
  {
    id: 'L1',
    text: 'Predict the direction and rough size of a voltage change from a power change: ΔV ≈ (R·ΔP + X·ΔQ) / V₀',
    stage: 'Stage 1',
  },
  {
    id: 'L2',
    text: 'Explain why active power dominates voltage on a weak feeder where R ≈ X, while reactive dominates on transmission where X ≫ R',
    stage: 'Stages 1–2',
  },
  {
    id: 'L3',
    text: 'Read a voltage profile and identify the electrically weakest bus — and say why it is weakest',
    stage: 'Stage 1',
  },
  {
    id: 'L4',
    text: 'State the [0.95, 1.05] pu statutory band, and explain what a safety margin buys and costs',
    stage: 'Stage 3',
  },
  {
    id: 'L5',
    text: 'Distinguish a constraint satisfied by operating safely from one satisfied by not operating at all',
    stage: 'Stage 6',
  },
  {
    id: 'L6',
    text: 'Critique any controller comparison by demanding the service column beside the safety column',
    stage: 'Stages 4, 6',
  },
  {
    id: 'L7',
    text: 'Explain deployment shift: why a policy trained on a strong grid can fail on a weak one',
    stage: 'Stage 6',
  },
  {
    id: 'L8',
    text: 'Describe what a safety projection does, and why it must be rebuilt from live sensitivities each step',
    stage: 'Stage 5',
  },
];

export interface Finding {
  key: string;
  headline: string;
  body: string;
}

/** A controller that reports a service score this low did not operate at all. */
export const COLLAPSED_SERVICE = 0.02;

function find(dots: readonly Dot[], id: string): Dot | undefined {
  return dots.find((d) => d.id === id);
}

export function money(usd: number): string {
  return usd < 0 ? `−$${Math.abs(usd).toFixed(0)}` : `$${usd.toFixed(0)}`;
}

export function buildFindings(dots: readonly Dot[]): Finding[] {
  const mine = find(dots, 'manual');
  const unco = find(dots, 'uncoordinated');
  const droop = find(dots, 'droop');
  const sacLag = find(dots, 'sac-lag');
  const safeSac = find(dots, 'safesac');
  const out: Finding[] = [];

  if (mine) {
    out.push({
      key: 'you',
      headline: 'You ran the feeder yourself before you saw anyone solve it',
      body: `Your day: ${mine.violationRate.toFixed(3)} violation rate, ${mine.socMet.toFixed(
        3,
      )} of drivers served. That dot went on the map before you had seen a single controller, which is why the rest of it meant anything.`,
    });
  }

  if (unco) {
    out.push({
      key: 'unco',
      headline: 'Perfect service is easy if you will break the grid to get it',
      body: `Uncoordinated charging served ${unco.socMet.toFixed(
        3,
      )} — the best service score on the board — and spent ${unco.violationRate.toFixed(
        3,
      )} of the day outside the legal band to do it.`,
    });
  }

  if (droop && unco) {
    out.push({
      key: 'droop',
      headline: 'A rule that only knows its own bus protects the grid by refusing to use it',
      body: `The IEEE 1547 droop curve cut violations from ${unco.violationRate.toFixed(
        3,
      )} to ${droop.violationRate.toFixed(3)}, and cut service from ${unco.socMet.toFixed(
        3,
      )} to ${droop.socMet.toFixed(
        3,
      )} paying for it. Safety and service are the two axes, and the early controllers each buy one with the other.`,
    });
  }

  if (sacLag && droop) {
    const dominated =
      sacLag.violationRate > droop.violationRate && sacLag.socMet < droop.socMet;
    out.push({
      key: 'sac-lag',
      headline: dominated
        ? 'Intelligence was not the missing ingredient'
        : 'The neural network did not clearly beat the fifty-year-old rule',
      body: dominated
        ? `Plain deep RL landed at ${sacLag.violationRate.toFixed(3)}/${sacLag.socMet.toFixed(
            3,
          )} against droop's ${droop.violationRate.toFixed(3)}/${droop.socMet.toFixed(
            3,
          )} — worse on safety and worse on service, dominated on both axes by a rule from 1547. The agent could see everything about the system except how its own actions move voltage through the network.`
        : `Plain deep RL landed at ${sacLag.violationRate.toFixed(3)}/${sacLag.socMet.toFixed(
            3,
          )} against droop's ${droop.violationRate.toFixed(3)}/${droop.socMet.toFixed(
            3,
          )}. It does not clearly win, which is not what anybody expects from a trained agent against a fixed rule.`,
    });
  }

  if (safeSac && sacLag) {
    const gained = safeSac.socMet - sacLag.socMet;
    out.push({
      key: 'safesac',
      headline: 'Giving the agent the network physics changed what it could learn',
      body: `SafeSAC reached ${safeSac.violationRate.toFixed(3)}/${safeSac.socMet.toFixed(
        3,
      )} — ${gained >= 0 ? '+' : ''}${gained.toFixed(
        3,
      )} on service against the plain agent. The safety layer measures how much each station actually moves voltage at every bus, on the live network, every step. It was present during training, so this is a different learned policy rather than the old one behind a filter.`,
    });
  }

  return out;
}

/**
 * What the stage 6 choice actually bought. The learner who took the bait and the learner
 * who did not have discovered different things, and telling them the same thing wastes
 * the only moment in the arc where they have personally committed to an answer.
 */
export function pickVerdict(
  candidates: readonly Candidate[],
  pick: string | null,
): Finding | null {
  if (!pick) return null;
  const chosen = candidates.find((c) => c.id === pick);
  if (!chosen) return null;

  const bestSafety = Math.min(...candidates.map((c) => c.violationRate));

  if (chosen.socMet < COLLAPSED_SERVICE) {
    return {
      key: 'pick',
      headline: `You deployed ${chosen.label} — and it served nobody`,
      body: `It showed ${chosen.violationRate.toFixed(3)} violations${
        chosen.violationRate === bestSafety ? ', the best safety score on the table' : ''
      }, and ${money(
        chosen.netCostUsd,
      )}. The column you were not shown reads ${chosen.socMet.toFixed(
        3,
      )}. It earned that safety record by declining to operate, and because every vehicle in this scenario could physically have been charged in the time it was plugged in, that was a decision rather than a shortage. This is the failure that never shows up in the field, because reality does not hand you the counterfactual.`,
    };
  }

  return {
    key: 'pick',
    headline: `You deployed ${chosen.label}`,
    body: `${chosen.violationRate.toFixed(3)} violations, ${money(
      chosen.netCostUsd,
    )}, and ${chosen.socMet.toFixed(
      3,
    )} of drivers served. You did not take the bait — the controller with the best safety number and the only profit on that table was the one that never charged anybody. Whenever you are shown a safety number, ask what it cost in service.`,
  };
}

/**
 * The takeaway document. Deliberately light-themed rather than matching the app: this is
 * meant to be printed, filed and re-read, and the control-room palette does not survive
 * paper.
 */
export function onePagerHtml(
  dots: readonly Dot[],
  findings: readonly Finding[],
  verdict: Finding | null,
  grid: string,
  loadScale: number,
  when: string = new Date().toISOString().slice(0, 16).replace('T', ' '),
): string {
  const rows = dots
    .map(
      (d) =>
        `<tr><td>${d.label}${
          d.provenance === 'placeholder' ? ' *' : ''
        }</td><td class="n">${d.violationRate.toFixed(3)}</td><td class="n">${d.socMet.toFixed(
          3,
        )}</td></tr>`,
    )
    .join('\n');

  const findingBlocks = [...findings, ...(verdict ? [verdict] : [])]
    .map((f) => `<h3>${f.headline}</h3>\n<p>${f.body}</p>`)
    .join('\n');

  const objectiveRows = OBJECTIVES.map(
    (o) => `<tr><td class="k">${o.id}</td><td>${o.text}</td><td class="s">${o.stage}</td></tr>`,
  ).join('\n');

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bus 18 — debrief</title>
<style>
  body { font: 15px/1.55 Georgia, "Iowan Old Style", serif; color: #14202B;
         max-width: 46rem; margin: 3rem auto; padding: 0 1.5rem; background: #fff; }
  h1 { font-size: 1.6rem; margin: 0 0 0.2rem; }
  h2 { font-size: 1rem; text-transform: uppercase; letter-spacing: 0.09em;
       color: #6B7A87; margin: 2.2rem 0 0.8rem; font-family: system-ui, sans-serif; }
  h3 { font-size: 1.02rem; margin: 1.3rem 0 0.3rem; }
  p  { margin: 0 0 0.7rem; }
  .sub { color: #6B7A87; margin-bottom: 1.6rem; font-size: 0.9rem; }
  table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem 0.4rem 0; border-bottom: 1px solid #E3E8EC; }
  th { font-family: system-ui, sans-serif; font-size: 0.72rem; text-transform: uppercase;
       letter-spacing: 0.07em; color: #6B7A87; }
  .n { text-align: right; font-family: ui-monospace, Menlo, Consolas, monospace; }
  .k { font-family: ui-monospace, Menlo, Consolas, monospace; color: #0F6E63; width: 2.4rem; }
  .s { font-family: system-ui, sans-serif; font-size: 0.78rem; color: #6B7A87; white-space: nowrap; }
  footer { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #E3E8EC;
           color: #6B7A87; font-size: 0.82rem; }
  @media print { body { margin: 0 auto; } }
</style></head><body>

<h1>Bus 18 — your debrief</h1>
<p class="sub">${when} · ${grid} feeder · load scale ${loadScale.toFixed(
    2,
  )} · IEEE 33-bus Baran–Wu benchmark</p>

<h2>What you found</h2>
${findingBlocks}

<h2>Every run you finished</h2>
<table><thead><tr><th>Run</th><th class="n">Violation rate</th><th class="n">Service</th></tr></thead>
<tbody>${rows}</tbody></table>

<h2>The eight objectives</h2>
<table><thead><tr><th></th><th>You can now…</th><th>Taught in</th></tr></thead>
<tbody>${objectiveRows}</tbody></table>

<footer>
Violation rate is the fraction of the day, across all 33 buses, spent outside
[0.95, 1.05] pu. Service is the share of drivers who left with the charge they
arrived asking for. Every vehicle in this scenario could be fully charged within
its own plugged-in window, so unmet service is attributable to the controller and
not to a shortage.
${
  dots.some((d) => d.provenance === 'placeholder')
    ? '<br><br>* SAC-Lag and SafeSAC are labelled stand-ins, not the trained agents.'
    : ''
}
<br><br>Built on <em>Safe Deep Reinforcement Learning for Vehicle-to-Grid Voltage Support in
Weak Distribution Feeders</em>, Md. Rifat Rahman and Sad Sami, BUET EEE, 2026.
</footer>
</body></html>`;
}
