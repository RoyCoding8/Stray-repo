"""Persistent task investigations over the existing episode and verifier paths."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

from . import episode, experience, investigation, memory, verifier
from . import genome as genomes
from . import task as tasks
from .investigation import export, read

__all__ = ["create", "export", "read", "run", "step"]

QUESTION = "Does the solution satisfy the task obligation?"
POLICY = {"id": "task-seed/1"}
MEMORY_DEFAULT = {"scope": {"domain": "task"}, "view": "structured", "limit": 10}
MEMORY_VIEWS = {"structured", "raw-history"}


def _require(result):
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return result


def _memory_options(value):
    if value is None:
        return dict(MEMORY_DEFAULT)
    if not isinstance(value, dict) or set(value) - {"scope", "view", "limit"}:
        raise SettlementError("memory must contain only scope, view, and limit")
    scope = value.get("scope", MEMORY_DEFAULT["scope"])
    view = value.get("view", MEMORY_DEFAULT["view"])
    limit = value.get("limit", MEMORY_DEFAULT["limit"])
    if not isinstance(scope, dict):
        raise SettlementError("memory scope must be an object")
    if not isinstance(view, str) or view not in MEMORY_VIEWS:
        raise SettlementError("memory view must be structured or raw-history")
    if type(limit) is not int or limit <= 0:
        raise SettlementError("memory limit must be a positive integer")
    try:
        scope = json.loads(json.dumps(scope, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise SettlementError(f"memory scope must be JSON data: {exc}") from exc
    return {"scope": scope, "view": view, "limit": limit}


def _memory_snapshot(dsn, investigation_id, state, options, artifacts_root):
    purpose = f"task: {state['objective']}"
    result = memory.query(
        dsn, purpose=purpose, investigation_id=investigation_id,
        scope=options["scope"], artifacts_root=artifacts_root,
        visibility="learner", view=options["view"], limit=options["limit"])
    fields = ("revision", "purpose", "scope", "view", "claims",
              "observations", "missing_information")
    if not isinstance(result, dict) or any(field not in result for field in fields):
        raise SettlementError("memory query returned an incomplete snapshot")
    if (type(result["revision"]) is not int
            or not isinstance(result["claims"], list)
            or not isinstance(result["observations"], list)
            or not isinstance(result["missing_information"], list)):
        raise SettlementError("memory query returned a malformed snapshot")
    return {field: result[field] for field in fields}


def _revalidate_memory(dsn, snapshot, artifacts_root):
    if snapshot is None:
        return
    if not isinstance(snapshot, dict):
        raise SettlementError("pending decision has no pinned memory snapshot")
    observations = snapshot.get("observations")
    if not isinstance(observations, list):
        raise SettlementError("pinned memory observations are malformed")
    ids = [item.get("observation_id") for item in observations
           if isinstance(item, dict)]
    if len(ids) != len(observations) or any(type(item) is not int for item in ids):
        raise SettlementError("pinned memory observation identity is missing")
    if len(set(ids)) != len(ids):
        raise SettlementError("pinned memory snapshot repeats an observation")
    if snapshot.get("missing_information"):
        raise SettlementError("pinned memory snapshot has missing evidence")
    resolved = experience.resolve(
        dsn, ids, artifacts_root=artifacts_root,
        revision=snapshot.get("revision"), visibility="learner")
    if not isinstance(resolved, dict):
        raise SettlementError("memory resolution returned a malformed result")
    if resolved.get("revision") != snapshot.get("revision"):
        raise SettlementError("pinned memory revision could not be reproduced")
    if resolved.get("missing_information"):
        raise SettlementError("pinned memory evidence is unavailable")
    current = resolved.get("observations")
    if not isinstance(current, list):
        raise SettlementError("memory resolution returned malformed observations")
    if any(not isinstance(item, dict) or type(item.get("observation_id")) is not int
           for item in current):
        raise SettlementError("memory resolution returned malformed observation identities")
    by_id = {item.get("observation_id"): item
             for item in current if isinstance(item, dict)}
    if set(by_id) != set(ids) or len(by_id) != len(current):
        raise SettlementError("pinned memory evidence is unavailable")
    original = {item["observation_id"]: item for item in observations}
    if by_id != original:
        raise SettlementError("pinned memory evidence changed after query")


def create(dsn, agent, genome, *, investigation_id, task, token_allocation,
           cpu_allocation, max_steps, timeout_ms, token_ceiling,
           staging_root, artifacts_root, objective=None, memory=None):
    """Pin one development objective and its finite execution envelope."""
    for name, value in (("max_steps", max_steps), ("timeout_ms", timeout_ms),
                        ("token_ceiling", token_ceiling)):
        if type(value) is not int or value <= 0:
            raise SettlementError(f"{name} must be a positive integer")
    task = tasks.load(dsn, artifacts_root, task.digest)
    if task.split != "dev":
        raise SettlementError("continuing task investigations accept development tasks only")
    genomes.load(dsn, artifacts_root, genome.digest)
    memory_options = _memory_options(memory)
    config = {"task": task.digest, "genome": genome.digest,
              "token_allocation": token_allocation, "cpu_allocation": cpu_allocation,
              "max_steps": max_steps, "timeout_ms": timeout_ms,
              "memory": memory_options,
              "token_ceiling": token_ceiling, "model": agent.provider.model}
    payload = {"investigation_id": investigation_id, "objective": objective or task.instruction,
               "domain": "task", "allocation_id": token_allocation, "config": config,
               "policy": POLICY, "open_questions": [QUESTION], "artifact_refs": {}}
    _require(investigation.create(dsn, Command(
        request_id="p01-create:" + investigation_id, payload=payload)))
    return investigation.read(dsn, investigation_id)


def step(dsn, agent, checker, investigation_id, *, staging_root, artifacts_root):
    """Finish a pending action or admit and perform at most one new worker action."""
    state = investigation.read(dsn, investigation_id)
    if state is None:
        raise SettlementError("unknown investigation " + investigation_id)
    if state["domain"] != "task" or state["policy"] != POLICY:
        raise SettlementError("unsupported investigation domain or seed policy")
    config = state["config"]
    memory_options = _memory_options(config.get("memory"))
    pending = state["pending_decision"]
    experience.capture_investigation(
        dsn, investigation_id, artifacts_root=artifacts_root)
    if state["status"] in ("suspended", "completed", "unresolved"):
        return state
    if config["model"] != agent.provider.model:
        raise SettlementError("worker model differs from investigation configuration")
    item = tasks.load(dsn, artifacts_root, config["task"])
    current = genomes.load(dsn, artifacts_root, config["genome"])
    if pending is None:
        identity = hashlib.sha256(f"{investigation_id}:{state['revision']}".encode()).hexdigest()
        visible = {"objective": state["objective"],
                   "objective_revision": state["objective_revision"],
                   "state_revision": state["revision"],
                   "open_questions": state["open_questions"],
                   "artifact_refs": state["artifact_refs"],
                   "previous_observation": state["last_observation"],
                   "memory": _memory_snapshot(
                       dsn, investigation_id, state, memory_options, artifacts_root)}
        _require(investigation.decide(dsn, Command(
            request_id="p01-decide:" + identity, expected_revision=state["revision"],
            payload={"investigation_id": investigation_id,
                     "decision_id": "p01-decision-" + identity,
                     "attempt_id": "p01-attempt-" + identity,
                     "operation_id": "p01-worker-" + identity,
                     "action": {"kind": "worker",
                                "explanation": "Attempt the open obligation using checked feedback.",
                                "intended_observation": QUESTION},
                     "visible_input": visible})))
        state = investigation.read(dsn, investigation_id)
        pending = state["pending_decision"]
    roots = {"staging_root": staging_root, "artifacts_root": artifacts_root}
    visible = pending["visible_input"]
    _revalidate_memory(dsn, visible.get("memory"), artifacts_root)
    try:
        ep = episode.run_episode(
            dsn, agent, current, operation_id=pending["operation_id"], task=item,
            allocation_id=config["token_allocation"], attempt_id=pending["attempt_id"],
            timeout_ms=config["timeout_ms"], token_ceiling=config["token_ceiling"],
            continuation=visible, solution=visible["artifact_refs"].get("solution"), **roots)
        observation = {"episode": ep.operation_id, "status": ep.status,
                       "passed": None, "verdict": None, "solution": None,
                       "reason": ep.infra_reason}
        if ep.status == "completed":
            checked = verifier.verify_episode(
                dsn, agent, checker, ep.operation_id,
                allocation_id=config["cpu_allocation"], attempt_id=pending["attempt_id"], **roots)
            observation.update(status=checked.status, passed=checked.passed,
                               verdict=checked.operation_id, solution=checked.solution)
    except SettlementError as exc:
        state = investigation.read(dsn, investigation_id)
        if state["pending_decision"] == pending:
            investigation.observe(dsn, Command(
                expected_revision=state["revision"],
                payload={"investigation_id": investigation_id, "decision_id": pending["id"],
                         "operation_id": pending["operation_id"], "outcome": "unresolved",
                         "observation": {"episode": pending["operation_id"],
                                         "status": "refused", "passed": None,
                                         "verdict": None, "solution": None}}))
            state = investigation.read(dsn, investigation_id)
        return {**state, "execution_error": str(exc)}
    history = investigation.export(dsn, investigation_id)
    spent = len(history["decisions"])
    outcome = ("completed" if observation["passed"] is True else
               "ready" if observation["passed"] is False and spent < config["max_steps"] else
               "unresolved")
    refs = {"trajectory": ep.trajectory}
    if observation["solution"]:
        refs["solution"] = observation["solution"]
    _require(investigation.observe(dsn, Command(
        request_id="p01-observe:" + pending["id"], expected_revision=state["revision"],
        payload={"investigation_id": investigation_id, "decision_id": pending["id"],
                 "operation_id": pending["operation_id"], "observation": observation,
                 "outcome": outcome, "artifact_refs": refs,
                 "open_questions": [] if outcome == "completed" else [QUESTION]})))
    experience.capture_investigation(
        dsn, investigation_id, artifacts_root=artifacts_root)
    return investigation.read(dsn, investigation_id)


def run(dsn, agent, checker, investigation_id, *, staging_root, artifacts_root):
    """Run the finite envelope; stop at suspension, terminal outcome or pending uncertainty."""
    while True:
        before = investigation.read(dsn, investigation_id)
        after = step(dsn, agent, checker, investigation_id,
                     staging_root=staging_root, artifacts_root=artifacts_root)
        if (after["status"] != "ready" or after["revision"] == before["revision"]):
            return after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "inspect", "step", "resume", "suspend", "export"))
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--route-file", type=Path)
    parser.add_argument("--codex")
    parser.add_argument("--catalog-template", default=Provider.catalog_template)
    parser.add_argument("--genome")
    parser.add_argument("--task")
    parser.add_argument("--objective")
    parser.add_argument("--token-allocation")
    parser.add_argument("--cpu-allocation")
    parser.add_argument("--max-steps", type=int, default=2)
    parser.add_argument("--timeout-ms", type=int, default=180000)
    parser.add_argument("--token-ceiling", type=int, default=150000)
    args = parser.parse_args()
    roots = {"staging_root": args.root / "stage", "artifacts_root": args.root / "art"}
    if args.command in ("inspect", "export"):
        result = (investigation.read if args.command == "inspect" else investigation.export)(
            args.dsn, args.id)
        if result is None:
            parser.error("unknown investigation " + args.id)
    elif args.command == "suspend":
        state = investigation.read(args.dsn, args.id)
        if state is None:
            parser.error("unknown investigation " + args.id)
        _require(investigation.suspend(args.dsn, Command(
            expected_revision=state["revision"], payload={"investigation_id": args.id})))
        result = investigation.read(args.dsn, args.id)
    else:
        if not args.route_file or not args.codex:
            parser.error("create, step and resume require --route-file and --codex")
        route = dict(line.split("=", 1) for line in args.route_file.read_text().splitlines()
                     if line and not line.startswith("#"))
        agent = CodexLauncher(args.root / "runs", codex_cmd=[args.codex],
                              provider=Provider(route["SETTLEMENT_GATEWAY_ENDPOINT"],
                                                route["SETTLEMENT_GATEWAY_MODEL"],
                                                route["SETTLEMENT_GATEWAY_KEY"],
                                                catalog_template=args.catalog_template),
                              allowed_overrides=genomes.HARNESS_KEYS)
        checker = LocalLauncher(args.root / "verifiers")
        if args.command == "create":
            if not all((args.genome, args.task, args.token_allocation, args.cpu_allocation)):
                parser.error("create requires genome, task and token/cpu allocation identities")
            result = create(
                args.dsn, agent, genomes.load(args.dsn, roots["artifacts_root"], args.genome),
                investigation_id=args.id, task=tasks.load(args.dsn, roots["artifacts_root"], args.task),
                token_allocation=args.token_allocation, cpu_allocation=args.cpu_allocation,
                max_steps=args.max_steps, timeout_ms=args.timeout_ms,
                token_ceiling=args.token_ceiling, objective=args.objective, **roots)
        else:
            if args.command == "resume":
                state = investigation.read(args.dsn, args.id)
                if state is None:
                    parser.error("unknown investigation " + args.id)
                if state["status"] == "suspended":
                    _require(investigation.resume(args.dsn, Command(
                        expected_revision=state["revision"], payload={"investigation_id": args.id})))
            execute = step if args.command == "step" else run
            result = execute(args.dsn, agent, checker, args.id, **roots)
    print(json.dumps(result, indent=2, default=str))
    if args.command in ("step", "resume") and result["status"] in ("pending", "unresolved"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
