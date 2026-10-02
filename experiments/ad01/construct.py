"""Broker-backed acquired-method construction (AD01-LEARN-B).

The learner's construction requests travel through the broker as model
inference operations with durable attempt identities; responses parse
to exact source bytes that are gated, executed out of process and
checked before retention. Two lineages, one init plus one repair each.
"""

from __future__ import annotations

import hashlib
from typing import Any

FAMILY_TAG = {"software": "sw", "graph": "gr"}
MAX_LINEAGES = 2
CONSTRUCTION_CALL_CEILING = 4
PROMPT_BUDGET_CHARS = 8192


class ConstructionFailed(Exception):
    def __init__(self, message, *, calls_made=0, queries=0):
        super().__init__(message)
        self.calls_made = calls_made
        self.queries = queries


def _op_id(cid: str, lineage: int, attempt: str) -> str:
    return "ad01-%s-construct-l%d-%s" % (cid, lineage, attempt)


def _construction_allocation(dsn: str, cid: str, budget: dict,
                             parent_allocation_id: str) -> str:
    from settlement import store
    from settlement.common import Command, ResultCode
    aid = "ad01-%s-construct" % cid
    per_call = PROMPT_BUDGET_CHARS // 4 + int(budget.get(
        "max_output_tokens", 2048))
    need = CONSTRUCTION_CALL_CEILING * per_call
    made = store.subdivide_allocation(
        dsn, Command(request_id="subdivide-%s" % aid,
                     payload={"parent_id": parent_allocation_id,
                              "child_id": aid, "domain": "cpu",
                              "authorized": need, "max_occupancy": 8}))
    if made.code not in (ResultCode.APPLIED,
                         ResultCode.ALREADY_APPLIED):
        raise ConstructionFailed(
            "construction needs %d study authority from parent %s: %s"
            % (need, parent_allocation_id, made.detail))
    return aid


def _prompt(task: dict, experience: dict, budget: dict,
            prior_failure: dict | None) -> str:
    from . import method_exec
    from . import packet as _packet
    text = _packet.render_construction_prompt(
        _packet.construction_packet(
            task=task, experience=experience, budget=budget,
            prior_failure=prior_failure))
    rule = method_exec.entry_contract()["result_envelope"]["rule"]
    if rule not in text:
        text += "\nReturn envelope: %s." % rule
    return text


def _settled_text(dsn: str, operation_id: str) -> str | None:
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s"
                        " AND receipt_identity = %s AND outcome = 'success'",
                        (operation_id, "gw:%s" % operation_id))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        return None
    return str(dict(row.get("content") or {}).get("text", ""))


def _call(dsn: str, *, cid: str, lineage: int, attempt: str,
          prompt: str, budget: dict, gateway: Any, model: str,
          allocation_id: str) -> dict:
    from settlement import broker
    from settlement.common import ResultCode
    from .trajectory import reasoning_effort
    operation_id = _op_id(cid, lineage, attempt)
    settled = _settled_text(dsn, operation_id)
    if settled is not None:
        return {"operation_id": operation_id, "text": settled,
                "reused": True}
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": int(budget.get("max_output_tokens",
                                                     2048)),
                 "deadline_ms": int(budget.get("deadline_ms", 300_000)),
                 "reasoning_effort": reasoning_effort()},
        allocation_id=allocation_id)
    if ensured.code not in (ResultCode.APPLIED,
                            ResultCode.ALREADY_APPLIED):
        raise ConstructionFailed("construction call not admitted: %s"
                                 % ensured.detail)
    broker.dispatch_operation(dsn, operation_id, launchers={},
                              gateway=gateway)
    settled = _settled_text(dsn, operation_id)
    if settled is None:
        raise ConstructionFailed(
            "construction call %s left no settled response" % operation_id)
    return {"operation_id": operation_id, "text": settled, "reused": False}


def _check_source(source: str, entry: str, task: dict, max_queries: int, *,
                  dsn: str, allocation_id: str, operation_id: str) -> dict:
    from . import method_exec, trajectory
    member = {"capability_id": "acquired-check",
              "method_source": source, "entry": entry,
              "params": {"max_queries": 16},
              "scope": {"family": task["family"]}, "authored": False}
    try:
        method_exec.verify_member(member)
    except method_exec.MethodExecutionError as exc:
        return {"ok": False, "stage": "gate", "reason": str(exc)}
    try:
        result = method_exec.run_member_out_of_process(
            member, task, max_queries=max_queries, dsn=dsn,
            allocation_id=allocation_id, operation_id=operation_id)
    except method_exec.MethodExecutionError as exc:
        return {"ok": False, "stage": "execute", "reason": str(exc)}
    report = trajectory._check(task, result["candidate"])
    if report.get("verdict") != "preserved":
        return {"ok": False, "stage": "check", "result": result,
                "reason": "%s/%s" % (report.get("verdict"),
                                     report.get("reason", ""))}
    return {"ok": True, "stage": "check", "reason": "", "result": result}


def _member_id(task: dict, source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:8]
    return "acquired-%s-%s" % (FAMILY_TAG[task["family"]], digest)


def _source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _parse_entry(text: str) -> tuple:
    from . import packet as _packet
    return _packet.parse_construction_response(text)


def _evaluate(text: str, operation_id: str, task: dict, max_queries: int, *,
              dsn: str, allocation_id: str) -> dict:
    from . import method_exec
    source, problem = _parse_entry(text)
    failure = None
    checked = None
    entry = None
    if problem:
        failure = {"stage": "parse", "reason": problem,
                   "operation_id": operation_id}
    else:
        try:
            entry = _entry_name(source)
            method_exec.verify_member(
                {"method_source": source, "entry": entry})
        except (method_exec.MethodExecutionError, SyntaxError,
                ValueError) as exc:
            failure = {"stage": "gate", "reason": str(exc),
                       "operation_id": operation_id}
        if failure is None:
            checked = _check_source(
                source, entry, task, max_queries, dsn=dsn,
                allocation_id=allocation_id,
                operation_id=operation_id.replace("-construct-l", "-validate-l"))
            if not checked["ok"]:
                failure = {"stage": checked["stage"],
                           "reason": checked["reason"],
                           "operation_id": operation_id}
    return {"source": source, "entry": entry, "failure": failure,
            "ok": failure is None, "checked": checked}


def construct_method(dsn: str, *, campaign_id: str, task: dict,
                     experience: dict, budget: dict, gateway: Any,
                     model: str, study_root: str | None = None) -> dict:
    from .trajectory import _alloc_id, _campaign_operations

    episode = "%s-b%d-%s" % (campaign_id,
                             experience.get("boundary", {}).get("seq", 0),
                             task["task_id"])
    prior_lineages = sum(
        op["effect"] == "model-inference"
        and "-construct-l" in op["id"] and op["id"].endswith("-init")
        and not op["id"].startswith("ad01-%s-construct-" % episode)
        for op in _campaign_operations(dsn, campaign_id))
    if prior_lineages >= MAX_LINEAGES:
        raise ConstructionFailed("lineage cap reached (2/trajectory)")
    allocation_id = _construction_allocation(
        dsn, episode, budget, _alloc_id(campaign_id))
    calls_made = queries = 0
    operation_ids = []
    for lineage in range(1, MAX_LINEAGES - prior_lineages + 1):
        attempts = []
        for attempt in ("init", "repair"):
            if calls_made >= budget.get("model_calls", CONSTRUCTION_CALL_CEILING):
                raise ConstructionFailed("model call cap reached",
                                         calls_made=calls_made, queries=queries)
            operation_id = _op_id(episode, lineage, attempt)
            prior = attempts[-1]["failure"] if attempts else None
            try:
                record = _call(
                    dsn, cid=episode, lineage=lineage, attempt=attempt,
                    prompt=_prompt(task, experience, budget, prior),
                    budget=budget, gateway=gateway, model=model,
                    allocation_id=allocation_id)
            except ConstructionFailed as exc:
                from settlement import broker
                exists = broker.read_operation(
                    dsn, operation_id) is not None
                exc.calls_made = calls_made + int(exists)
                exc.queries = queries
                if attempt == "repair":
                    if exists:
                        operation_ids.append(operation_id)
                        calls_made += 1
                    attempts.append({
                        "operation_id": operation_id,
                        "failure": {"stage": "repair-transport",
                                    "reason": str(exc),
                                    "operation_id": operation_id}})
                    break
                raise
            operation_ids.append(operation_id)
            calls_made += 1
            evaluated = _evaluate(
                record["text"], operation_id, task,
                max(0, budget.get("max_queries", 16) - queries),
                dsn=dsn, allocation_id=_alloc_id(campaign_id))
            queries += (evaluated["checked"] or {}).get("result", {}).get("queries", 0)
            attempts.append({**record, **evaluated})
            if evaluated["failure"] is None:
                member = _member(task, evaluated["source"], evaluated["entry"],
                                 campaign_id, lineage, attempts, calls_made,
                                 study_root=study_root)
                member["validation"] = {"result": evaluated["checked"]["result"],
                                        "queries": queries}
                member["operation_ids"] = operation_ids
                return member
    raise ConstructionFailed("construction exhausted without a checked method",
                             calls_made=calls_made, queries=queries)


def _entry_name(source: str) -> str:
    import ast
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    raise ValueError("no entry function")


def _member(task: dict, source: str, entry: str, cid: str, lineage: int,
            attempts: list, calls_made: int,
            study_root: str | None = None) -> dict:
    init = attempts[0]
    repair = attempts[1] if len(attempts) > 1 else None
    return {
        "capability_id": _member_id(task, source),
        "method_source": source, "entry": entry,
        "params": {"max_queries": 16},
        "scope": {"family": task["family"]}, "authored": False,
        "qualified_on": task.get("task_id", ""),
        "source_digest": _source_digest(source),
        "lineage": {
            "campaign_id": cid, "lineage": lineage,
            "study_root": study_root,
            "init_operation": init["operation_id"],
            "repair_operation": repair["operation_id"] if repair else None,
            "init_failure": (init.get("failure") if repair else None),
            "calls_made": calls_made,
        },
    }
