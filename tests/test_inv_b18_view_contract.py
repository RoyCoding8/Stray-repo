"""The contract view has to carry what a policy guard reads.

B9 closed the dispatch and left the view named as the surviving blocker.
The name was right and the diagnosis under it was wrong, so this file
corrects the diagnosis by measurement and pins the repair.

**The contract view already publishes the field the guard reads.** The
brief said it did not, and the reason it seemed not to is one layer down:
`contract_view` carries `observed` as the same list the world published at
`symptom.observed`, and `s09_swe_binding.project_swe_view` then *overwrites*
it. That projection was written for the raw world view and reads
`public_state["symptom"]["observed"]`; handed a parity state it finds no
`symptom`, its `.get` default is `[]`, and it replaces a populated
`observed` with `{}`. The guard on `observed.0.kind` then resolves `{}["0"]`,
raises, and the executor's own catch answers with its refusal action.

So the guard's field is `observed.0.kind`, the contract publishes it, and the
projection emptied it. That makes the repair the guard already reading a
field the contract already publishes, and it is one function that reads a
key the caller did not send.

This is not the same defect as the one B9 recorded. There, the raw policy
view produced `construct/code.inspect` and the contract view produced
`stop/swe.task`; that disagreement is real and is asserted below as the
witness for the repair rather than repeated as a conclusion. What was
missing was the reading of it.

Offline lane. No live model call, no network, no fixture gateway. The
children driven here are real `LocalLauncher` dispatches on this host.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import ordering_graph_policy
from experiments.ad01 import policy_action
from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_swe_binding as swe_binding
from experiments.ad01 import s09_swe_experiment as swe_experiment
from experiments.ad01 import s09_swe_tasks as swe_tasks
from experiments.ad01 import s09_swe_world as swe_world


# The field `swe_graph_record`'s first guard reads, and the literal the world
# publishes there. Spelled out rather than imported so a change to the
# record's guard cannot leave this asserting the old field's value.
GUARD_FIELD = "observed.0.kind"
GUARD_LITERAL = "value"


def _policy_view(observed_kind: str = GUARD_LITERAL) -> dict:
    """A real SWE policy view, one public test already run.

    `observed_kind` rewrites the one field under guard, so two calls differ
    in nothing else. It is the disagreement the repair is measured by, so it
    touches that field and nothing else.
    """
    instance = swe_tasks.instance("held_out", swe_tasks.HELD_OUT_TEMPLATES[0],
                                  swe_tasks.HELD_OUT_MECHANISMS[0])
    session = swe_world.SweSession(instance)
    session.run_public_test(instance["public_tests"][0]["name"])
    view = session.policy_view()
    if observed_kind != view["symptom"]["observed"][0]["kind"]:
        view["symptom"]["observed"][0] = dict(
            view["symptom"]["observed"][0], kind=observed_kind)
    return view


# --- 1. the contract carries what the guard reads -----------------------


def test_the_field_the_guard_reads_is_carried_by_the_contract_view():
    """The literal, and the exact-field admission that guards the check.

    The six contract fields and `admit_shared_view`'s equality against
    `policy_action.view_contract()["fields"]` are what make this an
    assertion about the contract rather than about one dict. Adding a key
    to the projection without declaring it here would be refused.
    """
    view = _policy_view()
    contract = parity.contract_view(view)

    assert set(contract) == set(policy_action.view_contract()["fields"]) == {
        "instrument", "task_id", "observed", "remaining", "public_world",
        "action_schema"}
    assert contract["observed"] == [
        {"test": "case-01", "expected": 76, "actual": 121,
         "kind": GUARD_LITERAL}]
    assert parity.admit_shared_view(contract) is None

    # The guarded field is the contract's `observed`, not the world's
    # `symptom`. Asserted as the path the evaluator walks, so a reader sees
    # the repair is a change of read, not a widened contract.
    assert "symptom" not in contract
    assert contract["observed"][0]["kind"] == GUARD_LITERAL


def test_the_projection_no_longer_empties_a_field_the_contract_published():
    """The defect itself, on the projection that carried it.

    Handed a parity state, `project_swe_view` used to read `symptom`,
    find nothing, and write `{}` over a populated `observed`. So the guard
    raised rather than being decided. The raw path is driven too, so the
    repair cannot be a change that only serves the parity caller.
    """
    raw = _policy_view()
    from_raw = swe_binding.project_swe_view(raw)

    assert from_raw["observed"] == {
        "0": {"test": "case-01", "expected": 76, "actual": 121,
              "kind": GUARD_LITERAL}}, (
        "the raw world view still projects: the SWE world nests its "
        "observations under symptom and that path must keep working")

    from_contract = swe_binding.project_swe_view(
        parity._ordering_state_from_view(parity.contract_view(raw)))

    assert from_contract["observed"] == from_raw["observed"], (
        "the parity state publishes the same observations flat, so the "
        "projection has to re-index those rather than the empty default")


# --- 2. the guard no longer takes its always arm ------------------------


def test_two_contract_views_differing_only_in_the_guarded_field_disagree():
    """Disagreement, on the real record, through the real harness seam.

    This is the assertion that fails against the defect. Both inputs are
    contract views of a real SWE turn and differ in one field; under the
    projection that emptied it, both resolved `{}["0"]`, both raised, and
    both came back as the same refusal. Asserted as literals, so a
    regression to a *different* constant cannot pass as a disagreement.

    The seam driven is `_action_graph_factory`'s own `decide`, which is what
    `_run_arm` calls per turn, so the projection runs inside the child
    exactly once as it does in a comparison. Projecting here instead would
    have run it twice and measured a shape no arm is given.
    """
    record = swe_binding.swe_graph_record("b18-view-contract")
    policy = ordering_graph_policy.load_policy(
        record, world=swe_binding.SWE_WORLD)
    arm = policy.nodes[policy.start].arms[0]

    def projected(observed_kind: str) -> dict:
        return swe_binding.project_swe_view(
            parity.contract_view(_policy_view(observed_kind)))

    # The guard is decided, which is the property this lane repairs. Under
    # the defect it raised on `{}["0"]` for both and neither arm was ever
    # chosen, so neither of these booleans existed.
    assert arm.guard == {"field": GUARD_FIELD, "op": "ne", "value": ""}
    assert ordering_graph_policy._evaluate_guard(
        arm.guard, projected(GUARD_LITERAL), {}, swe_binding.SWE_WORLD) is True
    assert ordering_graph_policy._evaluate_guard(
        arm.guard, projected(""), {}, swe_binding.SWE_WORLD) is False
    assert ordering_graph_policy._field_value(
        projected(GUARD_LITERAL), {}, GUARD_FIELD,
        swe_binding.SWE_WORLD) == GUARD_LITERAL
    assert ordering_graph_policy._field_value(
        projected(""), {}, GUARD_FIELD, swe_binding.SWE_WORLD) == ""

    # And the two differ through the real bounded child.
    def decide_for(observed_kind: str) -> dict:
        return parity._action_graph_factory(
            record, world="swe")(
                parity.contract_view(_policy_view(observed_kind)))

    reached = decide_for(GUARD_LITERAL)
    declined = decide_for("")

    assert reached != declined, (
        "one action for both views means the guard was not read")
    assert declined == {
        "kind": policy_action.STOP,
        "target": "swe.task",
        "inputs": {},
        "evidence_refs": [],
        "requested_resources": {}}, declined
    assert reached["target"] == swe_binding.SWE_WORLD.stop_target
    # What the reached arm reaches is NOT this lane's defect. `'0'` is the
    # projection emptying the observations; the world refusing the chosen
    # construct over the budget's shape is the separate defect asserted
    # below. A regression to the projection bug would say `'0'` here.
    assert reached["inputs"]["bridge_refusal"]["reason"] != "'0'", reached
    assert swe_binding.SWE_WORLD.field_type(GUARD_FIELD) == "string"


def test_the_graph_cell_reaches_a_guarded_turn_through_the_common_contract():
    """The path the matrix cell needs, end to end, through the harness.

    `compare_arms` is what the cell is measured by, so the guard is
    resolved through `contract_view` rather than beside it: the state
    `_ordering_state_from_view` builds is the one the executor projects.
    Asserted on the projected view the evaluator is handed, not on a
    re-derived copy.
    """
    contract = parity.contract_view(_policy_view())
    state = parity._ordering_state_from_view(contract)
    projected = swe_binding.project_swe_view(state)
    policy = ordering_graph_policy.load_policy(
        swe_binding.swe_graph_record("b18-in-harness"),
        world=swe_binding.SWE_WORLD)
    arm = policy.nodes[policy.start].arms[0]

    assert arm.guard == {"field": GUARD_FIELD, "op": "ne", "value": ""}
    assert arm.guard["field"] == "observed.0.kind", (
        "the record guards a field the contract has to publish; a different "
        "field means this lane measured the wrong one")
    assert ordering_graph_policy._evaluate_guard(
        arm.guard, projected, {}, swe_binding.SWE_WORLD) is True
    assert ordering_graph_policy._field_value(
        projected, {}, GUARD_FIELD, swe_binding.SWE_WORLD) == GUARD_LITERAL


# --- 3. the recorded blocker names what still holds the cell ------------


def test_the_support_record_names_the_surviving_blocker_not_the_closed_one():
    """The record must not keep blaming a repair that happened.

    `support()` read that the contract view "carries no symptom key for the
    swe binding's projection to re-publish". The symptom key was never the
    problem and the projection now reads what it is handed, so that
    sentence describes a defect this file closed. The record still carries
    the world as incomparable, and the reason it names is asserted.
    """
    support = swe_experiment.support()

    assert support["comparable_through_compare_arms"] is False
    assert "carries no symptom key" not in support["why_not_comparable"], (
        "the record still blames the contract view for not carrying symptom, "
        "which was never the problem and is what this lane corrected")
    assert "decided against an empty table" not in \
        support["why_not_comparable"], (
        "the guard is decided against the observations the contract "
        "publishes; a record still calling that an empty table describes the "
        "defect this file closed")
    assert "the budget's shape" in support["why_not_comparable"], (
        "the step driver factory, the typed AST's stop target and the "
        "budget's shape are what survive; the record has to name the last "
        "one rather than the observation view this lane closed")
    assert "has no attribute 'get'" in support["why_not_comparable"], (
        "the surviving refusal is measured, so the record carries its text "
        "rather than a sentence about a projection that is repaired")
    # The graph cell itself is closed, so the record may not name it among
    # the blockers. Asserted both ways: absent here, present as supported.
    assert parity.ACTION_GRAPH in support["supported_representations"]
    assert support["missing_representations"] == []


def test_the_contract_view_carries_the_swe_observation_without_a_symptom_key():
    """The declared world contract is unchanged by this repair.

    `admit_world_view` compares the world's own twelve published fields
    against `VIEW_CONTRACT_FIELDS` for exact equality, so a world that grew
    a thirteenth field would be refused here. The repair is in the
    projection, not in what the world publishes, and this is what keeps it
    from becoming a world that publishes the harness's shape.
    """
    declared = parity.VIEW_CONTRACT_FIELDS[swe_world.INSTRUMENT_ID]

    assert declared == frozenset({
        "action_schema", "entry", "instrument", "last_effect", "max_budget",
        "public_tests", "remaining", "source", "split", "structure",
        "symptom", "task_id"})
    assert "symptom" in declared and "observed" not in declared, (
        "the world still nests its observations; the contract reads them "
        "through the declared path rather than the world publishing flat")
    assert parity.admit_world_view(_policy_view()) is None


# --- 4. the blocker that survives the projection repair -----------------


def test_the_guarded_turn_the_record_reaches_is_still_refused_on_the_budgets_shape():
    """What still holds the graph cell, named and measured.

    The guard is decided now, and the arm it reaches is refused for a
    reason one layer below the view. `contract_view` publishes `remaining`
    as the scalar `admit_shared_view` requires, by a declared read of
    `("remaining", "test")`. The SWE world publishes it as a per-dimension
    mapping and `admits` calls `.get` on it, so the contract's scalar is
    the shape the world's own admission cannot read.

    This is a different defect from the projection's and it is not this
    lane's to repair: the scalar is required by
    `admit_shared_view`'s `0 <= remaining <= max_queries` check, and
    republishing a mapping there would be widening the contract rather
    than reading one. The per-dimension map is also not recoverable from
    what the contract does carry, because `action_schema.budget` holds the
    ceiling and the live count is lower once a test has been run.

    So the honest disposition is that the cell stays unsupported, on the
    budget's shape rather than on the observations. Asserted rather than
    written down, so the record cannot drift back to the closed reason.
    """
    contract = parity.contract_view(_policy_view())
    raw = _policy_view()
    construct = {
        "kind": policy_action.CONSTRUCT, "target": "code.inspect",
        "inputs": {"line": 1}, "evidence_refs": [],
        "requested_resources": {}}

    assert contract["remaining"] == 1 and type(contract["remaining"]) is int, (
        "the contract publishes the declared scalar; a mapping here would be "
        "a contract the exact check admits only by being weakened")
    assert raw["remaining"] == {"edit": 1, "inspect": 4, "localize": 2,
                                "probe": 303, "test": 1}, (
        "the world publishes the per-dimension map its admission reads")
    # The ceiling the contract does carry, and why it cannot stand in.
    assert contract["action_schema"]["budget"]["test"] == 2
    assert raw["action_schema"]["budget"]["test"] == 2
    assert raw["remaining"]["test"] == 1, (
        "the schema holds the ceiling and the live count is already spent, "
        "so a projection cannot rebuild the map from what the contract "
        "carries")
    assert swe_world.admits(None, raw, construct) is True
    with pytest.raises(AttributeError):
        swe_world.admits(None, contract, construct)