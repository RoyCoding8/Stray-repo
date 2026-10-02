#!/usr/bin/env bash
# Drops ONLY databases whose names begin s09o_, which are owned by this task.
# Never touches s09_local_*, ec02test_*, inv_*, or anything else.
set -u
H=/var/run/postgresql
U=ubuntu
mine=$(psql -h "$H" -U "$U" -lqt -A -F, 2>/dev/null | cut -d, -f1 | grep '^s09o_' || true)
if [ -z "$mine" ]; then
  echo "no s09o_ databases present"
else
  for d in $mine; do
    dropdb -h "$H" -U "$U" --if-exists "$d" && echo "dropped $d"
  done
fi
echo "--- remaining s09 databases ---"
psql -h "$H" -U "$U" -lqt -A -F, 2>/dev/null | cut -d, -f1 | grep '^s09' || echo "none"
