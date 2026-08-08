# Project context — persistent memory

Durable record of everything established for the 2026 IEEE Metaverse Grand Challenge entry.
Committed to git so it survives session loss and context compaction. Update it, don't replace it.

Last updated: 8 August 2026.

---

## 1. The competition

**2026 IEEE Metaverse Grand Challenge for Simulation-Based Learning**
Track entered: **Sustainable Smart Cities and Urban Innovation** (theme 2 of 3).

| Fact | Value |
| --- | --- |
| Entry period | 15 Feb 2026 08:00 EDT → **15 Aug 2026 23:59 EDT** |
| Winners announced | 14 Sept 2026 |
| Team size | 1–5, one team per person, **members locked at submission** |
| Entries per team | Exactly one, one declared theme |
| Deliverable 1 | PowerPoint, **hard cap 5 slides**, no appendix allowance |
| Deliverable 2 | Video, **5–7 min, MP4** |
| Judged on | Slides + video **only**. No live demo. Judges never run your build. |
| Submission portal | `https://app.smartsheet.com/b/form/019e6b3c328078b2b90678fc9c56342c` |
| Competition page | `https://metaversereality.ieee.org/competition/` |
| 2026 rules PDF | `https://metaversereality.ieee.org/wp-content/uploads/2026/04/IEEE-FD-and-YP-2026-Metaverse-Grand-Challenge-for-Simulation-Based-Learning-Final-R2.pdf` |
| General contact | `metaversechallenge@ieee.org` |
| Office hours / chair | `polatgoktas@ieee.org` (Polat Goktas, competition chair) |
| Prize (theme 2) | US$2,500 travel reimbursement ×2 · backpack+certificate ×2 · **US$1,000 cash, Smart Cities only** |
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
5. Impact, scalability, platform access + demo/repo links (must open **without login**)

### Theme 2 sub-buckets (from the 2025 webinar)

- **Virtual Sustainability Labs** — carbon-neutral design, green architecture, community resource management
- **Eco-Innovation in Action** — energy-efficient buildings, smart grids, waste management, urban farming
- **Public Safety & Resilience** — disaster preparedness, emergency response, smart surveillance

Theme 2 is judged by a **separate selection committee** for the IEEE Smart Cities award — inferred to be
infrastructure/power engineers, so real engineering is scrutinised.

### Rules traps confirmed

- Three files in the supplied packet still show the **2025** deadline (1 Sept 2025). Stale. Correct date is 15 Aug 2026.
- Slide 39 of the 2026 kick-off deck has a QR labelled "Submit Your Project" that actually decodes to the
  **Google expression-of-interest form**, not the portal. Slides 38 and 45 are correct.
- The expression-of-interest form is **optional and is not an entry**.
- **Originality:** FAQ 8 — "Your project must be original, not previously published or submitted elsewhere."
  Warranty clause — entry must be "your sole original work, has not been previously published, released or
  distributed." See §3 for why this matters here.
- Licence grant covers name, likeness and **voice** — perpetual, worldwide. Relevant if anyone narrates on camera.
- Contest is **not open to individuals or teams subject to export control regulations**.

### 2025 winners — the pattern to match

All four built **VR training simulations replacing an expensive or risky physical activity**. None built a
general-purpose metaverse world.

| Team | Project | Note |
| --- | --- | --- |
| InscapeXR (IIT Kharagpur) — 1st | VR STEM experiments | AI tutor, haptics, gamified |
| Innov8 (Nigeria) — 1st | SkillForge-VR, voice-first VR TVET trainer | Multilingual, claimed 40% faster acquisition |
| N-Tail Lab (Cal Poly Pomona) — 2nd | BroncoVerse, VR digital-logic lab | Logged time/errors/hints to a database |
| MedXperience — 2nd | VR IV-insertion nursing trainer | **n=9 study**: cognitive load 12→7.2, SUS 80.28 |

Field size 2025: 131 expressions of interest from 24 countries.
**A 9-person user study was enough to place second.** Almost nobody brings numbers.

---

## 2. The thesis (user's own prior work)

**"Safe Deep Reinforcement Learning for Vehicle-to-Grid Voltage Support in Weak Distribution Feeders:
A Physics-Aware Approach"**

- Authors: **Md. Rifat Rahman (202006137)** — the user — and **Sad Sami (202006150)**
- Supervisor: Dr. Md. Forkan Uddin, Professor
- Institution: Dept. of EEE, **Bangladesh University of Engineering and Technology (BUET)**, Dhaka
- Course: EEE 400, B.Sc. thesis, **accepted/certified June 2026**
- Files: `SafeSAC_Final.pdf` (64 pp), `Abstract.pdf`, `thesis11.ipynb` (39 cells, ~286k chars of code),
  `thesisbookartifacts21.ipynb` (12 cells, figure generation)

### What it does

Casts real-time bidirectional EV charging as a **constrained Markov decision process** over a 288-step day
on a modified **IEEE 33-bus Baran–Wu** feeder. **SafeSAC** = augmented-Lagrangian Soft Actor-Critic
+ a **safety-projection layer solving an 8-variable second-order cone program (SOCP) at every control step**.
The projection is rebuilt each step from **voltage sensitivities measured on the live network**, so it adapts
to the deployment grid's R/X structure instead of assuming a strong grid.

### The physics that makes it interesting

`ΔV ≈ (R·ΔP + X·ΔQ) / V₀`

- Transmission (strong): X ≫ R → **reactive** power drives voltage
- Weak distribution feeder: R ≈ X → **active** power drives voltage — exactly what an EV charger commands
- Measured dominance ratio `mean|∂V/∂P| / |∂V/∂Q| = **1.271**` on the weak feeder

This inverts the intuition anyone trained on transmission systems carries. **This is the teachable core.**

### Headline results (25 shared-seed episodes per method, load scale 0.50)

| Method | Viol. rate | Vmin (pu) | SoC met | Net cost | V2G util. |
| --- | --- | --- | --- | --- | --- |
| Uncoordinated | 0.116 ± 0.009 | 0.9383 | 0.996 | $230.7 | 0.000 |
| Droop (IEEE 1547) | 0.052 ± 0.009 | 0.9474 | 0.325 | $66.3 | 0.097 |
| SAC-Lag (weak) | 0.090 ± 0.024 | 0.9425 | 0.277 | $104.3 | 0.176 |
| **SafeSAC (weak)** | **0.091 ± 0.002** | 0.9438 | **0.569** | $125.9 | 0.103 |
| SAC-Lag (strong→weak) | 0.015 ± 0.014 | 0.9492 | **0.000** | −$38.2 | 0.105 |
| SafeSAC (strong→weak) | 0.106 ± 0.003 | 0.9438 | 0.447 | $69.7 | 0.048 |

Paired stats, SafeSAC vs SAC-Lag (n=25):

- Violation rate: Δ +0.0008, p_t = 0.86, d = 0.06 → **statistically tied on safety**
- SoC met: Δ **+0.292**, p ≈ 2.2×10⁻⁹, **Cohen's d = 2.04** → roughly doubled service
- Net cost: Δ +$21.6, p = 0.0019, d = 0.89 → modest economic premium
- Cross-deploy: every effect |d| ≥ 9.4

Projection grid-awareness — identical −80 kW V2G request:

| Station | Raw | Safe (weak) | Safe (strong) | Curtailment |
| --- | --- | --- | --- | --- |
| 1 (bus 18, most sensitive) | −80.0 | **−54.13** | −80.00 | 25.87 kW |
| 2 | −80.0 | −77.95 | −80.00 | 2.05 kW |
| 3 | −80.0 | −76.85 | −80.00 | 3.15 kW |
| 4 | −80.0 | −73.30 | −80.00 | 6.70 kW |

### The single most valuable finding for teaching

Under a **strong→weak deployment shift**, the unprotected SAC-Lag agent **collapses to a
non-charging, drain-and-sell policy**: SoC targets met = **0.000**, violation rate a superb-looking **0.015**,
net cost **−$38** (it makes money). It looks like the safest, cheapest controller on the dashboard.
It has simply **stopped serving anyone**.

SafeSAC deployed identically stays operational: 0.447 SoC met at sensible cost.

This is a rare, genuinely profound lesson about **safety metrics being gameable by doing nothing**, and it
is the user's own experimental result. Nothing in the 2025 winning field is comparable.

### Pre-registered decision gates — 3/5 pass (disclosed honestly in the thesis)

1. V–P dominance ≥ 0.90 → 1.271 **PASS**
2. Projection grid-awareness > 1 kW → **FAIL** (artefact: weak grid infeasible, strong grid allowed full
   −80 kW, an 80 kW divergence — *stronger* evidence than the gate sought; conservative feasibility guard)
3. In-distribution safety ratio ≤ 1.05 → 1.009 **PASS**
4. Cross-deployment safety → **FAIL** (SAC-Lag "wins" only by not operating; see above)
5. Service quality ≥ −0.10 → +0.292 **PASS**

### Stack and reproducibility

Python 3.12, PyTorch 2.10 (CUDA 12.8), Tesla T4, pandapower 3.2.0, CVXPY 1.5.3 + CLARABEL,
Gymnasium. Master seed **137710**. Disjoint train/eval seed bands. SHA-256-fingerprinted checkpoints.
Key classes in `thesis11.ipynb`: `EVChargingFeederEnv`, `SensitivityProjector`, `GridSensitivities`,
`SACLagAgent`, `SafeSACLagAgent`, `DroopAgent`, `UncoordinatedAgent`, `Scenario`, `NetworkContext`.

### Stated limitations (thesis §6.11)

Single training seed per configuration · parametric (not measured) load model · structural 9–12% violation
floor at load scale 0.50 · linearised safety model with fixed 0.010 pu margin · **simulation only, no field validation**.

---

## 3. Verdict on using the thesis as the entry

**The thesis as-submitted is NOT a competition-winning entry.** Reasons:

1. **Wrong meaning of "simulation."** The competition wants a simulation a *human learns inside*. The thesis
   uses simulation as a *training environment for an RL agent*. No human learner exists anywhere in it.
   This fails the 25% criterion definitionally, not marginally.
2. **No user experience** — 15% criterion scores near zero.
3. **No gamification or adaptive learning for a person** — most of the 10% AI criterion is about educational AI.
4. **Prior-submission risk.** The thesis was submitted and certified for a B.Sc. degree at BUET in June 2026.
   FAQ 8 and the warranty clause both bar previously submitted/published work.

**But it is an outstanding foundation.** The agreed direction is to build a *new* educational simulator this
week that teaches what the thesis discovered, using the thesis's real physics, real benchmark network, and
real recorded agent behaviour as content. The submitted artefact is the simulator (new work); the thesis is
disclosed as underlying prior research, the way any project cites its own literature.

**Action required: email `metaversechallenge@ieee.org` to disclose and confirm.** Do this immediately —
there is time for a reply before the deadline, and doing it after submission is worthless.

---

## 4. Build state

Repo: `rifat137710/Public`, branch `claude/hello-vj564a`.

**Done (8 Aug):** GridKeeper simulation core — swing-equation district frequency model,
`df/dt = (P_gen − P_load)·f₀ / (2·Σ H·S)`, with load damping, time-delayed UFLS, diesel state machine,
battery efficiency/SOC limits, and the grid-forming vs grid-following inverter distinction.
Deterministic, headless, 24 h in <1 s. `npm run sim` runs a four-strategy validation harness; 9/9 assertions pass.

Files: `src/sim/types.ts`, `src/sim/scenario.ts`, `src/sim/engine.ts`, `scripts/headless.ts`.

**Model finding that contradicted the design assumption:** battery *reserve* does not decide survival
(a 25-min island needs only ~250 kWh). **Inverter control mode** does. Scoring must therefore weight
frequency quality and carbon intensity, not unserved energy alone.

**Pending decision:** whether to keep the generic microgrid scenario or repoint the simulator onto the
thesis's IEEE 33-bus weak feeder and V2G subject matter. The latter is the stronger entry.

### Artifacts published

- Competition dossier — `https://claude.ai/code/artifact/eb405721-ed3e-493c-81b6-0858d7331a38`
- Build plan — `https://claude.ai/code/artifact/53203c55-7c4f-4e76-ad22-1dc1ad185110`

---

## 5. Environment constraints

This session's egress policy **blocks all direct web access** — `metaversereality.ieee.org`, YouTube,
`ieee-isemv.org`, GitHub web, Wikipedia all return `EGRESS_BLOCKED`. Web *search* works. Consequences:

- The Smartsheet submission form **has never been opened**. Its fields, file-size limits, and whether the
  video is uploaded or linked are all **unknown**. The user must check this directly.
- No webinar recording has been watched. The 2026 kick-off slides were read in full; spoken content is unread.
- `bit.ly/4igbnPi` (2025 flyer shortlink) could not be resolved.

## 6. Open items

- [ ] User to open the Smartsheet form and report its fields and limits
- [ ] Email `metaversechallenge@ieee.org` re: thesis-derived work and originality
- [ ] Confirm whether Sad Sami joins the competition team (co-author of the underlying research)
- [ ] Recruit 8–10 people for the user study
