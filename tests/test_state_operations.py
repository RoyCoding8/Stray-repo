from __future__ import annotations

import uuid

from settlement import store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _setup(dsn):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _prepare(dsn, op_id="op1", body=None, exposure=40, res_id="res-op"):
    return store.prepare_operation(dsn, _cmd({
        "operation_id": op_id, "attempt_id": "att1", "allocation_id": "a1",
        "reservation_id": res_id, "exposure": exposure,
        "operation": body or {"kind": "infer", "n": 1}, "execution_version": "exec-v3"}))


def test_prepare_is_immutable_and_idempotent(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    assert _prepare(dsn).code == ResultCode.APPLIED
    same = _prepare(dsn)
    assert same.code == ResultCode.ALREADY_APPLIED
    clashing = _prepare(dsn, body={"kind": "infer", "n": 2})
    assert clashing.code == ResultCode.INVALID_INPUT


def test_dispatch_admission_checks_grant_and_records_before_send(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _prepare(dsn)
    stale_grant = store.advance_dispatch(
        dsn, _cmd({"operation_id": "op1", "launcher_id": "L1", "grant_version": 999,
                   "ownership_generation": gen}))
    assert stale_grant.code == ResultCode.UNAUTHORIZED
    current = store.get_control(dsn)["authority_version"]
    ok = store.advance_dispatch(
        dsn, _cmd({"operation_id": "op1", "launcher_id": "L1", "grant_version": current,
                   "ownership_generation": gen}))
    assert ok.code == ResultCode.APPLIED
    state = store.restart_reconciliation(dsn)
    assert [o["id"] for o in state["unfinished_operations"]] == ["op1"]
    assert state["unfinished_operations"][0]["launcher_id"] == "L1"
    assert [m["workflow_identity"] for m in store.scan_outbox(dsn)] == ["dispatch:op1"]


def test_stale_generation_cannot_dispatch(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    _prepare(dsn)
    refused = store.advance_dispatch(
        dsn, _cmd({"operation_id": "op1", "launcher_id": "L1", "ownership_generation": 42}))
    assert refused.code == ResultCode.STALE_REVISION


def test_receipt_duplicate_conflict_and_settle_once(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _prepare(dsn)
    store.advance_dispatch(dsn, _cmd({"operation_id": "op1", "launcher_id": "L1",
                                      "ownership_generation": gen}))
    content = {"tokens": 12, "status": "ok"}
    first = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc1",
                                           "content": content, "outcome": "success",
                                           "provenance": "gw-1"}))
    assert first.code == ResultCode.APPLIED and first.data["settled"] is True
    dup = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc1",
                                         "content": dict(content), "outcome": "success"}))
    assert dup.code == ResultCode.ALREADY_APPLIED
    conflict = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc1",
                                              "content": {"tokens": 13, "status": "ok"},
                                              "outcome": "success"}))
    assert conflict.code == ResultCode.APPLIED and conflict.data.get("conflict") is True
    assert conflict.data["settled"] is True
    state = store.restart_reconciliation(dsn)
    assert [o["id"] for o in state["unfinished_operations"]] == ["op1"]
    assert state["unfinished_operations"][0]["reconcile_state"] == "conflict"
    resolved = store.reconcile_operation(dsn, _cmd({"operation_id": "op1", "resolution": "reconciled"}))
    assert resolved.code == ResultCode.APPLIED
    assert store.restart_reconciliation(dsn)["unfinished_operations"] == []


def test_unknown_outcome_retains_exposure_and_cancel_keeps_late_receipts(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _prepare(dsn)
    store.advance_dispatch(dsn, _cmd({"operation_id": "op1", "launcher_id": "L1",
                                      "ownership_generation": gen}))
    unknown = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc-u",
                                             "content": {"note": "timeout"}, "outcome": "unknown"}))
    assert unknown.code == ResultCode.APPLIED and unknown.data["settled"] is False
    pending = store.restart_reconciliation(dsn)
    assert pending["unfinished_operations"][0]["dispatch_state"] == "unresolved"
    assert store.request_cancellation(dsn, _cmd({"operation_id": "op1"})).code == ResultCode.APPLIED
    late = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc-late",
                                          "content": {"tokens": 3}, "outcome": "success"}))
    assert late.code == ResultCode.APPLIED and late.data["settled"] is True
    assert store.confirm_cancellation(dsn, _cmd({"operation_id": "op1"})).code == ResultCode.APPLIED


def test_restart_reconciliation_reports_registry(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _prepare(dsn, op_id="opA")
    _prepare(dsn, op_id="opB", res_id="res-B", exposure=10, body={"kind": "exec"})
    store.acquire_work(dsn, _cmd({"attempt_id": "att2", "investigation_id": "i1"}))
    store.advance_dispatch(dsn, _cmd({"operation_id": "opA", "launcher_id": "L9",
                                      "ownership_generation": gen}))
    state = store.restart_reconciliation(dsn)
    assert [o["id"] for o in state["unfinished_operations"]] == ["opA"]
    live = {a["id"]: a for a in state["live_attempts"]}
    assert live["att1"]["ownership_generation"] == gen
    assert live["att2"]["ownership_generation"] == gen + 1
    assert state["execution_versions"] == [{"id": "opA", "execution_version": "exec-v3"}]
