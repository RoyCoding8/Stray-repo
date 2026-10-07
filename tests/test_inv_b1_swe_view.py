"""What the SWE world actually supports, measured rather than asserted.

The milestone-B inventory reads the SWE harness as forked and names the
view contract at seven fields. Both were true of an older tree and are
false of this one, and the difference decides what this lane is. The view
contract is declared per world and the SWE world is admitted whole
(`s09_swe_experiment.path_fork` reports `common_path_usable: true` with no
missing and no extra field), so the fork the inventory describes is
already closed and re-closing it would be work against a repair someone
else landed.

What is not closed is `compare_arms` on this world, and each arm is
blocked at a different place with a different reason. Every test here
drives the real executor and names the refusal it produced, because the
acceptance for a cell that still cannot be supported is a concrete
witness and not a repaired machinery. A test that only asserted a
proportion or a count would pass against any future state of the code,
which is the failure mode this file exists to prevent.

Three findings, each pinned below.

The typed-AST cell can build replacement source text. The recorded
missing cell says it cannot, and that claim is false: the frozen loader
accepts a document whose edit payload is assembled by nodes, the SWE
world admits the resulting `use/code.repair`, and the repair runs. What
the cell cannot do is read the program to choose the line, which is a
different and much smaller limit.

The graph arm carries a value it read, on the executor that binds one.
`ordering_graph_policy` resolves a bound action input at turn time, so
a localize names the failing test the world published rather than a
literal the record spelled. `boolean_graph_policy` is the executor this
world's graph path runs, it publishes no binding, and it still discards
the read value. Both halves are driven below, so neither can rot into a
claim.

Neither graph arm reaches a world turn at all on this host. The bounded
child the parity harness runs a graph through cannot import `settlement`,
because `s09_graph_budget` puts the repository root on the child's path
where the package lives under `src/`. That is a harness defect and it is
the largest of the three, but it is not in this lane's files.
"""

from __future__ import annotations

import hashlib

import pytest

from experiments.ad01 import boolean_graph_policy
from experiments.ad01 import boolean_rule
from experiments.ad01 import ordering_graph_policy
from experiments.ad01 import policy_action
from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_graph_budget
from experiments.ad01 import s09_swe_ast as swe_ast
from experiments.ad01 import s09_swe_binding as swe_binding
from experiments.ad01 import s09_swe_experiment as swe_experiment
from experiments.ad01 import s09_swe_tasks as swe_tasks
from experiments.ad01 import s09_swe_world as swe
from settlement import child_limits
from settlement.child_limits import ChildLimits

REQUIRES_BOUNDED_CHILD = pytest.mark.skipif(
    child_limits.child_setup_refusal(ChildLimits(cpu_seconds=10)) is not None,
    reason="requires a host that can install the declared child CPU limit")


def _task():
    return swe_tasks.instances_for_seed("held_out", 0)


def _repair_document() -> dict:
    """A document that assembles its edit payload out of nodes.

    Nothing in it is a raw JSON string: the line number, the operation and
    the replacement text are each built by an expression node, and the
    payload is an object node over a list node. A node set that cannot
    build source text refuses this at the loader, which is what makes
    running it a measurement rather than a reading.
    """
    edit = {"op": "obj", "fields": {
        "line": {"op": "const", "value": 3},
        "op": {"op": "const", "value": "replace"},
        "text": {"op": "const", "value": "    total = 0"}}}
    return {"policy_id": "swe-repair-probe", "entry": {
        "op": "return_action", "kind": "use", "target": "code.repair",
        "inputs": {"op": "obj", "fields": {"edits": {"op": "list",
                                                     "items": [edit]}}},
        "evidence_refs": [], "requested_resources": {},
        "state": {"op": "const", "value": {}}}}


def test_the_swe_view_contract_is_declared_and_the_world_is_admitted_whole():
    """The fork the inventory names is closed, and this pins it shut.

    Twelve declared fields, twelve published, nothing missing and nothing
    extra, and no refusal. A view contract that grew a thirteenth field
    without the world publishing it would fail here rather than quietly
    becoming a subset test, which is the property the exactness buys.
    """
    fork = swe_experiment.path_fork()

    assert fork["common_path_usable"] is True
    assert fork["refusal"] is None
    assert fork["missing_from_swe"] == []
    assert fork["extra_in_swe"] == []
    declared = parity.VIEW_CONTRACT_FIELDS[swe.INSTRUMENT_ID]
    assert declared == frozenset(fork["fields_published_by_swe"])
    assert len(declared) == 12, (
        "the SWE view publishes twelve fields; a different count means the "
        "world's own surface moved and this record moved with it")
    assert "source" in declared and "public_tests" in declared, (
        "the fields a repair arm needs are declared, which is what makes "
        "their absence from the executor a refusal rather than a gap")


@REQUIRES_BOUNDED_CHILD
def test_the_typed_ast_cell_builds_replacement_source_text_and_the_world_runs_it():
    """The recorded missing cell is false, so the cell is driven instead.

    The claim under test is the one `missing_cells` records: that the
    frozen node set builds no replacement source text. The loader accepts
    the document, the SWE world admits the action it produces, and
    `apply_action` runs the repair. A recorded expressivity limit that a
    three-line run contradicts is not a limit.
    """
    from experiments.ad01 import boolean_ast_policy as frozen

    document = _repair_document()
    record = {"artifact": {
        "kind": "learning-policy", "representation": "typed-ast",
        "version": frozen._REPRESENTATION, "policy_id": document["policy_id"],
        "ast_digest": hashlib.sha256(
            frozen._canonical(document)).hexdigest()},
        "policy_ast": document}

    body, _ = frozen._load(record)
    task = _task()
    session = swe.SweSession(task)
    view = swe_ast.swe_view(session.policy_view())
    result = frozen._run_step(
        body, view, {}, timeout_ms=10_000, cpu_seconds=5,
        max_output_bytes=65_536, memory_bytes=None)
    action, _ = policy_action.parse_step_result(result)

    assert action.kind == policy_action.USE
    assert action.target == "code.repair"
    assert action.inputs["edits"] == [
        {"line": 3, "op": "replace", "text": "    total = 0"}], (
        "the payload is assembled by nodes, so the text reached the action "
        "rather than being spelled in the record")
    assert swe.admits(None, session.policy_view(), action.as_dict()) is True
    effect = swe.apply_action(session, action.as_dict())
    assert effect["repaired"]["edited"] == [3], effect


def test_the_typed_ast_cells_remaining_limit_is_reading_the_program():
    """What the cell cannot do, named exactly and measured.

    It cannot read the program under repair, so it cannot choose which
    line to edit from what it sees. That is the whole of the limit, and it
    is the loader's own refusal rather than a sentence about a grammar.
    """
    from experiments.ad01 import boolean_ast_policy as frozen

    with pytest.raises(Exception) as caught:
        frozen._expr({"op": "field", "scope": "view", "name": "source"},
                     "p", frozen._Budget(), 1)
    assert "unknown view field 'source'" in str(caught.value)

    cell = swe_ast.missing_cells()["typed-ast"]
    assert "node set refuses view.source" in cell["witness"], cell["witness"]
    # The recorded cell must not still claim the node set cannot build
    # source text. That claim is false (the test above drives it), and a
    # recorded refusal that overstates the limit is worse than none.
    assert "no node that builds replacement source text" not in \
        cell["missing_cell"], (
            "the cell still names the source-text limit the executor does "
            "not have; narrow it to reading the program")
    assert "no node that builds source text" not in \
        swe_ast.expressivity()["cannot"][0]["missing_cell"]


def test_a_graph_arm_acts_on_a_value_it_read_where_the_binding_exists():
    """The view-read defect, closed on the executor that carries a binding.

    B1 proved this defect by disagreement: two views differing on one
    observed field produced byte-identical actions. B2 closed it on
    `ordering_graph_policy` with `FIELD_BINDING`, and
    `test_two_views_differing_only_in_an_observed_value_now_produce_different_
    actions` asserts that on the ordering world. Copying that assertion
    here would be a second copy of one test, not coverage.

    So this drives B1's own angle instead: the *view-read path* B1
    identified, on the world B1 was measuring. A record binds an action
    input to `observed.0.test`, the executor resolves it at turn time, and
    the failing test name the world published arrives in the action. That
    is the property B1 asserted as impossible.

    And the limit that survives is asserted here rather than left silent:
    `boolean_graph_policy` is the executor the SWE graph path actually
    runs, it publishes no binding, and it still discards the read value.
    Both halves are driven, so neither can rot into a claim.
    """
    record = _bound_localize_record()

    # The binding is gated by the same world field table a guard is, so
    # the record loads rather than being refused on a field it has not
    # heard of.
    policy = ordering_graph_policy.load_policy(
        record, world=swe_binding.SWE_WORLD)
    assert policy.start == "localize"

    task = _task()
    session = swe.SweSession(task)
    session.run_all_public()
    view = session.policy_view()
    published = [item["test"] for item in view["symptom"]["observed"]]
    assert published, "the world published no failing test to bind"

    action = ordering_graph_policy.choose_action(
        record, world=swe_binding.SWE_WORLD)(view)

    assert action["kind"] == policy_action.CONSTRUCT, action
    assert action["target"] == "code.localize", action
    assert action["inputs"]["test"] == published[0], (
        "the action must carry the test name the world published, read "
        "through the binding, rather than a literal the record spelled")
    assert swe.admits(None, view, action) is True, (
        "the SWE world admits a localize naming a test it saw fail, so a "
        "bound localize is a real repair step and not a refused one")
    effect = swe.apply_action(session, action)
    assert effect["localized"]["test"] == published[0], effect

    # The same disagreement that proved the defect, against the executor
    # the SWE graph cell actually runs. This is the limit that survives
    # the repair, and it is measured rather than assumed.
    literal = {
        "policy_id": "b1c-boolean-literal",
        "start": "decide",
        "nodes": {
            "decide": {"kind": "action", "arms": [
                {"guard": {"field": "observed.0.y.0", "op": "eq",
                           "value": 1},
                 "action": {"kind": "stop", "target": "boolean.task",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 1},
                {"guard": {"always": True},
                 "action": {"kind": "stop", "target": "boolean.task",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 0}]},
            "done": {"kind": "action", "arms": [
                {"guard": {"always": True},
                 "action": {"kind": "stop", "target": "boolean.task",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 0}]},
        },
    }
    assert not hasattr(boolean_graph_policy, "FIELD_BINDING"), (
        "the Boolean executor grew a binding; re-read this test, because "
        "the limit it measures is now closed there too")

    def _boolean_view(first_output: int) -> dict:
        return {"instrument": "boolean-rule-v1", "task_id": "t",
                "split": "dev", "max_queries": boolean_rule.MAX_QUERIES,
                "remaining": boolean_rule.MAX_QUERIES - 1,
                "observed": [{"x": 0, "y": [first_output, 0, 0, 0]}],
                "hypothesis_class": {"class_size": 2},
                "action_schema": _boolean_schema()}

    first = boolean_graph_policy.choose_action(literal)(_boolean_view(1))
    second = boolean_graph_policy.choose_action(literal)(_boolean_view(0))

    assert first == second, (
        "the Boolean executor now disagrees on observed.0.y.0 and emits "
        "one action for both, so it carries a read value; the recorded "
        "witness below no longer describes it")
    assert "boolean_graph_policy" in swe_ast.missing_cells()["action-graph"][
        "witness"], (
        "the recorded witness must name the executor that still discards "
        "the read value, or it names a repair that already happened")


def _bound_localize_record() -> dict:
    """A SWE graph record whose localize input is bound, not spelled.

    The arm reads `observed.0.test` and puts that value in the action. The
    record names the field; it does not name the test.
    """
    return {
        "policy_id": "b1c-bound-localize",
        "start": "localize",
        "nodes": {
            "localize": {"kind": "action", "arms": [
                {"guard": {"field": "observed.0.test", "op": "ne",
                           "value": ""},
                 "action": {"kind": "construct", "target": "code.localize",
                            "inputs": {"test": {
                                ordering_graph_policy.FIELD_BINDING:
                                    "observed.0.test"}},
                            "evidence_refs": [], "requested_resources": {}},
                 "next": "done", "progress": 1},
                {"guard": {"always": True},
                 "action": {"kind": "stop", "target": "swe.task",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 0}]},
            "done": {"kind": "action", "arms": [
                {"guard": {"always": True},
                 "action": {"kind": "stop", "target": "swe.task",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}},
                 "next": "done", "progress": 0}]},
        },
    }


def _boolean_schema() -> dict:
    from experiments.ad01 import boolean_active
    return boolean_active.action_schema(boolean_rule.MAX_QUERIES)


def test_the_graph_child_now_imports_the_package_it_needs():
    """The largest blocker, closed. This pins it shut.

    B1 recorded that the bounded child received the repository root while
    the package it needs lives under `src/`, so it died with
    `ModuleNotFoundError` before any graph was loaded and the harness
    reported the symptom as `no receipt`. That was a defect in the child's
    import path and it is repaired: `package_search_path()` publishes
    `src/`.

    The assertion is on the live value, because the point of the repair is
    that a child can now import. It is `src/` and not the repository root
    for a containment reason, not a convenience: the study keeps each
    task's id key under `experiments/`, so a child that could import the
    study package tree could invert a published opaque id back to its
    seed. So this asserts both halves: the package is reachable, and the
    study tree is not.
    """
    import sys
    from pathlib import Path
    from settlement import exec_profile
    del sys

    published = Path(exec_profile.package_search_path())

    assert (published / "settlement" / "__init__.py").exists(), (
        "the published import path no longer carries the package a child "
        "needs, so the graph child cannot start again")
    assert not (published / "experiments").exists(), (
        "the published import path grants the study package tree, which "
        "holds the task-id key; the containment decision is `src/` and not "
        "the repository root")
    assert published != Path(s09_graph_budget.__file__).resolve(
    ).parent.parent.parent, (
        "the import path widened to the repository root, which would make "
        "the task-id key reachable from every child")

    # The driver still names the study package, because the graph executor
    # is itself a study module. That is a different path from the
    # launcher's, and it is the reason the two are separate.
    driver = s09_graph_budget._GRAPH_DRIVER
    assert "sys.path.insert(0, sys.argv[1])" in driver and (
        "settlement" in driver or "broker" in driver), (
        "the child's own driver no longer imports what it runs; re-read "
        "this test before assuming the graph child still works")


def test_the_swe_world_admits_a_localize_that_reads_the_failing_test_it_observed():
    """The gate a repaired graph arm would have to satisfy, already true.

    `code.localize` is admitted only for a test the world has seen fail,
    which is why the graph cell's load-time check refuses it: the static
    view is the one in which nothing has failed. At turn time the world
    admits a localize naming a test the arm observed, so the load-time
    refusal is a property of the load-time view and not of the world.

    This is what the view-read defect is standing in front of. A graph arm
    that could carry the observed name into the action could reach this
    gate; one holding a literal cannot.
    """
    task = _task()
    session = swe.SweSession(task)
    session.run_all_public()
    view = session.policy_view()

    assert view["symptom"]["observed"], view["symptom"]
    name = view["symptom"]["observed"][0]["test"]
    localize = {"kind": "construct", "target": "code.localize",
                "inputs": {"test": name}, "evidence_refs": [],
                "requested_resources": {}}

    assert swe.admits(None, view, localize) is True
    effect = swe.apply_action(session, localize)
    assert effect["localized"]["test"] == name
    # And the load-time view, in which nothing has failed, refuses it.
    assert swe.admits(None, swe_binding.SWE_WORLD.static_view, localize) is False


@REQUIRES_BOUNDED_CHILD
def test_compare_arms_on_the_swe_world_reports_each_arms_own_named_refusal():
    """The end-to-end reachability check, with the three reasons recorded.

    Acceptance for this lane is three comparable representation kinds or a
    named refusal per unsupported cell. The cells are not comparable, so
    this records which arm is blocked where, by what, and that a change to
    any of the three is deliberate rather than silent.
    """
    registry = parity.ArmRegistry()
    step = swe_experiment.build_step_lineages()[0]
    registry.register(name="b1-step", representation_kind=parity.PYTHON_STEP,
                      driver_factory=swe_experiment.lineage_driver,
                      policy_record=step.record)
    ast = parity.register_typed_ast(
        registry, name="b1-ast",
        policy_record=swe_ast.make_record("b1-ast", index=0))
    graph = parity.register_action_graph(
        registry, name="b1-graph",
        policy_record=swe_binding.swe_graph_record(), world="swe")
    assert isinstance(ast, parity.ArmRegistration)
    assert isinstance(graph, parity.ArmRegistration)

    result = parity.compare_arms(
        registry, ("b1-step", "b1-ast", "b1-graph"),
        parity.ComparisonConditions(split="held_out", seed=0, max_queries=2,
                                    world="swe"))

    assert result.status == "incomparable"
    by_arm = {issue.arm_names[0]: issue for issue in result.incompatibilities
              if issue.arm_names}

    # The STEP arm is not a policy defect: the harness hands every driver
    # factory the step budget and the SWE lineage driver takes no such
    # argument. Named so the fix is a signature, not a guess.
    step_issue = by_arm["b1-step"]
    assert str(step_issue.reason) == "driver-factory-failed"
    assert "lineage_driver() got an unexpected keyword argument" in \
        step_issue.details["error"], step_issue.details

    # The typed AST arm reaches the world and is refused by it at turn
    # time, which is a different failure from the one the inventory names.
    ast_issue = by_arm["b1-ast"]
    assert str(ast_issue.reason) in {
        "world-action-refused", "episode-failed"}, str(ast_issue.reason)

    # The graph arm reaches a child, reaches the SWE world, and comes back
    # with a record. It used to be refused here as "stop target must be
    # boolean.task", because the bounded driver had no `swe` branch and sent
    # everything it had no executor for to the Boolean one. So the arm's
    # absence from `by_arm` is the assertion: a graph that runs produces a
    # record and no refusal, and a graph that is mis-loaded produces neither.
    records = {item.arm_name: item for item in result.records}
    assert "b1-graph" in records, (
        "the graph arm produced no record, so it never reached the world: %r"
        % sorted(records))
    graph_record = records["b1-graph"]
    assert graph_record.representation_kind == parity.ACTION_GRAPH
    assert graph_record.turns_taken >= 1, (
        "a record with no turns is an arm that was handed nothing")
    assert "b1-graph" not in by_arm, (
        "the graph arm is still refused, and the refusal is %r"
        % by_arm.get("b1-graph"))


def test_the_graph_cell_records_its_own_witness_on_the_lineage():
    """The unfillable cell stays recorded, and it names the executor.

    This is the property the acceptance rests on: a cell that cannot be
    supported carries a witness naming the input and the reason, so a
    later change to that refusal is a decision someone made.
    """
    lineage = next(item for item in swe_experiment.LINEAGES
                   if item.name == "action-graph-L0")

    assert lineage.built_ok, lineage.build_error
    witness = swe_ast.missing_cells()["action-graph"]["witness"]
    assert lineage.record["unfillable_cell"] == witness
    assert "boolean_graph_policy._parse_action" in witness, (
        "the witness must name the executor that still discards the read "
        "value. `ordering_graph_policy` binds and resolves, so naming it "
        "would describe a repair that already happened")
    assert "discarded" in witness, (
        "the witness must say the evaluator's read value is discarded by "
        "the executor this world actually runs")


def test_the_swe_action_vocabulary_admits_all_five_kinds_the_cell_uses():
    """The SWE world offers every kind the shared contract names.

    The inventory recorded the typed-AST validator refusal as the limit.
    That refusal named a Boolean-world validator this arm never calls; the
    SWE world itself admits `use/code.repair`, which the repair test above
    drives end to end. So the world binding is not the limit and this
    pins the vocabulary that says so.
    """
    task = _task()
    view = swe.SweSession(task).policy_view()

    assert set(view["action_schema"]["actions"]) == set(
        policy_action.ACTION_KINDS) - {policy_action.PROBE}, (
        "the SWE world names no `probe`, and every other shared kind is "
        "offered; a missing one here is a real refusal")
    assert set(parity.contract_view(view)["action_schema"]["actions"]) == \
        set(view["action_schema"]["actions"])


def test_support_names_all_three_representations_and_why_they_are_not_comparable():
    """The study's own support record, corrected and kept honest.

    It reported one supported representation and two missing, which described
    the cells' inability to repair rather than their ability to run. All
    three lineages build against their own real executors, so the record
    says three supported and zero missing, and carries a separate field for
    the thing that is actually false: `compare_arms` does not reach a
    comparable result, and the reasons are named rather than implied.
    """
    support = swe_experiment.support()

    assert support["supported_representations"] == [
        parity.PYTHON_STEP, parity.TYPED_AST, parity.ACTION_GRAPH]
    assert support["missing_representations"] == []
    assert support["comparable_through_compare_arms"] is False
    assert "step driver factory" in support["why_not_comparable"]
    assert "boolean stop target" in support["why_not_comparable"]
    assert "no swe branch" not in support["why_not_comparable"], (
        "the bounded driver names an executor per world and has a swe "
        "branch, so the dispatch is closed. A record still blaming it "
        "describes a mis-load tests/test_inv_b9_graph_driver.py replaced")
    assert "contract view" in support["why_not_comparable"], (
        "the surviving blocker is the projection the common harness hands "
        "the arm. The record has to name that one rather than the one a "
        "later lane closed, or a reader counts the wrong repair")
    assert "cannot import" not in support["why_not_comparable"], (
        "the record still blames an import failure that no longer happens")


def test_every_declared_lineage_builds_for_all_three_cells():
    """Four lineages per cell, and every one of them loads.

    The matrix records an unbuilt lineage as a refused row rather than
    dropping it, so a lineage that stopped building would show as a zero
    repair rate and be misread as a bad arm. This checks the build
    directly for all twelve.
    """
    lineages = swe_experiment.LINEAGES
    by_kind: dict[str, list] = {}
    for lineage in lineages:
        by_kind.setdefault(lineage.representation_kind, []).append(lineage)

    assert set(by_kind) == set(parity.REPRESENTATION_KINDS), (
        "a representation cell has no lineage at all")
    for kind, cell in sorted(by_kind.items()):
        assert len(cell) == swe_experiment.LINEAGES_PER_CELL, (
            "%s has %d lineages, not %d"
            % (kind, len(cell), swe_experiment.LINEAGES_PER_CELL))
        for lineage in cell:
            assert lineage.built_ok, (kind, lineage.build_error)
