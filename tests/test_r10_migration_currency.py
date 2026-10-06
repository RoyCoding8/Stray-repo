"""R10: nothing verified the schema was current, so a stale store read as healthy.

`apply_migrations` recorded migration names and every downstream reader
trusted that record. A store built from a directory missing its trailing
migration held a record that was internally consistent -- every name it
recorded was a real name, and every file it had applied was applied -- and
every consumer read from that record alone. So the state named here, a
store one migration behind its own directory, was not distinguishable from
a healthy one at any point in the tree.

The check sits in two places because two kinds of caller were wrong, and
one place would leave the other unwatched. `apply_migrations` verifies
because it is the function that created the state it would be verifying,
so a caller who never asks is still refused -- that is the call that
withheld `0020` and reported success. `boot.check_database` verifies
because it is the report that rendered a lagging schema as
`connected; 19 migrations recorded` with `exercised=True`, and a health
report that cannot see a defect is not a health report. Neither is a
function a caller has to remember to invoke, which is the shape three
lanes in this batch found to be the standing defect in this tree.

Currency is equality in both directions, and the tests below pin the two
definitions that look equivalent and are not. A subset check -- every
recorded name is still a file on disk -- passes on precisely the state
that occurred, because every name the stale store recorded does still
exist. A version high-water mark passes for a withdrawn migration and
moves forward, so it can never say a file is gone. Both are demonstrated
below as passing on a state that must refuse, so the reason for equality
is on the record rather than asserted in a comment.

A caller that means a partial store is not exempt and does not need to
be. It built its store from the partial directory, so both sides of the
comparison name the same nineteen files and the store is current for what
it claims to be. No flag, no second code path: the directory a caller
passes is already the statement of which schema it means, and it was
already an argument.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from pathlib import Path

import pytest

from settlement import boot, db

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"
ON_DISK = {path.name for path in MIGRATIONS.glob("*.sql")}
TRAILING = sorted(ON_DISK)[-1]


def _withheld_dir() -> Path:
    """The real migrations directory with its last file taken out.

    Copied rather than filtered at each call site: a partial store and a
    store built from a directory this tree no longer holds are the two
    states the check has to tell apart, and only a real directory on disk
    tells it.
    """
    tmp = Path(tempfile.mkdtemp(prefix="r10-migrations-"))
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name != TRAILING:
            shutil.copy2(path, tmp / path.name)
    return tmp


@contextlib.contextmanager
def _store(token: str, migrations_dir: Path):
    """A disposable store already migrated from ``migrations_dir``.

    `create_disposable_db` applies the directory itself, so these stores
    are born in the state under test rather than having to be driven into
    it. A test that wants the apply's own return value asks for a second
    apply, which is where the idempotence claim lives.
    """
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db(token, migrations_dir=migrations_dir)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)


def _recorded(dsn: str) -> set[str]:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM schema_migrations")
            found = {row[0] for row in cur.fetchall()}
            conn.commit()
    return found


# --- 1. A store one migration behind is refused, and named -----------------


def test_a_stale_store_is_refused_by_the_migration_it_lacks() -> None:
    """The withheld trailing migration is what the refusal says.

    A24's measurement was that a caller passing a directory missing
    `0020_mission_in_flight.sql` got a silent success. This is the
    missing half: a store built that way must be refused afterwards, by
    name, since a count leaves the reader to diff it against a directory
    it may not hold, which is the same undiagnosable state one step
    earlier.
    """
    partial = _withheld_dir()
    try:
        with _store("r10-stale", partial) as dsn:
            assert TRAILING not in _recorded(dsn)

            with pytest.raises(db.MigrationSetStale) as raised:
                db.verify_current(dsn, MIGRATIONS)
            assert TRAILING in str(raised.value), str(raised.value)
    finally:
        shutil.rmtree(partial, ignore_errors=True)


def test_boot_reports_a_stale_store_as_healthy_and_naming_it_is_the_fix() -> None:
    """RED on base using only base's own API, so it fails on the gap.

    Every other test here names `db.MigrationSetStale`, which does not
    exist at the base commit, so those failures prove the symbol is
    absent rather than that the hole was real. This one is written
    against what base already had -- `apply_migrations` and
    `check_database` -- and asserts the state, not the API. At base it
    fails because `check_database` has no parameter saying which
    directory the store should match, so it reports a store missing
    `0020` as `exercised=True` with a detail string that reads as a
    healthy boot. The trailing assertions are what keep it from being
    satisfied by an unrelated error: the refusal has to name the
    migration, and the store has to have been reachable, or a store that
    was merely down would also pass.
    """
    partial = _withheld_dir()
    try:
        with _store("r10-gap", partial) as dsn:
            db.apply_migrations(dsn, partial)
            assert TRAILING not in _recorded(dsn)

            try:
                status = boot.check_database(dsn, MIGRATIONS)
            except TypeError:
                status = boot.check_database(dsn)
            assert status.exercised is False, (
                "a store one migration behind reported exercised=%r with detail %r"
                % (status.exercised, status.detail))
            assert status.reachable is True, status
            assert TRAILING in status.detail, status.detail
    finally:
        shutil.rmtree(partial, ignore_errors=True)


def test_boot_refuses_a_stale_store_rather_than_reporting_it_healthy() -> None:
    """`check_database` is the report that read as healthy, so it must not.

    Before this a store holding 19 of 20 migrations produced
    `connected; 19 migrations recorded` with `exercised=True`, and
    `validate` computes its `ok` from that flag -- so a lagging schema
    advertised the same operations as a healthy one. The assertion is on
    `exercised`, the flag `ok` is computed from, because a detail string
    nobody parses is not a refusal.
    """
    partial = _withheld_dir()
    try:
        with _store("r10-boot", partial) as dsn:
            status = boot.check_database(dsn, MIGRATIONS)
            assert status.exercised is False, status
            assert status.reachable is True, status
            assert TRAILING in status.detail, status.detail
    finally:
        shutil.rmtree(partial, ignore_errors=True)


# --- 2. The check cannot be satisfied vacuously ----------------------------


def test_a_current_store_passes_and_holds_exactly_the_directory() -> None:
    """The green side of the same predicate, on a real store.

    Without this, `verify_current` could pass by refusing nothing: a
    version that always returned, or one that read an empty record on a
    store that was never migrated, would satisfy every refusal test above.
    The returned set is the store's own committed record and it equals the
    directory's names -- asserted against the table, not assumed from the
    apply that wrote it.
    """
    with _store("r10-current", MIGRATIONS) as dsn:
        recorded = db.verify_current(dsn, MIGRATIONS)
        assert recorded == ON_DISK
        assert _recorded(dsn) == recorded

        status = boot.check_database(dsn, MIGRATIONS)
        assert status.exercised is True, status
        assert "current" in status.detail, status.detail


def test_a_store_never_migrated_is_refused_rather_than_read_as_empty() -> None:
    """The check reads committed state, so a missing table must raise.

    If that read were swallowed into an empty set, "current" would mean
    "empty" and every test above would pass for the wrong reason. This is
    the same vacuity the deleted `UndefinedColumn` catch in
    `run._hold_on_mission_entry` had, reached from the other side: a
    broad catch around the state read turns "cannot tell" into "fine".
    """
    import psycopg

    from tests.conftest_isolation import admin_dsn, dsn_with_dbname

    admin = admin_dsn()
    import uuid

    name = f"s09iso_r10-untouched_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute('CREATE DATABASE "%s"' % name)
    try:
        dsn = dsn_with_dbname(admin, name)
        with pytest.raises(Exception) as raised:
            db.verify_current(dsn, MIGRATIONS)
        assert "schema_migrations" in str(raised.value), str(raised.value)
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name)


# --- 3. The definitions of current that each miss the state that occurred --


def test_a_subset_check_would_pass_the_stale_store() -> None:
    """Why "every recorded name is present" is the wrong predicate.

    This is the check that looks correct and catches nothing: every name
    the stale store records is a file that still exists, so a subset test
    passes on exactly the state that occurred. Asserting the wrong
    predicate here, on a real store, keeps the reason for equality on the
    record instead of in a comment somebody can delete.
    """
    partial = _withheld_dir()
    try:
        with _store("r10-subset", partial) as dsn:
            recorded = _recorded(dsn)
            assert recorded <= ON_DISK, "the subset check would pass a stale store"
            assert not ON_DISK <= recorded, "the stale store is missing a file"
    finally:
        shutil.rmtree(partial, ignore_errors=True)


def test_a_withdrawn_migration_is_refused() -> None:
    """Equality runs both ways: a file the directory no longer names is a fault.

    A high-water mark and a subset check both pass here. The store applied
    the newest migration it knows of, so its version is at the top, and
    every name it records is still a file -- yet it holds a schema from a
    migration this tree has withdrawn. Nothing that only looks forward can
    say so, which is why this case is tested rather than assumed away.
    """
    partial = _withheld_dir()
    try:
        with _store("r10-withdrawn", MIGRATIONS) as dsn:
            with pytest.raises(db.MigrationSetStale) as raised:
                db.verify_current(dsn, partial)
            assert TRAILING in str(raised.value), str(raised.value)
    finally:
        shutil.rmtree(partial, ignore_errors=True)


# --- 4. A caller that means a partial store says so with a directory -------


def test_a_caller_naming_a_partial_directory_is_current_for_it() -> None:
    """How an intended partial store is told from a stale one.

    This is the answer to the objection that a check at apply time would
    refuse every test that builds a partial store deliberately. It would,
    and that is the correct answer: such a caller names the directory it
    means, both when it applies and when it asks. The store was built from
    the nineteen files the directory holds, so the comparison agrees with
    itself and the caller is not forced to disable anything.
    """
    partial = _withheld_dir()
    try:
        with _store("r10-partial", partial) as dsn:
            assert TRAILING not in _recorded(dsn)
            assert db.verify_current(dsn, partial) == {
                p.name for p in partial.glob("*.sql")}
            status = boot.check_database(dsn, partial)
            assert status.exercised is True, status
    finally:
        shutil.rmtree(partial, ignore_errors=True)


# --- 5. The empty-directory refusal survives the move ------------------------


def test_an_empty_directory_is_refused_before_any_connection() -> None:
    """`MigrationSetEmpty` still fires, and now from the shared reader.

    The refusal moved out of `apply_migrations` into `migration_files` so
    `verify_current` cannot accept an empty directory by having nothing
    to compare. Had it, "current" would be vacuously true for every store
    whenever the path was wrong -- the exact failure `MigrationSetEmpty`
    exists to prevent, reintroduced through the fix for it.
    """
    empty = Path(tempfile.mkdtemp(prefix="r10-empty-"))
    try:
        with pytest.raises(db.MigrationSetEmpty):
            db.migration_files(empty)
        with pytest.raises(db.MigrationSetEmpty):
            db.verify_current("dbname=r10-does-not-exist", empty)
    finally:
        shutil.rmtree(empty, ignore_errors=True)


def test_a_second_apply_against_a_narrower_directory_is_refused() -> None:
    """The withholding is caught at the call that did the withholding.

    A24's store was created by a caller that passed a directory missing
    its trailing migration and `apply_migrations` returned. With the
    verification inside the function, that same call raises -- so the
    defect is refused where it is produced, not by a later reader that
    has no way to know what happened. The call is also idempotent in the
    ordinary case, so this is not a store that has to be thrown away.
    """
    partial = _withheld_dir()
    try:
        with _store("r10-second", MIGRATIONS) as dsn:
            assert db.apply_migrations(dsn, MIGRATIONS) == []
            with pytest.raises(db.MigrationSetStale) as raised:
                db.apply_migrations(dsn, partial)
            assert TRAILING in str(raised.value), str(raised.value)
    finally:
        shutil.rmtree(partial, ignore_errors=True)
