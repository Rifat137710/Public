# ISGT Asia 2026 submission

`main.tex` → `main.pdf`. Six pages, A4, IEEEtran `conference` class.

## Build

```bash
python3 make_figs.py                  # regenerate fig1..fig5 from the production data
pdflatex main.tex && pdflatex main.tex
```

The second `pdflatex` pass resolves cross-references. A clean build reports
6 pages, 0 undefined references, 0 overfull boxes, and all fonts embedded.

## Where the numbers come from

`make_figs.py` reads `../results/production/*.pkl` directly — the pickles written
by the notebooks during the run of 2026-08-19. The per-hour P/Q angle tables are
parsed from `../results/e11b_log_20260819.txt`, because E11b stores only per-seed
summaries in its pickle. Nothing is transcribed by hand, so the figures and the
tables in the paper cannot drift apart.

Every value quoted in the text was cross-checked against the same pickles.

| Figure | File | Source |
|---|---|---|
| 1 | `fig1_decomposition.pdf` | E2, E8, E13 |
| 2 | `fig2_ceiling.pdf` | E5 (no-injection baseline), E8 (optimized) |
| 3 | `fig3_learning.pdf` | E13 |
| 4 | `fig4_pq.pdf` | E11b log tables at 100k steps |
| 5 | `fig5_frontier.pdf` | E3 frontier, mild |

Figure file names match figure numbers. If a figure moves in the text, LaTeX
renumbers it and the file name should be updated to match.

## Before submitting

Three items only the author can settle:

1. **Funding footnote.** There is currently no `\thanks{}` block and no
   Acknowledgment section. If a grant needs crediting, IEEE convention puts it in
   a `\thanks{}` on the first page rather than in a separate section — adding an
   Acknowledgment section instead will push the paper to seven pages.
2. **Reference [1].** `Global EV Outlook` is an annual series; confirm the edition.
3. **Page limit.** The paper is exactly at six pages. Any addition needs a
   corresponding cut.

## Revision log

- Rewritten in the plainer register of the ISGT/PES sample papers: descriptive
  section titles, no rhetorical framing, no bold in tables.
- Author block completed.
- All five figures rebuilt from the production pickles rather than from values
  transcribed out of the logs.
- E11b (P/Q allocation at 100k steps) folded into Section IV-C. Both load levels
  return a FLAT verdict, so the 20k-step diagnosis holds at five times the budget.
  The aggressive-peak numbers changed materially against the earlier single-seed
  measurement: mean absolute deviation 32.5° rather than 20.1° at 20k, and half of
  all sampled hub-hours absorb reactive power at 100k.
- References renumbered into order of first citation.
- Figures 2 and 3 moved to single-column to hold six pages.
