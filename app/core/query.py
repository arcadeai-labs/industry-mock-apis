"""Helpers for filtered, paginated list endpoints and ID generation."""
import secrets
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from fastapi import Query

from app.core.db import fetch_all, fetch_val


@dataclass
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: int = Query(25, ge=1, le=500, description="Maximum number of records to return."),
    offset: int = Query(0, ge=0, description="Number of records to skip."),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


class Where:
    """Accumulates optional SQL filters. Methods ignore None values.

        w = Where().eq("b.status", status).ilike(["c.name", "c.email"], q).gte("b.amount", min_amount)
        sql = f"SELECT ... FROM t b {w.sql}"; params = w.params
    """

    def __init__(self) -> None:
        self.clauses: list[str] = []
        self.params: list[Any] = []

    def add(self, clause: str, *params: Any) -> "Where":
        self.clauses.append(clause)
        self.params.extend(params)
        return self

    def eq(self, column: str, value: Any) -> "Where":
        if value is not None:
            self.add(f"{column} = %s", value)
        return self

    def in_(self, column: str, values: Iterable[Any] | None) -> "Where":
        if values:
            self.add(f"{column} = ANY(%s)", list(values))
        return self

    def gte(self, column: str, value: Any) -> "Where":
        if value is not None:
            self.add(f"{column} >= %s", value)
        return self

    def lte(self, column: str, value: Any) -> "Where":
        if value is not None:
            self.add(f"{column} <= %s", value)
        return self

    def ilike(self, columns: str | Sequence[str], value: str | None) -> "Where":
        if value:
            cols = [columns] if isinstance(columns, str) else list(columns)
            pattern = f"%{value}%"
            self.add("(" + " OR ".join(f"{c}::text ILIKE %s" for c in cols) + ")", *([pattern] * len(cols)))
        return self

    @property
    def sql(self) -> str:
        return (" WHERE " + " AND ".join(self.clauses)) if self.clauses else ""


def paginated(
    select_sql: str,
    params: Sequence[Any],
    *,
    order_by: str,
    page: PageParams,
    meta: dict | None = None,
) -> dict:
    """Run a SELECT (without ORDER BY/LIMIT) and return the standard list envelope."""
    total = fetch_val(f"SELECT count(*) FROM ({select_sql}) AS _q", params)
    rows = fetch_all(f"{select_sql} ORDER BY {order_by} LIMIT %s OFFSET %s", [*params, page.limit, page.offset])
    return list_response(rows, total=total, page=page, meta=meta)


def list_response(rows: list[dict], *, total: int | None = None, page: PageParams | None = None, meta: dict | None = None) -> dict:
    total = len(rows) if total is None else total
    limit = page.limit if page else len(rows)
    offset = page.offset if page else 0
    body: dict[str, Any] = {
        "data": rows,
        "pagination": {"total": total, "limit": limit, "offset": offset, "has_more": offset + len(rows) < total},
    }
    if meta:
        body["meta"] = meta
    return body


def new_id(prefix: str) -> str:
    """IDs for records created through the API, e.g. BRK-7F3A9C21 (seed data uses numeric suffixes)."""
    return f"{prefix}-{secrets.token_hex(4).upper()}"
