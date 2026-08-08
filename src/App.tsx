/**
 * Bus 18 — the operator's screen.
 *
 * One screen, three registers: the village you feel it in, the console you measure it
 * with, and the map that shows where your decision sits among the alternatives. No
 * navigation, because the whole point is relating the three to each other at once.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { LiveSim, runEpisode } from './sim/live.js';
import { STATION_BUSES, type GridKind } from './sim/network.js';
import { V_LOWER } from './sim/projection.js';
import { STEPS_PER_DAY, clockOf, priceTier } from './sim/profiles.js';
import {
  droop,
  placeholderController,
  uncoordinated,
  type Controller,
} from './sim/controllers.js';
import { Village } from './ui/Village.js';
import { VoltageProfile } from './ui/VoltageProfile.js';
import { ParetoMap, type Dot } from './ui/ParetoMap.js';

const SLIDER_LIMIT_KW = 800;
const SPEEDS = [1, 4, 16, 64] as const;

const REFERENCE_CONTROLLERS: Controller[] = [
  uncoordinated,
  droop,
  placeholderController({
    id: 'sac-lag',
    label: 'SAC-Lag (plain deep RL)',
    eagerness: 0.85,
    backoffPu: 0.952,
    arbitrage: true,
    usesProjection: false,
  }),
  placeholderController({
    id: 'safesac',
    label: 'SafeSAC',
    eagerness: 0.95,
    backoffPu: 0.948,
    arbitrage: false,
    usesProjection: true,
  }),
];

export default function App() {
  const [grid, setGrid] = useState<GridKind>('weak');
  const [loadScale, setLoadScale] = useState(0.5);
  const [projection, setProjection] = useState(true);
  const [commands, setCommands] = useState<number[]>([0, 0, 0, 0]);
  const [speed, setSpeed] = useState<number>(16);
  const [playing, setPlaying] = useState(false);
  const [focusBus, setFocusBus] = useState<number | null>(null);
  const [dots, setDots] = useState<Dot[]>([]);
  const [, forceRender] = useState(0);

  const simRef = useRef<LiveSim | null>(null);
  if (simRef.current === null) simRef.current = new LiveSim({ grid, loadScale });

  // Rebuild the world when a scenario knob moves. The learner's accumulated dots stay,
  // because comparing a weak-grid run with a strong-grid one is the point.
  useEffect(() => {
    simRef.current = new LiveSim({ grid, loadScale });
    setCommands([0, 0, 0, 0]);
    setPlaying(false);
    forceRender((n) => n + 1);
  }, [grid, loadScale]);

  const sim = simRef.current;
  const commandsRef = useRef(commands);
  commandsRef.current = commands;

  const finishRun = useCallback(() => {
    const totals = sim.finalTotals();
    setDots((prior) => [
      ...prior.filter((d) => d.id !== 'manual'),
      {
        id: 'manual',
        label: 'You',
        violationRate: totals.violationRate,
        socMet: totals.socMet,
        provenance: 'human',
        mine: true,
      },
    ]);
  }, [sim]);

  const advance = useCallback(() => {
    if (sim.finished) {
      setPlaying(false);
      return;
    }
    sim.advance(commandsRef.current, projection);
    if (sim.finished) {
      setPlaying(false);
      finishRun();
    }
    forceRender((n) => n + 1);
  }, [sim, projection, finishRun]);

  // Playback clock. Steps are emitted on a wall-clock accumulator rather than one per
  // frame, so the day runs at the same rate on a 60 Hz and a 120 Hz display.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let previous = performance.now();
    let carry = 0;

    const tick = (now: number): void => {
      const elapsed = (now - previous) / 1000;
      previous = now;
      carry += elapsed * speed;
      let budget = 0;
      while (carry >= 1 && budget < 40) {
        carry -= 1;
        budget++;
        if (sim.finished) break;
        sim.advance(commandsRef.current, projection);
      }
      if (sim.finished) {
        setPlaying(false);
        finishRun();
      }
      forceRender((n) => n + 1);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, sim, projection, finishRun]);

  const reset = useCallback(() => {
    sim.reset();
    setCommands([0, 0, 0, 0]);
    setPlaying(false);
    forceRender((n) => n + 1);
  }, [sim]);

  const runReference = useCallback(
    (controller: Controller) => {
      const result = runEpisode(controller, { grid, loadScale });
      setDots((prior) => [
        ...prior.filter((d) => d.id !== controller.id),
        {
          id: controller.id,
          label: controller.label,
          violationRate: result.violationRate,
          socMet: result.socMet,
          provenance: result.provenance,
          mine: false,
        },
      ]);
    },
    [grid, loadScale],
  );

  // Keyboard. Everything reachable without a mouse, which the accessibility criterion
  // asks for and which also makes a clean take for the video.
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.target instanceof HTMLInputElement && event.key !== 'Escape') return;
      switch (event.key) {
        case ' ':
          event.preventDefault();
          setPlaying((p) => !p);
          break;
        case 'ArrowRight':
          event.preventDefault();
          advance();
          break;
        case 'p':
        case 'P':
          setProjection((v) => !v);
          break;
        case 'g':
        case 'G':
          setGrid((v) => (v === 'weak' ? 'strong' : 'weak'));
          break;
        case 'r':
        case 'R':
          reset();
          break;
        case 'q':
        case 'Q':
          setCommands([0, 0, 0, 0]);
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [advance, reset]);

  const preview = projection ? sim.preview(commands) : { safeKw: sim.clampToFleet(commands), relaxed: false };
  const displayed = sim.last?.voltages ?? sim.background;
  const totals = sim.totals();
  const step = Math.min(sim.step, STEPS_PER_DAY - 1);
  const tier = priceTier(step);

  const worstBus = sim.last?.vMinBus ?? 18;
  const worstV = sim.last?.vMin ?? sim.background[18];
  const outOfBand = sim.last?.violations ?? 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          Bus 18<span>IEEE 33-bus feeder · {grid} grid</span>
        </div>

        <div className="clock">{clockOf(step)}</div>
        <span className="tier" data-tier={tier}>
          {tier} · ${sim.price.toFixed(2)}/kWh
        </span>

        <div className="transport">
          <button className="ctl" onClick={() => setPlaying((p) => !p)} disabled={sim.finished}>
            {playing ? 'Pause' : 'Play'}
          </button>
          <button className="ctl" onClick={advance} disabled={playing || sim.finished}>
            Step
          </button>
          <button className="ctl" onClick={reset}>
            Reset
          </button>
          {SPEEDS.map((s) => (
            <button
              key={s}
              className="ctl"
              data-active={speed === s}
              onClick={() => setSpeed(s)}
            >
              ×{s}
            </button>
          ))}
        </div>

        <div className="spacer" />
        <span className="hint">
          {sim.finished ? 'Day complete — your dot is on the map' : `${sim.last?.connected ?? 0} vehicles plugged in`}
        </span>
      </header>

      <div className="main">
        <div className="village">
          <Village
            voltages={displayed}
            stationKw={sim.last?.safeKw ?? [0, 0, 0, 0]}
            solarKw={sim.solarKw}
            dayFraction={step / STEPS_PER_DAY}
            focusBus={focusBus}
            animate
          />
          <div className="village-readout">
            worst bus <b>{worstBus}</b> at{' '}
            <b className={worstV < V_LOWER ? 'bad' : undefined}>{worstV.toFixed(4)} pu</b>
            <br />
            <span className={outOfBand > 0 ? 'bad' : undefined}>
              {outOfBand} of 33 buses outside [0.95, 1.05]
            </span>
            <br />
            solar {sim.solarKw.toFixed(0)} kW per array
          </div>
        </div>

        <div className="console">
          <section className="section">
            <h2>Voltage profile</h2>
            <VoltageProfile
              voltages={displayed}
              ghost={sim.last?.backgroundVoltages}
              focusBus={focusBus}
              onFocusBus={setFocusBus}
            />
            <p className="hint">
              Solid: now. Dotted: before this step's command.
            </p>
          </section>

          <section className="section">
            <h2>Your dispatch</h2>
            {STATION_BUSES.map((bus, k) => {
              const cap = sim.capabilities[k];
              const raw = commands[k];
              const safe = preview.safeKw[k];
              const curtailed = Math.abs(raw - safe) > 1;
              const toPct = (kw: number) => ((kw + SLIDER_LIMIT_KW) / (2 * SLIDER_LIMIT_KW)) * 100;

              return (
                <div
                  className="station"
                  key={bus}
                  onMouseEnter={() => setFocusBus(bus)}
                  onMouseLeave={() => setFocusBus(null)}
                >
                  <div className="station-name">
                    <b>Station {k + 1}</b>
                    bus {bus} · {cap?.connected ?? 0} EV
                  </div>

                  <div className="slider-wrap">
                    <div className="slider-track" />
                    <div
                      className="slider-available"
                      style={{
                        left: `${toPct(cap?.maxDrawKw ?? 0)}%`,
                        width: `${toPct(cap?.maxInjectKw ?? 0) - toPct(cap?.maxDrawKw ?? 0)}%`,
                      }}
                    />
                    {curtailed && (
                      <div
                        className="slider-gap"
                        style={{
                          left: `${Math.min(toPct(raw), toPct(safe))}%`,
                          width: `${Math.abs(toPct(raw) - toPct(safe))}%`,
                        }}
                      />
                    )}
                    <div className="slider-safe" style={{ left: `calc(${toPct(safe)}% - 1.5px)` }} />
                    <input
                      type="range"
                      min={-SLIDER_LIMIT_KW}
                      max={SLIDER_LIMIT_KW}
                      step={10}
                      value={raw}
                      aria-label={`Station ${k + 1} at bus ${bus}, kilowatts, negative is charging`}
                      onChange={(e) => {
                        const next = commands.slice();
                        next[k] = Number(e.target.value);
                        setCommands(next);
                      }}
                    />
                  </div>

                  <div className="station-value">
                    {safe.toFixed(0)} kW
                    {curtailed && (
                      <span className="curtailed">asked {raw.toFixed(0)}</span>
                    )}
                  </div>
                </div>
              );
            })}
            <p className="hint">
              Negative charges, positive sends power back. The green mark is what the
              safety layer will actually execute.
            </p>
          </section>

          <section className="section">
            <h2>Scenario</h2>
            <div className="row">
              <button
                className="ctl"
                data-active={projection}
                onClick={() => setProjection((v) => !v)}
              >
                Safety projection {projection ? 'ON' : 'OFF'}
              </button>
              <button
                className="ctl"
                data-active={grid === 'weak'}
                onClick={() => setGrid(grid === 'weak' ? 'strong' : 'weak')}
              >
                {grid === 'weak' ? 'Weak feeder' : 'Strong feeder'}
              </button>
              <select
                className="ctl"
                value={loadScale}
                onChange={(e) => setLoadScale(Number(e.target.value))}
                aria-label="Load scale"
              >
                <option value={0.3}>Load 0.30</option>
                <option value={0.5}>Load 0.50</option>
                <option value={0.7}>Load 0.70</option>
              </select>
            </div>
          </section>

        </div>
      </div>

      <div className="bottom">
        <div className="bottom-left">
          <section className="section">
            <h2>Your run so far</h2>
            <dl className="scorecard">
              <div className="metric">
                <dt>Violations</dt>
                <dd data-state={totals.violationRate > 0.05 ? 'bad' : 'good'}>
                  {totals.violationRate.toFixed(3)}
                </dd>
              </div>
              <div className="metric">
                <dt>SoC met</dt>
                <dd data-state={totals.socMet > 0.5 ? 'good' : 'bad'}>
                  {totals.socMet.toFixed(3)}
                </dd>
              </div>
              <div className="metric">
                <dt>Departed</dt>
                <dd>{totals.departed}</dd>
              </div>
              <div className="metric">
                <dt>Net cost</dt>
                <dd>${totals.netCostUsd.toFixed(0)}</dd>
              </div>
              <div className="metric">
                <dt>Worst V</dt>
                <dd data-state={totals.vMinPu < V_LOWER ? 'bad' : 'good'}>
                  {totals.vMinPu.toFixed(4)}
                </dd>
              </div>
            </dl>
          </section>

          <section className="section">
            <h2>Compare against</h2>
            <div className="row">
              {REFERENCE_CONTROLLERS.map((c) => (
                <button key={c.id} className="ctl" onClick={() => runReference(c)}>
                  {c.label}
                </button>
              ))}
            </div>
            {REFERENCE_CONTROLLERS.some(
              (c) => c.provenance === 'placeholder' && dots.some((d) => d.id === c.id),
            ) && (
              <p className="provenance-note">
                * SAC-Lag and SafeSAC are labelled stand-ins, not the trained agents —
                their recorded episodes are still to be exported from the thesis notebook.
              </p>
            )}
          </section>
        </div>

        <div className="map-wrap">
          <h2>The map — every run you finish leaves a dot</h2>
          <ParetoMap dots={dots} />
        </div>
      </div>
    </div>
  );
}
