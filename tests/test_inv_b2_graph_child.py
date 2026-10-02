"""A graph arm must reach a world turn, and a missing import must not read as one.

Two defects, both proved by driving the real executors rather than by
reading them.

The first is the load-bearing one. `s09_graph_budget` runs a graph turn in a
bounded child, and that child could not import the `settlement` package
because the launcher handed the child no import path at all. The child died
with `ModuleNotFoundError` before any graph was loaded, and the harness
reported the symptom as `no receipt`. That conflates "the program produced
nothing" with "the program never ran", which is the distinction this project
exists to keep.

The second is that `ordering_graph_policy._parse_action` deep-copied the raw
action node, so a guard's read value was discarded and a graph arm could
only act on a literal. B1 proved it by disagreement on the Boolean world.
These tests prove the repair the same way: two views differing only in an
observed field must now produce different actions.

Offline lane. No live model call, no network, no fixture gateway. The child
under test is a real `LocalLauncher` dispatch on this host.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import ordering_graph_policy as graph
from experiments.ad01 import policy_action
from experiments.ad01 import s09_graph_budget
from experiments.ad01 import s09_representation_matrix as matrix
from experiments.ad01 import second_active
from settlement import broker
from settlement import exec_profile
from settlement.launcher_local import LocalLauncher, PROFILE


# --- 1. a graph arm reaches a world turn ---------------------------------


def test_a_graph_arm_reaches_a_world_turn_through_the_bounded_child():
    """The child imports the package and the graph's arm reaches the world.

    Asserted on the action the real bounded child returns, with its inputs
    spelled out. A test asserting only "no exception" would pass against
    the pre-fix child too, because the pre-fix failure is an exception the
    harness converts into `GraphBudgetRefused` -- the absence of a turn was
    being reported as a refusal rather than as a failure to start.
    """
    record = matrix.ordering_graph_record()
    session = second_active.ScheduleSession(second_active.make_task("dev", 5))
    cursor: dict = {}

    action = s09_graph_budget.run_graph_step(
        record, second_active.public_state(session), cursor, world="ordering")

    assert action == {
        "kind": policy_action.PROBE,
        "target": "schedule.compare",
        "inputs": {"left": "verify", "right": "build"},
        "evidence_refs": [],
        "requested_resources": {"queries": 1},
    }, action
    # The turn moved the graph's own cursor, which is how a child that
    # cannot hold a closure between turns is proved to have advanced.
    assert cursor == {"at": "decide", "progress": 1}, cursor


def test_the_launcher_publishes_the_package_directory_and_not_the_root():
    """Containment, measured rather than argued.

    The child runs with `containment=False`, so the question is not whether
    it can read a host file -- it can, and every receipt says so. The
    question is which *package* the launcher puts on the import path on the
    child's behalf. The study keeps each task's id key in
    `experiments/ad01/worlds.py`, so a launcher that handed over the
    repository root would hand over the key's package for free. Handing
    over `src/` grants exactly one package and does not grant that one.
    """
    environment = exec_profile.scrub_env({})
    search_path = Path(environment["PYTHONPATH"])

    assert (search_path / "settlement" / "__init__.py").exists(), (
        "the child cannot import settlement from the path the launcher set")
    assert (search_path / "experiments").exists() is False, (
        "the launcher's import path exposes the study package tree, which "
        "holds the task-id key")
    assert search_path.resolve() != ROOT.resolve(), (
        "the launcher's import path is the repository root, which is the "
        "change this repair exists not to make")


def test_the_scrub_still_drops_a_secret_the_import_path_change_carries():
    """Widening the import path must not widen the environment.

    The two are different properties and only one of them is being changed
    here, so the other is asserted against a child that actually runs on
    this host.
    """
    result = exec_profile.dispatch(
        "local-process",
        [sys.executable, "-c", "import os;print(sorted(os.environ.items()))"],
        timeout_ms=30_000, cpu_seconds=10, max_output_bytes=65_536,
        extra_env={"SETTLEMENT_GATEWAY_KEY": "s3cr3t", "KEEP_ME": "visible"})

    assert result.returncode == 0, result.stderr
    assert "s3cr3t" not in result.stdout, result.stdout
    assert "'KEEP_ME', 'visible'" in result.stdout, result.stdout
    assert "'PYTHONPATH'" in result.stdout, result.stdout


# --- 2. a failed import is not a child that returned nothing -------------


def _dispatch(tmp_path, operation_id, source):
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(broker.BrokerOp(
        operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": PROFILE,
                 "argv": [sys.executable, "-c", source],
                 "timeout_ms": 30_000, "cpu_seconds": 10,
                 "max_output_bytes": 65_536}))
    assert outcome.sent is True, outcome.refused_reason
    return outcome.receipt.content


def test_a_child_that_died_to_import_is_not_reported_as_a_child_that_ran_nothing(tmp_path):
    """The two receipts are different facts and are named differently.

    A child that never got past its imports and a child that ran to
    completion and printed nothing both produce a receipt with no typed
    worker payload in it. Before this repair the only thing separating them
    was a `returncode` buried in `data`, and every caller in the tree read
    `data["worker"]`, found nothing, and reported `no receipt` for both.
    """
    died = _dispatch(tmp_path, "b2-died", "import settlement_no_such_package")
    ran_empty = _dispatch(tmp_path, "b2-empty", "pass")

    assert died["parse"] == "child-failed", died
    assert ran_empty["parse"] == "empty", ran_empty
    assert died["_verdict"] == "failure", died
    assert ran_empty["_verdict"] == "success", ran_empty
    # The child that died says so in its own words, and names the module.
    assert "settlement_no_such_package" in died["data"]["stderr"], died
    # No synthesized worker envelope. A receipt whose child never produced
    # a typed payload must not carry one, because that would be a claim no
    # worker made.
    assert "worker" not in died["data"], died
    assert "worker" not in ran_empty["data"], ran_empty


def test_a_child_that_ran_and_printed_a_non_envelope_is_a_third_fact(tmp_path):
    """Ran, exited zero, printed something that is not the contract.

    The third state, and the one most easily collapsed into the other two.
    A child that exits zero having printed garbage produced no receipt, and
    it is not the same as a child that produced no receipt because it never
    ran.
    """
    garbage = _dispatch(tmp_path, "b2-garbage", "print('not an envelope')")

    assert garbage["parse"] == "rejected", garbage
    assert garbage["_verdict"] == "failure", garbage
    assert garbage["data"]["returncode"] == 0, garbage


def test_the_graph_harness_names_which_of_the_two_it_saw():
    """The two states reach the harness as two different refusal reasons.

    Asserted on the refusal text, because the receipt vocabulary is the
    launcher's and this is the harness reading it. A harness that reported
    both as `no receipt` left a reader unable to tell a graph that could not
    start from one that ran and declined to answer.

    Driven rather than restated: the harness's own refusal branch is called
    with the two real receipts a host produces for the two real children,
    so the strings asserted here are the ones the code builds.
    """
    import pytest
    import tempfile

    scratch = Path(tempfile.mkdtemp(prefix="b2-map-"))
    died = _dispatch(scratch, "b2-map-died",
                     "import settlement_no_such_package")
    ran_empty = _dispatch(scratch, "b2-map-empty", "pass")
    assert died["parse"] == "child-failed", died
    assert ran_empty["parse"] == "empty", ran_empty

    def _refuse(receipt):
        with pytest.raises(s09_graph_budget.GraphBudgetRefused) as caught:
            s09_graph_budget._refuse_failed_receipt(receipt, timeout_ms=30_000)
        return str(caught.value)

    dead_reason = _refuse(died)
    empty_reason = _refuse(ran_empty)

    assert "child-failed" in dead_reason, dead_reason
    assert "settlement_no_such_package" in dead_reason, dead_reason
    assert empty_reason.endswith("child-ran-and-returned-nothing"), empty_reason
    assert dead_reason != empty_reason
    assert "no receipt" not in dead_reason, dead_reason
    assert "no receipt" not in empty_reason, empty_reason


# --- 3. the view-read repair ---------------------------------------------


def _bound(field):
    """A binding spelled the way a record on disk spells one.

    Built here rather than reached through the module so the test states the
    wire shape instead of trusting the constant that defines it.
    """
    return {graph.FIELD_BINDING: field}


def _stop(inputs=None):
    return {"kind": policy_action.STOP, "target": "schedule.task",
            "inputs": inputs if inputs is not None else {},
            "evidence_refs": [], "requested_resources": {}}


def _ordering_record(policy_id="b2-observed-read"):
    """A graph whose action carries a field it read rather than a literal.

    The guard reads `observed.0.earlier` and the action's `seen` input is
    bound to that same field, so the emitted action has to carry whatever
    the world published.
    """
    return {
        "policy_id": policy_id,
        "start": "decide",
        "nodes": {
            "decide": {"kind": graph.GRAPH_NODE_KIND, "arms": [
                {"guard": {"field": "observed.0.earlier", "op": "ne",
                           "value": ""},
                 "action": _stop({"seen": _bound("observed.0.earlier")}),
                 "next": "done", "progress": 1},
                {"guard": {"always": True}, "action": _stop(),
                 "next": "done", "progress": 0}]},
            "done": {"kind": graph.GRAPH_NODE_KIND, "arms": [
                {"guard": {"always": True}, "action": _stop(),
                 "next": "done", "progress": 0}]},
        },
    }


def _session_republishing(earlier):
    """One comparison, published under one of two `earlier` values.

    Nothing else in the view differs, so `observed.0.earlier` is the only
    field that could change the answer.
    """
    session = second_active.ScheduleSession(second_active.make_task("dev", 5))
    session._comparisons[("analysis", "build")] = earlier
    return session


def test_two_views_differing_only_in_an_observed_value_now_produce_different_actions():
    """The anti-disagreement test, the mirror of B1's.

    B1 handed two views to the Boolean executor and showed the emitted
    actions were byte-identical, which is only possible if the value the
    evaluator read was thrown away. These two views differ in one observed
    field, the action carries that field, and the two emitted actions are
    no longer the same bytes. The assertions are literals, so a graph that
    emitted one action for both would fail on the value and not on a count.
    """
    record = _ordering_record()
    policy = graph.load_policy(record, world=graph.ORDERING_WORLD)
    arm = policy.nodes["decide"].arms[0]
    assert arm.guard["field"] == "observed.0.earlier"

    first = graph.choose_action(record, world=graph.ORDERING_WORLD)(
        second_active.public_state(_session_republishing("analysis")))
    second = graph.choose_action(record, world=graph.ORDERING_WORLD)(
        second_active.public_state(_session_republishing("build")))

    assert first != second, (
        "the two views disagree on observed.0.earlier and the graph emitted "
        "one action for both, so the read value still never reaches the "
        "action")
    assert first["inputs"]["seen"] == "analysis", first
    assert second["inputs"]["seen"] == "build", second


def test_a_bound_field_the_world_does_not_publish_is_refused_rather_than_guessed():
    """An unreadable bound field is a refusal, not a null.

    The alternative is an action carrying `None` where a name belongs, which
    the world would then refuse with a message about the wrong thing.
    """
    import pytest

    record = _ordering_record("b2-unreadable")
    record["nodes"]["decide"]["arms"][0]["action"]["inputs"]["seen"] = \
        _bound("observed.9.earlier")

    graph.load_policy(record, world=graph.ORDERING_WORLD)
    action = graph.choose_action(record, world=graph.ORDERING_WORLD)(
        second_active.public_state(_session_republishing("analysis")))

    refusal = action["inputs"]["bridge_refusal"]
    assert refusal["stage"] == "graph-step", action
    assert "observed.9.earlier" in refusal["reason"], action


def test_a_binding_names_a_field_a_guard_could_not_have_named():
    """The binding is typed by the same world field table a guard is.

    A binding is a claim about a field, so it is gated by the same
    vocabulary. Without that, a record could bind a field the guard grammar
    has never heard of and the arm would resolve it by walking the view.
    """
    import pytest

    record = _ordering_record("b2-unknown-field")
    record["nodes"]["decide"]["arms"][0]["action"]["inputs"]["seen"] = \
        _bound("private.tables")

    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(record, world=graph.ORDERING_WORLD)

    assert "unknown field" in str(caught.value)


def test_a_literal_action_still_loads_and_still_carries_its_literal():
    """The repair adds a capability; it does not change the old records.

    Every record in the tree spells its action out, and those must load and
    emit exactly what they spelled.
    """
    record = matrix.ordering_graph_record()
    policy = graph.load_policy(record, world=graph.ORDERING_WORLD)
    arm = policy.nodes["probe"].arms[0]

    assert arm.action.inputs == {"left": "verify", "right": "build"}, arm
    action = graph.choose_action(record, world=graph.ORDERING_WORLD)(
        second_active.public_state(
            second_active.ScheduleSession(second_active.make_task("dev", 5))))

    assert action["inputs"] == {"left": "verify", "right": "build"}, action


def test_the_boolean_field_b1s_witness_names_is_not_this_executors_vocabulary():
    """Why the proof sits on the ordering world rather than the Boolean one.

    B1 drove `observed.0.y.0` through the Boolean executor. That is a
    Boolean observation path, and `ordering_graph_policy` refuses it at
    load, so the same disagreement cannot be staged on the world this
    repair owns. Asserted so a later reader does not assume the two
    executors share one field vocabulary.
    """
    assert graph.ORDERING_WORLD.field_type("observed.0.y.0") is None
    assert graph.ORDERING_WORLD.field_type("observed.0.earlier") == "string"
