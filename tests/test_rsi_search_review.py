from __future__ import annotations

import copy
import shutil
import sys

import pytest
from rsi_search_fixture import bundle
from test_rsi_capability_integration import _genome, _qualify, _task
from test_rsi_investigate import _scenario
from test_rsi_search_agenda import _charter_with_policy, _grant, _policy, _spawn_count

from rsi import agenda, archive, capability, genome, investigation, search, task, verifier
from settlement import broker, store
from settlement.common import Command, SettlementError, StaleRevision


def test_offline_replay_does_not_relabel_an_executed_policy():
    baseline = bundle()
    assert search.recompute(baseline)["supported"] == 1
    changed = copy.deepcopy(baseline)
    for identity in (changed["policy"], changed["pinned_evaluation"]):
        identity.update(genome="another-policy", name="another-method",
                        method_digest="another-closure")

    result = search.recompute(changed)

    assert (result["supported"], result["gaps"]) == (0, 1)
    assert result["screening_cpu_units"] == 4


def _native_agenda(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "run", "sol-native", "pass-first")
    policy, checker = _policy(run, tmp_path, action="choose", opportunity_id="first")
    for domain in ("tokens", "cpu"):
        store.seed_allocation(migrated_db, Command(
            request_id=f"sol-native-allocation:{domain}",
            payload={"allocation_id": domain, "domain": domain, "authorized": 100_000}))
    organism = _genome()
    item = _task("sol-native-task", 9)
    genome.publish(migrated_db, organism, parent=None, origin="sol-native", **run["roots"])
    task.publish(migrated_db, item, **run["roots"])
    checked, retained = _qualify((migrated_db, run["roots"], organism, checker, tmp_path))
    assert checked.passed is True and retained["status"] == "retained"

    def create(identity, grant_version):
        charter = _charter_with_policy(run, identity, policy, grant_version=grant_version)
        charter["opportunities"] = charter["opportunities"][:1]
        charter["allocations"] = {domain: {"id": domain, "units": 100_000}
                                  for domain in ("tokens", "cpu")}
        charter["opportunities"][0].update(
            task_id=item.digest, genome_id=organism.digest,
            objective=item.instruction, timeout_ms=5_000,
            method_request={"name": "maximum", "interface": "sequence-maximum/1",
                            "value": [-5, 9, 2]})
        _grant(migrated_db, charter, identity)
        agenda.create(migrated_db, agenda_id=identity, charter=charter,
                      artifacts_root=run["roots"]["artifacts_root"])

    return run, checker, create


def _change_runtime(run, checker, flight, tmp_path, monkeypatch):
    alternate = tmp_path / "trusted-python-copy.exe"
    shutil.copy2(sys.executable, alternate)
    monkeypatch.setattr(checker, "staged_python", lambda: str(alternate))
    state = investigation.read(run["dsn"], flight["investigation_id"])
    organism = genome.load(run["dsn"], run["roots"]["artifacts_root"], state["config"]["genome"])
    item = task.load(run["dsn"], run["roots"]["artifacts_root"], state["config"]["task"])
    plan = agenda._native_start_plan(
        checker, organism, item, flight["start"]["visible_input"], state["config"])
    assert plan.execution_version != flight["start"]["runtime"]["execution_version"]
    return alternate


@pytest.mark.parametrize("worker_state", ["absent", "prepared", "dispatching"])
def test_pending_work_rechecks_the_policy_pinned_native_runtime(
        migrated_db, tmp_path, monkeypatch, worker_state):
    run, checker, create = _native_agenda(migrated_db, tmp_path)
    create("sol-baseline", 1)
    baseline = agenda.wake(migrated_db, None, checker, "sol-baseline", **run["roots"])
    assert baseline["status"] == "acknowledged"
    choice = next(row for row in agenda.export(migrated_db, "sol-baseline")["decisions"]
                  if row["kind"] == "p05.choice")
    captured = search.capture(migrated_db, choice["data"]["frame_digest"], "first", **run["roots"])
    assert captured["status"] == "supported"

    create("sol-resume", 2)
    finish = agenda._finish

    def crash_after_work_choice(*args, **kwargs):
        if kwargs["flight"].get("kind") == "work":
            raise RuntimeError("crash before native worker dispatch")
        return finish(*args, **kwargs)

    monkeypatch.setattr(agenda, "_finish", crash_after_work_choice)
    with pytest.raises(RuntimeError, match="crash before native worker dispatch"):
        agenda.wake(migrated_db, None, checker, "sol-resume", **run["roots"])
    flight = agenda.read(migrated_db, "sol-resume")["flight"]
    assert flight["kind"] == "work"
    operation_id = flight["start"]["operation_id"]
    assert broker.read_operation(migrated_db, operation_id) is None
    monkeypatch.setattr(agenda, "_finish", finish)
    if worker_state != "absent":
        dispatch = broker.dispatch_operation

        def crash_during_worker_dispatch(dsn, candidate_id, **kwargs):
            if candidate_id == operation_id:
                if worker_state == "dispatching":
                    dispatch(dsn, candidate_id, **kwargs, _crash_after_send=True)
                raise RuntimeError("crash during worker dispatch")
            return dispatch(dsn, candidate_id, **kwargs)

        monkeypatch.setattr(broker, "dispatch_operation", crash_during_worker_dispatch)
        with pytest.raises(RuntimeError, match="crash during worker dispatch"):
            agenda.wake(migrated_db, None, checker, "sol-resume", **run["roots"])
        monkeypatch.setattr(broker, "dispatch_operation", dispatch)
    operation_before = broker.read_operation(migrated_db, operation_id)
    sent = []
    dispatch = checker.dispatch

    def record_send(operation):
        sent.append(operation.operation_id)
        return dispatch(operation)

    monkeypatch.setattr(checker, "dispatch", record_send)
    if operation_before is not None:
        assert operation_before["dispatch_state"] == worker_state
        assert operation_before["execution_version"] == flight["start"]["runtime"]["execution_version"]
    _change_runtime(run, checker, flight, tmp_path, monkeypatch)
    resumed = agenda.wake(migrated_db, None, checker, "sol-resume", **run["roots"])

    operation = broker.read_operation(migrated_db, operation_id)
    assert resumed["status"] == "pending"
    assert operation == operation_before
    assert sent == []
    if worker_state == "dispatching":
        assert _spawn_count(checker, operation) == "1"
    elif worker_state == "prepared":
        assert not (checker.run_dir / (
            checker.native_id(operation_id, operation["execution_version"]) + ".spawns")).exists()
    assert agenda.read(migrated_db, "sol-resume")["flight"] == flight


@pytest.mark.parametrize("intervention", ["none", "receipt-conflict", "pending-input"])
def test_terminal_worker_receipt_recovery_preserves_identity_and_uncertainty(
        migrated_db, tmp_path, monkeypatch, intervention):
    run, checker, create = _native_agenda(migrated_db, tmp_path)
    create("sol-terminal-baseline", 1)
    baseline = agenda.wake(
        migrated_db, None, checker, "sol-terminal-baseline", **run["roots"])
    assert baseline["status"] == "acknowledged"
    choice = next(row for row in agenda.export(migrated_db, "sol-terminal-baseline")["decisions"]
                  if row["kind"] == "p05.choice")
    assert search.capture(
        migrated_db, choice["data"]["frame_digest"], "first", **run["roots"])["status"] == "supported"

    create("sol-terminal", 2)
    interpret = capability._interpret

    def crash_before_capability_result(*args, **kwargs):
        if args[2].name == "maximum":
            raise RuntimeError("crash after broker receipt before capability result")
        return interpret(*args, **kwargs)

    monkeypatch.setattr(capability, "_interpret", crash_before_capability_result)
    with pytest.raises(RuntimeError, match="crash after broker receipt before capability result"):
        agenda.wake(migrated_db, None, checker, "sol-terminal", **run["roots"])
    monkeypatch.setattr(capability, "_interpret", interpret)
    flight = agenda.read(migrated_db, "sol-terminal")["flight"]
    operation_id = flight["start"]["operation_id"]
    operation = broker.read_operation(migrated_db, operation_id)
    assert operation["dispatch_state"] == "observed" and operation["settled"] is True
    assert archive.decision(migrated_db, "capability-use:" + operation_id) is None
    assert _spawn_count(checker, operation) == "1"

    alternate = _change_runtime(run, checker, flight, tmp_path, monkeypatch)
    if intervention == "receipt-conflict":
        receipt, = store.operation_receipts(migrated_db, operation_id)
        content = {**receipt["content"], "review_conflict": True}
        conflict = store.admit_receipt(migrated_db, Command(
            request_id="sol-terminal-receipt-conflict",
            payload={"operation_id": operation_id, "receipt_identity": receipt["receipt_identity"],
                     "outcome": receipt["outcome"], "content": content,
                     "provenance": receipt["provenance"]}))
        assert conflict.data["conflict"] is True
    elif intervention == "pending-input":
        read = investigation.read

        def changed_pending_input(dsn, investigation_id):
            state = read(dsn, investigation_id)
            if investigation_id == flight["investigation_id"]:
                state = copy.deepcopy(state)
                state["pending_decision"]["visible_input"]["objective"] = "different pending objective"
            return state

        monkeypatch.setattr(investigation, "read", changed_pending_input)

    operation_before = broker.read_operation(migrated_db, operation_id)
    sent = []
    dispatch = checker.dispatch

    def record_send(operation):
        sent.append(operation.operation_id)
        return dispatch(operation)

    monkeypatch.setattr(checker, "dispatch", record_send)
    if intervention == "pending-input":
        with pytest.raises(StaleRevision, match="pending P01 input differs"):
            agenda.wake(migrated_db, None, checker, "sol-terminal", **run["roots"])
    else:
        try:
            resumed = agenda.wake(migrated_db, None, checker, "sol-terminal", **run["roots"])
        except SettlementError:
            if intervention != "receipt-conflict":
                raise
        else:
            assert resumed["status"] == ("acknowledged" if intervention == "none" else "pending")

    operation_after = broker.read_operation(migrated_db, operation_id)
    assert operation_after == operation_before
    assert operation_after["execution_version"] == flight["start"]["runtime"]["execution_version"]
    assert _spawn_count(checker, operation_after) == "1"
    assert checker.staged_python() == str(alternate)
    state = investigation.read(migrated_db, flight["investigation_id"])
    item = task.load(migrated_db, run["roots"]["artifacts_root"], state["config"]["task"])
    expected_sends = ([verifier.operation_id_for(operation_id, item.evaluator_version)]
                      if intervention != "pending-input" else [])
    assert sent == expected_sends
    if intervention != "none":
        assert agenda.read(migrated_db, "sol-terminal")["flight"] == flight
        assert not any(row["kind"] == "p05.ack" for row in
                       agenda.export(migrated_db, "sol-terminal")["decisions"])
    if intervention == "receipt-conflict":
        assert operation_after["reconcile_state"] == "conflict"
        assert len(store.operation_receipt_conflicts(migrated_db, operation_id)) == 1
        organism = genome.load(
            migrated_db, run["roots"]["artifacts_root"], state["config"]["genome"])
        retained = capability.retain(
            migrated_db, "sol-conflicted-retention", genome=organism, name="maximum",
            episode_id=operation_id, artifacts_root=run["roots"]["artifacts_root"])
        assert retained["status"] == "rejected"
