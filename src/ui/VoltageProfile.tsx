/**
 * Voltage against bus index — the thesis's Figure 5.2, live.
 *
 * The statutory limits are drawn as walls rather than gridlines, because the single
 * most important thing on this chart is that the line must stay between them. The
 * ghost trace shows the same feeder a moment ago, before the current command was
 * applied, so the learner sees the size of their own effect rather than being told it.
 */

import { N_BUS, STATION_BUSES } from '../sim/network.js';
import { V_LOWER, V_UPPER } from '../sim/projection.js';

const WIDTH = 420;
const HEIGHT = 146;
const PAD_L = 40;
const PAD_R = 12;
const PAD_T = 10;
const PAD_B = 26;

const V_MIN_AXIS = 0.84;
const V_MAX_AXIS = 1.06;

interface Props {
  voltages: Float64Array;
  ghost?: Float64Array;
  focusBus: number | null;
  onFocusBus?: (bus: number | null) => void;
}

function x(bus: number): number {
  return PAD_L + ((bus - 1) / (N_BUS - 1)) * (WIDTH - PAD_L - PAD_R);
}

function y(v: number): number {
  const t = (v - V_MIN_AXIS) / (V_MAX_AXIS - V_MIN_AXIS);
  return HEIGHT - PAD_B - t * (HEIGHT - PAD_T - PAD_B);
}

function path(voltages: Float64Array): string {
  let d = '';
  for (let bus = 1; bus <= N_BUS; bus++) {
    d += `${bus === 1 ? 'M' : 'L'}${x(bus).toFixed(1)},${y(voltages[bus]).toFixed(1)}`;
  }
  return d;
}

export function VoltageProfile({ voltages, ghost, focusBus, onFocusBus }: Props) {
  const ticks = [0.85, 0.90, 0.95, 1.0, 1.05];

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width="100%"
      role="img"
      aria-label="Voltage magnitude against bus index, with the statutory limits marked"
      onMouseLeave={() => onFocusBus?.(null)}
    >
      {/* The legal band, as a region rather than a pair of lines. */}
      <rect
        x={PAD_L}
        y={y(V_UPPER)}
        width={WIDTH - PAD_L - PAD_R}
        height={y(V_LOWER) - y(V_UPPER)}
        fill="rgba(79, 179, 162, 0.06)"
      />

      {ticks.map((v) => (
        <g key={v}>
          <line
            x1={PAD_L}
            x2={WIDTH - PAD_R}
            y1={y(v)}
            y2={y(v)}
            stroke={v === V_LOWER || v === V_UPPER ? 'var(--limit)' : 'var(--line)'}
            strokeWidth={v === V_LOWER || v === V_UPPER ? 1.4 : 1}
            strokeDasharray={v === V_LOWER || v === V_UPPER ? '5 3' : undefined}
          />
          <text
            x={PAD_L - 6}
            y={y(v) + 3.5}
            textAnchor="end"
            fontSize="9"
            fontFamily="var(--mono)"
            fill={v === V_LOWER || v === V_UPPER ? 'var(--limit)' : 'var(--ink-3)'}
          >
            {v.toFixed(2)}
          </text>
        </g>
      ))}

      {STATION_BUSES.map((bus) => (
        <line
          key={bus}
          x1={x(bus)}
          x2={x(bus)}
          y1={PAD_T}
          y2={HEIGHT - PAD_B}
          stroke="rgba(79, 163, 240, 0.18)"
          strokeWidth={1}
        />
      ))}

      {ghost && (
        <path
          d={path(ghost)}
          fill="none"
          stroke="var(--ink-3)"
          strokeWidth={1.2}
          strokeDasharray="3 3"
          opacity={0.8}
        />
      )}

      <path d={path(voltages)} fill="none" stroke="var(--ink)" strokeWidth={1.8} />

      {STATION_BUSES.map((bus) => (
        <circle
          key={bus}
          cx={x(bus)}
          cy={y(voltages[bus])}
          r={bus === focusBus ? 4 : 2.6}
          fill={voltages[bus] < V_LOWER ? 'var(--limit)' : 'var(--charge)'}
        />
      ))}

      {[1, 8, 16, 24].map((bus) => (
        <text
          key={bus}
          x={x(bus)}
          y={HEIGHT - 9}
          textAnchor="middle"
          fontSize="9"
          fontFamily="var(--mono)"
          fill="var(--ink-3)"
        >
          {bus}
        </text>
      ))}

      <text
        x={PAD_L}
        y={HEIGHT - 1}
        fontSize="9.5"
        fontFamily="var(--mono)"
        fill="var(--ink-3)"
      >
        bus index
      </text>

      {/* Invisible hit targets, so hovering the chart highlights a bus in the village. */}
      {Array.from({ length: N_BUS }, (_, i) => i + 1).map((bus) => (
        <rect
          key={bus}
          x={x(bus) - 5}
          y={PAD_T}
          width={10}
          height={HEIGHT - PAD_T - PAD_B}
          fill="transparent"
          onMouseEnter={() => onFocusBus?.(bus)}
        />
      ))}
    </svg>
  );
}
