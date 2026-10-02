from __future__ import annotations

import uuid

import pytest

from settlement import store
from settlement.common import Command, ConflictPayload, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _alloc(dsn, aid="a1", authorized=100):
    return store.seed_allocation(dsn, _cmd({"allocation_id": aid, "domain": "cpu", "authorized": authorized}))


def test_duplicate_same_payload_returns_original_result(migrated_db):
    dsn = migrated_db
    assert _alloc(dsn).code == ResultCode.APPLIED
    payload = {"allocation_id": "a1", "reservation_id": "r1", "amount": 30}
    first = store.reserve(dsn, Command(request_id="dup-req", payload=payload))
    second = store.reserve(dsn, Command(request_id="dup-req", payload=dict(payload)))
    assert first.code == ResultCode.APPLIED
    assert second.code == ResultCode.ALREADY_APPLIED
    assert second.data == first.data


def test_duplicate_different_payload_is_an_error(migrated_db):
    dsn = migrated_db
    assert _alloc(dsn).code == ResultCode.APPLIED
    store.reserve(dsn, Command(request_id="dup-req",
                               payload={"allocation_id": "a1", "reservation_id": "r1", "amount": 30}))
    with pytest.raises(ConflictPayload):
        store.reserve(dsn, Command(request_id="dup-req",
                                   payload={"allocation_id": "a1", "reservation_id": "r1", "amount": 31}))


def test_refusal_is_journaled_and_replayed(migrated_db):
    dsn = migrated_db
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    bad = {"investigation_id": "i1", "objective": "changed"}
    first = store.amend_commitment(dsn, Command(request_id="amend-1", payload=bad, expected_revision=99))
    assert first.code == ResultCode.STALE_REVISION
    again = store.amend_commitment(dsn, Command(request_id="amend-1", payload=dict(bad), expected_revision=99))
    assert again.code == ResultCode.STALE_REVISION
    assert again.detail == first.detail


def test_duplicate_reserve_does_not_double_spend(migrated_db):
    dsn = migrated_db
    assert _alloc(dsn, authorized=50).code == ResultCode.APPLIED
    payload = {"allocation_id": "a1", "reservation_id": "r1", "amount": 50}
    assert store.reserve(dsn, Command(request_id="rr", payload=payload)).code == ResultCode.APPLIED
    assert store.reserve(dsn, Command(request_id="rr", payload=dict(payload))).code == ResultCode.ALREADY_APPLIED
    extra = store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r2", "amount": 1}))
    assert extra.code == ResultCode.INSUFFICIENT_RESOURCES
