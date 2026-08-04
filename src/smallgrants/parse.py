"""Parse IRS Form 990-PF e-file XML into normalized records.

Design note: the IRS efile schema changes between tax years. Extracting by fixed
XPath breaks on older filings. Instead we locate elements by local name within a
scoped subtree, which is stable across schema versions.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Iterator

# Grants actually paid during the year. Deliberately NOT
# GrantOrContributionApprvFutPaymtGrp, which is money approved but unpaid.
GRANTS_PAID_TAG = "GrantOrContributionPdDurYrGrp"


def local(tag: str) -> str:
    """Strip the {namespace} prefix ElementTree prepends."""
    return tag.rsplit("}", 1)[-1]


def find_first(elem: ET.Element | None, name: str) -> ET.Element | None:
    """First descendant (or self) with the given local name."""
    if elem is None:
        return None
    if local(elem.tag) == name:
        return elem
    for child in elem.iter():
        if local(child.tag) == name:
            return child
    return None


def text_of(elem: ET.Element | None, name: str) -> str | None:
    node = find_first(elem, name)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def int_of(elem: ET.Element | None, name: str) -> int | None:
    raw = text_of(elem, name)
    if raw is None:
        return None
    try:
        return int(float(raw.replace(",", "")))
    except ValueError:
        return None


def bool_of(elem: ET.Element | None, name: str) -> bool | None:
    """IRS indicator elements.

    Checkbox-style indicators ('X') are only present when true, so absence means
    'not checked', which is NOT the same as an affirmative false. Callers must
    distinguish None from False.
    """
    raw = text_of(elem, name)
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "x", "yes"}


def _address(elem: ET.Element | None) -> dict[str, str | None]:
    return {
        "address": text_of(elem, "AddressLine1Txt"),
        "city": text_of(elem, "CityNm"),
        "state": text_of(elem, "StateAbbreviationCd"),
        "zip": (text_of(elem, "ZIPCd") or "")[:5] or None,
    }


def _recipient_name(block: ET.Element) -> tuple[str | None, bool]:
    """Return (name, is_person). Recipients may be organizations or individuals."""
    business = find_first(block, "RecipientBusinessName")
    if business is not None:
        line1 = text_of(business, "BusinessNameLine1Txt")
        line2 = text_of(business, "BusinessNameLine2Txt")
        name = " ".join(p for p in (line1, line2) if p)
        if name:
            return name, False
    person = text_of(block, "RecipientPersonNm")
    if person:
        return person, True
    return None, False


def parse_return(xml_bytes: bytes, source: str = "") -> tuple[dict | None, list[dict]]:
    """Parse one filing. Returns (foundation, grants); (None, []) if not a 990-PF."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None, []

    header = find_first(root, "ReturnHeader")
    if header is None:
        return None, []
    if (text_of(header, "ReturnTypeCd") or "").upper() != "990PF":
        return None, []

    pf = find_first(root, "IRS990PF")
    if pf is None:
        return None, []

    filer = find_first(header, "Filer")
    ein = text_of(filer, "EIN")
    if not ein:
        return None, []

    name_node = find_first(filer, "BusinessName")
    line1 = text_of(name_node, "BusinessNameLine1Txt")
    line2 = text_of(name_node, "BusinessNameLine2Txt")
    addr = _address(find_first(filer, "USAddress"))

    tax_year = int_of(header, "TaxYr")
    period_end = text_of(header, "TaxPeriodEndDt")
    if tax_year is None and period_end:
        tax_year = int(period_end[:4])

    supplementary = find_first(pf, "SupplementaryInformationGrp")
    app_info = find_first(supplementary, "ApplicationSubmissionInfoGrp")

    balance = find_first(pf, "Form990PFBalanceSheetsGrp")
    analysis = find_first(pf, "AnalysisOfRevenueAndExpenses")
    activity = find_first(pf, "StatementsRegardingActy4720Grp")

    foundation = {
        "ein": ein.zfill(9),
        "tax_year": tax_year,
        "period_end": period_end,
        "name": " ".join(p for p in (line1, line2) if p),
        "in_care_of": text_of(filer, "InCareOfNm"),
        "phone": text_of(filer, "PhoneNum"),
        "address": addr["address"],
        "city": addr["city"],
        "state": addr["state"],
        "zip": addr["zip"],
        "total_assets_eoy": int_of(balance, "TotalAssetsEOYAmt"),
        "assets_fmv_eoy": int_of(balance, "TotalAssetsEOYFMVAmt"),
        "total_grants_paid": int_of(analysis, "ContriPaidRevAndExpnssAmt"),
        "grants_to_individuals": bool_of(activity, "GrantsToIndividualsInd"),
        "grants_to_organizations": bool_of(activity, "GrantsToOrganizationsInd"),
        # Part XV line 2: checked when the foundation only funds preselected
        # organizations and accepts no unsolicited requests. Absence means the
        # box was not checked, which is weaker than an affirmative "we are open".
        "only_preselected": bool_of(pf, "OnlyContriToPreselectedInd") is True,
        "declared_closed": bool_of(pf, "OnlyContriToPreselectedInd") is True,
        # Application instructions the foundation chose to publish.
        "app_contact_name": text_of(app_info, "RecipientPersonNm")
        or text_of(find_first(app_info, "RecipientBusinessName"), "BusinessNameLine1Txt"),
        "app_contact_phone": text_of(app_info, "RecipientPhoneNum"),
        "app_form_required": text_of(app_info, "FormAndInfoAndMaterialsTxt")
        or text_of(app_info, "ApplicationFormRequiredTxt"),
        "app_deadlines": text_of(app_info, "SubmissionDeadlinesTxt"),
        "app_restrictions": text_of(app_info, "RestrictionsOnAwardsTxt"),
        "has_application_info": app_info is not None,
        "source_archive": source,
    }

    grants: list[dict] = []
    scope = supplementary if supplementary is not None else pf
    for block in scope.iter():
        if local(block.tag) != GRANTS_PAID_TAG:
            continue
        recipient, is_person = _recipient_name(block)
        raddr = _address(find_first(block, "RecipientUSAddress"))
        amount = int_of(block, "Amt")
        grants.append(
            {
                "ein": foundation["ein"],
                "tax_year": tax_year,
                "recipient_name": recipient,
                "recipient_is_person": is_person,
                "recipient_city": raddr["city"],
                "recipient_state": raddr["state"],
                "recipient_zip": raddr["zip"],
                "relationship": text_of(block, "RecipientRelationshipTxt"),
                "recipient_status": text_of(block, "RecipientFoundationStatusTxt"),
                "purpose": text_of(block, "GrantOrContributionPurposeTxt"),
                "amount": amount,
            }
        )

    foundation["grant_count"] = len(grants)
    return foundation, grants


def iter_archive(path: str) -> Iterator[tuple[str, bytes]]:
    """Yield (member_name, xml_bytes) from a filings archive without extracting."""
    import zipfile

    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.filename.lower().endswith(".xml"):
                yield info.filename, zf.read(info)


def parse_archive(path: str) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Parse every 990-PF in one archive. Returns (foundations, grants, stats)."""
    import os

    source = os.path.basename(path)
    foundations: list[dict] = []
    grants: list[dict] = []
    total = 0
    for _, blob in iter_archive(path):
        total += 1
        foundation, rows = parse_return(blob, source)
        if foundation is None:
            continue
        foundations.append(foundation)
        grants.extend(rows)
    stats = {
        "archive": source,
        "filings_seen": total,
        "pf_filings": len(foundations),
        "grant_records": len(grants),
        "pf_with_grants": sum(1 for f in foundations if f["grant_count"] > 0),
        "declared_closed": sum(1 for f in foundations if f["declared_closed"]),
        "with_application_info": sum(1 for f in foundations if f["has_application_info"]),
    }
    return foundations, grants, stats
