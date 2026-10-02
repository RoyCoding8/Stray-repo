from __future__ import annotations

import hashlib
import json

import pytest

from experiments.ad01 import seeds, trajectory


def _member(capability_id: str, source: str) -> dict:
    return {
        "capability_id": capability_id,
        "family": "software",
        "authored": False,
        "method_source": source,
        "source_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "params": {"max_queries": 4},
    }


def _repertoire(members: list[dict]) -> dict:
    return {"campaign_id": "c1", "members": members, "queries": 0}


def _write(tmp_path, repertoire: dict):
    path = tmp_path / "repertoire.json"
    path.write_text(json.dumps(repertoire, sort_keys=True, indent=1) + "\n")
    return path


def test_acquired_member_may_not_claim_a_seed_capability_id(tmp_path):
    seed_id = seeds.SEED_CAPABILITIES[0]["capability_id"]
    path = _write(tmp_path, _repertoire([_member(seed_id, "def f(): return 1\n")]))

    with pytest.raises(ValueError, match="reserved seed capability id"):
        trajectory.load_repertoire(path)


def test_acquired_member_with_its_own_id_is_accepted(tmp_path):
    path = _write(tmp_path, _repertoire([_member("acquired-x", "def f(): return 1\n")]))

    repertoire = trajectory.load_repertoire(path)

    assert repertoire["members"][0]["capability_id"] == "acquired-x"


def test_authored_seed_member_is_unaffected_by_the_reservation(tmp_path):
    seed_id = seeds.SEED_CAPABILITIES[0]["capability_id"]
    member = _member(seed_id, "")
    member["authored"] = True
    member.pop("method_source")
    member.pop("source_digest")
    path = _write(tmp_path, _repertoire([member]))

    repertoire = trajectory.load_repertoire(path)

    assert repertoire["members"][0]["capability_id"] == seed_id


def test_run_member_reports_the_bytes_it_actually_executed(monkeypatch):
    import experiments.ad01.method_exec as method_exec

    acquired = _member("acquired-x", "ACQUIRED = 1\n")
    acquired["entry"] = "ENTRY"

    monkeypatch.setattr(
        method_exec, "run_member_out_of_process",
        lambda member, task, **kwargs: {
            "candidate": "out", "queries": 1, "operation_ids": ["op-1"]})
    result = trajectory._run_member(
        acquired, {"family": "software"}, max_queries=4)

    assert result["executed_source"] == "ACQUIRED = 1\n"


def test_seed_dispatch_reports_seed_bytes_not_a_member_claim(monkeypatch):
    seed_id = seeds.SEED_CAPABILITIES[0]["capability_id"]
    stolen = _member(seed_id, "STOLEN = 1\n")

    monkeypatch.setattr(
        seeds, "run_seed",
        lambda capability, task, **kwargs: {
            "candidate": "out", "queries": 1, "operation_ids": ["op-seed"]})
    result = trajectory._run_member(
        stolen, {"family": "software"}, max_queries=4)

    assert result["executed_source"] == seeds.SEED_CAPABILITIES[0]["method"]
    assert result["executed_source"] != "STOLEN = 1\n"
