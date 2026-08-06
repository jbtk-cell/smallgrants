"""Write a serving-only copy of the corpus.

The built database is about 2.5 GB, most of which is scaffolding: raw grant rows
before deduplication, the 1.98M-row business master file, the grantee keys used
to compute openness. None of it is read while serving. Dropping it leaves roughly
500 MB, which fits on a cheap host and copies over a home connection.

Rebuilding the corpus needs the full database. Serving does not.
"""

from __future__ import annotations

import os
import shutil

SERVING_TABLES = ("foundation_signals",)

# Serving reads these columns of `grants` and no others. recipient_zip carries
# the ZIP-prefix half of the geography score; recipient_is_person is read when a
# foundation page lists who it actually paid.
GRANT_COLUMNS = (
    "ein", "tax_year", "recipient_name", "recipient_state", "recipient_zip",
    "recipient_is_person", "purpose", "amount", "recipient_ntee", "ntee_major",
    "is_individual", "resolution_tier",
)

# The masthead counts come from `filings`. Only these columns are read, and the
# rest of the table (addresses, contacts, financials) stays behind.
FILING_COLUMNS = ("ein", "tax_year", "declared_closed", "has_application_info")


def package(data_dir: str, out_dir: str | None = None) -> dict:
    import duckdb

    out_dir = out_dir or os.path.join(data_dir, "dist")
    os.makedirs(out_dir, exist_ok=True)
    src = os.path.join(data_dir, "smallgrants.duckdb")
    dst = os.path.join(out_dir, "smallgrants.duckdb")
    if not os.path.exists(src):
        raise FileNotFoundError(f"no corpus at {src}; run the build first")
    if os.path.exists(dst):
        os.remove(dst)

    con = duckdb.connect(dst)
    con.execute(f"ATTACH '{src}' AS s (READ_ONLY)")
    for table in SERVING_TABLES:
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM s.{table}")
    con.execute(
        f"CREATE TABLE grants AS SELECT {', '.join(GRANT_COLUMNS)} FROM s.grants"
    )
    con.execute(
        f"CREATE TABLE filings AS SELECT {', '.join(FILING_COLUMNS)} FROM s.filings"
    )
    con.execute("CREATE INDEX grants_ein ON grants(ein)")
    con.execute("CREATE INDEX signals_ein ON foundation_signals(ein)")
    con.execute("DETACH s")
    con.close()

    copied = []
    for name in ("cause_embeddings.npy", "cause_embeddings_eins.txt"):
        srcf = os.path.join(data_dir, name)
        if os.path.exists(srcf):
            shutil.copy2(srcf, os.path.join(out_dir, name))
            copied.append(name)

    total = sum(
        os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir)
    )
    return {
        "out_dir": out_dir,
        "database_mb": round(os.path.getsize(dst) / 1e6, 1),
        "embeddings_copied": ", ".join(copied) or "none found",
        "total_mb": round(total / 1e6, 1),
        "original_mb": round(os.path.getsize(src) / 1e6, 1),
    }
