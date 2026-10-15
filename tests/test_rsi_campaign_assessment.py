from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fixtures.p10_campaign import ROOT, prepare_campaign
from rsi import archive, episode, gate, genome, verifier
from settlement import db
from settlement.launcher_codex import CodexLauncher, Provider


def _gate_args(case, gate_id):
    round_ = case["rounds"][0]
    return {
        "gate_id": gate_id,
        "epoch": round_["epoch"],
        "parent": round_["parent"],
        "candidate": round_["candidate"],
        "token_allocation": case["charter"]["allocations"]["tokens"]["id"],
        "cpu_allocation": case["charter"]["allocations"]["cpu"]["id"],
        "staging_root": case["run"]["roots"]["staging_root"],
        "artifacts_root": case["run"]["roots"]["artifacts_root"],
        "route_identity": round_["route_identity"],
    }


def test_infra_outcome_with_false_normalization_is_not_a_test_score():
    unknown = SimpleNamespace(
        operation_id="unknown-op",
        status="infra_failed",
        passed=False,
        detail={"parse": "typed-json", "data": {
            "worker": {"status": "error", "data": {
                "tests": 2, "failures": 0, "errors": 0, "skipped": 0,
            }},
        }},
    )
    assert gate._known_test_result("unused", unknown) is False


def test_truncated_or_timed_out_typed_output_is_not_a_test_score():
    for detail in (
        {"parse": "typed-json", "truncated": True, "data": {"timed_out": False}},
        {"parse": "typed-json", "truncated": False, "data": {"timed_out": True}},
    ):
        detail["data"]["worker"] = {"status": "error", "data": {
            "tests": 2, "failures": 0, "errors": 0, "skipped": 0,
        }}
        detail["_verdict"] = "failure"
        verdict = SimpleNamespace(
            operation_id="unknown-op", status="failed", passed=False, detail=detail,
        )
        assert gate._known_test_result("unused", verdict) is False

    malformed = SimpleNamespace(
        operation_id="unknown-op", status="failed", passed=False,
        detail={"parse": "typed-json", "truncated": False, "_verdict": "failure",
                "data": []},
    )
    assert gate._known_test_result("unused", malformed) is False


def test_unknown_gate_effect_remains_incomplete_and_reuses_original_operation(
    migrated_db, tmp_path
):
    case = prepare_campaign(migrated_db, tmp_path / "prepare", campaign_id="p10-infra", round_count=1)
    infra_agent = CodexLauncher(
        tmp_path / "infra-runs",
        codex_cmd=[sys.executable, str(ROOT / "tests" / "fixtures" / "fake_codex.py"), "infra"],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=frozenset(),
    )
    kwargs = _gate_args(case, "p10-recoverable-gate")
    first = gate.run(migrated_db, infra_agent, case["run"]["checker"], **kwargs)
    assert first["disposition"] == "incomplete"
    assert archive.decision(migrated_db, "gate:p10-recoverable-gate") is None
    with db.read_connect(migrated_db) as conn:
        operation_ids = [row[0] for row in conn.execute(
            "SELECT id FROM operations WHERE id LIKE 'rsi-gate-%' ORDER BY id").fetchall()]
    assert len(operation_ids) == 1

    again = gate.run(migrated_db, infra_agent, case["run"]["checker"], **kwargs)
    assert again["disposition"] == "incomplete"
    with db.read_connect(migrated_db) as conn:
        replayed_ids = [row[0] for row in conn.execute(
            "SELECT id FROM operations WHERE id LIKE 'rsi-gate-%' ORDER BY id").fetchall()]
    assert replayed_ids == operation_ids
    assert archive.decision(migrated_db, "gate:p10-recoverable-gate") is None


def test_known_failed_pristine_test_remains_a_gate_task_result(migrated_db, tmp_path):
    case = prepare_campaign(migrated_db, tmp_path / "prepare", campaign_id="p10-known-fail", round_count=1)
    report = gate.run(
        migrated_db, case["run"]["agent"], case["run"]["checker"],
        **_gate_args(case, "p10-known-failure-gate"),
    )
    parent_result, candidate_result = report["phases"]["val"]
    assert (parent_result["status"], parent_result["passed"]) == ("failed", False)
    assert (candidate_result["status"], candidate_result["passed"]) == ("passed", True)
    assert report["disposition"] == "quarantine"
    assert archive.decision(migrated_db, "gate:p10-known-failure-gate")["data"] == report


def test_gate_exports_the_exact_historical_parent_checks_used_for_regression(
    migrated_db, tmp_path
):
    case = prepare_campaign(migrated_db, tmp_path / "prepare", campaign_id="p10-baseline", round_count=1)
    roots = case["run"]["roots"]
    parent = genome.Genome({"AGENTS.md": b"Implement add."})
    candidate = genome.Genome({"AGENTS.md": b"Implement add.", "meta/note.md": b"child"})
    genome.publish(migrated_db, parent, parent=None, origin="baseline-test", **roots)
    genome.publish(migrated_db, candidate, parent=parent.digest, origin="baseline-test", **roots)
    task_ = case["tasks"]["development"]
    episode_id = "p10-baseline-parent"
    prior = episode.run_episode(
        migrated_db, case["run"]["agent"], parent, operation_id=episode_id,
        task=task_, allocation_id=case["charter"]["allocations"]["tokens"]["id"],
        attempt_id=None, token_ceiling=5_000, timeout_ms=30_000,
        staging_root=roots["staging_root"], artifacts_root=roots["artifacts_root"],
    )
    checked = verifier.verify_episode(
        migrated_db, case["run"]["agent"], case["run"]["checker"], prior.operation_id,
        allocation_id=case["charter"]["allocations"]["cpu"]["id"], attempt_id=None,
        staging_root=roots["staging_root"], artifacts_root=roots["artifacts_root"],
    )
    assert checked.status == "passed" and checked.passed is True

    kwargs = _gate_args(case, "p10-baseline-gate")
    kwargs.update(parent=parent.digest, candidate=candidate.digest)
    report = gate.run(migrated_db, case["run"]["agent"], case["run"]["checker"], **kwargs)
    assert episode_id in {item["episode"] for item in report["regression_baseline"]}
    assert task_.digest in {item["task"] for item in report["phases"]["regression"]}
    saved = archive.decision(migrated_db, "gate-baseline:p10-baseline-gate")
    assert saved["data"]["checks"] == report["regression_baseline"]
