"""Regression tests for defects found in adversarial review.

Each test here corresponds to a specific wrong answer the product gave a user.
"""

from __future__ import annotations

import pytest

from smallgrants.agents import (
    _EXCLUDES_INDIVIDUALS,
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
