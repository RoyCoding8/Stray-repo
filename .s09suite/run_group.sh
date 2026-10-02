#!/bin/bash
# One bounded measurement group. Hard ceiling: 280s of pytest, 300s wall.
#
# Usage: run_group.sh <n> <file> [<file> ...]
#
# Why S09ISO_SCAN_DIR is set: the isolation harness creates and migrates a
# database for every redirectable seam it finds in tests/, which is 37 of them
# and 58 seconds, before a single test runs. Pointing the scan at a directory
# holding only this group's files creates only the stores those files need.
# It changes no test's semantics: each file still gets its own per-run store,
# named from this group's token. A store for a file that is not running is
# simply never created.
#
# A distinct token per group: the harness derives every database name from it,
# so two groups can never share a store, and a killed group's leaked databases
# are attributable to exactly one token.
set -u
REPO=/home/ubuntu/AI/Agent-Society-v2
cd "$REPO" || exit 2

N="$1"; shift
LOG=".s09suite/g${N}.log"
DONE=".s09suite/g${N}.done"
SCAN=".s09suite/scan_g${N}"

export S09ISO_TOKEN="$(printf '5e9b%04x' "$N")"
export S09ISO_SCAN_DIR="$REPO/$SCAN"

rm -rf "$SCAN"; mkdir -p "$SCAN"
for f in "$@"; do ln -sf "$REPO/$f" "$SCAN/$(basename "$f")"; done

# A previous group killed at the 280s ceiling leaves its databases behind, and
# a rerun of that same group then dies at CREATE DATABASE with
# DuplicateDatabase before a single test runs. Reclaim this group's own token
# first. The pattern is anchored to the token this script derives, so it can
# only ever name databases this lane created.
psql "dbname=postgres host=/var/run/postgresql user=ubuntu" -tAc \
  "select datname from pg_database where datname ~ '^s09iso_${S09ISO_TOKEN}_'" \
  2>/dev/null | while read -r db; do
    case "$db" in *r03flow*|*ec02test_live*) continue;; esac
    psql "dbname=postgres host=/var/run/postgresql user=ubuntu" -q \
      -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" >/dev/null 2>&1
  done

: > "$DONE"
{
  echo "=== group $N  token=$S09ISO_TOKEN  files=$# ==="
  for f in "$@"; do echo "  $f"; done
} >> "$DONE"

timeout -k 20 280 .venv/bin/python -m pytest -q -p no:cacheprovider -rfE \
  --tb=line --timeout=200 --timeout-method=signal "$@" > "$LOG" 2>&1
RC=$?

# pytest -q hides failure counts from a grep for ^FAILED: count the dot stream.
LAST="$(grep -E '^[0-9]+ (failed|passed)' "$LOG" | tail -1)"
{
  echo "rc=$RC"
  echo "summary: ${LAST:-<none: group did not finish>}"
  if [ "$RC" -eq 124 ] || [ "$RC" -eq 137 ]; then
    echo "KILLED-BY-TIMEOUT: token=$S09ISO_TOKEN leaked its databases; reclaim them"
  fi
} >> "$DONE"
rm -rf "$SCAN"
cat "$DONE"
