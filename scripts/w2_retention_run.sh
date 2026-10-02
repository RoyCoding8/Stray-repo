#!/usr/bin/env bash
# Run the W2 retention and adaptation contrasts under WSL, where child
# processes work.
#
# Modelled on scripts/w2_e2_contrast_run.sh, which is the working recipe for
# this route. Three things differ and each is deliberate:
#
# * the module is w2_retention_campaign, not e2_contrast_campaign;
# * the relay port is 4117, because 4100 is held by a relay from another
#   lane whose Windows bridge half points at a worktree that no longer
#   exists, and this script refuses to reuse a relay it did not verify;
# * max_output_tokens is 1024, not 2048. The route fails at 2048 on this
#   campaign's prompts, so the budget is the one the last campaign
#   measured as working rather than the one the inherited cap sheet names.
#
# S09ISO_DISABLE is required because conftest_isolation.py:701 returns early
# only when it is set, and the three settlement DSNs are unset so nothing
# can reach a real store by accident. The gateway key is read from the
# environment and never written to an artifact.
set -euo pipefail

WORKTREE=/mnt/d/AI/Agent-Society-v2/.worktrees/w2-e2-retention
PY=/root/w0venv/bin/python3
RELAY_PORT=4117
MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
MAX_OUTPUT_TOKENS=1024
TOKEN=invr1w2retention
DBFILE=/tmp/${TOKEN}.dsn

cd "$WORKTREE"
export WORKTREE
unset SETTLEMENT_DSN SETTLEMENT_TEST_DSN SETTLEMENT_TEST_TRUNCATE_DSN
export S09ISO_DISABLE=1
export PYTHONPATH="$WORKTREE:$WORKTREE/src"
export SETTLEMENT_GATEWAY_ENDPOINT="http://127.0.0.1:${RELAY_PORT}/v1/"
export SETTLEMENT_GATEWAY_KEY="${SETTLEMENT_GATEWAY_KEY:-sk-cx-local}"
export SETTLEMENT_MODEL="$MODEL"
export SETTLEMENT_REPLICA_MODEL="$MODEL"
export SETTLEMENT_CONTRAST_MODEL="$MODEL"
# `RouteContract.from_mapping` (settlement/gateway.py:49) requires all five of
# endpoint, requested_model, resolved_model, provider and tier, and refuses an
# incomplete one before the send as `pre-send-route-refusal`.
#
# The endpoint carries no trailing slash, because `HttpGatewayAdapter.__init__`
# (gateway_http.py:552) does `endpoint.rstrip("/")` on the adapter's own copy
# and `_endpoints_equal` compares the two canonical forms.
ROUTE_ENDPOINT="http://127.0.0.1:${RELAY_PORT}/v1"

# The provider string is the one the RESPONSE body names, not the one
# `/v1/models` attributes the catalog entry to. `_returned_route` reads
# `provider` off the response and `route_matches` is case-insensitive on it.
export SETTLEMENT_EXPECTED_ROUTE="{\"endpoint\":\"$ROUTE_ENDPOINT\",\"requested_model\":\"$MODEL\",\"resolved_model\":\"$MODEL\",\"provider\":\"Nvidia\",\"tier\":\"free\"}"
export SETTLEMENT_ADMIN_DSN="dbname=postgres host=/var/run/postgresql user=root"

# The relay is verified, not assumed. A relay left behind by another lane
# answers on its port and can still be wired to a bridge half that no longer
# exists, so a health check alone is not enough: one real completion is
# required before any campaign dispatch is spent.
if ! curl -sf -m 5 "http://127.0.0.1:${RELAY_PORT}/health" >/dev/null; then
  nohup "$PY" scripts/wsl_gateway_relay.py serve --port "$RELAY_PORT" \
    >/tmp/relay${RELAY_PORT}.log 2>&1 &
  sleep 4
fi
curl -sf -m 5 "http://127.0.0.1:${RELAY_PORT}/health" >/dev/null || {
  echo "relay is not healthy on ${RELAY_PORT}" >&2; exit 4; }
if ! curl -sf -m 60 -X POST "http://127.0.0.1:${RELAY_PORT}/v1/chat/completions" \
    -H "Authorization: Bearer ${SETTLEMENT_GATEWAY_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with the single word OK.\"}],\"max_tokens\":16}" \
    >/dev/null; then
  echo "relay answered no completion; the Windows bridge half is probably"
  echo "wired to a worktree that no longer exists" >&2
  exit 5
fi

RERUN=""
if [ "${1:-}" = "--rerun" ]; then
  RERUN="--rerun"
  TOKEN=invr1w2retentionr2
fi
DBFILE="/tmp/${TOKEN}.dsn"

"$PY" - "$TOKEN" "$DBFILE" <<'PYEOF'
import os
import sys

os.environ.setdefault("S09ISO_DISABLE", "1")
sys.path.insert(0, os.environ["WORKTREE"])
sys.path.insert(0, os.path.join(os.environ["WORKTREE"], "src"))
from experiments.ad01 import s09_run_isolation

token, path = sys.argv[1], sys.argv[2]
db = s09_run_isolation.create_disposable_db(
    token, admin_dsn=os.environ.get("SETTLEMENT_ADMIN_DSN"))
with open(path, "w", encoding="utf-8") as handle:
    handle.write(db.dsn)
print("store: %s" % db.name)
PYEOF

DSN=$(cat "$DBFILE")
exec "$PY" -m experiments.ad01.w2_retention_campaign \
  --dsn "$DSN" --max-output-tokens "$MAX_OUTPUT_TOKENS" $RERUN
