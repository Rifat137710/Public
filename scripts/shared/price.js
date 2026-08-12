/**
 * The retail tariff the day is charged at.
 *
 * Three tiers, as the reference study uses them. It lives here rather than in either page because
 * both of them now show it — the lesson as a readout, the city on the mimic board — and a
 * price that disagreed between the two would make the same evening peak look like two
 * different events.
 *
 * The 17:00 step onto the peak rate is what the learned agents are reacting to when they
 * starve the evening, and the 22:00 step off it is what they are all waiting for. So this
 * is not decoration on a display; it is the signal that produces the second peak.
 */

/** $/kWh at a five-minute step index. */
export function priceAt(step) {
  const hour = (step * 5) / 60;
  if (hour >= 17 && hour < 22) return 0.30;
  if (hour >= 7 && hour < 17) return 0.15;
  return 0.08;
}

export function priceTier(step) {
  const p = priceAt(step);
  return p >= 0.30 ? 'peak' : p >= 0.15 ? 'day' : 'cheap';
}
