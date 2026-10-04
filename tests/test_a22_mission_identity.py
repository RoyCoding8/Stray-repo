"""The live entry's mission comes from the durable entry, not from a caller.

`frontier.create_store` and `mission.as_declaration` both claimed the mission
dict was `mission.read_declaration` output. It was not: every production
caller passed a hand-built dict, and `read_declaration` had no caller at all.
A declared authority with no reader reads as done.

The tests below pin the repaired boundary. `ensure_live_store` takes a `dsn`
and an `investigation_id` and reads the declaration off the row, so the live
path has an investigation identity and `read_declaration` has its first
caller. Each test names the mechanism it fails on, and each was shown red
against the pre-repair `ensure_live_store` by reverting the read and
re-running, not by argument.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import live_construct as live
from experiments.ad01 import mission
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

# The charter shape `ensure_live_store` accepts, as a fixture. It was a
# production helper with no production caller, deleted in 8d354a5.
from conftest import live_mission

MIGRATIONS = ROOT / "migrations"
# Not bare hex: `s09_run_isolation` refuses the pytest harness's own 8-hex
# run-token space, because a store named in it is indistinguishable from a
# live run's and the stale sweep would reclaim it.
RUN_TOKEN = "a22identity"

INVESTIGATION = "a22-live-identity"
ENVIRONMENTS = [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}]


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture()
def entered(store, request):
    """A migrated store holding one recorded mission entry.

    Module scope for the database, function scope for the row: each test
    records its own entry under its own investigation id, so one test's
    declaration cannot answer another's assertion.
    """
    investigation_id = "a22-%s" % request.node.name.replace("_", "-")
    mission.record_mission(
        store, investigation_id,
        objective=live.LIVE_MISSION_OBJECTIVE,
        environments=ENVIRONMENTS,
        constraints=["deterministic only"],
        success_criteria=["committed predictor"],
        improvement_mode="improve")
    return store, investigation_id


def test_live_store_reads_its_mission_from_the_entry(entered, tmp_path):
    """A store opened by identity names the entry's objective and environments.

    Against the pre-repair `ensure_live_store` there is no way to express this
    at all: the signature takes no `dsn`, so the only mission a caller can
    supply is one it wrote itself.
    """
    dsn, investigation_id = entered

    store = live.ensure_live_store(
        tmp_path / "store.json", None, dict(live.LIVE_AUTHORITY),
        dsn=dsn, investigation_id=investigation_id)

    assert store._doc["mission"] == {
        "objective": live.LIVE_MISSION_OBJECTIVE,
        "environments": ENVIRONMENTS}


def test_read_declaration_is_the_live_paths_reader(entered, tmp_path):
    """The store's mission is the entry's, key for key, on both fields.

    This is the seam the two docstrings claim. It is asserted against the
    read the boundary actually performs, not against a hand-restated literal,
    so it fails if the boundary goes back to trusting its caller.

    The document holds two of the declaration's four charter fields, and that
    is the narrowing `create_store` documents: a STEP view names the
    objective and a reopened store is recognised by its environments. So the
    store is a projection of the declaration, not a copy of it, and the
    assertion compares on the fields the store keeps.
    """
    dsn, investigation_id = entered

    store = live.ensure_live_store(
        tmp_path / "store.json", None, dict(live.LIVE_AUTHORITY),
        dsn=dsn, investigation_id=investigation_id)

    declared = mission.read_declaration(dsn, investigation_id)
    assert store._doc["mission"] == {
        "objective": declared["objective"],
        "environments": declared["environments"]}
    assert set(declared) == {"objective", "environments", "constraints",
                             "success_criteria"}


def test_caller_dict_cannot_override_the_entry(entered, tmp_path):
    """A caller-supplied dict is ignored when the identity is given.

    The point of threading `dsn` is that the entry owns the mission. A
    boundary that reads the entry and then lets the caller's dict win would
    pass the two tests above and still be the defect they were written
    against, so the conflicting dict has to be refused by being overwritten,
    not by being honoured.
    """
    dsn, investigation_id = entered
    invented = {"objective": "an objective the caller invented",
                "environments": [{"instrument": "boolean-rule-v1",
                                  "split": "qual", "seed": 99}],
                "constraints": [], "success_criteria": []}

    store = live.ensure_live_store(
        tmp_path / "store.json", invented, dict(live.LIVE_AUTHORITY),
        dsn=dsn, investigation_id=investigation_id)

    assert store._doc["mission"]["objective"] == live.LIVE_MISSION_OBJECTIVE
    assert store._doc["environments"] == ENVIRONMENTS


def test_reopening_by_identity_keeps_the_entry(entered, tmp_path):
    """The second open reads the same row, and a mismatch is still refused.

    A restarted run re-opens the store by the same identity. If the read were
    skipped on the reopen path the objective check would compare the file
    against itself and never notice that the entry had moved.

    The refusal below was `mission mismatch`, reached by comparing the
    document's objective against the entry's. Now that the live store records
    the investigation that owns it (A27's `StoreIdentity`, wired in by A31),
    naming a *different* investigation is refused earlier and more precisely:
    the store is owned by the first one, so there is nothing to reconcile and
    the objective is never compared. Both are `LiveRefused`, so a caller that
    catches the live refusal still catches this one.
    """
    dsn, investigation_id = entered
    path = tmp_path / "store.json"

    live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                           dsn=dsn, investigation_id=investigation_id)
    reopened = live.ensure_live_store(
        path, None, dict(live.LIVE_AUTHORITY),
        dsn=dsn, investigation_id=investigation_id)

    assert reopened._doc["mission"]["objective"] == live.LIVE_MISSION_OBJECTIVE

    other = "a22-other-investigation"
    mission.record_mission(
        dsn, other, objective="a different objective",
        environments=ENVIRONMENTS)
    with pytest.raises(live.LiveRefused, match="owned by investigation"):
        live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                               dsn=dsn, investigation_id=other)


def test_half_an_identity_is_refused(store, tmp_path):
    """A `dsn` with no investigation, or an investigation with no `dsn`.

    Either half names no entry, so falling back to the caller's dict would
    reopen exactly the defect the keyword arguments were added to close.
    """
    for kwargs in ({"dsn": store},
                   {"investigation_id": INVESTIGATION}):
        with pytest.raises(live.LiveRefused, match="together"):
            live.ensure_live_store(tmp_path / "store.json", None,
                                   dict(live.LIVE_AUTHORITY), **kwargs)


def test_unknown_investigation_refuses_rather_than_inventing(store, tmp_path):
    """A mission entry that does not exist is a refusal, not an empty one.

    Reading a missing row as an empty declaration would open a live store
    with no objective, which `create_store` refuses for a different reason
    and which reads as a store rather than as the failure it is.
    """
    with pytest.raises(mission.MissionRefused):
        live.ensure_live_store(tmp_path / "store.json", None,
                               dict(live.LIVE_AUTHORITY), dsn=store,
                               investigation_id="a22-never-recorded")


def test_live_mission_declares_the_full_charter_shape():
    """`live_mission` produces what `as_declaration` produces.

    It did not: it returned two keys where `MissionEntry.as_declaration`
    returns four. `frontier` reads only the two it uses, so no behaviour
    depended on the difference, which is exactly why it survived.
    """
    declared = live_mission(live.LIVE_MISSION_OBJECTIVE,
                                 ENVIRONMENTS)

    assert declared == mission.MissionEntry(
        investigation_id="unused", objective=live.LIVE_MISSION_OBJECTIVE,
        environments=ENVIRONMENTS, constraints=[],
        success_criteria=[], improvement_mode="improve").as_declaration()


def test_the_live_entry_records_its_own_mission(store, tmp_path):
    """`_run_frontier_investigation`'s mission recorder writes what it reads.

    The production entry has to record the row it later reads, or the read
    has nothing to answer. The recorder is exercised here directly because
    the full function needs a model route; the identity it derives and the
    declaration it produces are both asserted.
    """
    from scripts import invl02_live as driver

    freeze = {"study_root": "invl02-live-e0", "run_id": "a22run0001",
              "charter": {"objective": live.LIVE_MISSION_OBJECTIVE},
              "tasks": [], "use_tasks": [], "boolean_seeds": {}}
    investigation_id = driver._live_investigation_id(freeze, "control")

    assert investigation_id == "invl02-live-e0-a22run0001-control"

    driver._record_live_mission(store, investigation_id, freeze)

    assert mission.read_declaration(store, investigation_id) == {
        "objective": live.LIVE_MISSION_OBJECTIVE,
        "environments": driver._live_environments(freeze),
        "constraints": [], "success_criteria": []}


def test_improvement_mode_has_a_reader(store, entered, tmp_path):
    """The constrained mode is read back, and the live path consumes it.

    `improvement_mode` is CHECK-constrained because it "decides which executor
    holds authority", and before this it had no reader at all: a mode written
    and never consulted is a decision that records as done. The reader exists
    and returns each recorded mode, and the live path's own entry is read
    through it rather than assumed.

    The live path's refusal of an `operate` entry is a guard on that read, but
    it is not reachable end-to-end: `_record_live_mission` writes `improve` on
    every entry it opens, so the entry it then reads is always `improve`. The
    guard is asserted here as the check it performs, not as a path that fires.
    """
    dsn, investigation_id = entered

    assert mission.read_improvement_mode(dsn, investigation_id) == "improve"

    operating = "a22-operating-mission"
    mission.record_mission(
        dsn, operating, objective=live.LIVE_MISSION_OBJECTIVE,
        environments=ENVIRONMENTS, improvement_mode="operate")

    assert mission.read_improvement_mode(dsn, operating) == "operate"

    with pytest.raises(mission.MissionRefused):
        mission.read_improvement_mode(dsn, "a22-never-recorded")


def test_two_arms_of_one_run_are_two_investigations():
    """The control arm and the live arm do not share a mission entry.

    They share a study root and a run id, so an id keyed on either alone
    would have the live arm's recorder overwrite the control arm's charter.
    """
    from scripts import invl02_live as driver

    freeze = {"study_root": "invl02-live-e0", "run_id": "a22run0001"}

    assert driver._live_investigation_id(freeze, "control") != \
        driver._live_investigation_id(freeze, "live")
    assert driver._live_investigation_id(
        {**freeze, "run_id": "a22run0002"}, "control") != \
        driver._live_investigation_id(freeze, "control")


def test_every_live_store_caller_threads_an_identity():
    """No production caller reaches `ensure_live_store` with a bare dict.

    The defect was a docstring describing a read that no caller performed.
    Asserting the call sites keeps it that way: a new live caller that
    hand-builds a mission has to be counted here, because the docstrings
    would otherwise be describing it.
    """
    import ast

    tree = ast.parse(
        (ROOT / "scripts" / "invl02_live.py").read_text(encoding="utf-8"))
    sites = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "ensure_live_store"]
    assert sites, "the live entry no longer calls ensure_live_store"
    for site in sites:
        keywords = {kw.arg for kw in site.keywords}
        assert {"dsn", "investigation_id"} <= keywords, (
            "a live store is opened without naming its mission")
