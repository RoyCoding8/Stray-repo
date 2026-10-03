"""Acquired-behavior end-to-end experiment (E2E-3/E2E-4).

Orchestrates campaign.run_campaign, which freezes the retention record
(rpr-retention/1), then a retained-mode panel run on a fresh evidence
root, then the checker decision, then the disposition-bound use step.
The frozen retention file is the single source of truth between phases:
every later phase reloads retention, campaign record and disposition
from disk through retention.load_retention, so a fresh process finishes
evaluation, disposition or use without in-memory state and without
touching the gateway. Blocked acquisition stops honestly with the
highest phase actually completed; empty retention still runs evaluation
with recorded fallbacks and never forces a positive.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import campaign, panel, retention
from experiments.representation.acquire import run as panel_run
from experiments.representation.experiment import checker
from settlement import launcher_local
from settlement.common import SettlementError

PHASES = ("acquisition", "evaluation", "disposition", "use")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path) -> dict:
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError):
        raise SettlementError("experiment input %s unreadable" % path)


def decide_disposition(dsn: str, eval_root) -> tuple:
    manifest, sha, pending = checker.load_manifest()
    problems = list(pending)
    if manifest is None:
        disposition = {"panel_version": panel.PANEL_VERSION,
                       "manifest_sha256": sha, "records": 0, "controls": {},
                       "promising": False, "release_eligible": False,
                       "release_note": "no manifest: nothing certifiable",
                       "use_authorized": False,
                       "use_authorization_reason": "no manifest",
                       "reasons": ["missing-manifest"], "problems": problems}
    else:
        records, more = checker.check_evidence(Path(eval_root), manifest,
                                               sha)
        problems.extend(more)
        checker.check_barrier(records, manifest, problems)
        controls = checker.check_controls(Path(eval_root), problems)
        rule = checker.pilot_rule(records, controls)
        if dsn:
            try:
                checker.cross_check_db(dsn, Path(eval_root), records,
                                       problems)
            except Exception as exc:
                problems.append("db-cross-check-failed %s" % exc)
        disposition = {"panel_version": panel.PANEL_VERSION,
                       "manifest_sha256": sha, "records": len(records),
                       "controls": controls, "means": rule["means"],
                       "clauses": rule["clauses"],
                       "resources": rule["resources"],
                       "efficiency": rule["efficiency"],
                       "reasons": rule["reasons"],
                       "promising": rule["promising"],
                       "release_eligible": False,
                       "release_note": rule["release_note"],
                       "use_authorized": False,
                       "use_authorization_reason": "a pilot never"
                       " authorizes general use",
                       "problems": problems}
    target = Path(eval_root) / "disposition.json"
    raw = (json.dumps(disposition, sort_keys=True, indent=2) + "\n").encode()
    target.write_bytes(raw)
    return disposition, _digest(raw)


def run_use_phase(dsn: str, *, tag: str, artifacts_root, staging_root,
                  runs_root, eval_root) -> dict:
    evidence_root = Path(eval_root).parent
    retention_path = evidence_root / "campaign" / ("retention-%s.json" % tag)
    retained = retention.load_retention(str(retention_path), dsn,
                                        artifacts_root)
    campaign_record = _read_json(evidence_root / "campaign" / ("%s.json"
                                                               % tag))
    if campaign_record.get("tag") != tag:
        raise SettlementError("campaign record tag disagrees")
    index = _read_json(Path(eval_root) / "index.json")
    if index.get("tag") != tag:
        raise SettlementError("evaluation index tag disagrees")
    disposition = _read_json(Path(eval_root) / "disposition.json")
    disp_digest = _digest((Path(eval_root) / "disposition.json")
                          .read_bytes())
    base = panel_run.ensure_foundation(dsn, tag)
    launcher = launcher_local.LocalLauncher(str(runs_root))
    ctx = {**base, "tag": tag, "run_tag": "%s-ret" % tag,
           "launcher": launcher, "artifacts_root": Path(artifacts_root),
           "staging_root": Path(staging_root),
           "evidence_root": Path(eval_root), "retention": retained,
           "retention_digest": _digest(retention_path.read_bytes()),
           "retention_path": str(retention_path),
           "disposition": disposition, "disposition_digest": disp_digest}
    panel_run.bind_retention(dsn, ctx)
    routes = {}
    for task_id in panel.USE:
        result = panel_run.run_use_task(dsn, ctx, task_id)
        routes[task_id] = result["record"]["selected"]["route"]
    return routes


def _write_status(evidence_root, status: dict):
    target = Path(evidence_root) / ("experiment-%s.json" % status["tag"])
    target.write_bytes((json.dumps(status, sort_keys=True, indent=2)
                        + "\n").encode())
    return target


def run_experiment(dsn: str, *, gateway, model: str, grant_units: int,
                   tag: str, artifacts_root, staging_root, runs_root,
                   evidence_root,
                   phases=("acquisition", "evaluation", "disposition",
                           "use")) -> dict:
    for phase in phases:
        if phase not in PHASES:
            raise SettlementError("unknown phase %r" % (phase,))
    wanted = [phase for phase in PHASES if phase in phases]
    status: dict = {"tag": tag, "model": model,
                    "phases_requested": list(phases),
                    "phases_completed": [], "phase_completed": "none",
                    "acquired": None, "retention_path": None,
                    "retention_digest": None}
    evidence_root = Path(evidence_root)
    if "acquisition" in wanted:
        if gateway is None:
            raise SettlementError("acquisition needs a gateway")
        record = campaign.run_campaign(
            dsn, tag=tag, model=model, grant_units=grant_units,
            gateway=gateway, artifacts_root=Path(artifacts_root),
            staging_root=Path(staging_root), runs_root=Path(runs_root),
            evidence_root=evidence_root)
        status["acquisition"] = {
            "blocked": record["blocked"],
            "reason": record.get("reason", ""),
            "acquired": record.get("acquired", False),
            "spent": record.get("spent", {})}
        if record["blocked"]:
            _write_status(evidence_root, status)
            return status
        rpath = evidence_root / record["retention_path"]
        rdigest = _digest(rpath.read_bytes())
        status["acquisition"]["campaign_record"] = str(
            evidence_root / "campaign" / ("%s.json" % tag))
        status["acquired"] = record["acquired"]
        status["retention_path"] = str(rpath)
        status["retention_digest"] = rdigest
        status["phases_completed"].append("acquisition")
        status["phase_completed"] = "acquisition"
    eval_root = evidence_root / ("eval-%s" % tag)
    if "evaluation" in wanted:
        rpath = status["retention_path"] or str(
            evidence_root / "campaign" / ("retention-%s.json" % tag))
        index = panel_run.run_panel(
            dsn, tag=tag, artifacts_root=Path(artifacts_root),
            staging_root=Path(staging_root), runs_root=Path(runs_root),
            evidence_root=eval_root, mode="retained",
            retention_path=rpath)
        if status["retention_path"] is None:
            status["retention_path"] = rpath
            status["retention_digest"] = _digest(
                Path(rpath).read_bytes())
        status["evaluation"] = {
            "evidence_root": str(eval_root),
            "arm_task_records": index["arm_task_records"],
            "control_records": index["control_records"],
            "means": index["means"]}
        status["phases_completed"].append("evaluation")
        status["phase_completed"] = "evaluation"
    if "disposition" in wanted:
        disposition, disp_digest = decide_disposition(dsn, eval_root)
        status["disposition"] = {
            "promising": disposition["promising"],
            "release_eligible": disposition["release_eligible"],
            "release_note": disposition["release_note"],
            "use_authorized": disposition["use_authorized"],
            "reasons": disposition["reasons"],
            "problems": disposition["problems"],
            "digest": disp_digest}
        status["phases_completed"].append("disposition")
        status["phase_completed"] = "disposition"
    if "use" in wanted:
        routes = run_use_phase(dsn, tag=tag, artifacts_root=artifacts_root,
                               staging_root=staging_root,
                               runs_root=runs_root, eval_root=eval_root)
        status["use"] = {"routes": routes, "records": len(routes)}
        status["phases_completed"].append("use")
        status["phase_completed"] = "use"
        status["final_check"] = checker.check_all(eval_root, dsn=dsn)
    _write_status(evidence_root, status)
    return status


def main(argv) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="RPR end-to-end experiment")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--tag", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--grant-units", default="")
    parser.add_argument("--artifacts-root", default="")
    parser.add_argument("--staging-root", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--evidence-root", default="")
    parser.add_argument("--phases", default=",".join(PHASES))
    args = parser.parse_args(argv)
    dsn = args.dsn or os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn or not args.tag or not args.evidence_root:
        print("need --dsn (or SETTLEMENT_TEST_DSN), --tag, --evidence-root")
        return 2
    phases = tuple(part for part in args.phases.split(",") if part)
    if "acquisition" in phases:
        print("acquisition needs a gateway: call run_experiment")
        return 2
    try:
        status = run_experiment(
            dsn, gateway=None, model=args.model,
            grant_units=int(args.grant_units or 0), tag=args.tag,
            artifacts_root=args.artifacts_root,
            staging_root=args.staging_root, runs_root=args.runs_root,
            evidence_root=args.evidence_root, phases=phases)
    except SettlementError as exc:
        print(json.dumps({"tag": args.tag, "error": str(exc)}))
        return 1
    print(json.dumps(status, sort_keys=True, indent=2))
    return 0 if _evidence_clean(status) else 1


def _evidence_clean(status: dict) -> bool:
    """Whether the evidence root is free of checker problems.

    `decide_disposition` accumulates manifest drift, evidence gaps, a
    failed barrier, controls that did not pass and a cross-check that
    blew up into `problems`, and the checker's own CLI exits 1 on that
    list. `promising`, `release_eligible` and `use_authorized` are
    findings and policy constants, not faults, so they are not read
    here. A run that asked for no disposition holds no verdict.
    """
    disposition = status.get("disposition")
    if disposition is not None and disposition.get("problems"):
        return False
    final = status.get("final_check")
    if final is not None and not final.get("clean"):
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
