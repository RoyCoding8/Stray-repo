from __future__ import annotations

import uuid

from settlement import store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _setup_operation(dsn, op_id="op1", exposure=40):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    assert acquired.code == ResultCode.APPLIED
    prepared = store.prepare_operation(dsn, _cmd({
        "operation_id": op_id, "attempt_id": "att1", "allocation_id": "a1",
        "reservation_id": "res-op", "exposure": exposure, "operation": {"kind": "infer", "n": 1}}))
    assert prepared.code == ResultCode.APPLIED
    gen = acquired.data["ownership_generation"]
    advanced = store.advance_dispatch(dsn, _cmd({"operation_id": op_id, "launcher_id": "L1",
                                                 "ownership_generation": gen}))
    assert advanced.code == ResultCode.APPLIED
    return gen


def test_intent_survives_crash_before_delivery_and_redelivers(migrated_db):
    dsn = migrated_db
    _setup_operation(dsn)
    pending = store.scan_outbox(dsn)
    assert [m["workflow_identity"] for m in pending] == ["dispatch:op1"]
    crashed_claim = store.claim_outbox(dsn, _cmd({"workflow_identity": "dispatch:op1"}))
    assert crashed_claim.code == ResultCode.APPLIED
    assert crashed_claim.data["delivered"] is False
    assert [m["workflow_identity"] for m in store.scan_outbox(dsn)] == ["dispatch:op1"]
    first = store.record_delivery(dsn, _cmd({"workflow_identity": "dispatch:op1"}))
    assert first.code == ResultCode.APPLIED
    assert store.scan_outbox(dsn) == []
    replay = store.record_delivery(dsn, _cmd({"workflow_identity": "dispatch:op1"}))
    assert replay.code == ResultCode.ALREADY_APPLIED
    assert store.scan_outbox(dsn) == []


def test_claim_after_delivery_reports_already(migrated_db):
    dsn = migrated_db
    _setup_operation(dsn)
    assert store.record_delivery(dsn, _cmd({"workflow_identity": "dispatch:op1"})).code == ResultCode.APPLIED
    claimed = store.claim_outbox(dsn, _cmd({"workflow_identity": "dispatch:op1"}))
    assert claimed.code == ResultCode.ALREADY_APPLIED
    assert claimed.data["delivered"] is True


def test_unknown_intent_is_refused(migrated_db):
    dsn = migrated_db
    result = store.record_delivery(dsn, _cmd({"workflow_identity": "dispatch:nope"}))
    assert result.code == ResultCode.INVALID_INPUT
    result = store.claim_outbox(dsn, _cmd({"workflow_identity": "dispatch:nope"}))
    assert result.code == ResultCode.INVALID_INPUT
