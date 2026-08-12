/**
 * The sun, and what the town looks like under it.
 *
 * The city used to be lit by one hemisphere light and nothing else, which meant it was
 * midnight at every hour of a twenty-four hour day. Noon looked like 23:00, the rooftop
 * PV was invisible at the moment it mattered, and the evening peak — the thing the whole
 * build exists to show — arrived as dark giving way to slightly darker.
 *
 * The sun here is not decoration and it is not a separate assumption. Sunrise and sunset
 * are read off the exported solar series: the first and last five-minute step where the
 * arrays produce anything. So the sun in the sky and the generation on the roofs are the
 * same data, and a viewer who notices the light going amber at six is watching the same
 * event that empties the PV column.
 *
 * There are no sun shadows. A directional shadow map wide enough to cover half a
 * kilometre of feeder is either enormous or useless, the point light following the
 * camera already grounds the near geometry, and diffuse shading alone is what separates
 * a lit box from a flat one. That is the whole win; the rest is cost.
 */

import * as THREE from 'three';
import { WORLD } from './core.js';

/* ------------------------------------------------------------------ palette */

const NIGHT_SKY = new THREE.Color(0x070a0e);
const DUSK_SKY = new THREE.Color(0x53321f);
const DAY_SKY = new THREE.Color(0x7ea6c9);

const NIGHT_HEMI_UP = new THREE.Color(0x3a4c64);
const NIGHT_HEMI_DOWN = new THREE.Color(0x0e151d);
const DAY_HEMI_UP = new THREE.Color(0xa8cdee);
const DAY_HEMI_DOWN = new THREE.Color(0x424a54);

const SUN_LOW = new THREE.Color(0xffa860);
const SUN_HIGH = new THREE.Color(0xfff2dc);

/**
 * Moonlight, and the reason it exists.
 *
 * A feeder end at 0.866 pu genuinely has no working streetlight on it, and rendering
 * that honestly produced a frame that was entirely black — indistinguishable, to anyone
 * watching a recording, from a page that had failed to load. The fix is not to cheat the
 * lamps brighter. It is to light the sky: a real street at night with the lights out is
 * still a street you can see the shape of. The lamps stay exactly as dark as the physics
 * says; the world behind them stops being nothing.
 */
const NIGHT_FLOOR = 3.3;
const DAY_CEILING = 5.0;

/* -------------------------------------------------------------- the day itself */

/** First and last step with any PV output, as hours. The sun is defined to match. */
const SOLAR_HOURS = (() => {
  const lit = WORLD.day.filter((f) => (f.solar ?? 0) > 0);
  const hourOf = (f) => (f.t * 24) / WORLD.day.length;
  return lit.length
    ? { rise: hourOf(lit[0]), set: hourOf(lit[lit.length - 1]) }
    : { rise: 6, set: 18 };
})();

const smoothstep = (edge0, edge1, x) => {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
};

/**
 * Sun elevation as a number in [-1, 1], where 0 is the horizon and 1 is local noon.
 * Below the horizon it keeps going negative, which is what drives the twilight ramp.
 */
export function elevationAt(step) {
  const hour = (step * 24) / WORLD.day.length;
  const span = SOLAR_HOURS.set - SOLAR_HOURS.rise;
  return Math.sin(((hour - SOLAR_HOURS.rise) / span) * Math.PI);
}

export function buildSky(scene) {
  const hemi = new THREE.HemisphereLight(NIGHT_HEMI_UP, NIGHT_HEMI_DOWN, NIGHT_FLOOR);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(SUN_HIGH, 0);
  sun.position.set(300, 200, -180);
  scene.add(sun);
  scene.add(sun.target);

  const sky = new THREE.Color();
  const fog = new THREE.Color();

  /** Paint the sky for a given five-minute step of the day. */
  function apply(step) {
    const elev = elevationAt(step);

    // Two overlapping ramps: night gives way to dusk as the sun approaches the horizon,
    // and dusk gives way to full daylight once it is properly up. Sunrise and sunset get
    // the warm band for free, in both directions, without being special-cased.
    const twilight = smoothstep(-0.22, 0.10, elev);
    const daylight = smoothstep(0.04, 0.46, elev);

    sky.copy(NIGHT_SKY).lerp(DUSK_SKY, twilight).lerp(DAY_SKY, daylight);
    scene.background.copy(sky);

    // Fog takes the sky's colour so the horizon dissolves into it rather than ending in
    // a visible seam, and thins in daylight — a clear noon should see down the feeder.
    fog.copy(sky).multiplyScalar(0.82);
    scene.fog.color.copy(fog);
    scene.fog.density = 0.0042 - 0.0020 * daylight;

    hemi.color.copy(NIGHT_HEMI_UP).lerp(DAY_HEMI_UP, daylight);
    hemi.groundColor.copy(NIGHT_HEMI_DOWN).lerp(DAY_HEMI_DOWN, daylight);
    hemi.intensity = NIGHT_FLOOR + (DAY_CEILING - NIGHT_FLOOR) * daylight;

    // Below the horizon the sun is switched off rather than dimmed, so it can never
    // light the underside of the town from beneath it.
    const up = Math.max(0, elev);
    sun.intensity = 5.2 * daylight;
    sun.color.copy(SUN_LOW).lerp(SUN_HIGH, smoothstep(0.05, 0.55, elev));

    // Rises over the far end of the feeder and sets behind the control room, which is
    // the direction a learner walks all day.
    const along = Math.cos(((step * 24) / WORLD.day.length - SOLAR_HOURS.rise)
      / (SOLAR_HOURS.set - SOLAR_HOURS.rise) * Math.PI);
    sun.position.set(240 + along * 430, 40 + up * 320, -210);

    return { elev, daylight, twilight };
  }

  return { apply, sun, hemi, solarHours: SOLAR_HOURS };
}
