#!/usr/bin/env bash
# Runs a Stage 9 gate set in the WSL runtime and writes output plus exit status to a durable log.
# Usage: gate.sh <log-name> <pytest-target> [more targets...]
set -u
ROOT=/mnt/d/AI/Agent-Society-v2-investigation-review
PY=/home/ubuntu/.venvs/as9/bin/python
LOGDIR=/mnt/d/AI/s09o/logs
mkdir -p "$LOGDIR"
NAME=$1
shift
LOG="$LOGDIR/$NAME.log"
cd "$ROOT" || exit 90
export PYTHONPATH="$ROOT:$ROOT/src:$ROOT/experiments"
{
  echo "=== gate $NAME ==="
  date -Is
  echo "root=$ROOT"
  echo "targets=$*"
  "$PY" -c 'import settlement, sys; print("settlement.__file__=" + settlement.__file__); print("python=" + sys.version)'
  "$PY" -m pytest "$@" -q -p no:cacheprovide
  echo "EXIT=$?"
  date -Is
} >"$LOG" 2>&1
tail -25 "$LOG"
