"""One quiescence predicate, on the durable row, in one vocabulary.

`FrontierStore.is_quiescent` and `mission.IN_FLIGHT_STATES` were both called
"still going" and shared no status string. They are not two names for one
thing. The frontier's list lives in a JSON document in a file, is keyed on
opportunities, and its states are `pending` and `settled`; the mission entry's
list lives in a SQL column, is keyed on attempts, and its states are `held`,
`restored` and `suspended`. Nothing in the repository writes a frontier effect
into `investigations.in_flight` or an in-flight row into `pending_effects`, and
`StoreIdentity.dsn` -- the field that was supposed to route one to the other --
is validated, never persisted and never dereferenced. So the disjointness is
two records of two different units of work, not one duplicated enumeration.

What that leaves is a question the durable side could not answer at all:
whether an investigation has admitted work it has not run. Three vocabularies
were answering adjacent versions of it -- `pending`/`settled` in the document,
`held`/`restored`/`suspended` on the entry, `accepted`/`incorporated` plus
`effect_record IS NULL` on `s09_policy_state` -- and none of them was a
predicate over the row. `mission.is_quiescent` is that predicate, and it reads
the in-flight list alone, which is the only one of the three that `mission`
owns.

Each test gets its own investigation, so no test's admission is another test's
starting state.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import frontier, mission
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import boolean_rule as br
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a34q"

DECISION = {"basis_references": [],
            "question": "does the boundary express the decision",
            "next_action": {"kind": "development", "task_id": "dev-task-0",
                            "max_queries": 16}}

OPPORTUNITY = {
    "opportunity_id": "opp-first",
    "mission_link": "probe boolean rules",
    "question": "what does input 3 reveal on the dev rule task",
    "intervention": {"instrument": "boolean-rule-v1",
                     "target": "rule-dev-0004", "inputs": {"x": 3}},
    "resources": {"queries": 1, "steps": 1}}


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture()
def inv(store):
    """One recorded mission, its own row, so no test inherits an admission."""
    investigation_id = "a34q-%s" % uuid.uuid4().hex[:10]
    mission.record_mission(
        store, investigation_id, objective="probe boolean rules",
        environments=[{"instrument": "boolean-rule-v1", "split": "dev",
                       "seed": 4}])
    return investigation_id


def _admit(dsn: str, investigation_id: str, attempt_id: str,
           *, seq: int = 0) -> None:
    mission.admit_operation(
        dsn, investigation_id, seq=seq, attempt_id=attempt_id,
        decision=DECISION, program_digest="d" * 64, task_id="dev-task-0",
        capability_id="seed-sw-greedy")


def _live_store(path, identity):
    store = frontier.create_store(
        path, namespace=frontier.NAMESPACE,
        mission={"objective": "probe boolean rules",
                 "environments": [{"instrument": "boolean-rule-v1",
                                   "split": "dev", "seed": 4}]},
        authority={"queries": 32, "steps": 16}, identity=identity)
    store.propose(dict(OPPORTUNITY))
    return store


def test_a_fresh_mission_is_quiescent(store, inv):
    """A recorded mission with nothing admitted reads as quiescent.

    The yes case with nothing injected. A predicate that refused everything
    would pass every "must not be quiescent" test, so the empty admission is
    asserted here on its own: it is the state a study is in between
    boundaries, and it is genuinely finished work.
    """
    assert mission.read_in_flight(store, inv) == []
    assert mission.is_quiescent(store, inv) is True


def test_an_admitted_operation_is_not_quiescent(store, inv):
    """One admitted, unrun operation is not quiescence. The no case."""
    _admit(store, inv, "a34q-held-0")

    assert mission.is_quiescent(store, inv) is False


@pytest.mark.parametrize("state", ["held", "restored", "suspended"])
def test_every_in_flight_state_is_not_quiescent(store, inv, state):
    """All three of the column's own states, each reached as its own writer
    reaches it.

    Not by writing the literal into the column. `resume_operation` is what
    makes a state `restored`. `suspended` is declared by `IN_FLIGHT_STATES` and
    is what a barrier records, so it is written as a barrier writes it: the
    same list with one entry's `status` and `barrier_ref` replaced. No barrier
    caller exists in this tree, so the fixture writes it directly rather than
    inventing a seam to call.

    If a state were added to the column later and turned out to mean the work
    is finished, this is the test that says so.
    """
    _admit(store, inv, "a34q-all-%s" % state)
    if state == "restored":
        mission.resume_operation(store, inv)
    elif state == "suspended":
        with mission.connect(store) as conn:
            conn.execute(
                "UPDATE investigations"
                " SET in_flight = jsonb_set("
                " jsonb_set(in_flight, '{0,status}', %s::jsonb),"
                " '{0,barrier_ref}', to_jsonb(%s::text)),"
                " updated_at = now() WHERE id = %s",
                ('"suspended"', "barrier-a34q", inv))
            conn.commit()

    assert [item.status for item in mission.read_in_flight(store, inv)] \
        == [state]
    assert mission.is_quiescent(store, inv) is False


def test_a_resumed_operation_is_still_not_quiescent(store, inv):
    """Resuming is not settling. Both reads, before and after.

    The false green this guards: a predicate that read the column's `status`
    field and treated anything but `held` as finished would report a resumed
    investigation as quiescent while every operation in it is still to run.
    Restoration is explicitly not execution -- `resume_operation` writes no
    effect record and runs nothing -- so the row is more live after a resume,
    not less.
    """
    _admit(store, inv, "a34q-resume-0")
    assert mission.is_quiescent(store, inv) is False

    restored = mission.resume_operation(store, inv)

    assert [item.status for item in restored] == ["restored"]
    assert mission.is_quiescent(store, inv) is False


def test_two_operations_are_not_quiescent_while_either_remains(store, inv):
    """The predicate counts the list, so one survivor still holds it open.

    A predicate that asked about one attempt would answer a question that was
    not asked. This is the reason the signature takes an investigation and not
    an attempt id: the answer is about the whole entry.
    """
    _admit(store, inv, "a34q-two-0")
    _admit(store, inv, "a34q-two-1", seq=1)
    assert len(mission.read_in_flight(store, inv)) == 2

    mission.release_operation(store, inv, "a34q-two-0")
    assert mission.is_quiescent(store, inv) is False

    mission.release_operation(store, inv, "a34q-two-1")
    assert mission.is_quiescent(store, inv) is True


def test_an_absent_investigation_is_refused_not_quiescent(store):
    """No row is not a finished investigation. The refusal, not a True.

    `read_in_flight` raises for an absent investigation rather than returning
    an empty list, so a predicate returning True here would be the one reader
    in the module that calls a mission which was never recorded a finished
    one. A caller gating a decision on this would proceed against nothing.
    """
    with pytest.raises(mission.MissionRefused) as refusal:
        mission.is_quiescent(store, "a34q-never-recorded")
    assert str(refusal.value) == (
        "no mission for investigation %r" % "a34q-never-recorded")


def test_a_status_the_module_cannot_read_is_not_quiescent(store, inv):
    """An uninterpretable entry is a refusal from the reader, not from this.

    `InFlightOperation.from_json` raises on a status outside
    `IN_FLIGHT_STATES`, so a column entry this module cannot read is visible
    as an error. The predicate deliberately does not inherit that: it counts
    the row's entries, so a corrupt one reads back as "not quiescent" -- the
    conservative answer, and the one a caller gating on quiescence can act on.

    Fault injection in the direction that matters. A predicate reading the
    column's `status` would have to enumerate the values that mean finished,
    and an unrecognised one would either pass as finished or raise.
    """
    _admit(store, inv, "a34q-corrupt-0")
    with mission.connect(store) as conn:
        conn.execute(
            "UPDATE investigations SET in_flight = jsonb_set("
            " in_flight, '{0,status}', %s::jsonb),"
            " updated_at = now() WHERE id = %s",
            ('"quiescent"', inv))
        conn.commit()

    assert mission.is_quiescent(store, inv) is False
    with pytest.raises(mission.MissionRefused) as refusal:
        mission.read_in_flight(store, inv)
    assert str(refusal.value) == "unknown in-flight state 'quiescent'"

    with mission.connect(store) as conn:
        conn.execute(
            "UPDATE investigations SET in_flight = '[]'::jsonb,"
            " updated_at = now() WHERE id = %s", (inv,))
        conn.commit()
    assert mission.is_quiescent(store, inv) is True


def test_a_frontier_effect_is_not_an_in_flight_operation(store, inv,
                                                         tmp_path):
    """The measurement, pinned: two records of two different units of work.

    A store is opened under a real `StoreIdentity` naming this investigation
    -- both names, the `dsn` included, exactly as
    `live_construct.ensure_live_store` builds one for a live arm -- and one
    effect is admitted and left unrun.

    The store's own quiescence says False. The mission entry's says True, and
    keeps saying True after the effect settles. They are not two names for one
    thing: the effect is keyed on an opportunity and lives in a file, the
    in-flight row is keyed on an attempt and lives in the row, and nothing
    carries one to the other. Folding the document's list into this predicate
    would make a durable answer depend on a file, and would report quiescent
    while a frontier effect is still to settle.
    """
    live = _live_store(tmp_path / "frontier.json",
                       frontier.StoreIdentity(investigation_id=inv,
                                              dsn=store))

    package = channel.make_control("low")
    live.bind_active(package)
    effect = live.accept("opp-first", package["package_digest"])
    assert effect["status"] == "pending"
    assert live.is_quiescent() is False

    assert mission.is_quiescent(store, inv) is True, (
        "the mission entry grew a frontier effect it never wrote")

    task = br.make_task("dev", 4)
    channel.execute_operate_action(
        live, {"kind": "probe",
               "inputs": {"opportunity_id": "opp-first", "x": 3},
               "requested_resources": {"queries": 1, "steps": 1}}, task)
    live.settle(effect["effect_id"], live.observations[-1])

    assert live.is_quiescent() is True
    assert mission.is_quiescent(store, inv) is True
    assert live.identity.investigation_id == inv


def test_an_unresolved_boundary_row_is_not_an_in_flight_operation(store, inv):
    """The third vocabulary is separate too, and is named here.

    `s09_policy_state` records an accepted action whose effect has not run as
    `accepted` with a null `effect_record`, and every reader treats that pair
    as the unsettled signal (`trajectory.py:374`, `_s09_incorporate` is the
    only writer that moves it). It is a row per boundary on a table this
    module does not own, and a boundary drained by the `legacy-drain` path
    writes it without ever calling `admit_operation`.

    So an investigation with an unresolved boundary and an empty in-flight
    list is a state that really occurs, and this predicate answers True for
    it. That is the honest answer for the column it owns, and it is why
    "quiescence" was never one predicate: three vocabularies answer three
    different questions, and only this one is about the mission entry.
    """
    with mission.connect(store) as conn:
        conn.execute(
            "INSERT INTO s09_policy_state"
            " (investigation_id, seq, attempt_id, effect_id, accepted_action)"
            " VALUES (%s, 0, %s, %s, %s::jsonb)",
            (inv, "att-%s-0" % inv, "eff-%s-0" % inv,
             '{"status": "pending"}'))
        conn.commit()
        row = conn.execute(
            "SELECT status, effect_record FROM s09_policy_state"
            " WHERE investigation_id = %s", (inv,)).fetchone()
        conn.commit()

    assert row["status"] == "accepted" and row["effect_record"] is None, (
        "the boundary row is not in the unsettled state this test needs: %r"
        % dict(row))

    assert mission.read_in_flight(store, inv) == []
    assert mission.is_quiescent(store, inv) is True


def test_the_frontier_keeps_its_own_two_states(tmp_path):
    """`is_quiescent` on the store is unchanged and is its own predicate.

    Named so the two cannot be mistaken for one implementation later. The
    store's answer is about the document it holds open in memory; the entry's
    is about the row. Both are true at once in the test above, and neither
    answers for the other.
    """
    live = _live_store(tmp_path / "own.json", None)

    assert live.is_quiescent() is True
    assert live.pending_effects == []
    assert live.settled_effects == []


def test_release_deletes_and_the_predicate_follows_the_deletion(store, inv):
    """Settlement removes the row, so it is the absence of a row, not a state.

    The asymmetry this lane was told not to repair, pinned so a later repair
    is a deliberate change and not a drift. `release_operation` is the only
    writer that removes an entry and it removes rather than marks, which is
    why the predicate has no `settled` state to read: on this side of the
    module, "settled" is the absence of a row. The document side is the
    opposite -- `settle` writes the value `settled` and keeps the row -- which
    is the same word with the opposite lifecycle, and the clearest single
    reason the two vocabularies are not one.
    """
    _admit(store, inv, "a34q-release-0")
    assert mission.is_quiescent(store, inv) is False

    mission.release_operation(store, inv, "a34q-release-0")

    assert mission.is_quiescent(store, inv) is True
    assert mission.read_in_flight(store, inv) == []