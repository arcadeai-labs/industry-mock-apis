"""Thin synchronous Postgres access layer on a psycopg connection pool.

Rows come back as dicts. Use `%s` placeholders and pass params as a list/tuple.
"""
import time
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

_pool: ConnectionPool | None = None


def init_pool(wait_seconds: int = 90) -> None:
    global _pool
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            break
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)
    _pool = ConnectionPool(
        settings.database_url,
        min_size=2,
        max_size=20,
        kwargs={"row_factory": dict_row, "autocommit": True},
        open=True,
    )


def close_pool() -> None:
    if _pool is not None:
        _pool.close()


def pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool


def fetch_all(sql: str, params: Sequence[Any] | None = None) -> list[dict]:
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params: Sequence[Any] | None = None) -> dict | None:
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchone()


def fetch_val(sql: str, params: Sequence[Any] | None = None) -> Any:
    row = fetch_one(sql, params)
    return None if row is None else next(iter(row.values()))


def execute(sql: str, params: Sequence[Any] | None = None) -> int:
    with pool().connection() as conn:
        return conn.execute(sql, params).rowcount


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """Yield a connection inside a transaction. Commits on success, rolls back on error.

    Usage:
        with transaction() as conn:
            row = conn.execute("SELECT ... FOR UPDATE", [id]).fetchone()
            conn.execute("UPDATE ...", [...])
    """
    with pool().connection() as conn:
        with conn.transaction():
            yield conn
