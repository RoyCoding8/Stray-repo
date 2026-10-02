"""A8 in production: the ladder's own recorder is adopted by its own study.

`0f4f8c7` gave `selection.DecisionRecorder` a `study_root` and a
`study_allocation` and proved the mechanism in a test that called the
recorder directly. Nothing in the ladder called it that way. The four
`run_investigations` call sites in the E3 modules are not four
unadopted runs:

* `e3_ladder._run_arm` and `e3_ladder.divergence_survey` pass no `dsn`,
  so they build no recorder at all. They are the offline half, and there
  is nothing in a store for them to be adopted into.
* `s09_e3_selection.run_policy` reaches a store only through
  `store_witness`, which is handed a bare dsn and never binds a study.
  Adopting it would mean minting a study root for the sever control,
  and no E3 selection root is in `offline_recompute.AUTHORITATIVE_STUDY_ROOTS`.
  The study identity of that witness is not a decision this repair may make.
* `e3_ladder.store_ladder` receives `study_root` as an argument, has one
  bound to it by every caller, and threads it into the operation it
  never forwards to the recorder.

That last one is the defect in the run that matters, and it is the one
under test. Its recorder seeded a parentless per-cell allocation, so its
operations were real, settled and receipted while sitting outside the
study's subtree. `e3_ladder.store_verdict` named the resulting split as
the run's headline finding, and `tests/test_s09_e3_ladder.py` pinned the
split with `assert not verdict["walk_agrees_with_prefix"]`, so the
ladder reported a blind spot in the store's own contamination scanner
and passed for having found it.

The assertions here read through `s09_run_isolation._persisted_operations`,
which is the scanner the isolation gate actually uses, rather than
through the ladder's own walk. A test that measured the walk against
itself would pass whether or not the real gate could see the work.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest


def _study_operation_ids(dsn: str, study_root: str) -> set:
    """What the store's own isolation gate finds for ``study_root``."""
    from experiments.ad01 import s09_run_isolation as iso

    return {row["id"] for row in iso._persisted_operations(dsn, study_root)}


@pytest.fixture
def migrated_db():
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db("a8prod")
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)


@pytest.fixture
def study(migrated_db):
    import contextlib

    from settlement import authority

    from experiments.ad01 import e3_ladder

    @contextlib.contextmanager
    def bind():
        handle = authority.authorize_study(
            migrated_db, e3_ladder.STUDY_ROOT, authorized=100_000,
            allocation_id=e3_ladder.STUDY_ALLOCATION,
            ceilings={"max_operations": 512, "max_development": 512})
        try:
            yield handle.study_root
        finally:
            _wipe(migrated_db, e3_ladder.STUDY_ALLOCATION)

    return bind()


def _wipe(dsn: str, allocation_id: str) -> None:
    import contextlib

    from settlement import db

    with contextlib.suppress(Exception):
        with db.connect(dsn) as conn:
            conn.execute("DELETE FROM operations WHERE allocation_id LIKE %s"
                         " OR allocation_id LIKE %s",
                         (allocation_id + "/%", "ad01-e3ladder-root-%"))
            conn.execute("DELETE FROM receipts WHERE operation_id NOT IN"
                         " (SELECT id FROM operations)")
            conn.execute("DELETE FROM allocations WHERE id LIKE %s",
                         (allocation_id + "/%",))
            conn.execute("DELETE FROM allocations WHERE id LIKE %s",
                         ("e3ladder-root-%",))
            conn.execute("DELETE FROM study_authority WHERE allocation_id = %s",
                         (allocation_id,))
            conn.commit()


def test_the_ladders_own_recorder_is_adopted_by_the_study_it_runs_under(migrated_db, study):
    """Both admission paths land in one subtree, and the gate sees all of it.

    The recorder is the run's own record of the decisions it made while
    making them, and `admit_study_call` is the study's durable
    reservation owner. Both are the same study's work, so a contamination
    read scoped to that study has to return both. It returned one.

    Break by dropping the `study_root=` and `study_allocation=` arguments
    from the `run_investigations` call in `store_ladder`, or by seeding
    the child with a `parent_id` other than the study's own allocation.
    """
    from experiments.ad01 import e3_ladder

    with study as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)

        recorder = sum(arm["recorder_admitted"] for arm in payload["arms"])
        assert recorder > 0, (
            "the run's own recorder admitted nothing, so its adoption is "
            "untested rather than repaired")
        assert not [a for a in payload["arms"] if a["refused"]], (
            "a cell was refused: %r"
            % [a["refused"] for a in payload["arms"] if a["refused"]])

        verdict = e3_ladder.store_verdict(migrated_db, study_root)
        seen = _study_operation_ids(migrated_db, study_root)
        assert len(seen) == verdict["operations_in_store"], (
            "the store's own isolation scanner returned %d of the %d "
            "operations this study made, so %d of them are outside every "
            "study-scoped read: %r"
            % (len(seen), verdict["operations_in_store"],
               verdict["operations_in_store"] - len(seen),
               verdict["walk_missed"][:3]))

        assert sum(arm["recorder_orphaned"] for arm in payload["arms"]) == 0, (
            "%d operations the ladder really made are outside every "
            "study-scoped read"
            % sum(arm["recorder_orphaned"] for arm in payload["arms"]))
        assert verdict["walk_agrees_with_prefix"], (
            "the parentage walk found %d of %d operations, so the two reads "
            "of the same study still disagree"
            % (verdict["walked_operation_count"],
               verdict["operations_in_store"]))
        assert verdict["walk_missed"] == []
        assert verdict["every_counted_operation_is_this_study"]
        assert verdict["every_recorder_operation_is_adopted_under_the_study"]


def test_the_recorder_is_still_a_second_admission_path(migrated_db, study):
    """Adoption must not have collapsed the two trees into one.

    The repair parents the recorder's allocation under the study. It
    does not make the recorder's path the same as `admit_study_call`'s,
    and `per_path` is what shows the two are still separately exercised.
    A fix that stopped admitting through the recorder at all would pass
    the adoption test above with an empty second tree.

    Break by classifying the recorder's children as `admit_study_call`,
    or by making the second tree empty.
    """
    from experiments.ad01 import e3_ladder

    with study as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)
        verdict = e3_ladder.store_verdict(migrated_db, study_root)

        assert verdict["per_path"]["admit_study_call"] > 0
        assert verdict["per_path"]["decision_recorder"] > 0, (
            "the recorder admitted nothing, so the second tree is untested")
        assert sum(verdict["per_path"].values()) == \
            verdict["operations_in_store"]
        assert verdict["per_path"]["decision_recorder"] == \
            sum(arm["recorder_admitted"] for arm in payload["arms"])


def test_the_cap_sheet_bounds_both_admission_paths(migrated_db, study):
    """The study's ceiling has to cover the work, not one of the two trees.

    Before adoption the recorder's operations sat outside the study's
    allocation subtree, so `_study_operation_counts` could not see them
    and `max_operations` under-counted the study against itself. Adoption
    fixes the count and creates the hazard: the ceiling now refuses work
    it used to be blind to. A cap derived from the widest cell alone
    bounds one tree and leaves the other to hit the limit.

    Break by sizing `max_operations` from one path, or by authorizing
    under a ceiling below the operations the matrix actually writes.
    """
    from experiments.ad01 import e3_ladder
    from settlement import authority

    cap = e3_ladder.cap_sheet(e3_ladder.ladder(shared=False, worlds=(0,)),
                              study_root=e3_ladder.STUDY_ROOT,
                              authorized_units=100_000)
    ceiling = e3_ladder.study_ceilings(cap)
    assert ceiling["max_operations"] > 0

    import contextlib

    @contextlib.contextmanager
    def tight():
        handle = authority.authorize_study(
            migrated_db, e3_ladder.STUDY_ROOT, authorized=100_000,
            allocation_id=e3_ladder.STUDY_ALLOCATION, ceilings=ceiling)
        try:
            yield handle.study_root
        finally:
            _wipe(migrated_db, e3_ladder.STUDY_ALLOCATION)

    with tight() as study_root:
        payload = e3_ladder.store_ladder(migrated_db, study_root)
        verdict = e3_ladder.store_verdict(migrated_db, study_root)

    assert not [a for a in payload["arms"] if a["refused"]], (
        "the production cap sheet refused %d decisions, so it does not "
        "bound the matrix the study actually runs"
        % sum(len(a["refused"]) for a in payload["arms"]))
    assert verdict["operations_in_store"] <= ceiling["max_operations"], (
        "the study wrote %d operations under a ceiling of %d"
        % (verdict["operations_in_store"], ceiling["max_operations"]))
