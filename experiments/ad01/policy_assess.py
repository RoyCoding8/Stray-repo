"""Sealed finite-panel assessment for learning-policy artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import time

from settlement import db, store
from settlement.common import Command, ConflictPayload, ResultCode

from . import method_exec, policy_step, records, seeds, trajectory, worlds


PANEL_PROTOCOL = "s09-policy-assess-01"
EVALUATOR_VERSION = "s09-policy-eval-01"
_DEFAULT_MAX_STEPS = 6


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _protocol_request_id(proposal_id: str) -> str:
    return "s09-policy-protocol-%s" % proposal_id


def _read_journal(dsn: str, request_id: str) -> dict | None:
    from psycopg.rows import dict_row
    with db.connect(dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT result_data FROM command_journal WHERE request_id = %s",
            (request_id,)).fetchone()
        conn.commit()
    return dict(row["result_data"]) if row is not None else None


def _panel_identity(panel: dict) -> dict:
    if not isinstance(panel, dict):
        raise ValueError("panel must be an object")
    task_ids = panel.get("task_ids")
    scope = panel.get("scope")
    if not isinstance(task_ids, list) or not task_ids or any(
            not isinstance(task_id, str) or not task_id for task_id in task_ids):
        raise ValueError("panel needs non-empty task ids")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("panel task ids must be unique")
    if not isinstance(scope, dict):
        raise ValueError("panel needs a scope")
    return {"panel_id": str(panel.get("panel_id", "")),
            "task_ids": list(task_ids), "scope": dict(scope)}


def _panel_digest(panel: dict) -> str:
    identity = _panel_identity(panel)
    return _digest({"panel_id": identity["panel_id"],
                    "task_ids": identity["task_ids"],
                    "scope": identity["scope"]})


def _rule_identity(rule: dict) -> dict:
    if not isinstance(rule, dict):
        raise ValueError("rule must be an object")
    required = ("rule_id", "margin", "min_preserved", "resource_ceiling", "tie")
    if any(key not in rule for key in required):
        raise ValueError("rule is missing a required field")
    if rule["tie"] != "reject":
        raise ValueError("rule tie must be reject")
    for key in ("margin", "min_preserved", "resource_ceiling"):
        if type(rule[key]) is not int or rule[key] < 0:
            raise ValueError("rule %s must be a nonnegative integer" % key)
    max_steps = rule.get("max_steps", _DEFAULT_MAX_STEPS)
    if type(max_steps) is not int or max_steps <= 0:
        raise ValueError("rule max_steps must be a positive integer")
    return {"rule_id": str(rule["rule_id"]),
            "margin": rule["margin"],
            "min_preserved": rule["min_preserved"],
            "resource_ceiling": rule["resource_ceiling"],
            "max_steps": max_steps, "tie": "reject"}


def _rule_digest(rule: dict) -> str:
    return _digest(_rule_identity(rule))


def panel_for(*, scope: dict, world: int, seed: str, size: int = 2) -> dict:
    if not isinstance(scope, dict) or not isinstance(scope.get("family"), str):
        raise ValueError("panel scope needs a family")
    if type(world) is not int or type(size) is not int or size <= 0:
        raise ValueError("panel world and size are invalid")
    family = scope["family"]
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    if str(world) not in membership:
        raise ValueError("unknown panel world %r" % world)
    available = []
    development = trajectory._dev_task_ids()
    for group in ("within", "transfer"):
        for task_id in membership[str(world)].get(group, {}).get(family, []):
            if task_id not in development:
                worlds.load_task(worlds.FROZEN_DIR, task_id)
                available.append(task_id)
    if size > len(available):
        raise ValueError("panel size exceeds frozen task family")
    task_ids = sorted(available,
                      key=lambda task_id: _source_digest(
                          "%s:%s:%s" % (seed, world, task_id)))[:size]
    identity = {"task_ids": task_ids, "scope": dict(scope)}
    panel_digest = _digest(identity)
    return {"panel_id": "s09-panel-%s" % panel_digest[:16],
            "task_ids": task_ids, "panel_digest": panel_digest,
            "scope": dict(scope)}


def rule_for(*, margin: int = 1, min_preserved: int = 1,
             resource_ceiling: int = 0) -> dict:
    rule = {"margin": margin, "min_preserved": min_preserved,
            "resource_ceiling": resource_ceiling,
            "max_steps": _DEFAULT_MAX_STEPS, "tie": "reject"}
    for key, value in rule.items():
        if key != "tie" and (type(value) is not int or value < 0):
            raise ValueError("rule %s must be a nonnegative integer" % key)
    if rule["max_steps"] <= 0:
        raise ValueError("rule max_steps must be positive")
    rule["rule_id"] = "s09-rule-%s" % _rule_digest(
        {**rule, "rule_id": ""})[:16]
    return {"rule_id": rule["rule_id"], "margin": rule["margin"],
            "min_preserved": rule["min_preserved"],
            "resource_ceiling": rule["resource_ceiling"],
            "max_steps": rule["max_steps"], "tie": rule["tie"]}


def _protocol_record(proposal_id: str, panel: dict, rule: dict) -> dict:
    panel_digest = _panel_digest(panel)
    rule_id = _rule_identity(rule)["rule_id"]
    protocol_digest = _digest({"protocol": PANEL_PROTOCOL,
                               "panel_digest": panel_digest,
                               "rule_id": rule_id,
                               "rule_digest": _rule_digest(rule)})
    return {"proposal_id": proposal_id, "panel_digest": panel_digest,
            "rule_id": rule_id, "rule_digest": _rule_digest(rule),
            "protocol_digest": protocol_digest}


def freeze_protocol(dsn: str, *, proposal_id: str, panel: dict,
                    rule: dict) -> dict:
    if not proposal_id:
        raise ValueError("protocol needs a proposal id")
    frozen = _protocol_record(proposal_id, panel, rule)
    request_id = _protocol_request_id(proposal_id)
    existing = _read_journal(dsn, request_id)
    if existing is not None:
        if existing != frozen:
            raise ValueError("proposal %r already froze a different panel or rule"
                             % proposal_id)
        return existing
    payload = {"proposal_id": proposal_id,
               "panel_digest": frozen["panel_digest"],
               "rule_id": frozen["rule_id"],
               "rule_digest": frozen["rule_digest"],
               "protocol_digest": frozen["protocol_digest"]}
    try:
        result = store.transact(
            dsn, Command(request_id=request_id, payload=payload),
            lambda cur, control: (ResultCode.APPLIED, "policy protocol frozen",
                                  frozen, [], []))
    except ConflictPayload as exc:
        raise ValueError("proposal %r already froze a different panel or rule"
                         % proposal_id) from exc
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise ValueError("protocol not persisted: %s" % result.detail)
    data = dict(result.data or frozen)
    if data != frozen:
        raise ValueError("proposal %r already froze a different panel or rule"
                         % proposal_id)
    return data


def _empty_arm(task_count: int) -> dict:
    return {"decisions": [], "effects": [],
            "quality": {"tasks": task_count, "preserved": 0,
                        "reduced": 0, "failed": task_count},
            "resources": {"step_calls": 0, "model_calls": 0,
                          "queries": 0, "child_wall_ms": 0}}


def _state_digest(state: dict) -> str:
    return _digest(state)


def _elapsed_ms(started: int) -> int:
    return max(1, int(math.ceil((time.perf_counter_ns() - started) / 1_000_000)))


def _candidate_from_action(task: dict, action: dict) -> tuple[dict | None, int, int, int, str | None]:
    kind = action["kind"]
    inputs = dict(action.get("inputs") or {})
    if kind not in ("construct_method", "use_method"):
        if kind in ("diagnose", "stop"):
            return None, 0, 0, 0, None
        return None, 0, 0, 0, "action has no task-producing effect"
    if "candidate" in inputs:
        return None, 0, 0, 0, ("policy-supplied candidate is not a task outcome;"
                               " a learning policy directs method execution and"
                               " does not answer the panel task itself")
    source = inputs.get("method_source") or inputs.get("source")
    max_queries = inputs.get("max_queries", 16)
    if type(max_queries) is not int or max_queries < 0:
        return None, 0, 0, 0, "max_queries must be a nonnegative integer"
    started = time.perf_counter_ns()
    if isinstance(source, str) and source:
        entry = inputs.get("entry", "ENTRY")
        member = {"method_source": source, "entry": entry}
        try:
            method_exec.verify_member(member)
            result = method_exec.run_member_out_of_process(
                member, task, max_queries=max_queries)
        except Exception as exc:
            return None, 0, 0, _elapsed_ms(started), str(exc)
        return result.get("candidate"), int(result.get("queries", 0)), 0, \
            _elapsed_ms(started), None
    method_id = inputs.get("method_id")
    if method_id is None:
        method_id = "seed-%s-greedy" % ("sw" if task["family"] == "software"
                                         else "gr")
    capability = next((item for item in seeds.SEED_CAPABILITIES
                       if item["capability_id"] == method_id), None)
    if capability is None or capability["family"] != task["family"]:
        return None, 0, 0, _elapsed_ms(started), "unknown task method %r" % method_id
    try:
        result = seeds.run_seed(capability, task, max_queries=max_queries)
    except Exception as exc:
        return None, 0, 0, _elapsed_ms(started), str(exc)
    return result.get("candidate"), int(result.get("queries", 0)), 0, \
        _elapsed_ms(started), None


def _effect(task: dict, action: dict) -> tuple[dict, dict | None, int, int, int]:
    kind = action["kind"]
    if action.get("target") != task["task_id"]:
        return {"kind": kind, "accepted": False,
                "reason": "action target does not match panel task"}, None, 0, 0, 0
    if kind == "request_model":
        return {"kind": kind, "accepted": False,
                "reason": "model execution is unavailable in sealed assessment"}, None, 0, 0, 0
    if kind == "propose_revision":
        return {"kind": kind, "accepted": False,
                "reason": "revision proposal is not a panel task effect"}, None, 0, 0, 0
    candidate, queries, model_calls, wall_ms, failure = _candidate_from_action(task, action)
    if failure:
        return {"kind": kind, "accepted": False, "reason": failure}, None, wall_ms, queries, model_calls
    if kind in ("diagnose", "stop"):
        return {"kind": kind, "accepted": True}, None, wall_ms, queries, model_calls
    if candidate is None:
        return {"kind": kind, "accepted": False,
                "reason": "action produced no candidate"}, None, wall_ms, queries, model_calls
    return {"kind": kind, "accepted": True}, candidate, wall_ms, queries, model_calls


def _run_arm(policy_record: dict, task_ids: list[str], rule: dict) -> dict:
    arm = _empty_arm(len(task_ids))
    reports = []
    seq = 0
    for task_id in task_ids:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        state = {}
        observations = []
        last_result = None
        task_report = None
        for step_no in range(rule["max_steps"]):
            view = policy_step.materialize_view(
                task=task, observations=observations, open_questions=[],
                last_result=last_result,
                eligible_methods=[item["capability_id"] for item in seeds.SEED_CAPABILITIES
                                  if item["family"] == task["family"]],
                remaining={"steps": rule["max_steps"] - step_no,
                           "model_calls": 0, "queries": 0})
            previous = dict(state)
            started = time.perf_counter_ns()
            try:
                stepped = policy_step.run_policy_step(policy_record, view, state)
            except Exception as exc:
                elapsed = _elapsed_ms(started)
                arm["resources"]["step_calls"] += 1
                arm["resources"]["child_wall_ms"] += elapsed
                arm["decisions"].append({"seq": seq, "task_id": task_id,
                                          "kind": "step_error", "target": task_id,
                                          "state_digest": _state_digest(previous)})
                arm["effects"].append({"kind": "step_error", "accepted": False,
                                        "reason": str(exc)})
                seq += 1
                break
            elapsed = _elapsed_ms(started)
            arm["resources"]["step_calls"] += 1
            arm["resources"]["child_wall_ms"] += elapsed
            action = dict(stepped["action"])
            state = dict(stepped["state"])
            arm["decisions"].append({"seq": seq, "task_id": task_id,
                                      "kind": action["kind"],
                                      "target": task_id if action["target"] != task_id
                                      else action["target"],
                                      "state_digest": _state_digest(state)})
            effect, candidate, effect_ms, queries, model_calls = _effect(task, action)
            arm["effects"].append(effect)
            arm["resources"]["queries"] += queries
            arm["resources"]["model_calls"] += model_calls
            arm["resources"]["child_wall_ms"] += effect_ms
            seq += 1
            if candidate is not None:
                try:
                    report = trajectory._check(task, candidate)
                    initial, final = trajectory._size(task, candidate)
                    task_report = {"report": report, "initial": initial,
                                   "final": final}
                except Exception as exc:
                    task_report = {"report": {"verdict": "failed",
                                               "reason": str(exc)},
                                   "initial": trajectory._size(task, task)[0],
                                   "final": trajectory._size(task, task)[0]}
                break
            last_result = {"verdict": "unmeasured", "kind": action["kind"],
                           "accepted": effect["accepted"]}
            observations.append({"observation_id": "panel-%s-%d" % (task_id, step_no),
                                 "task_id": task_id, "verdict": "unmeasured",
                                 "detail": {"accepted": effect["accepted"]}})
            if action["kind"] == "stop":
                break
        reports.append(task_report)
    preserved = 0
    reduced = 0
    for task_report in reports:
        if task_report is None:
            continue
        report = task_report["report"]
        if report.get("verdict") == "preserved":
            preserved += 1
            if task_report["final"] < task_report["initial"]:
                reduced += 1
    arm["quality"] = {"tasks": len(task_ids), "preserved": preserved,
                       "reduced": reduced, "failed": len(task_ids) - preserved}
    return arm


def _verify_candidate(source: str, digest: str, artifact: dict) -> dict | None:
    if _source_digest(source) != digest:
        raise ValueError("candidate source digest does not match candidate_digest")
    try:
        policy_step.verify_policy_record(artifact)
    except method_exec.MethodExecutionError as exc:
        return {"reason": "candidate source unavailable: %s" % exc}
    return None


def _verify_incumbent(source: str, digest: str, artifact: dict) -> None:
    if _source_digest(source) != digest:
        raise ValueError("incumbent source digest does not match incumbent_digest")
    policy_step.verify_policy_record(artifact)


def _decision(candidate: dict, incumbent: dict, rule: dict) -> tuple[str, str]:
    cq = candidate["quality"]
    iq = incumbent["quality"]
    if cq["preserved"] < rule["min_preserved"]:
        return "reject", "candidate preserved %d tasks; minimum is %d" % (
            cq["preserved"], rule["min_preserved"])
    margin = cq["reduced"] - iq["reduced"]
    if margin < rule["margin"]:
        return "reject", "reduction margin %d is below %d; tie rejects" % (
            margin, rule["margin"])
    candidate_cost = (candidate["resources"]["queries"]
                      + candidate["resources"]["model_calls"]
                      + candidate["resources"]["step_calls"])
    incumbent_cost = (incumbent["resources"]["queries"]
                      + incumbent["resources"]["model_calls"]
                      + incumbent["resources"]["step_calls"])
    overrun = candidate_cost - incumbent_cost
    if overrun > rule["resource_ceiling"]:
        return "reject", "resource overrun: candidate %d versus incumbent %d " \
            "(ceiling %d), counting queries, model calls and policy steps" % (
                candidate_cost, incumbent_cost, rule["resource_ceiling"])
    return "bind", "candidate preserved %d/%d and reduced %d/%d within resource ceiling" % (
        cq["preserved"], cq["tasks"], cq["reduced"], cq["tasks"])


def _persist_assessment(dsn: str, record: dict) -> dict:
    request_id = record["attempt_id"]
    payload = {"proposal_id": record["proposal_id"],
               "candidate_digest": record["candidate_digest"],
               "protocol_id": record["protocol_id"],
               "evaluator_version": record["evaluator_version"],
               "panel_digest": record["panel"]["panel_digest"],
               "rule_id": record["rule"]["rule_id"]}
    try:
        result = store.transact(
            dsn, Command(request_id=request_id, payload=payload),
            lambda cur, control: (ResultCode.APPLIED, record["outcome"],
                                  record, [], []))
    except ConflictPayload as exc:
        raise ValueError("assessment request identity has different inputs") from exc
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise ValueError("assessment not persisted: %s" % result.detail)
    return dict(result.data or record)


def assess_policy(dsn: str, *, proposal_id: str, candidate_source: str,
                  candidate_digest: str, candidate_artifact: dict,
                  incumbent_source: str, incumbent_digest: str,
                  incumbent_artifact: dict, panel: dict, rule: dict,
                  scope: dict, protocol_id: str,
                  evaluator_version: str = EVALUATOR_VERSION) -> dict:
    frozen = _read_journal(dsn, _protocol_request_id(proposal_id))
    if frozen is None:
        raise ValueError("policy protocol is not frozen for proposal %r" % proposal_id)
    supplied_panel_digest = _panel_digest(panel)
    supplied_rule = _rule_identity(rule)
    if (frozen.get("panel_digest") != supplied_panel_digest or
            frozen.get("rule_id") != supplied_rule["rule_id"] or
            frozen.get("rule_digest") != _rule_digest(supplied_rule)):
        raise ValueError("policy exposure differs from frozen protocol")
    if _source_digest(candidate_source) != candidate_digest:
        raise ValueError("candidate source digest does not match candidate_digest")
    candidate_unavailable = _verify_candidate(candidate_source, candidate_digest,
                                               candidate_artifact)
    attempt_id = records.assessment_attempt_id(proposal_id, candidate_digest)
    if candidate_unavailable is not None:
        empty_candidate = _empty_arm(len(panel["task_ids"]))
        empty_incumbent = _empty_arm(len(panel["task_ids"]))
        record = {"proposal_id": proposal_id, "attempt_id": attempt_id,
                  "outcome": "unavailable", "reason": candidate_unavailable["reason"],
                  "protocol_id": protocol_id, "evaluator_version": evaluator_version,
                  "scope": dict(scope), "candidate_digest": candidate_digest,
                  "panel": {"panel_id": panel.get("panel_id", ""),
                            "task_ids": list(panel["task_ids"]),
                            "panel_digest": supplied_panel_digest,
                            "scope": dict(panel["scope"])},
                  "rule": supplied_rule,
                  "arms": {"candidate": empty_candidate,
                           "incumbent": empty_incumbent}}
        return _persist_assessment(dsn, record)
    _verify_incumbent(incumbent_source, incumbent_digest, incumbent_artifact)
    stored = _read_journal(dsn, attempt_id)
    if stored is not None:
        return stored
    candidate_record = {"artifact": dict(candidate_artifact["artifact"]),
                        "policy_source": candidate_source}
    incumbent_record = {"artifact": dict(incumbent_artifact["artifact"]),
                        "policy_source": incumbent_source}
    candidate_arm = _run_arm(candidate_record, list(panel["task_ids"]), supplied_rule)
    incumbent_arm = _run_arm(incumbent_record, list(panel["task_ids"]), supplied_rule)
    outcome, reason = _decision(candidate_arm, incumbent_arm, supplied_rule)
    record = {"proposal_id": proposal_id, "attempt_id": attempt_id,
              "outcome": outcome, "reason": reason,
              "protocol_id": protocol_id, "evaluator_version": evaluator_version,
              "scope": dict(scope), "candidate_digest": candidate_digest,
              "panel": {"panel_id": panel.get("panel_id", ""),
                        "task_ids": list(panel["task_ids"]),
                        "panel_digest": supplied_panel_digest,
                        "scope": dict(panel["scope"])},
              "rule": supplied_rule,
              "arms": {"candidate": candidate_arm, "incumbent": incumbent_arm}}
    return _persist_assessment(dsn, record)
