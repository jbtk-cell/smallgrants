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
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from smallgrants import usage

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
        )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "q": q, "state": state, "zip3": zip3, "amount": _clean(amount, 12),
            "applicant": applicant, "include_closed": closed,
            "results": results, "error": error, "summary": corpus_summary(),
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
        },
    )


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


@app.get("/method", response_class=HTMLResponse)
def method(request: Request):
    return templates.TemplateResponse(
        request, "method.html", {"summary": corpus_summary()}
    )


@app.get("/f/{ein}", response_class=HTMLResponse)
def foundation(request: Request, ein: str):
    ein = _clean(ein, 12)
    usage.record(
        data_dir(), "foundation", request, ein=ein,
        source="search" if "referer" in request.headers else "direct",
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
