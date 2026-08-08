/**
 * Stage 6: the procurement table.
 *
 * Two columns, which is what a manager actually gets handed: how often does it break
 * the rules, and what does it cost. The service column exists and is deliberately not
 * shown until after the learner has committed to a choice — because that is exactly
 * the position a real engineer is in, and the moment of being caught is the lesson.
 */

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
            : 'Four candidate controllers. Same feeder, same day, same fleet.'}
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
                <td>
                  {c.label}
                  {c.provenance === 'placeholder' && <span className="star"> *</span>}
                </td>
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
    </div>
  );
}
