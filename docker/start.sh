#!/usr/bin/env bash
set -Eeuo pipefail

pg_pid=""
api_pid=""
web_pid=""
startup_pid=""
cleanup() {
    trap - EXIT TERM INT
    local children=() pid running attempt
    if [[ -n "$startup_pid" ]]; then
        children+=("$startup_pid")
        kill -TERM "$startup_pid" 2>/dev/null || true
    fi
    if [[ -n "$web_pid" ]]; then
        children+=("$web_pid")
        kill -QUIT "$web_pid" 2>/dev/null || true
    fi
    if [[ -n "$api_pid" ]]; then
        children+=("$api_pid")
        kill -TERM "$api_pid" 2>/dev/null || true
    fi
    # Reserve most of Docker's 30-second stop timeout for PostgreSQL.
    for ((attempt = 0; attempt < 8; attempt++)); do
        running=false
        for pid in "${children[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then running=true; fi
        done
        if [[ "$running" == false ]]; then break; fi
        sleep 1
    done
    for pid in "${children[@]}"; do
        kill -KILL "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    if [[ -n "$pg_pid" ]]; then
        kill -INT "$pg_pid" 2>/dev/null || true
        wait "$pg_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 0' TERM INT

startup() {
    "$@" <&0 &
    startup_pid=$!
    wait "$startup_pid"
    startup_pid=""
}

install -d -o postgres -g postgres -m 700 "$PGDATA"
install -d -o postgres -g postgres -m 775 /var/run/postgresql
if [[ ! -s "$PGDATA/PG_VERSION" ]]; then
    startup gosu postgres initdb --auth-local=trust --auth-host=scram-sha-256
fi

gosu postgres postgres -c listen_addresses='' -c unix_socket_directories=/var/run/postgresql &
pg_pid=$!
for ((attempt = 0; attempt < 60; attempt++)); do
    if gosu postgres pg_isready -q -h /var/run/postgresql -U postgres; then break; fi
    if ! kill -0 "$pg_pid" 2>/dev/null; then wait "$pg_pid"; exit 1; fi
    sleep 1
done
gosu postgres pg_isready -q -h /var/run/postgresql -U postgres

startup gosu postgres psql -h /var/run/postgresql --set ON_ERROR_STOP=1 <<'SQL'
SELECT 'CREATE ROLE fairtoy LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fairtoy') \gexec
SELECT 'CREATE DATABASE fairtoy OWNER fairtoy'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'fairtoy') \gexec
SQL

startup gosu fairtoy alembic upgrade head
startup gosu fairtoy fairtoy-import \
    --idempotency-key local-catalog-v1 \
    --finishers /data/finishers.csv \
    --suppliers /data/suppliers.csv \
    --factories /data/factories.csv \
    --parts /data/parts.csv \
    --toys /data/toys.csv \
    --bill-of-materials /data/bill_of_materials.csv

gosu fairtoy uvicorn app.main:app --host 127.0.0.1 --port 8000 --root-path /api \
    --timeout-graceful-shutdown 5 &
api_pid=$!
nginx -g 'daemon off;' &
web_pid=$!

set +e
wait -n "$pg_pid" "$api_pid" "$web_pid"
status=$?
set -e
printf 'A required service exited (status %s); stopping container.\n' "$status" >&2
exit 1
