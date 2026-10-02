"""Bounded live model campaign for Representation Lane D (RPR-03/06).

Without a configured gateway endpoint, key and grant this command performs
no inference, emits no model output, real or simulated, and records the
exact runnable command, the capped campaign budget and equal-opportunity
accounting. With a full configuration it runs the finite acquisition
orchestration in :mod:`campaign`: 2 source + 2 transfer broker-routed
model construction calls per arm (12 total, fixed token caps, retries 0),
response parsing into candidate bytes, publication through artifacts,
staged execution of those bytes through the existing profile runner,
verdict recording and A/B/C retention with the core frozen before any
graph exposure. Credentials alone never suffice: a durable seeded grant
is admitted before any dispatch, and gateway discovery/auth remain
explicit external blockers after the runnable path exists.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

REP = ROOT / "experiments" / "representation"

from experiments.representation.acquire import campaign

ENDPOINT_ENV = "SETTLEMENT_GATEWAY_ENDPOINT"
KEY_ENV = "SETTLEMENT_GATEWAY_KEY"
GRANT_ENV = "SETTLEMENT_GRANT_UNITS"

CAMPAIGN_BUDGET = dict(campaign.BUDGET)

RUNNABLE_COMMAND = ("SETTLEMENT_TEST_DSN=$SETTLEMENT_TEST_DSN "
                    ".venv/bin/python "
                    "experiments/representation/acquire/live_campaign.py "
                    "--protocol rpr-acq-C --grant $SETTLEMENT_GRANT_UNITS "
                    "--model $SETTLEMENT_MODEL --dsn $SETTLEMENT_TEST_DSN "
                    "--artifacts-root $ARTIFACT_ROOT")


def preflight(env=None, cli=None) -> dict:
    config = campaign.resolve_config(cli, dict(os.environ) if env is None
                                     else dict(env))
    missing = [name for name, value in
               ((ENDPOINT_ENV, config["endpoint"]),
                (KEY_ENV, config["gateway_key"]),
                (GRANT_ENV, config["grant"])) if not value]
    if missing:
        return {"blocked": True, "reason": "missing-inputs",
                "missing": missing,
                "command": RUNNABLE_COMMAND,
                "budget": CAMPAIGN_BUDGET,
                "equal_opportunity": campaign.EQUAL_OPPORTUNITY,
                "spent": {"model_calls": 0, "input_tokens": 0,
                          "output_tokens": 0, "grant_units": 0},
                "model_output": "none: no inference performed, nothing"
                                " simulated or stubbed"}
    try:
        grant_units = int(config["grant"])
    except (TypeError, ValueError):
        grant_units = 0
    if grant_units <= 0:
        return {"blocked": True, "reason": "invalid-grant",
                "missing": [],
                "command": RUNNABLE_COMMAND,
                "budget": CAMPAIGN_BUDGET,
                "equal_opportunity": campaign.EQUAL_OPPORTUNITY,
                "spent": {"model_calls": 0, "input_tokens": 0,
                          "output_tokens": 0, "grant_units": 0},
                "model_output": "none: no inference performed, nothing"
                                " simulated or stubbed",
                "detail": "grant %r is not a positive integer"
                          % (config["grant"],)}
    need, _ = campaign.required_grant_for_contexts()
    if grant_units < need:
        return {"blocked": True, "reason": "grant-below-requirement",
                "missing": [],
                "command": RUNNABLE_COMMAND,
                "budget": CAMPAIGN_BUDGET,
                "equal_opportunity": campaign.EQUAL_OPPORTUNITY,
                "spent": {"model_calls": 0, "input_tokens": 0,
                          "output_tokens": 0, "grant_units": 0},
                "model_output": "none: no inference performed, nothing"
                                " simulated or stubbed",
                "grant_units": grant_units,
                "required_exposure": need}
    if not config["model"]:
        return {"blocked": True, "reason": "missing-model",
                "missing": [],
                "command": RUNNABLE_COMMAND,
                "budget": CAMPAIGN_BUDGET,
                "equal_opportunity": campaign.EQUAL_OPPORTUNITY,
                "spent": {"model_calls": 0, "input_tokens": 0,
                          "output_tokens": 0, "grant_units": 0},
                "model_output": "none: no inference performed, nothing"
                                " simulated or stubbed",
                "detail": "set --model or SETTLEMENT_MODEL"}
    if not config["dsn"]:
        return {"blocked": True, "reason": "missing-dsn",
                "missing": [],
                "command": RUNNABLE_COMMAND,
                "budget": CAMPAIGN_BUDGET,
                "equal_opportunity": campaign.EQUAL_OPPORTUNITY,
                "spent": {"model_calls": 0, "input_tokens": 0,
                          "output_tokens": 0, "grant_units": 0},
                "model_output": "none: no inference performed, nothing"
                                " simulated or stubbed",
                "detail": "set --dsn, SETTLEMENT_TEST_DSN or SETTLEMENT_DSN"}
    return {"blocked": False, "reason": "configured",
            "missing": [],
            "command": RUNNABLE_COMMAND,
            "budget": CAMPAIGN_BUDGET,
            "equal_opportunity": campaign.EQUAL_OPPORTUNITY,
            "endpoint": config["endpoint"],
            "key_configured": True,
            "grant_units": grant_units,
            "model": config["model"],
            "dsn_configured": True,
            "spent": {"model_calls": 0, "input_tokens": 0,
                      "output_tokens": 0, "grant_units": 0}}


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Lane D live campaign")
    parser.add_argument("--protocol", default="rpr-acq-C")
    parser.add_argument("--grant", default="")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--gateway-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--tag", default="live")
    parser.add_argument("--allocation", default="")
    parser.add_argument("--artifacts-root", default="")
    parser.add_argument("--staging-root", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--evidence-root", default=str(REP / "evidence"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    cli = {"endpoint": args.endpoint, "gateway_key": args.gateway_key,
           "grant": args.grant, "model": args.model, "dsn": args.dsn}
    record = {"protocol": args.protocol, **preflight(None, cli)}
    if record["blocked"]:
        print(json.dumps(record, indent=2))
        if args.write:
            target = Path(args.evidence_root) / "live_blocker.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((json.dumps(record, sort_keys=True, indent=2)
                                + "\n").encode())
        return 2
    from settlement.gateway_http import (HttpGatewayAdapter,
                                         gateway_timeout_overrides)
    config = campaign.resolve_config(cli, os.environ)
    try:
        adapter = HttpGatewayAdapter(
            endpoint=config["endpoint"], api_key=config["gateway_key"],
            api=os.environ.get("SETTLEMENT_GATEWAY_API", "chat"),
            **gateway_timeout_overrides())
    except ValueError as exc:
        blocked = {"protocol": args.protocol,
                   **campaign.blocked_record("gateway-config", detail=str(exc))}
        print(json.dumps(blocked, indent=2))
        return 2
    record = campaign.run_campaign(
        config["dsn"], tag=args.tag, model=config["model"],
        grant_units=int(config["grant"]), gateway=adapter,
        artifacts_root=args.artifacts_root or "var/rpr-camp-artifacts",
        staging_root=args.staging_root or "var/rpr-camp-staging",
        runs_root=args.runs_root or "var/rpr-camp-runs",
        evidence_root=args.evidence_root,
        allocation_id=args.allocation)
    print(json.dumps(record, indent=2))
    return 0 if not record.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
