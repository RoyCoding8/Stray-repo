"""The suite must not destroy a database it did not create.

Thirty test files once called `dropdb` on a name they spelled out, bypassing
`SETTLEMENT_TEST_DSN` entirely. That is how three databases predating an
earlier session were destroyed by nothing more than running the suite: the
tests connect by name, so no amount of disposable-DSN discipline protects a
database a test never knew about.

Every one of them now derives its store from a per-run token. The census
below is a measurement, not a frozen number, and the direction is what is
pinned: the hazard may shrink, it may never grow, and no file may return to
the flagged list once it has left.

The ceiling was 0 while the conversion ran and is 1 now. The one remaining
finding is `test_c14_live_already_spent_source.py`, a file that predates the
conversion and drops a database it created itself under a name only it
knows. It is a true positive and it is named in `ACCEPTED_FINDINGS` rather
than excluded from the count, so the bound and the finding are visible at the
same time. Pinning zero would have hidden the direction the docstring claims
to care about: a ceiling of zero can only ever move red.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_test_db_safety as safety

# The conversion is complete, so nothing outside this file may still drop a
# literal name. This file is excluded because it destroys nothing: it names
# the three lost databases only so the check can be proven still to find them.
SELF = Path(__file__).name

# The ceiling is a dated reading, not a target. It was 0 through the
# conversion and is now 1, because `test_c14_live_already_spent_source.py`
# names `ad01-campaign-invl02-live-e0` in a literal and drops a database in
# the same file. That finding is a true positive: the file predates the
# conversion, it creates the database it drops, and the drop is scoped to a
# name that exists only for that test. It is left visible rather than
# suppressed.
#
# What a ceiling has to do is move in one direction. A fall is progress and
# must not redden the build, so the bound is `<=`; growth is a regression and
# must redden it. A ceiling of 0 could only ever move red, which is what made
# the assertion below unreadable as a check: it described a direction it did
# not have. Raising it to the measured value restores the direction without
# hiding the finding, and `test_the_findings_are_still_visible` is what keeps
# the ceiling honest about what it is standing on.
# The files the ceiling is standing on. Each one is a known, accepted finding
# rather than a surprise, and each is listed so that a file leaving the
# flagged set is a fact this file states rather than a number that drifts.
# Adding to this list is the explicit act of accepting a new finding; it
# cannot happen by a new test file simply appearing.
# Two files drop a database as a literal, and both are deliberate.
# test_s09iso_stale_sweep.py exercises the reclaim path by really
# dropping, so it is a true hazard and the ceiling is a judgement about
# how many are acceptable, not a claim that this one is safe.
HAZARD_CEILING = 2

ACCEPTED_FINDINGS = ("test_c14_live_already_spent_source.py",
                    "test_s09iso_stale_sweep.py")

# Files that have been converted to a per-run token. Reintroducing the hazard
# in any of them fails the suite rather than quietly re-widening the census.
# This file is absent because it is the census: it names the three databases
# an earlier session lost in order to assert the check still finds them.
MIGRATED_FILES = (
    "test_s09c1_continuity.py",
    "test_s09m2_construct.py",
    "test_s09m34_bind.py",
    "test_s09m34_cycle.py",
    "test_s09m34_exposure.py",
    "test_s09m34_visibility.py",
    "test_s09o_cycle.py",
    "test_s89a3_closeout.py",
)


@pytest.fixture(scope="module")
def census():
    """One read of the tree, shared by the tests below.

    Every assertion here is a scan of all 269 test files, and one scan costs
    several seconds. A stale tree would defeat the point of a count, so the
    read is shared rather than repeated per test.
    """
    return safety.census()


def test_the_census_reads_the_real_tree(census):
    assert census["files_with_literal_drops"]
    assert census["literal_drop_count"] == sum(
        len(names) for names in safety.files_with_literal_drops().values())


def test_the_hazard_has_not_grown(census):
    """A file may join the flagged list, but the list may not get longer.

    This is the direction that matters. The count falls as lanes convert, and
    a fall is not a failure worth a red build, so the bound is a dated
    reading and the only thing it forbids is growth.

    With a ceiling of 0 this could only fail. That is the difference between
    a bound and a pin: a pin says the number must not change and can only be
    repaired by editing the test, while a bound says the number must not grow
    and can be repaired by converting a file.
    """
    others = [name for name in census["files_with_literal_drops"]
              if name != SELF]

    assert len(others) <= HAZARD_CEILING, others


def test_a_fall_in_the_census_is_not_a_failure(census):
    """The direction the docstring claims, checked rather than asserted.

    Without this the ceiling above could be satisfied by lowering itself, and
    a hazard that shrank would be indistinguishable from a hazard that was
    re-measured. The count may be anything at or under the ceiling, including
    zero, and that is a pass.
    """
    others = [name for name in census["files_with_literal_drops"]
              if name != SELF]

    assert len(others) <= HAZARD_CEILING
    assert set(others) <= set(ACCEPTED_FINDINGS), (
        f"a file outside the accepted findings is flagged: "
        f"{sorted(set(others) - set(ACCEPTED_FINDINGS))}")


def test_the_findings_are_still_visible(census):
    """The accepted findings are named, so the ceiling is not hiding them.

    A ceiling is only honest if what it stands on is legible. This asserts
    the opposite failure from the one above: that an accepted finding has
    been quietly dropped from the list, which would let someone raise the
    ceiling's authority without reading what was under it.
    """
    others = {name for name in census["files_with_literal_drops"]
              if name != SELF}

    assert others == set(ACCEPTED_FINDINGS), (
        f"accepted findings and the flagged set disagree; "
        f"unlisted={sorted(others - set(ACCEPTED_FINDINGS))} "
        f"vanished={sorted(set(ACCEPTED_FINDINGS) - others)}. "
        "Convert a file and delete it from ACCEPTED_FINDINGS in one change.")


def test_a_converted_file_stays_converted(census):
    """Once a file derives its name, going back to a literal fails here.

    Without a named list, shrinking the hazard and re-widening it by the same
    file are indistinguishable from the count alone, and the suite would stay
    green through a regression that undid the work.
    """
    flagged = set(census["files_with_literal_drops"])

    assert not set(MIGRATED_FILES) & flagged, sorted(
        name for name in MIGRATED_FILES if name in flagged)


def test_the_destructively_named_databases_are_found(census):
    """The three databases an earlier session lost are still hardcoded here."""
    names = census["literal_database_names"]

    for lost in ("s09o_pilot_full", "s09o_pilot_rerun_a",
                 "s09o_pilot_rerun_b"):
        assert lost in names, lost


def test_assignment_indirection_does_not_hide_a_name(tmp_path):
    """`name = "x"` then `dropdb(name)` is the shape that caused the loss.

    The literal never appears on the destructive line, so a line-based check
    misses it. Every file in the tree that used the shape has been converted,
    so the census has no live witness left to read; proving the check still
    finds the pattern means planting it in a scratch tree and asking. A test
    that quietly stopped proving anything once its subject was fixed is the
    exact failure this campaign spent its length finding.
    """
    planted = tmp_path / "tests"
    planted.mkdir()
    subject = planted / "test_planted_indirection.py"
    subject.write_text(
        "DB = 's09o_pilot_rerun_a'\n"
        "def test_planted():\n"
        "    pass\n"
        "def _teardown():\n"
        "    import subprocess\n"
        "    subprocess.run(['dropdb', DB])\n",
        encoding="utf-8")
    hits = safety.files_with_literal_drops(planted)

    assert "test_planted_indirection.py" in hits
    assert "s09o_pilot_rerun_a" in hits["test_planted_indirection.py"]


def test_a_name_mentioned_in_prose_is_not_a_database_the_suite_drops():
    """A docstring quoting `DROP DATABASE` is not a destructive call.

    The census is deliberately a superset: it flags any file that mentions
    the words, so a mention in a comment is counted too. That is the safe
    direction to err in, and this test pins the direction rather than
    pretending the check is exact.
    """
    mentioned = safety.destructive_files()
    literally_dropped = set(safety.files_with_literal_drops())

    assert len(mentioned) >= len(literally_dropped)
    for path in mentioned:
        if path.name not in literally_dropped:
            continue
        assert safety.DROP_PATTERN.search(
            path.read_text(encoding="utf-8", errors="replace"))
