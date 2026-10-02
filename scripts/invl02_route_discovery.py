"""Record a read-only route reconciliation against a gateway model list."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from settlement.gateway_http import HttpGatewayAdapter


def _git_commit() -> str:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def discover_route(out, *, client=None) -> dict:
    from experiments.ad01 import live_construct as live
    from scripts.invl02_live import _load_live_environment

    route = dict(live.OUTPUT_ROUTE)
    if client is None:
        _load_live_environment()
        import os
        endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
        api_key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    else:
        endpoint = route["endpoint"]
        api_key = "mock-client"
    adapter = HttpGatewayAdapter(
        endpoint=endpoint,
        api_key=api_key,
        api="responses",
        client=client,
        expected_route=route,
    )
    module_path = Path(live.__file__).resolve()
    evidence = {
        "schema": "settlement-gateway/route-discovery-v1",
        "module": {
            "path": str(module_path),
            "source_sha256": hashlib.sha256(
                module_path.read_bytes()).hexdigest(),
        },
        "git_commit": _git_commit(),
        "route_passed_to_adapter": route,
        **adapter.discover_model_route(route),
    }
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "route-discovery.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=1) + "\n")
    return evidence


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    if not args or args[0] != "--out":
        print("usage: invl02_route_discovery.py --out DIRECTORY",
              file=sys.stderr)
        return 2
    try:
        out = args[args.index("--out") + 1]
        evidence = discover_route(out)
    except Exception as exc:
        print("route discovery refused: %s" % exc, file=sys.stderr)
        return 3
    print("route discovery %s" % evidence["result"]["verdict"])
    return 0 if evidence["result"]["verdict"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
