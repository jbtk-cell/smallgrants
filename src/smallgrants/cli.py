"""Command line interface for the SmallGrants pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys

DEFAULT_YEARS = [2022, 2023, 2024, 2025, 2026]
DEFAULT_DATA = os.path.expanduser("~/smallgrants/data")


def _years(raw: str | None) -> list[int]:
    if not raw:
        return DEFAULT_YEARS
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smallgrants", description=__doc__)
    ap.add_argument("--data-dir", default=DEFAULT_DATA)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="download and parse IRS 990-PF archives")
    p.add_argument("--years", help="e.g. 2022-2026 or 2024,2025")
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--keep-archives", action="store_true")

    sub.add_parser("load", help="load staging parquet into DuckDB")
    sub.add_parser("summary", help="print corpus summary")

    p = sub.add_parser("enrich", help="entity resolution and NTEE join")
    p.add_argument("--skip-download", action="store_true")

    sub.add_parser("derive", help="compute per-foundation signals")
    sub.add_parser("validate", help="validate the openness ratio against declared status")

    p = sub.add_parser("embed", help="build cause-profile embeddings")
    p.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")

    p = sub.add_parser("search", help="find funders from the command line")
    p.add_argument("query")
    p.add_argument("--state", default=None)
    p.add_argument("--amount", type=int, default=None)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--include-closed", action="store_true")

    p = sub.add_parser("serve", help="run the web application")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    args = ap.parse_args(argv)
    data = args.data_dir

    if args.cmd == "ingest":
        from smallgrants.ingest import ingest

        results = ingest(_years(args.years), data, args.workers, args.keep_archives)
        errs = [r for r in results if r.get("error")]
        done = [r for r in results if not r.get("error") and not r.get("skipped")]
        print(f"\ncompleted {len(done)} archives, {len(errs)} errors")
        print(f"  990-PF filings: {sum(r.get('pf_filings', 0) for r in done):,}")
        print(f"  grant records:  {sum(r.get('grant_records', 0) for r in done):,}")
        for e in errs:
            print(f"  ERROR {e['archive']}: {e['error'][:100]}")
        return 1 if errs else 0

    if args.cmd == "load":
        from smallgrants.store import load_staging

        for k, v in load_staging(data).items():
            print(f"{k:14} {v:,}")
        return 0

    if args.cmd == "summary":
        from smallgrants.store import summary

        print(json.dumps(summary(data), indent=2, default=str))
        return 0

    if args.cmd == "enrich":
        from smallgrants.enrich import enrich

        for k, v in enrich(data, skip_download=args.skip_download).items():
            print(f"{k:28} {v}")
        return 0

    if args.cmd == "derive":
        from smallgrants.derive import derive

        for k, v in derive(data).items():
            print(f"{k:28} {v}")
        return 0

    if args.cmd == "validate":
        from smallgrants.derive import validate_openness

        report = validate_openness(data)
        print(json.dumps(report, indent=2, default=str))
        return 0

    if args.cmd == "embed":
        from smallgrants.match import build_embeddings

        for k, v in build_embeddings(data, args.model).items():
            print(f"{k:28} {v}")
        return 0

    if args.cmd == "search":
        from smallgrants.match import search

        results = search(
            data,
            args.query,
            state=args.state,
            amount=args.amount,
            limit=args.limit,
            include_closed=args.include_closed,
        )
        if not results:
            print("no matches")
            return 0
        for i, r in enumerate(results, 1):
            print(f"\n{i}. {r['name']}  ({r['city']}, {r['state']})")
            print(f"   score {r['score']:.3f} | typical grant ${r['median_grant']:,.0f} "
                  f"| {r['grant_count']} grants | last filed {r['last_year']}")
            if r.get("app_deadlines"):
                print(f"   deadline: {r['app_deadlines'][:90]}")
            if r.get("app_restrictions"):
                print(f"   restrictions: {r['app_restrictions'][:90]}")
            for ev in r["evidence"][:3]:
                print(f"     - ${ev['amount']:,} to {ev['recipient_name']} ({ev['tax_year']})"
                      f"{' - ' + ev['purpose'] if ev.get('purpose') else ''}")
            for note in r.get("caveats", []):
                print(f"   ! {note}")
        return 0

    if args.cmd == "serve":
        import uvicorn

        os.environ["SMALLGRANTS_DATA"] = data
        uvicorn.run("smallgrants.app:app", host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
