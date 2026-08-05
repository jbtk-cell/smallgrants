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
    con.execute("DROP TABLE IF EXISTS filings")
    con.execute(
        f"""
        CREATE TABLE filings AS
        SELECT * FROM (
            SELECT *, row_number() OVER (
                PARTITION BY ein, tax_year ORDER BY grant_count DESC
            ) AS _rn
            FROM read_parquet('{fglob}', union_by_name=true)
        ) WHERE _rn = 1
        """
    )
    con.execute("ALTER TABLE filings DROP COLUMN _rn")

    con.execute("DROP TABLE IF EXISTS grants_raw")
    if glob.glob(gglob):
        con.execute(
            f"CREATE TABLE grants_raw AS SELECT * FROM read_parquet('{gglob}', union_by_name=true)"
        )
    else:
        con.execute("CREATE TABLE grants_raw (ein VARCHAR, tax_year INTEGER)")

    # Drop grants belonging to filings that lost the dedup above.
    con.execute(
        """
        DELETE FROM grants_raw
        WHERE (ein, tax_year) NOT IN (SELECT ein, tax_year FROM filings)
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
        "SELECT count(*), median(amount), sum(amount) FROM grants_raw WHERE amount IS NOT NULL"
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
