/**
 * Bus 18 — the operator's screen.
 *
 * One screen, three registers: the village you feel it in, the console you measure it
 * with, and the map that shows where your decision sits among the alternatives. No
 * navigation, because the whole point is relating the three to each other at once.
 *
 * The six-stage arc drives which of those registers is visible when. Controls appear as
 * a stage needs them; a learner handed every option at once explores none of them.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LiveSim, runEpisode } from './sim/live.js';
import { NOMINAL_LOAD_KW, STATION_BUSES, type GridKind } from './sim/network.js';
import { DEFAULT_MARGIN_PU, V_LOWER } from './sim/projection.js';
import { STEPS_PER_DAY, clockOf, priceTier } from './sim/profiles.js';
import {
  droop,
  placeholderController,
  uncoordinated,
  type Controller,
} from './sim/controllers.js';
import { STAGES, unlockedBy, type Unlock } from './content/stages.js';
import { SHORTLIST } from './content/thesis.js';
import { Village } from './ui/Village.js';
import { MAX_DEPTH, depthOf } from './ui/layout.js';
import { VoltageProfile } from './ui/VoltageProfile.js';
import { ParetoMap, type Dot } from './ui/ParetoMap.js';
import { StageCard } from './ui/StageCard.js';
import { Leaderboard, type Candidate } from './ui/Leaderboard.js';
import { Debrief } from './ui/Debrief.js';

const SLIDER_LIMIT_KW = 800;
const SPEEDS = [1, 4, 16, 64] as const;

const sacLag = placeholderController({
  id: 'sac-lag',
  label: 'SAC-Lag (plain deep RL)',
  eagerness: 0.85,
  backoffPu: 0.952,
  arbitrage: true,
  usesProjection: false,
});

const safeSac = placeholderController({
  id: 'safesac',
  label: 'SafeSAC',
  eagerness: 0.95,
  backoffPu: 0.948,
  arbitrage: false,
  usesProjection: true,
});

/**
 * The stage-6 trap: an agent trained on a stiff grid and deployed on this one. It holds
 * a near-perfect safety record and turns a profit, by declining to charge anybody.
 */
const sacLagShifted = placeholderController({
  id: 'sac-lag-shift',
  label: 'SAC-Lag (trained on a strong grid)',
  eagerness: 0,
  backoffPu: 0.9,
  arbitrage: true,
  usesProjection: false,
});

const CONTROLLERS: Record<string, Controller> = {
  uncoordinated,
  droop,
  'sac-lag': sacLag,
  safesac: safeSac,
  'sac-lag-shift': sacLagShifted,
};

const COMPARABLE = [uncoordinated, droop, sacLag, safeSac];

type Phase = 'brief' | 'running' | 'reveal' | 'debrief' | 'sandbox';

export default function App() {
  const [stageIndex, setStageIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>('brief');
  const [pick, setPick] = useState<string | null>(null);

  const [grid, setGrid] = useState<GridKind>('weak');
  const [loadScale, setLoadScale] = useState(0.5);
  /**
   * How far inside the statutory band the safety layer aims, in per unit.
   *
   * This is the one number in the whole system that lets a learner buy safety and watch
   * the price arrive. It has an optimum rather than a direction — past it you pay in
   * service *and* get worse safety, because once the tightened band is already breached
   * the projection falls into its relaxed branch and stops steering. Wound far enough up
   * it reproduces the stage-6 trap from the inside: a controller with an excellent
   * violation rate that serves nobody.
   */
  const [marginPu, setMarginPu] = useState(DEFAULT_MARGIN_PU);
  const [projection, setProjection] = useState(false);
  const [commands, setCommands] = useState<number[]>([0, 0, 0, 0]);
  const [speed, setSpeed] = useState<number>(16);
  const [playing, setPlaying] = useState(false);
  const [focusBus, setFocusBus] = useState<number | null>(null);
  const [selectedBus, setSelectedBus] = useState<number | null>(null);
  const [dots, setDots] = useState<Dot[]>([]);
  const [, forceRender] = useState(0);

  const stage = STAGES[Math.min(stageIndex, STAGES.length - 1)];
  const inArc = phase !== 'sandbox';
  const unlocked: Set<Unlock> = useMemo(
    () => (inArc ? unlockedBy(stageIndex) : new Set(['map', 'projection', 'grid', 'loadScale', 'compare', 'margin'] as Unlock[])),
    [inArc, stageIndex],
  );

  const simRef = useRef<LiveSim | null>(null);
  if (simRef.current === null) simRef.current = new LiveSim({ grid, loadScale, marginPu });
  const sim = simRef.current;

  const commandsRef = useRef(commands);
  commandsRef.current = commands;

  const rebuild = useCallback(() => {
    simRef.current = new LiveSim({ grid, loadScale, marginPu });
    setCommands([0, 0, 0, 0]);
    setPlaying(false);
    forceRender((n) => n + 1);
  }, [grid, loadScale, marginPu]);

  useEffect(() => {
    rebuild();
  }, [rebuild]);

  const activeController: Controller | null =
    inArc && stage.mode === 'watch' && stage.controllerId
      ? CONTROLLERS[stage.controllerId] ?? null
      : null;

  const recordDot = useCallback(
    (id: string, label: string, provenance: string, mine: boolean) => {
      const totals = sim.finalTotals();
      setDots((prior) => [
        ...prior.filter((d) => d.id !== id),
        {
          id,
          label,
          violationRate: totals.violationRate,
          socMet: totals.socMet,
          lossKwh: totals.totalLossKwh,
          provenance,
          mine,
        },
      ]);
      return totals;
    },
    [sim],
  );

  const onDayComplete = useCallback(() => {
    setPlaying(false);
    if (!inArc) {
      recordDot('manual', 'You', 'human', true);
      return;
    }
    if (activeController) {
      recordDot(activeController.id, activeController.label, activeController.provenance, false);
    } else {
      recordDot('manual', 'You', 'human', true);
    }
    setPhase('reveal');
  }, [inArc, activeController, recordDot]);

  const stepOnce = useCallback(() => {
    if (sim.finished) return;
    if (activeController) {
      sim.advanceWith(activeController, stage.projection ?? activeController.usesProjection);
    } else {
      sim.advance(commandsRef.current, projection);
    }
  }, [sim, activeController, stage.projection, projection]);

  const advance = useCallback(() => {
    if (sim.finished) return;
    stepOnce();
    if (sim.finished) onDayComplete();
    forceRender((n) => n + 1);
  }, [sim, stepOnce, onDayComplete]);

  // Playback clock. Steps run on a wall-clock accumulator rather than one per frame, so
  // the day takes the same time on a 60 Hz and a 120 Hz display.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let previous = performance.now();
    let carry = 0;

    const tick = (now: number): void => {
      carry += ((now - previous) / 1000) * speed;
      previous = now;
      let budget = 0;
      while (carry >= 1 && budget < 40 && !sim.finished) {
        carry -= 1;
        budget++;
        stepOnce();
      }
      if (sim.finished) onDayComplete();
      forceRender((n) => n + 1);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, sim, stepOnce, onDayComplete]);

  const reset = useCallback(() => {
    sim.reset();
    setCommands([0, 0, 0, 0]);
    setPlaying(false);
    forceRender((n) => n + 1);
  }, [sim]);

  const beginStage = useCallback(() => {
    if (stage.projection !== undefined) setProjection(stage.projection);
    rebuild();
    setPhase('running');
    if (stage.mode === 'watch') setPlaying(true);
  }, [stage, rebuild]);

  const nextStage = useCallback(() => {
    // The arc does not end on the stage 6 reveal. Six stages produce a sequence of
    // moments; the debrief is where they are consolidated into something retained.
    if (stageIndex >= STAGES.length - 1) {
      setPhase('debrief');
      return;
    }
    setStageIndex((n) => n + 1);
    setPhase('brief');
  }, [stageIndex]);

  const openSandbox = useCallback(() => {
    setPhase('sandbox');
    rebuild();
  }, [rebuild]);

  const skipToSandbox = useCallback(() => {
    setPhase('sandbox');
    rebuild();
  }, [rebuild]);

  const runReference = useCallback(
    (controller: Controller) => {
      const result = runEpisode(controller, { grid, loadScale, marginPu });
      setDots((prior) => [
        ...prior.filter((d) => d.id !== controller.id),
        {
          id: controller.id,
          label: controller.label,
          violationRate: result.violationRate,
          socMet: result.socMet,
          lossKwh: result.totalLossKwh,
          provenance: result.provenance,
          mine: false,
        },
      ]);
    },
    [grid, loadScale, marginPu],
  );

  /**
   * Stage 6's shortlist is the thesis's own evaluation, not a run of this simulator.
   *
   * That is deliberate and it is the more honest of the two options. A procurement
   * decision is made from a report somebody else produced — you are handed a table and
   * you have to read it, which is the entire skill the stage is about. Scoring the
   * candidates here instead would quietly hand the learner a table computed by the same
   * engine they have been watching all afternoon, which is not the position anybody is
   * ever in.
   *
   * It also means the trap is now a measured result rather than a device. The agent that
   * posts the best safety score and the only profit put zero kilowatt-hours into a
   * battery across the whole evaluation, and nobody arranged that.
   */
  const candidates: Candidate[] = useMemo(() => {
    if (!inArc || stage.mode !== 'choose') return [];
    return SHORTLIST.map((r) => ({
      id: r.id,
      label: r.label,
      violationRate: r.violationRate,
      netCostUsd: r.netCostUsd,
      socMet: r.socMet,
      provenance: 'measured',
    }));
  }, [inArc, stage.mode]);

  const choose = useCallback((id: string) => {
    // The pick deliberately does not become a dot on the map. The map's axes are this
    // simulator's — bus-steps out of 288 x 33, service over all 287 vehicles — and the
    // table's are the thesis's — steps out of 288, service over the ~27 that departed.
    // Putting one on the other would be the exact mistake stage 6 exists to teach.
    setPick(id);
    setPhase('reveal');
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.target instanceof HTMLInputElement) return;
      if (phase !== 'running' && phase !== 'sandbox') return;
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
          if (unlocked.has('projection')) setProjection((v) => !v);
          break;
        case 'g':
        case 'G':
          if (unlocked.has('grid')) setGrid((v) => (v === 'weak' ? 'strong' : 'weak'));
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
  }, [advance, reset, phase, unlocked]);

  const preview = projection
    ? sim.preview(commands)
    : { safeKw: sim.clampToFleet(commands), relaxed: false };
  const displayed = sim.last?.voltages ?? sim.background;
  const totals = sim.totals();
  const step = Math.min(sim.step, STEPS_PER_DAY - 1);
  const tier = priceTier(step);
  const worstBus = sim.last?.vMinBus ?? 18;
  const worstV = sim.last?.vMin ?? sim.background[18];
  const outOfBand = sim.last?.violations ?? 0;

  const manualDriving = phase === 'sandbox' || (inArc && stage.mode === 'manual');
  /**
   * The table stays up through the reveal.
   *
   * It used to unmount the moment a choice was made, which meant the reveal card headed
   * "The third column" was the only place that column ever existed — Leaderboard's whole
   * revealed state, the service figure, the collapsed row, the "your pick" marker, was
   * unreachable code. Being told the number you were not shown is an argument. Watching
   * it appear in the row you just chose is the lesson.
   */
  const showChoice = inArc && stage.mode === 'choose' && (phase === 'running' || phase === 'reveal');

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

        {!showChoice && (
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
              <button key={s} className="ctl" data-active={speed === s} onClick={() => setSpeed(s)}>
                ×{s}
              </button>
            ))}
          </div>
        )}

        <div className="spacer" />

        {inArc ? (
          <span className="stage-flag">
            <b>
              Stage {stage.n}/6 · {stage.eyebrow}
            </b>
            {stage.task}
          </span>
        ) : (
          <span className="stage-flag">
            <b>Sandbox</b> Everything unlocked. Try to beat SafeSAC.
          </span>
        )}
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
            selectedBus={selectedBus}
            onSelectBus={setSelectedBus}
            onHoverBus={setFocusBus}
            requestKw={commands}
            onDragStation={
              manualDriving
                ? (k, kw) => {
                    const next = commands.slice();
                    next[k] = Math.max(-SLIDER_LIMIT_KW, Math.min(SLIDER_LIMIT_KW, Math.round(kw / 10) * 10));
                    setCommands(next);
                  }
                : undefined
            }
          />
          <div className="village-hud">
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

          {selectedBus !== null && (
            <div className="street-card">
              <div className="street-head">
                Street at bus <b>{selectedBus}</b>
                <button
                  className="street-close"
                  onClick={() => setSelectedBus(null)}
                  aria-label="Stop inspecting this street"
                >
                  ×
                </button>
              </div>
              <dl>
                <div>
                  <dt>Voltage</dt>
                  <dd className={(displayed[selectedBus] ?? 1) < V_LOWER ? 'bad' : undefined}>
                    {(displayed[selectedBus] ?? 1).toFixed(4)} pu
                  </dd>
                </div>
                <div>
                  <dt>Down the line</dt>
                  <dd>
                    {depthOf(selectedBus)} of {MAX_DEPTH} poles
                  </dd>
                </div>
                <div>
                  <dt>Demand</dt>
                  <dd>{(NOMINAL_LOAD_KW[selectedBus] ?? 0).toFixed(0)} kW</dd>
                </div>
                {STATION_BUSES.includes(selectedBus) && (
                  <div>
                    <dt>Station</dt>
                    <dd>
                      {(sim.last?.safeKw[STATION_BUSES.indexOf(selectedBus)] ?? 0).toFixed(0)} kW
                      {manualDriving && <span className="street-hint">drag it</span>}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          )}
          </div>
        </div>

        <div className="console">
          {showChoice ? (
            <Leaderboard candidates={candidates} chosen={pick} onChoose={choose} />
          ) : (
            <>
              <section className="section">
                <h2>Voltage profile</h2>
                <VoltageProfile
                  voltages={displayed}
                  ghost={sim.last?.backgroundVoltages}
                  focusBus={focusBus}
                  onFocusBus={setFocusBus}
                />
                <p className="hint">Solid: now. Dotted: before this step's command.</p>
              </section>

              <section className="section">
                <h2>{manualDriving ? 'Your dispatch' : `${activeController?.label ?? ''} is driving`}</h2>
                {STATION_BUSES.map((bus, k) => {
                  const cap = sim.capabilities[k];
                  const raw = manualDriving ? commands[k] : (sim.last?.rawKw[k] ?? 0);
                  const safe = manualDriving ? preview.safeKw[k] : (sim.last?.safeKw[k] ?? 0);
                  const curtailed = Math.abs(raw - safe) > 1;
                  const toPct = (kw: number) =>
                    ((kw + SLIDER_LIMIT_KW) / (2 * SLIDER_LIMIT_KW)) * 100;

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
                            data-cause={projection ? 'safety' : 'fleet'}
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
                          disabled={!manualDriving}
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
                          <span className="curtailed" data-cause={projection ? 'safety' : 'fleet'}>
                            asked {raw.toFixed(0)}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
                <p className="hint">
                  Negative charges, positive sends power back. The green mark is what
                  actually gets executed —{' '}
                  {projection
                    ? 'the safety layer curtails anything that would push a bus out of band.'
                    : 'with no safety layer running, the only limit is what the plugged-in vehicles can physically take.'}
                </p>
              </section>

              {(unlocked.has('projection') || unlocked.has('grid')) && (
                <section className="section">
                  <h2>Scenario</h2>
                  <div className="row">
                    {unlocked.has('projection') && (
                      <button
                        className="ctl"
                        data-active={projection}
                        onClick={() => setProjection((v) => !v)}
                      >
                        Safety projection {projection ? 'ON' : 'OFF'}
                      </button>
                    )}
                    {unlocked.has('grid') && (
                      <button
                        className="ctl"
                        data-active={grid === 'weak'}
                        onClick={() => setGrid(grid === 'weak' ? 'strong' : 'weak')}
                      >
                        {grid === 'weak' ? 'Weak feeder' : 'Strong feeder'}
                      </button>
                    )}
                    {unlocked.has('loadScale') && (
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
                    )}
                  </div>
                  {unlocked.has('margin') && (
                    <div className="row margin-row">
                      <label className="margin-label" htmlFor="marginPu">
                        Safety margin
                        <b>{marginPu.toFixed(3)} pu</b>
                      </label>
                      <input
                        id="marginPu"
                        type="range"
                        min={0}
                        max={0.045}
                        step={0.005}
                        value={marginPu}
                        onChange={(e) => setMarginPu(Number(e.target.value))}
                      />
                      <p className="source-note">
                        How far inside the {V_LOWER.toFixed(2)} floor the safety layer aims. It is not a
                        dial that runs from reckless to safe: the thesis picked {DEFAULT_MARGIN_PU.toFixed(3)},
                        and winding it further up costs drivers <em>and</em> lets violations back in, because
                        a layer whose own tightened band is already breached stops steering. Take it to
                        0.045 and you have rebuilt the stage-6 trap yourself.
                      </p>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </div>

      <div className="bottom">
        <div className="bottom-left">
          {!showChoice && (
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
                <dt>Line losses</dt>
                <dd title="Energy burned as heat in the wires. Rises with the square of current.">
                  {totals.totalLossKwh.toFixed(0)} kWh
                </dd>
              </div>
              <div className="metric">
                <dt>Worst V</dt>
                <dd data-state={totals.vMinPu < V_LOWER ? 'bad' : 'good'}>
                  {totals.vMinPu.toFixed(4)}
                </dd>
              </div>
            </dl>
          </section>
          )}

          {unlocked.has('compare') && !showChoice && (
            <section className="section">
              <h2>Compare against</h2>
              <div className="row">
                {COMPARABLE.map((c) => (
                  <button key={c.id} className="ctl" onClick={() => runReference(c)}>
                    {c.label}
                  </button>
                ))}
              </div>
            </section>
          )}

          {dots.some((d) => d.provenance === 'placeholder') && (
            <p className="provenance-note">
              * The SAC-Lag and SafeSAC dots are labelled stand-ins driven by this simulator,
              not the trained agents. What the trained agents actually scored is measured and
              is on the stage 6 table — but only as whole-episode totals, so it cannot be
              replayed step by step here or plotted on these axes.
            </p>
          )}
        </div>

        {unlocked.has('map') ? (
          <div className="map-wrap">
            <h2>The map — every run you finish leaves a dot</h2>
            <ParetoMap dots={dots} />
          </div>
        ) : (
          <div className="map-wrap map-locked">
            <h2>The map</h2>
            <p className="hint">
              Finish your own day first. Your dot goes down before you see how anyone else
              did.
            </p>
          </div>
        )}
      </div>

      {inArc && phase === 'brief' && (
        <StageCard
          eyebrow={`Stage ${stage.n} of 6 · ${stage.eyebrow}`}
          title={stage.title}
          paragraphs={stage.brief}
          actionLabel={stage.mode === 'manual' ? 'Take the controls' : stage.mode === 'choose' ? 'Show me the table' : 'Watch it run'}
          onAction={beginStage}
          secondary={
            stage.n === 1 ? { label: 'Skip to free play', onClick: skipToSandbox } : undefined
          }
        />
      )}

      {inArc && phase === 'reveal' && (
        <StageCard
          tone="reveal"
          eyebrow={`Stage ${stage.n} of 6 · ${stage.eyebrow}`}
          title={stage.revealTitle}
          paragraphs={stage.reveal({
            violationRate: sim.finalTotals().violationRate,
            socMet: sim.finalTotals().socMet,
            netCostUsd: sim.finalTotals().netCostUsd,
            vMinPu: sim.finalTotals().vMinPu,
            lossKwh: sim.finalTotals().totalLossKwh,
            dots,
          })}
          actionLabel={stageIndex >= STAGES.length - 1 ? 'See your debrief' : 'Next stage'}
          onAction={nextStage}
        />
      )}

      {phase === 'debrief' && (
        <Debrief
          dots={dots}
          candidates={candidates}
          pick={pick}
          grid={grid}
          loadScale={loadScale}
          onAction={openSandbox}
        />
      )}
    </div>
  );
}
