# Bus 18

Three ways into one question: what happens to a town's electricity when a few hundred
electric cars all want charging at once, and what does it take to run it properly?

Built for the **2026 IEEE Metaverse Grand Challenge for Simulation-Based Learning**,
Sustainable Smart Cities and Urban Innovation.

---

## Just open it

**https://rifat137710.github.io/Public/**

No install, no login, no account, no headset. It runs on a phone.

| | | |
| --- | --- | --- |
| **The lesson** | [`/`](https://rifat137710.github.io/Public/) | Six short lessons on one live simulation. Four controls and no jargon: pick a controller, pick how many cars, thin wire or thick, and scrub through the day. Ends on what a safety layer around a reinforcement-learning controller actually buys — nearly twice the drivers charged, out of range eight times less often. **Start here.** |
| **The console** | [`/trainer/`](https://rifat137710.github.io/Public/trainer/) | You are the operator. Six stages, four sliders, one day at a time — and a procurement decision at the end, from a table that is telling the truth and still leading you somewhere. |
| **The city** | [`/city/`](https://rifat137710.github.io/Public/city/) | The same feeder in three dimensions. Walk out of the control room and stand under a street light while the voltage at that bus falls. |

All three run the same power flow, on the same feeder, over the same day. There is one
copy of the physics in `scripts/shared/`, and every build re-solves 2304 recorded control
steps against the offline engine on load and prints the disagreement rather than assuming
it away.

---

## Run it on your own machine

You need [Node.js 22 or newer](https://nodejs.org). Then:

```bash
git clone https://github.com/rifat137710/Public.git
cd Public
git checkout claude/hello-vj564a
npm install
npm run dev
```

That prints a local address — open it in a browser. Edits to the source reload
instantly.

To build the production bundle and serve it exactly as the live site does:

```bash
npm run build
npm run preview
```

---

## Check the physics yourself

Every claim the simulator makes is checked against published numbers on every commit.
None of this needs a browser.

```bash
npm test
```

Runs two suites. **Nine physics gates** confirm the feeder reproduces the IEEE 33-bus
Baran–Wu benchmark and the base cases from the underlying research — including
V<sub>min</sub> 0.9131 pu and 202.7 kW of loss on the strong feeder, which are published
values that nothing here was tuned to. **Sixteen stage assertions** confirm the six-stage
script still tells the truth: that the droop rule really is safer than uncoordinated
charging, that plain deep RL really is dominated by it, and that the stage 6 trap really
does win every column it shows while serving nobody.

```bash
npm run calibrate
```

Fits the weak feeder's substation impedance to the published base case, then holds the
result up against voltage sensitivities that were **not** used in the fit. Per-station
P/Q ratios land within 1.5% of the published table and the active-over-reactive
dominance ratio comes out at 1.273 against a published 1.271.

```bash
npm run compare
```

Runs every controller across the same day and prints the comparison table, on the weak
feeder, on the strong feeder, and with the safety layer forced off.

---

## What is real and what is a stand-in

The simulator is honest about its own sources, and the interface shows it.

| Controller | Where its behaviour comes from |
| --- | --- |
| **Uncoordinated** | Computed live. Charge everything at full power on plug-in. |
| **Droop (IEEE 1547)** | Computed live from the standard's volt-watt curve. |
| **You** | Your hands on the sliders. |
| **SAC-Lag**, **SafeSAC** | **Labelled stand-ins.** Trained networks cannot be reconstructed from a table, so these are documented placeholders until the recorded episodes are exported from the research notebook. Anywhere they appear on screen, they are marked. |

The physics is not a stand-in. Move a slider and the number goes into a real
backward/forward sweep power flow on the real benchmark network. It is not an animation
of what would happen — it is computed, live, on the same model the research used.

---

## How it is put together

```
src/sim/        the physics — headless, tested, no DOM
  network.ts        IEEE 33-bus Baran-Wu line and load data
  powerflow.ts      backward/forward sweep solver
  sensitivities.ts  dV/dP and dV/dQ, measured by perturbation each step
  projection.ts     the safety layer, as a Dykstra projection onto the band
  fleet.ts          287 vehicles, arrivals, dwell, state of charge
  profiles.ts       load shape, solar, price, seeded randomness
  live.ts           the stepper, and the episode runner built on it
src/ui/         village canvas, charts, controls
src/content/    the six-stage script
tests/          the gates
```

There is no server and no backend. The expensive computation — training the agents,
running the shared-seed experiments — was done offline in the underlying research. The
browser does one matrix–vector product and one small projection per step.

Everything is deterministic from a seed, so any run in the video can be reproduced
exactly.

---

## Underlying research

*Safe Deep Reinforcement Learning for Vehicle-to-Grid Voltage Support in Weak
Distribution Feeders: A Physics-Aware Approach.* Md. Rifat Rahman and Sad Sami,
supervised by Dr. Md. Forkan Uddin. Department of Electrical and Electronic Engineering,
Bangladesh University of Engineering and Technology, 2026.

This simulator is a separate educational work built for the competition. The research is
cited as prior work, not submitted as the entry.
