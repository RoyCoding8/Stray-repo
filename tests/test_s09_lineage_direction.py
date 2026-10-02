"""A study's own ceilings must follow an operation down to a child allocation.

`store._study_root_for_allocation` resolved a study root by walking
`a.parent_id = line.id`, which is a walk *downward* from the starting row to
its descendants. A study root is an ancestor, so the walk visited children it
did not want and never the root it needed. Every operation under a child
allocation was persisted with no `study_root` in its payload, and
`_check_study_ceilings` returns immediately when the payload carries none. A
study's frozen ceilings were therefore never checked for anything the study
did below its own allocation, which is where a study does its work.

The contamination scanner reads the same question its own way and walks
*upward*, which is why adoption worked while the ceilings stayed blind.

Each assertion names the break that fails it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest


def _authorize(dsn: str, study_root: str, allocation_id: str,
               ceilings: dict | None = None, authorized: int = 1_000):
    from settlement import authority

    return authority.authorize_study(
        dsn, study_root, authorized=authorized, allocation_id=allocation_id,
        ceilings=dict(ceilings or {}))


def _subdivide(dsn: str, parent_id: str, child_id: str, authorized: int = 100):
    from settlement import store
    from settlement.common import Command

    store.subdivide_allocation(dsn, Command(
        request_id="lineage-subdivide-%s" % child_id,
        payload={"parent_id": parent_id, "child_id": child_id,
                 "authorized": int(authorized), "domain": "study"}))


def _note(dsn: str, operation_id: str, allocation_id: str):
    from settlement import broker

    return broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.DOMAIN_COMMAND,
        payload={"command": "note", "payload": {"decision": {"target": "x"}},
                 "idempotency_key": operation_id},
        allocation_id=allocation_id)


def _payload(dsn: str, operation_id: str) -> dict:
    from settlement import broker

    operation = broker.read_operation(dsn, operation_id)
    assert operation is not None, "no operation %r reached the store" % operation_id
    return dict(operation.get("payload") or {})


def test_a_child_allocation_binds_the_study_root_of_its_ancestor(migrated_db):
    """The direction of the walk, and the only thing it decides.

    Break by restoring `a.parent_id = line.id`, which walks from the
    starting allocation down to its children instead of up to the study
    allocation that owns it.
    """
    from settlement.common import ResultCode

    _authorize(migrated_db, "lineage-root", "lineage-alloc")
    _subdivide(migrated_db, "lineage-alloc", "lineage-alloc/w0/b14")

    admitted = _note(migrated_db, "lineage-child-op", "lineage-alloc/w0/b14")

    assert admitted.code is ResultCode.APPLIED, (
        "the child operation was refused for a reason unrelated to the "
        "lineage walk: %s" % admitted.detail)
    assert _payload(migrated_db, "lineage-child-op").get("study_root") == "lineage-root"


def test_a_study_ceiling_bounds_operations_admitted_under_a_child(migrated_db):
    """The money. A frozen ceiling that a child allocation can spend past.

    Break by skipping `_check_study_ceilings` for an operation whose
    payload has no `study_root`, which is what an unresolved lineage
    produces, or by walking the subtree but not the ancestor.
    """
    from settlement.common import ResultCode

    _authorize(migrated_db, "lineage-cap", "lineage-cap-alloc",
               ceilings={"max_operations": 1})
    _subdivide(migrated_db, "lineage-cap-alloc", "lineage-cap-alloc/w0")

    first = _note(migrated_db, "lineage-cap-op-0", "lineage-cap-alloc/w0")
    second = _note(migrated_db, "lineage-cap-op-1", "lineage-cap-alloc/w0")

    assert first.code is ResultCode.APPLIED, (
        "the first operation under a ceiling of 1 was refused: %s" % first.detail)
    assert second.code is not ResultCode.APPLIED, (
        "a study froze max_operations=1 and admitted a second operation "
        "below its own allocation")
    assert "max_operations=1" in str(second.detail or ""), (
        "the second operation was refused by something other than the "
        "frozen ceiling: %s" % second.detail)


def test_the_nearest_study_ancestor_owns_the_operation(migrated_db):
    """Nested studies. The inner one is the one that admitted the work.

    Break by returning the outermost ancestor, or the first authority row
    the scan happens to reach, either of which checks the outer study's
    ceilings against an operation the inner study paid for.
    """
    from settlement.common import ResultCode

    _authorize(migrated_db, "lineage-outer", "lineage-outer-alloc")
    _subdivide(migrated_db, "lineage-outer-alloc", "lineage-inner-alloc",
               authorized=1_000)
    _authorize(migrated_db, "lineage-inner", "lineage-inner-alloc",
               authorized=1_000)
    _subdivide(migrated_db, "lineage-inner-alloc", "lineage-inner-alloc/w0")

    _note(migrated_db, "lineage-nested-op", "lineage-inner-alloc/w0")

    assert _payload(migrated_db, "lineage-nested-op").get("study_root") == "lineage-inner", (
        "an operation under a nested study bound the outer study root")


def test_an_allocation_claimed_by_two_studies_is_refused_not_guessed(migrated_db):
    """One allocation, two authorities. There is no correct single answer.

    `study_authority` keys on `study_root` and constrains nothing on
    `allocation_id`, and `authorize_study` will attach a second study root
    to an allocation that already exists with the same authority. Binding
    either one silently leaves the other's ceilings unchecked for every
    operation admitted under that shared allocation, so the admission is
    refused instead. Break by keeping `LIMIT 1` and returning whichever
    row the scan reached first.
    """
    from settlement.common import ResultCode

    _authorize(migrated_db, "lineage-shared-a", "lineage-shared-alloc")
    _authorize(migrated_db, "lineage-shared-b", "lineage-shared-alloc")
    _subdivide(migrated_db, "lineage-shared-alloc", "lineage-shared-alloc/w0")

    admitted = _note(migrated_db, "lineage-shared-op", "lineage-shared-alloc/w0")

    assert admitted.code is not ResultCode.APPLIED, (
        "an operation under an allocation claimed by two studies was "
        "admitted against one of them: %s" % admitted.detail)
    assert "lineage-shared-a" in str(admitted.detail or "") \
        and "lineage-shared-b" in str(admitted.detail or ""), (
        "the refusal does not name both studies, so the caller cannot tell "
        "a misconfiguration from an exhausted ceiling: %s" % admitted.detail)


def test_an_allocation_with_no_study_ancestor_stays_unbound(migrated_db):
    """No study ancestor means no study root, not the nearest one.

    A study exists elsewhere in the same store, so any resolver that
    guesses by proximity binds this allocation's operations to a study
    that never authorized them. Break by falling back to a study root
    when the lineage walk returns nothing.
    """
    from settlement.common import ResultCode
    from settlement import store
    from settlement.common import Command

    _authorize(migrated_db, "lineage-bystander", "lineage-bystander-alloc")
    store.seed_allocation(migrated_db, Command(
        request_id="lineage-seed-orphan",
        payload={"allocation_id": "lineage-orphan-alloc", "domain": "study",
                 "authorized": 1_000}))
    _subdivide(migrated_db, "lineage-orphan-alloc", "lineage-orphan-alloc/w0")

    admitted = _note(migrated_db, "lineage-orphan-op", "lineage-orphan-alloc/w0")

    assert admitted.code is ResultCode.APPLIED, (
        "the operation was refused: %s" % admitted.detail)
    assert _payload(migrated_db, "lineage-orphan-op").get("study_root") is None, (
        "an allocation with no study ancestor was bound to a study root")


def test_a_parent_cycle_terminates_and_still_answers(migrated_db):
    """`parent_id` is written only at insert, but the walk must not hang.

    `UNION` deduplicates the working row set, so a walk that revisits an
    allocation stops. `UNION ALL` grows the row set by depth instead, never
    terminates, and the statement timeout turns that into an
    `UNAVAILABLE_DEPENDENCY` on the command rather than an answer. Break by
    switching the recursive term to `UNION ALL`.
    """
    from psycopg.rows import dict_row

    from settlement import db, store

    _authorize(migrated_db, "lineage-cycle-root", "lineage-cycle-root-alloc")
    with db.connect(migrated_db) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO allocations (id, parent_id, domain, epoch,"
                " authorized, amount_scale, max_occupancy, owner_scope)"
                " VALUES ('lineage-cycle-a', 'lineage-cycle-root-alloc', 'study',"
                " 0, 100, 1, 8, ''),"
                " ('lineage-cycle-b', 'lineage-cycle-a', 'study', 0, 100, 1, 8, '')")
            cur.execute("UPDATE allocations SET parent_id = 'lineage-cycle-b'"
                        " WHERE id = 'lineage-cycle-root-alloc'")
            conn.commit()

    with db.read_connect(migrated_db) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET LOCAL statement_timeout = '5000ms'")
            resolved = store._study_root_for_allocation(
                cur, "lineage-cycle-a")
        conn.commit()

    assert resolved == "lineage-cycle-root", (
        "the cyclic lineage answered %r; a walk that does not terminate "
        "returns a timeout rather than this" % (resolved,))


@pytest.fixture
def migrated_db():
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db("lineage")
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)
