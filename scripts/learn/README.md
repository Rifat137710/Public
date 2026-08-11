# The lesson

A single page that teaches what a smart grid full of electric cars actually does, and
what a safety layer around a reinforcement-learning controller buys you. Six short
lessons, one live simulation they all drive, and a scoreboard that recomputes on whatever
town the reader builds with the sliders.

Output is `docs/learn.html`, self-contained.

```sh
npm run learn          # build
npm run learn:check    # run every controller through a day under node, print the table
npm run learn:verify   # build, then drive the real page in headless Chromium
```

## What the reader can change

Four things, and no more. The page is for someone who has never heard of a per-unit
voltage:

| control | what it does |
| --- | --- |
| Who decides the charging | the four controllers |
| Electric cars in town | 20 to 287, resampled evenly across the four stations |
| The line into town | thin (weak source) or thick (stiff source) |
| Time of day | scrub, or press Play |

Everything else — the load shape, the tariff, the arrival times, the battery sizes — is
the thesis scenario and is not adjustable, because a reader who can change everything
learns nothing.

## The four controllers

Two are published rules and are exact: uncoordinated charging, and the IEEE 1547-2018
volt-watt droop curve. Two stand for the thesis's learned agents.

What is a stand-in is the **policy** — what the network asks for. Running the trained
actor needs its 95-number observation vector rebuilt, and that lives in the notebook
rather than in its outputs. What is not a stand-in is the **difference between them**:
SafeSAC's safety projection is the real algorithm, solved every step against
sensitivities measured on the live feeder. The thing the page claims to demonstrate is
therefore the thing that is actually computed.

The two policies are shaped by what each agent was trained against, which is the point
the lesson turns on:

- **Plain RL** is paid for cheap energy and learns to wait for the cheap hour. A price
  signal is identical at every station, so what it really learns is to synchronise: it
  starves the evening, then puts the whole fleet on charge the instant the tariff drops
  at 22:00. It builds a second peak of its own making.
- **SafeSAC** trains with the projection already in the loop, so it never had to spend
  capacity avoiding voltage — something else was guaranteeing that. It asks for
  everything and lets the projection decide how much of it is real.

## The result the page is built on

Weak feeder, 200 cars, one day:

| controller | out of range | drivers charged | worst voltage |
| --- | --- | --- | --- |
| No control | 19.38% | 195 / 200 | 0.877 |
| Droop (IEEE 1547) | 6.49% | 60 / 200 | 0.892 |
| Plain RL | 5.00% | 91 / 200 | 0.893 |
| **SafeSAC** | **0.78%** | **115 / 200** | **0.948** |

SafeSAC beats the standard on both counts at once, at every fleet size from 100 cars up,
on both feeders. That is checked in `verify.mjs` rather than asserted here — if a change
ever breaks it, the build fails instead of the page quietly lying.

Uncoordinated charging keeps topping the service column, and the page says so out loud
rather than hiding it. Nothing charges more cars than letting everyone charge; it does it
while a fifth of all street-hours sit outside the legal range. Reading one column without
the other is the specific mistake the whole entry is about.

## Two bugs worth not repeating

**The linearisation offset.** The safe set is built from `v ≈ v0 + S·(u − u0)`, where
`u0` is the command the sensitivities were measured at. Treating `v0` as the *idle*
voltage instead of the voltage at `u0` shrinks the safe set by the entire effect of `u0`,
and SafeSAC curtails roughly twice as hard as it should — it looked timid and served 44
drivers where it should have served 119. Folding the offset in gives
`vIdle = v0 − S·u0`, and everything is written against that.

**What "do not make it worse" is measured against.** When a bus is already out of range
with nothing charging, no command can fix it, so the constraint has to degrade. Degrading
it to "no worse than the current operating point" lets the layer ratchet: each step it
anchors to the low it allowed last step and calls that the new normal. It has to be "no
worse than idle".

Both were found by reading the scoreboard, not the code. The first made SafeSAC look
useless; the second made it look reckless, at 14% violations.

## What was tried and removed

Re-measuring the sensitivities about the projected command and projecting a second time
— textbook successive linearisation. It moves the day's result by 0.01 percentage points
for twice the power flows, so it is not in the code. The residual error is not from the
linearisation point; it is the curvature itself, and it costs SafeSAC about a thousandth
of a volt at the single worst moment of the evening.

## Verifying it

`verify.mjs` drives the built page in headless Chromium: load with zero console errors,
confirm the solver self-check, click all six lessons and confirm each one actually sets
the simulator, assert the central claim at four fleet sizes, play the day, and check the
page does not scroll sideways on a phone. Screenshots are written for every lesson.

The screenshots matter as much as the assertions. The voltage profile used to join bus 18
to bus 19 with a straight line — they are on different laterals and nothing connects
them — which drew a cliff that does not exist. No test would have caught it.
