"""A8: the recorder is adopted by construction, for every cell of a study.

`0f4f8c7` closed the creation half of A8. `DecisionRecorder` takes a
`study_root` and a `study_allocation`, seeds its own allocation with that
allocation as the parent, and the store's contamination scanner -- which
resolves a study by walking allocation parentage -- sees the run's
operations. A run with no study is still real, and still says so, through
`orphaned_operations`.

What that half did not survive contact with a second cell. The clamp it
added, `min(wanted, store.allocation_free(parent))`, asks the parent for
every free unit it has. One cell therefore exhausts the study allocation
and the second cell cannot start at all, which is the same study
under-reporting itself from the other direction: not a parentless
allocation this time, but a study that can hold exactly one.

A child allocation's authority has to cover what the run can spend. Each
recorder operation reserves and settles one unit, and the run's decisions
are bounded by its own envelope, so the run can never spend more units
than the envelope has. Asking the parent for more than that is what makes
the second cell unstartable; asking for less would be refused by
`_require_child_capacity` for a run that has room to work.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest


def _cell(dsn: str, campaign: str, study_root: str, allocation_id: str):
    from experiments.ad01 import agenda_policy, selection

    return selection.run_investigations(
        selection.portfolio_for_world(0), agenda_policy.agenda_policy(),
        selection.Allocation(authorized=40), world=0, dsn=dsn,
        campaign=campaign, study_root=study_root,
        study_allocation=allocation_id)


def test_every_cell_of_a_study_is_adopted_by_construction(migrated_db):
    """Two cells, one study, and the scanner sees both of them.

    The first cell is the case the existing tests cover, and it passes for
    the wrong reason: it takes everything the study allocation has left,
    so nothing is available to the second. A study that can host one cell
    is a study whose reported operation count is a function of which cell
    ran first.

    Break by making the second cell refuse, or by letting the first cell
    ask the parent for authority beyond what its own run can spend.
    """
    from settlement import authority, store

    authority.authorize_study(
        migrated_db, "a8multi", authorized=10_000, allocation_id="a8multi-alloc",
        ceilings={"max_operations": 512, "max_development": 512})

    first = _cell(migrated_db, "a8multi-cell0", "a8multi", "a8multi-alloc")
    second = _cell(migrated_db, "a8multi-cell1", "a8multi", "a8multi-alloc")

    for cell in (first, second):
        assert cell.operations, (
            "a cell admitted nothing, so its adoption is untested rather "
            "than repaired")
        assert not cell.refusals, (
            "a cell was refused by the store: %r" % (cell.refusals[:1],))
        assert cell.adopted_operations == len(cell.operations), (
            "the study's own scanner sees %d of %d operations this run "
            "made; invisible: %r"
            % (cell.adopted_operations, len(cell.operations),
               cell.adoption["invisible"]))
        assert cell.orphaned_operations == 0

    assert store.allocation_free(migrated_db, "a8multi-alloc") > 0, (
        "one cell took every free unit of the study allocation, so a "
        "second cell in the same study cannot be started")


def test_a_child_asks_only_for_what_its_own_run_can_spend(migrated_db):
    """The seeded child allocation is bounded, not merely legal.

    `_require_child_capacity` refuses a child larger than its parent's
    free units, and a study that survives its first cell is a study that
    has authority left. Both are satisfied by asking for the whole
    remainder, and only one of them is a reason to do that. Every decision
    a run charges costs at least one unit against its own envelope and
    every recorder operation settles exactly one, so the envelope is a
    bound on how many operations this cell can ever record. A child sized
    to that bound is both sufficient and no larger than it needs to be.

    Break by seeding the child at the parent's full remainder regardless
    of the run's envelope, or by seeding it below what the run can spend.
    """
    from settlement import authority, store

    authority.authorize_study(
        migrated_db, "a8bound", authorized=1_000_000,
        allocation_id="a8bound-alloc",
        ceilings={"max_operations": 512, "max_development": 512})
    free_before = store.allocation_free(migrated_db, "a8bound-alloc")

    run = _cell(migrated_db, "a8bound-cell0", "a8bound", "a8bound-alloc")

    child = store.allocation_status(migrated_db, "a8bound-cell0-a")
    assert child["parent_id"] == "a8bound-alloc", (
        "the child allocation is not parented under the study: %r"
        % child["parent_id"])
    assert 0 < child["authorized"] <= free_before, (
        "the child asked for %d of %d free units"
        % (child["authorized"], free_before))
    assert child["authorized"] <= run.envelope, (
        "the child holds %d units for a run whose envelope is %d; the "
        "surplus is authority no operation of this cell can draw on, and "
        "it is authority the next cell of this study cannot have"
        % (child["authorized"], run.envelope))
    assert store.allocation_free(migrated_db, "a8bound-alloc") > 0, (
        "the child took the study allocation's entire remainder")


@pytest.fixture
def migrated_db():
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db("a8adopt")
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)
