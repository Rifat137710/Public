/**
 * The village canvas — a resizing, device-pixel-aware surface, and the operator's primary
 * work surface rather than a readout beside one.
 *
 * Two things you can do here that you cannot do to a picture. You can point at any street
 * and the whole console follows: the voltage profile marks that bus, and the readout tells
 * you what it is doing and how far down the line it sits. And you can grab a charging
 * station where it stands and drag it, setting real power on the real feeder without ever
 * moving your eyes to a control panel.
 *
 * Everything the pointer can do here is also reachable from the console with a keyboard,
 * so this is an additional way in and never the only one.
 */

import { useCallback, useEffect, useRef } from 'react';
import { STATION_BUSES } from '../sim/network.js';
import { PLACES } from './layout.js';
import { busAt, drawVillage } from './village.js';

/** Vertical drag sensitivity. A full sweep of a laptop trackpad covers the whole range. */
const KW_PER_PIXEL = 6;

interface Props {
  voltages: Float64Array;
  stationKw: readonly number[];
  solarKw: number;
  dayFraction: number;
  focusBus: number | null;
  /** Lamps below the statutory floor flicker, which needs a running clock. */
  animate: boolean;
  /** The street being inspected. */
  selectedBus?: number | null;
  onSelectBus?: (bus: number | null) => void;
  onHoverBus?: (bus: number | null) => void;
  /** Present only while the learner is allowed to drive. */
  onDragStation?: (index: number, kw: number) => void;
  /** Current raw requests, so a drag starts from where the station already is. */
  requestKw?: readonly number[];
}

export function Village(props: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const sizeRef = useRef({ width: 0, height: 0 });
  const dragRef = useRef<{ station: number; startY: number; startKw: number } | null>(null);
  const draggingRef = useRef<number | null>(null);

  const propsRef = useRef<Props>(props);
  propsRef.current = props;

  /** Canvas-space coordinates for a pointer event, in CSS pixels. */
  const localPoint = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }, []);

  const hit = useCallback((x: number, y: number) => {
    const { width, height } = sizeRef.current;
    if (width === 0) return null;
    return busAt(width, height, PLACES, x, y);
  }, []);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const { x, y } = localPoint(event);
      const bus = hit(x, y);
      if (bus === null) {
        propsRef.current.onSelectBus?.(null);
        return;
      }

      propsRef.current.onSelectBus?.(bus);

      const station = STATION_BUSES.indexOf(bus);
      if (station >= 0 && propsRef.current.onDragStation) {
        dragRef.current = {
          station,
          startY: y,
          startKw: propsRef.current.requestKw?.[station] ?? 0,
        };
        draggingRef.current = station;
        event.currentTarget.setPointerCapture(event.pointerId);
      }
    },
    [hit, localPoint],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const { x, y } = localPoint(event);
      const drag = dragRef.current;

      if (drag) {
        // Up sends power back to the grid, down charges — the same direction the console
        // slider moves, so the two controls never contradict each other.
        const next = drag.startKw + (drag.startY - y) * KW_PER_PIXEL;
        propsRef.current.onDragStation?.(drag.station, next);
        return;
      }

      propsRef.current.onHoverBus?.(hit(x, y));
    },
    [hit, localPoint],
  );

  const endDrag = useCallback(() => {
    dragRef.current = null;
    draggingRef.current = null;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = (): void => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(1, Math.floor(rect.height));
      sizeRef.current = { width, height };
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
      const { width, height } = sizeRef.current;
      drawVillage(ctx, width, height, {
        places: PLACES,
        voltages: p.voltages,
        stationKw: p.stationKw,
        solarKw: p.solarKw,
        dayFraction: p.dayFraction,
        timeMs,
        focusBus: p.focusBus,
        selectedBus: p.selectedBus ?? null,
        draggingStation: draggingRef.current,
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

  return (
    <canvas
      ref={canvasRef}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onPointerLeave={() => {
        if (!dragRef.current) propsRef.current.onHoverBus?.(null);
      }}
      style={{ touchAction: 'none' }}
    />
  );
}
