"""The SWE `World` binding, and a typed-AST cell that is a projection.

The last open cell in the representation matrix was a missing *binding*, and
the previous lane proved the seam without writing it. These tests pin the
writing, and they pin the two things that make it honest:

* the SWE arm's origin is a stand-in, not an acquisition, and the gate that
  caught C15 cannot be talked into reading it as one;
* the typed AST can carry a value it read out of the view into an action,
  and the action graph cannot, which is the concrete attempted behaviour
  behind the recorded missing cell.

Nothing here dispatches, opens a database, or writes. `tests/test_s09_
test_db_safety.py` is unaffected because no database is named anywhere in
this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_ast_policy as frozen
from experiments.ad01 import ordering_graph_policy as graph
from experiments.ad01 import policy_action
from experiments.ad01 import s09_swe_ast as swe_ast
from experiments.ad01 import s09_swe_binding as binding
from experiments.ad01 import s09_swe_experiment as experiment
from experiments.ad01 import s09_swe_tasks as tasks
from settlement import child_limits
from settlement.child_limits import ChildLimits

REQUIRES_BOUNDED_CHILD = pytest.mark.skipif(
    child_limits.child_setup_refusal(ChildLimits(cpu_seconds=10)) is not None,
    reason="requires a host that can install the declared child CPU limit")
from experiments.ad01 import s09_swe_world as swe

HELD_OUT = [(template, mechanism)
            for template in tasks.HELD_OUT_TEMPLATES
            for mechanism in tasks.HELD_OUT_MECHANISMS]


def _observed_view(index: int = 0):
    """A real held-out view with one public test already observed."""
    template, mechanism = HELD_OUT[index]
    record = tasks.instance("held_out", template, mechanism)
    session = swe.SweSession(record)
    session.run_public_test(record["public_tests"][0]["name"])
    return session.policy_view()


# --- the binding ---------------------------------------------------------


def test_the_swe_world_is_a_world_value_and_not_a_reshaped_executor():
    """The seam is a value, so nothing above it had to change.

    `s09_e1_world_fit_probe` measured that a `World` whose `make_view`
    projects is enough, and left the value unwritten. This pins that the
    shipped value really is a `World` built from the SWE world's own
    published constants, so a reader can check the targets and the
    permitted kinds against `s09_swe_world` rather than take them on trust.
    """
    assert isinstance(binding.SWE_WORLD, graph.World)
    assert binding.SWE_WORLD.name == "swe"
    assert binding.SWE_WORLD.probe_target == swe.ACTION_TARGETS[
        policy_action.OBSERVE]
    assert binding.SWE_WORLD.construct_target == swe.CONSTRUCT_TARGETS[0]
    assert binding.SWE_WORLD.stop_target == swe.ACTION_TARGETS[policy_action.STOP]
    assert binding.SWE_WORLD.allowed_kinds == frozenset(swe.ACTION_TARGETS)


def test_the_swe_world_guard_vocabulary_is_the_worlds_own_observation_keys():
    """Every admitted observation key is a key the SWE world publishes.

    The guard vocabulary is a per-`World` value, so an arm can read
    whatever the binding declares. Declaring a key the world never emits
    would let a guard pass at load and then raise at run, which is the
    failure mode `s09_e1_world_fit_probe.observation_index_is_finite`
    warns about. This is measured over the real panel.
    """
    published = set()
    for template, mechanism in HELD_OUT:
        record = tasks.instance("held_out", template, mechanism)
        session = swe.SweSession(record)
        session.run_public_test(record["public_tests"][0]["name"])
        for item in session.policy_view()["symptom"]["observed"]:
            published |= set(item)

    assert published == {"actual", "expected", "kind", "test"}
    assert binding.swe_observation_keys() == frozenset(published)
    declared = {field.rsplit(".", 1)[1]
                for field in binding.SWE_WORLD.field_types
                if field.startswith("observed.0.")}
    assert declared <= published


def test_the_binding_steers_a_real_arm_through_the_real_evaluator_on_every_held_out_instance():
    """The 30 of 30, as a regression rather than a probe's claim.

    Every stage runs for real: the record goes through `load_policy`, the
    view through `SWE_WORLD.make_view`, and the chosen arm through
    `_evaluate_guard`. A `World` that fails any of them on any instance
    is a seam that happened to hold once.
    """
    chosen = []
    for index in range(len(HELD_OUT)):
        view = _observed_view(index)
        policy = graph.load_policy(
            binding.swe_graph_record("probe-%d" % index),
            world=binding.SWE_WORLD)
        projected = graph.make_view(view, world=binding.SWE_WORLD)
        node = policy.nodes[policy.start]
        arm = next(candidate for candidate in node.arms
                   if graph._evaluate_guard(candidate.guard, projected, {},
                                            binding.SWE_WORLD))
        chosen.append("%s/%s" % (arm.action.kind, arm.action.target))

    assert len(chosen) == 30
    assert set(chosen) == {"construct/code.inspect"}, sorted(set(chosen))


def test_the_projection_refuses_a_view_that_exposes_hidden_tables():
    """The projection re-shapes a published view; it does not widen it.

    `boolean_ast_policy._shared_view` refuses a public state carrying
    `tables`, and so does this one. A projection that quietly passed the
    whole SWE state through would let a program see something the policy
    view does not publish.
    """
    with pytest.raises(Exception, match="hidden tables"):
        binding.project_swe_view({"tables": {}, "instrument": "x"})


# --- the origin ----------------------------------------------------------


def test_the_ast_cell_declares_a_stand_in_origin_and_never_claims_an_acquisition():
    """A projection over a frozen authored policy is not an acquisition.

    `s09_swe_ast` borrows the frozen loader, the frozen node set and the
    frozen interpreter, and adds a view projection. No provider wrote
    those bytes, so the record says `fixture-stand-in`, and the gate leg
    added for C15 reads the claim rather than the label.
    """
    from experiments.ad01 import policy_step

    assert swe_ast.ORIGIN in policy_step.POLICY_ORIGINS
    assert swe_ast.ORIGIN == "fixture-stand-in"
    for index in range(4):
        record = swe_ast.lineage_record("swe-ast-L%d" % index, index=index)
        assert record["origin"] == swe_ast.ORIGIN
        assert record["acquisition_evidence"]["earned"] is False
        assert record["acquisition_evidence"]["reason"]
        # the bytes the frozen loader reads carry no origin of their own,
        # so nothing above the receipt could call them acquired
        assert "origin" not in record["ast_record"]["artifact"]


def test_the_gate_leg_cannot_read_the_ast_cell_as_an_acquisition():
    """The C15 leg, driven on a bundle carrying this cell.

    `earned_origin` returns a claimed `model-acquired` unchanged when the
    arm's own construction record shows an earned provider, and demotes it
    to `fixture-stand-in` otherwise. This cell claims a stand-in, so it is
    never in the acquired set at all: a bundle that contains it cannot
    satisfy `no_earned_acquired_arm` on its strength.
    """
    from experiments.ad01 import s09_verdict as verdict

    record = swe_ast.lineage_record("swe-ast-L0", index=0)
    bundle = verdict.Bundle(
        root=Path("/nonexistent"),
        freeze={"policy_identities": {"swe-ast-L0": {
            "artifact": {"origin": record["origin"],
                         "source_digest": record["ast_record"]["artifact"]
                         ["ast_digest"]}}}},
        construction={}, operations={}, use_records=(),
        accounting={}, assessment=())

    assert bundle.arm_origin("swe-ast-L0") == verdict.ORIGIN_STAND_IN
    assert bundle.earned_origin("swe-ast-L0") == verdict.ORIGIN_STAND_IN
    assert bundle.earned_arms_by_origin(verdict.ORIGIN_ACQUIRED) == ()


def test_the_gate_would_demote_this_cell_if_it_ever_claimed_an_acquisition():
    """The protection is live, not a label nobody checks.

    A bundle whose freeze claims `model-acquired` for the same record, with
    no construction evidence beside it, is demoted by `earned_origin`. This
    is the C15 defect exactly: the label said one thing and the record
    could not support it. If this test ever fails because the demotion was
    removed, the guard is gone and the label is the only thing left.
    """
    from experiments.ad01 import s09_verdict as verdict

    record = swe_ast.lineage_record("swe-ast-L0", index=0)
    forged = dict(record, origin=verdict.ORIGIN_ACQUIRED)
    bundle = verdict.Bundle(
        root=Path("/nonexistent"),
        freeze={"policy_identities": {"swe-ast-L0": {
            "artifact": {"origin": forged["origin"],
                         "source_digest": record["ast_record"]["artifact"]
                         ["ast_digest"]}}}},
        construction={}, operations={}, use_records=(),
        accounting={}, assessment=())

    assert bundle.arm_origin("swe-ast-L0") == verdict.ORIGIN_ACQUIRED
    assert bundle.earned_origin("swe-ast-L0") == verdict.ORIGIN_STAND_IN


# --- the cells -----------------------------------------------------------


def test_every_supported_cell_four_lineages_with_distinct_record_bytes():
    """Four lineages per cell, and no two hash alike.

    Independence is the record digest, not the name. Four lineages whose
    records hash alike would be one lineage wearing four names, which is
    the named way to manufacture replication.
    """
    for kind in experiment.REPRESENTATIONS:
        cell = [lineage for lineage in experiment.LINEAGES
                if lineage.representation_kind == kind]
        assert len(cell) == 4, kind
        assert len({lineage.digest for lineage in cell}) == 4, kind


def test_the_ast_and_graph_lineages_build_and_the_step_lineages_still_do():
    """Both previously missing cells are now cells, not refusals.

    `built_ok` is what `run_matrix` branches on, so a cell that is still a
    refusal is a cell that produced 156 rows of nothing.
    """
    for kind in experiment.REPRESENTATIONS:
        cell = [lineage for lineage in experiment.LINEAGES
                if lineage.representation_kind == kind]
        assert all(lineage.built_ok for lineage in cell), \
            [lineage.build_error for lineage in cell if not lineage.built_ok]


@REQUIRES_BOUNDED_CHILD
def test_the_ast_cell_carries_a_test_name_it_read_out_of_the_view():
    """The typed AST is contingent: its action input comes from the view.

    Turn two of the episode reads `observed[0].test` and puts that string
    into the next action's `test` input. If the program were committing a
    table it already had, the emitted name would be the same whatever the
    world showed. This is the check that a fixed-schedule arm fails.
    """
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    session = swe.SweSession(record)
    first = record["public_tests"][0]["name"]
    second = record["public_tests"][1]["name"]

    driver = swe_ast.choose_action(swe_ast.make_record("probe", index=0))
    first_action = driver(session.policy_view())
    assert first_action["kind"] == "check", \
        "with nothing observed the program runs the public tests"
    assert first_action["target"] == swe.ACTION_TARGETS[policy_action.CHECK]

    # The program names no test at all: it reads `observed[0].test` out of
    # the view and puts that string in the action. A policy committing a
    # schedule it already held would have to have `first` written into its
    # document, and the document is checked for that below.
    session.run_public_test(first)
    second_action = driver(session.policy_view())
    assert second_action["kind"] == "observe"
    assert second_action["inputs"]["test"] == first, \
        "the action input did not come from the observation"
    assert second != first

    body = repr(swe_ast.document("probe", index=0))
    assert first not in body and second not in body, (
        "the document names a test, so the value it emits is a constant "
        "rather than something it read")


def test_the_action_graph_cannot_carry_a_read_value_into_an_action():
    """The graph's missing cell, with the attempted behaviour named.

    A graph arm's action is a literal in the record: `_parse_action` reads
    the raw node and deep-copies it, so no guard value reaches an action
    input. A graph that localized a test would therefore have to spell the
    test name in the record, which is a constant it already had rather
    than something the world published.

    The attempt is driven rather than asserted: a graph whose guard reads
    the failing test out of the view and whose localize arm carries the
    matching name is loaded, and the loaded action is then shown to hold a
    literal while the guard's field is a dotted path into the same view.
    """
    raw = {
        "policy_id": "swe-localize-attempt",
        "start": "decide",
        "nodes": {
            "decide": {"kind": graph.GRAPH_NODE_KIND, "arms": [
                {"guard": {"field": "observed.0.test", "op": "ne",
                           "value": ""},
                 "action": {"kind": "construct", "target": "code.inspect",
                            "inputs": {"line": 1},
                            "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 1},
                {"guard": {"always": True},
                 "action": {"kind": "stop", "target": "swe.task",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 0}]},
            "done": {"kind": graph.GRAPH_NODE_KIND, "arms": [
                {"guard": {"always": True},
                 "action": {"kind": "stop", "target": "swe.task",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 0}]},
        },
    }
    policy = graph.load_policy(raw, world=binding.SWE_WORLD)
    arm = policy.nodes["decide"].arms[0]

    # the guard reads the view; the action it selects carries a literal
    assert arm.guard["field"] == "observed.0.test"
    view = binding.project_swe_view(_observed_view(0))
    assert graph._evaluate_guard(arm.guard, view, {}, binding.SWE_WORLD)
    assert arm.action.inputs == {"line": 1}, \
        "the action holds a literal; nothing the guard read reached it"

    # and the one action that would have to name a test cannot even be
    # written: `code.localize` is admitted only for a test the world has
    # already seen fail, and the load-time static view has failed none, so
    # the world's own admission refuses the record before any guard runs.
    localize = dict(raw, policy_id="swe-localize-attempt-2")
    localize["nodes"] = dict(raw["nodes"])
    localize["nodes"]["decide"] = {
        "kind": graph.GRAPH_NODE_KIND, "arms": [
            {"guard": {"field": "observed.0.test", "op": "ne", "value": ""},
             "action": {"kind": "construct", "target": "code.localize",
                        "inputs": {"test": view["observed"]["0"]["test"]},
                        "evidence_refs": [], "requested_resources": {}},
             "next": "done", "progress": 1},
            {"guard": {"always": True},
             "action": {"kind": "stop", "target": "swe.task", "inputs": {},
                        "evidence_refs": [], "requested_resources": {}},
             "next": "done", "progress": 0}]}
    with pytest.raises(Exception, match="does not admit"):
        graph.load_policy(localize, world=binding.SWE_WORLD)

    assert "action-graph" in swe_ast.missing_cells()
    cell = swe_ast.missing_cells()["action-graph"]
    assert cell["missing_cell"] and cell["witness"]


def test_both_new_cells_repair_nothing_and_the_missing_cell_is_recorded():
    """A cell that runs and scores zero is a finding; a refusal is not.

    The typed AST's node set publishes no view field carrying the program
    under repair, so it cannot choose an edit line from what it observed. It
    does build replacement source text — that half was measured and is no
    longer a recorded limit — but the cells as built do not repair, and the
    record says why with the refusal the frozen loader produced rather than
    leaving the reader to infer it from a zero.
    """
    findings = swe_ast.expressivity()
    assert findings["can"], findings
    cannot = findings["cannot"][0]
    assert cannot["missing_cell"]
    assert cannot["witness"]

    for kind in (experiment.TYPED_AST, experiment.ACTION_GRAPH):
        cell = [lineage for lineage in experiment.LINEAGES
                if lineage.representation_kind == kind]
        driver = experiment.lineage_driver(cell[0])
        episode = experiment.run_episode(driver, split="held_out", seed=0)
        assert episode["repaired"] is False
        assert episode["final"]["outcome"] != "repaired"


def test_each_cell_runs_in_its_own_executor_and_not_the_step_child():
    """Three representations must not share one executor.

    `lineage_driver` dispatches on the cell. Deleting that dispatch is
    the tempting simplification: the STEP child would then run the typed
    AST's document and the graph's record, both of which it cannot read,
    and both would be swallowed by the `except Exception` into a
    `stop`. The matrix would then report three names over one policy and
    every refusal would be invisible.

    So the check is on which executor each cell reaches, driven rather
    than inferred: the STEP cell goes through the shared bounded child,
    the typed AST through the frozen AST interpreter, and the graph
    through the graph executor's own cursor.
    """
    seen = {}
    for lineage in experiment.LINEAGES:
        if lineage.representation_kind in seen:
            continue
        driver = experiment.lineage_driver(lineage)
        code = getattr(driver, "__code__", None)
        seen[lineage.representation_kind] = code.co_filename if code else "?"

    graph_path = graph.__file__
    assert seen[experiment.ACTION_GRAPH] == graph_path, seen
    assert seen[experiment.TYPED_AST] != graph_path, seen
    assert seen[experiment.PYTHON_STEP] != graph_path, seen
    assert len(set(seen.values())) == 3, seen


def test_the_graph_cell_really_walks_its_cursor_rather_than_restarting():
    """A graph that restarted would answer as though it had not advanced.

    `choose_action` holds the cursor in its closure, so the second turn
    of an episode must not come from the start node. The record's arms
    branch on an observation field, so an episode that observed first
    takes a different arm on the second turn than one that has not.
    """
    view = _observed_view(0)
    driver = experiment.lineage_driver(
        next(lineage for lineage in experiment.LINEAGES
             if lineage.name == "action-graph-L0"))
    first = driver(view)
    second = driver(view)
    assert first["kind"] == "construct"
    assert second["kind"] == "stop", \
        "the graph restarted instead of advancing its cursor"

    # an unobserved view takes the other arm, which is what makes the
    # branch contingent rather than a fixed first move
    fresh = experiment.lineage_driver(
        next(lineage for lineage in experiment.LINEAGES
             if lineage.name == "action-graph-L1"))
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    unobserved = swe.SweSession(record).policy_view()
    assert fresh(unobserved)["kind"] == "stop", \
        "the arm did not depend on what the world had published"


def test_no_lineage_source_names_a_fault_mechanism_or_the_reference():
    """The cell's records are not answers wearing a policy's clothes.

    The STEP lineages already carry this check. The two new cells are
    authored the same way, so the same check is applied to them: neither
    the record bytes nor the projection may mention a mechanism, a patch
    or the reference program.
    """
    forbidden = ("mechanism", "patch", "reference_source", "injected")
    for lineage in experiment.LINEAGES:
        if lineage.representation_kind == experiment.PYTHON_STEP:
            continue
        blob = repr(lineage.record).lower()
        for word in forbidden:
            assert word not in blob, (lineage.name, word)
