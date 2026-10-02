"""RPR-01 splits: fixed-seed panels, controls, manifest, barrier, inventory."""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import checkers, graphs, software
from experiments.representation import splits

BASE = ROOT / "experiments" / "representation" / "fixtures"


def _read(path):
    return json.loads(Path(path).read_text())


def _panel_files(family, split):
    return sorted((BASE / family / split).glob("*.json"))


def test_split_counts_per_contract_section_7():
    for family in ("software", "graphs"):
        assert len(_panel_files(family, "development")) == 6
        assert len(_panel_files(family, "check")) == 4
        assert len(_panel_files(family, "evaluation")) == 8
    assert len(sorted((BASE / "controls").glob("*.json"))) == 4
    assert len(sorted((BASE / "use").glob("*.json"))) == 4


def test_generators_reproduce_committed_fixtures():
    for split in ("development", "check", "evaluation"):
        for index, path in enumerate(_panel_files("software", split)):
            assert _read(path) == splits.generate_software(split, index)
        for index, path in enumerate(_panel_files("graphs", split)):
            assert _read(path) == splits.generate_graph(split, index)
    disk = sorted((_read(p)["task_id"], _read(p))
                  for p in (BASE / "controls").glob("*.json"))
    fresh = sorted((t["task_id"], t) for t in splits.generate_controls())
    assert disk == fresh
    disk = sorted((_read(p)["task_id"], _read(p))
                  for p in (BASE / "use").glob("*.json"))
    fresh = sorted((t["task_id"], t) for t in splits.generate_use_panel())
    assert disk == fresh


def test_all_benefit_tasks_valid_within_caps():
    for family, check in (("software", software.task_is_valid),
                          ("graphs", graphs.witness_holds)):
        for split in ("development", "check", "evaluation"):
            for path in _panel_files(family, split):
                assert check(_read(path)), path.name


def test_both_faults_represented_in_development():
    faults = {splits.generate_software("development", i)["fault"]
              for i in range(6)}
    assert faults == {"stale-read", "stale-clear"}
    faults = {splits.generate_software("evaluation", i)["fault"]
              for i in range(8)}
    assert faults == {"stale-read", "stale-clear"}


def _shortest_odd_cycle(vertices, edges):
    table = {v: set() for v in vertices}
    for first, second in edges:
        table[first].add(second)
        table[second].add(first)
    best = None
    for root in vertices:
        dist = {root: 0}
        queue = deque([root])
        while queue:
            current = queue.popleft()
            for other in table[current]:
                if other not in dist:
                    dist[other] = dist[current] + 1
                    queue.append(other)
                elif dist[other] <= dist[current] and \
                        (dist[current] + dist[other] + 1) % 2 == 1:
                    length = dist[current] + dist[other] + 1
                    if best is None or length < best:
                        best = length
    return best


def test_graph_panel_spans_odd_lengths_with_c9_held_out():
    dev_lengths = {_shortest_odd_cycle(t["vertices"], t["edges"])
                   for t in (splits.generate_graph("development", i)
                             for i in range(6))}
    assert dev_lengths >= {5, 7}
    assert all(length in (5, 7) for length in dev_lengths)
    eva_lengths = {_shortest_odd_cycle(t["vertices"], t["edges"])
                   for t in (splits.generate_graph("evaluation", i)
                             for i in range(8))}
    assert 9 in eva_lengths


def test_controls_never_preserved():
    for path in sorted((BASE / "controls").glob("*.json")):
        task = _read(path)
        if task["family"] == "software":
            report = checkers.check_software(task, task)
        else:
            report = checkers.check_graph(task, task)
        assert report["verdict"] != "preserved", path.name


def test_use_panel_supported_valid_out_of_scope_refused():
    supported_sw = _read(BASE / "use" / "use-sw-supported.json")
    supported_gr = _read(BASE / "use" / "use-gr-supported.json")
    assert software.task_is_valid(supported_sw)
    assert graphs.witness_holds(supported_gr)
    oos_sw = _read(BASE / "use" / "use-sw-out-of-scope.json")
    oos_gr = _read(BASE / "use" / "use-gr-out-of-scope.json")
    assert len(oos_sw["ops"]) > software.MAX_OPS
    assert len(oos_gr["vertices"]) > graphs.MAX_VERTICES
    assert checkers.check_software(oos_sw, oos_sw)["verdict"] != "preserved"
    assert checkers.check_graph(oos_gr, oos_gr)["verdict"] != "preserved"


def test_manifest_verifies_and_detects_tamper(tmp_path):
    assert splits.verify_manifest(BASE) == []
    manifest = splits.write_fixtures(tmp_path)
    assert len(manifest["files"]) == 44
    assert splits.verify_manifest(tmp_path) == []
    first = tmp_path / manifest["files"][0]["path"]
    first.write_bytes(first.read_bytes() + b" ")
    assert splits.verify_manifest(tmp_path) != []


def test_graph_family_invisible_to_source_side():
    tokens = ("vert", "edge", "bipart", "triangle", "cycle", "graph")
    hits = []
    for path in sorted((BASE / "software").rglob("*.json")):
        text = path.read_text().lower()
        found = [token for token in tokens if token in text]
        if found:
            hits.append((path.name, found))
    assert hits == []


def test_inventory_matches_panel():
    inventory = json.loads(
        (ROOT / "experiments" / "representation" / "inventory.json").read_text())
    assert inventory["manifest"]["version"] == splits.MANIFEST_VERSION
    assert inventory["seeds"]["software"] == splits.SOFTWARE_SEEDS
    assert inventory["seeds"]["graphs"] == splits.GRAPH_SEEDS
    assert inventory["seeds"]["controls"] == splits.CONTROL_SEED
    assert inventory["seeds"]["use_panel"] == splits.USE_SEED
    assert inventory["fixture_counts"] == {
        "software": {"development": 6, "check": 4, "evaluation": 8},
        "graphs": {"development": 6, "check": 4, "evaluation": 8},
        "controls": 4, "use_panel": 4}
    assert (ROOT / "experiments" / "representation" / "INVENTORY.md").is_file()
