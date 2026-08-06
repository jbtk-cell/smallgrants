"""DuckDB storage for the parsed corpus."""

from __future__ import annotations

import glob
import os

import duckdb

DB_NAME = "smallgrants.duckdb"


def db_path(data_dir: str) -> str:
    return os.path.join(data_dir, DB_NAME)


def connect(data_dir: str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    os.makedirs(data_dir, exist_ok=True)
    con = duckdb.connect(db_path(data_dir), read_only=read_only)
    if not read_only:
        # Spill beside the database rather than into /tmp: the joins over the
        # full corpus can exceed memory, and a filled /tmp fails in confusing
        # ways far from the query that caused it.
        tmp = os.path.join(data_dir, "duckdb_tmp")
        os.makedirs(tmp, exist_ok=True)
        con.execute(f"SET temp_directory = '{tmp}'")
    return con


def load_staging(data_dir: str) -> dict[str, int]:
    """Load staging Parquet into DuckDB, replacing existing raw tables.

    A foundation files once per tax year, so (ein, tax_year) is the natural key.
    Amended returns can produce duplicates; we keep the filing with the most
    grant rows, which is the more complete document.
    """
    staging = os.path.join(data_dir, "staging")
    fglob = os.path.join(staging, "*.foundations.parquet")
    gglob = os.path.join(staging, "*.grants.parquet")
    if not glob.glob(fglob):
        raise FileNotFoundError(f"no staging parquet in {staging}; run ingest first")

    con = connect(data_dir)

    # A filing needs an identity, or the grant rows of a foundation's two filings
    # for one tax year pool together and its grant dollars double. Newer parses
    # carry the IRS object_id; archives staged before that fall back to the
    # staging file they came from, which is one archive per file.
    cols = {
        c[0]
        for c in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{fglob}', union_by_name=true)"
        ).fetchall()
    }
    has_oid = "object_id" in cols
    fkey = "object_id" if has_oid else "regexp_extract(filename, '[^/]+$')"
    # Prefer an amended return, then the newest, then the fullest schedule. The
    # last term makes the choice deterministic: 81% of duplicate pairs tie on
    # grant_count, and without a tiebreak DuckDB picked arbitrarily, so declared
    # status and assets changed between rebuilds.
    order = []
    if "amended" in cols:
        order.append("amended DESC")
    if "return_ts" in cols:
        order.append("return_ts DESC NULLS LAST")
    order += ["grant_count DESC", "filing_key DESC"]

    con.execute("DROP TABLE IF EXISTS filings")
    con.execute(
        f"""
        CREATE TABLE filings AS
        SELECT * EXCLUDE (_rn) FROM (
            SELECT *, row_number() OVER (
                PARTITION BY ein, tax_year ORDER BY {', '.join(order)}
            ) AS _rn
            FROM (
                SELECT * EXCLUDE (filename), {fkey} AS filing_key
                FROM read_parquet('{fglob}', union_by_name=true, filename=true)
            )
        ) WHERE _rn = 1
        """
    )

    con.execute("DROP TABLE IF EXISTS grants_raw")
    if glob.glob(gglob):
        gkey = "object_id" if has_oid else "replace(regexp_extract(filename, '[^/]+$'), '.grants.', '.foundations.')"
        con.execute(
            f"""
            CREATE TABLE grants_raw AS
            SELECT * EXCLUDE (filename), {gkey} AS filing_key
            FROM read_parquet('{gglob}', union_by_name=true, filename=true)
            """
        )
    else:
        con.execute("CREATE TABLE grants_raw (ein VARCHAR, tax_year INTEGER, filing_key VARCHAR)")

    # Keep only the grants belonging to the filing that won.
    con.execute(
        """
        DELETE FROM grants_raw g
        WHERE NOT EXISTS (
            SELECT 1 FROM filings f
            WHERE f.ein = g.ein AND f.tax_year = g.tax_year
              AND f.filing_key = g.filing_key
        )
        """
    )

    # Residual: two filings inside one archive share a filing_key when object_id
    # is unavailable. Only for pairs that still carry more rows than the winning
    # filing declared, collapse exact duplicate rows -- bounded so that a
    # foundation legitimately making two identical grants keeps both.
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _over AS
        SELECT g.ein, g.tax_year
        FROM grants_raw g JOIN filings f USING (ein, tax_year)
        GROUP BY g.ein, g.tax_year, f.grant_count
        HAVING count(*) > f.grant_count
        """
    )
    gcols = [c[0] for c in con.execute("DESCRIBE grants_raw").fetchall()]
    con.execute(
        f"""
        CREATE OR REPLACE TABLE grants_raw AS
        SELECT * EXCLUDE (_dup) FROM (
            SELECT g.*, CASE WHEN o.ein IS NULL THEN 1 ELSE
                row_number() OVER (PARTITION BY {', '.join('g.' + c for c in gcols)}) END AS _dup
            FROM grants_raw g LEFT JOIN _over o USING (ein, tax_year)
        ) WHERE _dup = 1
        """
    )

    counts = {
        "filings": con.execute("SELECT count(*) FROM filings").fetchone()[0],
        "foundations": con.execute("SELECT count(DISTINCT ein) FROM filings").fetchone()[0],
        "grants": con.execute("SELECT count(*) FROM grants_raw").fetchone()[0],
        "years": con.execute("SELECT count(DISTINCT tax_year) FROM filings").fetchone()[0],
    }
    con.close()
    return counts


def summary(data_dir: str) -> dict:
    con = connect(data_dir, read_only=True)
    row = con.execute(
        """
        SELECT
          count(*) AS filings,
          count(DISTINCT ein) AS foundations,
          min(tax_year) AS first_year,
          max(tax_year) AS last_year,
          sum(CASE WHEN declared_closed THEN 1 ELSE 0 END) AS declared_closed,
          sum(CASE WHEN has_application_info THEN 1 ELSE 0 END) AS with_app_info
        FROM filings
        """
    ).fetchone()
    grants = con.execute(
        # `grants`, not `grants_raw`: report the table the site actually serves
        # from. The two agree exactly, and grants_raw is build scaffolding that a
        # serving-only copy of the corpus does not carry.
        # Count every grant row, but take the median and total over the rows that
        # carry a dollar amount. Filtering the count too made the site report 170
        # fewer grants than the corpus holds, for no reason a reader could see.
        """
        SELECT count(*),
               median(amount) FILTER (WHERE amount IS NOT NULL),
               sum(amount)
        FROM grants
        """
    ).fetchone()
    con.close()
    return {
        "filings": row[0],
        "foundations": row[1],
        "year_range": f"{row[2]}-{row[3]}",
        "declared_closed": row[4],
        "with_application_info": row[5],
        "grant_records": grants[0],
        "median_grant": grants[1],
        "total_granted": grants[2],
    }
