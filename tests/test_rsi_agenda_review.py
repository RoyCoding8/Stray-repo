from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from test_rsi_agenda import _charter, _grant
from test_rsi_investigate import _scenario, _worker_calls

from rsi import agenda, investigation, task
from settlement import broker, store
from settlement.common import Command


def test_zero_turn_deferral_rechecks_restored_source_without_audit_growth(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path / "restore", "review-restore", "pass-first")
    charter = _charter(run)
    _grant(migrated_db, charter)
    agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    root = run["roots"]["artifacts_root"]
    hidden = root.with_name("hidden-artifacts")
    root.rename(hidden)
    try:
        first = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                            **run["roots"])
        assert first["status"] == "deferred"
        audit_count = len(agenda.export(migrated_db, "p05-one")["decisions"])
        repeated = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                               **run["roots"])
        assert repeated["status"] == "deferred"
        assert len(agenda.export(migrated_db, "p05-one")["decisions"]) == audit_count
    finally:
        hidden.rename(root)

    event_epoch = store.get_control(migrated_db)["event_epoch"]
    assert task.load(migrated_db, root, run["candidate"].digest).digest == run["candidate"].digest
    assert store.get_control(migrated_db)["event_epoch"] == event_epoch
    resumed = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                          **run["roots"])

    assert resumed["status"] == "acknowledged", resumed
    assert agenda.read(migrated_db, "p05-one")["turns"] == 1
    assert len(_worker_calls(run["worker_log"])) == 1


def test_acknowledged_agenda_rechecks_catalogue_after_later_deferral(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "later-restore", "review-later-restore",
                    "repair-after-feedback")
    charter = _charter(run, max_turns=3)
    _grant(migrated_db, charter)
    agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    first = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                        **run["roots"])
    assert first["status"] == "acknowledged", first
    root = run["roots"]["artifacts_root"]
    hidden = root.with_name("hidden-artifacts")
    root.rename(hidden)
    try:
        deferred = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                               **run["roots"])
        assert deferred["status"] == "deferred"
    finally:
        hidden.rename(root)

    event_epoch = store.get_control(migrated_db)["event_epoch"]
    assert task.load(migrated_db, root, run["candidate"].digest).digest == run["candidate"].digest
    assert store.get_control(migrated_db)["event_epoch"] == event_epoch
    resumed = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                          **run["roots"])

    assert resumed["status"] == "acknowledged", resumed
    assert agenda.read(migrated_db, "p05-one")["turns"] == 2
    assert len(_worker_calls(run["worker_log"])) == 2

    capped = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                         **run["roots"])
    assert capped["status"] == "deferred"
    audit_count = len(agenda.export(migrated_db, "p05-one")["decisions"])
    repeated = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                           **run["roots"])
    assert repeated["status"] == "deferred"
    assert len(agenda.export(migrated_db, "p05-one")["decisions"]) == audit_count


def test_zero_turn_deferral_rechecks_released_allocation_root(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "release", "review-release", "pass-first")
    charter = _charter(run)
    _grant(migrated_db, charter)
    agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    token_root = charter["allocations"]["tokens"]["id"]
    store.reserve(migrated_db, Command(request_id="review-reserve", payload={
        "allocation_id": token_root, "reservation_id": "review-other-work", "amount": 99_000}))

    deferred = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                           **run["roots"])
    assert deferred["status"] == "deferred"
    assert store.allocation_free(migrated_db, token_root) == 1_000
    released = store.release_reservation(migrated_db, Command(
        request_id="review-release", payload={"reservation_id": "review-other-work"}))
    assert released.code.value == "applied"
    assert store.allocation_free(migrated_db, token_root) == 100_000

    resumed = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                          **run["roots"])

    assert resumed["status"] == "acknowledged", resumed
    assert agenda.read(migrated_db, "p05-one")["turns"] == 1
    assert len(_worker_calls(run["worker_log"])) == 1


def test_zero_turn_deferral_reaches_hard_deadline_stop(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "deadline", "review-deadline", "pass-first")
    charter = _charter(run)
    charter["deadline"] = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
    _grant(migrated_db, charter)
    agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    root = run["roots"]["artifacts_root"]
    hidden = root.with_name("hidden-artifacts")
    root.rename(hidden)
    try:
        deferred = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                               **run["roots"])
        assert deferred["status"] == "deferred"
        time.sleep(2.1)
        stopped = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                              **run["roots"])
    finally:
        hidden.rename(root)

    assert stopped["status"] == "stopped"
    assert agenda.read(migrated_db, "p05-one")["status"] == "stopped"
    assert agenda.read(migrated_db, "p05-one")["turns"] == 0
    assert _worker_calls(run["worker_log"]) == []


def test_existing_p01_token_ceiling_must_fit_before_choice(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "token-limit", "review-token", "pass-first")
    charter = _charter(run)
    charter["opportunities"][0]["resource_ceilings"]["tokens"] = 1
    _grant(migrated_db, charter)
    agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    refused = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                          **run["roots"])

    assert refused["status"] == "deferred"
    assert agenda.read(migrated_db, "p05-one")["turns"] == 0
    assert not [decision for decision in agenda.export(
        migrated_db, "p05-one")["decisions"] if decision["kind"] == "p05.choice"]
    assert run["state"]["pending_decision"] is None
    assert _worker_calls(run["worker_log"]) == []


def _retained_native_opportunity(migrated_db, tmp_path, agenda_id, *, timeout_ms, value,
                                 method_name="maximum",
                                 method_interface="sequence-maximum/1"):
    from test_rsi_capability_integration import _create, _genome, _qualify

    from rsi import genome
    from settlement.launcher_local import LocalLauncher

    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    for domain in ("tokens", "cpu"):
        store.seed_allocation(migrated_db, Command(request_id=f"{agenda_id}-{domain}",
            payload={"allocation_id": domain, "domain": domain, "authorized": 100_000}))
    candidate = _genome()
    genome.publish(migrated_db, candidate, parent=None,
                   origin="independent-authored-test", **roots)
    env = (migrated_db, roots, candidate, LocalLauncher(tmp_path / "native"), tmp_path)
    _, retained = _qualify(env)
    assert retained["status"] == "retained"
    state = _create(env, [-5, 9, 2], 9)
    charter = _charter({"state": state}, agenda_id=agenda_id)
    opportunity = charter["opportunities"][0]
    opportunity["timeout_ms"] = timeout_ms
    opportunity["method_request"] = {
        "name": method_name, "interface": method_interface, "value": value}
    _grant(migrated_db, charter, agenda_id)
    agenda.create(migrated_db, agenda_id=agenda_id, charter=charter,
                  artifacts_root=roots["artifacts_root"])
    return state, charter, env[3], roots


def test_existing_native_timeout_must_fit_cpu_envelope_before_choice(migrated_db, tmp_path):
    agenda_id = "p05-native-timeout"
    state, charter, launcher, roots = _retained_native_opportunity(
        migrated_db, tmp_path, agenda_id, timeout_ms=1, value=[-5, 9, 2])
    expected_cpu = sum(broker.exposure_schedule(broker.SANDBOX_EXEC,
        {"timeout_ms": duration})[0] for duration in (1, 30_000))
    charter["opportunities"][0]["resource_ceilings"]["cpu"] = expected_cpu
    _grant(migrated_db, charter, agenda_id)

    refused = agenda.wake(migrated_db, None, launcher, agenda_id, **roots)

    assert refused["status"] == "deferred"
    assert agenda.read(migrated_db, agenda_id)["turns"] == 0
    assert not [decision for decision in agenda.export(
        migrated_db, agenda_id)["decisions"] if decision["kind"] == "p05.choice"]
    assert state["pending_decision"] is None


def test_existing_native_cpu_exposure_uses_its_stricter_timeout(migrated_db, tmp_path):
    from settlement import db

    agenda_id = "p05-native-cpu"
    state, charter, launcher, roots = _retained_native_opportunity(
        migrated_db, tmp_path, agenda_id, timeout_ms=10_000, value=[-5, 9, 2])
    expected_cpu = sum(broker.exposure_schedule(broker.SANDBOX_EXEC,
        {"timeout_ms": duration})[0] for duration in (5_000, 30_000))
    charter["opportunities"][0]["resource_ceilings"]["cpu"] = expected_cpu
    _grant(migrated_db, charter, agenda_id)

    result = agenda.wake(migrated_db, None, launcher, agenda_id, **roots)

    assert result["status"] == "acknowledged", result
    worker = broker.read_operation(migrated_db, result["acknowledgement"]["operation_id"])
    assert worker["payload"]["payload"]["timeout_ms"] == 5_000
    with db.read_connect(migrated_db) as conn:
        reserved_cpu = conn.execute(
            "SELECT sum(r.amount) FROM reservations r JOIN operations o"
            " ON o.id=r.operation_id WHERE o.attempt_id=%s",
            (result["acknowledgement"]["attempt_id"],)).fetchone()[0]
    assert reserved_cpu == expected_cpu
    assert state["pending_decision"] is None


@pytest.mark.parametrize(("method_name", "method_interface", "value"), [
    ("other-method", "sequence-maximum/1", [-5, 9, 2]),
    ("maximum", "other-interface/1", [-5, 9, 2]),
    ("maximum", "sequence-maximum/1", [1, 2, 3]),
])
def test_existing_native_method_request_must_match_before_choice(
    migrated_db, tmp_path, method_name, method_interface, value
):
    agenda_id = "p05-native-method"
    state, _, launcher, roots = _retained_native_opportunity(
        migrated_db, tmp_path, agenda_id, timeout_ms=5_000, value=value,
        method_name=method_name, method_interface=method_interface)
    prior_decisions = investigation.export(migrated_db, "later-use")["decisions"]

    refused = agenda.wake(migrated_db, None, launcher, agenda_id, **roots)

    assert refused["status"] == "deferred"
    assert agenda.read(migrated_db, agenda_id)["turns"] == 0
    assert not [decision for decision in agenda.export(
        migrated_db, agenda_id)["decisions"] if decision["kind"] == "p05.choice"]
    assert state["pending_decision"] is None
    assert investigation.export(migrated_db, "later-use")["decisions"] == prior_decisions


def test_peer_ack_after_choice_returns_the_original_outcome(migrated_db, tmp_path, monkeypatch):
    run = _scenario(migrated_db, tmp_path / "peer-ack", "review-peer-ack", "pass-first")
    charter = _charter(run)
    _grant(migrated_db, charter)
    agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    original = agenda._commit_choice
    peer_result = {}

    def peer_acknowledges_committed_choice(*args, **kwargs):
        flight = original(*args, **kwargs)
        peer_result["result"] = agenda.wake(
            migrated_db, run["agent"], run["checker"], "p05-one", **run["roots"])
        assert peer_result["result"]["status"] == "acknowledged"
        return flight

    monkeypatch.setattr(agenda, "_commit_choice", peer_acknowledges_committed_choice)
    result = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                         **run["roots"])

    assert result["status"] == "acknowledged", result
    assert result["acknowledgement"] == peer_result["result"]["acknowledgement"]
    assert agenda.read(migrated_db, "p05-one")["flight"] is None
    assert len(_worker_calls(run["worker_log"])) == 1


def test_peer_ack_does_not_let_original_wake_finish_a_newer_choice(
    migrated_db, tmp_path, monkeypatch
):
    run = _scenario(migrated_db, tmp_path / "newer-choice", "review-newer-choice",
                    "repair-after-feedback")
    charter = _charter(run, max_turns=3)
    _grant(migrated_db, charter)
    agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    commit = agenda._commit_choice
    step = agenda.investigate.step
    interleave = {}

    def peer_completes_then_admits_newer_choice(*args, **kwargs):
        flight = commit(*args, **kwargs)
        monkeypatch.setattr(agenda, "_commit_choice", commit)
        peer = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                           **run["roots"])
        assert peer["status"] == "acknowledged"
        interleave["acknowledgement"] = peer["acknowledgement"]
        assert len(_worker_calls(run["worker_log"])) == 1

        def interrupt_new_choice(*_args, **_kwargs):
            raise RuntimeError("interrupt after newer choice admission")

        monkeypatch.setattr(agenda.investigate, "step", interrupt_new_choice)
        try:
            with pytest.raises(RuntimeError, match="newer choice admission"):
                agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                            **run["roots"])
        finally:
            monkeypatch.setattr(agenda.investigate, "step", step)
        interleave["newer_flight"] = agenda.read(migrated_db, "p05-one")["flight"]
        assert interleave["newer_flight"] is not None
        assert interleave["newer_flight"] != flight
        return flight

    monkeypatch.setattr(agenda, "_commit_choice", peer_completes_then_admits_newer_choice)
    result = agenda.wake(migrated_db, run["agent"], run["checker"], "p05-one",
                         **run["roots"])

    assert result["status"] == "acknowledged", result
    assert result["acknowledgement"]["decision_id"] == interleave[
        "acknowledgement"]["decision_id"]
    assert agenda.read(migrated_db, "p05-one")["flight"] == interleave["newer_flight"]
    assert agenda.read(migrated_db, "p05-one")["turns"] == 2
    assert len(_worker_calls(run["worker_log"])) == 1
