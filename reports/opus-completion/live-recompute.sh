#!/usr/bin/env bash
# Independent offline recomputation of the live study bundle.
# Runs in a fresh process with NO gateway variables and an intentionally
# unreachable database DSN, so a database or provider dependency would fail loudly.
set -u
ROOT=/mnt/d/AI/Agent-Society-v2-investigation-review
PY=/home/ubuntu/.venvs/as9/bin/python
LOG=/mnt/d/AI/s09o/logs/live-recompute.log
OUT=/mnt/d/AI/s09o/evidence-live

cd "$ROOT" || exit 90
export PYTHONPATH="$ROOT:$ROOT/src:$ROOT/experiments"
unset SETTLEMENT_GATEWAY_ENDPOINT SETTLEMENT_GATEWAY_KEY SETTLEMENT_GATEWAY_API
unset S09_M5_LIVE_GRANT S09_STUDY_CALLS_ALREADY_SPENT VERCEL_API_KEY AI_GATEWAY_API_KEY
export SETTLEMENT_DSN="dbname=definitely_not_a_database host=/nonexistent user=nobody"

{
  echo "=== offline recomputation ==="
  date -Is
  echo "gateway endpoint present: ${SETTLEMENT_GATEWAY_ENDPOINT:-NO}"
  echo "gateway key present: ${SETTLEMENT_GATEWAY_KEY:-NO}"
  echo "dsn points at: $SETTLEMENT_DSN"
  echo "--- verifier ---"
  "$PY" -m scripts.s09_verify "$OUT"
  echo "VERIFY_EXIT=$?"
  date -Is
} >"$LOG" 2>&1
tail -45 "$LOG"
