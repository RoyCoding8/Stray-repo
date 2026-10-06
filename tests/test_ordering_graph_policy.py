"""The action-graph executor is Boolean-typed. The ordering world cannot load.

`boolean_graph_policy` is the executor for the guarded decision graph, and it
is Boolean-typed for one reason: `_parse_action` calls
`boolean_policy._validate_boolean_action`, a function whose probe branch
demands `boolean.query` and whose stop branch demands `boolean.task`. Every
other part of the executor — the node grammar, the guard vocabulary, the
reachability and terminal checks — is world-agnostic, and the constants that
make it Boolean are a target string and one validator call.

So `ordering_graph_record()` is refused at load, and the refusal names the
executor rather than the record:

    node probe arm 0 action: probe target must be boolean.query

That is a real answer to the handoff's question — the representation is
portable, the *executor* was not — but it is an accident of one constant,
and it is the same accident `boolean_ast_policy.expressivity_limits()`
records for the typed AST. The ordering world's validator already exists,
in `second_active._validate_comparison` and `_validate_order`; the graph
never asks it.

These tests pin the world-generic form: the same record loads against the
ordering world, runs a full three-turn episode, and keeps its cursor across
the process boundary the compute bound forces. The validator's world is a
parameter, and these tests would fail against an executor that hardcoded
either one.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import boolean_graph_policy as boolean_graph
from experiments.ad01 import ordering_graph_policy as graph
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step
from experiments.ad01 import second_active
from settlement.child_limits import ChildLimits, child_setup_refusal

_CHILD_REFUSAL = child_setup_refusal(ChildLimits(cpu_seconds=10))
from experiments.ad01 import s09_representation_matrix as matrix


ORDER = list(matrix.ORDERING_ORDER)
JOBS = matrix.ORDERING_JOBS


def _arm(guard, action, next_node, progress):
    return {"guard": guard, "action": action, "next": next_node,
            "progress": progress}


def _action(kind, target, inputs=None, resources=None):
    return {"kind": kind, "target": target,
            "inputs": {} if inputs is None else inputs,
            "evidence_refs": [],
            "requested_resources": {} if resources is None else resources}


ALWAYS = {"always": True}


def _driven_session(record, *, split="dev", seed=5, fresh_executor=True):
    """Drive the ordering episode, re-seeding the executor every turn.

    `fresh_executor=True` is the compute bound: `s09_graph_budget` runs one
    graph turn per child process, so nothing survives in a closure and the
    cursor has to be handed back in through `at_cursor` and read out
    through `decide.s09_cursor()`. The two paths are the same to the
    episode, so the tests run this one.

    The ordering world is terminal on commit, so a committing graph is
    asked for two turns, not three. `test_the_walk_reaches_the_stop_node`
    drives the third.
    """
    task = second_active.make_task(split, seed)
    session = second_active.ScheduleSession(task)
    trace = []
    cursor: dict = {}
    decide = graph.choose_action(record, at_cursor=None)
    while not second_active.is_terminal(session) and len(trace) < 6:
        action = decide(second_active.public_state(session))
        effect = second_active.apply_action(session, action)
        trace.append({"action": action, "effect": effect})
        if fresh_executor:
            cursor = decide.s09_cursor()
            decide = graph.choose_action(record, at_cursor=cursor or None)
        if effect["kind"] == policy_action.STOP:
            break
    return {"trace": trace, "session": session, "cursor": cursor}


def _walk_three_turns(record, *, split="dev", seed=5):
    """Drive the graph's full probe -> construct -> stop walk.

    The episode stops asking at commit, so the stop node is only reached by
    a driver that keeps asking. The public state is held fixed, which is
    what makes the walk the graph's own doing: nothing but the cursor
    moves it from arm to arm.
    """
    session = second_active.ScheduleSession(
        second_active.make_task(split, seed))
    view = second_active.public_state(session)
    actions = []
    cursor: dict = {}
    decide = graph.choose_action(record, at_cursor=None)
    for _ in range(3):
        action = decide(view)
        actions.append(action)
        cursor = decide.s09_cursor()
        decide = graph.choose_action(record, at_cursor=cursor or None)
    return {"actions": actions, "cursor": cursor}


def _committed_order(result):
    for entry in result["trace"]:
        if entry["action"]["kind"] == policy_action.CONSTRUCT:
            return entry["action"]["inputs"]["order"]
    raise AssertionError("the episode never constructed")


# --- the record loads against the ordering world ------------------------


def test_the_ordering_record_loads_against_the_ordering_executor():
    """The refusal was the executor's typing, not the record's shape."""
    policy = graph.load_policy(matrix.ordering_graph_record())

    assert policy.start == "probe"
    assert sorted(policy.nodes) == ["decide", "probe", "stop"]


def test_the_boolean_executor_still_refuses_the_ordering_record():
    """The two executors must disagree, or nothing was made world-generic.

    `ordering_graph_record` is not malformed. The Boolean executor refuses
    it because it asks the Boolean validator, and it must keep refusing it:
    an executor that accepted both would be validating against no world.
    """
    with pytest.raises(boolean_graph.GraphPolicyRefused) as caught:
        boolean_graph.load_policy(matrix.ordering_graph_record())

    assert "probe target must be boolean.query" in str(caught.value)


def test_the_ordering_executor_refuses_the_boolean_record():
    """Symmetry: the ordering world refuses `boolean.query` in turn."""
    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(matrix.graph_policy_record())

    assert "probe target must be schedule.compare" in str(caught.value)


def test_a_world_other_than_ordering_can_be_passed_in():
    """The validator's world is a parameter, not a constant.

    This is the load-bearing test for the design. A third world, invented
    here, with its own targets, its own guard fields and its own validator,
    must load and run through the same executor. It could not if the
    ordering targets were written into the parser.
    """
    toy_view = {"tally": 0, "seen": []}

    def toy_view_of(public_state):
        return dict(toy_view)

    def toy_validate(action, *, view=None):
        if action.kind == policy_action.PROBE:
            if action.target != "toy.look":
                raise policy_action.ActionRefused("probe target must be toy.look")
            if action.inputs.get("key") != "k":
                raise policy_action.ActionRefused("toy probe key must be k")
            return
        if action.kind == policy_action.CONSTRUCT:
            if action.target != "toy.build":
                raise policy_action.ActionRefused(
                    "construct target must be toy.build")
            return
        if action.target != "toy.task":
            raise policy_action.ActionRefused("stop target must be toy.task")

    toy = graph.World(
        name="toy",
        probe_target="toy.look",
        construct_target="toy.build",
        stop_target="toy.task",
        allowed_kinds=frozenset({policy_action.PROBE, policy_action.CONSTRUCT,
                                 policy_action.STOP}),
        field_types={"tally": "integer", "seen.count": "integer"},
        observation_paths={},
        derived_fields={},
        refusals=(policy_action.ActionRefused,),
        validate_action=toy_validate,
        make_view=toy_view_of,
        static_view={"tally": 0, "seen": []},
    )
    record = {
        "policy_id": "toy-graph", "start": "look",
        "nodes": {"look": {"kind": "action", "arms": [
            _arm({"field": "tally", "op": "eq", "value": 0},
                 _action("probe", "toy.look", {"key": "k"}), "build", 1),
                _arm(ALWAYS, _action("stop", "toy.task"), "build", 0)]},
            "build": {"kind": "action", "arms": [
                _arm(ALWAYS, _action("construct", "toy.build"), "done", 1)]},
            "done": {"kind": "action", "arms": [
                _arm(ALWAYS, _action("stop", "toy.task"), "done", 0)]},
        }}

    policy = graph.load_policy(record, world=toy)
    assert policy.start == "look"

    decide = graph.choose_action(record, world=toy)
    assert decide({}) == _action("probe", "toy.look", {"key": "k"})
    assert decide.s09_cursor() == {"at": "build", "progress": 1}


# --- the record runs a whole episode ------------------------------------


def test_a_full_episode_probes_then_commits_a_permutation():
    """Probe `schedule.compare`, then construct `schedule.commit`.

    The ordering world is terminal on commit, so a committing graph is
    asked for two turns and the episode ends there. The third node is
    reached by `test_the_walk_reaches_the_stop_node`, which keeps asking.
    """
    result = _driven_session(matrix.ordering_graph_record())

    kinds = [entry["action"]["kind"] for entry in result["trace"]]

    assert kinds == [policy_action.PROBE, policy_action.CONSTRUCT]
    assert result["trace"][0]["action"]["target"] == "schedule.compare"
    assert result["trace"][0]["action"]["inputs"] == {
        "left": JOBS[0], "right": JOBS[1]}
    assert result["trace"][1]["action"]["target"] == "schedule.commit"
    assert result["trace"][1]["action"]["inputs"] == {"order": ORDER}
    assert result["session"]._committed == tuple(ORDER)
    assert len(result["session"].comparisons) == 1


def test_the_walk_reaches_the_stop_node():
    """All three of the record's nodes fire, in the record's order."""
    walk = _walk_three_turns(matrix.ordering_graph_record())

    assert [action["kind"] for action in walk["actions"]] == [
        policy_action.PROBE, policy_action.CONSTRUCT, policy_action.STOP]
    assert walk["actions"][2]["target"] == "schedule.task"
    assert walk["cursor"] == {"at": "stop", "progress": 2}


def test_the_committed_order_is_a_permutation_of_the_four_job_ids():
    """`construct` must carry four distinct known job ids or be refused."""
    committed = _committed_order(_driven_session(matrix.ordering_graph_record()))

    assert sorted(committed) == sorted(second_active.JOB_IDS)
    assert len(set(committed)) == 4


def test_the_record_commits_a_fixed_order_and_so_scores_whether_or_not_it_is_right():
    """The record commits `ORDERING_ORDER`, so its score is a property of
    the record, not of what the episode learned.

    One comparison is spent and the observation is never read by a guard,
    so the committed permutation is the same on every task. This is a
    reachability artifact, not a policy claim, and the matrix presents it
    as one. Pinning the number stops "the ordering graph now runs" from
    being read as "the ordering graph now works" — it runs, and it commits
    a constant.
    """
    scores = []
    for seed in (3, 5, 11):
        result = _driven_session(matrix.ordering_graph_record(), seed=seed)
        scores.append(result["session"].score(result["session"]._committed))

    assert [s["n_comparisons"] for s in scores] == [1, 1, 1]
    assert {s["overall"] for s in scores} <= {0.0, 1.0}
    assert list(ORDER) == list(matrix.ORDERING_ORDER)


def test_the_ordering_step_control_is_still_refused_by_the_step_executor():
    """The ordering world has no STEP arm either, and that is measured here.

    The matrix's `build_ordering_registry` registers a STEP arm and a graph
    arm for the ordering world. The graph's absence was the recorded
    finding; the STEP arm's is the same accident one layer up, because
    `boolean_policy.choose_action` validates against the Boolean world
    before it ever runs the policy. So the registry raises on the first
    arm, and the ordering world has *no* working representation until this
    executor is wired in.

    This test is here so that the claim "the ordering graph works" is not
    read as "the ordering world works". It also names the shape of the
    gap: the STEP source is fine, the executor that runs it is Boolean.
    """
    from experiments.ad01 import boolean_policy

    record = matrix.ordering_step_record()
    decide = boolean_policy.choose_action(record)
    action = decide(second_active.public_state(
        second_active.ScheduleSession(second_active.make_task("dev", 5))))

    assert action["target"] == "boolean.task"
    refusal = action["inputs"]["bridge_refusal"]
    assert refusal["stage"] == "policy-step"
    if _CHILD_REFUSAL is not None \
            and _CHILD_REFUSAL.kind == "child-setup-unavailable":
        assert _CHILD_REFUSAL.reason in refusal["reason"]
    else:
        assert "probe target must be boolean.query" in refusal["reason"]


# --- the cursor survives the process boundary ----------------------------


def test_the_cursor_survives_a_fresh_executor_every_turn():
    """No closure survives the child process, so the cursor must.

    Without the cursor, turn two restarts at the start node, whose
    `observed.count == 0` guard no longer holds, and the episode takes the
    fallback arm and stops without ever constructing. So the assertion is
    on the construct happening at all, not on the cursor's shape.
    """
    result = _driven_session(matrix.ordering_graph_record(),
                             fresh_executor=True)

    assert [entry["action"]["kind"] for entry in result["trace"]] == [
        policy_action.PROBE, policy_action.CONSTRUCT]
    assert result["session"]._committed == tuple(ORDER)
    assert result["cursor"] == {"at": "stop", "progress": 2}


def test_the_cursor_and_the_closure_agree():
    """Reseeding from the cursor must be the same episode as keeping it.

    If these diverge, one of the two paths is lying about where the graph
    is, and the parity harness would report a result for a walk the arm
    did not take.
    """
    reseeded = _driven_session(matrix.ordering_graph_record(),
                              fresh_executor=True)
    in_process = _driven_session(matrix.ordering_graph_record(),
                                 fresh_executor=False)

    assert [entry["action"] for entry in reseeded["trace"]] == [
        entry["action"] for entry in in_process["trace"]]


def test_a_cursor_naming_an_unknown_node_is_refused():
    """A cursor from a different graph must not silently restart."""
    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.choose_action(matrix.ordering_graph_record(),
                            at_cursor={"at": "nowhere", "progress": 0})

    assert "unknown node" in str(caught.value)


def test_the_cursor_stays_inside_the_state_size_cap():
    """The cursor is a policy state, so the shared state cap applies."""
    decide = graph.choose_action(matrix.ordering_graph_record())
    decide(second_active.public_state(second_active.ScheduleSession(
        second_active.make_task("dev", 3))))

    assert policy_step.validate_state(decide.s09_cursor()) == {
        "at": "decide", "progress": 1}


# --- the world validator is consulted at both stages --------------------


def test_load_time_validation_rejects_a_construct_that_is_not_a_permutation():
    """Static: the ordering world's own construct rule, at load."""
    record = matrix.ordering_graph_record()
    record["nodes"]["decide"]["arms"][0]["action"]["inputs"]["order"] = [
        JOBS[0], JOBS[1], JOBS[2]]

    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(record)

    assert "permutation of job ids" in str(caught.value)


def test_load_time_validation_rejects_a_comparison_of_a_job_with_itself():
    """Static: `left == right` is refused by the ordering world, not by us."""
    record = matrix.ordering_graph_record()
    record["nodes"]["probe"]["arms"][0]["action"]["inputs"] = {
        "left": JOBS[0], "right": JOBS[0]}

    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(record)

    assert "must be distinct" in str(caught.value)


def test_load_time_validation_rejects_an_unknown_job_id():
    record = matrix.ordering_graph_record()
    record["nodes"]["probe"]["arms"][0]["action"]["inputs"]["right"] = "lint"

    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(record)

    assert "named job ids" in str(caught.value)


def _repeat_probe_record():
    """A graph that re-probes one pair, and is well-formed.

    The first arm's guard is `remaining != -1` rather than `always` because
    the loader requires exactly one `always` fallback per node, and the
    fallback is the stop this node needs for the self-loop to be loadable
    at all. A node whose every arm is a probe has no terminal in its
    reachable set, and the loader refuses a cycle that reaches none.
    """
    return {
        "policy_id": "repeat", "start": "probe",
        "nodes": {
            "probe": {"kind": "action", "arms": [
                _arm({"field": "remaining", "op": "ne", "value": -1},
                     _action("probe", "schedule.compare",
                             {"left": JOBS[0], "right": JOBS[1]},
                             {"queries": 1}), "probe", 1),
                _arm(ALWAYS, _action("stop", "schedule.task"), "probe", 0)]},
        }}


def test_turn_time_validation_sees_the_observations_the_view_carries():
    """Dynamic: the same validator, now with a live view.

    This is the test that separates `view=None` from `view=view`. A graph
    that re-probes a pair it has already compared is well-formed and
    loadable, and is refused only because the second turn's view carries
    the first turn's observation. An executor that validated statically
    only would let it through and the world would refuse it later, at a
    stage the harness does not attribute to the graph.
    """
    repeat = _repeat_probe_record()
    graph.load_policy(repeat)

    result = _driven_session(repeat)

    # The first comparison succeeds, so the loop runs a second time and the
    # repeat is what the turn-time validator catches. The graph's own
    # fallback stop then ends the episode.
    assert [entry["effect"]["kind"] for entry in result["trace"]] == [
        policy_action.PROBE, policy_action.STOP]
    refusal = result["trace"][1]["action"]
    assert refusal["target"] == "schedule.task"
    assert "already compared" in \
        refusal["inputs"]["bridge_refusal"]["reason"]
    assert len(result["session"].comparisons) == 1


def test_the_same_repeat_loads_because_the_static_view_is_empty():
    """The rule that fires at turn two cannot fire at load.

    `_validate_comparison` refuses a pair already in `session.comparisons`.
    At load the session is built from `world.static_view`, which is empty,
    so the same arm is admitted. Were the static view seeded from a real
    observation, a graph could not be re-driven across a process boundary
    at all, because every turn would look like a repeat.
    """
    repeat = _repeat_probe_record()

    graph.load_policy(repeat)
    world = graph.ORDERING_WORLD
    assert world.static_view["observed"] == []

    session = second_active.ScheduleSession(second_active.make_task("dev", 1))
    session.compare(JOBS[0], JOBS[1])
    view = graph.make_view(second_active.public_state(session))
    action = policy_action.parse_action(
        repeat["nodes"]["probe"]["arms"][0]["action"])

    with pytest.raises(second_active.ActionRefused):
        world.validate_action(action, view=view)


def test_the_first_nodes_guard_branch_is_evaluated_against_the_view():
    """A non-empty observation takes the fallback arm and stops at once."""
    session = second_active.ScheduleSession(second_active.make_task("dev", 2))
    session.compare(JOBS[0], JOBS[1])
    decide = graph.choose_action(matrix.ordering_graph_record())
    action = decide(second_active.public_state(session))

    assert action["target"] == "schedule.task"
    assert len(session.comparisons) == 1


def test_a_refused_turn_leaves_the_cursor_where_it_was():
    """A refusal is not a step, so the graph must not advance.

    Otherwise a policy that fails every turn would walk its progress
    counter to the state cap while the world learned nothing. The same
    session is used for both turns, so the second turn's view carries the
    first turn's comparison and the repeat is what gets refused.
    """
    session = second_active.ScheduleSession(second_active.make_task("dev", 1))
    decide = graph.choose_action(_repeat_probe_record())

    first = decide(second_active.public_state(session))
    second_active.apply_action(session, first)
    after_first = decide.s09_cursor()

    second = decide(second_active.public_state(session))
    after_second = decide.s09_cursor()

    assert first["kind"] == policy_action.PROBE
    assert "already compared" in \
        second["inputs"]["bridge_refusal"]["reason"]
    assert after_first == after_second == {"at": "probe", "progress": 1}


def test_a_self_loop_with_no_terminal_is_refused_at_load():
    """The loop above is loadable only because it can stop.

    Every arm of this node is a probe, so the node is reachable and no
    arm of it can reach a terminal. Both halves are here because the pair
    *is* the rule: a cycle is fine, a cycle with no way out is not.
    """
    looped = {
        "policy_id": "loop", "start": "probe",
        "nodes": {
            "probe": {"kind": "action", "arms": [
                _arm({"field": "remaining", "op": "ne", "value": -1},
                     _action("probe", "schedule.compare",
                             {"left": JOBS[0], "right": JOBS[1]},
                             {"queries": 1}), "probe", 1),
                _arm(ALWAYS, _action("probe", "schedule.compare",
                                     {"left": JOBS[2], "right": JOBS[3]},
                                     {"queries": 1}), "probe", 1)]},
        }}

    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(looped)

    assert "cycle cannot reach a terminal" in str(caught.value)


# --- guards read the ordering world's view, not the Boolean one's -------


def test_a_guard_can_read_an_ordering_observation_field():
    """`observed.0.earlier` is an ordering field; there is no Boolean one."""
    record = {
        "policy_id": "obs-guard", "start": "probe",
        "nodes": {
            "probe": {"kind": "action", "arms": [
                _arm({"field": "observed.count", "op": "eq", "value": 0},
                     _action("probe", "schedule.compare",
                             {"left": JOBS[0], "right": JOBS[1]},
                             {"queries": 1}), "early", 1),
                _arm({"field": "observed.0.earlier", "op": "eq",
                      "value": JOBS[1]},
                     _action("construct", "schedule.commit",
                             {"order": ORDER}), "stop", 1),
                _arm(ALWAYS, _action("stop", "schedule.task"), "probe", 0)]},
            "early": {"kind": "action", "arms": [
                _arm(ALWAYS, _action("stop", "schedule.task"), "probe", 0)]},
            "stop": {"kind": "action", "arms": [
                _arm(ALWAYS, _action("stop", "schedule.task"), "stop", 0)]},
        }}
    graph.load_policy(record)

    session = second_active.ScheduleSession(second_active.make_task("dev", 4))
    # Make the first comparison report JOBS[1] as earlier by construction.
    session._comparisons[(JOBS[0], JOBS[1])] = JOBS[1]
    decide = graph.choose_action(record)
    action = decide(second_active.public_state(session))

    assert action["target"] == "schedule.commit"


def test_a_guard_on_an_unknown_field_is_refused_at_load():
    """The guard vocabulary is the world's, so it fails at load, not turn."""
    record = matrix.ordering_graph_record()
    record["nodes"]["probe"]["arms"][0]["guard"] = {
        "field": "observed.0.y.0", "op": "eq", "value": 1}

    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(record)

    assert "unknown field" in str(caught.value)


def test_the_field_vocabulary_is_the_ordering_worlds():
    """What a guard may name, and of what type, comes from the world."""
    types = graph.ORDERING_WORLD.field_types

    assert types["remaining"] == "integer"
    assert types["public_world.split"] == "string"
    assert types["observed.count"] == "integer"
    assert "class_size" not in types
    assert "public_world.hypothesis_class.job_count" in types


def test_a_derived_field_counts_the_ordering_hypothesis_class():
    """`job_count` is the ordering analogue of Boolean's `class_size`."""
    view = graph.make_view(second_active.public_state(
        second_active.ScheduleSession(second_active.make_task("dev", 1))))

    assert graph._field_value(
        view, {}, "public_world.hypothesis_class.job_count") == 4


def test_every_field_the_loader_admits_is_also_readable():
    """A field the loader types but the evaluator cannot read is a trap.

    `FIELD_TYPES`/`field_types` gates load, `_field_value` gates the guard.
    When they disagree, the loader admits a guard that is then silently
    always-false — the graph takes the fallback and the failure looks like
    a policy decision rather than a read that never resolved.

    This walks the whole vocabulary, which is how the single-segment bug
    was found: `remaining` and `instrument` have no `.` to walk, so the
    original loop returned the whole view and compared a dict to an int.
    """
    view = graph.make_view(second_active.public_state(
        second_active.ScheduleSession(second_active.make_task("dev", 1))))
    state = {"at": "probe", "progress": 3}
    expected = {
        "instrument": "ordering-constraints-v1",
        "task_id": view["task_id"],
        "remaining": second_active.MAX_QUERIES,
        "public_world.split": "dev",
        "public_world.max_queries": second_active.MAX_QUERIES,
        "observed.count": 0,
        "public_world.hypothesis_class.job_count": 4,
        "state.at": "probe",
        "state.progress": 3,
    }

    assert sorted(expected) == sorted(graph.ORDERING_WORLD.field_types)
    for field, value in expected.items():
        assert graph._field_value(view, state, field) == value, field
        assert graph._evaluate_guard(
            {"field": field, "op": "eq", "value": value}, view, state), field


def test_the_boolean_executors_own_field_reader_is_wrong_for_these_fields():
    """The defect this lane found, now fixed and pinned in both executors.

    `boolean_graph_policy._field_value` returned the whole view for a
    single-segment field, so `remaining` and `instrument` resolved to a
    dict and every guard naming one of them was silently false. The
    ordering record in `s09_representation_matrix` does not guard on
    either, so no existing Boolean arm was affected — which is why it
    survived. This lane did not own that file; the integration owner fixed
    it, and this test now asserts the fix rather than the defect.

    `tests/test_s09graph_field_reader.py` is the fuller account, including
    the `public_world.*` family and a walk of every field the loader
    admits.
    """
    view = graph.make_view(second_active.public_state(
        second_active.ScheduleSession(second_active.make_task("dev", 1))))

    assert boolean_graph._field_value(view, {}, "remaining") \
        == second_active.MAX_QUERIES
    assert boolean_graph._evaluate_guard(
        {"field": "remaining", "op": "eq",
         "value": second_active.MAX_QUERIES}, view, {})
    assert graph._evaluate_guard(
        {"field": "remaining", "op": "eq",
         "value": second_active.MAX_QUERIES}, view, {},
        graph.ORDERING_WORLD)
