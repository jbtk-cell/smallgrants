---
title: SmallGrants
emoji: 📒
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Find US foundations that have funded work like yours
---

# SmallGrants

An open index of US foundation giving, built from IRS Form 990-PF bulk filings.
8,388,280 grants paid by 142,806 private foundations.

Source and full validation record: https://github.com/jbtk-cell/smallgrants

## Space configuration

Set these under Settings.

**Variables**

| Name | Value |
|---|---|
| `SMALLGRANTS_SITE_URL` | `https://<owner>-smallgrants.hf.space` |
| `SMALLGRANTS_CORPUS_REPO` | the Dataset repo holding the packaged corpus |
| `SMALLGRANTS_USAGE_REPO` | a **private** Dataset repo for the usage log |
| `SMALLGRANTS_USAGE_DIR` | `/home/user/data/usage` |
| `SMALLGRANTS_TRUST_PROXY` | `1` |

**Secrets**

| Name | Value |
|---|---|
| `HF_TOKEN` | a write token, so the usage log can be committed back |

`SMALLGRANTS_SITE_URL` is what turns robots.txt from `Disallow: /` into an
invitation, and points canonicals, the sitemap and the share image at the real
host. Until it is set the Space runs but asks not to be indexed.

A free Space has no persistent disk. The usage log is mirrored to an append-only
journal and committed to `SMALLGRANTS_USAGE_REPO` every ten minutes; the database
is rebuilt from that journal after a restart. Without `HF_TOKEN` and a usage repo
the site still works, but every restart erases the record of who used it.
