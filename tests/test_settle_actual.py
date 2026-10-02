import uuid

from settlement import db, store
from settlement.common import Command, ResultCode


def _cmd(payload, request_id=None):
    return Command(request_id=request_id or f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _dispatch(dsn, operation_id, launcher="L1"):
    """Put a prepared operation into the state a receipt is admitted against.

    Two preconditions, not one. `admit_receipt` refuses a `prepared` operation
    at `store.py:1803`, and separately refuses a receipt that names no
    provenance at `store.py:1814`. An operation in this file binds no attempt,
    so `advance_dispatch` runs the grant check and nothing else, and
    `launcher_id` is the only field it needs.
    """
    dispatched = store.advance_dispatch(
        dsn, _cmd({"operation_id": operation_id, "launcher_id": launcher}))
    assert dispatched.code == ResultCode.APPLIED, dispatched.detail


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
    _dispatch(dsn, "op1")
    result = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc1",
                                            "content": {"text": "done"}, "outcome": "success",
                                            "actual_cost": 9, "provenance": "L1"}))
    assert result.code == ResultCode.APPLIED
    status = store.allocation_status(dsn, "a1")
    assert (status["consumed"], status["reserved"]) == (9, 0)


def test_success_without_actual_cost_consumes_full_reservation(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.prepare_operation(dsn, _cmd({"operation_id": "op1", "allocation_id": "a1",
                                       "reservation_id": "r1", "exposure": 40,
                                       "operation": {"kind": "model"}}))
    _dispatch(dsn, "op1")
    result = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc1",
                                            "content": {"text": "done"}, "outcome": "success",
                                            "provenance": "L1"}))
    assert result.code == ResultCode.APPLIED
    status = store.allocation_status(dsn, "a1")
    assert (status["consumed"], status["reserved"]) == (40, 0)


def test_overcharge_preserves_receipt_and_holds_liability(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.prepare_operation(dsn, _cmd({"operation_id": "op1", "allocation_id": "a1",
                                       "reservation_id": "r1", "exposure": 40,
                                       "operation": {"kind": "model"}}))
    _dispatch(dsn, "op1")
    result = store.admit_receipt(dsn, _cmd({"operation_id": "op1", "receipt_identity": "rc1",
                                            "content": {"text": "done"}, "outcome": "success",
                                            "actual_cost": 10 ** 9, "provenance": "L1"}))
    assert result.code == ResultCode.APPLIED
    assert result.data["settled"] is False
    assert "outside reserved" in result.data["settlement_refused"]
    status = store.allocation_status(dsn, "a1")
    assert (status["consumed"], status["reserved"]) == (0, 40)
    op = store.operation_receipts(dsn, "op1")
    assert [r["receipt_identity"] for r in op] == ["rc1"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT dispatch_state, reconcile_state, settled FROM operations WHERE id = %s",
                        ("op1",))
            row = cur.fetchone()
            conn.commit()
    # This asserted ("observed", "unresolved", False). No state of this store is
    # that, and none ever could be: `admit_receipt` has exactly two writers
    # for `dispatch_state`, and the one that sets "observed" (store.py:2043)
    # sets `reconcile_state` to "none" in the same statement, while both
    # writers that set "unresolved" also set `reconcile_state` to "unresolved"
    # (store.py:1999 and store.py:2029). Nothing writes "observed" and
    # "unresolved" together, so the assertion could never have held and the
    # test was red for a cause that was not the missing dispatch.
    #
    # What it meant to check is that the liability is still open: an operation
    # whose settlement was refused is not observed and not settled, and it
    # stays on the reconciliation register so a human or a later receipt can
    # close it. That is the state below, and the test now says so.
    assert (row[0], row[1], row[2]) == ("unresolved", "unresolved", False)
    assert [o["id"] for o in store.restart_reconciliation(dsn)["unfinished_operations"]] == ["op1"]


def test_seed_existing_allocation_refuses_without_downgrade(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.prepare_operation(dsn, _cmd({"operation_id": "op1", "allocation_id": "a1",
                                       "reservation_id": "r1", "exposure": 40,
                                       "operation": {"kind": "model"}}))
    refused = store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu",
                                               "authorized": 10}))
    assert refused.code != ResultCode.APPLIED
    status = store.allocation_status(dsn, "a1")
    assert (status["authorized"], status["reserved"]) == (100, 40)


def test_unknown_outcome_ignores_actual_and_retains_exposure(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 30}))
    result = store.settle_reservation(
        dsn, _cmd({"reservation_id": "r1", "outcome": "unknown", "actual_cost": 5}))
    assert result.code == ResultCode.ALREADY_APPLIED
    status = store.allocation_status(dsn, "a1")
    assert (status["consumed"], status["reserved"]) == (0, 30)
