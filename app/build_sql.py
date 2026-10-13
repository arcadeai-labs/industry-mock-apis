"""Build (and optionally apply) the database schema and mock data for every domain.

    python -m app.build_sql --out /tmp/seed                 # writes 01_schema.sql and 02_seed.sql
    python -m app.build_sql --apply postgresql://...        # executes them against a database
    python -m app.build_sql --domains banking --apply ...   # common + one domain (for development)
"""
import argparse
import importlib
import sys
import time
from datetime import datetime
from pathlib import Path

from app.core.seedlib import SeedContext, SeedRun, SeedWriter
from app.domains import resolve_keys, schema_path


def build(domains: list[str] | None = None, now: datetime | None = None) -> tuple[str, str, dict[str, int]]:
    keys = resolve_keys(domains)
    schema_sql = "\n".join(
        f"-- ===== {key} =====\n" + schema_path(key).read_text() for key in keys
    )
    run = SeedRun(now)
    writer = SeedWriter()
    writer.raw("SET client_min_messages = warning;")
    for key in keys:
        writer.comment(f"===== {key} =====")
        importlib.import_module(f"app.domains.{key}.seed").seed(writer, SeedContext(run, key))
    writer.raw("ANALYZE;")
    return schema_sql, writer.sql(), writer.row_counts


def drop_sql(domains: list[str] | None = None) -> str:
    return "\n".join(f"DROP SCHEMA IF EXISTS {k} CASCADE;" for k in reversed(resolve_keys(domains)))


def apply(dsn: str, domains: list[str] | None = None) -> dict[str, int]:
    import psycopg

    schema_sql, seed_sql, counts = build(domains)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(drop_sql(domains))
        conn.execute(schema_sql)
        conn.execute(seed_sql)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, help="Directory to write 01_schema.sql and 02_seed.sql into")
    parser.add_argument("--apply", metavar="DSN", help="Apply schema and seed data to this database")
    parser.add_argument("--domains", help="Comma-separated domain keys (common is always included)")
    args = parser.parse_args()
    domains = [d.strip() for d in args.domains.split(",")] if args.domains else None

    started = time.perf_counter()
    if args.apply:
        counts = apply(args.apply, domains)
    else:
        if not args.out:
            parser.error("pass --out DIR or --apply DSN")
        schema_sql, seed_sql, counts = build(domains)
        out = args.out
        out.mkdir(parents=True, exist_ok=True)
        (out / "01_schema.sql").write_text(schema_sql)
        (out / "02_seed.sql").write_text(seed_sql)
    total = sum(counts.values())
    print(f"Seeded {total:,} rows across {len(counts)} tables in {time.perf_counter() - started:.1f}s", file=sys.stderr)
    for table, n in sorted(counts.items()):
        print(f"  {table:<45} {n:>8,}", file=sys.stderr)


if __name__ == "__main__":
    main()
