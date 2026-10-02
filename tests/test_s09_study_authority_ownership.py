"""Why `study_authority.allocation_id` carries no unique constraint.

N-207 made an allocation claimed by two study roots a loud refusal in
`store._study_root_for_allocation`, and that refusal is the only thing
holding the invariant. The schema does nothing on its own: `0015` keys the
table on `study_root` and leaves `allocation_id` free, and the very state
the refusal exists for is one `authority.authorize_study` creates without
argument when the allocation already holds the same authority.

A unique index would look like the obvious hardening, so these tests pin
the reasons it is not one, and they are the reasons a reviewer needs
before adding it.

A unique index cannot be added safely. `db.apply_migrations` runs each
file in autocommit and writes `schema_migrations` only after the whole
file succeeds, so a `CREATE UNIQUE INDEX` that hits a database already
holding a duplicate aborts the run with no row recorded. The database
then fails to boot forever, on a live study store, over a constraint
whose only added value is rejecting a state the code already refuses.

It would also make a legitimate state unrepresentable, and the last test
shows the legitimate state is not that one. A nested study is authorized
on an allocation of its own below the outer study's allocation, so
nesting never needed two roots on one allocation, and the only caller
that produces a shared allocation is the misconfiguration the refusal
names.

And it would be refused in the wrong place, in the wrong type.
`store.transact` re-raises any `UniqueViolation` other than
`command_journal_pkey` (store.py:320), so the constraint would surface
as a raw psycopg error escaping `authorize_study` instead of the
`ConflictPayload` that names both studies and lets a caller tell a
misconfiguration from an exhausted ceiling. Typing that error means
editing `authority.py`, which is a second change to buy nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest


def _authorize(dsn: str, study_root: str, allocation_id: str,
               authorized: int = 1_000, ceilings: dict | None = None):
    from settlement import authority

    return authority.authorize_study(
        dsn, study_root, authorized=authorized, allocation_id=allocation_id,
        ceilings=dict(ceilings or {}))


def _subdivide(dsn: str, parent_id: str, child_id: str, authorized: int = 1_000):
    from settlement import store
    from settlement.common import Command

    store.subdivide_allocation(dsn, Command(
        request_id="ownership-subdivide-%s" % child_id,
        payload={"parent_id": parent_id, "child_id": child_id,
                 "authorized": int(authorized), "domain": "study"}))


def _model_payload() -> dict:
    return {"model": "test", "messages": [{"role": "user", "content": "x"}],
            "max_output_tokens": 8, "deadline_ms": 1_000}


def _claimants(dsn: str, allocation_id: str) -> list[str]:
    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT study_root FROM study_authority"
                        " WHERE allocation_id = %s ORDER BY study_root",
                        (allocation_id,))
            roots = [row[0] for row in cur.fetchall()]
            conn.commit()
    return roots


def test_one_allocation_holding_two_studies_is_reachable_and_stays_representable(migrated_db):
    """The state the refusal guards is built by the public API, not by SQL.

    Both authorizations return, so nothing in the schema stopped them and
    nothing records that they happened. Break by adding any constraint on
    `study_authority.allocation_id`, or by teaching `authorize_study` to
    refuse the second attachment, and this fails at the second call
    rather than reporting what the constraint would do to a live store.
    """
    from settlement import authority

    first = _authorize(migrated_db, "own-shared-a", "own-shared-alloc")
    second = _authorize(migrated_db, "own-shared-b", "own-shared-alloc")

    assert (first.allocation_id, second.allocation_id) == (
        "own-shared-alloc", "own-shared-alloc"), (
        "the second study did not attach to the shared allocation: %r"
        % (second.allocation_id,))
    assert _claimants(migrated_db, "own-shared-alloc") == [
        "own-shared-a", "own-shared-b"], (
        "the shared allocation no longer holds both study roots, so the "
        "refusal under test can no longer be reached through this API")
    assert authority.bind_study(
        migrated_db, "own-shared-a").study_root == "own-shared-a"
    assert authority.bind_study(
        migrated_db, "own-shared-b").study_root == "own-shared-b"


def test_the_study_admission_path_refuses_a_shared_allocation_too(migrated_db):
    """The second write site, which no existing test covers.

    `store._bind_study_allocation` guards both inserts into `operations`
    (store.py:1473 and 1664). `test_s09_lineage_direction` proves the
    guard on the `ensure_operation` path only, so a change to the study
    path alone would leave an operation admitted against one of two
    studies. Break by dropping the `_bind_study_allocation` call from
    `admit_study_operation`.
    """
    from settlement import authority, broker

    _authorize(migrated_db, "own-admit-a", "own-admit-alloc")
    _authorize(migrated_db, "own-admit-b", "own-admit-alloc")

    refused = authority.admit_study_call(
        migrated_db, "own-admit-a", kind="development",
        operation_id="own-admit-op", effect="model-inference",
        payload=_model_payload())

    assert refused.reason == "admission-refused", (
        "a shared allocation was admitted against one of its two studies: "
        "%s" % getattr(refused, "detail", ""))
    detail = str(getattr(refused, "detail", ""))
    assert "own-admit-a" in detail and "own-admit-b" in detail, (
        "the refusal does not name both studies, so a caller cannot tell "
        "a misconfiguration from an exhausted ceiling: %s" % detail)
    assert broker.read_operation(migrated_db, "own-admit-op") is None, (
        "the operation was persisted under an allocation claimed by two "
        "studies even though the binding refused")


def test_a_nested_study_runs_on_its_own_allocation_below_the_outer_one(migrated_db):
    """The legitimate state, and it is not the state a unique index forbids.

    An inner study is authorized on an allocation subdivided from the
    outer study's, then admits work that binds to the inner root. A unique
    index on `allocation_id` leaves this working and forbids only the
    misconfiguration above, so the constraint's real cost is paid on live
    stores and its real benefit is already bought here. Break by making
    the nearest-ancestor walk return the outer root, or by authorizing
    the inner study on the outer study's allocation.
    """
    from settlement import authority
    from settlement import broker

    _authorize(migrated_db, "own-outer", "own-outer-alloc", authorized=5_000,
               ceilings={"max_operations": 8})
    _subdivide(migrated_db, "own-outer-alloc", "own-inner-alloc")
    _authorize(migrated_db, "own-inner", "own-inner-alloc",
               authorized=1_000, ceilings={"max_operations": 8})

    granted = authority.admit_study_call(
        migrated_db, "own-inner", kind="development",
        operation_id="own-nested-op", effect="model-inference",
        payload=_model_payload())

    assert getattr(granted, "operation_id", None) == "own-nested-op", (
        "a nested study was refused: %s / %s"
        % (getattr(granted, "reason", ""), getattr(granted, "detail", "")))
    operation = broker.read_operation(migrated_db, "own-nested-op")
    assert dict(operation.get("payload") or {}).get("study_root") == "own-inner", (
        "the nested operation bound the outer study root, so the outer "
        "study's ceilings were checked against work the inner study paid for")


def test_the_schema_constrains_nothing_on_allocation_id(migrated_db):
    """The decision itself, stated where a later lane adding a constraint meets it.

    `apply_migrations` records a migration only after its whole file
    succeeds, so an index that meets a live duplicate leaves the store
    unable to boot with nothing recorded to retry. Break by adding a
    unique index here, and read this module's docstring first: the cost
    lands on a live study store, not on a test.
    """
    from settlement import db

    with db.read_connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename ="
                " 'study_authority' AND indexdef LIKE '%UNIQUE%'"
                " ORDER BY indexname")
            unique = [row[0] for row in cur.fetchall()]
            conn.commit()

    assert unique == ["study_authority_pkey"], (
        "study_authority now carries unique indexes %r. Confirm against "
        "every live database that none holds a duplicated allocation_id "
        "before assuming this is safe." % (unique,))


@pytest.fixture
def migrated_db():
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db("own")
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)
