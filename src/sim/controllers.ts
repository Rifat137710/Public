/**
 * The controllers the learner compares.
 *
 * Two of these are rules, and they are implemented here in full because a rule is a
 * rule: the uncoordinated baseline and the IEEE 1547 volt-watt droop compute their
 * commands live from the same feeder state the learner sees.
 *
 * The learned controllers are different in kind. Plain RL and Shielded RL are trained
 * networks whose weights live in the source evaluation, and no amount of cleverness here
 * can reconstruct their per-step behaviour. So every controller carries a `provenance`
 * field, and the interface renders it: a controller is either computed live from a
 * published rule, played back from the recorded export, driven by the learner, or an
 * explicitly-labelled stand-in awaiting the export. Nothing pretends to be a trained
 * agent that is not one.
 */

import type { StationCapability } from './fleet.js';

export type Provenance =
  /** Computed live here from a published rule. */
  | 'rule'
  /** The learner's own hands. */
  | 'human'
  /** Per-step actions replayed from the recorded export. */
  | 'recorded'
  /** A documented stand-in. Must be visibly labelled wherever it is shown. */
  | 'placeholder';

export interface ControlContext {
  step: number;
  /** True bus voltages at the start of this step, pu, indexed by node. */
  voltages: Float64Array;
  capabilities: readonly StationCapability[];
  stationBuses: readonly number[];
  /** Retail price this step, $/kWh. */
  price: number;
}

export interface Controller {
  id: string;
  label: string;
  provenance: Provenance;
  /** Shown next to the label wherever provenance is not 'rule'. */
  note?: string;
  /**
   * Whether this controller is wrapped in the safety projection by default.
   *
   * Only Shielded RL is. The uncoordinated baseline has no grid awareness at all, and droop
   * carries its own — the standard's volt-watt curve *is* its safety mechanism, and
   * bolting a network-aware projection onto it would be a different method than the one
   * being compared. Getting this wrong collapses every controller onto the same point
   * and makes the comparison meaningless.
   */
  usesProjection: boolean;
  /** Station commands in kW, injection positive. */
  command(ctx: ControlContext): number[];
  reset?(): void;
}

// ---------------------------------------------------------------------------

/**
 * Everybody charges the moment they plug in, at whatever the charger will give them.
 * No grid awareness of any kind. This is what the feeder gets today.
 */
export const uncoordinated: Controller = {
  id: 'uncoordinated',
  label: 'Uncoordinated',
  provenance: 'rule',
  usesProjection: false,
  command(ctx) {
    return ctx.capabilities.map((cap) => cap.maxDrawKw);
  },
};

// ---------------------------------------------------------------------------

/** Volt-watt breakpoints, per unit. Full service above V1, nothing below V2. */
export const DROOP_V1 = 0.995;
export const DROOP_V2 = 0.968;
export const DROOP_V3 = 0.950;

/**
 * IEEE 1547-2018 volt-watt droop, applied locally at each station.
 *
 * The station reads the voltage at its own bus and derates. Above V1 it charges freely;
 * between V1 and V2 it tapers charging linearly to zero; below V2 it reverses into
 * discharge, reaching full support at V3.
 *
 * The decisive property is what it cannot see. Each station responds only to its own
 * bus, so it has no way to know that curtailing at bus 18 would let bus 33 charge, or
 * that its own discharge is the reason a neighbour is now out of band. That blindness
 * is not a flaw in the implementation — it is the standard, and it is what the
 * comparison is about.
 */
export const droop: Controller = {
  id: 'droop',
  label: 'Droop (IEEE 1547)',
  provenance: 'rule',
  usesProjection: false,
  command(ctx) {
    return ctx.capabilities.map((cap, k) => {
      const v = ctx.voltages[ctx.stationBuses[k]];

      if (v >= DROOP_V1) return cap.maxDrawKw;

      if (v >= DROOP_V2) {
        const fraction = (v - DROOP_V2) / (DROOP_V1 - DROOP_V2);
        return cap.maxDrawKw * fraction;
      }

      const support = Math.min(1, (DROOP_V2 - v) / (DROOP_V2 - DROOP_V3));
      return cap.maxInjectKw * support;
    });
  },
};

// ---------------------------------------------------------------------------

/**
 * The learner. Commands come from the interface rather than from a policy; this exists
 * so a human run is scored on exactly the same path as every automated one.
 */
export function manualController(read: () => number[]): Controller {
  return {
    id: 'manual',
    label: 'You',
    provenance: 'human',
    usesProjection: false,
    command(ctx) {
      const raw = read();
      return ctx.capabilities.map((cap, k) => {
        const wanted = raw[k] ?? 0;
        return Math.min(cap.maxInjectKw, Math.max(cap.maxDrawKw, wanted));
      });
    },
  };
}

// ---------------------------------------------------------------------------

export interface RecordedEpisode {
  controllerId: string;
  label: string;
  /** actions[step][station], kW, injection positive. */
  actions: number[][];
  /** Optional per-step voltages, for cross-checking the replay against the reference study. */
  voltages?: number[][];
  /** Whether the recorded actions were produced with the safety layer in the loop. */
  usesProjection: boolean;
  source: string;
}

/**
 * Play back a controller's actions exactly as the source evaluation recorded them. This is how
 * Plain RL and Shielded RL reach the simulator once the recorded export exists: their
 * behaviour is data, not a reimplementation.
 */
export function recordedController(episode: RecordedEpisode): Controller {
  return {
    id: episode.controllerId,
    label: episode.label,
    provenance: 'recorded',
    usesProjection: episode.usesProjection,
    note: `Replayed from ${episode.source}`,
    command(ctx) {
      const row = episode.actions[Math.min(ctx.step, episode.actions.length - 1)];
      return ctx.capabilities.map((cap, k) =>
        Math.min(cap.maxInjectKw, Math.max(cap.maxDrawKw, row[k] ?? 0)),
      );
    },
  };
}

// ---------------------------------------------------------------------------

export interface PlaceholderShape {
  id: string;
  label: string;
  /**
   * How readily the controller charges when the price is favourable, 0..1.
   * This is a shape parameter of a stand-in, not a property of any trained network.
   */
  eagerness: number;
  /** Voltage at which it starts backing off. Higher is more timid. */
  backoffPu: number;
  /** Whether it will discharge for revenue at peak price. */
  arbitrage: boolean;
  /** Mirrors the method being stood in for: true only for the Shielded RL placeholder. */
  usesProjection: boolean;
}

/**
 * A labelled stand-in for a learned controller.
 *
 * This is NOT the trained agent and must never be presented as one. It exists so the
 * comparison view, the map, and the six-stage arc can be built and tested before the
 * recorded export lands, and so the swap to real recorded behaviour is a data change
 * rather than a code change. Anything rendering a controller with provenance
 * 'placeholder' is required to say so on screen.
 */
export function placeholderController(shape: PlaceholderShape): Controller {
  return {
    id: shape.id,
    label: shape.label,
    provenance: 'placeholder',
    usesProjection: shape.usesProjection,
    note: 'Reference implementation — figures provisional',
    command(ctx) {
      return ctx.capabilities.map((cap, k) => {
        const v = ctx.voltages[ctx.stationBuses[k]];

        if (shape.arbitrage && ctx.price >= 0.30 && cap.maxInjectKw > 0 && v > shape.backoffPu) {
          return cap.maxInjectKw * 0.5;
        }
        if (v < shape.backoffPu) {
          const support = Math.min(1, (shape.backoffPu - v) / 0.015);
          return cap.maxInjectKw * support * 0.6;
        }
        const priceFactor = ctx.price <= 0.08 ? 1.0 : ctx.price <= 0.15 ? 0.7 : 0.25;
        return cap.maxDrawKw * shape.eagerness * priceFactor;
      });
    },
  };
}
