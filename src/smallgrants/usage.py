"""Usage logging.

Kept deliberately small and separate from the corpus. DuckDB allows one writer,
and the app holds a read-only connection, so writing events there would either
fail or lock out the site. This uses SQLite in its own file.

What it records: what was searched for, how many results came back, and which
foundations people opened. What it does not record: IP addresses, user agents,
names, or anything typed into the review box. Visitors are counted through a
salted hash that is rebuilt every night, so yesterday's hashes cannot be matched
to today's visitor or back to an address.

The one question this cannot answer is whether a funder was new to the person who
found it. That needs to be asked, not inferred, and asking it is a product
decision rather than a logging one. The schema has room for the answer when it is
wanted: add a column, record it on the outbound click.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
from datetime import date, datetime, timezone

log = logging.getLogger("smallgrants.usage")

_lock = threading.Lock()
_salt_day: str | None = None
_salt: str = ""

# Crawlers make up most of the traffic to a small site. Counting them turns a
# usage number into a fiction, so they are marked and excluded by default.
_BOT_MARKERS = (
    "bot", "crawl", "spider", "slurp", "curl", "wget", "python-requests",
    "httpx", "headless", "phantom", "scrapy", "monitor", "uptime", "pingdom",
    "facebookexternalhit", "preview", "fetcher", "archiver", "semrush", "ahrefs",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    day       TEXT NOT NULL,
    event     TEXT NOT NULL,
    visitor   TEXT,
    is_bot    INTEGER NOT NULL DEFAULT 0,
    query     TEXT,
    state     TEXT,
    amount    INTEGER,
    applicant TEXT,
    results   INTEGER,
    ein       TEXT,
    source    TEXT,
    -- Self-reported, on the 'applying' event only. 1 = the visitor already knew
    -- this funder, 0 = it was new to them, NULL = not asked or not answered.
    -- This single field is the difference between reporting reach and reporting
    -- discovery, and it cannot be reconstructed after the fact.
    already_knew INTEGER
);
CREATE INDEX IF NOT EXISTS events_day     ON events(day);
CREATE INDEX IF NOT EXISTS events_event   ON events(event);
CREATE INDEX IF NOT EXISTS events_visitor ON events(visitor);
"""


def usage_dir(data_dir: str) -> str:
    """Where the log lives. Separate from the corpus so a deployment can point it
    at the one directory it is able to persist."""
    d = os.environ.get("SMALLGRANTS_USAGE_DIR") or data_dir
    os.makedirs(d, exist_ok=True)
    return d


def db_path(data_dir: str) -> str:
    return os.path.join(usage_dir(data_dir), "usage.sqlite")


def journal_path(data_dir: str) -> str:
    """Append-only mirror of every event.

    A hosted container with no persistent disk has to copy this log somewhere
    else to keep it, and a SQLite file copied mid-write can come back unreadable.
    One JSON object per line always survives the copy: the worst case is a torn
    final line, which replay skips. SQLite stays the thing queries run against
    and is rebuilt from here whenever it is missing.
    """
    return os.path.join(usage_dir(data_dir), "events.jsonl")


def _connect(data_dir: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path(data_dir), timeout=5.0)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    # A log written before this column existed must keep working rather than
    # throw on every request.
    cols = {r[1] for r in con.execute("PRAGMA table_info(events)")}
    if "already_knew" not in cols:
        con.execute("ALTER TABLE events ADD COLUMN already_knew INTEGER")
    if not con.execute("SELECT 1 FROM events LIMIT 1").fetchone():
        _replay(con, data_dir)
    return con


FIELDS = (
    "ts", "day", "event", "visitor", "is_bot", "query", "state", "amount",
    "applicant", "results", "ein", "source", "already_knew",
)


def _replay(con: sqlite3.Connection, data_dir: str) -> None:
    """Rebuild an empty database from the journal, which is what happens on the
    first request after a container restart."""
    path = journal_path(data_dir)
    if not os.path.exists(path):
        return
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue  # a torn final line from an interrupted write
            rows.append(tuple(e.get(k) for k in FIELDS))
    if rows:
        con.executemany(
            f"INSERT INTO events ({','.join(FIELDS)}) "
            f"VALUES ({','.join('?' * len(FIELDS))})",
            rows,
        )
        con.commit()
        log.info("replayed %d events from the journal", len(rows))


def _daily_salt() -> str:
    """A salt that changes at midnight UTC and is never written down.

    Rotating it means a visitor hash is only comparable within one day. That is
    enough to count people without being able to follow them.
    """
    global _salt_day, _salt
    today = date.today().isoformat()
    if _salt_day != today:
        _salt_day, _salt = today, secrets.token_hex(16)
    return _salt


def looks_like_bot(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    if not ua:
        return True
    return any(m in ua for m in _BOT_MARKERS)


def visitor_hash(ip: str, user_agent: str) -> str:
    raw = f"{_daily_salt()}|{ip}|{user_agent}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def record(data_dir: str, event: str, request=None, **fields) -> None:
    """Write one event. Never raises: a logging failure must not cost a search."""
    try:
        ip, ua = "", ""
        if request is not None:
            ip = getattr(getattr(request, "client", None), "host", "") or ""
            ua = request.headers.get("user-agent", "")
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "day": date.today().isoformat(),
            "event": event,
            "visitor": visitor_hash(ip, ua),
            "is_bot": int(looks_like_bot(ua)),
            "query": (fields.get("query") or "")[:300] or None,
            "state": fields.get("state") or None,
            "amount": fields.get("amount"),
            "applicant": fields.get("applicant") or None,
            "results": fields.get("results"),
            "ein": fields.get("ein") or None,
            "source": fields.get("source") or None,
            "already_knew": fields.get("already_knew"),
        }
        with _lock:
            # Connect first. _connect replays the journal into an empty database,
            # so appending this event beforehand would replay it and then insert
            # it again.
            con = _connect(data_dir)
            with open(journal_path(data_dir), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            with con:
                con.execute(
                    f"INSERT INTO events ({','.join(FIELDS)}) "
                    f"VALUES ({','.join('?' * len(FIELDS))})",
                    tuple(row[k] for k in FIELDS),
                )
            con.close()
    except Exception:
        log.debug("usage event not recorded", exc_info=True)


def stats(data_dir: str, days: int = 30, include_bots: bool = False) -> dict:
    """Everything the log can honestly say."""
    # Either file is enough. After a container restart the journal is often the
    # only survivor, and _connect rebuilds the database from it.
    if not os.path.exists(db_path(data_dir)) and not os.path.exists(
        journal_path(data_dir)
    ):
        return {"error": "No usage log yet. It is created on the first request."}
    con = _connect(data_dir)
    where = "" if include_bots else "WHERE is_bot = 0"
    andw = "" if include_bots else "AND is_bot = 0"
    q = lambda sql, *a: con.execute(sql, a).fetchall()  # noqa: E731

    out: dict = {}
    out["totals"] = dict(
        zip(
            ["searches", "foundation_views", "reviews", "throttled",
             "visitors", "days_live"],
            q(
                # coalesce: sum() over no rows is NULL, and a usage report that
                # prints None where it means zero is a report nobody trusts.
                f"""SELECT
                      coalesce(sum(event='search'), 0),
                      coalesce(sum(event='foundation'), 0),
                      coalesce(sum(event='review'), 0),
                      coalesce(sum(event='throttled'), 0),
                      count(DISTINCT visitor), count(DISTINCT day)
                    FROM events {where}"""
            )[0],
        )
    )
    out["bots_excluded"] = q("SELECT count(*) FROM events WHERE is_bot = 1")[0][0]
    out["by_day"] = q(
        f"""SELECT day, count(DISTINCT visitor), sum(event='search'),
                   sum(event='foundation')
            FROM events {where} GROUP BY day ORDER BY day DESC LIMIT ?""",
        days,
    )
    out["top_queries"] = q(
        f"""SELECT query, count(*) FROM events
            WHERE event='search' AND query IS NOT NULL {andw}
            GROUP BY lower(query) ORDER BY 2 DESC LIMIT 15"""
    )
    out["top_states"] = q(
        f"""SELECT state, count(*) FROM events
            WHERE event='search' AND state IS NOT NULL AND state != '' {andw}
            GROUP BY state ORDER BY 2 DESC LIMIT 15"""
    )
    out["most_opened"] = q(
        f"""SELECT ein, count(*) FROM events
            WHERE event='foundation' AND ein IS NOT NULL {andw}
            GROUP BY ein ORDER BY 2 DESC LIMIT 15"""
    )
    # The share of searches that returned nothing. A high number means the corpus
    # is failing the people who showed up, which no visit count would reveal.
    row = q(
        f"""SELECT count(*), coalesce(sum(results = 0), 0) FROM events
            WHERE event='search' AND results IS NOT NULL {andw}"""
    )[0]
    out["empty_searches"] = {"searches": row[0] or 0, "returned_nothing": row[1] or 0}
    # Did anyone open a funder after searching? Without this, a visit count says
    # people arrived, not that the results were worth reading.
    # The claim this log exists to support. "Reported applying" is self-reported
    # intent, not a submitted application, and "new to them" is their answer, not
    # a measurement. Both are stated that way wherever they are shown.
    row = q(
        f"""SELECT count(*),
                   coalesce(sum(already_knew = 0), 0),
                   count(DISTINCT visitor),
                   count(DISTINCT CASE WHEN already_knew = 0 THEN ein END)
            FROM events WHERE event='applying' {andw}"""
    )[0]
    out["discovery"] = {
        "reported_applying": row[0],
        "funder_was_new_to_them": row[1],
        "people": row[2],
        "distinct_funders_newly_found": row[3],
    }
    out["searchers_who_opened_a_funder"] = q(
        f"""SELECT count(DISTINCT visitor) FROM events
            WHERE event='foundation' {andw}
              AND visitor IN (SELECT visitor FROM events WHERE event='search' {andw})"""
    )[0][0]
    con.close()
    return out
