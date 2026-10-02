"""RPR-01 trusted checkers plus independent reference cross-checks."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import checkers, graphs, software
from experiments.representation import graph_reference, software_reference
from experiments.representation.checkers import (
    GRAPH_REASONS, SOFTWARE_REASONS,
)

SW = ROOT / "experiments" / "representation" / "fixtures" / "software"
GR = ROOT / "experiments" / "representation" / "fixtures" / "graphs"
CT = ROOT / "experiments" / "representation" / "fixtures" / "controls"


def _sw_task():
    return {"family": "software", "task_id": "t", "fault": "stale-read",
            "ops": [{"op": "set", "key": "a", "value": "v1"},
                    {"op": "set", "key": "a", "value": "v2"},
                    {"op": "get", "key": "a", "id": "w"},
                    {"op": "set", "key": "b", "value": "v9"}],
            "witness": {"observation": "w",
                        "ref": {"type": "str", "value": "v2"},
                        "faulty": {"type": "str", "value": "v1"}},
            "seed": 0}


def test_software_checker_accepts_incumbent_and_reduction():
    task = _sw_task()
    incumbent = checkers.check_software(task, task)
    assert incumbent["verdict"] == "preserved"
    assert incumbent["reason"] == "ok-incumbent"
    assert incumbent["measure"] == incumbent["initial_measure"] == 4
    reduced = dict(task, ops=task["ops"][:3])
    report = checkers.check_software(task, reduced)
    assert report["verdict"] == "preserved"
    assert report["reason"] == "ok-preserved"
    assert report["measure"] == 3
    assert report["reason"] in SOFTWARE_REASONS


def test_software_checker_rejects_wrong_witness_invalid_measure():
    task = _sw_task()
    lost = dict(task, ops=[{"op": "set", "key": "a", "value": "v1"},
                           {"op": "get", "key": "a", "id": "w"},
                           {"op": "set", "key": "b", "value": "v9"}])
    report = checkers.check_software(task, lost)
    assert report["verdict"] == "not_preserved"
    assert report["reason"] == "witness-lost-agree"
    same_size = dict(task, ops=[{"op": "set", "key": "a", "value": "v1"},
                                {"op": "set", "key": "a", "value": "v2"},
                                {"op": "get", "key": "a", "id": "w"},
                                {"op": "set", "key": "b", "value": "v8"}])
    report = checkers.check_software(task, same_size)
    assert report["verdict"] == "invalid"
    assert report["reason"] == "illegal-deletion"
    grown = dict(task, ops=task["ops"] + [{"op": "set", "key": "b",
                                           "value": "v9"}])
    report = checkers.check_software(task, grown)
    assert report["verdict"] == "invalid"
    assert report["reason"] == "illegal-deletion"
    malformed = dict(task, ops=[{"op": "melt", "key": "a"}])
    report = checkers.check_software(task, malformed)
    assert report["verdict"] == "invalid"
    forged = dict(task, task_id="elsewhere")
    assert checkers.check_software(task, forged)["reason"] == "task-mismatch"
    assert checkers.check_software({"family": "software"}, task)["reason"] \
        == "invalid-task"


def test_graph_checker_accepts_incumbent_and_reduction():
    task = json.loads((GR / "development" / "gr-dev-00.json").read_text())
    incumbent = checkers.check_graph(task, task)
    assert incumbent["verdict"] == "preserved"
    assert incumbent["reason"] == "ok-incumbent"
    leaf = next(v for v, neighbors in graphs.adjacency(
        task["vertices"], task["edges"]).items() if len(neighbors) == 1)
    reduced = graphs.delete_vertices(task, {leaf})
    report = checkers.check_graph(task, reduced)
    assert report["verdict"] == "preserved"
    assert report["measure"] < report["initial_measure"]
    assert report["reason"] in GRAPH_REASONS


def test_graph_checker_rejects_bipartite_invalid_measure():
    task = json.loads((GR / "development" / "gr-dev-00.json").read_text())
    path = {"family": "graph", "task_id": task["task_id"],
            "vertices": [0, 1, 2], "edges": [[0, 1]], "seed": 0}
    assert not graphs.is_bipartite(task["vertices"], task["edges"])
    assert graphs.is_bipartite(path["vertices"], path["edges"])
    report = checkers.check_graph(task, path)
    assert report["verdict"] == "not_preserved"
    assert report["reason"] == "witness-lost-bipartite"
    loopy = {"family": "graph", "task_id": task["task_id"],
             "vertices": [0], "edges": [[0, 0]], "seed": 0}
    assert checkers.check_graph(task, loopy)["verdict"] == "invalid"
    forged = dict(task, task_id="elsewhere")
    assert checkers.check_graph(task, forged)["reason"] == "task-mismatch"


def test_oracle_budget_exhaustion_is_unknown():
    task = _sw_task()
    oracle = checkers.SoftwareOracle(task, max_queries=2)
    assert oracle.query(task)["verdict"] == "preserved"
    assert oracle.query(task)["verdict"] == "preserved"
    report = oracle.query(task)
    assert report["verdict"] == "unknown"
    assert report["reason"] == "budget-exhausted"
    assert oracle.exhausted()


def _all_graphs(count):
    pairs = [(i, j) for i in range(count) for j in range(i + 1, count)]
    for mask in range(1 << len(pairs)):
        yield list(range(count)), [[a, b] for bit, (a, b) in enumerate(pairs)
                                   if mask >> bit & 1]


def test_reference_bipartite_matches_bfs_on_all_small_graphs():
    checked = 0
    for vertices, edges in itertools.chain(_all_graphs(1), _all_graphs(2),
                                           _all_graphs(3), _all_graphs(4),
                                           _all_graphs(5)):
        assert graph_reference.bipartite_by_exhaustion(vertices, edges) \
            == graphs.is_bipartite(vertices, edges)
        checked += 1
    assert checked == 1 + 2 + 8 + 64 + 1024


def test_reference_triangles_match_detector_on_all_small_graphs():
    checked = 0
    for vertices, edges in itertools.chain(_all_graphs(1), _all_graphs(2),
                                           _all_graphs(3), _all_graphs(4),
                                           _all_graphs(5)):
        Triples = graph_reference.triangles_by_triples(vertices, edges)
        assert (len(Triples) > 0) == graphs.has_triangle(vertices, edges)
        checked += 1
    assert checked == 1 + 2 + 8 + 64 + 1024


def _software_sequences():
    alphabet = [
        {"op": "set", "key": "a", "value": "v1"},
        {"op": "set", "key": "a", "value": "v2"},
        {"op": "get", "key": "a", "id": ""},
        {"op": "set", "key": "b", "value": "v1"},
        {"op": "get", "key": "b", "id": ""},
        {"op": "clear"},
        {"op": "del", "key": "a"},
    ]
    for length in (1, 2, 3):
        for combo in itertools.product(range(len(alphabet)), repeat=length):
            ops, counter = [], 0
            for pick in combo:
                entry = dict(alphabet[pick])
                if entry["op"] == "get":
                    entry = dict(entry, id="o%d" % counter)
                    counter += 1
                ops.append(entry)
            yield ops


def test_reference_interpreter_matches_on_exhaustive_small_cases():
    checked = 0
    for ops in _software_sequences():
        assert software.reference_run(ops) == software_reference.run_reference(ops)
        for fault in software.FAULTS:
            assert software.faulty_run(ops, fault) == \
                software_reference.run_faulty(ops, fault)
        checked += 1
    assert checked == 7 + 49 + 343
