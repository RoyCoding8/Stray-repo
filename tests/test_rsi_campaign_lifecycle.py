from __future__ import annotations

import hashlib
import json

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Json
from test_rsi_agenda import _charter, _grant
from test_rsi_agenda_recovery import _child_wake
from test_rsi_investigate import _scenario, _worker_calls

from rsi import agenda, archive, investigation
from settlement import db, store
from settlement.common import Command, ResultCode, SettlementError, StaleRevision


def _create(migrated_db, tmp_path, agenda_id="p10-lifecycle", *, campaign=False):
    run = _scenario(migrated_db, tmp_path / "p01", agenda_id, "pass-first")
    run["scenario"] = "pass-first"
    charter = _charter(run, agenda_id=agenda_id)
    if campaign:
        charter["assessment_protocol"] = "a" * 64
    _grant(migrated_db, charter, agenda_id)
    agenda.create(migrated_db, agenda_id=agenda_id, charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    return run, charter


def _assignment(dsn, agenda_id, gate_id, round_id="round-1"):
    assignment_id = "p10-assignment-" + hashlib.sha256(
        f"{agenda_id}:{round_id}".encode()).hexdigest()
    state = agenda.read(dsn, agenda_id)
    data = {"agenda_id": agenda_id, "agenda_revision": state["revision"],
            "round_id": round_id, "gate_id": gate_id}
    payload = {"agenda_id": agenda_id, "revision": state["revision"], **data}

    def admit(cur, control):
        cur.execute("SELECT revision,status FROM rsi_agendas WHERE agenda_id=%s FOR UPDATE",
                    (agenda_id,))
        current = cur.fetchone()
        if (current is None or int(current["revision"]) != int(state["revision"])
                or current["status"] not in {"active", "complete"}):
            raise StaleRevision("agenda changed before assessment assignment")
        cur.execute("INSERT INTO rsi_decisions (id,kind,actor,subject,data)"
                    " VALUES (%s,'p10.assessment.assignment','fixed',%s,%s)",
                    (assignment_id, agenda_id, Json(data)))
        cur.execute("UPDATE rsi_agendas SET revision=revision+1,updated_at=now()"
                    " WHERE agenda_id=%s", (agenda_id,))
        return (ResultCode.APPLIED, "assessment assignment admitted", data,
                [("rsi.decision", {"id": assignment_id, "kind":
                                     "p10.assessment.assignment", "subject": agenda_id,
                                     "data": data})], [])

    result = store.transact(
        dsn, Command(request_id="p10-test-assignment:" + assignment_id,
                     payload=payload), admit)
    assert result.code == ResultCode.APPLIED
    return assignment_id, data


def test_controls_are_revisioned_idempotent_and_terminal(migrated_db, tmp_path):
    run, _ = _create(migrated_db, tmp_path)
    agenda_id = "p10-lifecycle"

    suspended = agenda.control(migrated_db, agenda_id, 0, "suspend")
    assert {key: suspended[key] for key in ("action", "status", "revision")} == {
        "action": "suspend", "status": "suspended", "revision": 1}
    assert agenda.control(migrated_db, agenda_id, 0, "suspend") == suspended
    with pytest.raises(StaleRevision):
        agenda.control(migrated_db, agenda_id, 0, "stop")
    with pytest.raises(SettlementError, match="action"):
        agenda.control(migrated_db, agenda_id, 1, "pause")

    resumed = agenda.control(migrated_db, agenda_id, 1, "resume")
    assert {key: resumed[key] for key in ("action", "status", "revision")} == {
        "action": "resume", "status": "active", "revision": 2}
    stopped = agenda.control(migrated_db, agenda_id, 2, "stop")
    assert {key: stopped[key] for key in ("action", "status", "revision")} == {
        "action": "stop", "status": "stopped", "revision": 3}
    assert agenda.wake(migrated_db, run["agent"], run["checker"], agenda_id,
                       staging_root=run["roots"]["staging_root"],
                       artifacts_root=run["roots"]["artifacts_root"])["status"] == "stopped"
    assert agenda.read(migrated_db, agenda_id)["flight"] is None
    assert _worker_calls(run["worker_log"]) == []
    controls = [decision for decision in agenda.export(
        migrated_db, agenda_id)["decisions"]
                if decision["kind"] == "p10.lifecycle.control"]
    assert len(controls) == 3
    assert {decision["data"]["action"] for decision in controls} == {
        "suspend", "resume", "stop"}


@pytest.mark.parametrize(("action", "expected_status"), [
    ("suspend", "suspended"),
    ("stop", "stopped"),
])
def test_controlled_pending_flight_survives_restart_without_dispatch(
    migrated_db, tmp_path, action, expected_status
):
    run, _ = _create(migrated_db, tmp_path, agenda_id="p10-restart-" + action)
    agenda_id = "p10-restart-" + action

    crashed = _child_wake(run, agenda_id, "crash-after-choice")
    assert crashed.returncode == 17, crashed.stderr
    before = agenda.read(migrated_db, agenda_id)
    assert before["flight"] is not None
    assert _worker_calls(run["worker_log"]) == []

    agenda.control(migrated_db, agenda_id, before["revision"], action)
    restarted = _child_wake(run, agenda_id, "resume")
    assert restarted.returncode == 0, restarted.stderr
    assert json.loads(restarted.stdout)["status"] == expected_status
    after = agenda.read(migrated_db, agenda_id)
    assert after["status"] == expected_status
    assert after["flight"] == before["flight"]
    assert _worker_calls(run["worker_log"]) == []
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


@pytest.mark.parametrize(("action", "expected_status"), [
    ("suspend", "suspended"),
    ("stop", "stopped"),
])
def test_acknowledgement_preserves_control_committed_after_verified_work(
    migrated_db, tmp_path, monkeypatch, action, expected_status
):
    agenda_id = "p10-ack-" + action
    run, _ = _create(migrated_db, tmp_path, agenda_id=agenda_id)
    original = agenda._ack_evidence

    def control_after_evidence(dsn, flight):
        evidence = original(dsn, flight)
        if evidence is not None:
            state = agenda.read(dsn, agenda_id)
            agenda.control(dsn, agenda_id, state["revision"], action)
        return evidence

    monkeypatch.setattr(agenda, "_ack_evidence", control_after_evidence)
    result = agenda.wake(
        migrated_db, run["agent"], run["checker"], agenda_id,
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])

    assert result["status"] == "acknowledged"
    after = agenda.read(migrated_db, agenda_id)
    assert after["status"] == expected_status
    assert after["flight"] is None
    assert after["turns"] == 1
    assert _worker_calls(run["worker_log"])


def test_control_winning_before_choice_prevents_flight_admission(
    migrated_db, tmp_path, monkeypatch
):
    agenda_id = "p10-choice-control-race"
    run, _ = _create(migrated_db, tmp_path, agenda_id=agenda_id)
    original = agenda._commit_choice

    def suspend_before_commit(dsn, current_id, state, snapshot, choice):
        agenda.control(dsn, current_id, state["revision"], "suspend")
        return original(dsn, current_id, state, snapshot, choice)

    monkeypatch.setattr(agenda, "_commit_choice", suspend_before_commit)
    result = agenda._wake(
        migrated_db, run["agent"], run["checker"], agenda_id,
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])

    assert result["status"] == "stale"
    state = agenda.read(migrated_db, agenda_id)
    assert state["status"] == "suspended"
    assert state["flight"] is None
    assert not [decision for decision in agenda.export(
        migrated_db, agenda_id)["decisions"] if decision["kind"] == "p05.choice"]
    assert _worker_calls(run["worker_log"]) == []


def test_public_wake_refuses_campaign_owned_agenda_before_effects(migrated_db, tmp_path):
    agenda_id = "p10-public-wake"
    run, _ = _create(migrated_db, tmp_path, agenda_id=agenda_id, campaign=True)

    with pytest.raises(SettlementError, match="campaign"):
        agenda.wake(
            migrated_db, run["agent"], run["checker"], agenda_id,
            staging_root=run["roots"]["staging_root"],
            artifacts_root=run["roots"]["artifacts_root"])

    state = agenda.read(migrated_db, agenda_id)
    assert state["flight"] is None
    assert agenda.export(migrated_db, agenda_id)["decisions"] == []
    assert _worker_calls(run["worker_log"]) == []
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_pending_assignment_blocks_campaign_lane_development_admission(
    migrated_db, tmp_path
):
    agenda_id = "p10-assignment-block"
    run, _ = _create(migrated_db, tmp_path, agenda_id=agenda_id, campaign=True)
    assignment_id, assignment = _assignment(migrated_db, agenda_id, "gate-pending")

    with db.connect(migrated_db) as conn, conn.cursor(row_factory=dict_row) as cur:
        pending = agenda._pending_assessment(cur, agenda_id)
    assert pending["id"] == assignment_id
    assert pending["data"] == assignment

    result = agenda._wake(
        migrated_db, run["agent"], run["checker"], agenda_id,
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])
    state = agenda.read(migrated_db, agenda_id)
    assert result["status"] == "stale"
    assert state["flight"] is None

    p01 = investigation.read(migrated_db, run["state"]["investigation_id"])
    choice = {"id": "first", "investigation_id": run["state"]["investigation_id"],
              "target_revision": p01["revision"], "ranked": [], "rank_reason": "test"}
    current = agenda.read(migrated_db, agenda_id)
    snapshot = agenda._source_snapshot(migrated_db, current)
    assert agenda._commit_choice(migrated_db, agenda_id, current, snapshot, choice) is None

    assert not [decision for decision in agenda.export(
        migrated_db, agenda_id)["decisions"] if decision["kind"] == "p05.choice"]
    assert any(decision["id"] == assignment_id for decision in agenda.export(
        migrated_db, agenda_id)["decisions"])
    assert _worker_calls(run["worker_log"]) == []
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_pending_assignment_clears_only_after_matching_final_gate_decision(
    migrated_db, tmp_path
):
    agenda_id = "p10-assignment-gate-final"
    _create(migrated_db, tmp_path, agenda_id=agenda_id, campaign=True)
    assignment_id, _ = _assignment(migrated_db, agenda_id, "gate-final")

    with db.connect(migrated_db) as conn, conn.cursor(row_factory=dict_row) as cur:
        assert agenda._pending_assessment(cur, agenda_id)["id"] == assignment_id

    archive.record(
        migrated_db, "gate:gate-final", kind="gate", actor="fixed",
        subject="candidate", data={"gate_id": "gate-final", "disposition": "pass"})
    with db.connect(migrated_db) as conn, conn.cursor(row_factory=dict_row) as cur:
        assert agenda._pending_assessment(cur, agenda_id) is None
