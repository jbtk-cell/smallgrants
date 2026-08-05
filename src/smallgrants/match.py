"""Matching and ranking.

Ranking is explicit and auditable. Each component is computed separately, kept on
a 0-1 scale, and returned alongside the result so a user can see why a foundation
placed where it did. There is no opaque blended score the user cannot inspect.

Hard filters remove foundations that cannot fund the user at all. Everything else
is a weighted ranking signal.
"""

from __future__ import annotations

import math
import os

import numpy as np

EMB_FILE = "cause_embeddings.npy"
EMB_INDEX = "cause_embeddings_eins.txt"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

WEIGHTS = {"cause": 0.45, "geography": 0.30, "size": 0.15, "openness": 0.10}

# Purpose strings that carry no information about what a foundation funds.
BOILERPLATE = {
    "", "GENERAL SUPPORT", "GENERAL", "CHARITABLE", "UNRESTRICTED", "GENERAL PURPOSE",
    "GENERAL OPERATIONS", "GENERAL OPERATING SUPPORT", "GENERAL OPERATING", "DONATION",
    "CONTRIBUTION", "N/A", "NONE", "SEE ATTACHED", "GENERAL FUND", "UNRESTRICTED GRANT",
    "CHARITABLE CONTRIBUTION", "GENERAL PURPOSES", "SUPPORT", "PUBLIC CHARITY",
    "CHARITABLE PURPOSES", "GENERAL CHARITABLE PURPOSES", "PROGRAM SUPPORT",
}


def _profile_sql() -> str:
    """Cause-profile text per foundation.

    Built from informative purpose text plus grantee names, because when purpose
    text is boilerplate the grantee's identity still says what gets funded.
    """
    boiler = ",".join(f"'{b}'" for b in sorted(BOILERPLATE) if b)
    return f"""
        WITH purposes AS (
            SELECT ein, upper(trim(purpose)) AS p, count(*) AS n
            FROM grants
            WHERE purpose IS NOT NULL AND upper(trim(purpose)) NOT IN ({boiler})
            GROUP BY 1, 2
        ),
        top_purposes AS (
            SELECT ein, string_agg(p, '. ' ORDER BY n DESC) AS purpose_text
            FROM (SELECT *, row_number() OVER (PARTITION BY ein ORDER BY n DESC) rn FROM purposes)
            WHERE rn <= 12 GROUP BY ein
        ),
        names AS (
            SELECT ein, recipient_name AS nm, count(*) AS n
            FROM grants WHERE recipient_name IS NOT NULL AND NOT recipient_is_person
            GROUP BY 1, 2
        ),
        top_names AS (
            SELECT ein, string_agg(nm, ', ' ORDER BY n DESC) AS name_text
            FROM (SELECT *, row_number() OVER (PARTITION BY ein ORDER BY n DESC) rn FROM names)
            WHERE rn <= 12 GROUP BY ein
        )
        SELECT f.ein,
               COALESCE(tp.purpose_text, '') AS purpose_text,
               COALESCE(tn.name_text, '')    AS name_text,
               f.top_ntee
        FROM foundation_signals f
        LEFT JOIN top_purposes tp ON tp.ein = f.ein
        LEFT JOIN top_names   tn ON tn.ein = f.ein
        WHERE f.grant_count > 0
    """


def build_embeddings(data_dir: str, model_name: str = DEFAULT_MODEL) -> dict:
    from sentence_transformers import SentenceTransformer

    from smallgrants.enrich import NTEE_MAJOR
    from smallgrants.store import connect

    con = connect(data_dir, read_only=True)
    rows = con.execute(_profile_sql()).fetchall()
    con.close()
    if not rows:
        raise RuntimeError("no foundation profiles; run derive first")

    eins, texts = [], []
    for ein, purpose_text, name_text, ntee in rows:
        cause = NTEE_MAJOR.get((ntee or "").upper(), "")
        text = ". ".join(p for p in (cause, purpose_text, name_text) if p).strip()
        if not text:
            continue
        eins.append(ein)
        texts.append(text[:2000])

    model = SentenceTransformer(model_name)
    import sys

    vecs = model.encode(
        texts, batch_size=256, convert_to_numpy=True, normalize_embeddings=True,
        show_progress_bar=sys.stderr.isatty(),  # a bar in a log file is just noise
    ).astype(np.float32)

    np.save(os.path.join(data_dir, EMB_FILE), vecs)
    with open(os.path.join(data_dir, EMB_INDEX), "w") as fh:
        fh.write("\n".join(eins))
    return {
        "foundations_embedded": len(eins),
        "skipped_no_text": len(rows) - len(eins),
        "dimensions": int(vecs.shape[1]),
        "model": model_name,
    }


_MODEL = None
_VECS = None
_EINS = None


def _load(data_dir: str, model_name: str = DEFAULT_MODEL):
    global _MODEL, _VECS, _EINS
    if _VECS is None:
        path = os.path.join(data_dir, EMB_FILE)
        if not os.path.exists(path):
            raise FileNotFoundError("embeddings missing; run `smallgrants embed`")
        _VECS = np.load(path)
        _EINS = open(os.path.join(data_dir, EMB_INDEX)).read().split("\n")
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(model_name)
    return _MODEL, _VECS, _EINS


def _size_fit(amount: int | None, median: float | None, mx: float | None) -> float:
    """1.0 when the ask sits at the foundation's typical grant, decaying with
    distance in log space. Asking far above their largest ever grant scores 0."""
    if amount is None or not median or median <= 0:
        return 0.5
    if mx and amount > mx:
        return 0.0
    return max(0.0, 1.0 - abs(math.log10(amount / median)) / 1.5)


def _geo_score(user_state, user_zip3, top_state, state_share, zip3_hits, state_hits) -> float:
    if user_state is None:
        return 0.5
    if zip3_hits:
        return 1.0
    if state_hits:
        return 0.65 + 0.25 * min(state_share or 0.0, 1.0)
    return 0.0


def search(
    data_dir: str,
    query: str,
    state: str | None = None,
    zip3: str | None = None,
    amount: int | None = None,
    limit: int = 10,
    include_closed: bool = False,
    for_individual: bool = False,
    model_name: str = DEFAULT_MODEL,
) -> list[dict]:
    from smallgrants.store import connect

    model, vecs, eins = _load(data_dir, model_name)
    qvec = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
    sims = vecs @ qvec.astype(np.float32)
    sim_by_ein = {e: float(s) for e, s in zip(eins, sims)}

    con = connect(data_dir, read_only=True)
    state_u = state.upper() if state else None

    # Geographic footprint per candidate, from actual grantee addresses. Scanning
    # only the rows that match the user's geography keeps this small; aggregating
    # every grant in the corpus on each search does not scale.
    footprint_cte = """
        WITH fp AS (
            SELECT ein,
                   count(*) FILTER (WHERE recipient_state = ?)             AS state_hits,
                   count(*) FILTER (WHERE substr(recipient_zip, 1, 3) = ?) AS zip3_hits
            FROM grants
            WHERE recipient_state = ? OR substr(recipient_zip, 1, 3) = ?
            GROUP BY ein
        )
    """
    where = ["f.grant_count > 0"]
    params: list = [state_u, zip3, state_u, zip3]
    if not include_closed:
        where.append("NOT f.declared_closed")
    if for_individual:
        where.append("COALESCE(f.individual_share, 0) > 0.2")
    else:
        where.append("COALESCE(f.individual_share, 1) < 0.9")
    if state_u:
        where.append("COALESCE(fp.state_hits, 0) > 0")
    if amount:
        where.append("(f.max_grant IS NULL OR f.max_grant >= ?)")
        params.append(amount)

    rows = con.execute(
        footprint_cte
        + f"""
        SELECT f.ein, f.name, f.city, f.state, f.zip3, f.median_grant, f.max_grant,
               f.grant_count, f.last_year, f.top_state, f.top_state_share,
               f.openness_ratio, f.declared_closed, f.has_application_info,
               f.app_deadlines, f.app_restrictions, f.app_contact_name,
               f.total_assets_eoy, f.ntee_coverage, f.individual_share,
               COALESCE(fp.state_hits, 0), COALESCE(fp.zip3_hits, 0)
        FROM foundation_signals f
        LEFT JOIN fp ON fp.ein = f.ein
        WHERE {' AND '.join(where)}
        """,
        params,
    ).fetchall()

    scored = []
    for r in rows:
        ein = r[0]
        cause = sim_by_ein.get(ein)
        if cause is None:
            continue
        cause_n = max(0.0, min(1.0, (cause + 1) / 2))
        geo = _geo_score(state_u, zip3, r[9], r[10], r[21], r[20])
        size = _size_fit(amount, r[5], r[6])
        openness = r[11] if r[11] is not None else 0.5
        score = (
            WEIGHTS["cause"] * cause_n
            + WEIGHTS["geography"] * geo
            + WEIGHTS["size"] * size
            + WEIGHTS["openness"] * min(openness * 2, 1.0)
        )
        scored.append((score, cause_n, geo, size, openness, r))

    scored.sort(key=lambda t: -t[0])
    top = scored[:limit]

    results = []
    for score, cause_n, geo, size, openness, r in top:
        ein = r[0]
        evidence = con.execute(
            """
            SELECT recipient_name, amount, tax_year, purpose
            FROM grants WHERE ein = ? AND amount IS NOT NULL
            ORDER BY tax_year DESC, amount DESC LIMIT 5
            """,
            [ein],
        ).fetchall()
        caveats = []
        if r[11] is None:
            caveats.append("Openness unknown: fewer than 3 years of grant history.")
        if (r[18] or 0) < 0.3:
            caveats.append("Cause profile is weak: most grantees could not be classified.")
        if not r[13]:
            caveats.append("Publishes no application instructions on its 990-PF.")
        if r[8] and r[8] < 2023:
            caveats.append(f"Most recent filing is {r[8]}; data may be stale.")
        results.append(
            {
                "ein": ein, "name": r[1], "city": r[2], "state": r[3],
                "median_grant": r[5] or 0, "max_grant": r[6] or 0,
                "grant_count": r[7], "last_year": r[8],
                "openness_ratio": r[11], "declared_closed": r[12],
                "app_deadlines": r[14], "app_restrictions": r[15],
                "app_contact_name": r[16], "total_assets": r[17],
                "score": round(score, 4),
                "components": {
                    "cause": round(cause_n, 3), "geography": round(geo, 3),
                    "size": round(size, 3), "openness": round(openness, 3),
                },
                "evidence": [
                    {"recipient_name": e[0], "amount": e[1], "tax_year": e[2], "purpose": e[3]}
                    for e in evidence
                ],
                "caveats": caveats,
            }
        )
    con.close()
    return results
