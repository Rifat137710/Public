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
npx tsx scripts/world-data.ts > scripts/shared/world.json
```

## Layout

The physics is not in this directory. The network, the solver, the sensitivities and the
fleet accounting live in `scripts/shared/`, which the lesson page in `scripts/learn/`
imports too — one copy, so the two builds cannot drift into disagreeing about what the
town does.

| file | what lives there |
| --- | --- |
| `../shared/grid.js` | network, backward/forward sweep, sensitivities, self-check |
| `../shared/fleet.js` | the fleet and the drivers-served accounting |
| `../shared/control.js` | the four controllers and the safety projection |
| `src/core.js` | ground plan and shared materials; re-exports the shared engine |
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
- **An adaptive quality ladder counts its own stalls.** Re-computing a day at new
  sandbox settings blocks the main thread for up to 190 ms, so the second in which you
  move the fleet slider measures as low frame rate and costs a tier — the ladder
  punishing you for touching the controls. A second containing a known blocking
  recompute is discounted rather than held against the renderer.
- **Anything automatic needs a way to say no.** The ladder dropped on a hitch and had
  no way back and no control, so one slow moment during load left the whole session on
  reduced resolution. That is a poor default for a learner and a fatal one for someone
  recording; hence the PICTURE control, and the pin that takes the pixel cap to 2.
- **Anisotropy is a capability, not a constant.** Board text is read at an angle from
  across the room — the worst case for trilinear filtering. A hardcoded 4 left small
  type soft on hardware that would have done 16 for nothing. Ask
  `renderer.capabilities.getMaxAnisotropy()`.
- **A stage must not tick its own objectives.** Stage 2 asks you to hand the stations
  back to the controller; its `setup` used to call `clearManual()` first, which
  completed the objective before the learner arrived.

## Parity with the website

The city is meant to do the same task as `src/`, not a different one. What that means
concretely, and where it deliberately stops:

| website | city |
| --- | --- |
| Six-stage arc | ported, with objectives that require going somewhere |
| Stage 6 procurement trap | ported, on a terminal by the control room door |
| Pareto map, a dot per finished run | ported, on the room's south wall and as a table |
| Debrief against eight objectives | ported, texts copied verbatim from `src/content/debrief.ts` |
| Weak / strong feeder | ported, unlocked after the arc |
| Speed control | ported, ×1 to ×64 |
| Load scale | ported, but only where it can be truthful — see below |
| Safety-projection toggle | **not** ported; stages 4 and 5 already are that comparison |
| "Compare against" reference runs | **not** a control; all four reference dots are always on the map |

Two of those are refusals rather than omissions.

**The projection toggle** would need the four controllers and the sensitivity model
ported to be truthful, because flipping it means re-deriving what the controller would
have commanded. The comparison it exists to teach — objective L8, what a safety
projection buys — is already the whole of stages 4 and 5: the same agent, with the
network put back in. A second control that could only replay commands recorded under
the opposite setting would teach the wrong thing.

**Load scale** is real, and it lifts the rooftop generation out before scaling, because
a town growing does not put more panels on its roofs. But it is only offered where the
recorded commands survive the change: with all four stations in manual, or with
uncoordinated charging, which pulls whatever the cars can take regardless of voltage.
Droop and the two agents back off as their local voltage falls, so replaying their
commands at another load would show a controller that never existed. Switching to one
of them returns the town to its base size rather than leaving a stale number on screen.

## The fleet, and why it is exported

Scoring a learner's own run needs drivers-served, which is counted over 287 vehicles
that each did or did not reach the charge they came for. That is not derivable from
recorded totals, so the fleet is exported and its accounting ported: connections,
deficit-weighted charge sharing, the 22 kW per-vehicle limit, and the clamp that stops
a manual command asking for more than the cars can physically take.

It is checked the way the solver is. Replaying all eight recorded runs through the port
reproduces the engine's own totals to 4×10⁻⁵ on drivers served and 5×10⁻⁵ on violation
rate, and both figures are printed on the page.

Two things this forced:

- **The export is every step, not every other one.** Scoring at half resolution would
  put an approximate dot on the same chart as exact ones.
- **Fleet values are exported at full precision.** Service is scored by
  `soc >= targetSoc - 1e-6`; a target rounded to four decimals carries fifty times the
  error of the tolerance it is compared against, and one vehicle in 287 landed on the
  wrong side of it.

## The feeder switch, and what it does not show

After the six stages, the town can be rebuilt on the canonical stiff feeder — the same
day, the same fleet, the same controllers, with the substation impedance taken out.
Across the day that is worth a great deal:

| controller | violations weak → stiff | drivers served | line loss |
| --- | --- | --- | --- |
| Droop (IEEE 1547) | 0.0445 → 0.0083 | 162 → 186 | 1116 → 923 kWh |
| SafeSAC | 0.0160 → 0.0000 | 159 → 204 | 947 → 725 kWh |

You can buy safety with control or with copper, and choosing between them is the actual
engineering decision. It is also not a free pass: even on the stiff feeder, uncoordinated
charging still has twenty buses outside the band at the evening peak.

Two things about how this is built:

- **The stiff-grid episodes are run, not replayed.** Droop reacts to its own local
  voltage, so on a stiffer source it issues genuinely different commands. Re-solving the
  weak-grid record against a stiffer source would show a controller that never existed.
  `world.json` therefore carries two sets of episodes, and the self-check verifies all
  1152 recorded steps across both.
- **It cannot demonstrate distribution shift.** The natural thing to want here is to
  watch the shifted agent become reasonable on the grid it was trained for. It does not:
  it charges nobody on either feeder, because it is a labelled stand-in whose refusal is
  written into it rather than learned. The switch shows what the network is worth. It
  will not show shift arising on its own until the trained episodes are exported from
  the notebook, and the stage-6 debrief says so in as many words.

The switch stays locked until the arc is finished, and every stage resets the town to
the weak feeder — a learner who stiffens the source during stage 2 has not solved the
problem the other five stages are about, they have removed it.

That gate is right for a learner and wrong for whoever is presenting the thing, who has
to reach a setting in one click and cannot walk six stages first every time. So the same
escape is offered twice — on the supervisory console in the room, and under the fleet
slider on the page. Neither marks a stage as taught: the arc is still there and still
unwalked, the sandbox is simply no longer behind it.

## Getting around without a mouse

Pointer lock is the nicer way to look around, and it is still the default — but it is
also a hard dependency on a device not everyone has. So the canvas is focusable, and
while it holds focus `←` `→` turn, `↑` `↓` look up and down, `WASD` walks, and `Enter`
and `F` work as they do under lock. Every objective in all six stages is reachable this
way; the keyboard test drives the whole thing with pointer lock never engaged.

`Enter` is what every prompt and every screen names. `E` still opens things too — it is
in every instruction written before this and in the hands of anyone who has already
walked the city — but a first-time visitor standing in front of a thing that says it can
be opened reaches for `Enter`, so `Enter` is what the city asks for.

Alongside that:

- **A text feeder.** Every bus, live, as a table below the controls — the mimic board
  for reading rather than walking.
- **A polite live region** that announces the bus you have arrived at and its voltage,
  on arrival rather than per frame.
- **Focus goes into a panel when it opens** and returns to the view on Escape. An open
  panel whose controls are in use is not rebuilt, because replacing `innerHTML` nine
  times a second destroys focus and interrupts a drag.
- **The annunciator flash is ~0.7 Hz**, well under the WCAG 2.3.1 three-per-second
  threshold, and does not run at all under `prefers-reduced-motion`.

## Cost

Instrument repaints are gated two ways. Each screen carries a signature of the state it
draws and repaints only when that moves; and past 45 m from the control room the whole
redraw is skipped, since the room is enclosed and the screens are behind a wall. Measured
by counting canvas text operations: 216/sec at the desk, 2/sec out at bus 16.

## Verifying it

`scripts/threejs` has no unit tests — it is checked by driving the real page in headless
Chromium: load with zero console errors, confirm the self-check line, walk the six
stages to completion, and read the screenshots. The screenshots matter. The upside-down
world, the culled road, the black windows, the white-out control room and the buried
console screens were all found by looking at an image, not by reading code.
