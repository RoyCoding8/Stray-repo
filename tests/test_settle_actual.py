import uuid

from settlement import store
from settlement.common import Command, ResultCode


def _cmd(payload, request_id=None):
    return Command(request_id=request_id or f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def test_settle_releases_unused_portion(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 30}))
    result = store.settle_reservation(
        dsn, _cmd({"reservation_id": "r1", "outcome": "success", "actual_cost": 12}))
    assert result.code == ResultCode.APPLIED
    assert result.data["consumed"] == 12
    status = store.allocation_status(dsn, "a1")
    assert (status["authorized"], status["consumed"], status["reserved"]) == (100, 12, 0)


def test_settle_rejects_out_of_range_actual(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 30}))
    assert store.settle_reservation(
        dsn, _cmd({"reservation_id": "r1", "outcome": "success", "actual_cost": 31})).code \
        == ResultCode.INVALID_INPUT
    assert store.settle_reservation(
        dsn, _cmd({"reservation_id": "r1", "outcome": "success", "actual_cost": -1})).code \
        == ResultCode.INVALID_INPUT
    status = store.allocation_status(dsn, "a1")
    assert (status["consumed"], status["reserved"]) == (0, 30)


def test_receipt_actual_cost_settles_partial(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.prepare_operation(dsn, _cmd({"operation_id": "op1", "allocation_id": "a1",
                                       "reservation_id": "r1", "exposure": 40,
                                       "operation": {"kind": "model"}}))
    result = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc1",
                                            "content": {"text": "done"}, "outcome": "success",
                                            "actual_cost": 9}))
    assert result.code == ResultCode.APPLIED
    status = store.allocation_status(dsn, "a1")
    assert (status["consumed"], status["reserved"]) == (9, 0)


def test_unknown_outcome_ignores_actual_and_retains_exposure(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 30}))
    result = store.settle_reservation(
        dsn, _cmd({"reservation_id": "r1", "outcome": "unknown", "actual_cost": 5}))
    assert result.code == ResultCode.ALREADY_APPLIED
    status = store.allocation_status(dsn, "a1")
    assert (status["consumed"], status["reserved"]) == (0, 30)
