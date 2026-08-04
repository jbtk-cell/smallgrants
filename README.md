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

Measured on 2026-08-04 against one 71 MB archive (12,245 filings):

- 68,094 Form 990-PF filings indexed for 2026
- 74% of 990-PFs carry recipient-level grant records
- Median grant **$5,000**; **55.6% of all grants are $5,000 or less**
- 68.8% of purpose descriptions carry usable information
- ~750,000 grant records per year; 3–4M across five years

The small-money layer is abundant. It is simply invisible.

## Core idea

Match funders on **what they actually funded**, not on what they say they fund —
most small foundations say nothing at all. Where a grant's stated purpose is
boilerplate, the recipient's identity still encodes the cause area, recovered by
joining recipients to their NTEE codes.

## Status

Approved design, not yet implemented. See
[`docs/superpowers/specs/2026-08-04-smallgrants-design.md`](docs/superpowers/specs/2026-08-04-smallgrants-design.md).

## Deliberate non-goals

No CRM. No donor management. **No mass email** — that is a legal and
deliverability trap, not a feature. US private foundations only in v1.
