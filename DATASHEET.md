# Datasheet: SmallGrants foundation giving corpus

Following the structure of Gebru et al., *Datasheets for Datasets*. Every figure
here was measured against the built corpus.

## Motivation

Private foundation grant schedules are public but effectively unusable: the IRS
publishes them as raw XML inside dozens of zip archives, one file per filing.
This corpus parses them into two tables so that a grant-seeking organization can
ask which foundations have actually funded work like theirs, nearby, at their
size. It was built by one person as an independent project, with no funding.

## Composition

Each record is one grant paid by one private foundation in one tax year, taken
from Form 990-PF Part XV line 3a (`GrantOrContributionPdDurYrGrp`). Grants
*approved for future payment* are deliberately excluded, since they are not money
that moved.

| | |
|---|---|
| Grant records | 8,388,280 |
| Distinct foundations | 142,806 |
| 990-PF filings parsed | 562,413 |
| Filing years | 2022–2026 |
| Tax years represented | 2019–2025 |
| Median grant | $2,500 |
| Grants of $5,000 or less | 63.9% |

Per grant: foundation EIN and name, tax year, recipient name, recipient city,
state and ZIP, stated purpose, amount, and where resolvable the recipient's EIN
and NTEE code. Per foundation: location, assets, the Part XV line 2 declaration
of whether it accepts unsolicited requests, published application deadlines and
restrictions, grant size distribution, geographic concentration, and a grantee
turnover ratio.

No personal data was collected deliberately, but **the source filings contain
names of individuals**: 814,371 grants are recorded as going to a named person,
mostly scholarship and fellowship recipients. These names are published by the
IRS as filed. They are carried through unchanged and are not enriched, linked, or
cross-referenced against anything.

## Collection

Downloaded from `apps.irs.gov/pub/epostcard/990/xml/{year}/`, which is the
authoritative public source, and parsed directly from the archives. Nothing is
scraped, purchased, or contributed by users.

Five of the 49 archives use deflate64 compression, which Python's `zipfile`
cannot read and which libarchive misreports as a damaged archive. They hold
89,345 filings and 1,044,450 grants, about 12% of the corpus. Any pipeline that
trusts the error message loses them silently.

## Preprocessing

**Deduplication.** A foundation sometimes files twice for one tax year. Filings
are identified by IRS object ID and one winner is chosen deterministically by
amended flag, then filing timestamp, then grant count. Before this was fixed,
95,477 surplus rows inflated totals by roughly $6.7B.

**Entity resolution.** Recipients are free text with no EIN, matched by
normalized name and state against the IRS Business Master File (1,983,563 rows).

| Tier | Grants | Share |
|---|---:|---:|
| Matched on name and state | 3,941,142 | 47.0% |
| Organization typed into the person field | 258,319 | 3.1% |
| Grants to individuals | 814,371 | 9.7% |
| Unresolved | 3,374,448 | 40.2% |

A national name fallback was tried and removed: it produced 3.3% of matches and
97.6% of those attached an organization in a different state from the recipient's
own address.

## Uses

Suitable for funder prospecting, and for research on foundation giving patterns,
grant size distributions, and geographic concentration of philanthropy.

**Not suitable** for computing any foundation's total giving without accounting
for the 40.2% unresolved recipients, for claims about a named recipient's total
funding received, or for anything requiring current-year data. Filings lag the
tax year, often by more than a year.

## Limitations

- **40.2% of recipients are unidentified.** They appear under trading names,
  abbreviations and misspellings that name matching does not recover. A
  foundation whose giving looks narrow here may simply have unmatched grantees.
- **990-PF only.** Community foundations and operating foundations file Form 990
  and are absent entirely, as are public charities that regrant.
- **The filer decides which field a name goes in.** Organizations get typed into
  the person field and people into the business field, so any count of
  "grants to individuals" from the raw flag alone is wrong in both directions.
- **Stated purpose is boilerplate 37.7% of the time.**
- **A validated signal that is weaker than it looks.** Grantee turnover was
  proposed as a proxy for whether a foundation takes new applicants. Tested
  against the 70% of foundations that declare their own status, it points the
  right way and is significant (n = 77,605, Welch t = 33.6) but small
  (Cohen's d = 0.286). Foundations that state they accept no unsolicited requests
  still replace about a third of their grantees annually.

## Distribution and maintenance

Code under MIT. The underlying filings are US government works in the public
domain. Rebuilding from source takes a few hours on a laptop and is a single
documented command sequence, so the corpus can be regenerated for any year range
rather than depending on a hosted copy.
