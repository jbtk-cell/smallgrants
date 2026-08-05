# SmallGrants — an open index of US foundation giving

**Status:** implemented; see [`docs/validation.md`](../../validation.md) for measured outcomes
**Date:** 2026-08-04
**Author:** Johnny Klaus

> The estimates in "Verified data foundation" below were taken from a single
> archive before the corpus was built. The built corpus is roughly twice as
> large: **562,413 filings, 142,806 foundations, 8,483,757 grant records**. The
> per-record structure, the grant-size distribution, and the boilerplate rate all
> held. The scale estimate did not, and the openness ratio did not survive
> validation intact — both are recorded in `docs/validation.md`.

## Problem

Roughly 1.3 million US nonprofits exist, and most are tiny: no development staff,
no CRM, no budget for funder research. The standard tool for finding foundations
is Candid's Foundation Directory at $219+/month. Student groups, all-volunteer
organizations, and individual researchers are priced out of it.

The information they need is already public. Every private foundation files IRS
Form 990-PF, and the grants schedule lists every grant it paid: recipient name,
recipient address, stated purpose, and exact amount. The IRS publishes these as
bulk XML.

Nobody mines it, because the data arrives as 142 zip archives of raw XML with no
index worth using. The barrier is not secrecy. It is tedium.

## Verified data foundation

All figures below were measured on 2026-08-04, not estimated.

**Source.** `https://apps.irs.gov/pub/epostcard/990/xml/{year}/` publishes an
annual index CSV plus monthly XML archives. The 2026 index is 43 MB and lists
**68,094 Form 990-PF filings**. The legacy AWS S3 mirror
(`s3://irs-form-990`) stopped updating on 2021-12-31 and must not be relied on.

**One archive, measured.** `2026_TEOS_XML_01A.zip` is 71 MB and expands to
12,245 filings, of which 1,057 are 990-PF. **786 of those (74%) contain
recipient-level grant records**, totalling 11,670 grants.

**Record structure**, confirmed on a real filing (John L. McHugh Foundation, MA,
48 grants):

```xml
<GrantOrContributionPdDurYrGrp>
  <RecipientBusinessName><BusinessNameLine1Txt>ALS ONE</BusinessNameLine1Txt></RecipientBusinessName>
  <RecipientUSAddress>
    <AddressLine1Txt>8 INDUSTRIAL WAY</AddressLine1Txt>
    <CityNm>WHITMAN</CityNm>
    <StateAbbreviationCd>MA</StateAbbreviationCd>
    <ZIPCd>02380</ZIPCd>
  </RecipientUSAddress>
  <RecipientRelationshipTxt>NONE</RecipientRelationshipTxt>
  <RecipientFoundationStatusTxt>PUBLIC CHARITY</RecipientFoundationStatusTxt>
  <GrantOrContributionPurposeTxt>UNRESTRICTED GRANT</GrantOrContributionPurposeTxt>
  <Amt>2000</Amt>
</GrantOrContributionPdDurYrGrp>
```

**Grant sizes.** Median $5,000; mean $35,509 (right-skewed by large outliers).
**55.6% of all grants are $5,000 or less. 70.8% are $10,000 or less.** The
small-money layer is abundant, not marginal. A student group seeking $3,000 is
asking for an ordinary amount.

**Purpose text quality.** 2,677 distinct strings. **68.8% carry usable
information; 31.2% are boilerplate** ("GENERAL SUPPORT" alone is 10.2%,
"CHARITABLE" 3.7%, "UNRESTRICTED" 2.8%). Semantic matching is viable but must
degrade gracefully on the boilerplate third.

**Scale.** Extrapolating from the measured batch: roughly **750,000 grant
records per year, 3–4 million across five years**. This fits comfortably in
DuckDB on a laptop. No distributed compute, no cloud bill.

**What ProPublica's API does and does not give.** The Nonprofit Explorer API
(`projects.propublica.org/nonprofits/api/v2/`) is free and needs no key. It
returns organization metadata and aggregate financials, including `contrpdpbks`
(total grants paid). It does **not** return recipient-level grants, and its
`download-xml` endpoint returns 403. It is useful for organization lookup and
validation, not as the primary source.

## Core insight

Do not match on what a foundation says it funds. Most small foundations publish
no mission statement, no website, and no guidelines. Match on **what it actually
funded** — the revealed preference in its grant history.

A foundation that gave $2,500 to three environmental education groups in New
Haven County is a materially better lead than one whose stated mission contains
the word "education."

### The boilerplate solution

When purpose text is uninformative, the **recipient's identity still encodes the
cause area**. Joining each grant recipient to the IRS exempt-organization master
file by EIN and name yields their NTEE code. A foundation's cause profile is then
the distribution of its grantees' NTEE codes — robust even when every purpose
field in its filing reads "GENERAL SUPPORT."

Purpose text becomes a secondary signal that sharpens matches. NTEE-derived cause
profile is the load-bearing one. This is the difference between a system that
demos well and one that works on the real 31% boilerplate.

## Architecture

Four stages, each independently testable, each with a defined input and output.

### ingest

Fetches the annual index CSVs and monthly XML archives from irs.gov. Maintains a
processed-archive manifest so reruns are incremental rather than full
re-downloads.

- **Input:** target years
- **Output:** raw archives on disk + manifest
- **Depends on:** irs.gov availability only

### parse

Converts 990-PF XML into normalized tabular records.

- **Input:** raw archives
- **Output:** two tables — `foundations` (EIN, name, address, tax year, total
  assets, total grants paid, filing object ID) and `grants` (one row per grant:
  foundation EIN, tax year, recipient name, recipient address, recipient
  relationship, recipient foundation status, purpose text, amount)
- **Depends on:** ingest

Filings without a grants schedule (26% of 990-PFs, measured) are recorded in
`foundations` with zero grant rows, not dropped — absence is itself information.

### enrich

- Entity resolution on recipient names, so `ALS ONE`, `ALS One Inc`, and
  `ALS-One` collapse to one entity
- Join resolved recipients to the IRS exempt-organization master file for NTEE
  codes
- Geocode recipient addresses to county

- **Input:** parsed tables
- **Output:** `grants` gains `recipient_entity_id`, `recipient_ntee`,
  `recipient_county`
- **Depends on:** parse

Unresolved recipients keep their raw name and a null entity ID. Coverage rate is
reported, not hidden.

### derive

Computes per-foundation signals across all available years.

- **Geographic footprint** — distribution of grantee counties/states
- **Grant-size distribution** — min, median, max, count
- **Cause profile** — NTEE distribution of grantees, plus embeddings of
  informative purpose text
- **Openness ratio** — share of a year's grantees not present in prior years

- **Input:** enriched tables
- **Output:** `foundation_signals` table
- **Depends on:** enrich, and at least three tax years of history

**Published artifact:** the enriched dataset plus `foundation_signals`, released
as Parquet with a documented schema and a data dictionary.

## Matching and ranking

A user supplies a project description, a location, and an amount sought.
Ranking is explicit and auditable — not a black-box score.

| Signal | Role |
|---|---|
| Geographic overlap with grantee footprint | Hard filter; does most of the work |
| Size fit against the foundation's typical range | Hard filter |
| Cause similarity (NTEE profile + purpose embeddings) | Ranking |
| Openness ratio | Ranking; demotes closed foundations |

Every result **cites actual prior grants as evidence**: "gave $2,500 to New Haven
Land Trust in 2024, $3,000 to Common Ground in 2023." The user evaluates the
funder from observed behavior, not from a similarity number they cannot audit.

Where cause similarity is unavailable (recipient unresolved and purpose text
boilerplate), the result is still returned, ranked on geography and size alone,
and **labeled as such**. Silent degradation is a defect.

## Where AI is used

**Used for:** embedding purpose text and user project descriptions; entity
resolution on messy recipient names; drafting a first-contact letter grounded in
a specific foundation's real grant history.

**Not used for:** producing the ranking (explicit scoring, as above); deciding
which organizations deserve funding; generating anything transmitted without the
user reading it.

BBB Give.org found that 55% of donors say they would be discouraged by charity
appeals not verified by a human, rising to 70% among households above $200,000.
Every generated draft is therefore a starting point the user must edit, and the
interface states this plainly. NIH policy NOT-OD-25-132 (effective 2025-09-25)
treats applications substantially developed by AI as non-original; the drafting
feature must not encourage users toward that boundary.

## Non-goals

- No CRM or donor-management features
- **No mass email.** Gmail and Yahoo bulk-sender rules require SPF/DKIM/DMARC
  alignment, one-click unsubscribe, and a spam-complaint rate under 0.3%; cold
  campaigns routinely exceed that. This is a legal and deliverability trap, not
  a feature.
- 990-PF only in v1. Public-charity grantmaking (Form 990 Schedule I) is v2.
- US only
- No wealth screening of individuals

## Honesty requirements

**Unsolicited applications.** Many small foundations accept none, and the 990
never records this. The openness ratio is a proxy, not a fact. It must be
displayed as a signal with its limits stated. A tool that sends users toward
unreachable funders reproduces the exact harm it claims to fix.

**Stale data.** Filings lag the tax year, often by more than a year. Every
foundation record displays its most recent filing year.

**Coverage gaps.** Entity-resolution and NTEE-join coverage rates are published
alongside the dataset.

## Risks and open questions

1. ~~**Openness ratio is unvalidated.**~~ **RESOLVED — tested, demoted.** Measured
   against the 70% of foundations that declare their own status on Part XV line 2
   (n=84,328): direction correct, Welch t=43.93, but Cohen's d=0.355. Foundations
   that declare they accept no unsolicited requests still replace a third of their
   grantees each year, so turnover cannot be trusted as a reachability signal on
   its own. Weight cut from 0.10 to 0.05, labelled "weak signal" everywhere it is
   shown, and the declared flag remains the primary filter. Full numbers in
   [`docs/validation.md`](../../validation.md).
2. **Entity-resolution quality is unmeasured.** Recipient names are free text
   with no EIN. If resolution accuracy is poor, NTEE-derived cause profiles
   degrade, and the boilerplate solution weakens with them.
3. **Filing lag** may make recent-behavior signals less useful than assumed.
4. **Sustainability.** An open tool that real organizations depend on creates an
   obligation beyond the author's interest in it. Publishing the dataset first
   means the contribution survives even if the application is retired.

## Success criteria

- The dataset reproduces from raw IRS archives with a single documented command
- Entity-resolution and NTEE-join coverage rates are measured and published
- For a held-out set of known foundation/grantee pairs, the true funder appears
  in the top 20 results for a description of what it actually funded
- At least one organization outside the author's own projects uses it to
  identify a funder they had not previously known about

## Build order

1. `ingest` + `parse` over a single year; validate record counts against the
   IRS index
2. Extend to five years; measure scale against the 750K/year estimate
3. `enrich`; measure and publish resolution coverage
4. `derive`; **validate the openness ratio before building on it**
5. Publish the dataset with its data dictionary
6. Matching and ranking, evaluated against the held-out criterion above
7. Web front end
8. Grounded drafting, last and optional
