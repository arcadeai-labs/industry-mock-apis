#!/usr/bin/env bash
# Development: load one industry (plus the shared seed data) into its own database and serve the API.
#   scripts/dev_domain.sh <industry-key> <port>
# Expects a local Postgres at 127.0.0.1:${DEV_PG_PORT:-56543} with user/password dev/dev (see docs/adding-an-industry.md).
set -euo pipefail
DOMAIN="${1:?industry key}"; PORT="${2:?port}"
cd "$(dirname "$0")/.."
PGURL="postgresql://dev:dev@127.0.0.1:${DEV_PG_PORT:-56543}"
DB="dev_${DOMAIN}"
.venv/bin/python - "$PGURL" "$DB" <<'PY'
import sys, psycopg
url, db = sys.argv[1], sys.argv[2]
with psycopg.connect(f"{url}/postgres", autocommit=True) as conn:
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db]).fetchone():
        conn.execute(f'CREATE DATABASE "{db}"')
PY
.venv/bin/python -m app.build_sql --domains "$DOMAIN" --apply "${PGURL}/${DB}"
export DATABASE_URL="${PGURL}/${DB}" API_BEARER_TOKEN="${API_BEARER_TOKEN:-dev-token}" ENABLED_DOMAINS="$DOMAIN"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
