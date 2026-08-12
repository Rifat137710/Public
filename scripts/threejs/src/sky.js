/**
 * The night the city is held at, and why it never turns into a day.
 *
 * There was a sun here. It was pleasant, it made the rooftop PV visible at the hour it
 * mattered, and it had to go — because the one signal this build exists to teach is
 * carried by the streetlights. A lamp's brightness *is* the voltage at its bus, and the
 * whole point of walking to bus 18 is that you can see it is dimmer than bus 2 without
 * reading a number. Under a midday sky you cannot: the sun floods the same surfaces the
 * lamps light, the difference between 0.95 pu and 0.87 pu falls under the ambient, and
 * the instrument stops being an instrument.
 *
 * So the town is on a permanent night, with one deliberate exception to honesty about
 * darkness: the sky itself keeps a moonlit floor. A feeder end at 0.866 pu genuinely has
 * no working streetlight on it, and rendering that faithfully produced a frame that was
 * entirely black — indistinguishable, on a recording, from a page that failed to load.
 * The fix is not to cheat the lamps brighter. It is to light the sky, because a real
 * street at night with its lights out is still a street you can see the shape of. The
 * lamps stay exactly as dark as the physics says; the world behind them is never nothing.
 *
 * The floor is set where a browned-out street still reads as a street and a healthy one
 * still reads as obviously brighter. Raising it washes the signal out; dropping it brings
 * the black frame back. Both failures have been seen, which is why the number is asserted
 * in `verify.mjs` rather than left to taste.
 */

import * as THREE from 'three';

const SKY = new THREE.Color(0x070a0e);
const FOG = new THREE.Color(0x0a0e13);

const MOON_UP = new THREE.Color(0x3a4c64);
const MOON_DOWN = new THREE.Color(0x0e151d);

/** Hemisphere intensity. The one number that decides whether the town is legible. */
export const MOONLIGHT = 3.3;

/** Thick enough that the far end of the feeder fades, thin enough to see a block ahead. */
export const FOG_DENSITY = 0.0042;

export function buildNight(scene) {
  const hemi = new THREE.HemisphereLight(MOON_UP, MOON_DOWN, MOONLIGHT);
  scene.add(hemi);

  scene.background.copy(SKY);
  scene.fog.color.copy(FOG);
  scene.fog.density = FOG_DENSITY;

  return {
    hemi,
    /** What the night is set to, for the checks and the debug surface. */
    report: () => ({
      hemiIntensity: hemi.intensity,
      background: scene.background.getHexString(),
      fogDensity: scene.fog.density,
    }),
  };
}
