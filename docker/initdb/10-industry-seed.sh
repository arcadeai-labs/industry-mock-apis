#!/usr/bin/env bash
# Runs once, when the Postgres data directory is first initialised: builds the schemas and mock data.
set -euo pipefail
echo "Generating mock data for all industry domains..."
OUT="$(mktemp -d)"
cd /app
/opt/venv/bin/python -m app.build_sql ${ENABLED_DOMAINS:+--domains "$ENABLED_DOMAINS"} --out "$OUT"
psql -v ON_ERROR_STOP=1 -q --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$OUT/01_schema.sql" -f "$OUT/02_seed.sql"
rm -rf "$OUT"
echo "Mock data loaded."
