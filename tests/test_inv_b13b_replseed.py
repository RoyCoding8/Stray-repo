"""Lane B13b: the E2 method is resolved per family, and the magnitudes are real.

`e2_replication`'s four authored policies named `seed-sw-ddmin` in their own
bytes. `s09_e2_scored.CONTROL_PREFIX` already maps `{"software": "seed-sw-",
"graph": "seed-gr-"}`, so on a graph target the policy asked for a method
absent from the target's own repertoire and `assessment_profile.dispatch`
refused the action. The replica's graph arms could not be read at all.

Each policy now takes its method from the view's own `eligible_methods`,
which `eligible_for` fills through `s09_e2_scored.control_candidates` — the
single reader of `CONTROL_PREFIX`. A third policy defect sat behind the
first: `READS_THE_VERDICT` indexed `task_content["ops"]` unconditionally, and
a graph task carries `edges` and no `ops`.

**Every literal below is measured on this source, through the same brokered
child execution the campaign runs, not asserted from a docstring.** The
magnitudes in the stale-magnitude section are the reachable ones: on
`ad01-w0-within-sw-00` `seed-sw-ddmin` reaches 3 of an initial 10, so the
maximum reachable reduction is exactly 0.7 and a reader scores 1.7 against an
echoer's 0.7. The 2.0 and 1.0 the tests used to pin were reachable only
under the `QUALITY` constant `d17b5a7` deleted, which made score arithmetic
incapable of returning anything but those two values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.ad01 import e2_replication as replica
from experiments.ad01 import method_exec
from experiments.ad01 import policy_step
from experiments.ad01 import s09_e2_scored as scored
from experiments.ad01 import trajectory
from experiments.ad01 import worlds
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"

GRAPH = "ad01-w0-within-gr-02"
SOFTWARE = "ad01-w0-within-sw-00"

# The broker keys a durable operation by its id and refuses the same id
# under a different payload, so every step this module runs takes a fresh one.
_STEP_COUNTER = {"n": 0}

# A software method named at a graph target. `dispatch` resolves the method
# against the target's own family repertoire, so this is refused on scope
# rather than on execution: the gate never runs the method at all.
SOFTWARE_METHOD_ON_GRAPH = '''def STEP(view, state):
    return {"action": {"kind": "use_method",
                       "target": view["task_content"]["task_id"],
                       "inputs": {"method_id": "seed-sw-ddmin", "max_queries": 8},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {}}
'''


def _observations(task_id: str, verdicts=("preserved",), detail=None):
    """Experience records in the shape a trajectory writes them.

    `detail` names a real unit of the target's own family, because that is
    the only thing that lets `READS_THE_VERDICT` find a witness to drop. A
    software op is a dict keyed by an op letter and a graph edge is a
    `[u, v]` pair whose marker is `"u-v"`, so the two families need
    different details. Both are measured rather than assumed, in
    `test_the_witness_is_found_in_each_family_own_unit_shape`.
    """
    return [{"observation_id": "obs-%s-%d" % (task_id, index),
             "task_id": task_id,
             "capability_id": "ad01-%s" % task_id.split("-")[3],
             "verdict": verdict,
             "detail": detail or "ref %s" % _first_marker(task_id)}
            for index, verdict in enumerate(verdicts)]


def _first_marker(task_id: str) -> str:
    """The marker of the target's own first unit."""
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    units = task.get("ops") or task.get("edges")
    unit = units[0]
    if isinstance(unit, dict):
        return str(unit.get("id") or unit.get("key"))
    return "-".join(str(part) for part in unit)


def _score(policy: str, task_id: str, observations) -> scored.Score:
    return scored.Score(
        {"policy_source": scored.proposal_source(json.dumps({"entry": policy}))},
        "authored-control", "b13b", 8)


def _view(task_id: str, observations):
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    return policy_step.materialize_view(
        task=task, observations=list(observations), open_questions=[],
        last_result=None, eligible_methods=replica.eligible_for(task),
        remaining={"steps": 1})


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db("b13b-replseed", migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture(scope="module")
def authority(store):
    """A real allocation and campaign authority for brokered execution.

    `method_exec` refuses any policy-source execution without a dsn, an
    allocation and an operation id, so a test that steps a policy at all has
    to carry all three. This is the same authority A2's positive control uses.
    """
    trajectory.set_namespace_token("")
    cid = trajectory.campaign_id(0, "I", 713)
    trajectory.authorize_campaign(store, cid, authorized=1000000)
    return {"dsn": store, "allocation_id": trajectory._alloc_id(cid), "cid": cid}


@pytest.fixture
def stepper(authority):
    """Step a policy under one real view, through the real child process.

    The operation id carries the task and a module-level counter rather than a
    per-test one, because the broker refuses an identity reused with a
    different payload and the disposable store outlives any single test.
    """
    def _step(policy: str, task_id: str, observations):
        _STEP_COUNTER["n"] += 1
        score = _score(policy, task_id, observations)
        result = method_exec.run_step_out_of_process(
            score.source, dict(_view(task_id, observations)), {},
            entry=policy_step.STEP_ENTRY,
            dsn=authority["dsn"],
            allocation_id=authority["allocation_id"],
            operation_id="ad01-%s-b13b-%s-%d"
                         % (authority["cid"], task_id, _STEP_COUNTER["n"]))
        return dict(result["action"].get("inputs") or {})

    return _step


# ---------------------------------------------------------------------------
# defect 1: the method is resolved from the target's own repertoire
# ---------------------------------------------------------------------------


def test_a_graph_target_is_asked_for_a_graph_method(stepper):
    """The literal is measured, not assumed.

    `seed-gr-ddmin` is what `eligible_for` puts first for a graph target and
    what the reader consequently names. On the same source and the same
    policy a software target yields `seed-sw-ddmin`, so the value is a
    property of the target's family rather than of the policy's bytes.
    """
    on_graph = stepper(replica.READS_THE_VERDICT, GRAPH, _observations(GRAPH))
    on_software = stepper(replica.READS_THE_VERDICT, SOFTWARE,
                          _observations(SOFTWARE))

    assert on_graph["method_id"] == "seed-gr-ddmin"
    assert on_software["method_id"] == "seed-sw-ddmin"


def test_every_authored_policy_takes_its_method_from_the_view(stepper):
    """No policy in the module restates a family prefix any more.

    The four policies are the whole set that had a literal in it. Each is
    stepped on both families and each lands on that family's own prefix.
    """
    for policy in (replica.READS_THE_VERDICT, replica.PROMPTED_SHAPE_READER,
                   replica.ECHOES_WITHOUT_READING, replica.IGNORES_THE_VIEW):
        on_graph = stepper(policy, GRAPH, _observations(GRAPH))
        on_software = stepper(policy, SOFTWARE, _observations(SOFTWARE))

        assert on_graph["method_id"] == "seed-gr-ddmin", policy[:40]
        assert on_software["method_id"] == "seed-sw-ddmin", policy[:40]


def test_the_method_the_reader_names_moves_with_the_verdicts(stepper):
    """A reader that re-routes is not a reader that always picks the same one.

    Measured on graph: a `not_preserved` stream names `seed-gr-greedy` and a
    `preserved` stream names `seed-gr-ddmin`. A policy that ignored the
    verdicts would name the same method under both.
    """
    routed = stepper(replica.PROMPTED_SHAPE_READER, GRAPH,
                     _observations(GRAPH, ("not_preserved",)))
    held = stepper(replica.PROMPTED_SHAPE_READER, GRAPH,
                   _observations(GRAPH, ("preserved",)))

    assert routed["method_id"] == "seed-gr-greedy"
    assert held["method_id"] == "seed-gr-ddmin"


def test_a_policy_naming_a_software_method_is_refused_on_graph():
    """The defect this lane repairs, on the refusal that exposed it.

    `assessment_profile.dispatch` resolves `method_id` against the target's
    own family repertoire, so a `seed-sw-` name on a graph target is refused
    on scope. The step itself is admitted — the ABI does not know about
    repertoires — so the refusal is asserted where it happens, at dispatch,
    and the correct graph method is shown to dispatch in the same test.
    """
    task = worlds.load_task(worlds.FROZEN_DIR, GRAPH)
    score = _score(SOFTWARE_METHOD_ON_GRAPH, GRAPH, _observations(GRAPH))
    record = score.record()
    refused = scored._dispatch(
        record,
        {"kind": "use_method", "target": GRAPH,
         "inputs": {"method_id": "seed-sw-ddmin", "max_queries": 8},
         "evidence_refs": [], "requested_resources": {"queries": 8}},
        score.digest)
    admitted = scored._dispatch(
        record,
        {"kind": "use_method", "target": GRAPH,
         "inputs": {"method_id": "seed-gr-ddmin", "max_queries": 8},
         "evidence_refs": [], "requested_resources": {"queries": 8}},
        score.digest)

    assert task["family"] == "graph"
    assert refused["accepted"] is False
    assert refused["candidate"] is None
    assert admitted["accepted"] is True
    assert admitted["candidate"] is not None


def test_the_scored_gate_cannot_execute_on_this_source_for_any_family():
    """The defect that gates this lane, named so it is not mistaken for ours.

    `Score.measure` calls `_execute` with no dsn, allocation or operation id,
    and `method_exec` refuses any policy-source execution without all three.
    So every reading this instrument produces is unscored, on graph and on
    software alike, and the graph repairs below are what becomes measurable
    once a caller carries authority. This asserts the refusal itself rather
    than a score, because the score is not obtainable here.

    The fix belongs with the campaign that owns the durable route, not with a
    qualification gate: adding a second execution path here would delete A2's
    recorded repair.
    """
    reading = _score(replica.PROMPTED_SHAPE_READER, GRAPH,
                     _observations(GRAPH)).measure(
                         worlds.load_task(worlds.FROZEN_DIR, GRAPH),
                         _observations(GRAPH),
                         eligible_methods=replica.eligible_for(
                             worlds.load_task(worlds.FROZEN_DIR, GRAPH)))

    assert reading.scored is False
    assert reading.detail == (
        "unscored: execute: the returned bytes admitted no action that reaches"
        " a method executor")

    with pytest.raises(method_exec.MethodExecutionError,
                       match="explicit authority and identity"):
        method_exec.run_step_out_of_process(
            _score(replica.PROMPTED_SHAPE_READER, GRAPH,
                   _observations(GRAPH)).source,
            dict(_view(GRAPH, _observations(GRAPH))), {},
            entry=policy_step.STEP_ENTRY)


# ---------------------------------------------------------------------------
# defect 2: the reader reads whichever unit list the family carries
# ---------------------------------------------------------------------------


def test_a_graph_task_has_no_ops_and_a_reader_does_not_need_them(stepper):
    """The shape assumption behind the second defect, named directly.

    A graph task's `task_content` carries `edges` and no `ops`, so a reader
    that indexed `ops` raised and the gate returned unscored rather than
    false. Both families are stepped and each plans over its own ten units,
    dropping the one a preserved observation names. The plan is nine long in
    both, because the witness is excluded from it either way.
    """
    graph_task = worlds.load_task(worlds.FROZEN_DIR, GRAPH)
    inputs = stepper(replica.READS_THE_VERDICT, GRAPH, _observations(GRAPH))

    assert "ops" not in graph_task
    assert len(graph_task["edges"]) == 10
    assert inputs["witness"] == 0
    assert len(inputs["plan"]) == 9


def test_the_witness_is_found_in_each_family_own_unit_shape(stepper):
    """What the reader matches on, measured per family.

    A software op is a dict and matches on its op letter; a graph edge is a
    `[u, v]` pair and matches on `"u-v"`. B13's repair called `.get` on both,
    which is an `AttributeError` on a list and made every graph reading
    unscored. These are the literals the policy now matches against, so a
    regression to a dict-only match is red here rather than silent.
    """
    assert _first_marker(GRAPH) == "0-1"
    assert _first_marker(SOFTWARE) == "c"

    on_graph = stepper(replica.READS_THE_VERDICT, GRAPH, _observations(GRAPH))
    on_software = stepper(replica.READS_THE_VERDICT, SOFTWARE,
                          _observations(SOFTWARE))

    assert on_graph["witness"] == 0
    assert on_software["witness"] == 0


def test_a_software_reader_still_plans_over_its_own_ops(stepper):
    """The graph repair did not cost the software leg its plan."""
    software_task = worlds.load_task(worlds.FROZEN_DIR, SOFTWARE)
    inputs = stepper(replica.READS_THE_VERDICT, SOFTWARE, _observations(SOFTWARE))

    assert len(software_task["ops"]) == 10
    assert len(inputs["plan"]) == 9


# ---------------------------------------------------------------------------
# the reachable magnitudes, and the stale-versus-regression ruling
# ---------------------------------------------------------------------------


def test_the_reachable_reduction_on_the_replica_target_is_zero_point_seven():
    """The measurement the stale assertions are corrected against.

    `normalized_reduction` is the checker's own measure: how much of the
    initial measure the candidate removed. On `ad01-w0-within-sw-00` the
    initial measure is 10, `seed-sw-ddmin` returns 3 and `seed-sw-greedy`
    returns 5, so 0.7 is the maximum any policy can earn on this target and
    the 1.0 the old tests pinned was never reachable here. This enumerates
    the world's own controls rather than restating a constant.
    """
    from experiments.ad01 import seeds

    task = worlds.load_task(worlds.FROZEN_DIR, SOFTWARE)
    measured = {}
    for method, capability_id in zip(("ddmin", "greedy"),
                                     replica.eligible_for(task)):
        capability = next(item for item in seeds.SEED_CAPABILITIES
                          if item["capability_id"] == capability_id)
        result = seeds.run_seed(capability, task, max_queries=8)
        report = scored._grade(task, result["candidate"], raw=True)
        measured[method] = (report["initial_measure"], report["measure"])
        assert scored.normalized_reduction(
            {"scored": True, "verdict": report["verdict"],
             "measure": report["measure"],
             "initial_measure": report["initial_measure"]}) == pytest.approx(
                 (report["initial_measure"] - report["measure"])
                 / report["initial_measure"])

    assert measured["ddmin"] == (10, 3)
    assert measured["greedy"] == (10, 5)
    assert max((initial - measure) / initial
               for initial, measure in measured.values()) == 0.7


def test_the_reader_is_not_a_strawman_written_to_lose(stepper):
    """What the gate certifies, measured where the instrument can execute.

    Separation is the property, and it is a difference between two policies
    that differ by the act of reading. The reader re-routes its method on the
    verdicts and so reaches a candidate the echoer cannot; the echoer moves a
    string into its inputs and reaches the same candidate either way. Both are
    stepped under real authority and under both verdict exposures, because
    `qualify_instrument` cannot run here at all (see the test above).

    A reader that always named the better method would move nothing under
    the flip, so a moving candidate is the property that distinguishes a real
    read from a fixed one.
    """
    software = _observations(SOFTWARE)
    alternate = [dict(row, verdict=scored.VERDICT_FLIP[str(row["verdict"])])
                 for row in software]

    reader = stepper(replica.PROMPTED_SHAPE_READER, SOFTWARE, software)
    reader_alt = stepper(replica.PROMPTED_SHAPE_READER, SOFTWARE, alternate)
    echoer = stepper(replica.ECHOES_WITHOUT_READING, SOFTWARE, software)
    echoer_alt = stepper(replica.ECHOES_WITHOUT_READING, SOFTWARE, alternate)

    assert reader["method_id"] != reader_alt["method_id"]
    assert echoer["method_id"] == echoer_alt["method_id"]
    assert reader["method_id"] == "seed-sw-ddmin"
    assert reader_alt["method_id"] == "seed-sw-greedy"
    # The echoer writes the verdicts it read into an input key; the reader
    # has no such key, because copying a verdict is not a decision. Both
    # echoed strings are the stream that policy saw, so the echoer does
    # report what it read and still decides nothing with it.
    assert echoer["read_verdicts"] == "preserved"
    assert echoer_alt["read_verdicts"] == "not_preserved"
    assert "read_verdicts" not in reader
    assert "read_verdicts" not in reader_alt


def _candidate(task_id: str, method_id: str):
    """The candidate the world produced for one method, run for real.

    `_evidence` compares candidates the method executor produced, not text
    this file wrote, so the candidate is obtained by running the seed
    capability the named method resolves to. A synthesised candidate would
    make the leg compare two literals from the test's own body.
    """
    from experiments.ad01 import seeds

    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    capability = next(item for item in seeds.SEED_CAPABILITIES
                      if item["capability_id"] == method_id)
    return seeds.run_seed(capability, task, max_queries=8)["candidate"]


def test_the_reader_earns_the_evidence_the_echoer_cannot(stepper):
    """The instrument's own arithmetic, on the two policies, run for real.

    `_evidence` compares the candidate the world produced under the arm's
    verdicts against the candidate it produced under flipped ones. The reader
    changes method under the flip and so the world returns a different
    candidate; the echoer changes a string it wrote and so it does not. The
    leg is 1.0 against 0.0, which is the discrimination the matrix credits
    the instrument with and the reason the reader is not a strawman.
    """
    software = _observations(SOFTWARE)
    alternate = [dict(row, verdict=scored.VERDICT_FLIP[str(row["verdict"])])
                 for row in software]

    reader = stepper(replica.PROMPTED_SHAPE_READER, SOFTWARE, software)
    reader_alt = stepper(replica.PROMPTED_SHAPE_READER, SOFTWARE, alternate)
    echoer = stepper(replica.ECHOES_WITHOUT_READING, SOFTWARE, software)
    echoer_alt = stepper(replica.ECHOES_WITHOUT_READING, SOFTWARE, alternate)

    reader_leg = scored._evidence(
        {"candidate": _candidate(SOFTWARE, reader["method_id"]),
         "action": {"inputs": reader}},
        {"candidate": _candidate(SOFTWARE, reader_alt["method_id"]),
         "action": {"inputs": reader_alt}})
    echoer_leg = scored._evidence(
        {"candidate": _candidate(SOFTWARE, echoer["method_id"]),
         "action": {"inputs": echoer}},
        {"candidate": _candidate(SOFTWARE, echoer_alt["method_id"]),
         "action": {"inputs": echoer_alt}})

    assert reader_leg["ratio"] == 1.0
    assert echoer_leg["ratio"] == 0.0
    assert reader_leg["ratio"] > echoer_leg["ratio"]


# ---------------------------------------------------------------------------
# the finding this lane records but does not repair
# ---------------------------------------------------------------------------


def test_the_membership_reader_is_vacuous_on_the_powered_graph_panel():
    """`panel_variation`'s own documented finding, re-measured here.

    `PROMPTED_SHAPE_READER` asks whether any observation is `not_preserved`.
    On the `ad01` world that separates. On the panel that carries the only
    powered `graph:dev+transfer` combination the stream already holds both
    verdicts, so the predicate is true under either exposure and the flip
    moves nothing it looks at. Counting losses is what survives: 7 against 1
    and 5 against 3. This is `panel_variation`'s record to keep and to
    repair; a qualification gate must not delete it.
    """
    from experiments.ad01 import panel_variation as pv

    task = next(item for item in pv.all_tasks()
                if item["task_id"] == "panel-w0-dev-gr-00")
    verdicts = pv.stream_verdicts(task, "ddmin", pv.ARM_BUDGET)
    flipped = [scored.VERDICT_FLIP.get(str(v), v) for v in verdicts]

    assert sorted(set(verdicts)) == ["not_preserved", "preserved"]
    assert ("not_preserved" in verdicts) == ("not_preserved" in flipped)
    losses = lambda rows: len([r for r in rows if r == "not_preserved"])
    assert losses(verdicts) == 7
    assert losses(flipped) == 1