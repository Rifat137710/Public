"""Pre-submission checks on the manuscript that a LaTeX run will not make.

pdflatex is happy to emit a paper whose references are out of citation order,
whose abstract is twice the length the venue allows, or which still contains a
number nobody regenerated. These are the checks that catch that. Run before
every submission:

    python scripts/check_paper.py

Exits non-zero if anything fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "paper" / "isgt2026.tex"

# IEEE PES: abstract limited to 150 words; up to 5 keywords, alphabetical.
# ISGT Asia 2026: full paper of 4-6 pages, A4.
ABSTRACT_MAX_WORDS = 150
KEYWORDS_MAX = 5
PAGES_MIN, PAGES_MAX = 4, 6

ok = True


def check(name: str, passed: bool, detail: str = "") -> None:
    global ok
    ok &= passed
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def strip_comments(tex: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", ln) for ln in tex.splitlines())


def main() -> int:
    raw = TEX.read_text()
    tex = strip_comments(raw)

    # --- abstract -----------------------------------------------------------
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    body = re.sub(r"\\[a-zA-Z]+\*?", " ", abstract.group(1))
    words = len([w for w in re.split(r"\s+", body.strip()) if w])
    check("abstract word count", words <= ABSTRACT_MAX_WORDS,
          f"{words} words (limit {ABSTRACT_MAX_WORDS})")
    check("abstract has no math", "$" not in abstract.group(1),
          "template forbids math in the abstract")
    check("abstract has no citations", "\\cite" not in abstract.group(1))

    # --- title --------------------------------------------------------------
    title = re.search(r"\\title\{(.*?)\n\}", tex, re.S).group(1)
    check("title has no math", "$" not in title)

    # --- keywords -----------------------------------------------------------
    kw = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", tex, re.S)
    terms = [t.strip().rstrip(".").lower()
             for t in kw.group(1).replace("\n", " ").split(",") if t.strip()]
    check("keyword count", len(terms) <= KEYWORDS_MAX,
          f"{len(terms)} (limit {KEYWORDS_MAX})")
    check("keywords alphabetical", terms == sorted(terms),
          "" if terms == sorted(terms) else f"{terms} != {sorted(terms)}")

    # --- references in first-citation order ---------------------------------
    doc = tex.split("\\begin{thebibliography}")[0]
    cited: list[str] = []
    for m in re.finditer(r"\\cite\{([^}]*)\}", doc):
        for k in m.group(1).split(","):
            k = k.strip()
            if k not in cited:
                cited.append(k)
    listed = re.findall(r"\\bibitem\{([^}]*)\}", tex)
    check("every citation has an entry", set(cited) <= set(listed),
          f"missing {set(cited) - set(listed)}" if set(cited) - set(listed) else "")
    check("no uncited entries", set(listed) <= set(cited),
          f"uncited {set(listed) - set(cited)}" if set(listed) - set(cited) else "")
    check("references in citation order", cited == listed,
          "" if cited == listed else
          f"first divergence at {next((i for i, (a, b) in enumerate(zip(cited, listed)) if a != b), len(cited)) + 1}")

    # --- no hand-typed results numbers --------------------------------------
    # Every measured quantity should arrive as a \n... macro from numbers.tex.
    # A bare four-decimal number in the prose means someone typed one in.
    prose = re.sub(r"\\input\{[^}]*\}", "", doc)
    prose = prose.split("\\begin{document}")[1]
    stray = re.findall(r"(?<![.\d])0\.\d{4}(?!\d)", prose)
    allowed = {"0.9550", "0.9658"}  # documented feeder constants, not results
    stray = [s for s in stray if s not in allowed]
    check("no hand-typed 4-decimal results", not stray, f"found {stray}")

    # --- template boilerplate must be gone ----------------------------------
    for phrase in ("Given Name Surname", "dept. name of organization",
                   "Identify applicable funding agency",
                   "This document is a model and instructions",
                   "template text is removed"):
        check(f"template text removed: {phrase[:34]!r}", phrase not in tex)

    # --- macros resolve -----------------------------------------------------
    defined = set(re.findall(r"\\newcommand\{\\(n[A-Za-z]+)\}",
                             (ROOT / "paper" / "tables" / "numbers.tex").read_text()))
    used = set(re.findall(r"\\(n[A-Z][A-Za-z]*)", doc))
    check("all number macros defined", used <= defined,
          f"undefined {sorted(used - defined)}" if used - defined else
          f"{len(used)} used")

    # --- compiled artefact --------------------------------------------------
    log = (ROOT / "paper" / "isgt2026.log")
    if log.exists():
        text = log.read_text(errors="ignore")
        pages = re.search(r"Output written on \S+ \((\d+) pages", text)
        n = int(pages.group(1)) if pages else 0
        check("page count", PAGES_MIN <= n <= PAGES_MAX,
              f"{n} pages (allowed {PAGES_MIN}-{PAGES_MAX})")
        n_over = text.count("Overfull \\hbox")
        check("no overfull boxes", n_over == 0, f"{n_over} overfull hboxes")
        check("no undefined references", "undefined" not in text.lower()
              or "There were undefined references" not in text)

    audit_numbers()

    print()
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


def audit_numbers() -> None:
    """Recompute the headline claims from raw JSON and find them in the PDF.

    Deliberately independent of tables/numbers.tex. The macros guarantee the
    manuscript agrees with whatever the generator computed; this checks that the
    generator computed the right thing, by deriving each number a second time
    and confirming it survived into the compiled artefact.
    """
    import json
    import subprocess

    pdf = ROOT / "paper" / "isgt2026.pdf"
    if not pdf.exists():
        check("pdf present for number audit", False, "compile first")
        return
    text = " ".join(subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                                   capture_output=True, text=True).stdout.split())

    def J(p):
        return json.loads((ROOT / "results" / p).read_text())

    mv, lv = J("staleness_sweep_25ep.json"), J("staleness_kerber.json")
    mvme, lvme = J("model_error_case33bw.json"), J("model_error_kerber.json")
    tr = J("trace_kerber.json")
    cells = [(mv, ["6.0", "8.0", "10.0"]), (lv, ["1.0", "2.0", "3.0"])]

    rec = [d["cells"][z][s]["288"]["viol"] / d["cells"][z][s]["raw"]["viol"]
           for d, zs in cells for z in zs for s in d["cells"][z]]
    infeas = {d["cells"][z][s]["288"]["infeasible"]
              for d, zs in cells for z in zs for s in d["cells"][z]}
    ks = mvme["scale"]
    safe = [k for k in ks
            if all(d["cells"][s][str(k)]["viol"] == 0.0
                   for d in (mvme, lvme) for s in ("uncoordinated", "urgency"))]
    m, l = mvme["cells"]["uncoordinated"], lv["cells"]["1.0"]["uncoordinated"]

    check("recovery spans 12 cells", len(rec) == 12, f"{len(rec)}")
    check("infeasibility at tau=288 uniform", len(infeas) == 1, f"{sorted(infeas)}")
    check("LV never-refreshed equals unprojected",
          l["288"]["viol"] == l["raw"]["viol"])

    for name, val in [
        ("recovery low", f"{100 * min(rec):.1f}"),
        ("recovery high", f"{100 * max(rec):.1f}"),
        ("safe window low", f"{min(mvme['jacobian_ratio'][str(k)] for k in safe):.2f}"),
        ("safe window high", f"{max(mvme['jacobian_ratio'][str(k)] for k in safe):.2f}"),
        ("Jacobian span low", f"{min(mvme['jacobian_ratio'].values()):.2f}"),
        ("Jacobian span high", f"{max(mvme['jacobian_ratio'].values()):.2f}"),
        ("MV under-est. infeasibility", f"{100 * m['0.2']['infeasible']:.1f}"),
        ("MV under-est. freeze rate", f"{100 * m['0.2']['frozen']:.1f}"),
        ("LV stale violation rate", f"{l['288']['viol']:.4f}"),
        ("trace steps below band", str(sum(tr["runs"]["unprojected"]["violating"]))),
    ]:
        check(f"in PDF: {name} = {val}", val in text)


if __name__ == "__main__":
    raise SystemExit(main())
