# Validation results

Every figure here was measured against the built corpus, not estimated.
Reproduce with `smallgrants validate` and the queries noted below.

## Corpus

Built from all 49 IRS Form 990-PF bulk archives for filing years 2022–2026.

| Measure | Value |
|---|---|
| 990-PF filings | 562,413 |
| Distinct foundations | 142,806 |
| Grant records | 8,483,757 |
| Tax years covered | 7 |
| Foundations with a grant schedule | 110,917 |
| Foundations declaring no unsolicited requests | 100,445 (70.3%) |
| Foundations publishing application instructions | 31,751 (22.2%) |

Five of the 49 archives are compressed with deflate64, which Python's `zipfile`
cannot decode. They hold 89,345 filings and 1,044,450 grants — about 12% of the
corpus — and are inflated directly rather than skipped.

## Entity resolution

Grant recipients are free text with no EIN, so they are matched by normalized
name against the IRS Exempt Organization Business Master File.

| Tier | Grants | Share |
|---|---:|---:|
| Matched on name + state | 3,990,840 | 47.0% |
| Matched on name, nationally unique | 279,732 | 3.3% |
| Grants to individuals (not in the BMF by design) | 1,082,970 | 12.8% |
| Unresolved | 3,130,215 | 36.9% |

**57.7% of organization-directed grants resolve to an EIN. 45.7% of all grants
carry an NTEE code.** The unresolved remainder is the single largest known
weakness: recipients appear under trading names, abbreviations, and misspellings
that name matching does not recover.

## The openness ratio — validated, and weaker than designed

The openness ratio is the share of a foundation's grantees each year that it had
not funded in any prior year. It was proposed as a behavioural proxy for "does
this foundation take on new grantees", because most foundations publish nothing
about whether they accept applications.

It can be tested, because 70% of foundations **declare** the answer on Part XV
line 2 of their own filing. That declaration is the label; the ratio is the
prediction.

Restricted to foundations with at least 3 observed grant years and at least 5
grants (n = 84,328):

| Group | n | Mean openness |
|---|---:|---:|
| Declared closed to unsolicited requests | 63,791 | 0.334 |
| Did not declare closed | 20,537 | 0.426 |
| **Difference** | | **+0.092** |

Welch t = 43.93. Cohen's d = **0.355**.

**Verdict: real, but weak.** The direction is the one the proxy requires and the
result is overwhelmingly significant at this sample size, but the effect is
small. The decisive fact is that foundations which state plainly that they accept
no unsolicited requests still replace **a third of their grantees every year**.
Grantee turnover therefore does not distinguish reachable foundations from closed
ones well enough to be trusted on its own.

Consequences, applied:

- Openness weight in ranking reduced from 0.10 to 0.05; the freed weight moved to
  geography, which the data supports far better.
- Both the results list and the foundation page label it "weak signal".
- The declared flag — a fact the foundation filed, not an inference — remains the
  primary reachability filter and excludes ~70% of foundations by default.

This is the outcome the design document required be tested before shipping. The
signal was not dropped, because it does carry information; it was demoted to what
the evidence supports.

## Search behaviour

A query for a student-run environmental monitoring project in Connecticut seeking
$3,000 returns The Rockfall Foundation (Middletown, CT) first. Its three most
recent grants are $4,000 to the Town of Portland, $3,500 to the Connecticut Forest
& Park Association, and $3,500 to the East Haddam Land Trust, each recorded with
the purpose ENVIRONMENTAL. It publishes a submission deadline.

The same foundation, asked for $500,000 from Texas, is refused: the ask exceeds
its largest recorded grant of $4,000 (disqualifying) and 100% of its giving is in
Connecticut (serious). Both findings are produced without any model call.

## Known limitations

- **36.9% of grants have an unresolved recipient**, so cause profiles are built
  from a partial view of what a foundation funded.
- Filings lag the tax year, often by more than a year. Every foundation displays
  its most recent filing year.
- Purpose text is boilerplate in about a third of records; cause matching leans on
  recipient NTEE codes for those.
- 990-PF only. Public charities that make grants (Form 990 Schedule I) are absent.
