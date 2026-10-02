#!/usr/bin/env bash
# Live Stage 9 policy study. Expects these in the environment, forwarded from Windows:
#   SETTLEMENT_GATEWAY_ENDPOINT, SETTLEMENT_GATEWAY_KEY, S09_M5_LIVE_GRANT,
#   S09_STUDY_CALLS_ALREADY_SPENT
# Never echoes the key.
set -u
ROOT=/mnt/d/AI/Agent-Society-v2-investigation-review
PY=/home/ubuntu/.venvs/as9/bin/python
LOG=/mnt/d/AI/s09o/logs/live-study.log
OUT=/mnt/d/AI/s09o/evidence-live
DB=s09o_live_01
MODEL=inclusionai/ling-3.0-flash-vl-free

cd "$ROOT" || exit 90
export PYTHONPATH="$ROOT:$ROOT/src:$ROOT/experiments"
export SETTLEMENT_GATEWAY_API=responses

{
  echo "=== live study ==="
  date -Is
  echo "endpoint=${SETTLEMENT_GATEWAY_ENDPOINT:-UNSET}"
  echo "key present=$([ -n "${SETTLEMENT_GATEWAY_KEY:-}" ] && echo yes || echo no)"
  echo "grant present=$([ -n "${S09_M5_LIVE_GRANT:-}" ] && echo yes || echo no)"
  echo "already spent=${S09_STUDY_CALLS_ALREADY_SPENT:-unset}"
  echo "model=$MODEL"
  echo "db=$DB"
  "$PY" -c 'import settlement,sys; print("settlement="+settlement.__file__); print("python="+sys.version)'

  dropdb -h /var/run/postgresql -U ubuntu --if-exists "$DB"
  createdb -h /var/run/postgresql -U ubuntu "$DB" || exit 91
  "$PY" -c "from settlement import db; db.apply_migrations('dbname=$DB host=/var/run/postgresql user=ubuntu', '$ROOT/migrations'); print('migrations applied')" || exit 92
  rm -rf "$OUT"
  mkdir -p "$OUT"

  echo "--- run ---"
  "$PY" -m scripts.s09_pilot run \
      --dsn "dbname=$DB host=/var/run/postgresql user=ubuntu" \
      --out "$OUT" --mode live --model "$MODEL"
  echo "RUN_EXIT=$?"
  date -Is
} >"$LOG" 2>&1
tail -40 "$LOG"
