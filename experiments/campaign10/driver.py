"""Prepare and operate the frozen P10 pilot through campaign's public APIs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rsi import campaign, gate, genome, task
from settlement import store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

try:
    from .freeze import HERE, SCENARIO, freeze_document, verify_freeze
except ImportError:  # Direct script execution from this experiment directory.
    from freeze import HERE, SCENARIO, freeze_document, verify_freeze

LIVE_ROUTE_FILE = Path("D:/AI/tools/rsi-openrouter-route.env")
LIVE_CODEX = Path("C:/Users/roysh/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe")


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _read_scenario(path: Path = SCENARIO) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "p10-campaign-pilot-scenario/1":
        raise ValueError("unsupported P10 pilot scenario")
    caps = value["caps"]
    expected = {
        "max_turns": 1, "assessment_rounds": 1, "after_turn": 1,
        "model_admissions_total": 6, "action_token_ceiling": 400_000,
        "action_timeout_ms": 90_000, "root_tokens": 2_400_000,
        "root_cpu": 3_000_000, "max_wakes_per_run": 5,
        "development_wall_seconds": 120, "assessment_wall_seconds": 480,
        "total_wall_seconds": 600, "execution": "benchmark",
    }
    if caps != expected:
        raise ValueError("pilot caps changed; prepare a new prospectively frozen run")
    if value["model"] != "openrouter/openrouter/free":
        raise ValueError("pilot model must remain the approved free OpenRouter route")
    if len(value["tasks"]) != 4:
        raise ValueError("pilot needs one campaign task and three distinct epoch tasks")
    if not value["candidate_advice"].startswith(value["parent_advice"]):
        raise ValueError("candidate genome must retain the parent advice")
    suffix = value["candidate_advice"][len(value["parent_advice"]):]
    if suffix != " Before editing, list the edge cases implied by the interface and test those cases using the supplied verifier.":
        raise ValueError("candidate may add only the frozen generic advice")
    if len({item["id"] for item in value["tasks"]}) != 4:
        raise ValueError("pilot task identities must be unique")
    return value


def _task_from_spec(spec: dict) -> task.Task:
    return task.Task(
        spec["name"], spec["split"], spec["instruction"],
        {path: raw.encode("utf-8") for path, raw in spec["workspace"].items()},
        {path: raw.encode("utf-8") for path, raw in spec["tests"].items()},
        {path: raw.encode("utf-8") for path, raw in spec["reference"].items()},
        tuple(spec["tests"]),
    )


def _route(mode: str, route_file: Path | None, model: str) -> tuple[str, dict | None]:
    if mode == "fixture":
        return campaign.route_identity("http://fixture/v1"), None
    route = campaign._read_route(route_file or LIVE_ROUTE_FILE)
    if route["SETTLEMENT_GATEWAY_MODEL"] != model:
        raise ValueError("external route model differs from the frozen pilot model")
    identity = campaign.route_identity(route["SETTLEMENT_GATEWAY_ENDPOINT"])
    return identity, route


def prepare(dsn: str, campaign_id: str, run_dir: Path, *, mode: str,
            route_file: Path | None = None, scenario_path: Path = SCENARIO) -> dict:
    if not re.fullmatch(r"p10-(?:fixture|live)-[A-Za-z0-9][A-Za-z0-9._-]{0,63}", campaign_id):
        raise ValueError("campaign id must be a unique p10-fixture-* or p10-live-* identity")
    if run_dir.exists():
        raise FileExistsError("run directory already exists; resume its recorded identity")
    if mode == "fixture" and not campaign_id.startswith("p10-fixture-"):
        raise ValueError("fixture campaign id must use the p10-fixture- prefix")
    if mode == "live" and not campaign_id.startswith("p10-live-"):
        raise ValueError("live campaign id must use the p10-live- prefix")

    scenario = _read_scenario(scenario_path)
    caps = scenario["caps"]
    route_id, _route_config = _route(mode, route_file, scenario["model"])
    stage_root, artifacts_root = run_dir / "stage", run_dir / "art"
    stage_root.mkdir(parents=True)
    artifacts_root.mkdir()

    published = {}
    for spec in scenario["tasks"]:
        item = _task_from_spec(spec)
        published[spec["id"]] = {"task": item, "digest": task.publish(
            dsn, item, staging_root=stage_root, artifacts_root=artifacts_root)}
    if len({gate.anchor_identity(item["task"]) for item in published.values()}) != 4:
        raise ValueError("campaign and assessment tasks must have distinct ground-truth content")
    development = published["campaign-development"]
    epoch_tasks = tuple(published[key]["task"] for key in (
        "assessment-development", "assessment-validation", "assessment-anchor"))
    parent = genome.Genome({"AGENTS.md": scenario["parent_advice"].encode("utf-8")})
    candidate = genome.Genome({"AGENTS.md": scenario["candidate_advice"].encode("utf-8")})
    parent_digest = genome.publish(
        dsn, parent, parent=None, origin="p10-pilot-human", staging_root=stage_root,
        artifacts_root=artifacts_root)
    candidate_digest = genome.publish(
        dsn, candidate, parent=parent_digest, origin="p10-pilot-human",
        staging_root=stage_root, artifacts_root=artifacts_root)

    token_root = "p10-tokens-" + campaign_id
    cpu_root = "p10-cpu-" + campaign_id
    store.seed_allocation(dsn, Command(request_id=f"{campaign_id}:tokens", payload={
        "allocation_id": token_root, "domain": "tokens", "authorized": caps["root_tokens"],
    }))
    store.seed_allocation(dsn, Command(request_id=f"{campaign_id}:cpu", payload={
        "allocation_id": cpu_root, "domain": "cpu", "authorized": caps["root_cpu"],
    }))
    epoch = gate.freeze(
        dsn, epoch_tasks,
        gate.Budget(scenario["model"], caps["action_token_ceiling"],
                    caps["action_timeout_ms"]),
        execution=caps["execution"],
    )
    protocol = {"schema": "p10-assessment/1", "rounds": [{
        "id": "final-assessment", "after_turn": caps["after_turn"],
        "epoch": epoch, "parent": parent_digest, "candidate": candidate_digest,
        "model": scenario["model"], "route_identity": route_id,
    }]}
    assessment_task_ids = [published[key]["digest"] for key in (
        "assessment-development", "assessment-validation", "assessment-anchor")]
    grant = {
        "kind": "rsi-agenda", "agenda_id": campaign_id,
        "development_task_ids": [development["digest"]],
        "assessment_task_ids": assessment_task_ids,
        "genome_ids": [parent_digest, candidate_digest],
        "effects": ["agent-run", "sandbox-exec"],
    }
    envelopes = {
        "max_turns": caps["max_turns"],
        "tokens": {"allocation_id": token_root, "units": caps["root_tokens"]},
        "cpu": {"allocation_id": cpu_root, "units": caps["root_cpu"]},
    }
    store.seed_grant(dsn, Command(request_id=f"{campaign_id}:grant", payload={
        "version": 1, "charter_text": "Bounded P10 pilot grant", "authority_grant": grant,
        "envelopes": envelopes,
    }))
    charter = {
        "grant_version": 1,
        "objective": "Complete one development task, then run the frozen final comparison.",
        "allocations": {
            "tokens": {"id": token_root, "units": caps["root_tokens"]},
            "cpu": {"id": cpu_root, "units": caps["root_cpu"]},
        },
        "policy": "seed/1", "max_turns": caps["max_turns"],
        "deadline": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "opportunities": [{
            "id": "campaign-development", "task_id": development["digest"],
            "genome_id": parent_digest,
            "objective": "Complete the distinct campaign development task.",
            "question": "Does the parent solve the supplied development task?",
            "priority": 1,
            "resource_ceilings": {"tokens": caps["action_token_ceiling"],
                                  "cpu": caps["action_timeout_ms"]},
            "timeout_ms": caps["action_timeout_ms"], "max_steps": 1,
            "expected_observation": "A pristine development verifier result.",
            "stop_condition": "Stop after the single turn or at the declared deadline.",
        }],
    }
    identities = {
        "campaign_id": campaign_id,
        "development_task": development["digest"],
        "assessment_tasks": {key: published[key]["digest"] for key in (
            "assessment-development", "assessment-validation", "assessment-anchor")},
        "parent_genome": parent_digest, "candidate_genome": candidate_digest,
        "epoch": epoch, "grant_version": 1,
        "allocation_roots": {"tokens": token_root, "cpu": cpu_root},
        "route_identity": route_id, "model": scenario["model"],
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    _json(run_dir / "scenario.json", scenario)
    _json(run_dir / "protocol.json", protocol)
    _json(run_dir / "charter.json", charter)
    _json(run_dir / "identities.json", identities)
    frozen = freeze_document(mode=mode, protocol=protocol, identities=identities,
                             scenario_path=scenario_path)
    _json(run_dir / "freeze.json", frozen)
    started = campaign.start(dsn, campaign_id=campaign_id, charter=charter,
                             protocol=protocol, staging_root=stage_root,
                             artifacts_root=artifacts_root)
    campaign.suspend(dsn, campaign_id, started["revision"])
    return {"status": "prepared_suspended", "campaign_id": campaign_id,
            "protocol_digest": started["protocol_digest"], "identities": identities}


def _launchers(mode: str, run_dir: Path, *, route_file: Path | None,
               codex: Path | None, model: str):
    if mode == "fixture":
        command = [sys.executable, str(HERE / "fixture_worker.py")]
        provider = Provider("http://fixture/v1", model, "fixture")
    else:
        route = campaign._read_route(route_file or LIVE_ROUTE_FILE)
        if route["SETTLEMENT_GATEWAY_MODEL"] != model:
            raise ValueError("external route model differs from the frozen pilot model")
        command = [str(codex or LIVE_CODEX)]
        provider = Provider(route["SETTLEMENT_GATEWAY_ENDPOINT"], model,
                            route["SETTLEMENT_GATEWAY_KEY"])
    agent = CodexLauncher(run_dir / "runs", codex_cmd=command, provider=provider,
                          allowed_overrides=genome.HARNESS_KEYS)
    checker = LocalLauncher(run_dir / "verifiers")
    return agent, checker


def _safe_run_summary(result: dict) -> dict:
    return {
        "status": result.get("status", "unknown"),
        "revision": result.get("revision"),
        "round_id": result.get("round_id"),
        "results": [{key: item.get(key) for key in ("status", "round_id", "gate_id")
                     if key in item} for item in result.get("results", [])
                    if isinstance(item, dict)],
    }


def _pending_operation_ids(bundle: dict) -> list[str]:
    pending_states = {"prepared", "dispatching", "sent", "unresolved"}
    return [item["id"] for item in bundle.get("operations", [])
            if (item.get("payload") or {}).get("effect") == "agent-run"
            and (not item.get("settled") or item.get("dispatch_state") in pending_states)]


def _evidence_snapshot(dsn: str, campaign_id: str, run_dir: Path) -> dict:
    try:
        bundle = campaign.export(dsn, campaign_id, artifacts_root=run_dir / "art")
        recomputed = campaign.recompute(bundle)
        _json(run_dir / "bundle.json", bundle)
        _json(run_dir / "recomputed.json", recomputed)
        admissions = [item for item in bundle["operations"]
                      if (item.get("payload") or {}).get("effect") == "agent-run"]
        return {
            "evidence_status": "exported_and_recomputed",
            "durable_agent_run_admissions": len(admissions),
            "admission_operation_ids": [item["id"] for item in admissions],
            "unresolved_operations": _pending_operation_ids(bundle),
            "recomputed": recomputed,
        }
    except Exception:  # noqa: BLE001 - preserve an unavailable export as incomplete evidence.
        return {"evidence_status": "unavailable"}


def step(dsn: str, campaign_id: str, run_dir: Path, *, phase: str,
         route_file: Path | None = None, codex: Path | None = None) -> dict:
    frozen = verify_freeze(run_dir / "freeze.json")
    if frozen["identities"]["campaign_id"] != campaign_id:
        raise ValueError("campaign id differs from frozen identity")
    if frozen["mode"] == "live" and phase not in {"development", "assessment"}:
        raise ValueError("unsupported live phase")
    if phase not in {"development", "assessment"}:
        raise ValueError("phase must be development or assessment")
    result_path = run_dir / f"{phase}.json"
    started_path = run_dir / f"{phase}.started.json"
    if result_path.exists() or started_path.exists():
        raise FileExistsError("phase already started; inspect the same campaign and reconcile it")
    scenario = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    caps = scenario["caps"]
    elapsed_before = time.time() - float(frozen["prepared_at_epoch"])
    remaining = caps["total_wall_seconds"] - elapsed_before
    is_development = phase == "development"
    wall = (caps["development_wall_seconds"] if is_development
            else caps["assessment_wall_seconds"])
    minimum_admission_window = (caps["action_timeout_ms"] / 1000
                                if is_development else
                                caps["action_timeout_ms"] * 5 / 1000)
    if remaining < minimum_admission_window:
        body = {"label": frozen["mode"], "phase": phase, "status": "incomplete",
                "unfinished_campaigns": [campaign_id], "score": None,
                "reason": "remaining total wall bound cannot cover the frozen action window"}
        body.update(_evidence_snapshot(dsn, campaign_id, run_dir))
        _json(result_path, body)
        return body
    wall = min(wall, remaining)
    started_at = time.time()
    _json(started_path, {"phase": phase, "started_at_epoch": started_at})
    inspection = campaign.inspect(dsn, campaign_id)
    if inspection is None or inspection["status"] != "suspended":
        body = {"label": frozen["mode"], "phase": phase, "status": "incomplete",
                "unfinished_campaigns": [campaign_id], "score": None,
                "reason": "campaign was not suspended"}
        body.update(_evidence_snapshot(dsn, campaign_id, run_dir))
        _json(result_path, body)
        return json.loads(result_path.read_text(encoding="utf-8"))
    try:
        campaign.resume(dsn, campaign_id, inspection["revision"])
        agent, checker = _launchers(frozen["mode"], run_dir, route_file=route_file,
                                    codex=codex, model=scenario["model"])
        run_result = campaign.run(
            dsn, agent, checker, campaign_id,
            staging_root=run_dir / "stage", artifacts_root=run_dir / "art",
            max_wakes=(1 if is_development else scenario["caps"]["max_wakes_per_run"]),
            wall_seconds=wall,
        )
    except Exception:  # noqa: BLE001 - campaign/provider failures remain incomplete, never scores.
        body = {"label": frozen["mode"], "phase": phase, "status": "incomplete",
                "unfinished_campaigns": [campaign_id], "score": None,
                "reason": "campaign call ended without a classifiable result"}
        body.update(_evidence_snapshot(dsn, campaign_id, run_dir))
        _json(result_path, body)
        return body

    body = {"label": frozen["mode"], "phase": phase,
            "status": run_result.get("status", "unknown"),
            "run": _safe_run_summary(run_result),
            "unfinished_campaigns": ([campaign_id] if run_result.get("status") in
                                     {"pending", "unscored", "deadline", "blocked", "unknown"}
                                     else []),
            "score": None}
    if is_development:
        current = campaign.inspect(dsn, campaign_id)
        if current and current["status"] in {"active", "complete"}:
            campaign.suspend(dsn, campaign_id, current["revision"])
            body["unfinished_campaigns"] = [campaign_id]
            if run_result.get("status") == "bound" and not current["flight_pending"]:
                body["status"] = "development_complete_suspended"
            else:
                body["status"] = "incomplete"
                body["reason"] = "development did not complete a bounded turn"
        else:
            body["unfinished_campaigns"] = [campaign_id]
            body["status"] = "incomplete"
        # Development can be incomplete too; preserve the durable campaign evidence.
        body.update(_evidence_snapshot(dsn, campaign_id, run_dir))
    else:
        evidence = _evidence_snapshot(dsn, campaign_id, run_dir)
        body.update(evidence)
        if evidence["evidence_status"] == "unavailable":
            body["status"] = "incomplete"
            body["unfinished_campaigns"] = [campaign_id]
            body["reason"] = "campaign export or recompute did not complete"
        else:
            if run_result.get("status") in {"pending", "unscored", "deadline", "blocked", "unknown"}:
                body["unfinished_campaigns"] = [campaign_id]
            if body["unresolved_operations"] and not body["unfinished_campaigns"]:
                body["unfinished_campaigns"] = [campaign_id]
            if body["durable_agent_run_admissions"] > scenario["caps"]["model_admissions_total"]:
                body["status"] = "incomplete"
                body["unfinished_campaigns"] = [campaign_id]
                body["reason"] = "durable admission count exceeded the frozen cap"
    body["elapsed_seconds"] = round(time.time() - started_at, 3)
    _json(result_path, body)
    return body


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "development", "assessment"))
    parser.add_argument("--mode", choices=("fixture", "live"), default="live")
    parser.add_argument("--id", required=True)
    parser.add_argument("--dsn", default=os.environ.get("S09ISO_ADMIN_DSN"))
    parser.add_argument("--route-file", type=Path, default=LIVE_ROUTE_FILE)
    parser.add_argument("--codex", type=Path, default=LIVE_CODEX)
    parser.add_argument("--evidence-root", type=Path, default=HERE / "evidence")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.dsn:
        raise SystemExit("S09ISO_ADMIN_DSN must name the isolated campaign database")
    run_dir = args.evidence_root / args.id
    try:
        if args.command == "prepare":
            result = prepare(args.dsn, args.id, run_dir, mode=args.mode,
                             route_file=args.route_file)
        else:
            result = step(args.dsn, args.id, run_dir, phase=args.command,
                          route_file=args.route_file, codex=args.codex)
    except Exception as exc:  # noqa: BLE001 - sanitize possibly credential-bearing failure text.
        print(json.dumps({"status": "incomplete", "error_type": type(exc).__name__,
                          "campaign_id": args.id}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
