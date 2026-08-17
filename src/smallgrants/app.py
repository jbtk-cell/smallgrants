"""Web application for SmallGrants.

Errors are logged in full and rendered as a fixed string. DuckDB exception text
carries the OS username, the interpreter path, the process id, the database path
and sometimes the table schema; rendering it put all of that in front of an
anonymous visitor whenever a rebuild held the write lock.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque

from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    Response,
)
from fastapi.templating import Jinja2Templates

from smallgrants import seo, usage

log = logging.getLogger("smallgrants")

BASE = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

# The docs routes enumerate every endpoint and parameter; off unless asked for.
_DOCS = os.environ.get("SMALLGRANTS_DOCS") == "1"
app = FastAPI(
    title="SmallGrants",
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)

CORPUS_UNAVAILABLE = (
    "The corpus could not be read. It may still be building — a rebuild holds a "
    "write lock and the site is unavailable until it finishes."
)
MAX_QUERY = 2000
MAX_PROJECT = 4000  # a funding ask, not an essay
LLM_CALLS_PER_HOUR = 30
_llm_calls: deque[float] = deque()

# A search embeds the query and scans 8.4M grant rows: roughly 0.8s of CPU on one
# core. There is no login to rate limit, so the expensive path is search itself,
# and a single unthrottled script can hold the site down. Counted per address.
SEARCHES_PER_MINUTE = 20
SEARCH_BURST_WINDOW = 60.0
_searches: dict[str, deque[float]] = {}
_search_lock = threading.Lock()

TOO_MANY_SEARCHES = (
    "Too many searches from this address in the last minute. Wait a moment and "
    "try again."
)


def client_key(request: Request) -> str:
    """The caller's address, trusting a proxy header only when told to.

    Behind Fly or any reverse proxy the socket address is the proxy, so every
    visitor would share one bucket and the first busy minute would lock out
    everybody. Reading the header unconditionally is worse: anyone could forge it
    and bypass the limit entirely. So it is read only when the deployment says a
    trusted proxy is in front.
    """
    if os.environ.get("SMALLGRANTS_TRUST_PROXY") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return getattr(getattr(request, "client", None), "host", "") or "unknown"


def search_rate_limited(key: str) -> bool:
    now = time.monotonic()
    with _search_lock:
        hits = _searches.setdefault(key, deque())
        while hits and now - hits[0] > SEARCH_BURST_WINDOW:
            hits.popleft()
        # Drop buckets that have gone quiet, so the dict cannot grow without
        # bound on a site that gets crawled.
        if len(_searches) > 4096:
            for k in [k for k, v in _searches.items() if not v or now - v[-1] > 300]:
                _searches.pop(k, None)
        if len(hits) >= SEARCHES_PER_MINUTE:
            return True
        hits.append(now)
        return False


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    # frame-ancestors already covers framing for anything current; this is for
    # browsers that predate it.
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=(), usb=(), "
        "interest-cohort=()"
    )
    # Only over TLS. Sending HSTS on a plain-HTTP local run would pin localhost
    # to HTTPS in the developer's browser and break every other project on it.
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


def data_dir() -> str:
    return os.environ.get("SMALLGRANTS_DATA", os.path.expanduser("~/smallgrants/data"))


def _int_or_none(raw: str, cap: int = 1_000_000_000) -> int | None:
    """str.isdigit() accepts characters int() rejects ('²'), and Python caps
    int-from-string at 4300 digits, so both were reachable 500s."""
    raw = (raw or "").strip()
    if not raw.isascii() or not raw.isdigit() or len(raw) > 12:
        return None
    value = int(raw)
    return value if 0 < value <= cap else None


def _flag(raw: str) -> bool:
    """bool("false") is True, so include_closed=false used to surface exactly the
    foundations the user asked to exclude."""
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean(raw: str, limit: int) -> str:
    return (raw or "").strip()[:limit]


def referral(request: Request, default: str = "") -> str:
    """Where this visitor came from, when a link said so.

    Outreach goes to a small number of umbrella organizations, each of which can
    put the tool in front of hundreds. Without a tag on the link there is no way
    to tell which of them actually sent anyone, and "we emailed 40 places and got
    some traffic" is not a finding. Links carry ?from=<tag>; nothing about the
    person is recorded, only which door they came through.
    """
    tag = (request.query_params.get("from") or "").strip()[:32]
    tag = "".join(c for c in tag if c.isalnum() or c in "-_")
    return tag or default


def corpus_summary() -> dict:
    from smallgrants.store import summary

    try:
        return summary(data_dir())
    except Exception:
        log.exception("corpus summary unavailable")
        return {}


def _rate_limited() -> bool:
    now = time.monotonic()
    while _llm_calls and now - _llm_calls[0] > 3600:
        _llm_calls.popleft()
    if len(_llm_calls) >= LLM_CALLS_PER_HOUR:
        return True
    _llm_calls.append(now)
    return False


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    state: str = "",
    zip3: str = "",
    amount: str = "",
    applicant: str = "organization",
    include_closed: str = "",
):
    # `from` is a Python keyword, so it is never a route parameter. referral()
    # reads it off the query string, and FastAPI ignores parameters it does not
    # declare.
    q = _clean(q, MAX_QUERY)
    state = _clean(state, 2).upper()
    zip3 = _clean(zip3, 3)
    applicant = applicant if applicant in {"organization", "individual"} else "organization"
    closed = _flag(include_closed)
    results, error = [], None

    if q and search_rate_limited(client_key(request)):
        error = TOO_MANY_SEARCHES
        # Logged separately so a wave of throttling is visible in `stats` rather
        # than looking like a drop in traffic.
        usage.record(data_dir(), "throttled", request, query=q, state=state)
    elif q:
        try:
            from smallgrants.match import search

            results = search(
                data_dir(),
                q,
                state=state or None,
                zip3=zip3 or None,
                amount=_int_or_none(amount),
                limit=25,
                include_closed=closed,
                for_individual=(applicant == "individual"),
            )
        except Exception:
            log.exception("search failed for query %r", q[:120])
            error = CORPUS_UNAVAILABLE

        usage.record(
            data_dir(), "search", request, query=q, state=state,
            amount=_int_or_none(amount), applicant=applicant, results=len(results),
            source=referral(request),
        )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "q": q, "state": state, "zip3": zip3, "amount": _clean(amount, 12),
            "applicant": applicant, "include_closed": closed,
            "results": results, "error": error, "summary": corpus_summary(),
            "meta": seo.meta(
                "/",
                f"{q[:60]} — funders — SmallGrants" if q else
                "SmallGrants — find US foundations that fund work like yours",
                seo.DESCRIPTION,
            ),
            "jsonld": seo.dataset_jsonld(),
        },
    )


def _foundation_page(request: Request, ein: str, critique=None, ask=None, thanks=None):
    from smallgrants.agents import foundation_profile

    try:
        profile = foundation_profile(data_dir(), ein)
        error = None
    except Exception:
        log.exception("profile lookup failed for ein %r", ein[:20])
        profile, error = None, CORPUS_UNAVAILABLE
    return templates.TemplateResponse(
        request,
        "foundation.html",
        {
            "profile": profile, "ein": ein, "critique": critique,
            "ask": ask or {}, "error": error, "summary": corpus_summary(),
            "thanks": thanks,
            "meta": seo.meta(
                f"/f/{ein}",
                f"{profile['name']} — grants it has paid — SmallGrants"
                if profile else f"{ein} — SmallGrants",
                seo.foundation_description(profile) if profile else seo.DESCRIPTION,
            ),
            "jsonld": seo.foundation_jsonld(ein, profile) if profile else None,
        },
    )


STATIC = os.path.join(BASE, "static")
_sitemap_cache: dict[str, str] = {}


@app.exception_handler(404)
async def not_found(request: Request, exc):
    """A JSON body reading {"detail":"Not Found"} is the framework's default and
    tells a visitor nothing. Foundation URLs get mistyped and shared broken."""
    return templates.TemplateResponse(
        request,
        "404.html",
        {
            "summary": corpus_summary(),
            "meta": seo.meta("/404", "Page not found — SmallGrants", seo.DESCRIPTION),
        },
        status_code=404,
    )


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg():
    return FileResponse(
        os.path.join(STATIC, "favicon.svg"), media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    # Browsers and crawlers request this path whatever the markup says.
    return favicon_svg()


@app.get("/og.png", include_in_schema=False)
def og_image():
    return FileResponse(
        os.path.join(STATIC, "og.png"), media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse(seo.robots())


@app.get("/llms.txt", include_in_schema=False)
def llms():
    return PlainTextResponse(seo.llms_txt())


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap():
    """Foundations with a published way to apply, plus the fixed pages.

    Listing all 142,806 foundation pages would submit a great many that carry a
    name and nothing else. The ones worth indexing are those that published
    application information, because those are the pages that answer the question
    someone typed into a search engine.
    """
    key = seo.site_url()
    if key not in _sitemap_cache:
        try:
            _sitemap_cache[key] = seo.build_sitemap(data_dir())
        except Exception:
            log.exception("sitemap build failed")
            return PlainTextResponse("", status_code=503)
    return Response(_sitemap_cache[key], media_type="application/xml")


@app.post("/f/{ein}/applying", response_class=HTMLResponse)
def applying(request: Request, ein: str, knew: str = Form("")):
    """One question, asked at the only moment its answer exists.

    Whether a funder was already known cannot be measured from server logs and
    cannot be reconstructed later, so it is asked here or never. Anonymous, no
    email, no account. The answer is self-reported and is labelled that way
    everywhere it is reported.
    """
    ein = _clean(ein, 12)
    if search_rate_limited(client_key(request)):
        return _foundation_page(request, ein, thanks="rate")
    knew_flag = {"yes": 1, "no": 0}.get(knew.strip().lower())
    usage.record(data_dir(), "applying", request, ein=ein, already_knew=knew_flag)
    return _foundation_page(request, ein, thanks="ok")


_individual_counts: dict = {}


def individual_counts() -> dict:
    """Sized once. Two numbers, both measured, shown on the scholarships page."""
    if not _individual_counts:
        try:
            from smallgrants.store import connect

            con = connect(data_dir(), read_only=True)
            try:
                n = con.execute(
                    "SELECT count(*) FROM grants WHERE is_individual"
                ).fetchone()[0]
                r = con.execute(
                    """SELECT count(*) FROM foundation_signals
                       WHERE grant_count >= 5
                         AND (individual_share > 0.7 OR person_share > 0.7)
                         AND NOT declared_closed AND has_application_info"""
                ).fetchone()[0]
            finally:
                con.close()
            _individual_counts.update(individual_grants=n, reachable=r)
        except Exception:
            log.exception("individual counts unavailable")
            return {"individual_grants": 0, "reachable": 0}
    return _individual_counts


@app.get("/scholarships", response_class=HTMLResponse)
def scholarships(
    request: Request, q: str = "", state: str = "", amount: str = ""
):
    """A separate door for people asking on their own behalf.

    The main form defaults to applying as an organization, which buries the
    individual path behind a dropdown. Students looking for scholarships are the
    largest group with no route to the free commercial alternatives, since those
    require a 501(c)(3) profile they cannot hold.
    """
    q = _clean(q, MAX_QUERY)
    state = _clean(state, 2).upper()
    results, error = [], None

    if q and search_rate_limited(client_key(request)):
        error = TOO_MANY_SEARCHES
        usage.record(data_dir(), "throttled", request, query=q, state=state)
    elif q:
        try:
            from smallgrants.match import search

            results = search(
                data_dir(), q, state=state or None,
                amount=_int_or_none(amount), limit=25, for_individual=True,
            )
        except Exception:
            log.exception("scholarship search failed for %r", q[:120])
            error = CORPUS_UNAVAILABLE
        usage.record(
            data_dir(), "search", request, query=q, state=state,
            amount=_int_or_none(amount), applicant="individual",
            results=len(results), source=referral(request, "scholarships"),
        )

    return templates.TemplateResponse(
        request,
        "scholarships.html",
        {
            "q": q, "state": state, "amount": _clean(amount, 12),
            "results": results, "error": error, "summary": corpus_summary(),
            "counts": individual_counts(),
            "meta": seo.meta(
                "/scholarships",
                f"{q[:50]} — scholarship funders — SmallGrants" if q else
                "Scholarships and grants to individuals, from IRS filings",
                "Find private foundations that have paid scholarships, fellowships "
                "and grants directly to individuals, taken from their own IRS Form "
                "990-PF filings. Free, no account.",
            ),
        },
    )


@app.get("/method", response_class=HTMLResponse)
def method(request: Request):
    return templates.TemplateResponse(
        request,
        "method.html",
        {
            "summary": corpus_summary(),
            "meta": seo.meta(
                "/method",
                "How SmallGrants works, and what it cannot tell you",
                "Where the data comes from, what 40% unresolved recipients means, "
                "and which of the original ideas failed when it was tested.",
            ),
        },
    )


@app.get("/f/{ein}", response_class=HTMLResponse)
def foundation(request: Request, ein: str):
    ein = _clean(ein, 12)
    usage.record(
        data_dir(), "foundation", request, ein=ein,
        source=referral(
            request, "search" if "referer" in request.headers else "direct"
        ),
    )
    return _foundation_page(request, ein)


@app.post("/f/{ein}", response_class=HTMLResponse)
def critique(
    request: Request,
    ein: str,
    project: str = Form(""),
    amount: str = Form(""),
    state: str = Form(""),
    applicant_type: str = Form("organization"),
):
    from smallgrants.agents import credentials_available, critique_ask

    ein = _clean(ein, 12)
    ask = {
        "project": _clean(project, MAX_PROJECT),
        "amount": _int_or_none(amount),
        "state": _clean(state, 2).upper() or None,
        "applicant_type": (
            applicant_type if applicant_type in {"organization", "individual"} else "organization"
        ),
    }
    # The project text itself is never logged. Only that a review was asked for,
    # for which foundation, and by which kind of applicant.
    usage.record(
        data_dir(), "review", request, ein=ein, state=ask["state"],
        amount=ask["amount"], applicant=ask["applicant_type"],
    )
    # The model path is an unauthenticated paid call. Deterministic checks always
    # run; only the model is rate limited.
    force_rules = credentials_available() and _rate_limited()
    try:
        result = critique_ask(data_dir(), ein, ask, force_rules=force_rules)
    except Exception:
        log.exception("critique failed for ein %r", ein)
        return _foundation_page(request, ein, None, ask)
    payload = result.to_dict()
    if force_rules:
        payload["verdict"] += " (hourly review limit reached; filing checks only)"
    return _foundation_page(request, ein, payload, ask)
