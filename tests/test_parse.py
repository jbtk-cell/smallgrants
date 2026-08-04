"""Parser tests against real IRS filings kept as fixtures."""

from __future__ import annotations

import os

import pytest

from smallgrants.enrich import normalize_name
from smallgrants.match import _size_fit
from smallgrants.parse import bool_of, parse_return

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name: str) -> bytes:
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        return fh.read()


def test_rejects_non_990pf():
    """A Form 990 is not a 990-PF and must not enter the corpus."""
    foundation, grants = parse_return(load("not_a_pf.xml"))
    assert foundation is None
    assert grants == []


def test_rejects_garbage():
    assert parse_return(b"not xml at all") == (None, [])
    assert parse_return(b"<Return></Return>") == (None, [])


def test_parses_foundation_identity():
    foundation, _ = parse_return(load("pf_grants_appinfo.xml"))
    assert foundation is not None
    assert foundation["name"]
    assert len(foundation["ein"]) == 9 and foundation["ein"].isdigit()
    assert foundation["tax_year"] and 2000 < foundation["tax_year"] < 2100


def test_extracts_grants_with_amounts():
    foundation, grants = parse_return(load("pf_grants_appinfo.xml"))
    assert len(grants) == 5
    assert foundation["grant_count"] == 5
    assert all(g["ein"] == foundation["ein"] for g in grants)
    assert all(g["amount"] is None or g["amount"] >= 0 for g in grants)
    assert any(g["recipient_name"] for g in grants)


def test_declared_closed_detected():
    """Part XV line 2 is the strongest reachability signal in the filing."""
    foundation, _ = parse_return(load("pf_declared_closed.xml"))
    assert foundation["declared_closed"] is True

    other, _ = parse_return(load("pf_grants_appinfo.xml"))
    assert other["declared_closed"] is False


def test_indicator_absence_is_not_false():
    """Checkbox indicators appear only when true. Absence must read as None, so
    callers can tell 'did not check the box' from an affirmative negative."""
    import xml.etree.ElementTree as ET

    elem = ET.fromstring("<Return><SomeInd>X</SomeInd></Return>")
    assert bool_of(elem, "SomeInd") is True
    assert bool_of(elem, "MissingInd") is None
    elem2 = ET.fromstring("<Return><SomeInd>false</SomeInd></Return>")
    assert bool_of(elem2, "SomeInd") is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("The Smith Foundation, Inc.", "SMITH FDN"),
        ("SMITH FOUNDATION INC", "SMITH FDN"),
        ("Smith  Foundation", "SMITH FDN"),
        ("St. Mary's Hospital", "ST MARYS HOSPITAL"),
        ("Saint Marys Hospital", "ST MARYS HOSPITAL"),
        ("Boys & Girls Club", "BOYS AND GIRLS CLUB"),
        ("Boys and Girls Club", "BOYS AND GIRLS CLUB"),
        ("", None),
        (None, None),
    ],
)
def test_name_normalization_collapses_formatting(raw, expected):
    assert normalize_name(raw) == expected


def test_name_normalization_keeps_distinct_orgs_distinct():
    """Normalization must not merge organizations that are genuinely different."""
    assert normalize_name("Yale University") != normalize_name("Yale New Haven Hospital")
    assert normalize_name("American Red Cross") != normalize_name("American Cancer Society")


def test_size_fit_scoring():
    # Asking exactly the typical grant is a perfect fit.
    assert _size_fit(5000, 5000, 50000) == pytest.approx(1.0)
    # Asking above their largest grant ever is impossible.
    assert _size_fit(100000, 5000, 50000) == 0.0
    # Unknown ask is neutral, not disqualifying.
    assert _size_fit(None, 5000, 50000) == 0.5
    # An order of magnitude off is penalised but not zeroed.
    assert 0 < _size_fit(500, 5000, 50000) < 1.0
