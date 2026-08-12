/**
 * Stage 6: the procurement table.
 *
 * Two columns, which is what a manager actually gets handed: how often does it break
 * the rules, and what does it cost. The service column exists and is deliberately not
 * shown until after the learner has committed to a choice — because that is exactly
 * the position a real engineer is in, and the moment of being caught is the lesson.
 *
 * The rows are the source evaluation, transcribed in `content/evaluation.ts`, not runs
 * of this simulator. That is what makes the table a report rather than a demonstration,
 * and it is also why the trap holds up: nobody arranged for the safest, cheapest row to
 * be the one that charges nobody. It was measured.
 */

import { EVALUATION } from '../content/evaluation.js';

export interface Candidate {
  id: string;
  label: string;
  violationRate: number;
  netCostUsd: number;
  socMet: number;
  provenance: string;
}

interface Props {
  candidates: readonly Candidate[];
  /** Once chosen, the third column appears and the choice is marked. */
  chosen: string | null;
  onChoose: (id: string) => void;
}

export function Leaderboard({ candidates, chosen, onChoose }: Props) {
  const revealed = chosen !== null;
  const bestSafety = Math.min(...candidates.map((c) => c.violationRate));
  const bestCost = Math.min(...candidates.map((c) => c.netCostUsd));

  return (
    <div className="leaderboard">
      <table>
        <caption>
          {revealed
            ? 'The column nobody asked for'
            : `Five candidate controllers, as evaluated by the vendor: ${EVALUATION.episodes} episodes each on this feeder, shared seeds.`}
        </caption>
        <thead>
          <tr>
            <th>Controller</th>
            <th className="num">Violation rate</th>
            <th className="num">Net cost</th>
            {revealed && <th className="num">Vehicles served</th>}
            <th />
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => {
            const isChoice = c.id === chosen;
            const collapsed = revealed && c.socMet < 0.02;
            return (
              <tr key={c.id} data-chosen={isChoice} data-collapsed={collapsed}>
                <td>{c.label}</td>
                <td className="num">
                  {c.violationRate.toFixed(3)}
                  {c.violationRate === bestSafety && <span className="best"> best</span>}
                </td>
                <td className="num">
                  {c.netCostUsd < 0
                    ? `−$${Math.abs(c.netCostUsd).toFixed(0)}`
                    : `$${c.netCostUsd.toFixed(0)}`}
                  {c.netCostUsd === bestCost && <span className="best"> best</span>}
                </td>
                {revealed && (
                  <td className="num">
                    <span className={collapsed ? 'zero' : undefined}>
                      {c.socMet.toFixed(3)}
                    </span>
                  </td>
                )}
                <td>
                  {!revealed ? (
                    <button className="ctl" onClick={() => onChoose(c.id)}>
                      Deploy this
                    </button>
                  ) : isChoice ? (
                    <span className="your-pick">your pick</span>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Always shown. It gives nothing away — a real report states its method — and it
          is what stops the numbers here being read against the map, which counts
          differently on both axes. */}
      <p className="source-note">
        Measured in the source evaluation, not by this simulator. Violation rate is the
        fraction of the day&rsquo;s {EVALUATION.steps} five-minute steps with any bus
        outside the band; vehicles served is over the {Math.round(EVALUATION.departures)}{' '}
        that departed during the episode. The map on the left counts both differently, so
        these rows do not belong on it.
      </p>

      {revealed && (
        <p className="source-note sting">
          One number was in the report all along and in none of the columns you were
          shown: energy delivered into batteries. Every other candidate moved between
          540 and 1130 kWh of it. The row with the best safety score and the only profit
          moved <strong>zero</strong>. Its entire throughput was discharge — it sold the
          drivers&rsquo; own batteries back to the grid and put nothing in.
        </p>
      )}
    </div>
  );
}
