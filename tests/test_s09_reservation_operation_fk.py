"""C23: a reservation must not name an operation that does not exist.

`reservations.operation_id` has no foreign key, so a caller of the public
`store.reserve` could name an operation the store had never heard of. The
reservation committed, spent allocation authority, and could then be neither
settled nor released: `settle_reservation` and `release_reservation` both
require the operation to exist whenever the id is non-empty, and neither
creates one. The failure surfaced at settle, one command after the reserve
that caused it and one commit too late to un-spend the exposure.

`reserve` now refuses that id itself. These tests pin the refusal, the
pass-through for a real operation, the empty-string path that carries no
operation at all, and the reserve-then-insert ordering that decides where the
check can live.
"""

import uuid

from psycopg.rows import dict_row

from settlement import db, store
from settlement.common import Command, ResultCode


def _cmd(payload, request_id=None):
    return Command(request_id=request_id or f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _seed(dsn, alloc="c23-a1", authorized=100):
    store.seed_allocation(dsn, _cmd({"allocation_id": alloc, "domain": "cpu",
                                     "authorized": authorized}))


def _reserved(dsn, reservation_id):
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT operation_id, state FROM reservations WHERE id = %s",
                        (reservation_id,))
            return cur.fetchone()


def test_reserve_refuses_nonexistent_operation(migrated_db):
    dsn = migrated_db
    _seed(dsn)

    result = store.reserve(dsn, _cmd({
        "allocation_id": "c23-a1", "reservation_id": "c23-dangling", "amount": 30,
        "operation_id": "c23-no-such-operation"}))

    assert result.code == ResultCode.INVALID_INPUT
    assert result.detail == "unknown operation c23-no-such-operation"
    assert _reserved(dsn, "c23-dangling") is None

    status = store.allocation_status(dsn, "c23-a1")
    assert (status["consumed"], status["reserved"]) == (0, 0), \
        "a refused reservation must spend no exposure"


def test_reserve_refuses_nonexistent_operation_before_a_real_one(migrated_db):
    """The refusal is per-call, not a poisoned store.

    A rejected reserve leaves the command journal row behind. If that row made
    the store refuse the next reserve, a caller that recovered by naming a real
    operation would be stuck, so this drives both in one store.
    """
    dsn = migrated_db
    _seed(dsn)

    refused = store.reserve(dsn, _cmd({
        "allocation_id": "c23-a1", "reservation_id": "c23-bad", "amount": 10,
        "operation_id": "c23-absent"}))
    assert refused.code == ResultCode.INVALID_INPUT

    store.prepare_operation(dsn, _cmd({
        "operation_id": "c23-real", "allocation_id": "c23-a1",
        "execution_version": "c23-v1", "operation": {"kind": "c23"}}))
    accepted = store.reserve(dsn, _cmd({
        "allocation_id": "c23-a1", "reservation_id": "c23-good", "amount": 10,
        "operation_id": "c23-real"}))

    assert accepted.code == ResultCode.APPLIED
    assert _reserved(dsn, "c23-good")["operation_id"] == "c23-real"


def test_prepare_operation_reserves_before_it_inserts(migrated_db):
    """Why the guard belongs in `reserve` and not in `_take_reservation`.

    Six in-tree callers reserve against an operation id in the same
    transaction that then inserts the operation: `_prepare_operation`, the
    study admission path, `team._insert_operation`, and both agenda probe
    sites. `prepare_operation` is the public door onto the first of those, so
    driving it proves the ordering holds for a caller that is not `reserve`.

    A guard moved down into `_take_reservation` passes every other test in
    this file and still breaks this one, which is the reason the check cannot
    live in the shared helper. It is also the reason a foreign key cannot
    enforce the invariant: the reference is briefly unsatisfied inside the
    transaction, and `agenda._agenda_charge_decision` never inserts its
    operation at all.
    """
    dsn = migrated_db
    _seed(dsn)

    prepared = store.prepare_operation(dsn, _cmd({
        "operation_id": "c23-prepared", "allocation_id": "c23-a1",
        "reservation_id": "c23-prepared-r", "exposure": 20,
        "execution_version": "c23-v1", "operation": {"kind": "c23"}}))

    assert prepared.code == ResultCode.APPLIED
    assert prepared.data["operation_id"] == "c23-prepared"
    assert _reserved(dsn, "c23-prepared-r")["operation_id"] == "c23-prepared"

    settled = store.settle_reservation(dsn, _cmd({
        "reservation_id": "c23-prepared-r", "outcome": "success", "actual_cost": 20}))
    assert settled.code == ResultCode.APPLIED
    assert settled.data["consumed"] == 20


def test_reserve_with_real_operation_still_settles(migrated_db):
    dsn = migrated_db
    _seed(dsn)
    store.prepare_operation(dsn, _cmd({
        "operation_id": "c23-settles", "allocation_id": "c23-a1",
        "execution_version": "c23-v1", "operation": {"kind": "c23"}}))

    reserved = store.reserve(dsn, _cmd({
        "allocation_id": "c23-a1", "reservation_id": "c23-settles-r", "amount": 30,
        "operation_id": "c23-settles"}))
    assert reserved.code == ResultCode.APPLIED
    assert _reserved(dsn, "c23-settles-r")["state"] == "reserved"

    settled = store.settle_reservation(dsn, _cmd({
        "reservation_id": "c23-settles-r", "outcome": "success", "actual_cost": 30}))

    assert settled.code == ResultCode.APPLIED
    assert settled.data["settled"] is True
    assert settled.data["consumed"] == 30
    assert _reserved(dsn, "c23-settles-r")["state"] == "settled"
    status = store.allocation_status(dsn, "c23-a1")
    assert (status["authorized"], status["consumed"], status["reserved"]) == (100, 30, 0)


def test_reserve_with_empty_operation_id_still_settles(migrated_db):
    """The path the 15 needs-reconciliation failures do not involve.

    An empty `operation_id` is the sentinel for a reservation with no operation
    behind it. It skips the existence check entirely, so it is the case a guard
    written as "every reservation needs an operation" would break.
    """
    dsn = migrated_db
    _seed(dsn)

    reserved = store.reserve(dsn, _cmd({
        "allocation_id": "c23-a1", "reservation_id": "c23-noop-r", "amount": 25}))
    assert reserved.code == ResultCode.APPLIED
    assert _reserved(dsn, "c23-noop-r")["operation_id"] == ""

    settled = store.settle_reservation(dsn, _cmd({
        "reservation_id": "c23-noop-r", "outcome": "success", "actual_cost": 25}))

    assert settled.code == ResultCode.APPLIED
    assert settled.data["consumed"] == 25
    assert _reserved(dsn, "c23-noop-r")["state"] == "settled"
    status = store.allocation_status(dsn, "c23-a1")
    assert (status["consumed"], status["reserved"]) == (25, 0)


def test_reserve_with_empty_operation_id_releases(migrated_db):
    """The other terminal transition, which also reads the operation id."""
    dsn = migrated_db
    _seed(dsn)
    store.reserve(dsn, _cmd({
        "allocation_id": "c23-a1", "reservation_id": "c23-rel-r", "amount": 40}))

    released = store.release_reservation(dsn, _cmd({"reservation_id": "c23-rel-r"}))

    assert released.code == ResultCode.APPLIED
    assert _reserved(dsn, "c23-rel-r")["state"] == "released"
    status = store.allocation_status(dsn, "c23-a1")
    assert (status["consumed"], status["reserved"]) == (0, 0)


def test_a_refused_reservation_can_never_reach_settle(migrated_db):
    """The original asymmetry, closed.

    Before the fix, `reserve` returned APPLIED for a nonexistent operation and
    the row committed. The only thing that stopped it settling was the check
    inside `settle_reservation`, which arrived one command too late and left
    the exposure reserved. Here the reserve itself refuses, so there is no row
    for settle to find and no exposure to strand.
    """
    dsn = migrated_db
    _seed(dsn)
    store.reserve(dsn, _cmd({
        "allocation_id": "c23-a1", "reservation_id": "c23-ghost-r", "amount": 50,
        "operation_id": "c23-ghost"}))

    settled = store.settle_reservation(dsn, _cmd({
        "reservation_id": "c23-ghost-r", "outcome": "success", "actual_cost": 50}))

    assert settled.code == ResultCode.INVALID_INPUT
    assert settled.detail == "unknown reservation c23-ghost-r"
    status = store.allocation_status(dsn, "c23-a1")
    assert (status["consumed"], status["reserved"]) == (0, 0)
