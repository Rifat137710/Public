# Novelty audit and reviewer defence — ISGT 2026 submission

**Author:** Md. Rifat Rahman (BUET EEE) · **Written:** 2026-08-15
**Purpose:** answer four questions honestly, with evidence, before a word of the
paper is written.

1. Is this type of work relevant to the venue?
2. Has anyone done it? Is the finding novel or already known?
3. What is the answer when a reviewer asks *why was this work done?*
4. Every other attack a reviewer can make, and whether our answer holds.

This document is deliberately adversarial. Where our position is weak it says so.

---

## 0. Executive summary

**Relevant:** yes, squarely in ISGT scope. Not at risk.

**Novel:** *partly, and less than I claimed last week.* The underlying
mechanism — that measurement feedback compensates for model error — is a known
principle in at least three separate literatures. What is not in the literature
is the **closed-loop safety-filter characterisation**: that a stale base point
does not degrade the filter, it **silently switches it off**, and the transition
is a cliff.

**One headline claim must be demoted.** "Faster refresh is worse" does not
survive per-seed scrutiny (§4.6). It is a 0.3 pp mean effect, 4/6 cells, no
stored variance. Keeping it as a headline is the single largest rejection risk
in the paper, because it is the one claim a reviewer can falsify with our own
appendix.

**What survives is still a paper.** It is a narrower paper than the one I
described previously.

---

## 1. Is this type of work relevant?

Yes, and this is the least uncertain thing in this document.

ISGT's call covers grid operation and control, EV integration, and AI/ML
applied to distribution systems. A paper that takes a mechanism *already in
wide use across that literature* — sensitivity-based action projection as a
safety filter — and establishes the conditions under which it stops working is
a service-to-the-field contribution of exactly the type conferences take.

The relevance argument is strengthened by how many recent papers **depend** on
the mechanism we are stress-testing. All of the following build a safety layer
on a voltage sensitivity matrix and none of them report its refresh
requirement:

| Work | Venue | Uses sensitivity-based safety projection | Reports refresh cadence |
|---|---|---|---|
| Multi-Agent RL with Safety Layer for Active Voltage Control | AAMAS 2023 | yes | no |
| Model-augmented safe RL for Volt-VAR control | Applied Energy 2022 | yes | no |
| Safe MADRL for inverter-based DER w/ communication delay | Applied Energy 2023 | yes | delay handled, cadence not swept |
| Physics-Regularized Bi-GAT safety-enhanced RL for voltage control | Energies 2026 | yes | no |
| Safety-Aware RL for EV Charging Station Management | 2024 | yes (PCPO) | no |
| DuMES dual-layer safety modules for EV charging | IET Smart Energy 2025 | yes | no |

The gap is real and it is load-bearing for a body of work, not a curiosity.
**Relevance: not a rejection risk.**

---

## 2. Prior art — what exists, and what does not

I searched five distinct framings of the claim. Findings below, ordered by how
dangerous each is to our novelty.

### 2.1 The mechanism is already known — in three literatures

This is the honest headline and I did not state it clearly before.

**(a) Incremental / sensor-based control (flight control, since ~2010).**
Incremental Nonlinear Dynamic Inversion replaces model terms with direct sensor
measurements, and the textbook result is that this "greatly improves robustness
against model uncertainties" while making the controller **sensitive to
measurement delay**. That is our finding's exact shape — model error cheap,
measurement currency expensive — established in a different domain fifteen
years ago.

**(b) Model-less / measurement-based voltage control (EPFL and others).**
An entire sub-literature estimates voltage sensitivity coefficients from
measurements *precisely because* the model-based ones are unreliable. A 2026
survey line states it directly: measurement-feedback approaches "leverage
real-time voltage measurements to correct gradient estimation errors, thereby
implicitly compensating for both parametric mismatches and structural
linearization inaccuracies."

**(c) Online feedback-based linearised power flow (Bai et al., IEEE TPWRS 2022;
arXiv 2103.14820).** *This is the nearest neighbour and a mandatory citation.*
It updates linearisation parameters online from instantaneous voltage and load
measurements, and — critically — it **already tests robustness against
measurement error, communication failure (via an explicit "freeze" strategy),
and update frequency** on IEEE 123-bus.

**Consequence.** We cannot claim to have discovered that measurement feedback
substitutes for model accuracy. If we do, a reviewer who knows (c) will reject
on novelty and be right to.

### 2.2 What is genuinely absent

Having conceded the mechanism, here is what none of the above does.

| Question | Prior art | Us |
|---|---|---|
| Does measurement feedback compensate model error? | **Answered** (a,b,c) | reconfirm, don't claim |
| Quantified as *Jacobian frozen, base point measured* vs *both frozen*, with everything else identical? | not found | **yes** |
| Measured on a **closed-loop constraint-enforcement filter**, metric = violation rate? | no — (c)'s metric is voltage *estimation error*, an open-loop accuracy metric | **yes** |
| Is the degradation gradual or a cliff? | (c) reports "update frequency can be set as any reasonable value" — i.e. benign | **cliff**, 0.0000 → full raw rate between 2 h and 4 h |
| Does the filter *report* that it has stopped protecting? | not asked | **no — infeasible rate is 0.0000 in 6/6 cells while protection is entirely gone** |
| Independent of what generates the request? | not asked | **yes — 3 unrelated sources** |
| Hosting-capacity envelope beyond which no cadence suffices | not found | **yes, Z ≤ 8 %** |

The distinction that carries the paper is **open-loop accuracy vs closed-loop
enforcement**. Bai et al. show a stale linearisation gets *less accurate*. We
show a stale linearisation makes a safety filter *inert* — which is not the
same statement, and does not follow from it. A model can be badly wrong and
still refuse unsafe actions; a model can be mildly wrong and pass everything.

### 2.3 The one place we contradict published work

The AAMAS 2023 safety-layer paper markets its design as "not requiring accurate
impedance values… using approximate sensitivity information." Meanwhile the
Bi-GAT paper (Energies 2026) motivates itself by "model-based projection being
sensitive to parameter error."

**These two claims contradict each other, and neither side ran the experiment.**
We did. Our answer sides with AAMAS: a wrong-network Jacobian costs 0.0000
violations. That is a small but real adjudication and worth one sentence in the
paper.

---

## 3. "Why was this work done?" — the reviewer-facing answer

Three paragraphs, in the order a reviewer will accept them.

**Because the field standardised on this mechanism without characterising it.**
Sensitivity-based action projection is now the default way to make an RL
controller safe on a distribution feeder (§1 table). Every one of those papers
computes a sensitivity matrix at some operating point and reuses it for some
interval. Not one states what interval, or shows what happens at another. A
mechanism this widely reused should have a published operating envelope.

**Because the failure is silent, and silence is what makes it a safety
problem.** If a stale filter degraded gracefully, an operator would see rising
violations and act. It does not. At the stalest setting the filter reports
**zero infeasibilities** — no alarm, no fallback, no diagnostic — while
delivering **97.9–100 % of the completely unprotected violation rate**. A
component that is fully broken and fully quiet cannot be caught by monitoring
its own outputs. That is a deployment hazard, and it is the reason this is a
grid paper rather than an RL paper.

**Because the binding constraint is metering, not computation.** Our own
measurement shows the projection consumes 0.004 % of a 300 s control interval:
computing the Jacobian is free. But a fresh **base point** is not a
computation, it is a *measurement*, and its cadence is set by infrastructure
the controller does not own — distribution state estimation on 1–15 min cycles,
AMI on 15 min to 1 h, SCADA telemetry concentrated at the substation rather
than at every station bus. A designer therefore cannot buy base-point currency
with compute, which is exactly why knowing how much of it is needed matters.
This also explains the asymmetry: the expensive artefact (an accurate network
model) turns out not to matter, and the artefact constrained by metering rollout
turns out to be everything.

---

## 4. Reviewer attack surface

Each attack, our answer, and an honest verdict on whether the answer holds.

### 4.1 "The mechanism is known — measurement feedback compensates model error."

**Answer.** Agreed, and we cite (a), (b), (c) in the introduction. Our claim is
not the mechanism, it is the *closed-loop consequence*: the transition is a
cliff, not a slope, and the filter does not signal it. Open-loop accuracy loss
(Bai et al.) does not predict binary loss of enforcement.

**Verdict: HOLDS — but only if we concede the mechanism in the introduction
rather than claiming it.** If the paper reads as "we discovered measurement
feedback beats model accuracy," this attack kills it. The framing must be
defensive from sentence one.

### 4.2 "Refreshing is cheap. Why would anyone run it stale? Strawman."

**Answer.** §3, paragraph three: refreshing the base point is a measurement, not
a computation, and its cadence is fixed by DSSE/AMI/SCADA infrastructure. Also
the freeze case is not hypothetical — it is exactly the communication-failure
contingency Bai et al. model with their "freeze" strategy, and our result says
that under that same contingency a safety filter does not merely lose accuracy,
it stops filtering.

**Verdict: HOLDS, but it is the most dangerous question in the review.** Our
defence is an argument about deployment, not a measurement — we simulate refresh
by recomputing power flow, not by simulating a metering pipeline. The paper must
state that plainly and frame the axis as **age of the base point**, agnostic to
what produces it. Do not oversell.

### 4.3 "Faster refresh is worse — this is just conservatism, and your own numbers wobble."

**Answer.** *Concede and demote.* See §4.6. This must not be a headline.

**Verdict: DOES NOT HOLD as currently claimed.**

### 4.4 "One feeder, one topology."

**Answer.** IEEE 33-bus with a Thévenin substation, swept across
Z ∈ [0.5 %, 12 %]. Conference scope; the second feeder (123-bus, European LV
unbalanced) is stated as journal work.

**Verdict: HOLDS at ISGT, would NOT hold at TSG.** Correctly allocated. But note
the sweep axis is weak — Jacobians differ only 1.16× across it (see
`03-isgt-2026-plan.md`), so it is a *base-voltage* sweep, not a topology sweep.
Describe it as an operating-stiffness sweep and do not imply topological
diversity.

### 4.5 "Your RL controller is bad. Why is RL in this paper?"

**Answer.** It is not a contribution. SAC-Lagrangian appears as **one of three
unrelated request sources** — greedy, deadline-aware heuristic, learned — used
to show the staleness result is a property of the *filter*, not of the
controller feeding it. The result replicates across all three, and the learned
source is the one that makes that claim non-trivial.

**Verdict: HOLDS, and is a strength if framed this way.** It becomes a liability
the moment the paper implies the RL is any good. It is not; §0 of the plan
records that a coin flip between two heuristics beats it.

### 4.6 "Show me the confidence intervals."

**This is where we are exposed.** Present state of the evidence:

| Claim | Replication | Verdict |
|---|---|---|
| Never-refreshed ≈ unprotected | 6/6 cells, 3 seeds × 200 ep, range 97.9–100 % | **solid** |
| Silent — infeasible rate 0.0000 while unprotected | 6/6 cells | **solid** |
| Cliff between 2 h and 4 h | 6/6 heuristic cells + 6/6 learned cells | **solid** |
| Wrong Jacobian costs nothing (0.0000 vs 0.0000) | 2 deploy points × 2 modes | **solid** |
| **"Faster refresh is worse"** | see below | **NOT ESTABLISHED** |

Per-seed service delta, refresh 12 minus refresh 1, learned source, 3 seeds ×
200 episodes:

| Z | seed | r1 | r12 | Δ |
|---|---|---|---|---|
| 6 % | 0 | 0.07276 | 0.08658 | **+0.01383** |
| 6 % | 1 | 0.01431 | 0.01431 | +0.00000 |
| 6 % | 2 | 0.13074 | 0.13074 | +0.00001 |
| 8 % | 0 | 0.06864 | 0.07066 | +0.00202 |
| 8 % | 1 | 0.01250 | 0.01250 | +0.00000 |
| 8 % | 2 | 0.13405 | 0.13532 | +0.00127 |

**4 of 6 strictly positive, 2 exactly zero, none negative, mean +0.0029.**
Direction is consistent; magnitude is negligible and significance is not
established. A sign test on n = 6 with two ties cannot reach p < 0.05.

And in the 25-episode heuristic sweep the ordering is not even monotone at
Z = 6 %: r1 0.7421, r3 0.7466, **r12 0.7383**, r24 0.7643. The dip at r12 is
noise-sized, and `results/staleness_sweep_25ep.json` **stores means only — no
per-episode variance**, so no interval can be computed from the saved artifact.

Worse, at Z = 8 % and Z = 10 % the relationship is cleanly **monotone
increasing** in refresh interval, with violations rising alongside. That is not
a surprising non-monotonicity — it is the ordinary conservatism/performance
trade-off, and a reviewer will name it as such:

| Z | r1 | r3 | r12 | r24 | r48 | shape |
|---|---|---|---|---|---|---|
| 6 % | 0.7421 | 0.7466 | 0.7383 | 0.7643 | 0.7933 | wobbly, +2.2 pp over r1..r24 |
| 8 % | 0.6409 | 0.6390 | 0.6674 | 0.6888 | 0.7171 | monotone |
| 10 % | 0.5514 | 0.5780 | 0.5944 | 0.5942 | 0.6782 | monotone |

**Required action.** Either (i) re-run the staleness sweep with ≥ 5 seeds,
storing per-episode arrays, and report stratified-bootstrap intervals; or
(ii) **demote the claim** to a secondary observation stated correctly as: *"at
Z ≤ 6 % the safety cost of extending the interval to 2 h is exactly zero, so
the conservatism/service trade-off is free in that band"* — which is true,
useful, and does not require the effect to be significant.

(ii) is the honest minimum and costs no compute. (i) is a few CPU-hours and
makes the paper better. Do both if time allows; do (ii) regardless.

### 4.7 "This is a characterisation, not a method. Where is the contribution?"

**Answer.** The output is a design rule with a number in it — refresh the base
point at least every 2 h, valid for Z ≤ 8 % — plus a named failure mode
(silent inertness) and a detection test (a filter reporting zero infeasibilities
on a loaded feeder is not protecting it, it has stopped binding). That last item
is actionable: it is a one-line runtime assertion any of the six papers in §1
could adopt.

**Verdict: HOLDS if we ship the assertion.** A pure "we measured things" paper
is at real risk at any venue. Convert the finding into a diagnostic the reader
can implement, state it in the abstract, and the contribution becomes concrete.
**This should be added to the paper — it is currently missing.**

### 4.8 "Your safety layer removes 12–29 % of the service. That is expensive."

**Answer.** Retention is 0.85–0.89 at the design operating point, and the
comparison that matters is against the alternative that achieves zero
violations — the droop controller — which delivers 0.0067 SoC against our
0.7094. Two orders of magnitude.

**Verdict: HOLDS.** Strongest single number in the paper.

### 4.9 "Freeze-to-zero as an infeasibility fallback is a poor design."

**Answer.** Agreed, and we report it as a *finding* rather than defending it:
past Z = 8 % the fallback becomes the dominant failure mode (0.1171 latched
violation contribution at Z = 10 %, r48). Redesign is stated as journal work.

**Verdict: HOLDS.** Reporting a weakness in your own design as a measured
regime boundary reads as rigour. Do not hide it.

### 4.10 "Simulation only."

**Verdict: HOLDS at ISGT** — the overwhelming majority of the §1 comparison set
is simulation-only on IEEE test feeders. Standard for the venue.

---

## 5. What must change before submission

Ordered by rejection risk removed per unit of work.

| # | Action | Cost | Risk removed |
|---|---|---|---|
| 1 | Demote "faster refresh is worse" to the free-trade-off statement of §4.6(ii) | 0 | **high** — removes the one falsifiable-from-our-own-appendix claim |
| 2 | Concede the known mechanism in the intro; cite INDI, model-less voltage control, Bai et al. TPWRS 2022 | ~half a day of reading | **high** — converts a novelty rejection into a positioning strength |
| 3 | Add the runtime diagnostic ("zero infeasibilities on a loaded feeder ⇒ filter not binding") to abstract + conclusions | 0 | medium — answers §4.7 |
| 4 | Reframe the axis as *age of the base point*, with the metering-cadence motivation of §3 stated explicitly and its simulation caveat admitted | 0 | medium — answers §4.2 |
| 5 | Describe the Z-sweep as operating stiffness, never as topological diversity | 0 | medium — pre-empts §4.4 |
| 6 | Re-run staleness sweep, ≥ 5 seeds, per-episode arrays, bootstrap CIs | few CPU-hours | medium — upgrades §4.6 from concession to result |
| 7 | Verify Bai et al. 2022 in full text (arXiv blocked here; use IEEE Xplore via BUET) and confirm its update-frequency experiment is open-loop accuracy only | 1 h | **high if wrong** — this is the paper that could pre-empt us |

Item 7 is not optional. It is the only prior work found that runs an
update-frequency experiment at all, and this audit relied on abstracts and
search snippets rather than the full text because `arxiv.org`, `doi.org`,
`mdpi.com`, `semanticscholar.org` and `sciencedirect.com` are all blocked by
this environment's egress proxy. **Read it before writing the introduction.**

---

## 6. Verdict

The work is relevant, the gap is real, and the strongest results replicate
across three request sources, three seeds and six cells. The paper is viable.

It is viable as a **narrower and more defensive** paper than previously framed:
one that concedes a known mechanism, contributes the closed-loop
characterisation of a silent failure mode, and ships a one-line diagnostic. The
version that claims to have discovered that measurement beats model, or that
leads with a 0.3 pp non-monotonicity, is the version that gets rejected.

---

## Sources consulted

- Multi-Agent Reinforcement Learning with Safety Layer for Active Voltage Control, AAMAS 2023 — https://dl.acm.org/doi/10.5555/3545946.3598807
- Safety Constrained Multi-Agent Reinforcement Learning for Active Voltage Control — https://arxiv.org/abs/2405.08443
- Model-augmented safe reinforcement learning for Volt-VAR control, Applied Energy 2022 — https://www.sciencedirect.com/science/article/abs/pii/S0306261922002148
- Safe multi-agent DRL for real-time decentralized control of inverter-based RES considering communication delay, Applied Energy 349 (2023) — https://www.sciencedirect.com/science/article/pii/S0306261923010127
- Physics-Regularized and Safety-Enhanced Bi-GAT RL Framework for Voltage Control, Energies 2026 — https://doi.org/10.3390/en19041036
- Safe Reinforcement Learning for Power System Control: A Review — https://arxiv.org/pdf/2407.00681
- A critical review of safe RL strategies in power and energy systems — https://www.sciencedirect.com/science/article/abs/pii/S0952197625000910
- **An Online Feedback-Based Linearized Power Flow Model for Unbalanced Distribution Networks, IEEE TPWRS 2022 — https://ieeexplore.ieee.org/document/9640330 (nearest prior art)**
- Model-less robust voltage control in active distribution networks using sensitivity coefficients estimated from measurements — https://www.researchgate.net/publication/362144187
- Experimental Validation of Model-less Robust Voltage Control using Measurement-based Estimated Voltage Sensitivity Coefficients — https://arxiv.org/abs/2304.13638
- Online Voltage Control for Active Distribution Grids via Measurement Feedback Correction, Electronics 2026 — https://www.mdpi.com/2079-9292/15/5/1031
- Provably robust online voltage control for distribution networks with line parameter estimation — https://www.sciencedirect.com/science/article/abs/pii/S0947358025000810
- Efficient Computation of Sensitivity Coefficients of Node Voltages and Line Currents in Unbalanced Radial Distribution Networks — https://www.academia.edu/17518551/
- Stability and Robustness Analysis and Improvements for Incremental Nonlinear Dynamic Inversion Control — https://www.academia.edu/65406664/
- Safety-Aware Reinforcement Learning for EV Charging Station Management in Distribution Network — https://arxiv.org/abs/2403.13236
- DuMES: DRL-Based EV Charging Scheduling With Dual-Layer Safety Modules, IET Smart Energy Systems 2025 — https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/ses2.70017
- Evaluation of AMI and SCADA Data Synergy for Distribution Feeder Modeling — https://ieeexplore.ieee.org/document/7061524/
- How to Create an Accurate Network Model and Dynamic State Data for an ADMS, IEEE Smart Grid — https://smartgrid.ieee.org/bulletins/april-2020/how-to-create-an-accurate-network-model-and-dynamic-state-data-for-an-advanced-distribution-management-system-adms
