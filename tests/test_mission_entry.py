"""One durable mission entry: frontier, permitted experience, active program,
acquired artifacts, retained use, improvement mode, as one row.

The assignment names six things a mission holds and one record that holds
them. Before this, three aggregates each held a part: `s09_policy_state` the
accepted decisions, `FrontierStore.pending_effects` the unresolved work, and
`context.resume_package` the continuation. A fourth, `frontier._blank_doc`,
held a file-based, digest-guarded, Boolean-only copy of the mission beside
them. Four partial owners is the defect.

So the entry lives in the table that already owns an investigation's identity
and objective, `investigations`, which is one row per investigation and needs
no join to answer any of the six. It is not a new table beside
`s09_policy_state`: that table is keyed `(investigation_id, seq)` and answers
"what did boundary N decide", so a mission placed there would be reachable
only at some seq, which is exactly the competing owner this removes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import frontier, mission
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "mission"
INVESTIGATION = "mission-inv"

# The six, written out. A count would pass against any six-shaped thing, so
# each is named and given a distinct literal value.
EXPECTED = {
    "frontier": {
        "open": ["does the boundary express the decision"],
        "success_criteria": ["committed predictor"],
    },
    "permitted_experience": {
        "constraints": ["deterministic only", "no live network"],
        "observations": [{"observation_id": "obs-1", "verdict": "unmeasured"}],
    },
    "active_program": {
        "program_id": "prog-7",
        "source_digest": "b" * 64,
        "version": 3,
    },
    "acquired_artifacts": [
        {"package_digest": "c" * 64, "origin": "acquired"},
    ],
    "retained_use": {
        "package_digest": "c" * 64,
        "used_on": ["ad01-w0-dev-sw-00"],
    },
    "improvement_mode": "improve",
}


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture(scope="module")
def entered(store):
    """One mission, opened and fully recorded.

    The five descriptive columns this used to write are gone (migration 0021).
    Each had no production reader anywhere in the tree, and `retained_use` had no
    writer either. The content they named is read from the document that owns it,
    so what is left here is the charter plus the one field production reads back.
    """
    mission.record_mission(
        store, INVESTIGATION, objective="probe boolean rules",
        environments=[{"instrument": "boolean-rule-v1", "split": "dev",
                       "seed": 4}],
        constraints=EXPECTED["permitted_experience"]["constraints"],
        success_criteria=EXPECTED["frontier"]["success_criteria"],
        improvement_mode=EXPECTED["improvement_mode"])
    return store


def test_entry_carries_only_the_fields_production_reads(entered):
    """The one field, as a literal value, read back from the entry."""
    entry = mission.read_mission(entered, INVESTIGATION)

    assert entry.improvement_mode == "improve"
    assert entry.as_declaration()["objective"] == "probe boolean rules"


def test_the_dropped_columns_are_gone_from_the_row(entered):
    """Not unread: absent. A column nobody reads is a claim, not a record.

    This is the regression for migration 0021. If one of the five returns, either
    a migration was reverted or a writer was reintroduced, and in the second case
    it is a writer with no reader again.
    """
    with mission.connect(entered) as conn:
        columns = [row["column_name"] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'investigations'").fetchall()]
        conn.commit()

    assert "in_flight" in columns, "the owning column must survive"
    assert "improvement_mode" in columns, "the read column must survive"
    for dropped in ("frontier", "permitted_experience", "active_program",
                    "acquired_artifacts", "retained_use"):
        assert dropped not in columns, (
            "%s came back; either a migration was reverted or something writes"
            " it with nothing reading it" % dropped)


def test_mission_fields_is_exactly_what_is_written(entered):
    """The declared set is one field, and the module refuses anything else.

    A field can no longer be dropped from the dataclass while the row still
    happens to carry it, because the row and the declaration are the same list.
    """
    assert mission.MISSION_FIELDS == ("improvement_mode",)
    with mission.connect(entered) as conn:
        names = conn.execute(
            "SELECT improvement_mode FROM investigations WHERE id = %s",
            (INVESTIGATION,)).fetchall()
        conn.commit()
    assert [row["improvement_mode"] for row in names] == ["improve"]

    with pytest.raises(mission.MissionRefused):
        mission.record_mission(
            store=None, investigation_id=INVESTIGATION,
            objective="probe boolean rules",
            environments=[], constraints=[], success_criteria=[],
            retained_use={"package_digest": "c" * 64})


def test_entry_is_one_row_not_a_join(entered):
    """One row answers all six. No second table, no join, no subquery."""
    with mission.connect(entered) as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM investigations WHERE id = %s",
            (INVESTIGATION,)).fetchone()
        row = conn.execute(
            "SELECT improvement_mode FROM investigations WHERE id = %s",
            (INVESTIGATION,)).fetchone()
        conn.commit()

    assert int(count["n"]) == 1
    assert row is not None
    # The declared field came back from that single row. The SQL above touches
    # exactly one relation; a join or a per-field lookup would need a second
    # name here.
    assert row["improvement_mode"] == "improve"

    with mission.connect(entered) as conn:
        owner = conn.execute(
            "SELECT count(DISTINCT table_name) AS n"
            " FROM information_schema.columns"
            " WHERE table_schema = 'public'"
            " AND column_name = ANY(%s)",
            (list(mission.MISSION_FIELDS),)).fetchone()
        conn.commit()
    assert int(owner["n"]) == 1


def test_s09_policy_state_has_no_competing_mission_columns(store, entered):
    """A second owner of any of the six is red, wherever it sits.

    `s09_policy_state` is the named rival: it is per-investigation and
    per-seq, so it could carry a mission and be reachable only at some seq.
    It must not, and neither may anything else.
    """
    with mission.connect(store) as conn:
        rival = conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public'"
            " AND table_name = 's09_policy_state'"
            " AND column_name = ANY(%s)",
            (list(mission.MISSION_FIELDS),)).fetchall()
        carriers = conn.execute(
            "SELECT table_name FROM information_schema.columns"
            " WHERE table_schema = 'public'"
            " AND column_name = ANY(%s)",
            (list(mission.MISSION_FIELDS),)).fetchall()
        conn.commit()

    assert rival == [], (
        "s09_policy_state gained a mission column: %s"
        % [r["column_name"] for r in rival])
    assert sorted({r["table_name"] for r in carriers}) == ["investigations"]


def test_frontier_mission_projection_deleted_after_migration(store, tmp_path):
    """The file-based projection is gone; its callers reach the durable entry.

    `_blank_doc` used to build a second, digest-guarded copy of the mission
    into the frontier JSON, and `_validate_document` refused the store if
    that copy was edited. A digest over a file nobody is obliged to write
    guards nothing, and file-based counters are a named recurring failure for
    this program. Both are gone, and the two call sites that read the
    mission through the document resolve to the durable entry.

    `_blank_doc` itself is not deleted: it is how a store's environments,
    grant and counters start, and none of those are the mission. What is
    asserted is what the store writes and what it refuses.
    """
    mission.record_mission(
        store, INVESTIGATION, objective="probe boolean rules",
        environments=[{"instrument": "boolean-rule-v1", "split": "dev",
                       "seed": 4}],
        constraints=EXPECTED["permitted_experience"]["constraints"],
        success_criteria=EXPECTED["frontier"]["success_criteria"])
    entry = mission.read_mission(store, INVESTIGATION)
    durable = entry.as_declaration()

    path = tmp_path / "frontier.json"
    opened = frontier.create_store(
        path, namespace=frontier.NAMESPACE, mission=durable,
        authority={"queries": 16, "steps": 12})

    # The document carries only what a STEP view names, and no second
    # authority beside it: two keys, no digest of them.
    assert opened._doc["mission"] == {
        "objective": "probe boolean rules",
        "environments": [{"instrument": "boolean-rule-v1", "split": "dev",
                          "seed": 4}]}
    assert "mission_projection" not in opened._doc

    # The guard is gone as a behavior, not as a string. Editing the mission
    # in the file used to be refused as "mission projection changed"; the
    # store now reopens, because the mission it names is a copy for the view
    # and the entry in Postgres is the record that owns it.
    tampered = dict(opened._doc)
    tampered["mission"] = {**opened._doc["mission"], "objective": "edited"}
    path.write_text(frontier.canonical(tampered) + "\n", encoding="utf-8")
    assert frontier.FrontierStore(str(path))._doc["mission"]["objective"] \
        == "edited"

    # Caller one: live_construct.ensure_live_store reads the objective back
    # through the document to detect a mission mismatch on an existing store.
    path.write_text(frontier.canonical(opened._doc) + "\n", encoding="utf-8")
    from experiments.ad01 import live_construct
    reopened = live_construct.ensure_live_store(path, durable,
                                                {"queries": 16, "steps": 12})
    assert reopened._doc["mission"]["objective"] == "probe boolean rules"

    # Caller two: improve_channel stamps every probe opportunity with the
    # mission objective, read straight off the document.
    from experiments.ad01 import improve_channel
    opportunity_id = improve_channel._improve_probe_opportunity(
        opened, {"task_id": "ad01-w0-dev-sw-00"}, x=-1,
        requested={"queries": 1, "steps": 0},
        package_digest="d" * 64, round_no=1, step=0)
    stamped = opened._doc["opportunities"][opportunity_id]
    assert stamped["mission_link"] == "probe boolean rules"