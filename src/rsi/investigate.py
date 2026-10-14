"""Persistent task investigations over the existing episode and verifier paths."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

from . import context, episode, experience, investigation, memory, verifier
from . import genome as genomes
from . import task as tasks
from .investigation import export, read

__all__ = ["create", "export", "read", "run", "step"]

QUESTION = "Does the solution satisfy the task obligation?"
POLICY = {"id": "task-seed/1"}
MEMORY_DEFAULT = {"scope": {"domain": "task"}, "view": "structured", "limit": 10}


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
    if not isinstance(view, str) or view not in memory.VIEWS:
        raise SettlementError("memory view must be structured or raw-history")
    if type(limit) is not int or limit <= 0:
        raise SettlementError("memory limit must be a positive integer")
    try:
        scope = json.loads(json.dumps(scope, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise SettlementError(f"memory scope must be JSON data: {exc}") from exc
    return {"scope": scope, "view": view, "limit": limit}


def _context_options(value, memory_value, *, stored=False):
    memory_options = _memory_options(memory_value)
    if value is None:
        options = {
            "policy": ("raw-history/1" if memory_options["view"] == "raw-history"
                       else "structured/1"),
            "scope": memory_options["scope"],
            "limit": memory_options["limit"],
            "budget": dict(context.DEFAULT_BUDGET),
            "required_observation_ids": [],
            "required_claim_ids": [],
        }
    else:
        allowed = {"policy", "budget", "required_observation_ids", "required_claim_ids"}
        if stored:
            allowed |= {"scope", "limit"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise SettlementError("context must contain only policy, budget, and required evidence ids")
        options = {
            "policy": value.get("policy", "structured/1"),
            "scope": value.get("scope", memory_options["scope"]),
            "limit": value.get("limit", memory_options["limit"]),
            "budget": value.get("budget", dict(context.DEFAULT_BUDGET)),
            "required_observation_ids": value.get("required_observation_ids", []),
            "required_claim_ids": value.get("required_claim_ids", []),
        }
        if not stored:
            try:
                options["budget"] = json.loads(json.dumps(
                    options["budget"], sort_keys=True, allow_nan=False))
            except (TypeError, ValueError) as exc:
                raise SettlementError(f"context budget must be JSON data: {exc}") from exc
    if not isinstance(options["policy"], str) or options["policy"] not in context.POLICIES:
        raise SettlementError("context policy is unsupported")
    if not isinstance(options["scope"], dict):
        raise SettlementError("context scope must be an object")
    if (type(options["limit"]) is not int or options["limit"] <= 0
            or options["limit"] > context.MAX_LIMIT):
        raise SettlementError(
            f"context limit must be between 1 and {context.MAX_LIMIT}")
    if not isinstance(options["budget"], dict):
        raise SettlementError("context budget must be an object")
    if set(options["budget"]) - set(context.DEFAULT_BUDGET):
        raise SettlementError("context budget contains unsupported fields")
    for field, default in context.DEFAULT_BUDGET.items():
        number = options["budget"].get(field, default)
        if type(number) is not int or number <= 0:
            raise SettlementError(f"context budget {field} must be a positive integer")
        if field == "packet_bytes" and number > context.MAX_PACKET_BYTES:
            raise SettlementError(
                f"context budget packet_bytes cannot exceed {context.MAX_PACKET_BYTES}")
        options["budget"][field] = number
    for field, identity_type in (("required_observation_ids", int),
                                 ("required_claim_ids", str)):
        values = options[field]
        if (not isinstance(values, list)
                or any(type(item) is not identity_type for item in values)
                or (field == "required_observation_ids"
                    and any(item <= 0 for item in values))
                or (field == "required_claim_ids"
                    and any(not item.strip() for item in values))
                or len(set(values)) != len(values)):
            raise SettlementError(f"context {field} must be a unique list of {identity_type.__name__} values")
    return options


def _context_validation(dsn, visible, artifacts_root):
    if "context_packet" in visible:
        packet = visible["context_packet"]
        if not isinstance(packet, dict):
            return {"status": "stale", "reason": "pending context packet is malformed"}
        return context.validate(dsn, packet, artifacts_root=artifacts_root)
    snapshot = visible.get("memory")
    if snapshot is not None:
        return context.validate(
            dsn, {"schema": "p02-legacy", "memory_view": snapshot},
            artifacts_root=artifacts_root)
    return {"status": "ready", "reason": "legacy decision has no memory snapshot"}


def _context_request(investigation_id, objective_revision, state_revision,
                     decision_id, attempt_id, operation_id, objective,
                     continuation, options):
    return {
        "investigation_id": investigation_id,
        "objective_revision": objective_revision,
        "state_revision": state_revision,
        "decision_id": decision_id,
        "attempt_id": attempt_id,
        "operation_id": operation_id,
        "continuation": continuation,
        "purpose": f"task: {objective}",
        "scope": options["scope"],
        "policy": options["policy"],
        "limit": options["limit"],
        "required_observation_ids": options["required_observation_ids"],
        "required_claim_ids": options["required_claim_ids"],
        "budget": options["budget"],
    }


def _continuation_fields(visible):
    fields = ("objective", "objective_revision", "state_revision",
              "open_questions", "artifact_refs", "previous_observation")
    return {field: visible[field] for field in fields}


def _packet_matches(packet, request):
    return isinstance(packet, dict) and packet.get("request") == request


def create(dsn, agent, genome, *, investigation_id, task, token_allocation,
           cpu_allocation, max_steps, timeout_ms, token_ceiling,
           staging_root, artifacts_root, objective=None, memory=None, context=None):
    """Pin one development objective and its finite execution envelope."""
    for name, value in (("max_steps", max_steps), ("timeout_ms", timeout_ms),
                        ("token_ceiling", token_ceiling)):
        if type(value) is not int or value <= 0:
            raise SettlementError(f"{name} must be a positive integer")
    task = tasks.load(dsn, artifacts_root, task.digest)
    if task.split != "dev":
        raise SettlementError("continuing task investigations accept development tasks only")
    genomes.load(dsn, artifacts_root, genome.digest)
    context_options = _context_options(context, memory)
    config = {"task": task.digest, "genome": genome.digest,
              "token_allocation": token_allocation, "cpu_allocation": cpu_allocation,
              "max_steps": max_steps, "timeout_ms": timeout_ms,
              "context": context_options,
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
        decision_id = "p01-decision-" + identity
        attempt_id = "p01-attempt-" + identity
        operation_id = "p01-worker-" + identity
        continuation = {
            "objective": state["objective"],
            "objective_revision": state["objective_revision"],
            "state_revision": state["revision"],
            "open_questions": state["open_questions"],
            "artifact_refs": state["artifact_refs"],
            "previous_observation": state["last_observation"],
        }
        options = _context_options(config.get("context"), config.get("memory"), stored=True)
        request = _context_request(
            investigation_id, state["objective_revision"], state["revision"],
            decision_id, attempt_id, operation_id, state["objective"],
            continuation, options)
        packet = context.build(dsn, request, artifacts_root=artifacts_root)
        if packet.get("status") != "ready":
            return {
                **state,
                "context_outcome": {
                    "status": "needs_information",
                    "request_id": identity,
                    "packet": packet,
                    "needs": packet.get("needs", []),
                },
            }
        if not _packet_matches(packet, request):
            return {
                **state,
                "context_outcome": {
                    "status": "stale",
                    "request_id": identity,
                    "reason": "context packet is not pinned to this decision request",
                },
            }
        validation = context.validate(dsn, packet, artifacts_root=artifacts_root)
        if validation.get("status") != "ready":
            return {
                **state,
                "context_outcome": {
                    "status": validation.get("status"),
                    "request_id": identity,
                    "packet": packet,
                    "reason": validation.get("reason"),
                },
            }
        visible = {**continuation, "context_packet": packet}
        _require(investigation.decide(dsn, Command(
            request_id="p01-decide:" + identity, expected_revision=state["revision"],
            payload={"investigation_id": investigation_id,
                     "decision_id": decision_id,
                     "attempt_id": attempt_id,
                     "operation_id": operation_id,
                     "action": {"kind": "worker",
                                "explanation": "Attempt the open obligation using checked feedback.",
                                "intended_observation": QUESTION},
                     "visible_input": visible})))
        state = investigation.read(dsn, investigation_id)
        pending = state["pending_decision"]
    roots = {"staging_root": staging_root, "artifacts_root": artifacts_root}
    visible = pending["visible_input"]
    if "context_packet" in visible:
        options = _context_options(config.get("context"), config.get("memory"), stored=True)
        try:
            request = _context_request(
                investigation_id, visible["objective_revision"], visible["state_revision"],
                pending["id"], pending["attempt_id"], pending["operation_id"],
                visible["objective"], _continuation_fields(visible), options)
        except KeyError:
            validation = {
                "status": "stale",
                "reason": "pending context continuation is incomplete",
            }
        else:
            if not _packet_matches(visible["context_packet"], request):
                validation = {
                    "status": "stale",
                    "reason": "context packet is not pinned to the admitted decision",
                }
            else:
                validation = _context_validation(dsn, visible, artifacts_root)
    elif config.get("context") is not None:
        validation = {
            "status": "stale",
            "reason": "P03 decision is missing its context packet",
        }
    else:
        validation = _context_validation(dsn, visible, artifacts_root)
    if validation.get("status") != "ready":
        return {
            **state,
            "context_outcome": {
                "status": validation.get("status"),
                "decision_id": pending["id"],
                "attempt_id": pending["attempt_id"],
                "operation_id": pending["operation_id"],
                "reason": validation.get("reason"),
            },
        }
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
        experience.capture_investigation(
            dsn, investigation_id, artifacts_root=artifacts_root)
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
    parser.add_argument("--context-policy", choices=tuple(sorted(context.POLICIES)))
    parser.add_argument("--context-budget-bytes", type=int)
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
            context_options = None
            if args.context_policy is not None or args.context_budget_bytes is not None:
                context_options = {}
                if args.context_policy is not None:
                    context_options["policy"] = args.context_policy
                if args.context_budget_bytes is not None:
                    context_options["budget"] = {
                        "packet_bytes": args.context_budget_bytes,
                    }
            result = create(
                args.dsn, agent, genomes.load(args.dsn, roots["artifacts_root"], args.genome),
                investigation_id=args.id, task=tasks.load(args.dsn, roots["artifacts_root"], args.task),
                token_allocation=args.token_allocation, cpu_allocation=args.cpu_allocation,
                max_steps=args.max_steps, timeout_ms=args.timeout_ms,
                token_ceiling=args.token_ceiling, objective=args.objective,
                context=context_options, **roots)
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
