"""Operational endpoints for running demos: reset the data set and inspect table sizes."""
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.db import fetch_all, pool
from app.core.errors import ApiError

router = APIRouter(prefix="/admin", tags=["Admin"])


def _reset() -> dict:
    from app.build_sql import build, drop_sql

    schema_sql, seed_sql, counts = build(settings.enabled_domains)
    with pool().connection() as conn:
        conn.execute(drop_sql(settings.enabled_domains))
        conn.execute(schema_sql)
        conn.execute(seed_sql)
    return {"status": "reset", "tables": len(counts), "rows": sum(counts.values()), "row_counts": counts}


@router.post("/reset-data", summary="Rebuild every schema and regenerate all mock data")
async def reset_data():
    """Drops and recreates every schema, then reloads fresh mock data anchored to the current time.
    Anything created or changed through the APIs is discarded."""
    if not settings.admin_reset_enabled:
        raise ApiError(403, "reset_disabled", "Data reset is disabled (ADMIN_RESET_ENABLED=false).")
    return await run_in_threadpool(_reset)


@router.get("/stats", summary="Row counts for every table, grouped by schema")
def stats():
    rows = fetch_all(
        """
        SELECT schemaname AS schema, relname AS table, n_live_tup AS approx_rows
          FROM pg_stat_user_tables
         ORDER BY schemaname, relname
        """
    )
    grouped: dict[str, dict[str, int]] = {}
    for r in rows:
        grouped.setdefault(r["schema"], {})[r["table"]] = r["approx_rows"]
    return {"schemas": grouped}
