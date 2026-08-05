"""Web application for SmallGrants."""

from __future__ import annotations

import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))
app = FastAPI(title="SmallGrants")


def data_dir() -> str:
    return os.environ.get("SMALLGRANTS_DATA", os.path.expanduser("~/smallgrants/data"))


def corpus_summary() -> dict:
    from smallgrants.store import summary

    try:
        return summary(data_dir())
    except Exception:
        return {}


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
    results, error = [], None
    amount_i = int(amount) if amount.strip().isdigit() else None
    if q.strip():
        try:
            from smallgrants.match import search

            results = search(
                data_dir(),
                q,
                state=state.strip() or None,
                zip3=zip3.strip() or None,
                amount=amount_i,
                limit=25,
                include_closed=bool(include_closed),
                for_individual=(applicant == "individual"),
            )
        except FileNotFoundError as exc:
            error = str(exc)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "q": q,
            "state": state,
            "zip3": zip3,
            "amount": amount,
            "applicant": applicant,
            "include_closed": bool(include_closed),
            "results": results,
            "error": error,
            "summary": corpus_summary(),
        },
    )


@app.get("/f/{ein}", response_class=HTMLResponse)
def foundation(request: Request, ein: str):
    from smallgrants.agents import foundation_profile

    profile = foundation_profile(data_dir(), ein)
    return templates.TemplateResponse(
        request,
        "foundation.html",
        {"profile": profile, "ein": ein, "critique": None, "ask": {}},
    )


@app.post("/f/{ein}", response_class=HTMLResponse)
def critique(
    request: Request,
    ein: str,
    project: str = Form(""),
    amount: str = Form(""),
    state: str = Form(""),
    applicant_type: str = Form("organization"),
):
    from smallgrants.agents import critique_ask, foundation_profile

    ask = {
        "project": project,
        "amount": int(amount) if amount.strip().isdigit() else None,
        "state": state.strip().upper() or None,
        "applicant_type": applicant_type,
    }
    result = critique_ask(data_dir(), ein, ask)
    return templates.TemplateResponse(
        request,
        "foundation.html",
        {
            "profile": foundation_profile(data_dir(), ein),
            "ein": ein,
            "critique": result.to_dict(),
            "ask": ask,
        },
    )
