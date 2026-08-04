"""Discover, download, and parse IRS 990 filing archives.

Archives are streamed: each is downloaded, parsed in memory, written to staging
Parquet, then deleted. Peak disk stays near one archive per worker rather than
the ~27 GB the full corpus would otherwise require.

The IRS download page's own listing is incomplete -- 2022_TEOS_XML_02A.zip exists
but is not linked -- so discovery probes for successor parts rather than trusting
the page.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

BASE = "https://apps.irs.gov/pub/epostcard/990/xml"
LISTING = "https://www.irs.gov/charities-non-profits/form-990-series-downloads"
ARCHIVE_RE = re.compile(r"https://apps\.irs\.gov/pub/epostcard/990/xml/(\d{4})/([A-Za-z0-9_]+\.zip)")
# Parts observed in the wild: 01A..NNA, occasionally with a B suffix.
PART_SUFFIXES = [f"{i:02d}{s}" for i in range(1, 40) for s in ("A", "B")]


def _head_ok(client: httpx.Client, url: str) -> bool:
    try:
        return client.head(url, timeout=20, follow_redirects=True).status_code == 200
    except httpx.HTTPError:
        return False


def discover_archives(years: list[int]) -> list[str]:
    """Return archive URLs for the given filing years, listed or not."""
    found: set[str] = set()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        try:
            html = client.get(LISTING).text
            for year, fname in ARCHIVE_RE.findall(html):
                if int(year) in years:
                    found.add(f"{BASE}/{year}/{fname}")
        except httpx.HTTPError:
            pass

        # Probe past the last listed part; the page under-reports some years.
        for year in years:
            misses = 0
            for suffix in PART_SUFFIXES:
                url = f"{BASE}/{year}/{year}_TEOS_XML_{suffix}.zip"
                if url in found:
                    misses = 0
                    continue
                if _head_ok(client, url):
                    found.add(url)
                    misses = 0
                else:
                    misses += 1
                    if misses >= 6:
                        break
    return sorted(found)


def _staging_paths(staging: str, name: str) -> tuple[str, str]:
    stem = name.replace(".zip", "")
    return (
        os.path.join(staging, f"{stem}.foundations.parquet"),
        os.path.join(staging, f"{stem}.grants.parquet"),
    )


def process_archive(url: str, staging: str, keep: bool = False) -> dict:
    """Download one archive, parse it, write staging Parquet, delete the zip."""
    from smallgrants.parse import parse_archive

    name = url.rsplit("/", 1)[-1]
    fpath, gpath = _staging_paths(staging, name)
    if os.path.exists(fpath) and os.path.exists(gpath):
        return {"archive": name, "skipped": True}

    zpath = os.path.join(staging, name)
    if not os.path.exists(zpath):
        tmp = zpath + ".part"
        with httpx.stream("GET", url, timeout=600, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
        os.replace(tmp, zpath)

    try:
        foundations, grants, stats = parse_archive(zpath)
    finally:
        if not keep and os.path.exists(zpath):
            os.remove(zpath)

    if foundations:
        pq.write_table(pa.Table.from_pylist(foundations), fpath)
    if grants:
        pq.write_table(pa.Table.from_pylist(grants), gpath)
    stats["skipped"] = False
    return stats


def ingest(years: list[int], data_dir: str, workers: int = 5, keep: bool = False) -> list[dict]:
    """Ingest every archive for the given years. Safe to re-run; completed
    archives are skipped via their staging Parquet."""
    staging = os.path.join(data_dir, "staging")
    os.makedirs(staging, exist_ok=True)
    urls = discover_archives(years)
    print(f"discovered {len(urls)} archives across years {years}", flush=True)

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_archive, u, staging, keep): u for u in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url = futures[fut]
            try:
                stats = fut.result()
            except Exception as exc:  # keep going; report at the end
                stats = {"archive": url.rsplit("/", 1)[-1], "error": str(exc)}
            results.append(stats)
            label = stats.get("archive", "?")
            if stats.get("error"):
                print(f"[{i}/{len(urls)}] {label} ERROR {stats['error'][:80]}", flush=True)
            elif stats.get("skipped"):
                print(f"[{i}/{len(urls)}] {label} (cached)", flush=True)
            else:
                print(
                    f"[{i}/{len(urls)}] {label} "
                    f"pf={stats['pf_filings']} grants={stats['grant_records']}",
                    flush=True,
                )
    return results
