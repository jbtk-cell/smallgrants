"""In-product agents: a funder researcher and an adversarial critic.

Both are pluggable. With Anthropic credentials available they run on Claude with
tools over the local corpus. Without credentials they fall back to deterministic
checks against the same data -- the fallback is narrower, not fake: every finding
it reports is derived from the foundation's own filing.

The critic is adversarial by construction. Its job is to find reasons the ask
will fail, not to encourage the user.
"""

from __future__ import annotations

import json
import os
from contextlib import closing
from dataclasses import dataclass, field

MODEL = "claude-opus-5"


def credentials_available() -> bool:
    """True when the Anthropic SDK will find credentials without prompting."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    config = os.environ.get("ANTHROPIC_CONFIG_DIR") or os.path.expanduser(
        "~/.config/anthropic"
    )
    creds = os.path.join(config, "credentials")
    return os.path.isdir(creds) and bool(os.listdir(creds))


@dataclass
class Finding:
    severity: str  # "disqualifying" | "serious" | "worth_checking"
    claim: str
    evidence: str
    source: str = "filing"  # "filing" for record-derived, else the model name


@dataclass
class Critique:
    findings: list[Finding] = field(default_factory=list)
    verdict: str = ""
    engine: str = "rules"

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "verdict": self.verdict,
            "findings": [
                {
                    "severity": f.severity,
                    "claim": f.claim,
                    "evidence": f.evidence,
                    "source": f.source,
                }
                for f in self.findings
            ],
        }


# --------------------------------------------------------------------------
# Corpus access shared by both engines
# --------------------------------------------------------------------------


def foundation_profile(data_dir: str, ein: str) -> dict | None:
    from smallgrants.store import connect

    con = connect(data_dir, read_only=True)
    row = con.execute(
        """
        SELECT ein, name, city, state, declared_closed, has_application_info,
               app_deadlines, app_restrictions, app_contact_name,
               grant_count, median_grant, min_grant, max_grant, p25_grant, p75_grant,
               total_granted, individual_share, top_state, top_state_share,
               states_funded, last_year, openness_ratio, total_assets_eoy, top_ntee
        FROM foundation_signals WHERE ein = ?
        """,
        [ein],
    ).fetchone()
    if row is None:
        con.close()
        return None
    cols = [d[0] for d in con.description]
    profile = dict(zip(cols, row))
    profile["recent_grants"] = [
        {"recipient": r[0], "amount": r[1], "year": r[2], "purpose": r[3], "state": r[4]}
        for r in con.execute(
            """
            SELECT recipient_name, amount, tax_year, purpose, recipient_state
            FROM grants WHERE ein = ? AND amount IS NOT NULL
            ORDER BY tax_year DESC, amount DESC LIMIT 25
            """,
            [ein],
        ).fetchall()
    ]
    con.close()
    return profile


# --------------------------------------------------------------------------
# Rule-based critic (no credentials required)
# --------------------------------------------------------------------------

import re

# "NO GRANTS TO INDIVIDUALS" and "SCHOLARSHIPS TO INDIVIDUALS" both contain the
# word "individuals" and mean opposite things. Matching the bare word treated the
# first as evidence of the second and told organizations not to apply: measured
# over the corpus, 53% of the disqualifying flags it produced were foundations
# that give individuals nothing at all. Negation is now detected explicitly, and
# a restriction alone never disqualifies -- the foundation's actual behaviour has
# to agree.
_EXCLUDES_INDIVIDUALS = re.compile(
    r"\b(?:no|not|never|non[- ]?)\s*"
    r"(?:\w+\s+){0,3}?(?:to\s+|for\s+)?individuals?\b"
    r"|\bindividuals?\s+(?:are\s+)?(?:not|excluded|ineligible)\b"
    r"|\b(?:organizations?|charities|501\s*\(?c\)?\s*\(?3\)?)\s+only\b"
    r"|\bno\s+scholarships?\b",
    re.I,
)
_INDIVIDUALS_ONLY = re.compile(
    r"\b(?:scholarship|tuition|graduating senior|undergraduate|student)s?\b", re.I
)

_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina",
    "SD": "south dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}


def _states_named(text: str) -> set[str]:
    """State codes whose full name appears in the text.

    Comparing the two-letter code against the text directly is what the earlier
    version did, so "TX" never matched "STATE OF TEXAS" (a false warning to Texas
    applicants) while "IN" matched inside "IN THE STATE OF OREGON" (no warning to
    Indiana applicants). Full names only, with word boundaries.
    """
    low = text.lower()
    return {
        code
        for code, name in _STATES.items()
        if re.search(rf"\b{re.escape(name)}\b", low)
    }


def _rule_findings(profile: dict, ask: dict) -> list[Finding]:
    findings: list[Finding] = []
    amount = ask.get("amount")
    state = (ask.get("state") or "").upper()
    is_org = ask.get("applicant_type", "organization") == "organization"

    if profile.get("declared_closed"):
        findings.append(
            Finding(
                "disqualifying",
                "This foundation accepts no unsolicited requests.",
                "It checked Part XV line 2 of its 990-PF: contributions only to "
                "preselected organizations.",
            )
        )

    restrictions = (profile.get("app_restrictions") or "").strip()
    share = profile.get("individual_share")
    grants = profile.get("grant_count") or 0
    excludes_individuals = bool(restrictions and _EXCLUDES_INDIVIDUALS.search(restrictions))

    if restrictions and state:
        named = _states_named(restrictions)
        if named and state not in named:
            pretty = ", ".join(sorted(_STATES[c].title() for c in named))
            findings.append(
                Finding(
                    "serious",
                    f"Its stated restrictions name {pretty}, which does not include your state.",
                    f'Restrictions on its filing: "{restrictions[:200]}"',
                )
            )

    if is_org:
        # Only disqualify an organization when the filing says individuals-only
        # AND the grant record agrees. Either one alone is not enough.
        says_individuals_only = bool(
            restrictions and _INDIVIDUALS_ONLY.search(restrictions) and not excludes_individuals
        )
        if says_individuals_only and share is not None and share > 0.5:
            findings.append(
                Finding(
                    "disqualifying",
                    "It funds individuals rather than organizations.",
                    f"{share:.0%} of its grants name a person, and its filing says: "
                    f'"{restrictions[:160]}"',
                )
            )
        elif share is not None and grants >= 10 and share > 0.9:
            findings.append(
                Finding(
                    "disqualifying",
                    "Effectively all of its grants go to individuals, not organizations.",
                    f"{share:.0%} of its {grants} grant records name a person rather "
                    "than an organization.",
                )
            )
    else:
        # The converse case had no check at all, so an individual asking a
        # foundation whose filing reads "NO GRANTS TO INDIVIDUALS" was told there
        # was no disqualifying problem.
        if excludes_individuals:
            findings.append(
                Finding(
                    "disqualifying",
                    "Its stated restrictions exclude individuals.",
                    f'Restrictions on its filing: "{restrictions[:200]}"',
                )
            )
        elif share is not None and grants >= 20 and share == 0:
            findings.append(
                Finding(
                    "disqualifying",
                    "It has never recorded a grant to an individual.",
                    f"All {grants} of its recorded grants name an organization.",
                )
            )

    if amount:
        mx, med, p75 = profile.get("max_grant"), profile.get("median_grant"), profile.get("p75_grant")
        if mx and amount > mx:
            findings.append(
                Finding(
                    "disqualifying",
                    f"Your ask exceeds the largest grant it has ever made.",
                    f"Largest recorded grant ${mx:,.0f}; you are asking ${amount:,.0f}.",
                )
            )
        elif p75 and amount > p75:
            findings.append(
                Finding(
                    "serious",
                    "Your ask is above the top quartile of what it gives.",
                    f"Typical grant ${med:,.0f}; 75th percentile ${p75:,.0f}; "
                    f"you are asking ${amount:,.0f}.",
                )
            )

    if state:
        top, top_share = profile.get("top_state"), profile.get("top_state_share") or 0
        funds_here = any(g.get("state") == state for g in profile.get("recent_grants", []))
        if top and top != state and top_share > 0.8 and not funds_here:
            findings.append(
                Finding(
                    "serious",
                    f"It concentrates its giving in {top}, not {state}.",
                    f"{top_share:.0%} of its grants go to {top}; none of its recent "
                    f"grants went to {state}.",
                )
            )

    deadlines = (profile.get("app_deadlines") or "").strip()
    if deadlines and deadlines.lower() not in {"none", "n/a", "no submission deadlines"}:
        findings.append(
            Finding(
                "worth_checking",
                "It publishes a submission deadline you must meet.",
                f'Stated deadline: "{deadlines[:160]}"',
            )
        )

    if not profile.get("has_application_info"):
        findings.append(
            Finding(
                "worth_checking",
                "It publishes no application instructions, so there is no documented way in.",
                "Its 990-PF has no application-submission section.",
            )
        )

    last = profile.get("last_year")
    if last and last < 2023:
        findings.append(
            Finding(
                "worth_checking",
                "Its most recent filing is old; it may be inactive.",
                f"Most recent 990-PF on record is for tax year {last}.",
            )
        )
    return findings


_SEVERITY_RANK = {"worth_checking": 1, "serious": 2, "disqualifying": 3}


def _worst(findings: list[Finding]) -> int:
    return max((_SEVERITY_RANK.get(f.severity, 0) for f in findings), default=0)


def _resolve_verdict(
    model_verdict: str, rule_findings: list[Finding], model_findings: list[Finding]
) -> str:
    """The filing record is the floor under the headline sentence.

    The model writes the verdict only when its own findings are at least as
    severe as the ones read off the filing. Otherwise the verdict is derived
    from the union, so an optimistic sentence can never sit above a serious
    fact the foundation itself filed.
    """
    if _worst(model_findings) >= _worst(rule_findings):
        return model_verdict
    return _verdict_from(rule_findings + model_findings)


def _verdict_from(findings: list[Finding]) -> str:
    if any(f.severity == "disqualifying" for f in findings):
        return "Do not send this. At least one disqualifying problem is on the record."
    if any(f.severity == "serious" for f in findings):
        return "Send only after resolving the serious problems below."
    if findings:
        return "No disqualifying problem found. Check the items below before sending."
    return (
        "No problem found in the filing data. That is not evidence the ask is good -- "
        "the corpus only knows what the foundation reported to the IRS."
    )


# --------------------------------------------------------------------------
# Claude-backed engines
# --------------------------------------------------------------------------

CRITIC_SYSTEM = """You are an adversarial reviewer of grant asks. Your job is to \
find the reasons this ask will be rejected, not to improve morale.

You are given a foundation's actual IRS 990-PF record -- what it funded, how much, \
where, what restrictions it published -- and a draft ask. Attack the ask against that \
record. Default to finding a problem; only report "no problem found" when the record \
genuinely supports the ask.

Every finding must cite the specific record fact that supports it. A finding you \
cannot ground in the supplied data is not a finding -- drop it. Do not invent \
facts about the foundation that are not in the data you were given.

Severity levels:
- disqualifying: the record shows this ask cannot succeed as written
- serious: the record shows a substantial mismatch the user must resolve
- worth_checking: a real risk that the record cannot settle either way"""

CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "description": "One sentence: send, fix first, or do not send, and why.",
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["disqualifying", "serious", "worth_checking"],
                    },
                    "claim": {"type": "string", "description": "The problem, one sentence."},
                    "evidence": {
                        "type": "string",
                        "description": "The specific record fact that establishes it.",
                    },
                },
                "required": ["severity", "claim", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "findings"],
    "additionalProperties": False,
}


def critique_ask(data_dir: str, ein: str, ask: dict, force_rules: bool = False) -> Critique:
    """Attack a draft ask against the foundation's own filing record."""
    profile = foundation_profile(data_dir, ein)
    if profile is None:
        return Critique(
            verdict=f"No foundation with EIN {ein} in the corpus.", engine="rules"
        )

    rule_findings = _rule_findings(profile, ask)

    if force_rules or not credentials_available():
        return Critique(
            findings=rule_findings, verdict=_verdict_from(rule_findings), engine="rules"
        )

    try:
        import anthropic

        client = anthropic.Anthropic()
        payload = {
            "foundation_record": {k: v for k, v in profile.items() if v is not None},
            "draft_ask": ask,
            "deterministic_checks_already_run": [
                {"severity": f.severity, "claim": f.claim, "evidence": f.evidence}
                for f in rule_findings
            ],
        }
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=CRITIC_SYSTEM,
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": CRITIQUE_SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": "Attack this ask against the record:\n\n"
                    + json.dumps(payload, indent=2, default=str),
                }
            ],
        )
        if response.stop_reason == "refusal":
            return Critique(
                findings=rule_findings,
                verdict=_verdict_from(rule_findings) + " (model declined; rules only)",
                engine="rules",
            )
        text = next(b.text for b in response.content if b.type == "text")
        parsed = json.loads(text)
        model_findings = [
            Finding(
                severity=f["severity"],
                claim=f["claim"],
                evidence=f["evidence"],
                source=MODEL,
            )
            for f in parsed.get("findings", [])
            # The deterministic checks are already in the list; don't repeat them.
            if not any(f["claim"].strip() == r.claim.strip() for r in rule_findings)
        ]
        # The record-derived findings are never replaced by the model's. An
        # earlier version substituted them, so a model that returned an empty
        # list turned a foundation that had filed "no unsolicited requests" into
        # "a strong fit; send it". The rules are the floor; the model can only
        # add to them, and the verdict never reads gentler than the filing.
        combined = rule_findings + model_findings
        return Critique(
            findings=combined,
            verdict=_resolve_verdict(parsed["verdict"], rule_findings, model_findings),
            engine=MODEL,
        )
    except Exception as exc:  # never let the critic break the app
        return Critique(
            findings=rule_findings,
            verdict=_verdict_from(rule_findings) + f" (model unavailable: {type(exc).__name__})",
            engine="rules",
        )


RESEARCH_SYSTEM = """You research a single private foundation for someone deciding \
whether to approach it. You have tools over a corpus built from IRS Form 990-PF \
filings -- every grant these foundations reported paying.

Ground every claim in a tool result. If the corpus cannot answer something, say so \
rather than filling the gap. You are not writing marketing copy: the reader needs to \
know whether this funder is reachable and what it actually funds, including when the \
answer is "not worth your time".

Report: what it actually funds (from its grant history, not its name), its typical \
grant size, whether it accepts unsolicited requests, any published deadline or \
restriction, and the single strongest angle for this specific applicant -- or that \
there isn't one."""


def research_funder(data_dir: str, ein: str, project: str) -> dict:
    """Investigate one foundation for a specific project. Requires credentials."""
    profile = foundation_profile(data_dir, ein)
    if profile is None:
        return {"error": f"No foundation with EIN {ein} in the corpus."}
    if not credentials_available():
        return {
            "engine": "unavailable",
            "profile": profile,
            "note": (
                "Funder research needs Anthropic credentials (ANTHROPIC_API_KEY or "
                "`ant auth login`). The raw record is included above; the critic still "
                "runs its deterministic checks without credentials."
            ),
        }

    import anthropic
    from anthropic import beta_tool

    @beta_tool
    def grant_history(min_amount: int = 0, limit: int = 40) -> str:
        """Read this foundation's actual paid grants. Call this first, before making
        any claim about what the foundation funds -- its name is not evidence.

        Args:
            min_amount: Only return grants at or above this dollar amount.
            limit: Maximum grants to return, newest first.
        """
        from smallgrants.store import connect

        con = connect(data_dir, read_only=True)
        rows = con.execute(
            """
            SELECT tax_year, recipient_name, recipient_state, amount, purpose
            FROM grants WHERE ein = ? AND COALESCE(amount, 0) >= ?
            ORDER BY tax_year DESC, amount DESC LIMIT ?
            """,
            [ein, min_amount, limit],
        ).fetchall()
        con.close()
        return json.dumps(
            [
                {"year": r[0], "recipient": r[1], "state": r[2], "amount": r[3], "purpose": r[4]}
                for r in rows
            ],
            default=str,
        )

    @beta_tool
    def similar_funders(limit: int = 10) -> str:
        """Find other foundations that funded the same recipients as this one. Call
        this when the user should know about comparable or better-fitting funders.

        Args:
            limit: Maximum foundations to return.
        """
        from smallgrants.store import connect

        con = connect(data_dir, read_only=True)
        rows = con.execute(
            """
            WITH mine AS (SELECT DISTINCT recipient_norm FROM grants WHERE ein = ?)
            SELECT g.ein, any_value(f.name), count(DISTINCT g.recipient_norm) AS shared
            FROM grants g
            JOIN mine m ON m.recipient_norm = g.recipient_norm
            JOIN foundation_signals f ON f.ein = g.ein
            WHERE g.ein <> ? AND NOT f.declared_closed
            GROUP BY g.ein ORDER BY shared DESC LIMIT ?
            """,
            [ein, ein, limit],
        ).fetchall()
        con.close()
        return json.dumps(
            [{"ein": r[0], "name": r[1], "shared_grantees": r[2]} for r in rows]
        )

    client = anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=RESEARCH_SYSTEM,
        output_config={"effort": "high"},
        tools=[grant_history, similar_funders],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Foundation record:\n{json.dumps(profile, indent=2, default=str)}\n\n"
                    f"The applicant's project:\n{project}\n\n"
                    "Research this foundation and report."
                ),
            }
        ],
    )
    final = None
    for message in runner:
        final = message
    if final is None:
        return {"error": "research agent returned nothing"}
    if final.stop_reason == "refusal":
        return {"engine": MODEL, "error": "model declined this request"}
    brief = "\n".join(b.text for b in final.content if b.type == "text")
    return {"engine": MODEL, "ein": ein, "brief": brief, "profile": profile}
