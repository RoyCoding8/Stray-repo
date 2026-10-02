"""Bounded live model campaign preflight for Representation Lane D (RPR-03/06).

Exact-blocker record: without a configured gateway endpoint, key and grant,
the live acquisition/transfer campaign cannot run. This command performs no
inference, emits no model output, real or simulated, and records the exact
runnable command, the capped campaign budget and equal-opportunity
accounting. With a gateway present it still refuses: spending grant funds
needs coordinator authorization, so presence only upgrades the record from
blocked-missing-inputs to blocked-awaiting-authorization.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

REP = ROOT / "experiments" / "representation"

ENDPOINT_ENV = "SETTLEMENT_GATEWAY_ENDPOINT"
KEY_ENV = "SETTLEMENT_GATEWAY_KEY"
GRANT_ENV = "SETTLEMENT_GRANT_UNITS"

CAMPAIGN_BUDGET = {"model_calls": 12, "input_tokens_per_call": 16384,
                   "output_tokens_per_call": 8192, "retries": 0,
                   "per_arm": {"source_calls": 2, "transfer_calls": 2},
                   "unused_capacity_transfer": False}

RUNNABLE_COMMAND = ("SETTLEMENT_TEST_DSN=$SETTLEMENT_TEST_DSN "
                    ".venv/bin/python "
                    "experiments/representation/acquire/live_campaign.py "
                    "--protocol rpr-acq-C --grant $SETTLEMENT_GRANT_UNITS "
                    "--artifacts-root $ARTIFACT_ROOT")


def preflight(env=None) -> dict:
    env = dict(os.environ) if env is None else dict(env)
    missing = [name for name in (ENDPOINT_ENV, KEY_ENV, GRANT_ENV)
               if not env.get(name)]
    if missing:
        return {"blocked": True, "reason": "missing-inputs",
                "missing": missing,
                "command": RUNNABLE_COMMAND,
                "budget": CAMPAIGN_BUDGET,
                "equal_opportunity": "2 source + 2 transfer calls per arm;"
                                     " unused capacity never transferred",
                "spent": {"model_calls": 0, "input_tokens": 0,
                          "output_tokens": 0, "grant_units": 0},
                "model_output": "none: no inference performed, nothing"
                                " simulated or stubbed"}
    return {"blocked": True, "reason": "awaiting-authorization",
            "missing": [],
            "command": RUNNABLE_COMMAND,
            "budget": CAMPAIGN_BUDGET,
            "equal_opportunity": "2 source + 2 transfer calls per arm;"
                                 " unused capacity never transferred",
            "spent": {"model_calls": 0, "input_tokens": 0,
                      "output_tokens": 0, "grant_units": 0},
            "model_output": "none: live construction needs coordinator"
                            " authorization before any grant is spent"}


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Lane D live preflight")
    parser.add_argument("--protocol", default="rpr-acq-C")
    parser.add_argument("--grant", default="")
    parser.add_argument("--artifacts-root", default="")
    parser.add_argument("--evidence-root", default=str(REP / "evidence"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    record = {"protocol": args.protocol, **preflight()}
    print(json.dumps(record, indent=2))
    if args.write:
        target = Path(args.evidence_root) / "live_blocker.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((json.dumps(record, sort_keys=True, indent=2)
                            + "\n").encode())
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
