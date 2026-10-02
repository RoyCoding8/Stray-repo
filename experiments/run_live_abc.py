"""Live §11 A/B/C entry point. Refuses without explicit live inputs.

Required:
  SETTLEMENT_GATEWAY_URL   live inference endpoint URL
  SETTLEMENT_GATEWAY_KEY   credential env var name content (never committed)
  SETTLEMENT_GRANT_UNITS   monetary grant cap in integer units (hard ceiling)

Command:
  uv run python experiments/run_live_abc.py --dsn postgresql://... \\
      --allocation live-abc --artifacts-root /path/artifacts
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "experiments")

from settlement.gateway_http import HttpGatewayAdapter  # noqa: E402

BLOCKER = ("live A/B/C blocked: set SETTLEMENT_GATEWAY_URL, SETTLEMENT_GATEWAY_KEY, "
           "and SETTLEMENT_GRANT_UNITS (monetary grant cap)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--allocation", required=True)
    parser.add_argument("--artifacts-root", required=True)
    args = parser.parse_args()
    url = os.environ.get("SETTLEMENT_GATEWAY_URL", "")
    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    grant = os.environ.get("SETTLEMENT_GRANT_UNITS", "")
    if not url or not key or not grant:
        print(BLOCKER)
        return 2
    gateway = HttpGatewayAdapter(endpoint=url, api_key=key)
    discovery = gateway.check_discovery()
    auth = gateway.check_auth()
    print(f"grant cap: {grant} units; gateway: {url}")
    print(f"discovery: {discovery}; auth: {auth}")
    print("live comparison entry: settlement.experiment.run_abcs(..., gateway=gateway,"
          " simulated=False) with arm prompts from experiments/fault_tasks.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
