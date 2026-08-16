# Paper — IEEE PES ISGT Asia 2026

`isgt2026.tex` · **Track:** Electric Vehicle-Grid Integration and Smart Charging
for Carbon Neutrality.

## Venue requirements, and where each is enforced

| Requirement | Source | Enforced by |
|---|---|---|
| 4–6 pages, full paper | ISGT Asia 2026 CFP | `check_paper.py` reads the page count out of the `.log` |
| A4, single PDF | ISGT Asia 2026 CFP | `\documentclass[conference,a4paper]` — verify with `pdfinfo` |
| Conference's own template | `conference-latex-template.zip` | `IEEEtran.cls` shipped in this directory is the one from the template |
| Abstract ≤ 150 words, no math/figures/tables/refs | IEEE PES author kit | `check_paper.py` |
| ≤ 5 keywords, alphabetical | IEEE PES author kit | `check_paper.py` |
| No math or special characters in title or abstract | template header | `check_paper.py` |
| All template guidance text removed | template footer, in red | `check_paper.py` |

Deviations from the shipped template, and why: `a4paper` (the CFP demands A4
while the template ships US Letter), `booktabs` added, `algorithmic` dropped as
unused. None of these touch margins, column widths, line spacing or type size.

## Build

```
python scripts/make_paper_tables.py      # tables/*.tex + tables/numbers.tex
python scripts/make_paper_figures.py     # figures/*.pdf
cd paper && pdflatex isgt2026 && pdflatex isgt2026
python scripts/check_paper.py            # must print "all checks passed"
```

`scripts/trace_episode.py` regenerates `results/trace_kerber.json`, which
Fig. 3 needs. It runs a simulation, so it is not part of the ordinary build.

## The rule that matters

**No number is typed into the `.tex` by hand** — not in the tables, and not in
the prose. Tables are `\input` from `tables/`; every figure quoted in a sentence
is a `\n...` macro from `tables/numbers.tex`. Both are generated from
`results/*.json`.

This is not fastidiousness. A transcription error in a paper is invisible to
every other check this repository runs — the tests, the reproduction gate and the
sweeps all pass regardless of what ends up in the manuscript. Writing
`numbers.tex` immediately corrected two figures that had been wrong in the draft
(the LV over-estimation cost is 11 percentage points, not 12; the MV service loss
is 3.9, not 4).

`check_paper.py` fails the build if a bare four-decimal number appears in the
prose, and separately **recomputes each headline claim from the raw JSON and
confirms it survived into the compiled PDF** — a path that does not go through
`numbers.tex`, so a bug in the generator cannot hide behind it.

| float | source | claim |
|---|---|---|
| Table I `testbeds` | `kerber_operating_point.json` | the two feeders share nothing |
| Table II `layer_not_learner` | `projected_heuristics.json`, `ablation/ablation.json` | C5 — 8.0× |
| Table III `staleness` | `staleness_sweep_25ep.json`, `staleness_kerber.json` | C1, C2 — absolute rates |
| Table IV `diagnostic` | `staleness_kerber.json`, `model_error_case33bw.json` | C4 — the spine |
| Fig. 1 `fig_loop` | — | the argument, before any data |
| Fig. 2 `fig_cliff` | both staleness files | C1, C2 — the headline |
| Fig. 3 `fig_trace` | `trace_kerber.json` | the mechanism, in one episode |
| Fig. 4 `fig_model_error` | both model-error files | C3 — 0.80×–2.06× |

## Claims are frozen

`docs/00-state-of-play.md` §2b. Do not strengthen them while editing. Each is
scoped to exactly what was measured, and that scoping is what stops the journal
work from contradicting a published sentence — see `docs/08-retroactive-risk.md`
for which claim each edit protects.

Reporting rules that travel with the claim set:

- three request sources on the MV feeder, **two** on the LV feeder — never
  "three sources" flat
- point estimates only; no confidence intervals claimed
- weak, low-SCR feeders only; no generalisation to well-built distribution
- refresh is simulated by recomputing power flow, not by a metering pipeline
- the cliff **location** is not a universal number — never "refresh within 2 h"
- MV at `Z_sub = 10 %` is outside the envelope: the layer does not reach zero
  violations at any cadence there. Shown in Fig. 2, not hidden.

## Before submission

| # | Item | State |
|---|---|---|
| 1 | Read Bai *et al.* (TPWRS 2022, ref. [11]) in full — nearest prior art | ⬜ **do first** |
| 2 | Verify every bibliography entry against the paper itself | ⬜ details came from indexing services |
| 3 | Co-authors, affiliations, funding `\thanks`, acknowledgment | ⬜ author's call |
| 4 | Settle authorship of the thesis-derived infrastructure with supervisors | ⬜ |
| 5 | Re-run `check_paper.py` after any edit | ⬜ |

The `\section*{Acknowledgment}` block is commented out rather than left empty —
restore it once there is text to put in it. Reference order is first-citation
order as IEEE requires, and `check_paper.py` verifies it; if you add or move a
citation, re-run the check.
