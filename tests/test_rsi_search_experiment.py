from __future__ import annotations

import importlib.util
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from experiments.search06 import driver
from experiments.search06 import freeze as search_freeze
from rsi import search
from settlement.launcher_local import LocalLauncher


def test_direct_file_freeze_can_pin_live_software_without_inference(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(driver.HERE))
    spec = importlib.util.spec_from_file_location("p06_direct_freeze", driver.HERE / "freeze.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    executable = tmp_path / "fixture-codex"
    executable.write_bytes(b"fixture executable identity")
    monkeypatch.setattr(module, "CODEX", executable)

    software = module._software(driver.ROOT, "live")

    assert software == {"codex": {
        "path": str(executable.resolve()),
        "sha256": driver.sha(b"fixture executable identity"),
    }}


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


@pytest.mark.parametrize(("observation_status", "passed"), [("passed", True), ("failed", False)])
def test_prospective_use_requires_acknowledged_checked_outcome(observation_status, passed):
    observed = {"episode": "worker-1", "verdict": "check-1",
                "status": observation_status, "passed": passed}
    outcome = {"status": "acknowledged", "opportunity_id": "general",
               "acknowledgement": {"observation": observed}}
    state = {"status": "unresolved", "last_observation": observed}

    result = driver._prospective_use_result(outcome, state)
    assert result == {"status": "complete", "checked": True, "passed": passed,
                      "selected_opportunity": "general", "observation": observed}

    for incomplete in (
        {**outcome, "status": "pending"},
        {**outcome, "status": "deferred"},
        {**outcome, "opportunity_id": "unknown"},
    ):
        result = driver._prospective_use_result(incomplete, state)
        assert result["status"] == "unscored"
        assert result["checked"] is False
        assert result["passed"] is None


def test_candidate_screen_requires_comparable_incumbent_evidence():
    candidate = {"supported": 3, "gaps": 0, "stops": 0, "refusals": 0,
                 "passed": 2, "screening_cpu_units": 500, "screening_cpu_units_unknown": 0}
    incumbent = {"supported": 3, "gaps": 0, "stops": 0, "refusals": 0,
                 "passed": 2, "screening_cpu_units": 600, "screening_cpu_units_unknown": 0}
    assert driver._screen_eligibility(candidate, incumbent, 3, 1000)["eligible"] is True

    incomplete = {**incumbent, "supported": 2, "gaps": 1, "passed": 0}
    result = driver._screen_eligibility(candidate, incomplete, 3, 1000)
    assert result["eligible"] is False
    assert result["incumbent_coverage_all_frames"] is False
    assert result["no_worse_checked_quality"] is False

    unknown_cost = {**incumbent, "screening_cpu_units": None,
                    "screening_cpu_units_unknown": 1}
    result = driver._screen_eligibility(candidate, unknown_cost, 3, 1000)
    assert result["eligible"] is False
    assert result["incumbent_costs_known"] is False


def test_fixture_freeze_rejects_collection_and_source_drift_and_reuses_run_identity(tmp_path):
    root = tmp_path / "checkout"
    for relative in driver.SOURCE_PATHS:
        source = driver.ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    scenario_path = root / "experiments/search06/scenario.json"
    scenario = driver._scenario(scenario_path)
    collection = {
        "schema": "p06-collection/1", "run_id": "fixture-collection",
        "scenario_sha256": driver.sha(driver.canonical(scenario)),
        "frames": ["frame-1", "frame-2", "frame-3"],
        "branches": [f"branch-{index}" for index in range(6)],
        "policies": {"authored-restricted": {}, "authored-general": {}},
    }
    collection_path = tmp_path / "collection.json"
    freeze_path = tmp_path / "freeze.json"
    collection_path.write_text(json.dumps(collection), encoding="utf-8")

    frozen = search_freeze.freeze(
        root, freeze_path, collection_path, mode="fixture", scenario_path=scenario_path)
    verified = search_freeze.verify_freeze(
        root, freeze_path, collection_path, scenario_path=scenario_path)
    assert verified["live_plan"] == frozen["live_plan"]
    assert driver._claim_run(frozen, freeze_path,
                             Path(frozen["live_plan"]["run_output"])) == frozen["live_plan"]["run_id"]
    assert driver._claim_run(verified, freeze_path,
                             Path(frozen["live_plan"]["run_output"])) == frozen["live_plan"]["run_id"]
    assert len(frozen["live_plan"]["operations"]["construction"]) == 2
    assert len(frozen["live_plan"]["allocations"]["construction"]) == 2
    assert "agenda_deadline" not in frozen["live_plan"]
    assert frozen["caps"]["max_use_seconds"] == scenario["caps"]["max_use_seconds"]
    with pytest.raises(ValueError, match="frozen directory"):
        driver._claim_run(verified, freeze_path, tmp_path / "new-run")

    changed_collection = {**collection, "branches": [*collection["branches"], "new"]}
    collection_path.write_text(json.dumps(changed_collection), encoding="utf-8")
    with pytest.raises(ValueError, match="collection_sha256"):
        search_freeze.verify_freeze(
            root, freeze_path, collection_path, scenario_path=scenario_path)
    collection_path.write_text(json.dumps(collection), encoding="utf-8")
    source_path = root / "src/rsi/search.py"
    source_path.write_bytes(source_path.read_bytes() + b"\n# drift\n")
    with pytest.raises(ValueError, match="source_sha256"):
        search_freeze.verify_freeze(
            root, freeze_path, collection_path, scenario_path=scenario_path)


def test_agenda_use_window_starts_after_construction_and_survives_resume():
    construction_finished = datetime(2026, 10, 16, 12, 3, tzinfo=UTC)
    seconds = 180
    deadline = driver._agenda_use_deadline(
        None, seconds, now=construction_finished)

    assert datetime.fromisoformat(deadline) == construction_finished + timedelta(seconds=seconds)

    existing = {"charter": {"deadline": deadline}}
    resumed_later = driver._agenda_use_deadline(
        existing, seconds, now=construction_finished + timedelta(hours=1))
    assert resumed_later == deadline

    expired = "2026-10-16T11:00:00+00:00"
    assert driver._agenda_use_deadline(
        {"charter": {"deadline": expired}}, seconds,
        now=construction_finished) == expired


def test_constructor_accounting_comes_from_durable_prepared_operation(migrated_db, tmp_path):
    from settlement import broker

    roots = driver._roots(migrated_db, "durable-evidence", tokens=10_000, cpu=1_000)
    operation_id = "p06-accounting-prepared"
    payload = {"profile": "local-process", "argv": ["python", "-c", "pass"],
               "timeout_ms": 100, "max_output_bytes": 1024}
    prepared = broker.ensure_operation(
        migrated_db, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload=payload, allocation_id=roots["cpu"])
    assert prepared.code.value == "applied"
    assert not (tmp_path / "live-result.json").exists()

    assert driver._construction_admissions(migrated_db, [operation_id, "not-admitted"]) == 1
    evidence = driver._construction_evidence(migrated_db, [operation_id, "not-admitted"])
    assert evidence["admissions"] == 1
    assert evidence["reserved_units_known"] == prepared.data["exposure"]
    assert evidence["reserved_units_unknown"] == 0
    assert evidence["operations"][0]["dispatch_state"] == "prepared"
    assert evidence["operations"][0]["reservation"] == {
        "amount": prepared.data["exposure"], "state": "reserved"}
    assert evidence["operations"][0]["receipts"] == []
    assert evidence["operations"][1] == {
        "operation_id": "not-admitted", "found": False,
        "reservation": None, "receipts": []}
