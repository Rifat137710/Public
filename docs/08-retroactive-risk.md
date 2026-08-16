# Retroactive risk — what a journal-stage result could do to a published conference paper

**Written:** 2026-08-15
**Constraint that forces this analysis:** the conference paper is *irreversible*
once published. Journal work continues afterwards. Any journal finding that
contradicts a published conference claim damages both.

**Governing principle:** *every conference claim must be stated at the scope it
was measured, so that any later finding **extends** it rather than
**contradicts** it.*

Stated the other way: a claim broader than its evidence is a debt that a future
experiment can call in.

---

## 1. The register

| # | Risk | Conference exposure | Verdict |
|---|---|---|---|
| **R1** | **G1 fails** — real metering cadences all sit inside the safe band | **Motivational only** | Manageable by framing |
| **R2** | **G4 fails** — the cliff does not appear on IEEE 123-bus | **Direct and serious** | **Retire before submission** |
| **R3** | **G2 / G3 fail** — age-aware tightening doesn't beat a fixed margin, or the bound is too loose | **None** | Conference immune |
| **R4** | A better-trained policy later beats projected-greedy | **Direct** | Manageable by scoping |
| **R5** | A real topology-mismatch axis shows network-model error *does* matter | **Direct and serious** | Manageable by scoping — but the scoping must be exact |
| **R6** | More seeds reverse "faster refresh is worse" | Already retired | Demoted in `04` §4.6 |

---

## 2. R1 — G1 fails

**What happens.** We find that DSSE at 1–15 min and AMI at 15 min–1 h put every
real deployment two orders of magnitude inside the safe band. Our cliff at 2–4 h
describes a regime nobody occupies.

**What it does *not* touch.** Every measured conference result stands. The
never-refreshed result, the cliff, the frozen-Jacobian result, the envelope, the
compute figures — all are measurements at specified refresh intervals on a
specified testbed. Whether anyone *operates* at 4 h does not make them false.

**What it does touch.** If the conference paper *motivates itself* by asserting
that real deployments operate in the unsafe regime, that assertion becomes
false, and it will be the first sentence of the paper.

**Mitigation — free, and it must be applied.**

> Do **not** claim that deployments operate at unsafe cadences. Motivate on
> what is independently true: *this mechanism's refresh requirement has never
> been reported, and it must be, because the failure is silent.* Then state the
> deployment-cadence question **explicitly as open**.

A paper that names its own open question cannot be embarrassed by the answer.
It can be *cited* by the answer.

---

## 3. R2 — G4 fails · **the one that must be retired now**

**What happens.** The cliff turns out to be a property of `case33bw`'s specific
line impedances rather than of radial distribution feeders generally. A
conference paper that said "a sensitivity-based safety layer" — unqualified —
was wrong.

**Why this one is different.** R1, R4 and R5 can be neutralised by writing the
claim more carefully. **R2 cannot.** The whole value of the paper is that the
finding generalises beyond one arbitrary test case. Scoping the claim to
"on `case33bw`" would protect us from being wrong and simultaneously make the
paper not worth publishing.

**Mitigation: run it before submitting.**

This is the cheapest of the four gates and we already have the machinery:

- `pandapower.networks` ships the IEEE 123-bus case
- `scripts/staleness_sweep.py` is source-agnostic — it takes a request source and a refresh cadence
- **The result replicates on heuristics**, so no retraining is needed and the
  observation-vector dimensionality problem never arises
- The Thévenin-stiffness construction transfers directly

Estimated cost: a few hours of code, a few hours of compute. **This converts the
single largest retroactive risk into a second-feeder result that strengthens the
conference paper.**

### The feeder — checked, not assumed

`pandapower` does **not** ship IEEE 123-bus. It does ship something better for
our purposes. Measured just now:

| network | buses | lines | vmin (base load) | note |
|---|---|---|---|---|
| `case33bw` | 33 | 37 | 0.9131 | our current testbed |
| **`create_kerber_dorfnetz`** | **116** | **114** | **0.9550** | **German village LV feeder — radial, weak, standard benchmark** |
| `create_cigre_network_mv` | 15 | 15 | 0.9230 | CIGRE MV benchmark, too small to add much |
| `create_kerber_landnetz_freileitung_1` | 15 | 13 | 0.9470 | rural overhead, too small |
| `ieee_european_lv_asymmetric` | — | — | — | unbalanced 3-phase; strongest validity, needs a 3-phase solver |

**`kerber_dorfnetz` is the right choice.** It is ~116 buses (comparable in scale
to IEEE 123), radial, a published German LV benchmark, ships with pandapower so
there is no data wrangling, and — decisively — **it sits at vmin 0.9550 at base
load, right at the band edge.** Voltage genuinely binds on it before any EV is
added, which simultaneously answers the NREL objection that voltage does not
bind on well-built feeders. It is a different topology, different impedance
scale, and a different voltage level from `case33bw`, so agreement between the
two is real external validity rather than a restatement.

Fall back to `ieee_european_lv_asymmetric` for the journal, where unbalanced
three-phase is worth the extra solver work.

### R2 — RUN. Result: gate passed, and one claim has to change

`results/staleness_kerber.json`, 3 stiffness points x 2 request sources x 6
refresh intervals x 25 episodes, the identical protocol to `case33bw`.

**The core claim replicates.** A never-refreshed projection reproduces the
unprojected violation rate on a feeder sharing nothing with the thesis testbed:

| feeder | cells | recovery of raw violation rate at r = 288 |
|---|---|---|
| `case33bw` | 6/6 | 100.0 % – 100.0 % |
| `kerber_dorfnetz` | 6/6 | **96.9 % – 100.0 %** |

and it is silent on both: infeasibility rate 0.0000 in every never-refreshed
cell. **R2 is retired. The finding is not a property of `case33bw`'s line
impedances.**

**But the design rule does not transfer, and that is the whole reason to have
run this first.** Last refresh interval with zero violations:

| feeder | Z | last clean interval |
|---|---|---|
| `case33bw` | 6 % | 24 steps — **2 h** |
| `case33bw` | 8 % | 3–12 steps — 15 min – 1 h |
| `kerber` | 1 % | 12 steps — **1 h** |
| `kerber` | 2 % | 12 steps — **1 h** |
| `kerber` | 3 % | 12 steps — **1 h** |

On the LV feeder the cliff sits at 1 h, identically across all three stiffness
levels and both request sources. **"Refresh within 2 hours" cannot be
published.** Had it been, the journal's second feeder would have contradicted a
published number — precisely the failure this document exists to prevent.

The claim that survives is better anyway: *the cliff is universal, its location
is feeder-specific, and it must be measured per feeder.* That is a stronger
statement about the mechanism and it hands the journal an obvious question —
predict the cliff location from feeder properties — instead of a correction.

**R6 is now settled too, and not as "noise".** Service change from refresh 1 to
refresh 48:

| feeder | cells where waiting *helps* service | mean |
|---|---|---|
| `case33bw` | **6/6** | +0.0684 |
| `kerber` | **0/6** | −0.0238 |

Internally consistent on each feeder, exactly opposite between them. So
"faster refresh is worse" is not a weak effect — it is a **real effect with
feeder-dependent sign**, which is far firmer grounds for keeping it out of the
paper than the sample-size argument in `04` §4.6.

### What the second feeder found that no amount of care would have

`N_BUS_CANONICAL` was pinned at 34 — `case33bw`'s weak bus count — and used as
the width of the projection's voltage band. On the 117-bus feeder every bus past
the 34th fell out of the constraint, and on a radial feeder those are exactly
the deep buses where the band breaks.

The projection then **reported zero infeasibilities, solved nothing, and
returned the raw action unchanged at every refresh interval.**

That is the same signature as the staleness failure this paper is about, which
is why it survived 84 tests, an exact reproduction gate and a published thesis:
on one feeder there was nothing to compare against. It is now covered by four
tests, including one that asserts equality with the unprojected run is a
*failure* signature rather than a success.

---

## 4. R3 — G2 / G3 fail

**Conference is fully immune.** The conference proposes no method. If
age-dependent tightening turns out to be no better than a fixed conservative
margin, or the drift bound is too loose to leave useful service, nothing in the
conference paper is contradicted — the journal simply needs a different cure
(event-triggered refresh, sensor placement, or the fallback redesign).

**This is worth noticing:** the conference paper's lack of a method, which is
its weakness as a contribution, is also what makes it un-invalidatable by the
journal's method risk.

---

## 5. R4 — a better policy later beats projected-greedy

**What happens.** In the journal, we or a reviewer train a policy that beats
uncoordinated + projection. The conference's "the layer, not the learner,
carries the service" reads as wrong.

**Mitigation — scoping, and it is nearly free.** What we measured:

- at *this* operating point, with *this* training budget, our learned policy
  contributes nothing positive;
- G0 swept load × penetration and found **sequencing gain negative in all six
  cells**, because deferred energy is never recovered in this EV model.

That second point supports a stronger statement than the first, but it is still
**testbed-scoped**. So:

> Claim: *on this testbed, the safety layer rather than the learned policy is
> what delivers safe service, and the operating-point sweep finds no reachable
> cell where sequencing helps.*
>
> Do **not** claim: *RL cannot help with EV voltage support.*

The first survives any future policy. The second does not survive one good paper
from anyone.

---

## 6. R5 — model error turns out to matter on a topology axis · **the subtle one**

**What happens.** The journal builds a genuine model-mismatch axis — different
line impedances, different topology — and finds that a wrong Jacobian *does*
degrade safety. The conference said "network model error is free."

**Why this is a real risk, not a hypothetical.** Our C3 result was measured on
the substation-stiffness axis **only**, and on that axis station-bus Jacobians
differ by just **1.16×**. That is a narrow range. It is entirely plausible that
a topology change producing a 5× or 10× Jacobian difference behaves differently.
We have no evidence either way, and "we found no effect over a 1.16× range" is
very weak grounds for "model error is free."

**Mitigation — scope C3 to the range actually measured.**

> Claim: *across a substation-stiffness range over which station-bus Jacobians
> differ by 1.16×, carrying the wrong network's Jacobian costs nothing, while
> freezing the base point costs everything — so within this range the
> protection is carried by the base point, not the model.*
>
> Do **not** claim: *network model error is free.*

Stated that way, a later finding that a 10× Jacobian error *does* matter becomes
a **natural extension** — "we now locate the threshold" — rather than a
correction. The conference sentence stays true forever.

This is the single most important line-edit in the paper, and it costs nothing.

---

## 7. What this changes

**The gate ordering flips.**

Earlier recommendation: Gate 1 first, because it is cheapest and carries the
most journal risk.

**Corrected: Gate 4 (123-bus) first, because it is the only gate that can
retroactively damage a published conference paper, and it is cheap.**

Gate 1 protects the *journal*. Gate 4 protects the *conference*. The conference
is the irreversible one, so it goes first.

**Order: G4 → submit → G1 → build the bound (G3) → G2.**

---

## 8. Bottom line

Of four gates, **two cannot touch the conference at all** (R3), **two are
neutralised by writing the claim at its measured scope** (R1, R4, R5), and
**one requires an experiment** (R2).

That experiment is a few hours of work on machinery that already exists.

With the 123-bus check run and the three scoping edits applied, **no journal
outcome can falsify a published conference claim.** Every one of the four gates
would then either extend the conference result or fail silently inside the
journal, where failure is recoverable.

That is the standard to meet before submitting, and it is reachable.
