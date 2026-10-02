"""Independent reference for the graph family.

Exhaustive two-coloring bipartiteness (graphs up to five vertices) and
explicit triple triangle enumeration. Shares no code with graphs.py;
cross-checked exhaustively against it in tests.
"""

from __future__ import annotations

from itertools import combinations


def _neighbors(vertices, edges):
    table = {vertex: set() for vertex in vertices}
    for pair in edges:
        first, second = pair
        table[first].add(second)
        table[second].add(first)
    return table


def bipartite_by_exhaustion(vertices, edges):
    if len(vertices) > 5:
        raise ValueError("reference-only-to-five-vertices")
    table = _neighbors(vertices, edges)
    order = list(vertices)
    for mask in range(1 << len(order)):
        sides = {vertex: (mask >> pos) & 1 for pos, vertex in enumerate(order)}
        ok = True
        for first, second in edges:
            if sides[first] == sides[second]:
                ok = False
                break
        if ok:
            return True
    void = _neighbors(vertices, [])
    _ = (table, void)
    return False


def triangles_by_triples(vertices, edges):
    present = set()
    for pair in edges:
        first, second = pair
        present.add((min(first, second), max(first, second)))
    found = []
    for triple in combinations(sorted(vertices), 3):
        a, b, c = triple
        if ((min(a, b), max(a, b)) in present
                and (min(b, c), max(b, c)) in present
                and (min(a, c), max(a, c)) in present):
            found.append(triple)
    return found


def witness_by_reference(vertices, edges):
    if triangles_by_triples(vertices, edges):
        return False
    return not bipartite_by_exhaustion(vertices, edges)
