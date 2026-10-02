"""B3: the repertoire admits a method acquired on a prior task.

`RETENTION_BLOCKER` named two things as necessary and neither existed
(`experiments/ad01/w2_retention_campaign.py:176-200`). This module is the
repair of both, and every literal below is measured on the frozen world by
running the member's own bytes through the frozen checkers, never asserted
from a docstring.

**The default repertoire is still closed, and that is still true.** The four
authored seed ids are still the whole of it, `default_repertoire()` with no
argument still returns them, and `tests/test_ad01_w2_retention.py:66-78`
still passes unedited. What changes is that closure is no longer the only
reachable state: a repertoire can now carry an acquired member, and the
eligible set for a task is derived from the repertoire in hand rather than
from a constant.

**Why an arrived member cannot execute by id alone.** `_resolve_method`
resolves a named `method_id` through `seeds.SEED_CAPABILITIES` and refuses
anything else, and that function is not this lane's to edit. So the arrival
path is the one the codebase already has for acquired bytes: the action
carries `method_source` and `entry` beside `method_id`, which is what
`trajectory._use_retained_method` and every `ctl-` control member already do.
The id is the name a policy selects from `eligible_methods`; the bytes are
the method. A policy naming the id alone is refused by the executor, and
that refusal is recorded rather than papered over.

**The fixture's origin is `fixture-stand-in`, and the label is the claim.**
These bytes were written here, not acquired from a provider. The lane is
offline and makes no live call. What the fixture proves is the mechanism:
that an arrived member's verdict is a property of the task it is carried to,
and not a constant.

**The verdicts below are measured, and they vary for fixed bytes.** One
member, whose bytes name the two op keys an acquisition on
`ad01-w0-dev-sw-00` would have kept, is carried to three tasks. It is
`preserved` on the task it was acquired on and on `within-sw-02`, and
`not_preserved` on `transfer-sw-00`. The reduction the campaign scores is
0.0 on the last and positive on the first, so two arms differing only in
whether they hold this member differ in `method_id` and in the scored
observable, and the panel is held identical across the pair.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from experiments.ad01 import assessment_profile
from experiments.ad01 import e2_replication as replica
from experiments.ad01 import method_exec
from experiments.ad01 import trajectory
from experiments.ad01 import worlds
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"

ACQUIRED_ON = "ad01-w0-dev-sw-00"
CARRIED_TO_PRESERVED = "ad01-w0-within-sw-02"
CARRIED_TO_REJECTED = "ad01-w0-transfer-sw-00"

MEMBER_ID = "acquired-sw-carried-keys"
ORIGIN = "fixture-stand-in"

# The op keys an acquisition on ACQUIRED_ON would have kept. They are the
# member's content, and the member's bytes name them as a literal, so what
# transfers is the knowledge and not a copy of the task.
CARRIED_KEYS = ("b", "o0")

# A member that returns its own input: a reducer whose verdict is
# `preserved` on every task, because the incumbent is preserved by
# definition and nothing was searched. Admitting it opens the repertoire
# and leaves the leg exactly as unmeasurable as it was, which is the case
# the campaign has to refuse to call a repair.
CONSTANT_SOURCE = (
    'def ENTRY(task, oracle, max_queries=16):\n'
    '    ops = list(task["ops"])\n'
    '    return {"candidate": {"family": "software",'
    ' "task_id": task["task_id"],\n'
    '                            "fault": task["fault"], "ops": ops,\n'
    '                            "witness": task["witness"],'
    ' "seed": task.get("seed")},\n'
    '                "queries": 0}\n')


def _member_source() -> str:
    """The carried member's bytes, as one function and nothing else.

    `verify_member` counts module-level functions and requires exactly one
    carrying the entry name, so the candidate builder is a nested function
    rather than a module-level helper. Nothing is imported and nothing is
    written: an acquired method reaches the world only through the oracle
    the driver hands it.

    The member verifies the set it carried before extending it, and returns
    what it carried when the oracle rejects it. A member that searched
    past a rejection and returned something else would measure the search,
    not the retention, and would be indistinguishable here from a member
    that had learned nothing from the task it was acquired on.
    """
    keys = "".join('"%s", ' % key for key in CARRIED_KEYS)
    return (
        'def ENTRY(task, oracle, max_queries=16):\n'
        '    ops = list(task["ops"])\n'
        '    keys = [str(op.get("id") or op.get("key")) for op in ops]\n'
        '    carried = (' + keys + ')\n'
        '    keep = [i for i, key in enumerate(keys) if key in carried]\n'
        '\n'
        '    def build(indices):\n'
        '        return {"family": "software",'
        ' "task_id": task["task_id"],\n'
        '                "fault": task["fault"],\n'
        '                "ops": [ops[i] for i in sorted(indices)],\n'
        '                "witness": task["witness"],\n'
        '                "seed": task.get("seed")}\n'
        '\n'
        '    if not keep:\n'
        '        return {"candidate": build(list(range(len(ops)))),'
        ' "queries": 0}\n'
        '    spent = 1\n'
        '    if str(oracle.query(build(keep)).get("verdict")) != "preserved":\n'
        '        return {"candidate": build(keep), "queries": spent}\n'
        '    grew = True\n'
        '    while grew and spent < max_queries and len(keep) < len(ops):\n'
        '        grew = False\n'
        '        for i in range(len(ops)):\n'
        '            if i in keep:\n'
        '                continue\n'
        '            spent = spent + 1\n'
        '            if spent > max_queries:\n'
        '                break\n'
        '            trial = keep + [i]\n'
        '            verdict = str(oracle.query(build(trial)).get("verdict"))\n'
        '            if verdict == "preserved":\n'
        '                keep = trial\n'
        '                grew = True\n'
        '                break\n'
        '    return {"candidate": build(keep), "queries": spent}\n')


def _member(capability_id: str = MEMBER_ID, *,
            source: str | None = None) -> assessment_profile.AcquiredMember:
    return assessment_profile.AcquiredMember(
        capability_id=capability_id, family="software", entry="ENTRY",
        method_source=_member_source() if source is None else source,
        origin=ORIGIN, acquired_on=ACQUIRED_ON)


def _repertoire(*members) -> assessment_profile.Repertoire:
    return assessment_profile.Repertoire(tuple(members))


def _reduction(report: dict) -> float:
    from experiments.ad01 import s09_e2_scored

    return float(s09_e2_scored.normalized_reduction(report))


# ---------------------------------------------------------------------------
# the arrival path
# ---------------------------------------------------------------------------


def test_the_default_repertoire_is_still_exactly_the_four_authored_seeds():
    """The frozen value, unchanged, so every archived run still reproduces.

    This is the same tuple `default_repertoire` returned before B3, and
    `tests/test_ad01_w2_retention.py:66-78` asserts against it. Opening the
    repertoire is a second reachable state, not a replacement of this one.
    """
    assert assessment_profile.default_repertoire() == (
        "seed-sw-ddmin", "seed-sw-greedy", "seed-gr-ddmin", "seed-gr-greedy")


def test_an_acquired_member_is_admitted_to_a_later_tasks_repertoire():
    """The arrival path, as a fixture: before and after, as literals.

    The same task, the same eligible call, with and without the member. Both
    lists are spelled out rather than compared to each other, because a test
    that only says "the second is longer" would pass with any longer list,
    including a wrong one.
    """
    target = worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_REJECTED)

    before = replica.eligible_for(target)
    after = replica.eligible_for(target, _repertoire(_member()))

    assert before == ["seed-sw-ddmin", "seed-sw-greedy"]
    assert after == ["seed-sw-ddmin", "seed-sw-greedy", MEMBER_ID]


def test_the_arrival_is_scoped_to_the_family_the_member_was_acquired_on():
    """A member acquired on a software task does not enter a graph one.

    Scope is what makes the arrived member mean anything: bytes learned on
    one family are not evidence about another, and an unscoped repertoire
    would offer a policy a method it has no reason to expect to work.

    The refusal is raised rather than silently applied, because a caller
    holding a study's whole collection should be told which member did not
    apply here rather than be handed a list that reads exactly like the
    frozen one.
    """
    graph = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-transfer-gr-00")

    with pytest.raises(assessment_profile.RepertoireRefused) as refused:
        replica.eligible_for(graph, _repertoire(_member()))

    assert "was acquired on a software task" in str(refused.value)
    assert MEMBER_ID in str(refused.value)

    # The type itself, asked non-strictly, answers the scoping question and
    # nothing else: the software member is out of scope on a graph task and
    # the graph seeds are still the whole of what may be named.
    assert _repertoire(_member()).eligible_for(
        graph, strict=False) == ["seed-gr-ddmin", "seed-gr-greedy"]


def test_a_member_is_refused_on_the_task_it_was_acquired_on():
    """Retention means a prior task. A member on its own task is not one.

    This is the invariant that separates a retained method from a cold
    acquisition dressed in the same record, and it is refused at the gate
    rather than left to a reader of the report.
    """
    own = worlds.load_task(worlds.FROZEN_DIR, ACQUIRED_ON)

    with pytest.raises(assessment_profile.RepertoireRefused) as refused:
        replica.eligible_for(own, _repertoire(_member()))

    assert "acquired on" in str(refused.value)


def test_a_member_claiming_a_seed_id_is_refused():
    """`trajectory.load_repertoire` already refuses this. So does the gate.

    Two refusals of the same collision in two owners is not duplication:
    the host's loader protects the study's stored repertoire, and this gate
    protects the one an assessment is handed.
    """
    for bad in ("seed-sw-ddmin", "seed-sw-greedy"):
        with pytest.raises(assessment_profile.RepertoireRefused):
            replica.eligible_for(
                worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_REJECTED),
                _repertoire(_member(bad)))


def test_a_member_claiming_an_unprefixed_id_is_refused():
    """The `ctl-` namespace is refused here, for the reason it was chosen.

    `control_arm.ID_PREFIX` exists so a control member cannot collide with
    the host's `run_seed` short-circuit. An arrived member in that namespace
    would collide with the control arm's own records, so the prefix is
    reserved rather than merely discouraged.
    """
    with pytest.raises(assessment_profile.RepertoireRefused) as refused:
        replica.eligible_for(
            worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_REJECTED),
            _repertoire(_member("ctl-software-greedy")))

    assert "reserved" in str(refused.value)


def test_a_member_whose_bytes_the_executor_refuses_never_reaches_the_view():
    """The byte gate is `verify_member` itself, not a second opinion of it.

    Source with an import in it, or with two entry functions, or with a
    dunder attribute, is refused by the executor's own contract. A gate
    carrying its own looser opinion would admit bytes the executor then
    refuses, and the eligible list would advertise a method that cannot run.
    The refusal is the executor's own message, so a reader sees which rule
    stopped it rather than a paraphrase of one.
    """
    imported = _member_source().replace(
        "    ops = list(task[\"ops\"])",
        "    import os\n    ops = list(task[\"ops\"])")

    with pytest.raises(assessment_profile.RepertoireRefused) as refused:
        replica.eligible_for(
            worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_REJECTED),
            _repertoire(_member(MEMBER_ID, source=imported)))

    assert "imports-forbidden" in str(refused.value)


def test_the_member_digest_is_derived_from_its_bytes_not_asserted():
    """A member states bytes, and the digest is a fact about them.

    There is no digest check at the gate and there is no need for one: the
    digest is a computed property of the bytes on a frozen dataclass, so a
    member cannot carry a digest that disagrees with its source. What is
    asserted here is that the digest the executable record carries is the
    digest of the bytes the executor would run, which is what
    `trajectory.load_repertoire` and the execution receipt each verify
    independently.
    """
    member = _member()
    executable = member.as_executable()
    admitted = replica.eligible_for(
        worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_REJECTED),
        _repertoire(member))

    assert member.source_digest == hashlib.sha256(
        member.method_source.encode("utf-8")).hexdigest()
    assert executable["source_digest"] == member.source_digest
    assert executable["method_source"] == member.method_source
    assert MEMBER_ID in admitted


def test_the_executor_verifies_the_digest_of_the_bytes_actually_staged(runs):
    """The receipt's digest is the member's, measured on the staged source.

    `method_exec` verifies the digest of what it wrote before it dispatches
    and again before it reads the receipt back, and returns the staged
    source. The member's declared digest and the executor's executed one are
    the same fact reached from two sides.
    """
    from experiments.ad01 import method_exec

    member = _member()
    assert hashlib.sha256(
        runs[CARRIED_TO_REJECTED]["executed_source"].encode(
            "utf-8")).hexdigest() == member.source_digest
    # and the executor's own gate accepts what the gate admitted
    assert method_exec.verify_member(member.as_executable()) == "ENTRY"


def test_a_member_with_no_bytes_is_refused_before_anything_runs_it():
    """Empty bytes are refused by name, not by an exception from the parser.

    `verify_member` would say `empty-method-source`, but the gate checks it
    first so a repertoire can hold a member that was recorded without its
    bytes and report that as the defect it is.
    """
    with pytest.raises(assessment_profile.RepertoireRefused) as refused:
        replica.eligible_for(
            worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_REJECTED),
            _repertoire(_member(MEMBER_ID, source="")))

    assert "no executable bytes" in str(refused.value)


def test_the_arrival_path_preserves_the_seeds_in_first_position():
    """The armed reader policies take `eligible[0]` and move to `[1]`.

    `PROMPTED_SHAPE_READER` reads no further than that. Appending an arrived
    member after the seeds is what keeps every existing policy's behaviour
    identical when one is present, so opening the repertoire does not
    silently re-point the policies the archived contrasts were measured with.
    """
    target = worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_REJECTED)
    opened = replica.eligible_for(target, _repertoire(_member()))

    assert opened[:2] == ["seed-sw-ddmin", "seed-sw-greedy"]
    assert opened[2:] == [MEMBER_ID]


# ---------------------------------------------------------------------------
# the fixture's bytes execute, and their verdict varies with the task
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db("b3-repertoire", migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture(scope="module")
def authority(store):
    """A real allocation and campaign authority, or no child may execute."""
    trajectory.set_namespace_token("")
    cid = trajectory.campaign_id(0, "I", 314)
    trajectory.authorize_campaign(store, cid, authorized=1000000)
    return {"dsn": store, "allocation_id": trajectory._alloc_id(cid),
            "cid": cid}


@pytest.fixture(scope="module")
def runs(authority):
    """The member's own bytes, executed on each of the three tasks.

    Not simulated and not graded by a second implementation: the member is
    staged and run through `method_exec.run_member_out_of_process` with the
    oracle on a socket, which is the route an acquired method takes, and the
    candidate it returns goes to the same `checkers.check_software` the
    authored controls are graded by.
    """
    from experiments.representation import checkers

    member = _member().as_executable()
    out = {}
    for index, task_id in enumerate(
            (ACQUIRED_ON, CARRIED_TO_PRESERVED, CARRIED_TO_REJECTED), start=1):
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        result = method_exec.run_member_out_of_process(
            copy.deepcopy(member), task, max_queries=8,
            dsn=authority["dsn"], allocation_id=authority["allocation_id"],
            operation_id="ad01-%s-b3-%s-%d"
                         % (authority["cid"], task_id, index))
        out[task_id] = {
            "report": checkers.check_software(task, result["candidate"]),
            "queries": int(result.get("queries") or 0),
            "candidate": result["candidate"],
            "trace_len": len(result.get("query_trace") or ()),
            "executed_source": result.get("source_bytes")}
    return out


def test_the_member_is_nameable_in_a_second_task_and_rejected_in_a_third(
        runs):
    """One member, two later tasks, two verdicts.

    A reducer whose verdict cannot vary is what made the leg unmeasurable.
    This is the varying one, and the verdicts are the frozen checker's, read
    off the candidate the member's own execution returned.
    """
    assert runs[ACQUIRED_ON]["report"]["verdict"] == "preserved"
    assert runs[CARRIED_TO_PRESERVED]["report"]["verdict"] == "preserved"
    assert runs[CARRIED_TO_REJECTED]["report"]["verdict"] == "not_preserved"
    assert (runs[CARRIED_TO_REJECTED]["report"]["reason"]
            == "witness-lost-agree")


def test_the_executed_bytes_are_the_member_bytes(runs):
    """The child ran the fixture's bytes, not something that resembles them.

    `method_exec` returns the staged source in `source_bytes` after
    verifying its digest against what it wrote. Reading it here is what
    makes the verdict above a fact about this source.
    """
    for task_id, run in runs.items():
        assert run["executed_source"] == _member_source(), task_id


def test_the_carried_member_actually_asked_the_oracle(runs):
    """A walk that did not happen is not an empty walk.

    The rejected task's run stops after one question, because the carried
    set was refused on the first probe and the member returns what it
    carried rather than searching past a rejection. The accepted task's run
    spends the budget extending. Both are traces, and the trace is written
    by the host side of the socket, so a member cannot narrate its own walk.
    """
    assert runs[CARRIED_TO_REJECTED]["queries"] == 1
    assert runs[CARRIED_TO_REJECTED]["trace_len"] == 1
    assert runs[CARRIED_TO_PRESERVED]["queries"] == 8
    assert runs[CARRIED_TO_PRESERVED]["trace_len"] == 8


def test_two_arms_differing_only_in_holding_the_member_differ_in_the_leg(
        runs):
    """The retained-method leg is measurable, with the panel held identical.

    Both readings are on `CARRIED_TO_PRESERVED`, the same task, at the same
    budget. The cold arm names a seed and the retained arm names the arrived
    member. The decision vector differs and so does the scored observable,
    and the only difference between the two conditions is whether the arm's
    repertoire held the member.
    """
    from experiments.ad01 import seeds
    from experiments.representation import checkers

    target = worlds.load_task(worlds.FROZEN_DIR, CARRIED_TO_PRESERVED)
    cold = replica.eligible_for(target)
    retained = replica.eligible_for(target, _repertoire(_member()))

    assert cold == ["seed-sw-ddmin", "seed-sw-greedy"]
    assert retained == ["seed-sw-ddmin", "seed-sw-greedy", MEMBER_ID]
    assert len(set(cold) ^ set(retained)) == 1

    capability = next(c for c in seeds.SEED_CAPABILITIES
                      if c["capability_id"] == "seed-sw-greedy")
    seeded = seeds.run_seed(capability, target, max_queries=8)
    cold_reduction = _reduction(
        checkers.check_software(target, seeded["candidate"]))
    member_reduction = _reduction(runs[CARRIED_TO_PRESERVED]["report"])

    assert runs[CARRIED_TO_PRESERVED]["report"]["verdict"] == "preserved"
    assert member_reduction > 0.0
    assert member_reduction != cold_reduction


# ---------------------------------------------------------------------------
# what the campaign now reports, and what it still does not claim
# ---------------------------------------------------------------------------


def test_the_campaign_measures_the_opened_case_as_well_as_the_default_one():
    """Both states, in one call, so a reader cannot read one as the other.

    `measure_repertoire_closure()` with no member still reports a closed
    repertoire, and that is still what the authored seeds alone are. Given
    an arrived member it reports the open one, and the two are separate
    fields rather than one flag that is true or false depending on who
    called it.
    """
    from experiments.ad01 import w2_retention_campaign as campaign

    default = campaign.measure_repertoire_closure()
    opened = campaign.measure_repertoire_closure(_repertoire(_member()))

    assert default["repertoire_closed"] is True
    assert opened["repertoire_closed"] is False
    assert opened["default_repertoire_closed"] is True
    # The panel targets are software, so a software member is admitted on
    # all of them and the eligible sets differ from the frozen one by
    # exactly that member. One distinct set, not two, and saying so is what
    # makes the row mean what it says.
    assert len(opened["distinct_eligible_sets"]) == 1
    # The row reports the sorted set because the closure compared SETS, and
    # order is not what this measurement is about; `eligible_for` itself is
    # asserted in selection order everywhere else.
    assert opened["distinct_eligible_sets"][0] == tuple(
        sorted(["seed-sw-ddmin", "seed-sw-greedy", MEMBER_ID]))
    assert all(MEMBER_ID in row["eligible_methods"] for row in opened["rows"])
    assert all(row["retained_method_nameable"] is True
               for row in opened["rows"])
    assert all(row["eligible_count"] == 3 for row in opened["rows"])


def test_a_leg_measured_without_executing_the_member_is_refused(authority):
    """The census refuses rather than reporting a leg it could not measure.

    `retained_leg_verdict` executes the member, and the executor refuses any
    execution without a store and an allocation. A caller with neither must
    be told it measured nothing, not handed a verdict derived from a
    reimplementation of the member.
    """
    from experiments.ad01 import w2_retention_campaign as campaign

    with pytest.raises(campaign.W2Refused) as refused:
        campaign.retained_leg_verdict(_member())

    assert "authority" in str(refused.value) or "store" in str(refused.value)


def test_the_campaign_refuses_to_call_the_leg_measurable_on_a_constant_verdict(
        authority):
    """A member is necessary and not sufficient, and the campaign says so.

    A member whose verdict is `preserved` on every task it is carried to
    would restore the defect this lane repairs: a repertoire that admits
    nothing a decision can differ on. The measurement reports the distinct
    verdicts and calls the leg measurable only when there is more than one,
    so the claim cannot be earned by admitting bytes alone.

    Both verdicts below come from executing the two members' own bytes
    through the brokered executor and grading with the frozen checker. The
    constant member returns its input and so is `preserved` on all eight
    non-acquisition tasks; the carried member's set is refused on most of
    them and kept on two.
    """
    from experiments.ad01 import w2_retention_campaign as campaign

    constant = _member("acquired-sw-constant", source=CONSTANT_SOURCE)
    verdict = campaign.retained_leg_verdict(constant, authority=authority)

    assert verdict["distinct_verdicts"] == ["preserved"]
    assert verdict["retained_method_leg_measurable"] is False

    varying = campaign.retained_leg_verdict(_member(), authority=authority)
    assert sorted(varying["distinct_verdicts"]) == ["not_preserved", "preserved"]
    assert varying["retained_method_leg_measurable"] is True
    assert varying["tasks_measured"] == 9
