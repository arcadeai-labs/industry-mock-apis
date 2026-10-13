#!/usr/bin/env bash
# Starts the embedded Postgres (official image entrypoint: initialises and seeds on first start),
# waits for it, then serves the API. If either process exits, the container stops.
set -Eeuo pipefail

if [[ "${AUTH_MODE:-static}" != "okta" && ( -z "${API_BEARER_TOKEN:-}" || "${API_BEARER_TOKEN}" == "change-me" ) ]]; then
  echo "ERROR: set API_BEARER_TOKEN in .env to your own value (see .env.example)." >&2
  exit 1
fi
# The database is only reachable inside the container, so a fixed default password is sufficient.
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-demo}"

docker-entrypoint.sh postgres -c max_connections=200 -c shared_buffers=256MB &
PG_PID=$!
API_PID=""

shutdown() {
  [[ -n "$API_PID" ]] && kill -TERM "$API_PID" 2>/dev/null || true
  kill -INT "$PG_PID" 2>/dev/null || true
  wait || true
}
trap 'shutdown; exit 0' TERM INT

# The init-time server only listens on the unix socket, so TCP readiness means init (and seeding) is done.
echo "Waiting for Postgres (first start generates and loads the mock data)..."
for _ in $(seq 1 300); do
  pg_isready -h 127.0.0.1 -p 5432 -U "$POSTGRES_USER" -q && break
  kill -0 "$PG_PID" 2>/dev/null || { echo "Postgres exited during startup" >&2; exit 1; }
  sleep 1
done
pg_isready -h 127.0.0.1 -p 5432 -U "$POSTGRES_USER" -q || { echo "Postgres did not become ready" >&2; exit 1; }

export DATABASE_URL="postgresql://${POSTGRES_USER}:$(python3 -c 'import os,urllib.parse;print(urllib.parse.quote(os.environ["POSTGRES_PASSWORD"],safe=""))')@127.0.0.1:5432/${POSTGRES_DB}"

cd /app
if [[ "${RESEED_ON_START:-false}" == "true" ]]; then
  echo "RESEED_ON_START=true: regenerating mock data anchored to today..."
  gosu api python -m app.build_sql ${ENABLED_DOMAINS:+--domains "$ENABLED_DOMAINS"} --apply "$DATABASE_URL"
fi

echo "Starting API on :8080"
gosu api uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers "${API_WORKERS:-2}" \
  --proxy-headers --forwarded-allow-ips '*' --no-server-header &
API_PID=$!

set +e
wait -n "$PG_PID" "$API_PID"
status=$?
echo "A service exited (status $status); stopping the container." >&2
shutdown
exit "$status"
