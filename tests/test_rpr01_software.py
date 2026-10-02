"""RPR-01 software family: interpreter semantics, faults and validity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import software
from experiments.representation.software import SoftwareInvalid

FIXTURES = ROOT / "experiments" / "representation" / "fixtures" / "software"


def test_reference_set_get_del_clear():
    ops = software.parse_ops([
        {"op": "set", "key": "a", "value": "v1"},
        {"op": "get", "key": "a", "id": "g0"},
        {"op": "del", "key": "a"},
        {"op": "get", "key": "a", "id": "g1"},
        {"op": "set", "key": "b", "value": "v2"},
        {"op": "clear"},
        {"op": "get", "key": "b", "id": "g2"},
    ])
    seen = software.reference_run(ops)
    assert seen["g0"] == {"type": "str", "value": "v1"}
    assert seen["g1"] == {"type": "missing", "value": None}
    assert seen["g2"] == {"type": "missing", "value": None}


def test_stale_read_after_overwrite():
    ops = software.parse_ops([
        {"op": "set", "key": "a", "value": "v1"},
        {"op": "set", "key": "a", "value": "v2"},
        {"op": "get", "key": "a", "id": "w"},
        {"op": "get", "key": "a", "id": "w2"},
    ])
    ref = software.reference_run(ops)
    bad = software.faulty_run(ops, "stale-read")
    assert ref["w"] == {"type": "str", "value": "v2"}
    assert bad["w"] == {"type": "str", "value": "v1"}
    assert bad["w2"] == {"type": "str", "value": "v2"}


def test_stale_read_consumed_once_and_cleared():
    ops = software.parse_ops([
        {"op": "set", "key": "a", "value": "v1"},
        {"op": "set", "key": "a", "value": "v2"},
        {"op": "clear"},
        {"op": "set", "key": "a", "value": "v3"},
        {"op": "get", "key": "a", "id": "w"},
    ])
    bad = software.faulty_run(ops, "stale-read")
    assert bad["w"] == {"type": "str", "value": "v3"}


def test_stale_state_after_clear():
    ops = software.parse_ops([
        {"op": "set", "key": "a", "value": "v1"},
        {"op": "set", "key": "b", "value": "v2"},
        {"op": "clear"},
        {"op": "get", "key": "a", "id": "wa"},
        {"op": "get", "key": "b", "id": "wb"},
    ])
    ref = software.reference_run(ops)
    bad = software.faulty_run(ops, "stale-clear")
    assert ref["wa"] == {"type": "missing", "value": None}
    assert bad["wb"] == {"type": "str", "value": "v2"}
    assert bad["wa"] == {"type": "missing", "value": None}


def test_parse_rejects_shapes():
    with pytest.raises(SoftwareInvalid):
        software.parse_ops([{"op": "set", "key": "zzz", "value": "v1"}])
    with pytest.raises(SoftwareInvalid):
        software.parse_ops([{"op": "frobnicate"}])
    with pytest.raises(SoftwareInvalid):
        software.parse_ops([{"op": "get", "key": "a", "id": "x"},
                            {"op": "get", "key": "b", "id": "x"}])
    with pytest.raises(SoftwareInvalid):
        software.parse_ops([{"op": "set", "key": "a", "value": "v1"}] * 25)


def test_tasks_are_data_files_never_programs():
    for path in sorted(FIXTURES.rglob("*.json")):
        text = path.read_text()
        raw = json.loads(text)
        assert isinstance(raw, dict)
        assert raw["family"] == "software"
        assert set(raw) == {"family", "task_id", "fault", "ops", "witness", "seed"}
        assert "def " not in text and "import " not in text


def test_committed_fixtures_valid_and_capped():
    files = sorted(FIXTURES.rglob("*.json"))
    assert len(files) == 18
    faults = set()
    for path in files:
        task = json.loads(path.read_text())
        assert software.task_is_valid(task), path.name
        assert len(task["ops"]) <= software.MAX_OPS
        faults.add(task["fault"])
        keys = {op.get("key") for op in task["ops"] if op.get("key")}
        assert len(keys) >= 2, path.name
    assert faults == {"stale-read", "stale-clear"}


def test_legal_deletion_is_subsequence():
    task = json.loads((FIXTURES / "development" / "sw-dev-00.json").read_text())
    ops = task["ops"]
    assert software.is_legal_deletion(ops, ops)
    assert software.is_legal_deletion(ops, ops[1:])
    assert software.is_legal_deletion(ops, [])
    assert not software.is_legal_deletion(ops, ops[::-1])
    forged = list(ops)
    forged.append({"op": "get", "key": "a", "id": "forged"})
    assert not software.is_legal_deletion(ops, forged)


def test_witness_identity_stable_through_deletion():
    task = json.loads((FIXTURES / "development" / "sw-dev-00.json").read_text())
    designated = task["witness"]["observation"]
    drop = 0 if task["ops"][0].get("id") != designated else 1
    kept = [op for i, op in enumerate(task["ops"]) if i != drop]
    surviving = [op.get("id") for op in kept if op.get("id") == designated]
    assert surviving == [designated]
    assert software.is_legal_deletion(task["ops"], kept)
    assert software.task_digest(task) == software.task_digest(dict(task))
