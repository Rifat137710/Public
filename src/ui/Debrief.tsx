/**
 * The debrief — the last thing the learner sees before the sandbox opens.
 *
 * Six stages produce a sequence of moments, and a sequence of moments is not the same
 * thing as a retained idea. This screen does the consolidation: it puts every dot the
 * learner generated in one frame, states each finding as a claim with their own numbers
 * attached, and names the eight objectives explicitly so they leave knowing what they
 * were supposed to have learned rather than only how it felt.
 *
 * The claims themselves live in content/debrief.ts, where they can be tested without a
 * browser. This file only renders them.
 */

import { useCallback } from 'react';
import { ParetoMap, type Dot } from './ParetoMap.js';
import type { Candidate } from './Leaderboard.js';
import { OBJECTIVES, buildFindings, onePagerHtml, pickVerdict } from '../content/debrief.js';

interface Props {
  dots: readonly Dot[];
  candidates: readonly Candidate[];
  pick: string | null;
  grid: string;
  loadScale: number;
  onAction: () => void;
}

function download(filename: string, contents: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([contents], { type: mime }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function Debrief({ dots, candidates, pick, grid, loadScale, onAction }: Props) {
  const findings = buildFindings(dots);
  const verdict = pickVerdict(candidates, pick);

  const saveOnePager = useCallback(() => {
    download(
      'bus18-debrief.html',
      onePagerHtml(dots, buildFindings(dots), pickVerdict(candidates, pick), grid, loadScale),
      'text/html',
    );
  }, [dots, candidates, pick, grid, loadScale]);

  const saveJson = useCallback(() => {
    download(
      'bus18-results.json',
      JSON.stringify(
        {
          exportedAt: new Date().toISOString(),
          scenario: { grid, loadScale, network: 'IEEE 33-bus Baran-Wu' },
          runs: dots.map((d) => ({
            id: d.id,
            label: d.label,
            violationRate: d.violationRate,
            socMet: d.socMet,
            provenance: d.provenance,
            mine: d.mine,
          })),
          stage6: { pick, candidates },
        },
        null,
        2,
      ),
      'application/json',
    );
  }, [dots, candidates, pick, grid, loadScale]);

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Debrief">
      <div className="card debrief" data-tone="debrief">
        <p className="card-eyebrow">Debrief · all six stages complete</p>
        <h1 className="card-title">What you found today</h1>

        <div className="debrief-map">
          <ParetoMap dots={dots} />
        </div>

        {[...findings, ...(verdict ? [verdict] : [])].map((f) => (
          <section key={f.key} className="finding" data-emphasis={f.key === 'pick'}>
            <h3>{f.headline}</h3>
            <p>{f.body}</p>
          </section>
        ))}

        <h2 className="debrief-h2">The eight objectives</h2>
        <ul className="objectives">
          {OBJECTIVES.map((o) => (
            <li key={o.id}>
              <span className="obj-id">{o.id}</span>
              <span className="obj-text">{o.text}</span>
              <span className="obj-stage">{o.stage}</span>
            </li>
          ))}
        </ul>

        <div className="card-actions">
          <button className="ctl primary" onClick={onAction}>
            Open the sandbox
          </button>
          <button className="ctl" onClick={saveOnePager}>
            Save one-page summary
          </button>
          <button className="ctl quiet" onClick={saveJson}>
            Save raw results
          </button>
        </div>
      </div>
    </div>
  );
}
