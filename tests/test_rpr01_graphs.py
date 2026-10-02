"""RPR-01 graph family: validity, triangles, bipartiteness, legality."""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import graphs
from experiments.representation.graphs import GraphInvalid

FIXTURES = ROOT / "experiments" / "representation" / "fixtures" / "graphs"


def test_parse_rejects_nonsimple_graphs():
    base = {"family": "graph", "task_id": "g", "vertices": [0, 1, 2],
            "edges": [[0, 1], [1, 2]], "seed": 0}
    graphs.parse_graph(base)
    with pytest.raises(GraphInvalid):
        graphs.parse_graph(dict(base, edges=[[0, 0], [0, 1]]))
    with pytest.raises(GraphInvalid):
        graphs.parse_graph(dict(base, edges=[[0, 1], [1, 0]]))
    with pytest.raises(GraphInvalid):
        graphs.parse_graph(dict(base, edges=[[0, 1], [1, 9]]))
    with pytest.raises(GraphInvalid):
        graphs.parse_graph(dict(base, vertices=[0, 0, 1]))
    with pytest.raises(GraphInvalid):
        graphs.parse_graph(dict(base, vertices=list(range(11)),
                                edges=[[i, i + 1] for i in range(10)]))


def test_triangle_and_bipartite_detectors():
    assert graphs.has_triangle([0, 1, 2], [[0, 1], [1, 2], [2, 0]])
    assert not graphs.has_triangle([0, 1, 2, 3, 4],
                                   [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0]])
    assert graphs.is_bipartite([0, 1, 2, 3], [[0, 1], [1, 2], [2, 3], [3, 0]])
    assert not graphs.is_bipartite([0, 1, 2, 3, 4],
                                   [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0]])


def test_witness_conjunction():
    cycle5 = {"family": "graph", "task_id": "g", "vertices": [0, 1, 2, 3, 4],
              "edges": [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0]], "seed": 0}
    assert graphs.witness_holds(cycle5)
    assert not graphs.witness_holds(dict(cycle5, edges=[[0, 1]]))
    triangle = dict(cycle5, vertices=[0, 1, 2],
                    edges=[[0, 1], [1, 2], [2, 0]])
    assert not graphs.witness_holds(triangle)


def test_legal_subgraph_preserves_vertex_ids():
    task = json.loads((FIXTURES / "development" / "gr-dev-00.json").read_text())
    assert graphs.is_legal_subgraph(task, task)
    smaller = graphs.delete_vertices(task, {task["vertices"][-1]})
    assert smaller["vertices"] != task["vertices"]
    assert graphs.is_legal_subgraph(task, smaller)
    assert graphs.is_legal_subgraph(task, graphs.delete_edges(task, {0}))
    grown = dict(task, vertices=sorted(task["vertices"] + [99]))
    assert not graphs.is_legal_subgraph(task, grown)
    renumbered = {"family": "graph", "task_id": task["task_id"],
                  "vertices": list(range(len(task["vertices"]))),
                  "edges": task["edges"], "seed": 0}
    if renumbered["vertices"] != task["vertices"]:
        assert not graphs.is_legal_subgraph(task, renumbered)
    forged = dict(task, task_id="other")
    assert not graphs.is_legal_subgraph(task, forged)


def test_committed_fixtures_witness_and_caps():
    files = sorted(FIXTURES.rglob("*.json"))
    assert len(files) == 18
    for path in files:
        task = json.loads(path.read_text())
        assert graphs.witness_holds(task), path.name
        assert len(task["vertices"]) <= graphs.MAX_VERTICES
        assert len(task["edges"]) <= graphs.MAX_EDGES


def _components(vertices, edges):
    table = {v: set() for v in vertices}
    for first, second in edges:
        table[first].add(second)
        table[second].add(first)
    seen, count = set(), 0
    for root in vertices:
        if root in seen:
            continue
        count += 1
        queue = deque([root])
        seen.add(root)
        while queue:
            current = queue.popleft()
            for other in table[current]:
                if other not in seen:
                    seen.add(other)
                    queue.append(other)
    return count


def test_panel_spans_constructions():
    tasks = [json.loads(path.read_text()) for path in FIXTURES.rglob("*.json")]
    assert any(_components(t["vertices"], t["edges"]) >= 2 for t in tasks)
    assert any(any(len(n) == 1 for n in
                   graphs.adjacency(t["vertices"], t["edges"]).values())
               for t in tasks)
    assert any(len(t["edges"]) - len(t["vertices"])
               + _components(t["vertices"], t["edges"]) >= 2 for t in tasks)
