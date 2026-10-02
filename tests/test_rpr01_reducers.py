"""RPR-01 baseline reducers: ddmin and domain-aware greedy on both families."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import checkers, reducers
from experiments.representation.checkers import GRAPH_REASONS, SOFTWARE_REASONS

SW = ROOT / "experiments" / "representation" / "fixtures" / "software"
GR = ROOT / "experiments" / "representation" / "fixtures" / "graphs"
CT = ROOT / "experiments" / "representation" / "fixtures" / "controls"

SW_PAIR = ["development/sw-dev-00.json", "development/sw-dev-01.json"]
GR_PAIR = ["development/gr-dev-00.json", "development/gr-dev-02.json"]


def _load(directory, name):
    return json.loads((directory / name).read_text())


@pytest.mark.parametrize("name", SW_PAIR)
@pytest.mark.parametrize("method", ["ddmin", "greedy"])
def test_software_reducers_preserve_and_shrink(name, method):
    task = _load(SW, name)
    oracle = checkers.SoftwareOracle(task, max_queries=64)
    result = reducers.reduce_software(task, oracle, method=method,
                                      max_queries=64)
    report = checkers.check_software(task, result["candidate"])
    assert report["verdict"] == "preserved"
    assert len(result["candidate"]["ops"]) < len(task["ops"])
    assert result["queries"] <= 64
    assert result["status"] == "locally-irreducible"
    designated = task["witness"]["observation"]
    assert any(op.get("id") == designated for op in result["candidate"]["ops"])
    for entry in oracle.history:
        assert entry["reason"] in SOFTWARE_REASONS


@pytest.mark.parametrize("name", GR_PAIR)
@pytest.mark.parametrize("method", ["ddmin", "greedy"])
def test_graph_reducers_preserve_and_shrink(name, method):
    task = _load(GR, name)
    oracle = checkers.GraphOracle(task, max_queries=64)
    result = reducers.reduce_graph(task, oracle, method=method, max_queries=64)
    report = checkers.check_graph(task, result["candidate"])
    assert report["verdict"] == "preserved"
    before = len(task["vertices"]) + len(task["edges"])
    after = len(result["candidate"]["vertices"]) + len(result["candidate"]["edges"])
    assert after < before
    assert result["queries"] <= 64
    assert set(result["candidate"]["vertices"]) <= set(task["vertices"])
    for entry in oracle.history:
        assert entry["reason"] in GRAPH_REASONS


def test_reducers_use_only_legal_operations():
    task = _load(SW, SW_PAIR[0])
    oracle = checkers.SoftwareOracle(task, max_queries=64)
    reducers.reduce_software(task, oracle, method="ddmin", max_queries=64)
    for entry in oracle.history:
        assert entry["verdict"] in ("preserved", "not_preserved", "unknown")
        assert entry["reason"] not in ("invalid-candidate", "illegal-deletion",
                                       "task-mismatch")
    graph = _load(GR, GR_PAIR[0])
    g_oracle = checkers.GraphOracle(graph, max_queries=64)
    reducers.reduce_graph(graph, g_oracle, method="ddmin", max_queries=64)
    for entry in g_oracle.history:
        assert entry["verdict"] in ("preserved", "not_preserved", "unknown")
        assert entry["reason"] not in ("invalid-candidate", "illegal-subgraph",
                                       "task-mismatch")


def test_reducers_stop_at_budget_keep_incumbent():
    task = _load(SW, SW_PAIR[0])
    oracle = checkers.SoftwareOracle(task, max_queries=2)
    result = reducers.reduce_software(task, oracle, method="greedy",
                                      max_queries=2)
    assert result["queries"] <= 2
    assert result["status"] in ("budget-exhausted", "locally-irreducible")
    assert checkers.check_software(task, result["candidate"])["verdict"] \
        == "preserved"


def test_reducers_refuse_invalid_start():
    task = json.loads((CT / "ctrl-sw-wrong-obs.json").read_text())
    oracle = checkers.SoftwareOracle(task, max_queries=16)
    result = reducers.reduce_software(task, oracle, method="greedy",
                                      max_queries=16)
    assert result["status"] == "initial-not-preserved"
    assert result["kept"] == list(range(len(task["ops"])))


def test_reducers_reject_unknown_method():
    task = _load(SW, SW_PAIR[0])
    oracle = checkers.SoftwareOracle(task)
    with pytest.raises(ValueError):
        reducers.reduce_software(task, oracle, method="nope")
    with pytest.raises(ValueError):
        reducers.reduce_graph(_load(GR, GR_PAIR[0]), oracle, method="nope")
