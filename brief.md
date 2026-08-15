# Bus 18 — handover brief

You are picking up a competition entry with hours left on the clock. Read this whole
file before doing anything. It is written to be sufficient on its own.

---

## 1. The clock

**Deadline: 15 August 2026, 23:59 EDT.** At the time this was written it was
**10:36 EDT on 15 August** — roughly **13 hours left**.

**The video does not exist.** It is a mandatory deliverable and it is the only thing
that can still lose the entry outright. Everything else in this brief is secondary to
that. If you find yourself polishing code, stop and ask whether the video is recorded.

---

## 2. What the competition is

- **IEEE Metaverse Grand Challenge for Simulation-Based Learning, 2026.**
- Track: **Sustainable Smart Cities and Urban Innovation**.
- Entrant: **Md. Rifat Rahman**, BUET EEE, **solo**.
- **Judged on two artifacts only: a slide deck and a video.** The live site is not
  judged directly — it is evidence the deck and video point at.
- **Hard caps: 5 slides maximum, video 5–7 minutes, MP4.**

The deck is at `docs/bus18-slides.pptx` (5 slides, at the cap). The video script is a
timed 6:30 cut at `docs/video-script.html`.

---

## 3. What the project is

"Bus 18" teaches one engineering idea by making you live it: **on a weak distribution
feeder, coordinating EV charging is a two-objective problem, and a controller that
looks perfect on a safety report may be achieving that by serving nobody.**

The simulation is an **IEEE 33-bus Baran–Wu radial feeder** at 12.66 kV, deliberately
weakened at the substation. Four charging stations at **buses 18, 22, 25 and 33**.
Rooftop PV at buses 6, 13 and 30. **287 vehicles**, one 24-hour day in **288 five-minute
steps**. Scenario is fixed: `{ grid: 'weak', loadScale: 0.5, seed: 137710 }`.

Physics is a **backward/forward sweep power flow**. Nothing on screen is animated to
look right — every lamp, meter and instrument is downstream of one `solveAt()` call per
step. If it looks wrong, the number behind it is wrong.

### The four controllers

| Controller | Violations | Served /287 | Line loss | Net cost | Worst bus |
|---|---|---|---|---|---|
| Uncoordinated | 0.3186 | 282 | 3398 kWh | $2093 | 0.8459 pu |
| Droop (IEEE 1547) | 0.0445 | 162 | 1116 kWh | $1194 | 0.9364 pu |
| Plain RL | 0.0574 | 76 | 1222 kWh | $770 | 0.8755 pu |
| Shielded RL | 0.0160 | 159 | 947 kWh | $1159 | 0.9471 pu |

Stage 6 adds a fifth, **Plain RL (trained on a stiff feeder)**: violations **0.0020**,
net **−$315** (the only profit), and it serves **0 of 287**. It wins on every column a
procurement table shows, by refusing to operate. That is the trap the entry is built
around.

### NAMING RULE — do not break this

The user asked that their underlying research not be identifiable in the entry.

- The learned controllers are **"Plain RL"** and **"Shielded RL"**. Never "SafeSAC",
  never "SAC-Lag".
- Never write "soft actor-critic", "Lagrangian", "thesis", or "notebook" in anything
  user-facing.
- **Internal ids are unchanged** — `'sac-lag'` and `'safesac'` still identify the
  controllers in `world.json` and the engine. Do not rename those; the numbers depend
  on them.
- A test enforces this: the city suite asserts the rendered page text contains no
  `SafeSAC|SAC-Lag|thesis`.

**Two exposures are still open — see §8.**

---

## 4. Where everything lives

Repo: **`Rifat137710/Public`** (public). Branches **`main`** and
**`claude/hello-vj564a`** are kept identical. HEAD at handover: **`253038f`**.

Push to both. The user has standing permission for `main`. Pushing to any other branch
needs explicit permission.

### Live URLs (GitHub Pages, deploys from `main` on push)

| URL | What |
|---|---|
| `https://rifat137710.github.io/Public/` | The lesson — six-part explanation, all four controllers on one chart |
| `https://rifat137710.github.io/Public/city/` | **The city** — the walkable 3D build. This is the demo. |
| `https://rifat137710.github.io/Public/trainer/` | The operator's console — same six stages, flat screen |
| `https://rifat137710.github.io/Public/pack/` | Tester pack |
| `https://rifat137710.github.io/Public/script/` | The video script |
| `https://rifat137710.github.io/Public/blueprint/` | Technical blueprint |
| `https://rifat137710.github.io/Public/bus18-slides.pptx` | The deck |

### Layout

```
src/                 React 19 + TS 5.7 + Vite 8 site (the lesson and trainer)
  sim/               the engine: network, power flow, sensitivities, projection, fleet
  content/           stages.ts, debrief.ts, evaluation.ts  (was thesis.ts — renamed)
  ui/                ParetoMap, Leaderboard, VoltageProfile
scripts/
  shared/            grid.js, fleet.js, control.js, price.js, world.json
                     ^ ONE copy of the physics, imported by BOTH the city and the lesson
  threejs/           the city: src/{core,city,room,mission,live,debrief,main}.js
                     shell.html is the page chrome; /*BUNDLE*/ is where the bundle lands
  learn/             the lesson page build
  build-slides.js    generates docs/bus18-slides.pptx
  world-data.ts      regenerates scripts/shared/world.json
docs/                build output + hand-written pages + docs/source/ reference material
tests/               physics.test.ts, stages.test.ts
```

`scripts/shared/` is the single source of physics truth. The city and the lesson both
import it so they cannot drift into disagreeing about what the town does.

### Commands

```sh
npm run build          # tsc + lesson + city + vite + assemble → dist/
npm test               # 36 node assertions (physics + stages)
npm run city:verify    # build the city, then 79 browser assertions (headless Chromium)
npm run learn:verify   # build the lesson, then 24 browser assertions
node scripts/verify-site.mjs   # 13 link/route assertions
npx tsc --noEmit       # typecheck
npm run world          # regenerate world.json  (only if the engine changed)
```

**All suites were green at handover: 79 city, 24 lesson, 13 site, 36 node, tsc clean,
zero console errors.** Keep them that way — they are the entry's credibility claim.

`npm run city:verify` takes several minutes. Run it in the background, do not block on it.

---

## 5. The city — how to drive it for the video

Enter at `/Public/city/` and click the view (or focus it and use keys).

| Key | Action |
|---|---|
| ↑ ↓ | Walk forward / back |
| ← → | Step sideways |
| A D | Turn |
| W S | Look up / down |
| Shift | Run |
| Enter | Use what you face |
| F | Acknowledge alarms |
| **Space or /** | **Hold and release the day** — the presenter's pause |
| 1–4 | Select controller |
| [ ] | Speed (0.25× … 64×) |
| , . | Nudge the clock |
| R | Reset the day |
| G | Switch feeder (after unlock) |
| T | Hide the page controls (cockpit mode) |

**Before recording, set `Picture` to `Full quality`** in the control bar. Left on `Auto`
the page drops render resolution to protect frame rate, which softens all the board
text. This is the single most common way to ruin a take.

**To reach the sandbox without walking six stages**, use the button under *Electric cars
in town* ("Demonstrating? Open the sandbox now"), or the same escape on the in-world
supervisory console.

### The control room

Boards, and where they hang:
- **Mimic board** (west wall, 15 m) — the live one-line. Footer row reads
  `PLUGGED IN · CHARGED · LEFT SHORT · DRAWING`.
- **Supervisory console** (north wall) — carries every setting the page has, plus fleet
  size and safety margin. `Go to → Supervisory desk`.
- **Alarm annunciator** and **sequence-of-events log** (south wall).
- **Pareto map** (east stand).
- **Procurement terminal** (by the door) — the stage-6 table.

### The money shot

**19:00 at bus 18.** Run **Uncoordinated** — worst bus **0.8663 pu**, the street lamps
brown out visibly. Then press **4** for Shielded RL and watch them come back. Voltage is
the lamp brightness; that is the whole instrument.

The strongest single fact in the project, if you need one line of narration:
**at 19:00 the town breaks its own voltage band with zero cars charging** (0.9441 pu,
29 of 288 steps out of band). Shielded RL, discharging at buses 18 and 33 while charging
at 22 and 25, holds it at **0.9471 pu** — *better than an empty feeder* — and spends
**24 steps out of band where an empty car park spends 29**.

---

## 6. The day, hour by hour

Everything below is computed from `scripts/shared/world.json` and the four recorded
episodes. A reference page exists at
`https://claude.ai/code/artifact/2e362815-f8de-4973-aeb6-9fa093908fe2`.

**Tariff:** $0.08/kWh 00:00–07:00 and 22:00–24:00 · $0.15 07:00–17:00 ·
**$0.30 peak 17:00–22:00**.

**Town demand:** gross peak **19:00 at 1858 kW**; trough 03:00 at 650 kW; net trough
(after PV) 12:35 at 320 kW.

**Rooftop PV:** first output 06:05, last **18:25**, peak 12:15 at 750 kW.

**Fleet:** first arrival 05:20, last arrival 22:55, last departure 23:55. **Peak plugged
21:15, 147 of 287.** Median dwell 5.2 h. Arrival humps 07:00–09:00 (74 cars) and
17:00–19:00 (101 cars).

**The collision:** the tariff steps up at 17:00, the town's own load peaks at 19:00, the
sun quits at 18:25, and the biggest wave of drivers plugs in behind all three. Nothing
was tuned to make that happen — it is what a commuter town does.

**Controller peaks:** Uncoordinated 3168 kW at 21:00 · Droop 1815 kW at 11:00 ·
Plain RL **exactly 0 kW for 17:00–22:00, then 2587 kW at 22:00** the second the tariff
drops · Shielded RL 1247 kW at 11:00.

**Violations:** Uncoordinated 195/288 (07:45–23:55) · Droop 83/288 (09:45–23:55) ·
Plain RL 33/288, clustered at its self-made 22:00 peak · Shielded RL 24/288, and **all
of them inside 18:20–20:15** — the town's own window, not the fleet's.

---

## 7. The deliverables, honestly

### The video — DOES NOT EXIST. Highest priority.

`docs/video-script.html` is a **timed 6:30 cut**, shot by shot, with a "before you
record" checklist and a table of the exact numbers the build currently produces. Its
numbers were verified against `world.json` at handover and **match exactly**.

The script's own rule, which is good advice: **never narrate a number the screen is not
showing.** A judge watching with a scoring sheet will catch a mismatch, and one mismatch
costs more than any shot gains.

Beats: cold open (lights go out) → the problem → stage 1 you drive and fail → stages 2
and 3, the two corners → stage 4 the credibility beat → stage 5 physics restored →
stage 6 the trap → debrief and energy → evidence → close.

### The deck — 5 slides, at the cap

1. Title / framing.
2. **"A neural network lost to a rule from 1547."** Comparison table + Pareto plane.
   **Its numbers are correct and current** — 0.319/0.983, 0.045/0.564, 0.057/0.265,
   0.016/0.554 all match `world.json`, and the domination claim is asserted by a passing
   test. *(An earlier session wrongly reported this slide as stale. It is not.)*
3. Six stages, "you fail first."
4. "Real physics, in a browser tab" — verification against published Baran–Wu values.
5. What it teaches, and how we know. **Has three blanks** for tester-study results:
   pick-rate, pre/post concept score, and SUS. Needs roughly 8 tester sessions. The
   speaker note says "the blanks are filled from the tester study before submission."

With 13 hours left, **the tester study is very unlikely to happen.** The honest options
are to state N and the numbers you actually have, or to state plainly that the study is
pending. Do not invent them — the entry's whole credibility posture is that every number
is sourced.

---

## 8. Open problems — read before you touch anything

### 8a. The shipped deck still says "SafeSAC" (BLOCKING for the naming rule)

`docs/bus18-slides.pptx` was built on 11 August, **before** the rename. Unzipping it
shows **"SafeSAC" twice** in the slide XML. It is a judged deliverable and it is live at
`/Public/bus18-slides.pptx`.

`scripts/build-slides.js` has been updated with the correct labels, **but it cannot run
as-is**: it opens with `const pptxgen = require('pptxgenjs')` while `package.json` sets
`"type": "module"`, so node refuses it. Also `pptxgenjs` is **not** in `package.json`
dependencies — install it with `npm install --no-save pptxgenjs`.

**Fix:** rename the file to `scripts/build-slides.cjs` (or convert the `require` to an
`import`), install pptxgenjs, run it, then re-verify with:
```sh
cd /tmp && rm -rf pptx && mkdir pptx && cd pptx \
  && unzip -q /home/user/Public/docs/bus18-slides.pptx \
  && grep -roh "SafeSAC\|SAC-Lag" ppt/slides/ | sort | uniq -c
```
Expect no output.

### 8b. The research document is committed to the public repo

**`docs/source/SafeSAC_Final.txt`** is in git, in a public repository. It names the
method in its filename and contains the full text. Deleting it from the working tree
does **not** remove it from history — that needs a rewrite and a force-push.

This is the user's call, and it has real trade-offs. Present the options; do not rewrite
history unprompted:
- Leave it (a judge browsing the repo can find it).
- Delete the file going forward (removes it from the tip, not from history).
- Rewrite history and force-push (removes it properly; destructive, and the repo has a
  deploy workflow keyed on branch pushes).

Other files in `docs/source/` are competition reference material — rules, FAQs, the
kickoff webinar, the competition page — and are useful to keep.

### 8c. Slide 5 cites the prior work by title and authors

Slide 5 carries: *"Prior work: Safe Deep Reinforcement Learning for Vehicle-to-Grid
Voltage Support in Weak Distribution Feeders — Md. Rifat Rahman and Sad Sami, BUET EEE,
2026. Cited as prior work, not submitted as the entry."*

This was left deliberately. Citing your own prior work is normal and proper, and removing
a citation to conceal provenance would be a worse problem than the one it solves —
especially in a competition with originality rules. **Flag it to the user as a decision,
do not silently delete it.** Check `docs/source/2026-official-rules.txt` for what the
rules actually require on prior work before advising.

### 8d. Uncommitted work in the tree at handover

Five files are modified and not yet committed: `docs/blueprint.html`,
`docs/video-script.html`, `docs/tester-pack.html`, `docs/CONTEXT.md` (all four had the
old names and were renamed — these pages are **deployed**, so this was a live leak), and
`scripts/build-slides.js` (label fix). **Rebuild, run the suites, commit and push these.**

### 8e. Lower priority

- `docs/feeder33-3d.html` and `docs/feeder33-walk.html` are earlier builds, not deployed,
  still in the repo.
- The two learned controllers are **reference implementations**, not the trained agents.
  They are marked as such everywhere they appear ("reference implementation — figures
  provisional"). **Keep that marking.** Removing it would present provisional figures as
  measured ones.

---

## 9. How the user wants to be worked with

Direct instructions from earlier sessions, still in force:

- *"In this competition, you will be totally guiding me, so look twice before you leap.
  Don't provide me anything without double checking."* — **Verify before asserting.**
  Compute numbers from the repo rather than recalling them.
- *"Do not overcomplicate the backend thing."*
- *"Don't change the main work algorithm of the task."* The physics, the controllers and
  the six-stage arc are settled. Do not redesign them.
- *"The user interface will be an easy interface with understandable parameters."*
- Prose should be **formal and spare**. The user explicitly objected to copy that
  "looks like an AI generated thing" — cut chatty asides, em-dash pile-ups, and headings
  with dashes in them. Tables beat paragraphs for reference material.
- Do **not** open pull requests unless asked.
- Report failures with the actual output. If something is skipped, say so.

### A caution from this session

I twice told the user slide 2 was stale and inverted. **It was not** — I had carried the
claim forward without re-checking it against `world.json`. It cost their trust and could
have cost them an hour of pointless rework. Check the artifact, not your memory of it.

---

## 10. What actually changed most recently

Commit `253038f`, "Rename the learned controllers, rebuild the procurement board, walk
on the arrows":

- Renamed the controllers everywhere; regenerating `world.json` changed **exactly ten
  strings and no figure**.
- **Procurement board rebuilt.** It was a 418×285 canvas carrying type sized for twice
  that: headings overlapped by 40 px, row names ran through their own figures, the
  footnote was drawn above the last row's baseline. Now 924×630 with columns measured
  from the drawing context. Two latent bugs fixed at the same time: the board drew
  `WORLD.runs` while its own panel and the stage-6 debrief drew the candidate shortlist,
  so the **trap candidate was missing from the board** and `picked` highlighted the wrong
  row.
- **`LEFT SHORT`** added to the mimic footer — vehicles that plugged in and drove away
  below the charge they came for. Counts departures only.
- **Walking moved to the arrow keys**, turning and looking to WASD. Neither axis had a
  test before; both do now.
- Earlier commit `efbb950` added the **Picture (Auto / Full quality)** control after the
  quality ladder was found to have no way back and to be **counting its own blocking
  recomputes as dropped frames** — so using the sandbox cost you resolution.

The two columns on the procurement board stay two columns. Drivers served is exactly the
column that would expose the trap, and its absence is what stage 6 teaches.

---

## 11. Environment notes

- Working directory `/home/user/Public`. Node 22.
- Chromium for Playwright: `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
  Import as `import playwright from '/home/user/Public/node_modules/playwright-core/index.js'`
  — it is CommonJS, so named imports fail.
- Scripts that import `scripts/shared/*.js` need **esbuild bundling** to run under node
  (world.json import attribute). Such scripts must live in the **repo root** — the
  scratchpad cannot resolve `esbuild`.
- The sandbox proxy blocks `rifat137710.github.io` and `api.github.com` from plain
  node/curl. Use the GitHub MCP tools; slice large results with python.
- Deploy: `.github/workflows/deploy.yml`, concurrency `pages-${{ github.ref }}`, deploy
  job gated to `main`. Build ~25 s, deploy ~60–90 s.
