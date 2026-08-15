# SmallGrants

An open index of US foundation giving, built from IRS Form 990-PF bulk filings.

## Why

The underlying information is already public. Every private foundation files a
Form 990-PF listing each grant it paid: recipient, address, purpose, and amount.
The IRS publishes these as bulk XML. The barrier to using them is tedium, not
secrecy.

**Who this is actually for.** Candid's Foundation Directory lists at $219+/month,
but that price is not what most small nonprofits pay. A registered 501(c)(3) with
under $1M in revenue can get free Candid Premium through the Go for Gold program
by earning a Gold Transparency Seal, and many public libraries offer free access
through Candid's Funding Information Network. If you are an incorporated
nonprofit, do that first. It is a better product than this one.

What those routes require is a 501(c)(3) and a maintained public profile. Student
groups, unincorporated volunteer groups, fiscally sponsored projects, mutual aid
groups, and individuals seeking scholarships or fellowships have none of that and
qualify for none of it. That is who this is for.

**What else exists.** [Grantmakers.io](https://www.grantmakers.io/) is free, open
source, well built, and already lets you search the same 990-PF data by foundation
name or by grantee name and location. If you can name a peer organization that
resembles yours, use it. This project differs in three specific ways, listed under
"How this differs" below, and not in the general claim of making 990 data
searchable. That was already done.

## What the data actually contains

Built and measured on 2026-08-04 from all 49 IRS bulk archives, filing years
2022–2026:

- **562,413** Form 990-PF filings
- **142,806** foundations, **8,388,280** grant records
- Median grant **$2,500**; **63.9% of all grants are $5,000 or less**
- **70.3%** of foundations filed that they accept no unsolicited requests
- 62.3% of purpose descriptions carry usable information

The small-money layer is abundant. It is simply invisible.

## Core idea

Match funders on **what they actually funded**, not on what they say they fund —
most small foundations say nothing at all. Where a grant's stated purpose is
boilerplate, the recipient's identity still encodes the cause area, recovered by
joining recipients to their NTEE codes.

The strongest filter is one the foundations hand over themselves: Part XV line 2
of the 990-PF, where 70% declare that they fund only preselected organizations.
Excluding them removes most of the noise before any ranking happens.

## How this differs

Three things, and it is worth being precise because the rest overlaps with tools
that already exist.

**You describe your work; you do not name a peer.** Existing 990 search tools
match on a grantee's name or location, which means you have to already know an
organization like yours that got funded. Here the query is a sentence about what
you do, embedded and matched against what each foundation actually funded, with
recipient NTEE codes filling in for the 37.7% of purpose fields that are
boilerplate.

**Size fit is scored, and mismatch is disqualifying.** A foundation whose largest
grant in five years was $6,835 is not a prospect for a $50,000 ask, however well
the cause matches. That comparison is made for every result.

**Every funder is reviewed against your specific ask, and told to you as
reasons.** This is the part nothing else does. Before you write anything, the
review reads the foundation's own filing and returns findings with severity and a
quotation: your ask exceeds their largest grant ever, their stated restrictions
name a state that is not yours, they have never funded an individual, they filed
that they accept no unsolicited requests. It is built to tell you **not** to
apply, with the filing text that says so. Nothing is inferred that the record
does not support, and where the record is too thin the review says that instead
of guessing.

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

## Deploying

The built database is 2.65 GB, most of it scaffolding the site never reads: raw
grant rows from before deduplication, the 1.98M-row IRS business master file, the
grantee keys used to compute openness. `package` writes a serving-only copy.

```
smallgrants package                     # -> data/dist, 566 MB + 170 MB embeddings
```

`Dockerfile` builds an image with CPU-only torch and the embedding model baked in,
so a running container never calls out to Hugging Face. It reads the corpus from
`/data`. Give it 1 GB of memory: the model needs about that resident, and a
512 MB box is killed on the first search in a way that looks like a corpus
failure rather than a memory one.

`fly.toml` is filled in for Fly.io:

```
fly launch --no-deploy
fly volumes create data --size 2
fly deploy
# then copy data/dist/* into the volume
```

Any host that runs a container with a 1 GB volume works the same way. Nothing in
the app assumes Fly.

## Knowing whether anyone used it

The site keeps its own usage log in SQLite, separate from the corpus, with no
third-party analytics and no cookies. It records what was searched for, how many
results came back, and which foundations were opened. It does not record IP
addresses, user agents, or anything typed into the review box. Visitors are
counted through a hash whose salt is regenerated nightly, so yesterday's hashes
cannot be matched to today's visitor.

```
smallgrants stats                       # searches, visitors, empty searches, funnel
```

Two of those numbers matter more than the visit count. **Searches that returned
nothing** shows the corpus failing people who did show up. **Visitors who
searched and then opened a funder** shows whether the results were worth reading.

One thing the log deliberately cannot tell you: whether a funder was new to the
person who found it. That has to be asked at the moment someone clicks through,
and it is the difference between claiming reach and claiming impact. The schema
has room for the answer whenever that question is worth adding.

## What did not survive contact with the data

The openness ratio — the share of grantees new each year — was the design's most
novel signal. Tested against the 70% of foundations that declare their own
status, it holds in the right direction and is overwhelmingly significant
(n=77,605, Welch t=33.6) but the effect is small (Cohen's d=0.286): foundations
that state they accept no unsolicited requests still replace a third of their
grantees annually. It was demoted from 0.10 to 0.05 weight and is labelled a weak
signal wherever it appears, rather than quietly shipped as if it were decisive.

Three adversarial reviewers then went at the code. They found, among others, a
critic that discarded its own record-derived disqualifiers in favour of whatever
the model returned; an individuals check that read "NO GRANTS TO INDIVIDUALS" as
evidence *of* grants to individuals (53% false positives); a geography score that
rewarded funders for being concentrated somewhere other than the user's state;
and roughly $6.7B of grant dollars double-counted because grant rows carried no
filing identity. All are fixed and pinned by regression tests. The full list,
including what the reviewers cleared with proof, is in `docs/validation.md`.

## Deliberate non-goals

No CRM. No donor management. **No mass email** — that is a legal and
deliverability trap, not a feature. US private foundations only in v1.
