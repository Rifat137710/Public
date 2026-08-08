/**
 * The safety-service plane.
 *
 * Every completed run leaves a permanent dot. By the end of the six stages the learner
 * has rebuilt the thesis's Pareto figure out of their own attempts — and, crucially,
 * their own dot went down first, before they had seen any controller solve the problem.
 *
 * Up and to the left is better: fewer violations, more vehicles served.
 */

const WIDTH = 620;
const HEIGHT = 150;
const PAD_L = 46;
const PAD_R = 130;
const PAD_T = 12;
const PAD_B = 34;

export interface Dot {
  id: string;
  label: string;
  violationRate: number;
  socMet: number;
  provenance: string;
  /** The learner's own attempts are drawn differently from the reference controllers. */
  mine: boolean;
}

interface Props {
  dots: readonly Dot[];
  maxViolation?: number;
}

const COLOURS: Record<string, string> = {
  manual: '#E4EAEE',
  uncoordinated: '#E3B24F',
  droop: '#4FA3F0',
  'sac-lag': '#E4776B',
  safesac: '#68D6A8',
};

export function ParetoMap({ dots, maxViolation = 0.36 }: Props) {
  const x = (violation: number) =>
    PAD_L + Math.min(1, violation / maxViolation) * (WIDTH - PAD_L - PAD_R);
  const y = (soc: number) => HEIGHT - PAD_B - soc * (HEIGHT - PAD_T - PAD_B);

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width="100%"
      role="img"
      aria-label="Safety against service. Each completed run leaves a dot; up and to the left is better."
    >
      {[0, 0.25, 0.5, 0.75, 1].map((soc) => (
        <g key={soc}>
          <line
            x1={PAD_L}
            x2={WIDTH - PAD_R}
            y1={y(soc)}
            y2={y(soc)}
            stroke="var(--line)"
            strokeWidth={1}
          />
          <text
            x={PAD_L - 6}
            y={y(soc) + 3.5}
            textAnchor="end"
            fontSize="9"
            fontFamily="var(--mono)"
            fill="var(--ink-3)"
          >
            {soc.toFixed(2)}
          </text>
        </g>
      ))}

      {[0, 0.1, 0.2, 0.3].map((v) => (
        <text
          key={v}
          x={x(v)}
          y={HEIGHT - 18}
          textAnchor="middle"
          fontSize="9"
          fontFamily="var(--mono)"
          fill="var(--ink-3)"
        >
          {v.toFixed(2)}
        </text>
      ))}

      <text
        x={PAD_L + 8}
        y={PAD_T + 20}
        fontSize="9"
        fontFamily="var(--mono)"
        fill="var(--ink-3)"
      >
        ← safer · more served ↑
      </text>
      <text
        x={(PAD_L + WIDTH - PAD_R) / 2}
        y={HEIGHT - 4}
        textAnchor="middle"
        fontSize="9"
        fontFamily="var(--mono)"
        fill="var(--ink-3)"
      >
        violation rate
      </text>

      {dots.map((dot, i) => {
        const colour = COLOURS[dot.id] ?? 'var(--ink-2)';
        const cx = x(dot.violationRate);
        const cy = y(dot.socMet);
        return (
          <g key={`${dot.id}-${i}`}>
            {dot.mine ? (
              <circle
                cx={cx}
                cy={cy}
                r={5}
                fill="none"
                stroke={colour}
                strokeWidth={1.8}
              />
            ) : (
              <circle cx={cx} cy={cy} r={4.5} fill={colour} />
            )}
            {dot.provenance === 'placeholder' && (
              <text x={cx + 7} y={cy - 5} fontSize="8" fill="var(--warn)" fontFamily="var(--mono)">
                *
              </text>
            )}
          </g>
        );
      })}

      {dots.map((dot, i) => (
        <g key={`legend-${dot.id}-${i}`} transform={`translate(${WIDTH - PAD_R + 10}, ${PAD_T + 8 + i * 15})`}>
          <circle
            cx={0}
            cy={-3.5}
            r={4}
            fill={dot.mine ? 'none' : COLOURS[dot.id] ?? 'var(--ink-2)'}
            stroke={COLOURS[dot.id] ?? 'var(--ink-2)'}
            strokeWidth={dot.mine ? 1.6 : 0}
          />
          <text x={9} y={0} fontSize="9.5" fill="var(--ink-2)" fontFamily="var(--mono)">
            {dot.label.length > 16 ? `${dot.label.slice(0, 15)}…` : dot.label}
          </text>
        </g>
      ))}

      {dots.length === 0 && (
        <text
          x={(WIDTH - PAD_R + PAD_L) / 2}
          y={HEIGHT / 2}
          textAnchor="middle"
          fontSize="11"
          fill="var(--ink-3)"
        >
          Finish a day to put your first dot on the map.
        </text>
      )}
    </svg>
  );
}
