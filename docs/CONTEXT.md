# Project context — persistent memory

Durable record for the 2026 IEEE Metaverse Grand Challenge entry. Committed to git so it survives
session loss and context compaction. **This file is the source of truth. Read it first after any
compaction.** Update it; do not let it go stale.

Last updated: 8 August 2026 (post-design, pre-build).

---

## 0. Where we are right now

**Decision made and final:** build **Bus 18**, a browser-based weak-feeder operator trainer that
teaches what the user's SafeSAC thesis discovered. The thesis is *underlying research*, not the entry.

**Built so far:** a TypeScript simulation engine + validation harness (generic microgrid version,
9/9 assertions passing) and a notebook exporter. **Next step:** repoint the engine onto the IEEE
33-bus feeder and build the visual system. Nothing of the visual system exists yet.

**Immediately next action:** build engine + village against public 33-bus benchmark data. The user
was last asked whether to start with the engine or mock the screen layout first — awaiting that answer.

---

## 1. The competition

**2026 IEEE Metaverse Grand Challenge for Simulation-Based Learning**
Track entered: **Sustainable Smart Cities and Urban Innovation** (theme 2 of 3).

| Fact | Value |
| --- | --- |
| Entry period | 15 Feb 2026 08:00 EDT → **15 Aug 2026 23:59 EDT** |
| Winners announced | 14 Sept 2026 |
| Team | 1–5 people; **user is solo** (confirmed); members lock at submission |
| Entries per team | Exactly one, one declared theme |
| Deliverable 1 | PowerPoint, **hard cap 5 slides**, no appendix allowance |
| Deliverable 2 | Video, **5–7 min, MP4** |
| Judged on | Slides + video **only**. No live demo. Judges never run the build. |
| Submission portal | `https://app.smartsheet.com/b/form/019e6b3c328078b2b90678fc9c56342c` |
| Competition page | `https://metaversereality.ieee.org/competition/` |
| 2026 rules PDF | `https://metaversereality.ieee.org/wp-content/uploads/2026/04/IEEE-FD-and-YP-2026-Metaverse-Grand-Challenge-for-Simulation-Based-Learning-Final-R2.pdf` |
| General contact | `metaversechallenge@ieee.org` |
| Chair / office hours | `polatgoktas@ieee.org` (Polat Goktas) |
| Prizes (theme 2 eligible) | US$2,500 travel ×2 · backpack+certificate ×2 · **US$1,000 cash, Smart Cities only** |
| ISEMV 2026 | 22–24 Oct 2026, UCLan Cyprus + hybrid |

### Judging weights (confirmed in four independent documents)

| Criterion | Weight |
| --- | --- |
| Effectiveness of Simulation-Based Learning | 25% |
| Creativity & Innovation | 20% |
| Educational Impact / Learning Effectiveness | 20% |
| User Experience (UI/UX) & Engagement | 15% |
| Integration of AI, Gamification, Adaptive Learning | 10% |
| Sustainability, Accessibility, Ethical Considerations | 10% |

**65% of the score is pedagogy.** Only 25% rewards technology (UX + AI/gamification).

### Organisers' prescribed slide structure

1. Introduce the idea — challenge and solution
2. System design and user interaction
3. Gamification and learning outcomes
4. **Map your work explicitly to the evaluation criteria**
5. Impact, scalability, platform access + demo/repo links (**must open without login**)

### Rules facts that shaped decisions

- **FAQ 9 (decisive for tech choice):** *"simulations can be developed in 2D or 3D environments and may
  run on desktop, web, mobile, or immersive platforms (e.g. VR/AR). The key evaluation focus is on the
  interactivity, innovation, and learning effectiveness, not the platform."*
- **FAQ 12:** evaluation is entirely on slides + video; judges have no access to live demos.
- **FAQ 13:** a visual walkthrough or concept video is acceptable if it convincingly shows function.
- **Originality:** FAQ 8 — *"must be original, not previously published or submitted elsewhere."*
  Warranty clause — *"sole original work, has not been previously published, released or distributed."*
- Licence grant covers name, likeness and **voice**, perpetual and worldwide.
- Not open to individuals/teams subject to export control regulations.

### Traps in the supplied packet

- Three packet files still show the **2025** deadline (1 Sept 2025). Stale. Correct: 15 Aug 2026.
- Slide 39 of the 2026 kick-off deck has a QR labelled "Submit Your Project" that decodes to the
  **Google expression-of-interest form**, not the portal. Slides 38 and 45 are correct.
- The expression-of-interest form is **optional and is not an entry**.

### 2025 winning field — the bar

131 expressions of interest, 24 countries, four awards. All four winners built **VR training
simulations replacing an expensive or risky physical activity**. None built a general metaverse world.

| Team | Project | Note |
| --- | --- | --- |
| InscapeXR (IIT Kharagpur) — 1st | VR STEM experiments | AI tutor, haptics, gamified |
| Innov8 (Nigeria) — 1st | SkillForge-VR, voice-first VR TVET trainer | Multilingual; claimed 40% faster acquisition |
| N-Tail Lab (Cal Poly Pomona) — 2nd | BroncoVerse, VR digital-logic lab | Logged time/errors/hints to a database |
| MedXperience — 2nd | VR IV-insertion nursing trainer | **n=9 study**: cognitive load 12→7.2, SUS 80.28 |

**A 9-person study placed second.** Almost nobody brings numbers at all.

---

## 2. The thesis (user's own prior work)

**"Safe Deep Reinforcement Learning for Vehicle-to-Grid Voltage Support in Weak Distribution Feeders:
A Physics-Aware Approach"**

- Authors: **Md. Rifat Rahman (202006137)** — the user — and **Sad Sami (202006150)**
- Supervisor: Dr. Md. Forkan Uddin, Professor
- Institution: Dept. of EEE, **BUET**, Dhaka. Course EEE 400. **Accepted/certified June 2026.**
- Files supplied: `SafeSAC_Final.pdf` (64 pp), `Abstract.pdf`, `thesis11.ipynb` (39 cells, ~286k chars),
  `thesisbookartifacts21.ipynb` (12 cells)
- User states he did all the work and enters solo. The PDF carries two names plus supervisor
  certification, so cite the thesis as published when referencing it.

### Method

Bidirectional EV charging as a **constrained Markov decision process** over a 288-step day on a modified
**IEEE 33-bus Baran–Wu** feeder. **SafeSAC** = augmented-Lagrangian Soft Actor-Critic + a safety
projection solving an **8-variable SOCP every control step**, rebuilt each step from **voltage
sensitivities measured on the live network**.

### The physics (this is the teachable core)

```
ΔV ≈ (R·ΔP + X·ΔQ) / V₀
```

- Transmission (strong): X ≫ R → **reactive** power drives voltage
- Weak distribution feeder: R ≈ X → **active** power drives voltage — what an EV charger commands
- Measured: `mean|∂V/∂P| / |∂V/∂Q| = **1.271**` (thesis Gate 1)

This inverts the intuition anyone trained on transmission carries.

### Headline results — Table 6.1 (25 shared-seed episodes/method, load scale 0.50)

| Method | Viol. rate | Vmin (pu) | SoC met | Net cost | Reward | V2G util. |
| --- | --- | --- | --- | --- | --- | --- |
| Uncoordinated | 0.116 ± 0.009 | 0.9383 | 0.996 ± 0.012 | $230.7 | −205.6 | 0.000 |
| Droop (IEEE 1547) | 0.052 ± 0.009 | 0.9474 | 0.325 ± 0.113 | $66.3 | −733.2 | 0.097 |
| SAC-Lag (weak) | 0.090 ± 0.024 | 0.9425 | 0.277 ± 0.117 | $104.3 | −923.5 | 0.176 |
| **SafeSAC (weak)** | **0.091 ± 0.002** | 0.9438 | **0.569 ± 0.164** | $125.9 | −505.2 | 0.103 |
| SAC-Lag (strong→weak) | 0.015 ± 0.014 | 0.9492 | **0.000 ± 0.000** | −$38.2 | −1898.7 | 0.105 |
| SafeSAC (strong→weak) | 0.106 ± 0.003 | 0.9438 | 0.447 ± 0.074 | $69.7 | −1024.1 | 0.048 |

### Paired statistics, SafeSAC vs SAC-Lag (n = 25)

| Comparison | Metric | Δ | 95% CI | p (t) | p (Wilcoxon) | Cohen's d |
| --- | --- | --- | --- | --- | --- | --- |
| In-distribution | Violation rate | +0.0008 | [−0.008, 0.011] | 0.86 | 0.58 | 0.06 |
| | SoC met | **+0.292** | [0.232, 0.352] | 2.2e−9 | 6.0e−8 | **2.04** |
| | Net cost | +$21.6 | [9.5, 34.0] | 0.0019 | 0.0025 | 0.89 |
| Cross-deploy | Violation rate | +0.0907 | [0.085, 0.096] | 4.1e−21 | 1.2e−5 | 10.6 |
| | SoC met | +0.447 | [0.417, 0.477] | 1.9e−20 | 1.2e−5 | 11.9 |
| | Net cost | +$107.8 | [101.3, 113.9] | 1.7e−21 | 6.0e−8 | 9.41 |

### Projection grid-awareness — Table 5.3, identical −80 kW V2G request

| Station | Raw | Safe (weak) | Safe (strong) | Curtailment |
| --- | --- | --- | --- | --- |
| 1 (Baran–Wu bus 18, most sensitive) | −80.0 | **−54.13** | −80.00 | 25.87 kW |
| 2 | −80.0 | −77.95 | −80.00 | 2.05 kW |
| 3 | −80.0 | −76.85 | −80.00 | 3.15 kW |
| 4 | −80.0 | −73.30 | −80.00 | 6.70 kW |

### Pre-registered decision gates — 3/5 pass (disclosed honestly in the thesis)

1. V–P dominance ≥ 0.90 → 1.271 **PASS**
2. Projection grid-awareness > 1 kW → **FAIL** — artefact of a conservative feasibility guard; the weak
   grid was infeasible while the strong grid allowed full −80 kW, an 80 kW divergence, which is
   *stronger* evidence than the gate sought
3. In-distribution safety ratio ≤ 1.05 → 1.009 **PASS**
4. Cross-deployment safety → **FAIL** — SAC-Lag "wins" only by not operating (SoC met 0.000)
5. Service quality ≥ −0.10 → +0.292 **PASS**

### Stack and reproducibility

Python 3.12, PyTorch 2.10 (CUDA 12.8), Tesla T4, pandapower 3.2.0, CVXPY 1.5.3 + CLARABEL, Gymnasium.
Master seed **137710**. Disjoint train/eval seed bands. SHA-256-fingerprinted checkpoints.
Key notebook globals: `EVChargingFeederEnv`, `SensitivityProjector`, `GridSensitivities`,
`compute_voltage_sensitivities`, `SACLagAgent`, `SafeSACLagAgent`, `DroopAgent`, `UncoordinatedAgent`,
`Scenario`, `NetworkContext`, `build_network`, `evaluate_agent`.
Constants: `EV_MAX_CHARGE_KW = 22.0`, `EV_MAX_DISCHARGE_KW = 22.0`, `EV_SOC_FLOOR_DISCHARGE = 0.20`,
`LINEAR_DEGRADATION_COST_PER_KWH = 0.04`, TOU 0.08/0.15/0.30 $/kWh, `N_BUS_CANONICAL = 34`.

### Stated limitations (thesis §6.11)

Single training seed per configuration · parametric (not measured) load model · structural 9–12%
violation floor at load scale 0.50 · linearised safety model, fixed 0.010 pu margin · **simulation only,
no field validation**.

---

## 3. Why the thesis is the foundation and not the entry

Submitting the thesis itself would score ~30/100 and carries a real disqualification risk:

1. **Wrong sense of "simulation."** The thesis uses simulation as a *training environment for an RL
   agent*. The competition means an environment *a human learns inside*. No human learner exists in the
   thesis. This fails the 25% criterion definitionally.
2. **No user experience** → 15% near zero.
3. **No gamification / adaptive learning for a person** → most of the 10% AI criterion lost.
4. **Prior submission.** Certified for a B.Sc. at BUET, June 2026. FAQ 8 and the warranty clause both
   bar previously submitted work.

**Resolution:** the submitted artefact is a **new educational simulator built for this competition**.
The thesis is disclosed as underlying prior research and cited as published — normal practice.

**Open action:** email `metaversechallenge@ieee.org` disclosing the provenance and asking for
confirmation. Not yet done.

---

## 4. THE DESIGN — "Bus 18"

Named for Baran–Wu **bus 18**, the feeder-end station where the physics bites hardest — the one the
projection curtails from −80 kW to −54.13 kW.

### 4.1 The corrected narrative (intellectual core — do not lose this)

"RL is good for smart grids" is the weak pitch *and* not what the data says. The real story:

| | Violations | SoC met |
| --- | --- | --- |
| Droop (IEEE 1547, a fixed rule) | 0.052 | 0.325 |
| **SAC-Lag (plain deep RL)** | **0.090** | **0.277** |

**Plain deep RL is strictly dominated by a 1970s droop rule** — more violations *and* less service.
Then SafeSAC: same backbone, same budget, plus the physics projection → service 0.277 → 0.569 at
statistically identical safety (p = 0.86).

**The win is not RL. It is RL with the physics put back in.**

Showing that the obvious application of deep RL *fails* is what earns the right to the next stage.
This is more surprising, more honest, and more defensible than a chart where the author's method wins.

### 4.2 The visual system — three registers on one screen

Design principle: a learner must **feel** a consequence, **measure** it, then **locate** it in a space
of choices. One screen, no navigation — also far easier to film.

| Register | What it is | Job | Criterion |
| --- | --- | --- | --- |
| **1 · The Village** | Isometric 2.5D rural feeder — poles, houses, 4 EV stations, rooftop PV. **Voltage rendered as light**: houses at the feeder end dim, flicker, go dark. Canvas 2D, simple shapes and glow. | Feel it | UX & engagement 15% |
| **2 · The Console** | **|V| vs bus index with the 0.95 pu limit in red** (thesis Fig. 5.2, live). SafeSAC ghost trace on the same axes. Four station sliders (−80…+80 kW), projection toggle, weak/strong toggle, scorecard. | Measure it | Simulation effectiveness 25% |
| **3 · The Map** | The safety–service plane (violation rate vs SoC met). **Every attempt leaves a permanent dot, the learner's own first.** Becomes thesis Fig. 6.6, built by the learner. | Locate it | Educational impact 20% |

**Why voltage-as-light:** 0.96 → 0.94 means nothing to most viewers; a street going dark means
something to everyone. The village carries stakes so the console can carry precision.

### 4.3 The six-stage learning arc

1. **You drive.** Manual dispatch of 4 stations across a 288-step day. The learner fails one way or the
   other. **Their dot lands on the Map before they see any controller** — you cannot be impressed by a
   solution to a problem you have not felt. This ordering is load-bearing.
2. **Uncoordinated.** Everyone charges on plug-in. 0.996 service, 0.116 violations, village goes dark
   at the evening peak. Service without safety.
3. **Droop (IEEE 1547).** 0.052 violations, 0.325 service. Lights stay on, cars stay empty.
   Safety without service.
4. **Plain deep RL loses.** SAC-Lag: 0.090 / 0.277 — dominated by the rule. The credibility beat.
5. **Physics fixes it.** SafeSAC: 0.569 service at 0.091 violations. **The learner can toggle the
   projection off and watch the same agent fall back to the dominated point. That toggle is the thesis.**
6. **The trap.** Strong→weak SAC-Lag: violation 0.015 (best), cost −$38 (profitable), **SoC met 0.000**.
   Nearly everyone picks it when shown only safety and cost. A constraint satisfied by refusing to
   operate is not safety.

### 4.4 Runtime architecture — deliberately tiny

The thesis already ran every expensive computation. Only two things run live in the browser:

```
v = v₀ + Sᴾ·u        ← one matrix–vector product, ~5 lines
```

plus **playback of recorded episodes** (array reads). No server, no solver, no Python in the demo path
— which is also why the demo cannot break mid-recording.

**The projection, if implemented live:** because the voltage model is linear in `u`, the feasible set
`{u : 0.95 ≤ v₀ + S·u ≤ 1.05, u_min ≤ u ≤ u_max}` is a polytope, so the SOCP becomes a projection onto
it. 4 variables, ~70 constraints → **Dykstra's alternating projection, sub-millisecond in TypeScript**.
Same constraints, same 0.010 pu margin. Verify it reproduces −54.13 kW at station 1 before trusting it.

**De-risk:** the IEEE 33-bus Baran–Wu line data is a **published standard benchmark**, so sensitivity
matrices can be computed from public R/X data if the notebook export stalls. The user's export makes the
numbers *his*, which is better — but it is an improvement, not a dependency.

### 4.5 Tech stack — decided

**React + TypeScript + Vite. Canvas 2D for the village, SVG for charts, no chart libraries.**
Deploy to GitHub Pages from the user's own repo.

- Settled by FAQ 9 (platform explicitly does not affect score) and the slide-5 requirement for a link
  that opens without login.
- **Streamlit** = viable alternative only if the user wants to own/extend it in Python afterwards;
  every interaction round-trips to a server and that lag is what the 15% UX criterion measures.
- **Unity / Unreal / WebXR = rejected.** Weeks of engine learning, zero pedagogical gain, and a headset
  requirement would actively hurt the accessibility criterion. The 2025 winners used VR because their
  subject was physical procedure training; this one is not.

---

## 5. Pipeline and ownership

**Data → Engine → Village → Console + Map → Six stages → Deploy → Evidence → Deliverables → Submit**

| Stage | Output | Who |
| --- | --- | --- |
| 1 · Data | Sensitivities, topology, baseline profiles, 6 recorded episodes | User runs exporter; public-benchmark fallback exists |
| 2 · Engine | `v = v₀ + S·u`, projection, playback, scoring — headless, testable | Claude |
| 3 · Village | Isometric canvas scene, voltage-as-light | Claude |
| 4 · Console + Map | Voltage profile with ghost, sliders, toggles, scorecard, accumulating scatter | Claude |
| 5 · Six stages | Guided arc, reveals, debrief, accessibility pass | Claude |
| 6 · Deploy | GitHub Pages URL, no login | Claude configures |
| 7 · Evidence | 8–10 testers: concept pre/post, SUS, **Stage-6 pick rate** | User runs; Claude writes instruments + analyses |
| 8 · Deliverables | 5 slides, 6:30 video | Claude writes content/script; user records |
| 9 · Submit | Smartsheet portal | User |

### The one measurement worth designing for

Record **how many testers pick the collapsed controller** when shown only safety and cost columns.
If 7 of 9 engineers choose the AI that serves nobody, that single number beats any pre/post delta — it
demonstrates the misconception exists in exactly the population being taught.

### User study instruments (five concept questions, asked before and after)

1. When a microgrid/feeder is stressed, what happens to bus voltage — and which power quantity drives it?
2. On a weak feeder with R ≈ X, does active or reactive power dominate voltage? Why?
3. A deep-RL controller reports the lowest violation rate of any method. What must you check before
   trusting it?
4. Name two reasons a distribution operator might curtail a V2G discharge request.
5. Why can a controller trained on a strong grid fail when deployed on a weak one?

Score 0–2 each (0–10 total). Also capture **SUS** (10 items, free, >68 above average; MedXperience
reported 80.28) and one open question: *"What surprised you?"*

### Video shot list (6:30 target)

| Time | Shot |
| --- | --- |
| 0:00–0:30 | Cold open: −80 kW at bus 18, projection off, voltage profile drops through the red line, village goes dark. Title. |
| 0:30–1:10 | The problem: mass EV charging on weak rural feeders. Theme + benchmark named. |
| 1:10–2:20 | Stage 1–3: you drive and fail; uncoordinated; droop. Dots accumulate on the Map. |
| 2:20–3:30 | Stage 4: plain deep RL loses to the 1970s rule. The credibility beat. |
| 3:30–4:30 | Stage 5: projection on. 0.277 → 0.569 at the same safety. Toggle it off and back. |
| 4:30–5:30 | Stage 6: the leaderboard, the pick, SoC met 0.000, the replay. |
| 5:30–6:15 | Evidence: n, pre/post, SUS, and the pick rate. |
| 6:15–6:30 | Close: browser, no headset. Link held long enough to read. |

---

## 6. Build state

Repo `rifat137710/Public`, branch **`claude/hello-vj564a`** (all work pushed).

```
docs/CONTEXT.md                     this file
package.json  tsconfig.json         Node 22, TypeScript 5.7, tsx; `npm run sim`
src/sim/types.ts                    units, load/asset specs, SimState, telemetry
src/sim/scenario.ts                 profiles, seeded PRNG (mulberry32), default scenario
src/sim/engine.ts                   swing-equation engine, UFLS, scoring
scripts/headless.ts                 4-strategy validation harness, 9/9 assertions pass
scripts/export_evaluation_artifacts.py  notebook exporter + probe() introspection helper
```

**Note:** `src/sim/*` is currently the *generic microgrid* model (swing equation, frequency, diesel
genset, grid-forming vs grid-following inverters). It was built before the thesis arrived. It must be
**repointed** onto the 33-bus linearised voltage model. The clock, scoring skeleton, seeded determinism
and headless harness pattern all carry over; the physics module is replaced.

Finding from that engine worth keeping: battery *reserve* did not decide island survival (a 25-min
island needs only ~250 kWh) — **control mode** did. An assertion was rewritten to match the model rather
than retuning the scenario to protect the assumption.

### Exporter contract (`scripts/export_evaluation_artifacts.py`)

Run `probe()` in the notebook **first** — it reports which expected globals exist so naming mismatches
are fixed in one place. Then `export_all(...)`. Produces:

| File | Contents | Priority |
| --- | --- | --- |
| `sensitivities.json` | Sᴾ, Sᴼ (33×4), both grids, V–P dominance ratio | **Blocking — no physics without it** |
| `topology.json` | 33 buses, line R/X, station and PV bus indices | High |
| `baseline.json` | v₀ per step ×288, load/PV/price series | High |
| `episodes/*.json` | Per-step actions and voltages, all six controllers | High |
| `projection_probe.json` | Identical −80 kW request, both grids | Medium (values known) |
| `results.json` | Table 6.1 aggregates | Already transcribed |
| `*_actor.json` | Actor MLP weights + normaliser stats | Stretch — enables live policy |

### Published artifacts (same URLs on redeploy)

- Competition dossier — `https://claude.ai/code/artifact/eb405721-ed3e-493c-81b6-0858d7331a38`
- Visual system & pipeline — `https://claude.ai/code/artifact/53203c55-7c4f-4e76-ad22-1dc1ad185110`

---

### Settled on 8 Aug: platform, judging, and how the entry is actually seen

Checked against `docs/source/` because the "is a 2D browser app really a *metaverse* entry?" question
came up. It is settled, verbatim:

- **Kick-off FAQ 9** — *"Can our project be a mobile or web-based simulation, or does it have to be
  VR/AR? Yes, simulations can be developed in 2D or 3D environments and may run on desktop, web,
  mobile, or immersive platforms (e.g., VR/AR). The key evaluation focus is on the interactivity,
  innovation, and learning effectiveness, **not the platform**."* A 2D browser entry is explicitly in
  scope. Do not re-litigate this.
- **Judging criteria (official rules)** — sums to 100%, and **none of it scores 3D, immersion,
  avatars, or platform**: Effectiveness of Simulation-Based Learning **25%**; Creativity &
  Innovation **20%**; Educational Impact / Learning Effectiveness **20%**; UI/UX and Engagement
  **15%**; Integration of AI, Gamification and/or Adaptive Learning **10%**; Sustainability,
  Accessibility, and/or Ethical Considerations **10%**.
- **FAQ 12 — the one that reorders priorities.** *"Evaluation is based **entirely on the PowerPoint
  and video submission**. Make sure your video clearly showcases features, interactions, and value,
  **as the judges will not have access to live demos**."* Judges never click the URL. The deployed app
  is the thing being *filmed*, not the thing being judged. The video and the five slides are the
  actual deliverable.
- **FAQ 13** — source code and platform links still go *into the PowerPoint*, so the public URL is
  still required; it just is not the evaluation surface.
- Video length per the rules is **5–7 minutes**; the 6:30 target is in range.

### Track fit — checked against the three sub-bullets on 8 Aug

The rules say *"Each team must select **one** of the following **themes**"*, and every sub-bullet is
joined by "and/or". The bullets are illustrative scope for the theme, **not a checklist to satisfy**.
Against *Sustainable Smart Cities and Urban Innovation*:

- **"virtual laboratories and/or eco-friendly innovations"** — strong fit as built. Bus 18 *is* a
  virtual laboratory, and V2G plus rooftop PV are the eco-innovations under test.
- **"energy-efficient systems … sustainability analytics in an educational setting"** — was the real
  gap and is now closed. `totalLossKwh` had been computed at every step and thrown away. Measured
  across a day at load scale 0.50, seed 137710: idle **551.7 kWh**, uncoordinated **3397.7**, droop
  **1116.1**, SAC-Lag **1221.5**, SafeSAC **946.9**. Per driver *actually served*: SafeSAC **6.0 kWh**
  against uncoordinated **12.0**, and plain RL **16.1** against droop **6.9** — so the plain agent is
  wasteful as well as dominated, a third axis on the stage-4 result. Surfaced on the scorecard, in the
  stage-2 reveal, in the debrief and in the one-page export, and guarded by three assertions.
- **"public safety infrastructure … disaster resilience"** — not addressed, and not needed. Do not
  bolt on an outage scenario for checkbox reasons; it would dilute the arc with days left.

Consequence: interface work is justified by how well it *films* and by the 40% that is simulation
effectiveness plus engagement — not by immersion for its own sake. The deck's slide-3 definition of
the metaverse ("a shared, immersive, persistent 3D virtual space") describes the field, not the
entry constraint; FAQ 9 exists because entrants asked exactly that.

---

## 7. Environment constraints

Session egress policy **blocks all direct web access** — `metaversereality.ieee.org`, YouTube,
`ieee-isemv.org`, GitHub web, Wikipedia all return `EGRESS_BLOCKED`. WebSearch works; WebFetch does not.
Consequences:

- The **Smartsheet form has never been opened**. Fields, file-size limits, and whether the video is
  uploaded or linked are all **unknown**.
- No webinar recording watched. The 2026 kick-off slides were read in full; spoken content unread.
- `bit.ly/4igbnPi` unresolved.

### Deployment — read this before touching the workflow

The live site is **https://rifat137710.github.io/Public/** and it deploys from **`main`**, not from
the feature branch. Enabling Pages with "GitHub Actions" as the source creates a protected
`github-pages` environment whose deployment-branch policy allows **only the default branch**. Runs 1–3
built green and then failed in the `deploy` job in under a second, with no runner assigned and no logs
— that signature means the job was never dispatched, i.e. environment protection, not a build error.

Development stays on `claude/hello-vj564a`; shipping is `git push origin claude/hello-vj564a:main`
(a fast-forward, no force). Verify with `actions_list` on `deploy.yml` — the `deploy` job must show a
`runner_id` and steps, not a one-second failure.

Egress from the session also blocks `*.github.io`, so the deployed page **cannot be fetched from here**.
Trust the workflow conclusion instead: `actions/deploy-pages@v4` reports success only once the
deployment is serving. Visual checking is done against a local `vite preview` with Playwright, never
against the live URL.

Local tooling notes: no `pdftotext`/`poppler`; system `cryptography` is broken (pyo3 panic), so Python
PDF work runs from a venv at
`/tmp/claude-0/-home-user-Public/e7002dc9-9fa4-55e6-af4a-2b37b9d88d33/scratchpad/venv`
with `pypdf`, `pdfplumber`, `pypdfium2`, `opencv-python`. Page rendering via `pypdfium2`; QR decoding
via OpenCV (invert dark-background codes before decoding).

---

## 8. Open items

- [ ] **Claude:** repoint engine onto 33-bus linearised model; build village, console, map, six stages
- [ ] **User:** email `metaversechallenge@ieee.org` re: thesis provenance and originality
- [ ] **User:** open the Smartsheet portal, report fields and file-size limits
- [ ] **User:** run `probe()` in the notebook, then export `sensitivities.json` (highest priority file)
- [ ] **User:** recruit 8–10 testers
- [ ] Decide: start with engine, or mock the screen layout first for approval — *awaiting user's answer*

## 9. The blueprint (8 Aug 2026)

Full build blueprint written to **`docs/blueprint.html`** (committed) and published at
`https://claude.ai/code/artifact/196efff1-cbe6-4c54-a978-670fd161dbcf`. It supersedes the earlier
visual-system/pipeline artifact. Covers: system scope and file manifest (~30 files, ~3,500 LOC),
the one-screen wireframe, the full control inventory, eight learning objectives L1–L8 mapped to
stages and assessment questions, the six-stage arc beat by beat, the two-tier backend, the five
physics verification gates, the seven-day schedule, hardware/software list, scope ladder and risk
register.

**Deadline reality:** entry closes 15 Aug 2026 23:59 EDT = **09:59 on 16 Aug, Dhaka time**. Seven
days from the blueprint date.

### Numbers verified from the thesis text on 8 Aug (use these, they are checked)

- 288 steps × 5 min = one day (§4.5, `T = 288`, `Δt = 5 min`)
- EV stations at **buses 18, 22, 25, 33** (Fig. 4.2, 1-indexed); Table 4.1 lists the same as
  pandapower indices 17, 21, 24, 32. PV at buses **6, 13, 30**.
- Weak-grid `|∂V/∂P|` at bus 17: **9.08e−5 pu/kW**; bus 21: 2.46e−5; bus 24: 2.55e−5; bus 32: 5.71e−5.
  Weak mean `|∂V/∂P|` = 4.95e−5, `|∂V/∂Q|` = 3.87e−5 → ratio-of-means **1.280**; Gate 1 reports **1.271**.
  Quote as "1.27–1.28".
- Base case at **full** load: weak Vmin **0.882 pu**, loss **338.6 kW**; strong Vmin **0.913 pu**,
  loss **202.7 kW**. Full load is already infeasible in [0.95, 1.05] — this is *why* experiments run
  at load scale 0.50.
- Fleet: 287 arrivals, bimodal; battery σ 15 kWh clipped [30, 100]; arrival SoC [0.15, 0.55]; target
  SoC [0.70, 0.90]; dwell [2, 12] h, mean 7 h; 80% opt into V2G; 22 kW ceiling; η = 0.92.
- **Monte-Carlo check: 100% of energy-service requests are physically deliverable within dwell at the
  operating point.** Therefore unmet service reflects *control decisions, not infeasible demand*.
  This is what makes `SoC met = 0.000` damning rather than excusable — load-bearing for stage 6.
- Projection: 8 variables, CVXPY + CLARABEL; infeasible → curtail; **3 consecutive failures → freeze
  to a safe default**. Applied to the environment-facing action during both collection and evaluation;
  the policy gradient is taken w.r.t. the *unprojected* action — a safety filter, not a differentiable layer.
- Sign convention: **negative = discharge/injection**. Table 5.3's −80 kW is a V2G discharge request.
  *Unresolved:* which wall of the band binds at that operating point. Reproducing Table 5.3 from the
  exported sensitivities settles it; it changes one sentence of stage-5 narration and nothing structural.
