# ISGT Asia 2026 submission

**Deadline: 20 August 2026.** Conference 30 Oct – 1 Nov 2026, Wuhan.
Track: *Electric Vehicle-Grid Integration and Smart Charging for Carbon Neutrality*.

## Build

```
python make_figs.py     # regenerates all five figures as PDF (and PNG for review)
pdflatex main.tex && pdflatex main.tex
```

Compiles clean: 6 pages, 0 undefined references. `a4paper` is set deliberately — the
submission rules require A4 while the distributed IEEEtran template ships US-letter.

## Before you submit — three things only you can do

1. **Author block.** `main.tex` lines 22–33 are still the template placeholders.
2. **Funding footnote.** The template's `\thanks{}` was removed; add one if any grant must
   be acknowledged, or leave it out.
3. **Reference [12] and [1].** Every other reference was verified against a primary source
   this session. `iea2025` is an annual series (safe but check the edition you mean), and
   `v2gaging2024` (Dubarry, Devie, McKenzie, *J. Power Sources* 358:39–49, 2017) was
   substituted for an unverifiable 2024 review — its authors could not be confirmed, and
   guessing them was not acceptable.

## Pending result

Section IV-C and Fig. 4 currently report the **20 000-step** P/Q allocation measurement
(E11). The E11b re-run at 100 000 steps was still executing when this draft was written.
When `e11b_log.txt` lands, three places need updating:

- §IV-C numbers (23.6° / 20.1° and the day-mean angles)
- `AG_M` / `AG_A` arrays in `make_figs.py` (Fig. 4)
- the caveat sentence in §VII about the mild comparison

If E11b returns FLAT the claim strengthens and the wording barely changes. If it returns
CLOSING, §IV-C must be rewritten as "learnable but not at the budget this literature uses."

## Numbers and their sources

Every figure and table value is transcribed from the logs in `../results/`:

| file | experiments |
|---|---|
| `run_log_20260819.txt` | E0, E1, E2, E3, E5/E7, E6, E8, E9, E10, E11 |
| `e12_log_20260819.txt` | E12 |
| `e13_log_20260819.txt` | E13 |

`make_figs.py` holds them as literals with the source noted in its docstring, so a figure
cannot drift from the table silently.
