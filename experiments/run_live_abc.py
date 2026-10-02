"""Live §11 A/B/C entry point: executes the experiment protocol end to end.

Live mode requires explicit inputs and refuses otherwise (exit 2):
  SETTLEMENT_GATEWAY_ENDPOINT  live inference endpoint URL
      (SETTLEMENT_GATEWAY_URL is accepted as a legacy alias)
  SETTLEMENT_GATEWAY_KEY   gateway credential value (never committed)
  SETTLEMENT_GRANT_UNITS   monetary grant cap in integer units (hard ceiling)
  --model (or SETTLEMENT_MODEL)  configured model selection (required live)

Candidate execution is runsc-contained by default (--launcher runsc with a
pinned --runsc-image). Uncontained local execution needs both
`--launcher local` and `--allow-uncontained`; without admitted containment
the command refuses instead of running exposed. The grant cap binds to a
capped sub-allocation and the whole run executes under it.

Deterministic mode (--deterministic) runs the same protocol with scripted
adapters and no live endpoint, for local demonstration. Its report is
labeled simulated and never a live result.

Command:
  uv run python experiments/run_live_abc.py --dsn postgresql://... \\
      --allocation live-abc --artifacts-root /path/artifacts --model chat-x \\
      --runsc-image sha256:...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, "src")
sys.path.insert(0, "experiments")

from settlement import experiment, store
from settlement.common import Command, SettlementError
from settlement.gateway import GatewayError
from settlement.gateway_http import HttpGatewayAdapter
from settlement.launcher_local import LocalLauncher

BLOCKER = ("live A/B/C blocked: set SETTLEMENT_GATEWAY_ENDPOINT, SETTLEMENT_GATEWAY_KEY, "
           "and SETTLEMENT_GRANT_UNITS (monetary grant cap)")


def _select_launcher(args: argparse.Namespace):
    if args.launcher == "local" and not args.allow_uncontained:
        raise SettlementError(
            "live A/B/C refused: --launcher local needs --allow-uncontained; "
            "uncontained execution is never the silent default")
    if args.launcher == "runsc":
        if not args.runsc_image:
            raise SettlementError(
                "live A/B/C refused: --launcher runsc needs --runsc-image "
                "(pinned sha256 digest) or --launcher local with "
                "--allow-uncontained")
        from settlement.launcher_runsc import RunscLauncher
        launcher = RunscLauncher(args.runsc_image,
                                 run_dir=tempfile.mkdtemp(prefix="liveabc-runs-"),
                                 image_python=getattr(args, "runsc_python", "")
                                 or None)
        if launcher.available:
            return launcher
        if not args.allow_uncontained:
            raise SettlementError(
                f"live A/B/C refused: admitted containment unavailable "
                f"({launcher.reason}); pass --allow-uncontained to run exposed "
                "or fix the runsc host")
        print(f"warning: runsc unavailable ({launcher.reason}); "
              "running uncontained under explicit --allow-uncontained",
              file=sys.stderr)
    return LocalLauncher(tempfile.mkdtemp(prefix="liveabc-runs-"))


def _children_authorized(dsn: str, parent_id: str) -> int:
    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(authorized), 0) FROM allocations"
                        " WHERE parent_id = %s", (parent_id,))
            total = cur.fetchone()[0]
            conn.commit()
    return int(total)


def _bind_grant_cap(dsn: str, allocation_id: str, grant_units: int,
                    prefix: str) -> str:
    from settlement.common import ResultCode

    status = store.allocation_status(dsn, allocation_id)
    available = (int(status["authorized"]) - int(status["consumed"])
                 - int(status["reserved"])
                 - _children_authorized(dsn, allocation_id))
    if available <= 0:
        raise SettlementError(
            f"live A/B/C blocked: allocation {allocation_id} has no available units")
    cap = min(grant_units, available)
    child_id = f"{allocation_id}-{prefix}-cap"
    try:
        current = store.allocation_status(dsn, child_id)
    except SettlementError:
        current = None
    if current is None:
        result = store.subdivide_allocation(
            dsn, Command(request_id=f"{prefix}-subdivide",
                         payload={"parent_id": allocation_id,
                                  "child_id": child_id,
                                  "authorized": cap}))
        if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            raise SettlementError(
                f"live A/B/C refused: grant cap {cap} not admitted under "
                f"{allocation_id}: {result.detail}")
    elif int(current["authorized"]) > cap:
        raise SettlementError(
            f"live A/B/C refused: existing sub-allocation {child_id} authorizes "
            f"{current['authorized']} above the grant cap {cap}")
    return child_id


def _parse_ids(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _demo_double():
    from doubles import ScriptedDouble
    from fault_tasks import DEV_IDS, PANEL_IDS, TASKS, TRANSFER_IDS

    fixes = {t["id"]: t["fixed"] for t in TASKS}
    broken = {t["id"]: t["broken"] for t in TASKS}
    competence = {("B", "panel-triangular"): True, ("B", "panel-batcher"): True}
    for dev_id in DEV_IDS:
        competence[("DEV", dev_id)] = True
    return ScriptedDouble(competence, fixes, broken), DEV_IDS, PANEL_IDS, TRANSFER_IDS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--allocation", required=True)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--investigation", default="live-abc-inv")
    parser.add_argument("--protocol-prefix", default="liveabc")
    parser.add_argument("--evaluator-id", default="s3-eval")
    parser.add_argument("--evaluator-version", default="v1")
    parser.add_argument("--model", default=os.environ.get("SETTLEMENT_MODEL", ""))
    parser.add_argument("--deterministic", action="store_true")
    parser.add_argument("--launcher", default="runsc", choices=("runsc", "local"))
    parser.add_argument("--allow-uncontained", action="store_true")
    parser.add_argument("--runsc-image", default=os.environ.get("SETTLEMENT_RUNSC_IMAGE", ""))
    parser.add_argument("--runsc-python", default=os.environ.get("SETTLEMENT_RUNSC_PYTHON", ""))
    parser.add_argument("--dev", default="")
    parser.add_argument("--panel", default="")
    parser.add_argument("--transfer", default="")
    args = parser.parse_args()
    grant_units = 0
    if args.deterministic:
        adapter, dev_ids, panel_ids, transfer_ids = _demo_double()
        model, simulated = "scripted", True
    else:
        url = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT",
                             os.environ.get("SETTLEMENT_GATEWAY_URL", ""))
        key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
        grant = os.environ.get("SETTLEMENT_GRANT_UNITS", "")
        if not url or not key or not grant:
            print(BLOCKER)
            return 2
        try:
            grant_units = int(grant)
        except ValueError:
            print(f"live A/B/C blocked: SETTLEMENT_GRANT_UNITS={grant!r} is not an integer")
            return 2
        if grant_units <= 0 or not args.model:
            print("live A/B/C blocked: grant must be positive and --model (or SETTLEMENT_MODEL)"
                  " must select the comparison model")
            return 2
        try:
            launcher = _select_launcher(args)
        except SettlementError as exc:
            print(exc)
            return 3
        adapter = HttpGatewayAdapter(endpoint=url, api_key=key)
        status = adapter.check_discovery()
        if isinstance(status, GatewayError):
            print(f"live A/B/C blocked: discovery failed: {status}")
            return 3
        auth = adapter.check_auth()
        if isinstance(auth, GatewayError):
            print(f"live A/B/C blocked: auth failed: {auth}")
            return 3
        print(f"grant cap: {grant_units} units; gateway: {url}", file=sys.stderr)
        print(f"discovery: {status}; auth: {auth}", file=sys.stderr)
        model, simulated = args.model, False
        dev_ids, panel_ids, transfer_ids = None, None, None
        from fault_tasks import DEV_IDS, PANEL_IDS, TRANSFER_IDS

        dev_ids, panel_ids, transfer_ids = DEV_IDS, PANEL_IDS, TRANSFER_IDS
    dev_ids = _parse_ids(args.dev) or dev_ids
    panel_ids = _parse_ids(args.panel) or panel_ids
    transfer_ids = _parse_ids(args.transfer) or transfer_ids
    if args.deterministic:
        launcher = LocalLauncher(tempfile.mkdtemp(prefix="liveabc-runs-"))
        run_allocation = args.allocation
    try:
        if int(store.get_control(args.dsn).get("authority_version", 0)) < 1:
            print("live A/B/C blocked: no installed grant")
            return 3
        if args.deterministic:
            status = store.allocation_status(args.dsn, args.allocation)
            available = (int(status["authorized"]) - int(status["consumed"])
                         - int(status["reserved"]))
            if available <= 0:
                print(f"live A/B/C blocked: allocation {args.allocation} has no available units")
                return 3
        else:
            run_allocation = _bind_grant_cap(args.dsn, args.allocation,
                                             grant_units, args.protocol_prefix)
            print(f"grant cap: {grant_units} units; sub-allocation: {run_allocation}",
                  file=sys.stderr)
        try:
            store.admit_commitment(
                args.dsn, Command(request_id=f"{args.protocol_prefix}-cli-inv",
                                  payload={"investigation_id": args.investigation,
                                           "objective": "s3-abc",
                                           "scope": {}, "obligations": {}}))
        except SettlementError as exc:
            if "already exists" not in str(exc):
                raise
        from fault_tasks import BY_ID

        tasks = [BY_ID[i] for i in (dev_ids + panel_ids + transfer_ids)]
        report = experiment.run_abcs(
            args.dsn, launcher=launcher, artifacts_root=args.artifacts_root,
            allocation_id=run_allocation, investigation_id=args.investigation,
            tasks=tasks, dev_ids=dev_ids, panel_ids=panel_ids,
            transfer_ids=transfer_ids, lessons=None, gateway=adapter,
            grader_path="experiments/run_tests.py",
            protocol_prefix=args.protocol_prefix, fixer_version="fixer-v1",
            evaluator_id=args.evaluator_id,
            evaluator_version=args.evaluator_version, simulated=simulated,
            model=model)
    except SettlementError as exc:
        print(f"live A/B/C refused: {exc}")
        return 3
    print(json.dumps({"verdicts": report["verdicts"],
                      "budgets": {arm: {
                          "settled_usage_units_billed_money_only": b["settled_usage"],
                          "unresolved_exposure": b["unresolved_exposure"],
                          "token_estimates_never_a_monetary_ceiling":
                              b["token_estimates"]}
                          for arm, b in report["budgets"].items()},
                      "accounting": report["accounting"]["totals"],
                      "allocation": run_allocation,
                      "launcher": launcher.profile,
                      "development": {
                          "outcomes": {k: v["outcome"] for k, v in
                                       report["development"]["outcomes"].items()},
                          "lesson_provenance": report["development"]["lesson_provenance"],
                          "methods": report["development"]["methods"],
                          "acquisition": report["development"]["acquisition"]},
                      "simulated": report["simulated"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
