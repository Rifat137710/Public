# Academic CV — U.S. PhD Applications (BUET EEE)

A ready-to-compile LaTeX CV built for your exact situation: fresh B.Sc. from BUET EEE,
active research, papers in preparation, and competition work with genuine technical novelty.

| File | What it is |
| --- | --- |
| `cv.tex` | The CV. Self-contained — compiles with plain `pdflatex`, no external class files. |
| `cv.pdf` | Compiled output, so you can see the layout before editing anything. |

---

## 1. Get it running in two minutes

**Overleaf (recommended — no install):**
1. Go to overleaf.com → **New Project** → **Blank Project**
2. Delete the default `main.tex`, upload `cv.tex`
3. Menu → Compiler → **pdfLaTeX**. Hit Recompile.

**Locally:** `pdflatex cv.tex` — run it **twice** so the "Page 1 of 2" footer resolves.

Only three lines need editing before anything else works — they're at the top of the file:

```latex
\newcommand{\myname}{Rifat Arafat}          % EXACTLY as printed in your passport
\newcommand{\myemail}{rifatarafat1020@gmail.com}
\newcommand{\myphone}{+880 1XXX-XXXXXX}
```

Use your **passport spelling**. If your CV says "Rifat Arafat" and your transcript says
"Md. Rifat Arafat," someone in a graduate office has to reconcile two documents by hand,
and international admissions is exactly where that goes wrong.

> **Every fact in the template is a blank** — `XX`, `3.XX/4.00`, `[Month Year]`. The
> structure and phrasing are real and ready to use; the numbers deliberately are not.
> Before you send it anywhere, search the PDF for `XX` and `[` — if either turns up a
> hit, it isn't finished.

---

## 2. Your specific situation: no publications yet

**This is normal and it is not a problem.** U.S. PhD admissions in engineering do not
expect publications from a B.Sc. applicant — engineering has substantially lower
publishing expectations at the application stage than the life sciences do. The
committee is assessing *research potential*, not output. Roughly: a strong thesis,
a supervisor who can vouch for you specifically, and evidence you can drive a technical
problem to a measured result will beat a thin co-authored paper every time.

So the load is carried by **Research Experience**, and that section deserves most of
your editing effort. Three entries described concretely beat eight one-liners.

**The bullet formula:** action verb + technical specifics + method/tool + measured outcome.

| Don't write | Write |
| --- | --- |
| "Worked on machine learning for biomedical signals." | "Built a 1-D CNN classifier for 8-channel surface EMG, reaching 94.2% accuracy across 22 subjects — 6.1 points above the wavelet-feature baseline." |
| "Familiar with Cadence." | "Designed a 2.4 GHz LNA in 65 nm CMOS (Cadence Spectre), achieving 18.3 dB gain at 2.1 dB NF under a 1.2 V supply." |
| "Assisted my supervisor with his research." | "Derived and implemented the small-signal model for [X]; results matched Spectre simulation within 4% across 11 bias points." |

Numbers are what make a bullet checkable. A committee reading your CV has no way to
verify "worked on" — it has every way to picture "94.2% across 22 subjects."

### Your competition work — this is a real asset, use it properly

Competitions with novel technical content belong in **Research Competitions and
Technical Projects**, and you should describe them the way you'd describe research,
not the way you'd describe an extracurricular. What they demonstrate that coursework
cannot: you can pick a problem, scope it, and deliver under time pressure — which is
most of what a first-year PhD student actually has to learn.

Three things to make explicit for each one:
- **What was novel.** Name the thing that had not been done before: the topology, the
  formulation, the constraint you removed. One sentence, plainly.
- **Placement *and* field size.** "1st of 220 teams" carries information; "Champion" doesn't.
- **What *you* personally built.** On a team entry, say which subsystem was yours. Committees
  discount team achievements precisely because they can't tell.

### "Manuscripts in Preparation" — handle honestly

The template includes this section because you have papers in progress, and listing them
is legitimate. Two rules:

- **Only list a manuscript that actually exists as a draft.** Not an idea, not a plan, not
  "we're going to write this up." Some faculty will ask about it in an interview, and
  "in preparation" for something unwritten is the kind of thing that ends an application.
- **One or two entries reads as momentum. Four or five reads as padding.** If nothing is
  genuinely drafted yet, delete the whole section — the *"manuscript in preparation for
  [venue]"* line inside Research Experience carries the same signal at lower risk.

The promotion path is: **In Preparation → Under Review → Publications**. A paper only
moves up when the status is genuinely true. When something gets accepted, it moves to a
`Publications` section placed at the *top*, above everything else.

---

## 3. Things that belong on a Bangladeshi CV and will hurt you here

This is the highest-value section of this document, because these are conventions you
have probably seen on every CV around you and they read very differently in the U.S.

**Delete all of these:**

- Photograph
- Date of birth / age
- Marital status
- Religion
- Father's or mother's name
- National ID or passport number
- Nationality (it's on your application already)
- Permanent village/district address (city + country is enough)
- Blood group, height, signature line
- "Career Objective" paragraph

These are standard on a Bangladeshi CV and are non-standard to actively unhelpful on a
U.S. academic one. Photos and personal details are not expected on U.S./UK CVs, and there's
a second reason beyond convention: U.S. universities run formal bias-mitigation policies in
admissions, and a CV carrying age, marital status, religion, and a photo creates a problem
for the committee that they solve most easily by not engaging with it. Including them
signals unfamiliarity with the norms in a process where "does this person know how U.S.
research works" is part of what's being judged.

**Also drop:** self-rated skill bars ("Python ▮▮▮▮▯ 8/10"), school-level certificates,
club memberships without a role, and "References available on request" — either list them
or don't.

**Keep, because they help you specifically:**

- **CGPA as `3.XX/4.00`.** Always with the scale. Never convert to a percentage.
- **Class rank, if you're roughly top 15%.** Write `Rank 12 of 180`. This matters more than
  you'd think: committees know BUET is extremely selective at *entry* but have no reliable
  intuition for what a given CGPA means once you're inside. Rank tells them directly.
  Below top ~15%, leave it off — no rank is neutral, a mediocre rank is not.
- **The full institution name** — "Bangladesh University of Engineering and Technology
  (BUET)" on first use. Well known in engineering circles, not universally.

---

## 4. Length, and what to cut

**Two pages.** The template compiles to three with every section switched on, because it
shows you all of them. You are meant to delete.

Cut in this order if you're over:
1. The third Research Experience entry, if it's thin
2. Professional Service and Memberships (IEEE student membership alone is not an achievement)
3. Test Scores — the portal collects these anyway; the CV row is a convenience, not a requirement
4. Course projects that don't support your stated research interest
5. Coursework list, down to 6–8 courses

Do **not** cut Research Experience bullets to save space. Cut whole weak sections instead.
A tight two-page CV with three deep research entries is a much stronger document than a
two-page CV that mentions eleven things.

---

## 5. Tailoring per application

`Research Interests` is the most-read block on page 1 — it's what a faculty member skims
to decide whether you belong in their lab. Rewrite it for each school. Not dishonestly:
you reorder and re-emphasize what's genuinely true.

Make it specific enough that a wrong-fit professor self-selects out. "Machine learning
and signal processing" describes ten thousand applicants. "Learned digital pre-distortion
for mmWave power amplifiers" describes you, and it tells the one professor who works on
that to keep reading.

Per school, a 10-minute pass:
- [ ] Rewrite `Research Interests` toward that department's actual strengths
- [ ] Reorder Research Experience so the most relevant entry is first
- [ ] Reorder `Selected Coursework` to front-load what's relevant
- [ ] Drop projects that don't support the story
- [ ] Filename: `Rifat_Arafat_CV.pdf` — never `cv_final_v3.pdf`

Keep **one master CV** with everything in it, and cut down per application. Don't
maintain twelve divergent files.

---

## 6. The CV in your cold emails to professors

You mentioned you're preparing for PhD emailing, so: the CV is the attachment, not the
message. A professor decides from your **email body** whether to open the PDF at all.

- Attach as **PDF**, named `Rifat_Arafat_CV.pdf`. Never `.tex`, never `.docx`.
- The email should name **one specific paper of theirs** and say something technically real
  about it — a limitation, an extension you'd want to try. This is the whole ballgame. Generic
  admiration ("I am deeply impressed by your outstanding work") is the signature of a mass mail
  and is filtered accordingly.
- Keep it to ~150 words with a clear ask ("Are you taking students for Fall 2027?").
- The CV backs up the claim your email makes. If the email says you work on power
  electronics, the CV's first Research Experience entry should be about power electronics.

Also: keep the Google Scholar / GitHub / website links in the header **only if they're
populated**. An empty Scholar profile or a GitHub with three forked repos is worse than
no link — it's an invitation to check, and then a disappointment.

---

## 7. Other templates worth knowing

You asked for the best templates, so here's an honest survey. The one in this folder is
tailored to you, but these are the real alternatives:

| Template | Link | Verdict |
| --- | --- | --- |
| **Awesome-CV** | [posquit0/Awesome-CV](https://github.com/posquit0/Awesome-CV) | The most widely used academic/professional LaTeX CV (28k+ stars). Excellent typography, modular sections. Needs **XeLaTeX** and bundled fonts (Roboto, Source Sans Pro). Publication lists are hand-written, not BibTeX-driven, unless you use the fork below. |
| **Awesome-PhD-CV** | [LimHyungTae/Awesome-PhD-CV](https://github.com/LimHyungTae/Awesome-PhD-CV) | A curated collection specifically for PhD applicants, with three formats and genuinely good commentary on what to emphasize. Its `research-cv/` variant adapts Awesome-CV with BibTeX-driven publication lists — the natural upgrade once you have papers. Worth reading even if you don't use the files. |
| **moderncv** | [CTAN](https://ctan.org/pkg/moderncv) | The old standard. Extremely safe, slightly dated look, on every TeX installation. Fine choice; nobody will hold it against you. |
| **Overleaf CV gallery** | [overleaf.com/gallery/tagged/cv](https://www.overleaf.com/gallery/tagged/cv) | Hundreds of templates. Filter hard — most are industry résumés, not academic CVs. |

**Templates to avoid for this purpose:** AltaCV, Deedy, Jake's Résumé, and the two-column
"designer" styles generally. They're good at what they're for — one-page industry
applications, ATS parsing, information density — but a PhD application is a different
document with different conventions. Two columns, sidebars, skill bars, and accent-colored
infographics read as *industry* to an academic committee, and they break down as soon as you
need to list publications properly. Single column, generous whitespace, conventional
sectioning. Boring is correct here.

---

## 8. Before you submit — checklist

- [ ] Search the PDF for `XX` and `[` — zero hits
- [ ] Name matches your passport exactly
- [ ] Every claim is defensible in an interview
- [ ] No photo, DOB, marital status, religion, parents' names, NID
- [ ] CGPA shown as `X.XX/4.00`, with the scale
- [ ] Two pages
- [ ] All three referees have **agreed** — ask before you list anyone
- [ ] Each referee has your CV *and* your statement of purpose (they write better letters with both)
- [ ] Read aloud once for grammar. Then have someone else read it. A typo on page 1 of a
      research CV does real damage — it's the one thing on the page that's unambiguously your fault.
- [ ] Exported as PDF, opened once on a different device to confirm the fonts embedded

---

## Sources

- [Do You Need Publications to Apply for a PhD Program? — Academic Positions](https://academicpositions.com/career-advice/do-you-need-publications-to-apply-for-a-phd-program)
- [CV for PhD Application: Complete Guide — DiscoverPhDs](https://www.discoverphds.com/advice/applying/cv-for-phd-application)
- [Academic CV for PhD Applications — JobSprout](https://www.jobsprout.ai/blog/cv-for-academic-applications)
- [CVs for postgraduate research applications — University of Warwick Careers](https://warwick.ac.uk/services/careers/help/pgr/applications/cvs)
- [Awesome-PhD-CV — curated templates and guidelines](https://github.com/LimHyungTae/Awesome-PhD-CV)
- [Awesome-CV — posquit0](https://github.com/posquit0/Awesome-CV)
- [Overleaf CV template gallery](https://www.overleaf.com/gallery/tagged/cv)
- [International Resume Guide: CV Format by Country](https://resumeoptimizerpro.com/blog/understanding-international-resumes)
