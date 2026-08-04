"""Entity resolution and NTEE enrichment.

Grant recipients are free text with no EIN, so they must be matched back to the
IRS Business Master File by name. Resolution is tiered and every tier's coverage
is measured and reported -- an unresolved recipient is recorded as unresolved,
never silently guessed.
"""

from __future__ import annotations

import os
import re

import httpx

BMF_URLS = [f"https://www.irs.gov/pub/irs-soi/eo{i}.csv" for i in range(1, 5)]

NTEE_MAJOR = {
    "A": "Arts, Culture & Humanities",
    "B": "Education",
    "C": "Environment",
    "D": "Animal-Related",
    "E": "Health Care",
    "F": "Mental Health & Crisis Intervention",
    "G": "Diseases & Disorders",
    "H": "Medical Research",
    "I": "Crime & Legal-Related",
    "J": "Employment",
    "K": "Food, Agriculture & Nutrition",
    "L": "Housing & Shelter",
    "M": "Public Safety & Disaster Relief",
    "N": "Recreation & Sports",
    "O": "Youth Development",
    "P": "Human Services",
    "Q": "International & Foreign Affairs",
    "R": "Civil Rights & Advocacy",
    "S": "Community Improvement",
    "T": "Philanthropy & Voluntarism",
    "U": "Science & Technology",
    "V": "Social Science",
    "W": "Public & Societal Benefit",
    "X": "Religion-Related",
    "Y": "Mutual & Membership Benefit",
    "Z": "Unknown",
}

_SUFFIXES = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "LLC", "LTD",
    "ORGANIZATION", "ORG",
}
# Apostrophes are deleted rather than replaced with a space, so "St. Mary's"
# collapses to "ST MARYS" instead of splitting into "ST MARY S".
_DROP = re.compile(r"['’`]+")
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_WS = re.compile(r"\s+")
_ABBREV = [
    (r"\bSAINT\b", "ST"),
    (r"\bUNIVERSITY\b", "UNIV"),
    (r"\bDEPARTMENT\b", "DEPT"),
    (r"\bASSOCIATION\b", "ASSN"),
    (r"\bSOCIETY\b", "SOC"),
    (r"\bFOUNDATION\b", "FDN"),
    (r"\bINSTITUTE\b", "INST"),
]


def normalize_name(raw: str | None) -> str | None:
    """Canonical form for name matching. Conservative: it collapses formatting
    differences, not semantic ones."""
    if not raw:
        return None
    # Canonicalise on the word AND. "&" and "and" are the same token in practice
    # and appear interchangeably across filings for the same organization.
    s = _DROP.sub("", raw.upper())
    s = s.replace("&", " AND ")
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    if s.startswith("THE "):
        s = s[4:]
    for pattern, repl in _ABBREV:
        s = re.sub(pattern, repl, s)
    parts = [p for p in s.split(" ") if p]
    while parts and parts[-1] in _SUFFIXES:
        parts.pop()
    s = " ".join(parts)
    return s or None


_SQL_SUFFIXES = "INCORPORATED|INC|CORPORATION|CORP|ORGANIZATION|ORG|LLC|LTD|CO"


def norm_name_sql(col: str) -> str:
    """The same transformation as normalize_name(), as a SQL expression.

    Registering normalize_name as a Python UDF makes DuckDB call it once per row;
    on the ~2M-row Business Master File that dominates the whole stage. Expressed
    in SQL it runs vectorized. test_normalization_sql_matches_python keeps the two
    implementations honest.
    """
    e = f"upper({col})"
    e = f"regexp_replace({e}, '[''’`]', '', 'g')"      # apostrophes deleted, not spaced
    e = f"replace({e}, '&', ' AND ')"
    e = f"regexp_replace({e}, '[^A-Z0-9 ]+', ' ', 'g')"
    e = f"trim(regexp_replace({e}, ' +', ' ', 'g'))"
    e = f"regexp_replace({e}, '^THE ', '')"
    for pattern, repl in _ABBREV:
        word = pattern.replace(r"\b", "")
        e = f"regexp_replace({e}, '\\b{word}\\b', '{repl}', 'g')"
    e = f"regexp_replace({e}, '( ({_SQL_SUFFIXES}))+$', '')"
    e = f"regexp_replace({e}, '^({_SQL_SUFFIXES})$', '')"
    return f"nullif({e}, '')"


def download_bmf(data_dir: str) -> list[str]:
    """Fetch the four regional Exempt Organization Business Master File extracts."""
    dest = os.path.join(data_dir, "bmf")
    os.makedirs(dest, exist_ok=True)
    paths = []
    for url in BMF_URLS:
        path = os.path.join(dest, os.path.basename(url))
        if not os.path.exists(path) or os.path.getsize(path) < 1_000_000:
            with httpx.stream("GET", url, timeout=600, follow_redirects=True) as r:
                r.raise_for_status()
                tmp = path + ".part"
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_bytes(1 << 20):
                        fh.write(chunk)
                os.replace(tmp, path)
        paths.append(path)
    return paths


def enrich(data_dir: str, skip_download: bool = False) -> dict:
    """Build the enriched `grants` table and report resolution coverage."""
    from smallgrants.store import connect

    if not skip_download:
        download_bmf(data_dir)
    bmf_glob = os.path.join(data_dir, "bmf", "eo*.csv")

    con = connect(data_dir)
    con.execute(f"CREATE OR REPLACE MACRO norm_name(x) AS ({norm_name_sql('x')})")

    con.execute("DROP TABLE IF EXISTS bmf")
    con.execute(
        f"""
        CREATE TABLE bmf AS
        SELECT
            lpad(CAST(EIN AS VARCHAR), 9, '0') AS ein,
            NAME                               AS name,
            norm_name(NAME)                    AS name_norm,
            CITY                               AS city,
            STATE                              AS state,
            substr(CAST(ZIP AS VARCHAR), 1, 5) AS zip,
            nullif(trim(NTEE_CD), '')          AS ntee
        FROM read_csv('{bmf_glob}', header=true, union_by_name=true,
                      ignore_errors=true, all_varchar=true)
        WHERE NAME IS NOT NULL
        """
    )

    # Name+state is the primary key for matching. Where a normalized name maps to
    # several EINs in one state we cannot tell them apart, so we do not match.
    con.execute("DROP TABLE IF EXISTS bmf_state_unique")
    con.execute(
        """
        CREATE TABLE bmf_state_unique AS
        SELECT name_norm, state, any_value(ein) AS ein, any_value(ntee) AS ntee
        FROM bmf WHERE name_norm IS NOT NULL AND state IS NOT NULL
        GROUP BY name_norm, state HAVING count(DISTINCT ein) = 1
        """
    )
    con.execute("DROP TABLE IF EXISTS bmf_natl_unique")
    con.execute(
        """
        CREATE TABLE bmf_natl_unique AS
        SELECT name_norm, any_value(ein) AS ein, any_value(ntee) AS ntee
        FROM bmf WHERE name_norm IS NOT NULL
        GROUP BY name_norm HAVING count(DISTINCT ein) = 1
        """
    )

    con.execute("DROP TABLE IF EXISTS grants")
    con.execute(
        """
        CREATE TABLE grants AS
        WITH base AS (
            SELECT *, norm_name(recipient_name) AS recipient_norm
            FROM grants_raw
        )
        SELECT
            b.*,
            COALESCE(s.ein, n.ein)              AS recipient_ein,
            COALESCE(s.ntee, n.ntee)            AS recipient_ntee,
            upper(substr(COALESCE(s.ntee, n.ntee), 1, 1)) AS ntee_major,
            CASE
                WHEN b.recipient_is_person   THEN 'individual'
                WHEN s.ein IS NOT NULL       THEN 'name_state'
                WHEN n.ein IS NOT NULL       THEN 'name_national'
                ELSE 'unresolved'
            END                                 AS resolution_tier
        FROM base b
        LEFT JOIN bmf_state_unique s
               ON b.recipient_norm = s.name_norm AND b.recipient_state = s.state
        LEFT JOIN bmf_natl_unique n
               ON b.recipient_norm = n.name_norm AND s.ein IS NULL
        """
    )

    total = con.execute("SELECT count(*) FROM grants").fetchone()[0]
    tiers = dict(
        con.execute(
            "SELECT resolution_tier, count(*) FROM grants GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    )
    with_ntee = con.execute(
        "SELECT count(*) FROM grants WHERE recipient_ntee IS NOT NULL"
    ).fetchone()[0]
    org_grants = total - tiers.get("individual", 0)
    con.close()

    return {
        "grant_records": total,
        "bmf_rows": None,
        **{f"tier_{k}": v for k, v in tiers.items()},
        "org_grants": org_grants,
        "resolved_pct_of_org_grants": (
            round(100 * (org_grants - tiers.get("unresolved", 0)) / org_grants, 1)
            if org_grants
            else 0.0
        ),
        "ntee_coverage_pct": round(100 * with_ntee / total, 1) if total else 0.0,
    }
