#!/usr/bin/env bash
# Run the E2 contrast campaign under WSL, where child processes work.
#
# The environment is set here rather than in the caller so a rerun sends the
# same bytes. S09ISO_DISABLE is required because conftest_isolation.py:701
# returns early only when it is set, and the three settlement DSNs are unset
# so nothing can reach a real store by accident. The gateway key is read
# from the environment and never written to an artifact.
#
# The store is created here through s09_run_isolation, which is the module
# that owns disposable databases, and is left in place on exit so the
# receipts this run wrote can be re-read. `drop_campaign_db` removes it.
set -euo pipefail

WORKTREE=/mnt/d/AI/Agent-Society-v2/.worktrees/w2-e2-contrast
PY=/root/w0venv/bin/python3
RELAY_PORT=4100
MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
TOKEN=invr1e2contrast
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
# and `_endpoints_equal` compares the two canonical forms. A contract that kept
# the slash is refused as `gateway endpoint is not the frozen endpoint`.
ROUTE_ENDPOINT="http://127.0.0.1:${RELAY_PORT}/v1"

# The provider string is the one the RESPONSE body names, not the one
# `/v1/models` attributes the catalog entry to. `_returned_route` reads
# `provider` (or `provider_id`) off the response, and `route_matches` is
# case-insensitive on it, so a frozen `Nvidia` is the value the live body
# carries and `Kilo API`, which is the catalog's `owned_by`, is not. The
# distinction matters: the catalog is a listing and the response is the
# attestation, and the adapter reads the attestation.
export SETTLEMENT_EXPECTED_ROUTE="{\"endpoint\":\"$ROUTE_ENDPOINT\",\"requested_model\":\"$MODEL\",\"resolved_model\":\"$MODEL\",\"provider\":\"Nvidia\",\"tier\":\"free\"}"
# Named, not defaulted: this script runs on the WSL host that owns the
# socket, and the value passes straight into create_disposable_db, whose
# refusal on an empty route is what keeps the script from guessing a box.
export SETTLEMENT_ADMIN_DSN="${SETTLEMENT_ADMIN_DSN:-dbname=postgres host=/var/run/postgresql user=root}"

if ! pgrep -f "wsl_gateway_relay.py serve" >/dev/null; then
  nohup "$PY" scripts/wsl_gateway_relay.py serve --port "$RELAY_PORT" \
    >/tmp/relay.log 2>&1 &
  sleep 4
fi
curl -sf -m 5 "http://127.0.0.1:${RELAY_PORT}/health" >/dev/null || {
  echo "relay is not healthy" >&2; exit 4; }

RERUN=""
SUFFIX=""
if [ "${1:-}" = "--rerun" ]; then
  RERUN="--rerun"
  SUFFIX="r2"
  TOKEN=invr1e2contrastr2
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
exec "$PY" -m experiments.ad01.e2_contrast_campaign --dsn "$DSN" $RERUN
