from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from test_rsi_agenda import _charter, _grant
from test_rsi_investigate import _child_env, _scenario, _worker_calls

from rsi import agenda, investigate
from settlement import broker

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fixtures" / "fake_investigate.py"
RESUME_CHILD = ROOT / "tests" / "fixtures" / "p05_resume.py"


def _child_wake(run, agenda_id, mode):
    return subprocess.run(
        [sys.executable, str(RESUME_CHILD), mode, agenda_id,
         str(run["worker_log"].parent), str(FAKE), run["scenario"]],
        check=False,
        cwd=ROOT,
        env=_child_env(run["dsn"]),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_independent_wakes_share_one_choice_and_one_child_effect(migrated_db, tmp_path):
    """RED regression: separate wakes must not dispatch the pinned P01 effect twice."""
    run = _scenario(migrated_db, tmp_path / "p01", "p05-concurrent", "pass-first")
    run["scenario"] = "pass-first"
    agenda_id = "p05-concurrent"
    charter = _charter(run, agenda_id=agenda_id)
    _grant(migrated_db, charter, agenda_id)
    agenda.create(migrated_db, agenda_id=agenda_id, charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    start = Barrier(2)

    def wake():
        start.wait(timeout=10)
        return agenda.wake(
            migrated_db, run["agent"], run["checker"], agenda_id,
            staging_root=run["roots"]["staging_root"],
            artifacts_root=run["roots"]["artifacts_root"],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=60) for future in
                   [pool.submit(wake), pool.submit(wake)]]

    assert all(result["status"] in {"acknowledged", "complete", "pending"}
               for result in results)
    exported = agenda.export(migrated_db, agenda_id)
    assert [item["kind"] for item in exported["decisions"]] == [
        "p05.choice", "p05.ack"]
    assert exported["agenda"]["flight"] is None
    assert exported["agenda"]["turns"] == 1
    history = investigate.export(migrated_db, "p05-concurrent")
    workers = [item for item in history["decisions"] if item["kind"] == "worker"]
    assert len(workers) == 1
    assert history["observations"][0]["content"]["passed"] is True
    calls = _worker_calls(run["worker_log"])
    operation = (broker.read_operation(migrated_db, calls[0]["operation_id"])
                 if calls else None)
    operation_snapshot = None if operation is None else {
        "dispatch_state": operation["dispatch_state"],
        "reconcile_state": operation["reconcile_state"],
        "settled": operation["settled"],
        "reservation_id": operation["reservation_id"],
        "dispatch_generation": operation["payload"].get("_dispatch_generation"),
        "receipt_actual_cost": operation["payload"].get("_receipt_actual_cost"),
    }
    child_calls = [{key: call[key] for key in ("call", "operation_id", "prior_solution")}
                   for call in calls]
    assert len(calls) == 1, (
        f"child invocations={child_calls!r}; operation={operation_snapshot!r}")


def test_fresh_process_resumes_choice_before_p01_creation(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-unused", "pass-first")
    run["scenario"] = "pass-first"
    agenda_id = "p05-choice-replay"
    charter = _charter(run, agenda_id=agenda_id)
    del charter["opportunities"][0]["investigation_id"]
    _grant(migrated_db, charter, agenda_id)
    agenda.create(migrated_db, agenda_id=agenda_id, charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    crashed = _child_wake(run, agenda_id, "crash-after-choice")
    assert crashed.returncode == 17, crashed.stderr
    before = agenda.export(migrated_db, agenda_id)
    choice, = before["decisions"]
    flight = before["agenda"]["flight"]
    assert choice["kind"] == "p05.choice"
    assert flight["choice_id"] == choice["id"]
    assert investigate.read(migrated_db, flight["investigation_id"]) is None
    assert _worker_calls(run["worker_log"]) == []

    resumed = _child_wake(run, agenda_id, "resume")
    assert resumed.returncode == 0, resumed.stderr
    result = json.loads(resumed.stdout)
    after = agenda.export(migrated_db, agenda_id)

    assert result["status"] == "acknowledged"
    assert result["acknowledgement"]["observation"]["passed"] is True
    assert after["decisions"][0]["data"] == choice["data"]
    assert [item["kind"] for item in after["decisions"]] == [
        "p05.choice", "p05.ack"]
    assert after["agenda"]["flight"] is None
    assert after["agenda"]["turns"] == 1
    assert investigate.read(migrated_db, flight["investigation_id"])["status"] == "completed"
    assert len(_worker_calls(run["worker_log"])) == 1


def test_fresh_process_acknowledges_failed_ready_observation_before_next_choice(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-failed-ready", "repair-after-feedback")
    run["scenario"] = "repair-after-feedback"
    agenda_id = "p05-ack-replay"
    charter = _charter(run, agenda_id=agenda_id, max_turns=2)
    _grant(migrated_db, charter, agenda_id)
    agenda.create(migrated_db, agenda_id=agenda_id, charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    crashed = _child_wake(run, agenda_id, "crash-before-ack")
    assert crashed.returncode == 17, crashed.stderr
    before = agenda.export(migrated_db, agenda_id)
    choice, = before["decisions"]
    flight = before["agenda"]["flight"]
    observed = investigate.read(migrated_db, "p05-failed-ready")
    p01_history = investigate.export(migrated_db, "p05-failed-ready")
    worker_decision, = p01_history["decisions"]
    observation, = p01_history["observations"]

    assert choice["kind"] == "p05.choice"
    assert flight["choice_id"] == choice["id"]
    assert observed["status"] == "ready"
    assert observation["content"]["passed"] is False
    assert len(_worker_calls(run["worker_log"])) == 1

    resumed = _child_wake(run, agenda_id, "resume")
    assert resumed.returncode == 0, resumed.stderr
    result = json.loads(resumed.stdout)
    after_ack = agenda.export(migrated_db, agenda_id)

    assert result["status"] == "acknowledged"
    assert result["investigation"]["last_observation"] == observation["content"]
    assert result["acknowledgement"]["decision_id"] == worker_decision["id"]
    assert result["acknowledgement"]["observation"] == observation["content"]
    assert after_ack["decisions"][0]["data"] == choice["data"]
    assert [item["kind"] for item in after_ack["decisions"]] == [
        "p05.choice", "p05.ack"]
    assert after_ack["agenda"]["flight"] is None
    assert len(_worker_calls(run["worker_log"])) == 1

    next_result = agenda.wake(
        migrated_db, run["agent"], run["checker"], agenda_id,
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"],
    )
    final = agenda.export(migrated_db, agenda_id)
    assert next_result["status"] == "acknowledged"
    assert next_result["investigation"]["status"] == "completed"
    assert [item["kind"] for item in final["decisions"]] == [
        "p05.choice", "p05.ack", "p05.choice", "p05.ack"]
    assert final["decisions"][2]["data"]["target_revision"] == observed["revision"]
    assert len(_worker_calls(run["worker_log"])) == 2
