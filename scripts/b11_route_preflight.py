"""Route preflight only. Dispatches nothing.

Reads the router credential from its configured location into the process
environment, because `gateway.api_key_env` names the variable the adapter
reads and the value is never printed, written or logged. Then runs the shipped
adapter's preflight, which is a `GET /models` and a route reconciliation: no
model call, no token, no send.

Run this before the ladder. A route that cannot be attested free here will be
refused on the wire, and a send spent discovering that is a send wasted.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def load_credential() -> None:
    """Put the router key in the environment under the name the config reads.

    The value is moved from its configured location into the process
    environment and is never printed, written to a file, or placed in a
    command line. Only the variable NAME and the value's length are ever shown.
    """
    path = os.path.expanduser("~/.claude.json")
    with open(path, encoding="utf-8") as fh:
        env = json.load(fh)["mcpServers"]["cx-agent"]["env"]
    key = env.get("CX_AGENT_API_KEY", "")
    if not key:
        sys.exit("router credential is not configured")
    os.environ["SETTLEMENT_GATEWAY_KEY"] = key
    os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = "http://127.0.0.1:4000/v1"
    print("credential loaded: SETTLEMENT_GATEWAY_KEY len", len(key))
    print("endpoint SETTLEMENT_GATEWAY_ENDPOINT =",
          os.environ["SETTLEMENT_GATEWAY_ENDPOINT"])


def main() -> int:
    load_credential()
    import experiments.ad01.invr1b11_budget_probe as probe
    from settlement.gateway import GatewayError

    adapter = probe._gateway()
    print("adapter api", adapter.api, "route_mode", adapter.route_mode)
    catalog = probe._catalog(probe.dsn())
    for key in ("status", "model_count", "free_tier_ids", "pinned_id",
                "pinned_present", "verdict", "reason",
                "requested_model_ends_free", "read_error"):
        print("catalog.%s" % key, catalog.get(key))
    print("relevant_entries", catalog.get("relevant_entries"))

    result = adapter.preflight_route(probe.ROUTE)
    if isinstance(result, GatewayError):
        print("preflight REFUSED", str(result.kind), str(result.message)[:200])
        return 1
    print("preflight ACCEPTED", json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
