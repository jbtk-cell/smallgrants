---
title: 'SmallGrants: a reproducible corpus of US foundation giving from IRS Form 990-PF filings'
tags:
  - Python
  - philanthropy
  - nonprofit
  - open data
  - entity resolution
  - information retrieval
authors:
  - name: Johnny Klaus
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Johns Hopkins University, United States
    index: 1
date: 15 August 2026
bibliography: paper.bib
---

# Summary

Every private foundation in the United States files a Form 990-PF each year, and
Part XV of that form lists every grant it paid: recipient, location, stated
purpose, and amount. The IRS publishes these filings as bulk XML [@irs990xml].
The data is therefore public, complete, and almost unused, because it arrives as
dozens of zip archives holding one XML document per filing, with element names
that change between tax years.

SmallGrants is a pipeline that turns those archives into a queryable corpus of
8,388,280 grant records paid by 142,806 foundations over filing years 2022 to
2026, together with a web application built on top of it. The pipeline downloads
and parses the archives, deduplicates filings, resolves grant recipients against
the IRS Business Master File [@irsbmf] to recover activity codes, derives
per-foundation signals, and embeds each foundation's giving history so that
funders can be retrieved from a prose description of a project rather than from a
keyword.

Two properties distinguish the corpus from a naive parse. Filings are identified
by IRS object ID and deduplicated deterministically, because foundations
sometimes file twice for a tax year; before this was handled, 95,477 surplus
rows inflated grant totals by roughly $6.7 billion. Recipient identity is treated
as uncertain rather than assumed: 40.2% of recipients cannot be matched, and the
software reports that share rather than presenting partial coverage as complete.

# Statement of need

Research on foundation giving, and practical grant-seeking by small
organizations, both depend on knowing which funders have supported which
recipients. The commercial source, Candid's Foundation Directory [@candidfdo],
is licensed rather than open, which makes it unsuitable as a basis for
reproducible analysis even where an institution has access. Existing free tools
built on the same IRS data, notably Grantmakers.io [@grantmakersio], provide
lookup by foundation name or by grantee name and location, which serves
prospecting well but does not expose a corpus that can be rebuilt, audited, or
queried in bulk.

SmallGrants is designed so that the corpus is the artifact. The build runs end to
end from the published archives with a documented command sequence, so any figure
can be recomputed from source rather than taken on trust, and the year range is a
parameter rather than a fixed snapshot.

The software also demonstrates a retrieval problem specific to this data. Stated
grant purposes are boilerplate in 37.7% of records, so cause matching cannot rely
on them; instead the recipient's own registered activity code substitutes where
the purpose text is uninformative, and foundation giving histories are embedded
with a sentence transformer [@reimers2019sentencebert] so that a described
project can be matched against revealed funding behaviour rather than against
stated mission.

A further contribution is negative. The design proposed a behavioural signal,
the share of a foundation's grantees each year that it had not funded before, as
a proxy for whether a foundation accepts new applicants. Because roughly 70% of
foundations declare on Part XV line 2 whether they accept unsolicited requests,
that proxy can be validated against a labelled set. Across 77,605 foundations the
difference runs in the predicted direction and is significant (Welch
t = 33.6) but small (Cohen's d = 0.286): foundations that state they accept no
unsolicited requests still replace about a third of their grantees annually. The
signal was retained at reduced weight and labelled weak, and the measurement is
distributed with the software so the demotion can be checked.

Composition, collection, preprocessing, and limitations are documented in a
datasheet [@gebru2021datasheets] shipped with the repository.

# Acknowledgements

The corpus derives entirely from public filings published by the Internal
Revenue Service.

# References
