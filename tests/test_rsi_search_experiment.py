from __future__ import annotations

import json

from experiments.search06 import driver
from rsi import search
from settlement.launcher_local import LocalLauncher


def test_collector_screens_identical_supported_corpus_and_recomputes_offline(
    migrated_db, tmp_path, monkeypatch
):
    collection_dir = tmp_path / "collection"
    collection = driver.collect(migrated_db, collection_dir)

    assert collection["schema"] == "p06-collection/1"
    assert len(collection["frames"]) == 3
    assert len(collection["branches"]) == 6
    assert collection["costs"]["model_admissions"] == 0
    marker = collection["private_result_evidence"]["protected_future_marker"]
    for digest in collection["frames"]:
        frame = search.load_frame(
            migrated_db, digest,
            artifacts_root=collection_dir / "collection-runtime" / "art")
        assert len(frame["starts"]) == 3
        assert marker not in json.dumps(frame["visible"], sort_keys=True)

    screening = driver.screen(
        migrated_db, collection_dir / "collection.json", tmp_path / "screen",
        checker=LocalLauncher(tmp_path / "screen" / "policy-runs"))
    restricted = screening["evaluations"]["authored-restricted"]["evaluation"]
    general = screening["evaluations"]["authored-general"]["evaluation"]
    assert restricted["frames"] == general["frames"] == collection["frames"]
    assert restricted["branches"] == general["branches"] == collection["branches"]
    assert [row["selected"] for row in restricted["results"]] == [
        "restricted", "restricted", "restricted"]
    assert [row["selected"] for row in general["results"]] == [
        "general", "general", "general"]
    assert restricted["results"][0]["quality"]["passed"] is True
    assert restricted["results"][1]["quality"]["passed"] is False
    assert general["results"][1]["quality"]["passed"] is True
    assert all(row["branch_status"] == "supported" for row in restricted["results"])
    assert all((row["continuation_query"] or {}).get("status") == "gap"
               for row in general["results"])
    assert all(marker not in json.dumps(row.get("policy_output"), sort_keys=True)
               for row in general["results"])

    monkeypatch.delenv("SETTLEMENT_TEST_DSN", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_ENDPOINT", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_MODEL", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_KEY", raising=False)
    bundle_path = tmp_path / "screen" / "screening.json"
    offline_path = tmp_path / "offline.json"
    offline = driver.recompute(bundle_path, offline_path)
    assert offline["evaluations"]["authored-general"] == general["recomputed"]
    assert json.loads(offline_path.read_text(encoding="utf-8")) == offline


def test_constructor_stop_distinguishes_unusable_response_from_unresolved_effect():
    assert driver._construction_action({"status": "invalid"}) == "repair"
    assert driver._construction_action({"status": "completed", "child": "digest"}) == "screen"
    assert driver._construction_action({"status": "timeout"}) == "stop-unscored"
    assert driver._construction_action({"status": "unresolved"}) == "stop-unscored"


def test_offline_live_accounting_preserves_both_attempts_without_scoring(tmp_path, monkeypatch):
    monkeypatch.delenv("SETTLEMENT_TEST_DSN", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_ENDPOINT", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_MODEL", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_KEY", raising=False)
    ids = ["run-construct-0", "run-construct-1"]
    bundle = {
        "schema": "p06-live-result/1", "status": "unscored",
        "construction_operation_ids": ids, "admissions": 1,
        "construction_attempts": [{"operation_id": ids[0], "status": "timeout"}],
        "construction_accounting": {
            "admissions": 1, "reserved_units_known": 400_000,
            "reserved_units_unknown": 0,
            "operations": [
                {"operation_id": ids[0], "found": True,
                 "dispatch_state": "observed", "reconcile_state": "none",
                 "settled": True, "reservation": {"amount": 400_000, "state": "settled"},
                 "receipts": [{"receipt_identity": "fixture-receipt", "outcome": "failure"}]},
                {"operation_id": ids[1], "found": False, "receipts": []},
            ],
        },
    }
    expected = {
        "operation_ids": ids, "admissions": 1,
        "reserved_units_known": 400_000, "reserved_units_unknown": 0,
        "attempts": [{"operation_id": ids[0], "status": "timeout"}],
        "outcomes": [
            {"operation_id": ids[0], "dispatch_state": "observed",
             "reconcile_state": "none", "settled": True,
             "receipt_outcomes": ["failure"],
             "reservation": {"amount": 400_000, "state": "settled"}},
            {"operation_id": ids[1], "dispatch_state": None,
             "reconcile_state": None, "settled": None,
             "receipt_outcomes": [], "reservation": None},
        ],
    }
    assert driver._recompute_construction_accounting(bundle) == expected
    bundle_path, output_path = tmp_path / "live.json", tmp_path / "offline.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    report = driver.recompute(bundle_path, output_path)
    assert report["quality"] == "unscored"
    assert report["evaluations"] == {}
    assert report["construction_accounting"] == expected
