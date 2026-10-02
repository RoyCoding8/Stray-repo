#!/usr/bin/env bash
# Live study preflight. Reports presence only, never a secret value.
echo "=== WSL env presence ==="
for n in SETTLEMENT_GATEWAY_ENDPOINT SETTLEMENT_GATEWAY_URL SETTLEMENT_GATEWAY_KEY \
         SETTLEMENT_GATEWAY_API SETTLEMENT_DSN VERCEL_API_KEY AI_GATEWAY_API_KEY; do
  v=$(printenv "$n" || true)
  if [ -n "$v" ]; then echo "$n : set"; else echo "$n : unset"; fi
done

echo "=== repo env files ==="
ls -a /mnt/d/AI/Agent-Society-v2-investigation-review | grep -i '^\.env' || echo "no .env* in repo root"

echo "=== home shell init referencing SETTLEMENT or GATEWAY ==="
for f in /home/ubuntu/.bashrc /home/ubuntu/.profile /home/ubuntu/.bash_profile /home/ubuntu/.env; do
  if [ -f "$f" ]; then
    hits=$(grep -c -iE 'SETTLEMENT|GATEWAY|API_KEY' "$f" || true)
    echo "$f exists, matching lines: $hits"
  else
    echo "$f absent"
  fi
done

echo "=== existing databases ==="
psql -h /var/run/postgresql -U ubuntu -lqt -F '|' -A 2>/dev/null | cut -d'|' -f1 | grep -vE '^(template[01]|postgres|ubuntu)?$' || echo "none listed"

echo "=== prior live study roots in any reachable db ==="
echo "(no s09 databases exist, so no prior grant rows are reachable)"
