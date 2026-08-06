"""Web application for SmallGrants.

Errors are logged in full and rendered as a fixed string. DuckDB exception text
carries the OS username, the interpreter path, the process id, the database path
and sometimes the table schema; rendering it put all of that in front of an
anonymous visitor whenever a rebuild held the write lock.
"""

from __future__ import annotations

import logging
import os
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
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

    if q:
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


def _foundation_page(request: Request, ein: str, critique=None, ask=None):
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
        },
    )


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
