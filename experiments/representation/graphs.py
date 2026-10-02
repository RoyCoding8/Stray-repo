"""Graph family: triangle-free non-bipartite finite simple undirected graphs.

Legal outputs are subgraphs of the original preserving vertex identities:
vertex deletion (dropping incident edges) and edge deletion. Witness is the
conjunction of validity, absence of triangles and non-bipartiteness.
Caps: at most 10 vertices and 18 edges.
"""

from __future__ import annotations

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
