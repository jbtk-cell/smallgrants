# SmallGrants

An open index of US foundation giving, built from IRS Form 990-PF bulk filings.

## Why

Most US nonprofits are tiny — no development staff, no CRM, no budget for funder
research. The standard tool, Candid's Foundation Directory, costs $219+/month.
Student groups and all-volunteer organizations are priced out.

The underlying information is already public. Every private foundation files a
Form 990-PF listing each grant it paid: recipient, address, purpose, and amount.
The IRS publishes these as bulk XML. Almost nobody uses them, because the data
arrives as 142 zip archives of raw XML. The barrier is tedium, not secrecy.

## What the data actually contains

Built and measured on 2026-08-04 from all 49 IRS bulk archives, filing years
2022–2026:

- **562,413** Form 990-PF filings
- **142,806** foundations, **8,483,757** grant records
- Median grant **$5,000**; **55.6% of all grants are $5,000 or less**
- **70.3%** of foundations filed that they accept no unsolicited requests
- 68.8% of purpose descriptions carry usable information

The small-money layer is abundant. It is simply invisible.

## Core idea

Match funders on **what they actually funded**, not on what they say they fund —
most small foundations say nothing at all. Where a grant's stated purpose is
boilerplate, the recipient's identity still encodes the cause area, recovered by
joining recipients to their NTEE codes.

The strongest filter is one the foundations hand over themselves: Part XV line 2
of the 990-PF, where 70% declare that they fund only preselected organizations.
Excluding them removes most of the noise before any ranking happens.

## Status

Working. Corpus built, pipeline reproducible end to end, web app running locally.

- Design: [`docs/superpowers/specs/2026-08-04-smallgrants-design.md`](docs/superpowers/specs/2026-08-04-smallgrants-design.md)
- Measured results, including what failed validation: [`docs/validation.md`](docs/validation.md)

```
smallgrants ingest --years 2022-2026    # download + parse (49 archives, ~27 GB streamed)
smallgrants load                        # -> DuckDB
smallgrants enrich                      # entity resolution + NTEE
smallgrants derive                      # per-foundation signals
smallgrants validate                    # test the openness ratio against declared status
smallgrants embed                       # local sentence-transformers, no API key
smallgrants search "..." --state CT --amount 3000
smallgrants serve                       # http://127.0.0.1:8000
```

## What did not survive contact with the data

The openness ratio — the share of grantees new each year — was the design's most
novel signal. Tested against the 70% of foundations that declare their own
status, it holds in the right direction and is overwhelmingly significant
(n=84,328, Welch t=43.9) but the effect is small (Cohen's d=0.355): foundations
that state they accept no unsolicited requests still replace a third of their
grantees annually. It was demoted from 0.10 to 0.05 weight and is labelled a weak
signal wherever it appears, rather than quietly shipped as if it were decisive.

## Deliberate non-goals

No CRM. No donor management. **No mass email** — that is a legal and
deliverability trap, not a feature. US private foundations only in v1.
