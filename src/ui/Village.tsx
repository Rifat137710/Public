/**
 * The village canvas: a resizing, device-pixel-aware surface that redraws whenever the
 * feeder state changes, and animates continuously only while lamps are flickering.
 */

import { useEffect, useRef } from 'react';
import { NOMINAL_LOAD_KW } from '../sim/network.js';
import { buildLayout } from './layout.js';
import { drawVillage } from './village.js';

const PLACES = buildLayout(NOMINAL_LOAD_KW);

interface Props {
  voltages: Float64Array;
  stationKw: readonly number[];
  solarKw: number;
  dayFraction: number;
  focusBus: number | null;
  /** Lamps below the statutory floor flicker, which needs a running clock. */
  animate: boolean;
}

export function Village({
  voltages,
  stationKw,
  solarKw,
  dayFraction,
  focusBus,
  animate,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const propsRef = useRef<Props>({
    voltages,
    stationKw,
    solarKw,
    dayFraction,
    focusBus,
    animate,
  });
  propsRef.current = { voltages, stationKw, solarKw, dayFraction, focusBus, animate };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = 0;
    let height = 0;

    const resize = (): void => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    // Read the preference live rather than once: people change it mid-session, and a
    // reader who turns motion off should not have to reload to be taken seriously.
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

    const render = (timeMs: number): void => {
      const p = propsRef.current;
      drawVillage(ctx, width, height, {
        places: PLACES,
        voltages: p.voltages,
        stationKw: p.stationKw,
        solarKw: p.solarKw,
        dayFraction: p.dayFraction,
        timeMs,
        focusBus: p.focusBus,
        reducedMotion: motionQuery.matches,
      });
      frameRef.current = requestAnimationFrame(render);
    };
    frameRef.current = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frameRef.current);
      observer.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} />;
}
