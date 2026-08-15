"""Regression tests for defects found in adversarial review.

Each test here corresponds to a specific wrong answer the product gave a user.
"""

from __future__ import annotations

import pytest

from smallgrants.agents import (
    _EXCLUDES_INDIVIDUALS,
    Finding,
    _resolve_verdict,
    _rule_findings,
    _states_named,
    _verdict_from,
)
from smallgrants.match import _geo_score, _openness_score


def severities(findings, claim_contains):
    return [f.severity for f in findings if claim_contains.lower() in f.claim.lower()]


# --- "NO GRANTS TO INDIVIDUALS" used to disqualify organizations -------------


def test_excludes_individuals_is_not_read_as_individuals_only():
    """53% of the old disqualifying flags were foundations giving individuals
    nothing at all, because the word "individuals" was matched bare."""
    excluding = {
        "NO GRANTS TO INDIVIDUALS OR NON-U.S. INSTITUTIONS",
        "GRANTS LIMITED TO TAX-EXEMPT ORGANIZATIONS WITHIN OREGON. NO GRANTS TO INDIVIDUALS",
        "Individuals are not eligible.",
        "Applications from organizations only.",
    }
    for text in excluding:
        assert _EXCLUDES_INDIVIDUALS.search(text), text


def test_org_not_disqualified_by_a_no_individuals_restriction():
    profile = {
        "app_restrictions": "NO GRANTS TO INDIVIDUALS OR NON-U.S. INSTITUTIONS.",
        "individual_share": 0.0,
        "grant_count": 1169,
        "declared_closed": False,
        "has_application_info": True,
        "last_year": 2025,
    }
    findings = _rule_findings(profile, {"applicant_type": "organization", "state": "CA"})
    assert "disqualifying" not in [f.severity for f in findings]
    assert "Do not send" not in _verdict_from(findings)


def test_individual_is_disqualified_by_a_no_individuals_restriction():
    """The converse check did not exist, so an individual was told there was no
    disqualifying problem at a foundation that refuses individuals outright."""
    profile = {
        "app_restrictions": "NO GRANTS TO INDIVIDUALS OR NON-U.S. INSTITUTIONS.",
        "individual_share": 0.0,
        "grant_count": 1169,
        "declared_closed": False,
        "has_application_info": True,
        "last_year": 2025,
    }
    findings = _rule_findings(profile, {"applicant_type": "individual", "state": "CA"})
    assert "disqualifying" in [f.severity for f in findings]
    assert "Do not send" in _verdict_from(findings)


def test_org_still_disqualified_by_a_genuine_scholarship_fund():
    profile = {
        "app_restrictions": "SCHOLARSHIPS AWARDED TO GRADUATING SENIORS FOR TUITION.",
        "individual_share": 1.0,
        "grant_count": 40,
        "declared_closed": False,
        "has_application_info": True,
        "last_year": 2025,
    }
    findings = _rule_findings(profile, {"applicant_type": "organization", "state": "KS"})
    assert "disqualifying" in [f.severity for f in findings]


# --- state matching compared a 2-letter code against spelled-out names -------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("GRANTS LIMITED GEOGRAPHICALLY TO THE STATE OF TEXAS.", {"TX"}),
        ("...WITHIN THE STATE OF MARYLAND...", {"MD"}),
        ("Programs in the state of Oregon", {"OR"}),
        ("LOCATED IN THE STATE OF WISCONSIN", {"WI"}),
        ("No geographic limit stated.", set()),
    ],
)
def test_state_names_are_detected_properly(text, expected):
    assert _states_named(text) == expected


def test_home_state_applicant_is_not_warned_off():
    """"tx" is not a substring of "state of texas", so Texas applicants used to
    be warned that a Texas-only foundation might exclude them."""
    profile = {
        "app_restrictions": "GRANTS LIMITED GEOGRAPHICALLY TO THE STATE OF TEXAS.",
        "individual_share": 0.0, "grant_count": 50, "declared_closed": False,
        "has_application_info": True, "last_year": 2025,
    }
    assert not severities(
        _rule_findings(profile, {"applicant_type": "organization", "state": "TX"}),
        "restrictions name",
    )


def test_out_of_state_applicant_is_warned():
    """"in" IS a substring of "in the state of oregon", so Indiana applicants
    used to get no warning from an Oregon-only foundation."""
    profile = {
        "app_restrictions": "GRANTS MADE IN THE STATE OF OREGON",
        "individual_share": 0.0, "grant_count": 50, "declared_closed": False,
        "has_application_info": True, "last_year": 2025,
    }
    assert severities(
        _rule_findings(profile, {"applicant_type": "organization", "state": "IN"}),
        "restrictions name",
    ) == ["serious"]


# --- geography scored the foundation's own concentration, not the user's -----


def test_geo_rewards_giving_in_the_users_state_not_elsewhere():
    """A foundation with 1 New York grant out of 162 (91% Tennessee) outranked
    one with 34 of 45 in New York."""
    mostly_elsewhere = _geo_score("NY", None, state_hits=1, zip3_hits=0, grant_count=162)
    mostly_here = _geo_score("NY", None, state_hits=34, zip3_hits=0, grant_count=45)
    assert mostly_here > mostly_elsewhere
    assert mostly_elsewhere < 0.4


def test_geo_zero_when_never_funded_the_state():
    assert _geo_score("NY", None, 0, 0, 100) == 0.0


def test_geo_neutral_without_geography():
    assert _geo_score(None, None, 0, 0, 100) == 0.5


# --- unknown openness scored the maximum ------------------------------------


def test_unknown_openness_does_not_score_top():
    """Unknown mapped to 0.5 and was then doubled to 1.0, so the least-observed
    foundations got a perfect sub-score."""
    unknown = _openness_score(None)
    best = _openness_score(0.95)
    median = _openness_score(0.318)
    assert unknown < best
    assert unknown < median
    assert best <= 1.0


# --- people typed into the business-name field ------------------------------
#
# `individual_share` only counts recipients the filer put in the person field.
# Scholarship trusts routinely type the student into the business field, so the
# Myra Deane Memorial Trust -- ten grants, every one to a named person -- was
# recorded as 0% individuals. 869 foundations and 25,083 grants are affected.


def scholarship_trust(**over):
    """Recorded as 0% individuals; every recipient is actually a person."""
    p = {
        "app_restrictions": "", "individual_share": 0.0, "person_share": 0.95,
        "unresolved_share": 0.95, "grant_count": 40, "declared_closed": False,
        "has_application_info": True, "last_year": 2025,
    }
    p.update(over)
    return p


def test_individual_is_not_turned_away_from_a_scholarship_trust():
    """The critic said "It has never recorded a grant to an individual" -- a
    disqualifying verdict -- to an individual asking a fund that gives to
    nothing but individuals."""
    findings = _rule_findings(
        scholarship_trust(), {"applicant_type": "individual", "state": "MD"}
    )
    assert "disqualifying" not in [f.severity for f in findings]
    assert "Do not send" not in _verdict_from(findings)
    assert any("fund individuals" in f.claim for f in findings)


def test_organization_is_warned_about_a_scholarship_trust():
    findings = _rule_findings(
        scholarship_trust(), {"applicant_type": "organization", "state": "MD"}
    )
    assert severities(findings, "go to individuals") == ["serious"]


def test_never_funded_an_individual_needs_an_identified_record():
    """Asserting a negative from a record that is 40% unidentified overstates
    what the filing supports."""
    murky = scholarship_trust(person_share=0.0, unresolved_share=0.6, grant_count=30)
    assert severities(murky := _rule_findings(
        murky, {"applicant_type": "individual", "state": "MD"}), "record is incomplete"
    ) == ["worth_checking"]

    clear = scholarship_trust(person_share=0.0, unresolved_share=0.05, grant_count=30)
    assert severities(
        _rule_findings(clear, {"applicant_type": "individual", "state": "MD"}),
        "no record of a grant to an individual",
    ) == ["disqualifying"]


# --- the model could overwrite what the foundation filed about itself --------

OPTIMISTIC = "This is a strong fit. Send it."


def rule(severity):
    return Finding(severity=severity, claim=f"a {severity} fact", evidence="from the filing")


def model(severity):
    return Finding(
        severity=severity, claim=f"model says {severity}", evidence="inferred", source="model"
    )


def test_model_cannot_talk_past_a_disqualifying_filing_fact():
    """The critic used to return the model's list instead of its own, so a
    foundation that had filed "no unsolicited requests" became "send it"."""
    assert _resolve_verdict(OPTIMISTIC, [rule("disqualifying")], []) == (
        "Do not send this. At least one disqualifying problem is on the record."
    )


def test_model_cannot_talk_past_a_serious_filing_fact():
    """The first fix only guarded the disqualifying tier, so a serious fact off
    the filing still sat under an optimistic headline."""
    assert _resolve_verdict(OPTIMISTIC, [rule("serious")], []) == (
        "Send only after resolving the serious problems below."
    )


def test_model_cannot_talk_past_a_worth_checking_filing_fact():
    assert _resolve_verdict(OPTIMISTIC, [rule("worth_checking")], []) != OPTIMISTIC


def test_model_keeps_its_own_verdict_when_it_is_no_gentler():
    assert _resolve_verdict(OPTIMISTIC, [rule("serious")], [model("serious")]) == OPTIMISTIC
    assert _resolve_verdict(OPTIMISTIC, [rule("serious")], [model("disqualifying")]) == OPTIMISTIC
    assert _resolve_verdict(OPTIMISTIC, [], []) == OPTIMISTIC


def test_a_clean_record_does_not_invent_a_problem():
    assert _resolve_verdict("Nothing found.", [], [model("serious")]) == "Nothing found."


# --- web input handling: each of these was an unauthenticated 500 or an
# --- inverted filter before review --------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3000", 3000),
        ("", None),
        ("  ", None),
        ("²", None),          # '²'.isdigit() is True but int('²') raises
        ("٣", None),          # Arabic-Indic digit silently parsed as 3
        ("9" * 5000, None),   # int() refuses >4300 digits
        ("-5", None),
        ("0", None),
        ("abc", None),
    ],
)
def test_amount_parsing_never_raises(raw, expected):
    from smallgrants.app import _int_or_none

    assert _int_or_none(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("1", True), ("true", True), ("on", True), ("", False),
     ("0", False), ("false", False), ("off", False)],
)
def test_include_closed_flag(raw, expected):
    """bool("false") is True, so include_closed=false used to surface exactly the
    foundations the user asked to exclude."""
    from smallgrants.app import _flag

    assert _flag(raw) is expected


# --- pre-launch security checks ---------------------------------------------
#
# There is no login on this site, so the expensive path is search itself: each
# one embeds the query and scans 8.4M rows, roughly 0.8s of CPU. Unthrottled,
# one script holds the site down.


def test_search_rate_limit_trips_and_is_per_address():
    from smallgrants import app as A

    A._searches.clear()
    allowed = [not A.search_rate_limited("1.2.3.4") for _ in range(A.SEARCHES_PER_MINUTE)]
    assert all(allowed)
    assert A.search_rate_limited("1.2.3.4") is True
    # A different visitor is unaffected by the first one's burst.
    assert A.search_rate_limited("5.6.7.8") is False
    A._searches.clear()


def test_proxy_header_is_ignored_unless_the_deployment_opts_in(monkeypatch):
    """Trusting x-forwarded-for by default lets anyone forge it and skip the
    limit. Ignoring it behind a proxy puts every visitor in one bucket."""
    from smallgrants import app as A

    class R:
        headers = {"x-forwarded-for": "9.9.9.9"}
        client = type("C", (), {"host": "10.0.0.1"})()

    monkeypatch.delenv("SMALLGRANTS_TRUST_PROXY", raising=False)
    assert A.client_key(R()) == "10.0.0.1"
    monkeypatch.setenv("SMALLGRANTS_TRUST_PROXY", "1")
    assert A.client_key(R()) == "9.9.9.9"


# --- the one field that separates reach from discovery ----------------------


def test_applying_records_whether_the_funder_was_new(tmp_path):
    """Without this answer the log can only ever say people visited. It cannot
    be reconstructed later, so it is asked at the click or not at all."""
    from smallgrants import usage

    d = str(tmp_path)
    usage.record(d, "applying", None, ein="111", already_knew=0)
    usage.record(d, "applying", None, ein="222", already_knew=0)
    usage.record(d, "applying", None, ein="111", already_knew=1)
    s = usage.stats(d, include_bots=True)["discovery"]
    assert s["reported_applying"] == 3
    assert s["funder_was_new_to_them"] == 2
    assert s["distinct_funders_newly_found"] == 2


def test_unanswered_is_not_counted_as_new(tmp_path):
    """A skipped question must not inflate the discovery number."""
    from smallgrants import usage

    d = str(tmp_path)
    usage.record(d, "applying", None, ein="111", already_knew=None)
    s = usage.stats(d, include_bots=True)["discovery"]
    assert s["reported_applying"] == 1
    assert s["funder_was_new_to_them"] == 0


def test_usage_log_written_before_the_column_existed_still_works(tmp_path):
    """An older log must migrate rather than throw on every request."""
    import sqlite3

    from smallgrants import usage

    d = str(tmp_path)
    con = sqlite3.connect(usage.db_path(d))
    con.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,"
        " day TEXT NOT NULL, event TEXT NOT NULL, visitor TEXT,"
        " is_bot INTEGER NOT NULL DEFAULT 0, query TEXT, state TEXT, amount INTEGER,"
        " applicant TEXT, results INTEGER, ein TEXT, source TEXT)"
    )
    con.commit()
    con.close()
    usage.record(d, "applying", None, ein="111", already_knew=0)
    assert usage.stats(d, include_bots=True)["discovery"]["funder_was_new_to_them"] == 1
