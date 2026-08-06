"""Per-foundation signals, and validation of the openness ratio.

The openness ratio is the share of a year's grantees that the foundation had not
funded in any prior year. It is proposed as a behavioural proxy for "does this
foundation take on new grantees". Because roughly 70% of filers also declare
outright whether they accept unsolicited requests, that declaration gives us a
labelled set to validate the proxy against -- see validate_openness().
"""

from __future__ import annotations

import statistics

# Words that mark a recipient name as an organization. Used only to decide
# whether an *unresolved* name has the shape of a person's name.
_ORG_WORDS = """FOUNDATION INC INCORPORATED TRUST CHURCH UNIVERSITY COLLEGE SCHOOL
ACADEMY ASSOCIATION ASSN SOCIETY CENTER CENTRE COUNCIL FUND CLUB CORP CORPORATION
COMPANY INSTITUTE MUSEUM LIBRARY HOSPITAL CLINIC MINISTRIES MINISTRY MISSION TEMPLE
SYNAGOGUE PARISH DIOCESE CATHEDRAL CHAPEL ALLIANCE COALITION NETWORK PROJECT PROGRAM
SERVICES SERVICE ORGANIZATION ORG LLC LTD DEPT DEPARTMENT CITY TOWN COUNTY STATE
DISTRICT BOARD COMMITTEE COMMISSION AUTHORITY AGENCY AMERICAN NATIONAL INTERNATIONAL
UNITED FRIENDS HOUSE HOME CARE HEALTH MEDICAL CANCER CHILDRENS CHILDREN YOUTH FAMILY
FAMILIES ARTS ART MUSIC THEATRE THEATER ORCHESTRA BALLET OPERA PUBLIC RADIO
TELEVISION PRESS SCOUTS SCOUT LEAGUE SEMINARY YMCA YWCA SPCA HUMANE ANIMAL RESCUE
HOSPICE RELIEF GROUP PARTNERS PARTNERSHIP ENTERPRISES INDUSTRIES SYSTEMS SOLUTIONS
INSTITUTION ST SAINT THE OF AND FOR A AN""".split()


def person_shape_sql(col: str = "recipient_name") -> str:
    """SQL for "this unresolved recipient name has the shape of a person's name".

    Filers routinely type a person into the business-name field, so
    `recipient_is_person` misses them: a scholarship trust paying "BRUCE SIMON"
    and "WILLIAM TYLER" was recorded as 0% individuals. Two or three alphabetic
    tokens with no organization word is the discriminating shape. Measured
    against 3.9M recipients matched to the IRS business master file, it
    misfires on 0.001% of them.
    """
    return f"""(
        {col} IS NOT NULL
        AND NOT regexp_matches({col}, '[0-9&/,]')
        AND array_length(str_split(trim(upper({col})), ' ')) BETWEEN 2 AND 3
        AND NOT list_has_any(str_split(trim(upper({col})), ' '), {_ORG_WORDS!r})
    )"""


def derive(data_dir: str) -> dict:
    from smallgrants.store import connect

    con = connect(data_dir)

    # Grantee identity: resolved EIN where we have it, normalized name otherwise.
    con.execute("DROP TABLE IF EXISTS grantee_keys")
    con.execute(
        """
        CREATE TABLE grantee_keys AS
        SELECT *, COALESCE(recipient_ein, recipient_norm) AS grantee_key
        FROM grants
        WHERE COALESCE(recipient_ein, recipient_norm) IS NOT NULL
          -- Organizations only. Counting individuals made openness a scholarship
          -- detector: a fund paying a fresh cohort of students each year scores
          -- near 1.0, and the top 500 by openness averaged 65% individual grants
          -- against a corpus average of 19% -- the opposite of "an organization
          -- can apply here", which is the question the signal exists to answer.
          AND NOT is_individual
        """
    )

    # Latest filing per foundation supplies identity and declared status.
    con.execute("DROP TABLE IF EXISTS foundation_latest")
    con.execute(
        """
        CREATE TABLE foundation_latest AS
        SELECT * EXCLUDE (_rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY ein ORDER BY tax_year DESC) AS _rn
            FROM filings
        ) WHERE _rn = 1
        """
    )

    con.execute("DROP TABLE IF EXISTS foundation_signals")
    con.execute(
        """
        CREATE TABLE foundation_signals AS
        WITH gstats AS (
            SELECT
                ein,
                count(*)                                        AS grant_count,
                count(DISTINCT tax_year)                        AS grant_years,
                median(amount) FILTER (WHERE amount IS NOT NULL)                                  AS median_grant,
                min(amount)                                     AS min_grant,
                max(amount)                                     AS max_grant,
                sum(amount)                                     AS total_granted,
                quantile_cont(amount, 0.25) FILTER (WHERE amount IS NOT NULL)                     AS p25_grant,
                quantile_cont(amount, 0.75) FILTER (WHERE amount IS NOT NULL)                     AS p75_grant,
                avg(CASE WHEN is_individual THEN 1.0 ELSE 0.0 END) AS individual_share,
                -- individual_share only counts recipients the filer put in the
                -- person field. person_share adds unresolved names shaped like a
                -- person's, which is how scholarship trusts actually file.
                avg(CASE WHEN is_individual
                          OR (resolution_tier = 'unresolved' AND """ + person_shape_sql() + """)
                         THEN 1.0 ELSE 0.0 END)                 AS person_share,
                avg(CASE WHEN resolution_tier = 'unresolved' THEN 1.0 ELSE 0.0 END)
                                                                AS unresolved_share,
                count(DISTINCT recipient_state)                 AS states_funded
            FROM grants g
            GROUP BY ein
        ),
        -- Geographic concentration. Computed with a window rather than a
        -- correlated subquery: the correlated form re-scans the grants table once
        -- per foundation, which does not finish at corpus scale.
        state_counts AS (
            SELECT ein, recipient_state, count(*) AS n
            FROM grants WHERE recipient_state IS NOT NULL
            GROUP BY ein, recipient_state
        ),
        geo AS (
            SELECT ein, recipient_state AS top_state, top_state_share
            FROM (
                SELECT ein, recipient_state,
                       n::DOUBLE / sum(n) OVER (PARTITION BY ein) AS top_state_share,
                       row_number() OVER (PARTITION BY ein ORDER BY n DESC) AS rn
                FROM state_counts
            ) WHERE rn = 1
        ),
        causes AS (
            SELECT ein,
                   mode(ntee_major) AS top_ntee,
                   count(DISTINCT ntee_major) AS ntee_variety,
                   avg(CASE WHEN ntee_major IS NOT NULL THEN 1.0 ELSE 0.0 END) AS ntee_coverage
            FROM grants GROUP BY ein
        ),
        filing_span AS (
            SELECT ein, min(tax_year) AS first_year, max(tax_year) AS last_year,
                   count(DISTINCT tax_year) AS years_filed
            FROM filings GROUP BY ein
        )
        SELECT
            l.ein, l.name, l.city, l.state, l.zip,
            substr(l.zip, 1, 3)              AS zip3,
            l.total_assets_eoy, l.assets_fmv_eoy, l.total_grants_paid,
            l.declared_closed,
            l.has_application_info, l.app_deadlines, l.app_restrictions,
            l.app_contact_name, l.app_contact_phone,
            l.grants_to_individuals, l.grants_to_organizations,
            s.first_year, s.last_year, s.years_filed,
            g.grant_count, g.grant_years, g.median_grant, g.min_grant, g.max_grant,
            g.total_granted, g.p25_grant, g.p75_grant,
            g.individual_share, g.person_share, g.unresolved_share,
            g.states_funded, geo.top_state, geo.top_state_share,
            c.top_ntee, c.ntee_variety, c.ntee_coverage
        FROM foundation_latest l
        LEFT JOIN gstats      g ON g.ein = l.ein
        LEFT JOIN geo           ON geo.ein = l.ein
        LEFT JOIN causes      c ON c.ein = l.ein
        LEFT JOIN filing_span s ON s.ein = l.ein
        """
    )

    # Openness ratio: needs at least three observed grant years.
    con.execute("DROP TABLE IF EXISTS openness")
    con.execute(
        """
        CREATE TABLE openness AS
        WITH per_year AS (
            SELECT ein, tax_year, grantee_key,
                   min(tax_year) OVER (PARTITION BY ein, grantee_key) AS first_seen
            FROM (SELECT DISTINCT ein, tax_year, grantee_key FROM grantee_keys)
        ),
        yearly AS (
            SELECT ein, tax_year,
                   count(*) AS grantees,
                   sum(CASE WHEN tax_year = first_seen THEN 1 ELSE 0 END) AS new_grantees
            FROM per_year GROUP BY ein, tax_year
        ),
        eligible AS (
            SELECT ein, min(tax_year) AS base_year, count(*) AS yrs
            FROM yearly GROUP BY ein HAVING count(*) >= 3
        )
        SELECT y.ein,
               sum(y.new_grantees)::DOUBLE / nullif(sum(y.grantees), 0) AS openness_ratio,
               sum(y.grantees) AS grantee_slots,
               e.yrs AS observed_years
        FROM yearly y
        JOIN eligible e ON e.ein = y.ein
        WHERE y.tax_year > e.base_year      -- the first year is all-new by definition
        GROUP BY y.ein, e.yrs
        """
    )

    con.execute("ALTER TABLE foundation_signals ADD COLUMN IF NOT EXISTS openness_ratio DOUBLE")
    con.execute("ALTER TABLE foundation_signals ADD COLUMN IF NOT EXISTS openness_years INTEGER")
    con.execute(
        """
        UPDATE foundation_signals f
        SET openness_ratio = o.openness_ratio, openness_years = o.observed_years
        FROM openness o WHERE o.ein = f.ein
        """
    )

    # There was no index anywhere in the corpus; every evidence lookup and every
    # profile read was a full scan of an 8M-row table.
    con.execute("CREATE INDEX IF NOT EXISTS grants_ein ON grants (ein)")
    con.execute("CREATE INDEX IF NOT EXISTS signals_ein ON foundation_signals (ein)")

    out = {
        "foundations": con.execute("SELECT count(*) FROM foundation_signals").fetchone()[0],
        "with_grants": con.execute(
            "SELECT count(*) FROM foundation_signals WHERE grant_count > 0"
        ).fetchone()[0],
        "declared_closed": con.execute(
            "SELECT count(*) FROM foundation_signals WHERE declared_closed"
        ).fetchone()[0],
        "with_application_info": con.execute(
            "SELECT count(*) FROM foundation_signals WHERE has_application_info"
        ).fetchone()[0],
        "openness_computed": con.execute(
            "SELECT count(*) FROM foundation_signals WHERE openness_ratio IS NOT NULL"
        ).fetchone()[0],
    }
    con.close()
    return out


def validate_openness(data_dir: str) -> dict:
    """Test the openness ratio against foundations' own declared status.

    Hypothesis: foundations that declare they accept no unsolicited requests
    should show lower grantee turnover than those that do not.

    If the two groups' distributions are indistinguishable, the ratio carries no
    information about reachability and must not be shipped as if it does.
    """
    from smallgrants.store import connect

    con = connect(data_dir, read_only=True)
    rows = con.execute(
        """
        SELECT declared_closed, openness_ratio, grant_count
        FROM foundation_signals
        WHERE openness_ratio IS NOT NULL AND grant_count >= 5
        """
    ).fetchall()
    con.close()

    closed = [r[1] for r in rows if r[0]]
    other = [r[1] for r in rows if not r[0]]
    if len(closed) < 30 or len(other) < 30:
        return {
            "verdict": "INSUFFICIENT DATA",
            "closed_n": len(closed),
            "not_declared_n": len(other),
        }

    m_closed, m_other = statistics.mean(closed), statistics.mean(other)
    sd_closed, sd_other = statistics.pstdev(closed), statistics.pstdev(other)
    pooled = ((sd_closed**2 + sd_other**2) / 2) ** 0.5
    cohens_d = (m_other - m_closed) / pooled if pooled else 0.0

    # Welch's t, normal approximation. Two-sided.
    se = (sd_closed**2 / len(closed) + sd_other**2 / len(other)) ** 0.5
    t = (m_other - m_closed) / se if se else 0.0

    if abs(cohens_d) < 0.2:
        verdict = "NO USABLE SIGNAL - do not ship openness ratio as a reachability proxy"
    elif abs(cohens_d) < 0.5:
        verdict = "WEAK SIGNAL - usable only as a tiebreaker, must be labelled as weak"
    else:
        verdict = "SIGNAL CONFIRMED - openness ratio tracks declared status"

    return {
        "verdict": verdict,
        "closed_n": len(closed),
        "closed_mean_openness": round(m_closed, 4),
        "not_declared_n": len(other),
        "not_declared_mean_openness": round(m_other, 4),
        "difference": round(m_other - m_closed, 4),
        "cohens_d": round(cohens_d, 3),
        "welch_t": round(t, 2),
        "interpretation": (
            "Positive difference means foundations that did NOT declare themselves "
            "closed take on proportionally more new grantees, which is the direction "
            "the proxy requires."
        ),
    }
