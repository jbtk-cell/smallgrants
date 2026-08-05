# Validation results

Every figure here was measured against the built corpus, not estimated.
Reproduce with `smallgrants validate` and the queries noted below.

## Corpus

Built from all 49 IRS Form 990-PF bulk archives for filing years 2022–2026.

| Measure | Value |
|---|---|
| 990-PF filings | 562,413 |
| Distinct foundations | 142,806 |
| Grant records | 8,388,280 |
| Tax years covered | 7 |
| Foundations with a grant schedule | 110,922 |
| Foundations declaring no unsolicited requests | 100,448 (70.3%) |
| Foundations publishing application instructions | 31,747 (22.2%) |

Five of the 49 archives are compressed with deflate64, which Python's `zipfile`
cannot decode and which libarchive misreports as a damaged archive. They hold
89,345 filings and 1,044,450 grants — about 12% of the corpus — and are inflated
directly rather than skipped.

### Duplicate filings

A foundation sometimes files twice for one tax year. Grant rows carried no filing
identity, so both filings' schedules pooled together and the statement meant to
drop the loser matched **zero** rows: 95,477 surplus grant rows and roughly
**$6.7B of double-counted grant dollars**, with individual foundations reporting
double their actual giving (McKnight 2021: $292.7M recorded against $106.3M
filed). Filings are now identified by IRS object_id, and the winner is chosen
deterministically — 81% of duplicate pairs tie on grant count, so the previous
ordering picked arbitrarily and a foundation's declared status could change
between rebuilds.

## Entity resolution

Grant recipients are free text with no EIN, so they are matched by normalized
name against the IRS Exempt Organization Business Master File (1,983,563 rows).

| Tier | Grants | Share |
|---|---:|---:|
| Matched on name + state | 3,941,142 | 47.0% |
| Organization typed into the person field, recovered | 258,319 | 3.1% |
| Grants to individuals (not in the BMF by design) | 814,371 | 9.7% |
| Unresolved | 3,374,448 | 40.2% |

**55.4% of organization-directed grants resolve to an EIN. 42.6% of all grants
carry an NTEE code.**

Two corrections lowered these figures and raised their accuracy:

- **The national name fallback was removed.** It supplied 3.3% of matches, and
  97.6% of them attached an organization whose BMF state differed from the
  recipient's own address. The large charity is filed under a decorated name
  while a small unrelated organization holds the bare one, so `PLANNED
  PARENTHOOD` resolved to a single San Antonio organization across 5,175 grants
  and $64M in 46 states. Global name uniqueness turned out to be evidence of
  obscurity, not of identity.
- **Organizations filed as people are recovered.** 258,319 grants named an
  organization in `RecipientPersonNm` (`PLANNED PARENTHOOD`, `WOUNDED WARRIOR
  PROJECT`, `AMERICAN HEART ASSOCIATION`). They were previously counted as grants
  to individuals, which corrupted every foundation's individual share and caused
  the critic to tell organizations not to apply.

Unresolved recipients remain the largest known weakness: they appear under
trading names, abbreviations, and misspellings that name matching does not
recover.

## The openness ratio — validated, and weaker than designed

The openness ratio is the share of a foundation's grantees each year that it had
not funded in any prior year. It was proposed as a behavioural proxy for "does
this foundation take on new grantees", because most foundations publish nothing
about whether they accept applications.

It can be tested, because 70% of foundations **declare** the answer on Part XV
line 2 of their own filing. That declaration is the label; the ratio is the
prediction.

Restricted to foundations with at least 3 observed grant years and at least 5
grants (n = 77,605):

| Group | n | Mean openness |
|---|---:|---:|
| Declared closed to unsolicited requests | 59,952 | 0.324 |
| Did not declare closed | 17,653 | 0.395 |
| **Difference** | | **+0.071** |

Welch t = 33.61. Cohen's d = **0.286**.

**Verdict: real, but weak.** The direction is the one the proxy requires and the
result is not noise at this sample size, but the effect is small. The decisive
fact is that foundations which state plainly that they accept no unsolicited
requests still replace **a third of their grantees every year**.

An earlier measurement put d at 0.355. That figure was inflated: grants to
individuals were included, which made the ratio partly a scholarship-fund
detector — a fund paying a fresh cohort of students each year scores near 1.0,
and the top 500 foundations by openness averaged 65% individual grants against a
corpus average of 19%. Counting organizations only, which is the question the
signal exists to answer, the effect drops to 0.286.

Consequences, applied:

- Openness weight in ranking reduced from 0.10 to 0.05; the freed weight moved to
  geography, which the data supports far better.
- Unknown openness previously mapped to 0.5 and was then doubled to 1.0, giving
  the 17% of foundations with no openness data the **maximum** sub-score. It now
  scores below the corpus median.
- Both the results list and the foundation page label it "weak signal".
- The declared flag — a fact the foundation filed, not an inference — remains the
  primary reachability filter and excludes ~70% of foundations by default.

The design document required this be tested before anything was built on it. The
signal was not dropped, because it does carry information; it was demoted twice
to what the evidence supports.

## Search behaviour

A query for a student-run environmental monitoring project in Connecticut seeking
$3,000 returns The Rockfall Foundation (Middletown, CT) first. Its three most
recent grants are $4,000 to the Town of Portland, $3,500 to the Connecticut Forest
& Park Association, and $3,500 to the East Haddam Land Trust, each recorded with
the purpose ENVIRONMENTAL. It publishes a submission deadline.

The same foundation, asked for $500,000 from Texas, is refused: the ask exceeds
its largest recorded grant of $4,000 (disqualifying) and 100% of its giving is in
Connecticut (serious). Both findings are produced without any model call.

## Defects found by adversarial review

Three reviewers were run against the pipeline, the ranking and agents, and the
web layer. Everything below was measured, not speculated, and every item is
fixed.

**Honesty**
- The critic passed its record-derived findings to the model as context and then
  returned the model's list *instead of* its own. A model returning an empty list
  turned a foundation that had filed "no unsolicited requests" into "a strong
  fit; send it". Rule findings are now a floor the model can only add to.
- The individuals check matched the bare word, so `NO GRANTS TO INDIVIDUALS` read
  as evidence *of* grants to individuals. **53% of the disqualifying flags it
  produced were foundations that give individuals nothing at all.**
- An individual applying to a foundation whose filing refuses individuals got a
  clean bill of health — the converse check did not exist.
- The geography check compared a two-letter code against spelled-out state names:
  `tx` is not inside `state of texas` (Texas applicants warned off Texas-only
  funders, 152 of 291 cases) while `in` is inside `in the state of oregon`
  (Indiana applicants never warned).

**Ranking**
- Geography scored the foundation's concentration in *its own* top state, so a
  funder with 1 New York grant out of 162 and 91% of its giving in Tennessee
  outranked one with 34 of 45 in New York — and placed first with no caveats.
- Foundations with a single grant on record presented that one row as a "typical
  grant" with a perfect size-fit score and no caveat.
- Published score components did not sum to the published score.

**Security and robustness**
- DuckDB exception text was rendered to anonymous visitors, exposing the OS
  username, the absolute interpreter path, the process id, the database path and
  sometimes the table schema. This was reachable during any rebuild, because the
  write lock made every read fail.
- `str.isdigit()` accepts characters `int()` rejects, so `?amount=²` and a
  5,000-digit number were unauthenticated 500s.
- `bool("false")` is `True`, so `include_closed=false` surfaced exactly the
  foundations the user asked to exclude.
- The critique endpoint was an unauthenticated, unrate-limited paid model call
  accepting a 1 MB project field.
- There was no index in the corpus; each search issued 26 full scans of an 8M-row
  table.

**Cleared with proof:** SQL injection (every user value is bound; probes
including `state=CT' OR 1=1--` behave correctly), XSS (Jinja2 autoescaping
verified on across all templates, end-to-end against a corpus poisoned with
`<script>` in six fields), path traversal and SSRF in ingest, and unbounded
result-set DoS.

## Known limitations

- **40.2% of grants have an unresolved recipient**, so cause profiles are built
  from a partial view of what a foundation funded.
- Filings lag the tax year, often by more than a year. Every foundation displays
  its most recent filing year.
- Purpose text is boilerplate in about a third of records; cause matching leans on
  recipient NTEE codes for those.
- 990-PF only. Public charities that make grants (Form 990 Schedule I) are absent.
- DuckDB allows a single writer, so the site is unavailable while a rebuild runs.
