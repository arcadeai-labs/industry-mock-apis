"""Deterministic mock-data generation into plain SQL.

Each domain exposes `seed(w: SeedWriter, ctx: SeedContext)`. Values are converted to SQL literals:
None -> NULL, bool, int/float/Decimal, str, date/datetime (ISO), dict/list -> jsonb.
Randomness comes from `ctx.rng` / `ctx.fake`, both seeded per domain, so data is stable across builds;
timestamps are anchored to `ctx.now` so the data always looks recent.
"""
import json
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from faker import Faker


def lit(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, float):
        return repr(round(value, 6))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return f"'{value.isoformat()}'"
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, default=str).replace("'", "''")
        return f"'{text}'::jsonb"
    text = str(value).replace("'", "''")
    return f"'{text}'"


class SeedWriter:
    def __init__(self) -> None:
        self._chunks: list[str] = []
        self.row_counts: dict[str, int] = {}

    def comment(self, text: str) -> None:
        self._chunks.append(f"\n-- {text}\n")

    def raw(self, sql: str) -> None:
        self._chunks.append(sql.rstrip() + "\n")

    def insert(self, table: str, rows: Iterable[dict], batch_size: int = 500) -> None:
        rows = list(rows)
        if not rows:
            return
        columns = list(dict.fromkeys(k for r in rows for k in r))  # union of keys, first-seen order
        col_sql = ", ".join(columns)
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            values = ",\n".join("(" + ", ".join(lit(r.get(c)) for c in columns) + ")" for r in batch)
            self._chunks.append(f"INSERT INTO {table} ({col_sql}) VALUES\n{values};\n")
        self.row_counts[table] = self.row_counts.get(table, 0) + len(rows)

    def sql(self) -> str:
        return "".join(self._chunks)


class SeedRun:
    """State shared across all domains during one build (e.g. the user directory)."""

    def __init__(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.now = now.replace(second=0, microsecond=0)
        self.users: list[dict] = []
        self.organizations: list[dict] = []
        self.shared: dict[str, Any] = {}


class SeedContext:
    def __init__(self, run: SeedRun, domain: str) -> None:
        self.run = run
        self.domain = domain
        self.rng = random.Random(f"industry-demo::{domain}")
        self.fake = Faker("en_US")
        self.fake.seed_instance(sum(ord(c) for c in domain) * 7919)

    # time anchors -------------------------------------------------------
    @property
    def now(self) -> datetime:
        return self.run.now

    @property
    def today(self) -> date:
        return self.run.now.date()

    def ago(self, days: float = 0, hours: float = 0, minutes: float = 0) -> datetime:
        return self.now - timedelta(days=days, hours=hours, minutes=minutes)

    def ahead(self, days: float = 0, hours: float = 0) -> datetime:
        return self.now + timedelta(days=days, hours=hours)

    def random_time_between(self, start: datetime, end: datetime) -> datetime:
        span = (end - start).total_seconds()
        return (start + timedelta(seconds=self.rng.random() * max(span, 0))).replace(microsecond=0)

    def recent(self, max_days: float, min_days: float = 0) -> datetime:
        """A random timestamp between max_days and min_days ago."""
        return self.random_time_between(self.ago(days=max_days), self.ago(days=min_days))

    # directory ----------------------------------------------------------
    def users(self, domain: str | None = None, role: str | None = None) -> list[dict]:
        domain = self.domain if domain is None else domain
        return [
            u for u in self.run.users
            if (domain == "*" or u["domain"] == domain) and (role is None or role in u["roles"])
        ]

    def user(self, email: str) -> dict:
        for u in self.run.users:
            if u["email"] == email:
                return u
        raise KeyError(email)

    def org(self, domain: str | None = None) -> dict:
        domain = domain or self.domain
        return next(o for o in self.run.organizations if o["id"] == domain)

    # random helpers -----------------------------------------------------
    def pick(self, seq):
        return self.rng.choice(list(seq))

    def weighted(self, options: dict):
        """Pick a key from {value: weight}."""
        keys = list(options.keys())
        return self.rng.choices(keys, weights=list(options.values()), k=1)[0]

    def money(self, low: float, high: float, log_scale: bool = False) -> Decimal:
        if log_scale:
            import math
            value = math.exp(self.rng.uniform(math.log(low), math.log(high)))
        else:
            value = self.rng.uniform(low, high)
        return Decimal(str(round(value, 2)))
