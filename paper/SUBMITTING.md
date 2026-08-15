# Submitting to JOSS

`paper.md` and `paper.bib` are drafted to the Journal of Open Source Software
format. Read this before submitting, because acceptance is not certain and the
reason is worth understanding.

## Fill in first

- **ORCID.** `paper.md` carries a placeholder. Register at orcid.org, which takes
  a few minutes, and replace it. JOSS expects one.
- **Affiliation.** Confirm how you want to be listed.
- **Repository URL** in `CITATION.cff`, set to `jbtk-cell/smallgrants`. Change it
  if you publish under a different account or name.

## Where this may fail review

JOSS accepts research software, and asks two questions that this project answers
unevenly.

**Does it have an obvious research application?** Partly. The corpus is
defensible research infrastructure: philanthropy researchers need bulk grant data
and the licensed alternative cannot support reproducible work. The web
application on top of it is a practitioner tool, and reviewers may read the
project as an application with a dataset attached rather than as research
software. Lead with the corpus and the pipeline. The site is a demonstration of
the corpus, not the submission.

**Is it a substantial scholarly effort?** Yes on volume, and the validation work
is the strongest argument: a proposed signal was tested against a labelled set,
found weak, and demoted, with the measurement shipped. That is the part reviewers
are least likely to have seen before, and it is genuine scholarly practice rather
than a feature list.

The honest risk is a desk rejection on scope, before review. If that happens the
work is not wasted: the same paper fits a data or infrastructure venue, and the
Zenodo deposit already makes the corpus citable without any journal.

## JOSS checklist

Already satisfied:

- Open source under a recognized license (MIT)
- Automated tests (62, `pytest tests/`)
- Installation and usage documentation in the README
- Version control with substantive history

Add before submitting:

- **Community guidelines**: a short `CONTRIBUTING.md` covering how to report a
  problem, how to contribute, and how to seek support. JOSS checks for this
  explicitly.
- **A tagged release and archive.** Cut a version tag, connect the repository to
  Zenodo, then make a GitHub release so Zenodo mints the DOI. JOSS asks for that
  DOI in the submission form.

## Order of operations

1. Publish the repository.
2. Add `CONTRIBUTING.md`.
3. Connect Zenodo, tag `v1.0.0`, publish the release, record the DOI.
4. Submit at `joss.theoj.org/papers/new` with the repository URL and that DOI.

Steps 1 through 3 stand on their own. The corpus is citable after step 3 whatever
JOSS decides.
