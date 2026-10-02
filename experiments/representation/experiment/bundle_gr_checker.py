from __future__ import annotations

import sys

"""Graph family: triangle-free non-bipartite finite simple undirected graphs.

Legal outputs are subgraphs of the original preserving vertex identities:
vertex deletion (dropping incident edges) and edge deletion. Witness is the
conjunction of validity, absence of triangles and non-bipartiteness.
Caps: at most 10 vertices and 18 edges.
"""


from collections import deque

MAX_VERTICES = 10
MAX_EDGES = 18


class GraphInvalid(Exception):
    pass


def parse_graph(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise GraphInvalid("graph-not-a-dict")
    if raw.get("family") != "graph":
        raise GraphInvalid("wrong-family")
    vertices = raw.get("vertices")
    edges = raw.get("edges")
    if (not isinstance(vertices, list) or not vertices
            or any(not isinstance(v, int) or v < 0 for v in vertices)):
        raise GraphInvalid("bad-vertices")
    if len(set(vertices)) != len(vertices):
        raise GraphInvalid("duplicate-vertices")
    if len(vertices) > MAX_VERTICES:
        raise GraphInvalid("too-many-vertices")
    if not isinstance(edges, list):
        raise GraphInvalid("bad-edges")
    if len(edges) > MAX_EDGES:
        raise GraphInvalid("too-many-edges")
    known = set(vertices)
    seen: set = set()
    clean: list = []
    for edge in edges:
        if (not isinstance(edge, list) or len(edge) != 2
                or any(not isinstance(v, int) for v in edge)):
            raise GraphInvalid("bad-edge")
        first, second = edge
        if first == second:
            raise GraphInvalid("self-loop")
        if first not in known or second not in known:
            raise GraphInvalid("dangling-edge")
        key = (min(first, second), max(first, second))
        if key in seen:
            raise GraphInvalid("duplicate-edge")
        seen.add(key)
        clean.append([key[0], key[1]])
    task_id = raw.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise GraphInvalid("task-id-missing")
    return {"family": "graph", "task_id": task_id,
            "vertices": sorted(vertices), "edges": clean,
            "seed": raw.get("seed")}


def adjacency(vertices: list, edges: list) -> dict:
    table = {vertex: set() for vertex in vertices}
    for first, second in edges:
        table[first].add(second)
        table[second].add(first)
    return table


def has_triangle(vertices: list, edges: list) -> bool:
    table = adjacency(vertices, edges)
    for first, second in edges:
        if table[first] & table[second]:
            return True
    return False


def is_bipartite(vertices: list, edges: list) -> bool:
    table = adjacency(vertices, edges)
    color: dict = {}
    for root in vertices:
        if root in color:
            continue
        color[root] = 0
        queue = deque([root])
        while queue:
            current = queue.popleft()
            for other in table[current]:
                if other not in color:
                    color[other] = 1 - color[current]
                    queue.append(other)
                elif color[other] == color[current]:
                    return False
    return True


def witness_holds(graph: dict) -> bool:
    try:
        parsed = parse_graph(graph)
    except GraphInvalid:
        return False
    if has_triangle(parsed["vertices"], parsed["edges"]):
        return False
    return not is_bipartite(parsed["vertices"], parsed["edges"])


def is_legal_subgraph(original: dict, candidate: dict) -> bool:
    try:
        base = parse_graph(original)
        cand = parse_graph(candidate)
    except GraphInvalid:
        return False
    if cand["task_id"] != base["task_id"]:
        return False
    if not set(cand["vertices"]) <= set(base["vertices"]):
        return False
    base_edges = {(min(a, b), max(a, b)) for a, b in base["edges"]}
    for first, second in cand["edges"]:
        if (min(first, second), max(first, second)) not in base_edges:
            return False
        if first not in cand["vertices"] or second not in cand["vertices"]:
            return False
    return True


def delete_vertices(graph: dict, drop: set) -> dict:
    keep = [v for v in graph["vertices"] if v not in drop]
    kept = set(keep)
    edges = [[a, b] for a, b in graph["edges"] if a in kept and b in kept]
    return {"family": "graph", "task_id": graph["task_id"],
            "vertices": keep, "edges": edges, "seed": graph.get("seed")}


def delete_edges(graph: dict, drop: set) -> dict:
    edges = [edge for idx, edge in enumerate(graph["edges"]) if idx not in drop]
    return {"family": "graph", "task_id": graph["task_id"],
            "vertices": list(graph["vertices"]), "edges": edges,
            "seed": graph.get("seed")}


def measure(graph: dict) -> int:
    return len(graph["vertices"]) + len(graph["edges"])


def task_digest(graph: dict) -> str:
    from settlement.common import payload_digest
    return payload_digest({"task_id": graph["task_id"], "family": "graph",
                           "vertices": sorted(graph["vertices"]),
                           "edges": sorted(sorted(e) for e in graph["edges"])})


def odd_cycle(length: int, start: int = 0) -> tuple:
    vertices = list(range(start, start + length))
    edges = [[vertices[i], vertices[(i + 1) % length]] for i in range(length)]
    return vertices, edges
"""Trusted source checkers, one per family, plus budgeted oracle access.

Feedback vocabulary: ``preserved | not_preserved | invalid | unknown`` with
a checked measure and a bounded reason code. ``preserved`` requires a valid
candidate that stands in the legal subobject relation to the task, holds
the designated witness and (unless it is the byte-identical incumbent)
strictly decreases the source measure. Checker failure maps to ``unknown``,
never to evidence that the witness is absent.
"""



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

graphs = sys.modules[__name__]

def _wrapper_main(argv):
    import json as _json
    if argv == ['--selftest']:
        print(_json.dumps({'status': 'ok', 'data': {'checker_bundle': True}}))
        return 0
    doc = _json.load(open(argv[0], encoding='utf-8'))
    report = check_graph(doc['source_task'], doc['candidate'])
    _json.dump({'verdict': report['verdict'], 'measure': report['measure'], 'reason': report['reason']}, open(argv[1], 'w', encoding='utf-8'))
    return 0

if __name__ == '__main__':
    raise SystemExit(_wrapper_main(sys.argv[1:]))
