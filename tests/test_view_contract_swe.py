"""The policy view contract is declared once, and every world is admitted.

`s09_arm_parity.admit_world_view` used to demand exactly eight public-state
fields and refuse the SWE world's twelve, so the three-representation SWE
comparison could not run under the common harness. Two further projections
of the same view had been written beside it, each answering the same
questions differently: `s09_swe_ast.swe_view` reported the probe budget as
`max_queries` and `{"structure": ...}` as `hypothesis_class`, while
`s09_e1_fork_probe.honest_projection` reported the sum of all five budgets
and a list of fault-mechanism names.

These tests pin the converged contract: one declaration per world, read by
the one guard, with the two superseded projections gone.
"""

from __future__ import annotations

import json

import pytest

from experiments.ad01 import boolean_active
from experiments.ad01 import boolean_rule
from experiments.ad01 import policy_action
from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_swe_tasks as tasks
from experiments.ad01 import s09_swe_world as swe


def _swe_view(observed: int = 0):
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    session = swe.SweSession(record)
    for case in record["public_tests"][:observed]:
        session.run_public_test(case["name"])
    return session.policy_view()


def _boolean_state():
    return boolean_active.public_state(
        boolean_rule.RuleSession(boolean_rule.make_task("dev", 4)))


# --- the one declaration --------------------------------------------------


def test_the_swe_world_is_admitted_and_normalised_to_the_six_contract_fields():
    """The blocker, measured end to end on a real SWE view.

    Before this the guard refused with `non-contract-action-kind` and
    `contract_view` raised. Now the same view is admitted and comes back
    carrying the program under repair, which is the thing an eight-field
    projection would have dropped.
    """
    view = _swe_view()

    assert parity.admit_world_view(view) is None
    contract = parity.contract_view(view)

    assert set(contract) == set(policy_action.view_contract()["fields"])
    assert contract["instrument"] == "software-fault-repair-v1"
    assert contract["task_id"] == "swe-held_out-count-tail-sum-1fdc31"
    assert contract["observed"] == []
    assert contract["action_schema"]["format"] == "s09-swe-action-v1"
    # the program is still here: 13 lines, and the arm can act on them
    assert contract["public_world"]["hypothesis_class"]["editable_lines"] == 13


def test_the_three_disputed_fields_carry_the_values_the_swe_world_computed():
    """One vocabulary, not a union and not a loose subset.

    `observed` is the test record already published under `symptom`.
    `max_queries` is the `test` budget, the one dimension an observation
    spends, and it is the same number the schema's own budget carries so
    the guard's budget cross-check is a real check rather than a formality.
    `hypothesis_class` names the program shape and the lines an edit may
    touch, both of which `apply_edits` already bounds.
    """
    contract = parity.contract_view(_swe_view(observed=1))

    assert contract["observed"] == [
        {"test": "case-01", "expected": 76, "actual": 121, "kind": "value"}]
    assert contract["public_world"]["max_queries"] == 2
    assert contract["action_schema"]["budget"]["max_queries"] == 2
    assert contract["public_world"]["hypothesis_class"] == {
        "structure": "counting", "editable_lines": 13}
    assert parity.admit_shared_view(contract) is None


def test_a_view_is_admitted_only_for_the_world_that_declared_it():
    """A union of two vocabularies is not a contract, and is refused.

    This is the safety property the per-world declaration has to keep.
    A loose subset check would let an arm widen its own view by sending
    the union, and the union carries every field both worlds expose.
    """
    union = {**_swe_view(), **_boolean_state()}

    issue = parity.admit_world_view(union, arm_name="union")

    assert issue is not None
    assert issue.reason == \
        parity.IncomparabilityReason.NON_CONTRACT_ACTION_KIND
    assert "max_budget" in issue.details["public_state_fields"]
    assert "hypothesis_class" in issue.details["public_state_fields"]


def test_a_world_the_harness_does_not_know_is_refused_rather_than_guessed():
    """Both of a world's declarations have to be its own and to agree.

    Matching on either one alone is a hole: naming a declared format under
    an undeclared instrument would be admitted by the format and then
    projected with the wrong world's read paths. An undeclared world is
    refused the way `_WORLDS` already refuses an unrecognised world name,
    and a view that dropped one declared field is refused for the
    different reason that the set is exact rather than a subset.
    """
    mismatched = _swe_view()
    mismatched["action_schema"]["format"] = "s09-boolean-action-v1"

    issue = parity.admit_world_view(mismatched, arm_name="mismatched")
    assert issue is not None
    assert issue.details["public_state_fields"] == "unrecognised world"

    unknown = {**_swe_view(), "instrument": "no-such-instrument-v1"}
    assert parity.admit_world_view(unknown).details["public_state_fields"] == \
        "unrecognised world"

    short = {key: value for key, value in _swe_view().items()
             if key != "source"}
    issue = parity.admit_world_view(short)
    assert issue is not None
    assert issue.details["public_state_fields"] == sorted(short)


def test_the_boolean_view_is_unchanged_by_the_convergence():
    """The two worlds that already agreed must still agree, unchanged.

    A per-world contract that broke the legacy projection would trade one
    incomparable comparison for a different one.
    """
    state = _boolean_state()

    assert parity.admit_world_view(state) is None
    contract = parity.contract_view(state)
    assert set(contract) == set(policy_action.view_contract()["fields"])
    assert contract["public_world"]["max_queries"] == 8
    assert contract["action_schema"]["budget"]["max_queries"] == 8
    assert parity.admit_shared_view(contract) is None


def test_the_declared_contract_is_a_value_rather_than_a_restated_constant():
    """One source of truth, read by the guard and by the two projections.

    The field sets and the read paths live in the module that owns the
    guard. A test that compared the guard against a tuple it wrote itself
    would pass with the guard deleted, so this one asks the guard where
    its declaration came from and drives a field through a read path.
    """
    assert parity.VIEW_CONTRACT_FIELDS["software-fault-repair-v1"] == \
        frozenset(_swe_view())
    reads = parity.VIEW_CONTRACT_READS["software-fault-repair-v1"]
    assert reads["observed"] == ("symptom", "observed")
    assert reads["max_queries"] == ("action_schema", "budget", "test")
    assert reads["remaining"] == ("remaining", "test")

    # the read path is exercised, not restated: a world that moved the
    # observations would be read from the new place or refused, never
    # silently from the old one
    moved = _swe_view(observed=1)
    moved["symptom"]["transcript"] = moved["symptom"].pop("observed")
    with pytest.raises(KeyError):
        parity.contract_view(moved)


# --- contamination --------------------------------------------------------


def test_the_converged_contract_still_refuses_each_thing_it_used_to():
    """One runnable place to check the whole safety surface.

    Loosening a guard is only safe if the refusals survive the loosening,
    so they are enumerated together rather than left across four tests to
    be reconstructed. Each is a refusal the pre-existing guard made and
    this change must keep making.
    """
    view = _swe_view()
    boolean = _boolean_state()
    dropped = {k: v for k, v in view.items() if k != "source"}

    assert parity.admit_world_view(view) is None
    assert parity.admit_world_view({**view, "tables": {}}) is not None
    assert parity.admit_world_view(dropped) is not None
    assert parity.admit_world_view({**view, "instrument": "x"}) is not None
    assert parity.admit_world_view(
        {**view, "instrument": "boolean-rule-v1"}) is not None
    assert parity.admit_shared_view(parity.contract_view(view)) is None
    assert parity.admit_world_view(boolean) is None
    assert parity.admit_shared_view(parity.contract_view(boolean)) is None

    contract = json.dumps(parity.contract_view(view), default=str)
    assert not [mechanism for mechanism in tasks.MECHANISMS
                if mechanism in contract]


def test_two_arms_on_the_swe_world_now_compare_under_the_common_harness():
    """What W1 was blocked on, driven end to end through `compare_arms`.

    The blocker was a refusal, so the thing worth pinning is not the
    projection but a real two-arm comparison on the SWE world. Both arms
    must receive byte-identical views and a run that terminates without a
    single view refusal. The only reason `status` is still
    `incomparable` here is `insufficient-arms`, which is this test's own
    doing: both drivers are registered as doubles, and the harness
    refuses to call a pair of doubles a representation comparison. That
    is the harness refusing to over-claim, and it is the correct answer.
    """
    from experiments.ad01 import s09_swe_world as world_module

    def driver(_record, **_limits):
        return lambda _view: world_module.stop_action()

    registry = parity.ArmRegistry()
    for name, kind in (("swe-step", parity.PYTHON_STEP),
                       ("swe-graph", parity.ACTION_GRAPH)):
        registry.register(name=name, representation_kind=kind,
                          driver_factory=driver,
                          policy_record={"probe": name}, is_test_double=True)
    conditions = parity.ComparisonConditions(
        split="held_out", seed=0, max_queries=swe.BUDGET_LIMITS["test"],
        step_budget=parity.StepBudget(), world="swe")

    result = parity.compare_arms(registry, ("swe-step", "swe-graph"),
                                 conditions)

    assert [record.arm_name for record in result.records] == [
        "swe-step", "swe-graph"]
    assert {record.view_digest for record in result.records} \
        == {result.records[0].view_digest}
    assert [record.split for record in result.records] \
        == ["held_out", "held_out"]
    assert [record.seed for record in result.records] == [0, 0]
    assert [record.query_budget for record in result.records] == [2, 2]
    assert [record.turns_taken for record in result.records] == [1, 1]
    assert not [issue for issue in result.incompatibilities
                if issue.reason != parity.IncomparabilityReason
                .INSUFFICIENT_ARMS], result.incompatibilities


def test_the_swe_contract_view_carries_no_fault_label_or_protected_answer():
    """The contamination boundary, restated at the new boundary.

    `s09swe_contamination` pins the world's own view. The contract is a
    second projection of it, so the same properties are pinned on the
    projection the arms actually receive.
    """
    contract = parity.contract_view(_swe_view(observed=1))
    blob = json.dumps(contract, sort_keys=True, default=str)

    for mechanism in tasks.MECHANISMS:
        assert mechanism not in blob, mechanism
    for key in tasks.FAULT_LABEL_KEYS:
        assert key not in contract, key
    assert "tables" not in contract
    assert "mechanism" not in contract["public_world"]["hypothesis_class"]
    # the public tests are the panel's own, and they stay visible
    assert contract["observed"][0]["test"] == "case-01"
