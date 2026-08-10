# The city

A walkable IEEE 33-bus feeder in Three.js: a control room you work from, a town you
walk out into, and the six-stage arc from the website rebuilt as things you do with
your legs rather than cards you click through.

Build it with one command. Output is `docs/feeder33-city.html`, self-contained.

```sh
npm install three            # r185
node scripts/threejs/build.mjs
```

`src/core.js` imports `world.json`, regenerated from the simulation engine with:

```sh
npx tsx scripts/world-data.ts > scripts/threejs/world.json
```

## Layout

| file | what lives there |
| --- | --- |
| `src/core.js` | network, backward/forward sweep, self-check, ground plan, shared materials |
| `src/city.js` | roads, buildings, poles, conductors, grid hardware, the EV fleet |
| `src/room.js` | the control room and its instruments, all drawn to CanvasTextures |
| `src/mission.js` | the six stages, their objectives and their debriefs |
| `src/main.js` | renderer, interaction, HUD, loop |
| `shell.html` | page chrome and styles; `/*BUNDLE*/` is where the bundle lands |

## What is driven by the solver, and what is not

Everything visible is downstream of one `solveAt()` call per simulated step. Lamps dim
because the voltage at their bus fell (`V^3.4`, the incandescent law). Conductors glow
because that branch is carrying loss. A car charges slowly because the controller told
its station to back off. The mimic board, the trend wall, the annunciator and the four
desk consoles all read the same solution object.

Nothing is animated to look right. If it looks wrong, the number behind it is wrong.

The one thing not solved live is the recorded controller commands — those come from the
offline engine. On load the page re-solves all 576 of them and compares; the result is
printed on the page rather than assumed.

## Notes for anyone picking this up

Things that cost real time to find:

- **Lights are photometric, and 1/d² is brutal.** A street lamp 13 m away needs ~1550
  candela. A ceiling fitting 3 m away needs about a twentieth of that. Reusing the
  street value indoors rendered a pure white room.
- **`setColorAt` writes `instanceColor`, not `vertexColors`.** Setting
  `vertexColors: true` on a material with no such attribute makes the shader read black.
- **`display` on an element beats the UA `[hidden] { display: none }`.** `#enter` is a
  grid, so it needed an explicit `#enter[hidden]` rule or the click-to-enter overlay
  never went away.
- **Frame cost is fragments,** not draw calls or light count. Halving render size
  roughly triples the frame rate; emptying the light pool changes nothing. That is why
  the quality ladder ends in resolution.
- **Only one light casts shadows.** A shadow-casting point light is six render passes.
- **No volumetric cones.** An additively-blended cone reads as a hard silhouette; a
  convincing shaft needs raymarching through the light's falloff.
- **Station power is shared across every vehicle plugged in,** not across the six bays
  drawn under the canopy. Dividing by the bays gave each car 139 kW, a full battery in a
  quarter of a second, and a state-of-charge bar that told you nothing.
- **A stage must not tick its own objectives.** Stage 2 asks you to hand the stations
  back to the controller; its `setup` used to call `clearManual()` first, which
  completed the objective before the learner arrived.

## Verifying it

`scripts/threejs` has no unit tests — it is checked by driving the real page in headless
Chromium: load with zero console errors, confirm the self-check line, walk the six
stages to completion, and read the screenshots. The screenshots matter. The upside-down
world, the culled road, the black windows, the white-out control room and the buried
console screens were all found by looking at an image, not by reading code.
