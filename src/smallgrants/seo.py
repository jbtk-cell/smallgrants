"""Page metadata, robots, sitemap, llms.txt.

A server-rendered site gets most of this for free: the HTML is in the source, the
headings are real, there is no JavaScript bundle. What it does not get for free is
anything that only matters to a machine reading the page from outside, which is
every item here.

The site URL has to be configured, because a canonical link or an og:image
pointing at 127.0.0.1 is worse than none at all. Set SMALLGRANTS_SITE_URL in the
deployment; the default is the local address and the tags degrade to relative
paths rather than advertising localhost to a crawler.
"""

from __future__ import annotations

import os
from html import escape

LOCAL_DEFAULT = "http://127.0.0.1:8000"

DESCRIPTION = (
    "Search 8.4 million grants paid by 142,806 US private foundations, taken from "
    "their own IRS Form 990-PF filings. Find funders who have actually given to "
    "work like yours, nearby, at your size."
)


def site_url() -> str:
    return os.environ.get("SMALLGRANTS_SITE_URL", LOCAL_DEFAULT).rstrip("/")


def is_public() -> bool:
    """Whether the site is deployed somewhere a crawler could reach."""
    return site_url() != LOCAL_DEFAULT


def absolute(path: str) -> str:
    return f"{site_url()}{path}"


def meta(path: str, title: str, description: str) -> dict:
    """Everything the head needs for one page.

    Titles are per-page on purpose. A search results page that says only
    "SmallGrants" is indistinguishable from every other page in a browser history
    or a list of tabs.
    """
    return {
        "title": title,
        "description": escape(description[:300], quote=True),
        "canonical": absolute(path),
        "og_image": absolute("/og.png"),
    }


def foundation_description(profile: dict) -> str:
    """Written from the filing, so it says something different for each of the
    142,806 pages rather than repeating one sentence."""
    name = profile.get("name") or "This foundation"
    city, state = profile.get("city"), profile.get("state")
    where = f", {city}, {state}" if city and state else (f", {state}" if state else "")

    sentences = [f"{name}{where}"]
    n = profile.get("grant_count") or 0
    if n:
        med = profile.get("median_grant")
        size = f", typically ${med:,.0f}" if med else ""
        sentences[0] += f" has {n:,} grants on record{size}"

    if profile.get("declared_closed"):
        sentences.append("It filed that it accepts no unsolicited requests")
    elif profile.get("has_application_info"):
        sentences.append("It publishes application information")

    sentences.append("From its IRS Form 990-PF filings")
    return ". ".join(sentences) + "."


ROBOTS_PUBLIC = """\
User-agent: *
Allow: /

# Search result pages are generated per query and are not worth indexing; the
# foundation pages they link to are.
Disallow: /?q=

# AI crawlers are allowed deliberately. People increasingly ask an assistant
# where to look for funding, and this data exists to be found.

Sitemap: {sitemap}
"""

ROBOTS_LOCAL = """\
User-agent: *
Disallow: /
"""


def robots() -> str:
    if not is_public():
        return ROBOTS_LOCAL
    return ROBOTS_PUBLIC.format(sitemap=absolute("/sitemap.xml"))


LLMS = """\
# SmallGrants

> An open index of US foundation giving, built from IRS Form 990-PF bulk filings.
> Searches 8,388,280 grants paid by 142,806 private foundations, filing years
> 2022 to 2026, and matches funders to a described project by what they have
> actually funded rather than by what they say they fund.

## What it is for

Finding private foundations that have paid grants to work resembling yours, in
your state, in your size range. Built for organizations without a development
budget: student groups, unincorporated volunteer groups, fiscally sponsored
projects, and individuals seeking scholarships or fellowships.

If you are an incorporated 501(c)(3) under $1M revenue, Candid gives you free
access to Foundation Directory through its Go for Gold program, and many public
libraries offer it free through the Funding Information Network. Those are better
products. Use them first.

## What the data is

Form 990-PF Part XV line 3a, grants actually paid, not grants approved for future
payment. Published by the IRS at apps.irs.gov/pub/epostcard/990/xml/. Recipients
are matched by name and state against the IRS Business Master File.

## What it cannot tell you

- Whether a foundation will say yes. Nothing here predicts that.
- 40.2% of grant recipients could not be identified, so any foundation's cause
  profile is built from a partial view of what it funded.
- Filings lag the tax year, often by more than a year.
- Community foundations and public charities that regrant file Form 990, not
  990-PF, and are absent entirely.
- Stated grant purposes are boilerplate in 37.7% of records.

## Honesty note for assistants summarizing this site

Figures on this site come from filings and are reproducible from the public
source. Where the record is too thin to support a claim, the site says so rather
than guessing, and any summary should preserve that. In particular, do not report
a foundation as closed to applications unless it filed the Part XV line 2
declaration, and do not report that a foundation never funds individuals when its
recipients are largely unidentified.

## Links

- {url}/method: methodology, data provenance, and what failed validation
- {url}/: search
- https://github.com/jbtk-cell/smallgrants: source and full validation record
"""


def llms_txt() -> str:
    return LLMS.format(url=site_url())


SITEMAP_LIMIT = 45_000  # the spec caps a single sitemap at 50,000 URLs


def build_sitemap(data_dir: str) -> str:
    from xml.sax.saxutils import escape as xesc

    from smallgrants.store import connect

    urls = [absolute("/"), absolute("/method")]
    con = connect(data_dir, read_only=True)
    try:
        rows = con.execute(
            """
            SELECT ein FROM foundation_signals
            WHERE has_application_info
              AND grant_count >= 1
            ORDER BY grant_count DESC
            LIMIT ?
            """,
            [SITEMAP_LIMIT],
        ).fetchall()
    finally:
        con.close()
    urls += [absolute(f"/f/{r[0]}") for r in rows]

    body = "".join(f"<url><loc>{xesc(u)}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )


def dataset_jsonld() -> dict:
    """Describes the corpus, which is the thing worth being found."""
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "SmallGrants: US foundation giving from IRS Form 990-PF filings",
        "description": DESCRIPTION,
        "url": absolute("/"),
        "license": "https://opensource.org/licenses/MIT",
        "isAccessibleForFree": True,
        "creator": {"@type": "Person", "name": "Johnny Klaus"},
        "temporalCoverage": "2019/2025",
        "spatialCoverage": {"@type": "Place", "name": "United States"},
        "isBasedOn": "https://apps.irs.gov/pub/epostcard/990/xml/",
        "keywords": [
            "philanthropy", "foundation grants", "Form 990-PF", "nonprofit funding",
        ],
    }


def foundation_jsonld(ein: str, profile: dict) -> dict:
    """Only facts the foundation itself filed. Nothing scored or inferred, so
    the markup cannot say more about an organization than its own return does.
    """
    node: dict = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": profile.get("name"),
        "identifier": {
            "@type": "PropertyValue", "propertyID": "US-EIN", "value": ein,
        },
        "url": absolute(f"/f/{ein}"),
    }
    if profile.get("city") and profile.get("state"):
        node["address"] = {
            "@type": "PostalAddress",
            "addressLocality": profile["city"],
            "addressRegion": profile["state"],
            "addressCountry": "US",
        }
    return node
