#!/usr/bin/env bash
# Benchmark GET /users against a throwaway copy of the stack.
#
# usage: scripts/bench.sh [gunicorn flags]
#   scripts/bench.sh                  # gunicorn's default: 1 sync worker
#   scripts/bench.sh "--workers 4"
#
# Environment: API_PORT (5001), REQUESTS (3000), CONCURRENCY (20), SEED_USERS (50).
# Uses its own Compose project ("bench") and removes it, and its volume, afterwards.
set -euo pipefail

cd "$(dirname "$0")/.."

export API_PORT="${API_PORT:-5001}"
export GUNICORN_CMD_ARGS="${1:-}"
REQUESTS="${REQUESTS:-3000}"
CONCURRENCY="${CONCURRENCY:-20}"
SEED_USERS="${SEED_USERS:-50}"
PROJECT=bench

trap 'docker compose -p $PROJECT down -v >/dev/null 2>&1' EXIT

if ! out=$(docker compose -p $PROJECT up --build -d --wait 2>&1); then
  echo "$out" >&2
  exit 1
fi

for i in $(seq 1 "$SEED_USERS"); do
  curl -s -o /dev/null -X POST "localhost:$API_PORT/users" \
    -H 'Content-Type: application/json' \
    -d "{\"name\": \"User $i\", \"email\": \"user$i@example.com\"}"
done

URL="http://localhost:$API_PORT/users"
python3 scripts/load.py "$URL" 200 5 $PROJECT >/dev/null   # warm-up
echo "gunicorn flags: '${GUNICORN_CMD_ARGS}'  requests: $REQUESTS  concurrency: $CONCURRENCY"
python3 scripts/load.py "$URL" "$REQUESTS" "$CONCURRENCY" $PROJECT
