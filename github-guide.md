# Maintaining a GitHub for PhD Applications

Written for your situation: BUET EEE graduate, active research, manuscripts in
preparation, applying to U.S. PhD programs.

---

## First: "upload all my project contents" is the wrong goal

I want to push back on the premise, because it's the difference between a GitHub that
helps you and one that hurts you.

A professor who clicks the GitHub link on your CV spends **about ninety seconds** there.
They are not browsing your work. They are answering one question: *does the research
claim on this CV have something real behind it?*

That means GitHub is **evidence**, not **storage**. Fifteen repos of course assignments
answer the question badly — they say "here is someone who completed a degree," which the
transcript already said. Three repos where a stranger could clone the code and reproduce
your thesis figure answer it well.

The rule: **three excellent repositories beat fifteen mediocre ones.** If a repo doesn't
support the story your CV tells, it should not be pinned, and possibly should not be public.

If you want a backup of everything, that's a legitimate need — but it's what **private
repos** are for. Public and private are different tools for different jobs. Use both.

---

## Before anything else: what you must NOT upload

This section is first because the downside is asymmetric. A weak GitHub costs you a little.
Publishing the wrong thing can damage your relationship with your supervisor, your
department's foundry agreements, or a paper you haven't submitted yet.

### 1. Foundry PDK files, models, and tech files — this is the big one for EEE

If your work touched Cadence, Synopsys, or any real process node, the **PDK is under NDA**.
Your university holds that agreement, usually through Europractice, a foundry university
program, or a direct arrangement. Publishing PDK files, SPICE model cards, `.lib`/`.tech`
files, or extracted parasitics from a proprietary node is a genuine NDA violation — and
it isn't your NDA to breach. It's your department's, and the consequences land on your
supervisor.

**Safe to publish:** your own schematics as images, testbench topology, your analysis
scripts, measured or simulated *results*, plots.
**Not safe:** anything that came out of the PDK directory, netlists with foundry device
models in them, or layout using foundry layers.

When in doubt, ask your supervisor. Always ask before publishing anything from a
university-licensed tool flow.

### 2. Anything tied to your manuscripts in preparation

You have papers in progress. **Ask your advisor before publishing any of that code or
data.** Three reasons, all real:

- Lab policy often forbids it pre-submission, and you may not have been told explicitly
- Publishing methodology before submission can enable scooping
- Some journals have preprint/disclosure rules worth checking first

The normal pattern in engineering is: code stays private until acceptance, then goes public
with the paper (often with a Zenodo DOI — see below). Nothing is lost by waiting, and you
can still *mention* the work on your CV.

### 3. BUET course assignment solutions

Publicly posting solutions to courses still being taught creates an academic-integrity
problem for the department, and it's traceable to you by name. It also doesn't help you —
graders' assignments demonstrate nothing a transcript doesn't.

If a course project became something substantial and original, that's different: rewrite
it as a standalone project, describe it as your own work, and make sure it isn't a
solution key for a current assignment.

### 4. Credentials — and remember git never forgets

API keys, tokens, `.env` files, license server addresses, institutional paths. Deleting a
secret in a later commit **does not remove it** — it stays in the history and stays
readable. If you commit a secret, the fix is to rotate the secret, not to delete the file.

### 5. Licensed software artifacts

Your MATLAB `.m` files are yours. MATLAB itself, toolbox binaries, license files, and
installer archives are not redistributable.

---

## The structure that actually works

### Profile README

A repo named exactly after your username (`Rifat137710/Rifat137710`) with a `README.md`
renders on your profile page. This is the first thing a visitor sees. Keep it to a short
paragraph: who you are, what you work on, what you're looking for. Not a wall of
animated badges and language-usage charts — those read as a student portfolio, which is
not the impression you want on a PhD application.

A starter version is in `templates/profile-README.md`.

### Pinned repositories — you get six, use fewer

Pinning is curation, and curation is the whole point. For you, a good six would be:

1. Undergraduate thesis code — *if cleared by your supervisor*
2. The competition project with the genuine novelty
3. A reproduction or reimplementation of a paper in your target area
4. A tool or library, however small, that someone else could use
5. Something demonstrating range (an FPGA/HDL project, a measurement automation script)
6. — leave empty rather than fill it with something weak

An empty sixth slot costs nothing. A weak sixth repo costs you the impression the other
five made.

### Repository naming

`emg-gesture-classification` tells a reader what it is. `Project_1`, `EEE_400_final`,
`my-code`, and `test2` tell a reader you weren't thinking about them. Lowercase,
hyphenated, descriptive.

---

## The README is the deliverable

This is the part most students get wrong, so it's worth being blunt: **nobody is going to
read your code.** A professor evaluating you reads the README and looks at one figure.
That's the whole interaction.

So a research repo README needs to answer, in this order:

1. **What is this?** One sentence a non-specialist in your subfield can follow.
2. **What did it produce?** The result. A number, a plot, a claim. Put the key figure
   directly in the README — GitHub renders images inline and it's the single highest-value
   thing you can add.
3. **How do I run it?** Exact commands. Assume the reader has your repo and nothing else.
4. **What do I need?** `requirements.txt`, `environment.yml`, MATLAB version, toolboxes.
5. **Status and license.** Is this finished? Can I use it?

A full template is in `templates/project-README.md`.

### Reproducibility signals researchers notice

These are cheap and they read as professional maturity:

- A pinned dependency file (`requirements.txt` with versions, not just package names)
- **One command** that regenerates the main result — `python run_experiment.py --config configs/main.yaml`
- A fixed random seed, stated in the README
- The output figure committed to the repo, so it's visible without running anything
- A `data/README.md` explaining where data came from, even when the data itself is too
  large or too restricted to include

The last one matters more than you'd expect. "The dataset is not included because it's
under a data use agreement; instructions to request it are here" reads as *someone who
understands research norms*. Silence reads as carelessness.

---

## Mechanics

### Setting up a repo

```bash
mkdir emg-gesture-classification && cd emg-gesture-classification
git init
# write README.md and .gitignore FIRST, before adding code
git add .
git commit -m "Initial commit: EMG classification pipeline"
git branch -M main
git remote add origin https://github.com/Rifat137710/emg-gesture-classification.git
git push -u origin main
```

### .gitignore before your first commit

Getting this right up front saves pain later, because removing a file from history is much
harder than never adding it. Start from GitHub's templates at
[github/gitignore](https://github.com/github/gitignore) — there are ready-made ones for
Python, MATLAB, and more.

Minimum for a research repo:

```gitignore
# Data — track the pipeline, not the payload
data/raw/
data/processed/
*.mat
*.h5
*.csv

# Secrets
.env
*.key

# Python
__pycache__/
*.pyc
.ipynb_checkpoints/
venv/

# LaTeX
*.aux
*.log
*.synctex.gz

# EDA / simulation junk
*.raw
*.log
simulation/
```

Commit **one** small representative sample file so the pipeline is runnable, and document
where the full dataset lives.

### Large files

Git handles text well and binaries badly. A repo bloated with `.mat` files is slow to clone
and unpleasant to work with.

- **Files over 50 MB** trigger a GitHub warning; **over 100 MB** are rejected outright.
- **Git LFS** exists for this, but the free allowance is small — reported around 1 GiB
  storage and 1 GiB/month bandwidth, though GitHub has revised these terms and I couldn't
  confirm the current figure. Check the docs before relying on it.
- **The better answer:** don't. Put large datasets on Zenodo, Google Drive, or an
  institutional store, and link to them from the README. Reviewers expect this; it's normal.

### Commits

You don't need elaborate discipline for solo research code. You do need commits that
aren't `update`, `fix`, `asdf`. Write what changed and why:

```
Add Butterworth bandpass preprocessing (20-450 Hz)
Fix off-by-one in sliding-window segmentation
Replace wavelet baseline with 1-D CNN; +6.1pp accuracy
```

Anyone reading your history — including you in six months — can follow that.

### Licensing

No license means **nobody can legally use your code**, which defeats the purpose of
publishing it. Add one:

- **MIT** — permissive, simple, the default for research code. Use this unless you have a reason not to.
- **Apache 2.0** — permissive plus an explicit patent grant. Worth considering for hardware-adjacent work.
- **GPL-3.0** — requires derivatives stay open. Use deliberately, not by accident.

GitHub adds one for you: **Add file → Create new file → type `LICENSE`** → a template
picker appears.

### Making code citable with a DOI

Once a paper of yours is accepted and the code goes public, connect the repo to
[Zenodo](https://zenodo.org). Link your GitHub account, flip the switch for that repo, and
every GitHub **release** gets archived with its own DOI. The first DOI is a "concept DOI"
that always resolves to the latest version.

This lets you cite your own code in the paper and lets others cite the exact version they
used. Add a `CITATION.cff` file to the repo and GitHub renders a "Cite this repository"
button automatically. It's a small thing that signals you understand how research
software works.

---

## Your realistic priority order

You're applying now, so don't disappear into GitHub for three weeks. In rough order of
return on time:

1. **Ask your supervisor** what you're permitted to publish. Do this first — it takes one
   conversation and it determines everything else.
2. **Pick your two or three strongest projects.** Not all of them. Two or three.
3. **Write a real README for each**, with the key figure embedded. This is where most of
   the value is, and it's a few hours of work.
4. **Add a LICENSE and a `.gitignore`** to each.
5. **Write the profile README.**
6. **Pin them, in the order that matches your CV's story.**
7. Everything else — CI badges, GitHub Pages, contribution graphs — is optional and mostly
   doesn't matter for this audience.

Then go back to the CV and statement of purpose, which carry far more weight.

---

## The link on your CV

Your CV header has a GitHub link. Two rules:

- **If the profile is thin, delete the link.** An empty or coursework-only GitHub is worse
  than no link. The link is an invitation to check, and a disappointed reader is a worse
  outcome than an incurious one. Same logic applies to the Google Scholar link if you have
  no publications yet.
- **Make it consistent with your CV.** If your CV's first Research Experience entry is about
  power electronics, your top pinned repo shouldn't be a web scraper. The professor is
  checking whether the story holds together.

---

## Sources

- [Git LFS billing — GitHub Docs](https://docs.github.com/billing/managing-billing-for-git-large-file-storage/about-billing-for-git-large-file-storage) (quota figures unconfirmed — see note above)
- [Making code citable with Zenodo and GitHub — Software Sustainability Institute](https://www.software.ac.uk/blog/making-code-citable-zenodo-and-github)
- [Making your project citable — CodeRefinery](https://coderefinery.github.io/github-without-command-line/doi/)
- [How to Add a Citation to Your Code — pyOpenSci](https://www.pyopensci.org/lessons/package-share-code/publish-share-code/cite-code.html)
- [github/gitignore — official .gitignore templates](https://github.com/github/gitignore)
