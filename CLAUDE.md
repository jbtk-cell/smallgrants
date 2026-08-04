# SmallGrants — instructions for AI agents

Read `docs/superpowers/specs/2026-08-04-smallgrants-design.md` before doing
anything. It is the approved design and it is authoritative.

## Ground rules

**Measure, do not estimate.** Every quantitative claim in the spec was measured
against real IRS data on 2026-08-04. Keep that standard. If you assert a
coverage rate, a record count, or a match quality, produce the command that
generated it.

**The data source is irs.gov.** `https://apps.irs.gov/pub/epostcard/990/xml/`.
The legacy AWS mirror (`s3://irs-form-990`) stopped updating 2021-12-31 — do not
use it. ProPublica's Nonprofit Explorer API is useful for organization lookup and
validation but does not expose recipient-level grants.

**Degrade loudly.** 31% of grant purpose text is boilerplate and some recipients
will not resolve. When a signal is unavailable, say so in the output. Silent
degradation is a defect, not a fallback.

**Validate the openness ratio before building on it.** It is the most novel
signal in the design and the least verified. If grantee turnover turns out not to
predict whether a foundation responds to new applicants, drop it.

## Hard constraints

- No mass email, ever. Not a feature, not a helper, not a stretch goal.
- No wealth screening of individuals.
- AI drafts are starting points a human edits. Never imply otherwise in the UI.
- Publish coverage gaps and data staleness alongside results, not in a footnote.

## Style

Plain text. No emojis in code, commits, or documentation.
