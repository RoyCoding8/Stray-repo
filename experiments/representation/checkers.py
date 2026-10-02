"""Trusted source checkers, one per family, plus budgeted oracle access.

Feedback vocabulary: ``preserved | not_preserved | invalid | unknown`` with
a checked measure and a bounded reason code. ``preserved`` requires a valid
candidate that stands in the legal subobject relation to the task, holds
the designated witness and (unless it is the byte-identical incumbent)
strictly decreases the source measure. Checker failure maps to ``unknown``,
never to evidence that the witness is absent.
"""

from __future__ import annotations

from . import graphs, software

PRESERVED = "preserved"
NOT_PRESERVED = "not_preserved"
INVALID = "invalid"
UNKNOWN = "unknown"

SOFTWARE_REASONS = frozenset({
    "ok-preserved",
    "ok-incumbent",
    "witness-lost-agree",
    "witness-value-changed",
    "observation-missing",
    "illegal-deletion",
    "invalid-task",
    "invalid-candidate",
    "task-mismatch",
    "budget-exhausted",
    "checker-failure",
})

GRAPH_REASONS = frozenset({
    "ok-preserved",
    "ok-incumbent",
    "witness-lost-bipartite",
    "illegal-subgraph",
    "invalid-task",
    "invalid-candidate",
    "task-mismatch",
    "budget-exhausted",
    "checker-failure",
})


def check_software(task: dict, candidate) -> dict:
    try:
        parsed_task = software.parse_task(task)
    except software.SoftwareInvalid:
        return _report(INVALID, None, None, "invalid-task")
    except Exception:
        return _report(UNKNOWN, None, None, "checker-failure")
    initial = software.measure(parsed_task["ops"])
    try:
        if not isinstance(candidate, dict) or candidate.get("family") != "software":
            raise software.SoftwareInvalid("invalid-candidate")
        candidate_ops = software.parse_ops(candidate.get("ops"))
        if candidate.get("task_id", parsed_task["task_id"]) != parsed_task["task_id"]:
            raise software.SoftwareInvalid("task-mismatch")
    except software.SoftwareInvalid as exc:
        reason = str(exc) or "invalid-candidate"
        if reason == "task-mismatch":
            return _report(INVALID, None, initial, reason)
        return _report(INVALID, None, initial, "invalid-candidate")
    except Exception:
        return _report(UNKNOWN, None, initial, "checker-failure")
    current = software.measure(candidate_ops)
    if not software.task_is_valid(parsed_task):
        return _report(INVALID, current, initial, "invalid-task")
    if not software.is_legal_deletion(parsed_task["ops"], candidate.get("ops")):
        return _report(INVALID, current, initial, "illegal-deletion")
    if candidate.get("ops") == parsed_task["ops"]:
        if software.witness_holds(parsed_task, candidate_ops):
            return _report(PRESERVED, current, initial, "ok-incumbent")
        return _report(NOT_PRESERVED, current, initial, "witness-lost-agree")
    return _witness_verdict(parsed_task, candidate_ops, current, initial)


def _witness_verdict(parsed_task, candidate_ops, current, initial) -> dict:
    witness = parsed_task["witness"]
    try:
        actual = software.actual_witness(candidate_ops, parsed_task["fault"],
                                         witness["observation"])
    except software.SoftwareInvalid:
        return _report(NOT_PRESERVED, current, initial, "observation-missing")
    if actual["ref"] == actual["faulty"]:
        return _report(NOT_PRESERVED, current, initial, "witness-lost-agree")
    if actual["ref"] != witness["ref"] or actual["faulty"] != witness["faulty"]:
        return _report(NOT_PRESERVED, current, initial, "witness-value-changed")
    return _report(PRESERVED, current, initial, "ok-preserved")


def _report(verdict: str, current, initial, reason: str) -> dict:
    return {"verdict": verdict, "measure": current,
            "initial_measure": initial, "reason": reason}


def check_graph(task: dict, candidate) -> dict:
    try:
        parsed_task = graphs.parse_graph(task)
    except graphs.GraphInvalid:
        return _report(INVALID, None, None, "invalid-task")
    try:
        parsed_candidate = graphs.parse_graph(candidate)
    except graphs.GraphInvalid:
        return _report(INVALID, None, graphs.measure(parsed_task), "invalid-candidate")
    initial = graphs.measure(parsed_task)
    current = graphs.measure(parsed_candidate)
    if not graphs.witness_holds(parsed_task):
        return _report(INVALID, current, initial, "invalid-task")
    if parsed_candidate["task_id"] != parsed_task["task_id"]:
        return _report(INVALID, current, initial, "task-mismatch")
    if not graphs.is_legal_subgraph(parsed_task, parsed_candidate):
        return _report(INVALID, current, initial, "illegal-subgraph")
    if (parsed_candidate["vertices"] == parsed_task["vertices"]
            and sorted(map(sorted, parsed_candidate["edges"]))
            == sorted(map(sorted, parsed_task["edges"]))):
        if graphs.witness_holds(parsed_candidate):
            return _report(PRESERVED, current, initial, "ok-incumbent")
        return _report(NOT_PRESERVED, current, initial, "witness-lost-bipartite")
    if graphs.is_bipartite(parsed_candidate["vertices"], parsed_candidate["edges"]):
        return _report(NOT_PRESERVED, current, initial, "witness-lost-bipartite")
    return _report(PRESERVED, current, initial, "ok-preserved")


class BudgetedOracle:
    family: str = ""
    max_queries: int = 16

    def __init__(self, task: dict, *, max_queries: int = 16) -> None:
        self.task = task
        self.max_queries = max_queries
        self.queries_used = 0
        self.history: list = []

    def query(self, candidate) -> dict:
        if self.queries_used >= self.max_queries:
            report = _report(UNKNOWN, None, None, "budget-exhausted")
            self.history.append(report)
            return report
        self.queries_used += 1
        try:
            report = self.check(candidate)
        except Exception:
            report = _report(UNKNOWN, None, None, "checker-failure")
        self.history.append(report)
        return report

    def check(self, candidate) -> dict:
        raise NotImplementedError

    def exhausted(self) -> bool:
        return self.queries_used >= self.max_queries


class SoftwareOracle(BudgetedOracle):
    family = "software"

    def check(self, candidate) -> dict:
        return check_software(self.task, candidate)


class GraphOracle(BudgetedOracle):
    family = "graph"

    def check(self, candidate) -> dict:
        return check_graph(self.task, candidate)
