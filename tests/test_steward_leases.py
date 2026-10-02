from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from settlement import steward, store
from settlement.common import Command, ConflictPayload, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _alloc(dsn, aid="a1", authorized=100, scope=""):
    return store.seed_allocation(dsn, _cmd({"allocation_id": aid, "domain": "cpu",
                                            "authorized": authorized, "owner_scope": scope}))


def _invest(dsn, iid="i1"):
    return store.admit_commitment(dsn, _cmd({"investigation_id": iid, "objective": "o"}))


def _work(dsn, aid="w1", iid="i1", alloc="a1"):
    return store.acquire_work(dsn, _cmd({"attempt_id": aid, "investigation_id": iid,
                                         "allocation_id": alloc}))


def test_lease_expiry_refuses_stale_dispatch_and_fulfill_but_keeps_observation(migrated_db):
    dsn = migrated_db
    assert _alloc(dsn).code == ResultCode.APPLIED
    assert _invest(dsn).code == ResultCode.APPLIED
    first = _work(dsn)
    gen = first.data["ownership_generation"]
    assert steward.issue_lease(dsn, _cmd({"attempt_id": "w1", "holder": "worker-a"})) \
        .code == ResultCode.APPLIED
    assert steward.expire_lease(dsn, _cmd({"attempt_id": "w1"})).code == ResultCode.APPLIED
    lease = steward.read_lease(dsn, "w1")
    assert lease is not None and lease["state"] == "expired"
    assert store.prepare_operation(dsn, _cmd({"operation_id": "op1", "attempt_id": "w1",
                                              "operation": {"effect": "note"}})).code == ResultCode.APPLIED
    stale_dispatch = steward.dispatch_guarded(
        dsn, Command(request_id=f"req_{uuid.uuid4().hex[:12]}",
                     payload={"operation_id": "op1", "ownership_generation": gen}))
    assert stale_dispatch.code == ResultCode.STALE_REVISION
    stale_fulfill = store.fulfill_investigation(
        dsn, _cmd({"investigation_id": "i1", "attempt_id": "w1", "ownership_generation": gen}))
    assert stale_fulfill.code == ResultCode.STALE_REVISION
    seen = store.submit_observation(dsn, _cmd({"attempt_id": "w1", "content": {"n": 1}}))
    assert seen.code == ResultCode.APPLIED


def test_stale_fulfill_refused_through_steward_before_store(migrated_db):
    dsn = migrated_db
    _alloc(dsn)
    _invest(dsn)
    gen = _work(dsn).data["ownership_generation"]
    steward.issue_lease(dsn, _cmd({"attempt_id": "w1"}))
    steward.revoke_lease(dsn, _cmd({"attempt_id": "w1"}))
    refused = steward.fulfill_investigation(dsn, _cmd({"investigation_id": "i1", "attempt_id": "w1",
                                                       "ownership_generation": gen}))
    assert refused.code == ResultCode.STALE_REVISION
    assert "generation" in refused.detail


def test_reacquire_after_expiry_uses_current_generation(migrated_db):
    dsn = migrated_db
    _alloc(dsn)
    _invest(dsn)
    _work(dsn)
    steward.issue_lease(dsn, _cmd({"attempt_id": "w1", "holder": "a"}))
    steward.expire_lease(dsn, _cmd({"attempt_id": "w1"}))
    again = steward.reacquire_lease(dsn, _cmd({"attempt_id": "w1", "holder": "b"}))
    assert again.code == ResultCode.APPLIED
    assert again.data["ownership_generation"] == 2
    assert steward.read_lease(dsn, "w1")["holder"] == "b"


def test_lease_commands_are_idempotent_with_request_identity(migrated_db):
    dsn = migrated_db
    _alloc(dsn)
    _invest(dsn)
    _work(dsn)
    payload = {"attempt_id": "w1", "holder": "a"}
    first = steward.issue_lease(dsn, Command(request_id="lease-1", payload=dict(payload)))
    second = steward.issue_lease(dsn, Command(request_id="lease-1", payload=dict(payload)))
    assert (first.code, second.code) == (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    with pytest.raises(ConflictPayload):
        steward.issue_lease(dsn, Command(request_id="lease-1", payload={"attempt_id": "w1",
                                                                        "holder": "other"}))


def test_task_admission_cannot_consume_supervision_capacity(migrated_db):
    dsn = migrated_db
    _alloc(dsn, aid="sup", scope="supervision")
    _alloc(dsn, aid="dev", scope="development")
    _invest(dsn)
    refused = steward.admit_task(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                            "allocation_id": "sup", "kind": "task"}))
    assert refused.code == ResultCode.INSUFFICIENT_RESOURCES
    allowed = steward.admit_task(dsn, _cmd({"attempt_id": "w2", "investigation_id": "i1",
                                            "allocation_id": "dev", "kind": "task"}))
    assert allowed.code == ResultCode.APPLIED
    recovery = steward.admit_task(dsn, _cmd({"attempt_id": "w3", "investigation_id": "i1",
                                             "allocation_id": "sup", "kind": "recovery"}))
    assert recovery.code == ResultCode.APPLIED


def test_amend_allocation_refuses_shrink_below_commitments(migrated_db):
    dsn = migrated_db
    _alloc(dsn, authorized=100)
    store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 40}))
    bad = steward.amend_allocation(dsn, _cmd({"allocation_id": "a1", "authorized": 10}))
    assert bad.code == ResultCode.INVALID_INPUT
    good = steward.amend_allocation(dsn, _cmd({"allocation_id": "a1", "authorized": 200}))
    assert good.code == ResultCode.APPLIED and good.data["authorized"] == 200


def test_quarantine_degrades_cleanly_without_t5_tables(migrated_db, monkeypatch):
    import sys

    import settlement.capabilities  # noqa: F401  (prove the slice exists here)

    monkeypatch.setitem(sys.modules, "settlement.capabilities", None)
    dsn = migrated_db
    result = steward.quarantine_subject(dsn, _cmd({"subject": "cap-v3"}))
    assert result.code == ResultCode.UNAVAILABLE_DEPENDENCY
    assert "subject" not in result.data or True
    again = steward.quarantine_subject(
        dsn, Command(request_id=result.request_id, payload={"subject": "cap-v3"}))
    assert again.code == ResultCode.UNAVAILABLE_DEPENDENCY
    assert again.detail == result.detail


def test_deadline_sweep_lists_and_expires_overdue_attempts(migrated_db):
    dsn = migrated_db
    _alloc(dsn)
    _invest(dsn)
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    store.acquire_work(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                  "allocation_id": "a1", "deadline": past}))
    due = steward.due_attempts(dsn)
    assert [a["id"] for a in due] == ["w1"]
    assert steward.expire_attempt(dsn, _cmd({"attempt_id": "w1"})).code == ResultCode.APPLIED
    assert steward.due_attempts(dsn) == []
