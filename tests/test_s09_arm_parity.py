from __future__ import annotations

import hashlib
import json

import pytest

from experiments.ad01 import boolean_active
from experiments.ad01 import boolean_rule
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step
from experiments.ad01 import s09_arm_parity as parity


def _state():
    return boolean_active.public_state(boolean_rule.RuleSession(
        boolean_rule.make_task("dev", 4)))


def _stop():
    return {
        "kind": "stop",
        "target": "boolean.task",
        "inputs": {},
        "evidence_refs": [],
        "requested_resources": {},
    }


def _factory(kind="stop", *, mutate_view=False):
    def build(_record, **_limits):
        def decide(view):
            if mutate_view:
                view["public_world"]["max_queries"] += 1
            return {
                "kind": kind,
                "target": "boolean.task",
                "inputs": {},
                "evidence_refs": [],
                "requested_resources": {},
            }
        return decide
    return build


def _conditions():
    return parity.ComparisonConditions(
        split="dev", seed=4, max_queries=boolean_rule.MAX_QUERIES)


def _register_double(registry, name, kind, representation_kind, **kwargs):
    return registry.register(
        name=name,
        representation_kind=representation_kind,
        driver_factory=_factory(kind, **kwargs),
        policy_record={"representation": name},
        is_test_double=True,
    )


def test_raw_boolean_schema_is_admitted_only_by_the_documented_rename():
    raw = _state()

    assert parity.admit_world_view(raw) is None
    admitted = parity.contract_view(raw)

    assert set(raw["action_schema"]["actions"]) == {
        "probe", "commit", "stop"}
    assert set(admitted["action_schema"]["actions"]) == {
        "probe", "construct", "stop"}
    assert "commit" not in admitted["action_schema"]["actions"]
    assert admitted["action_schema"]["budget"]["max_queries"] == 8


def test_the_old_hardcoded_construct_policy_shape_is_caught_on_the_raw_schema():
    hardcoded_action = {
        "kind": policy_action.CONSTRUCT,
        "target": "boolean.commit",
        "inputs": {"specs": []},
        "evidence_refs": [],
        "requested_resources": {},
    }
    assert policy_action.parse_action(hardcoded_action).kind == "construct"

    issue = parity.admit_world_view(
        {**_state(), "action_schema": {
            **_state()["action_schema"],
            "actions": {
                **_state()["action_schema"]["actions"], "finalize": {},
            },
        }},
        arm_name="old-test",
    )

    assert issue.reason == "non-contract-action-kind"
    assert issue.details["action_kind"] == "finalize"
    assert issue.details["documented_renames"] == {"commit": "construct"}


def test_a_renamed_view_accepts_construct_and_rejects_commit_or_teleport():
    view = parity.contract_view(_state())

    construct = {
        "kind": "construct", "target": "boolean.commit", "inputs": {},
        "evidence_refs": [], "requested_resources": {},
    }
    commit = {**construct, "kind": "commit"}
    teleport = {**construct, "kind": "teleport"}

    assert parity.admit_action(view, construct) is None
    assert parity.admit_action(view, commit).reason == "private-action-kind"
    assert parity.admit_action(view, teleport).reason == "private-action-kind"


def test_non_contract_kind_and_budget_disagreement_are_machine_readable():
    state = _state()
    state["action_schema"]["actions"]["teleport"] = {}
    state["action_schema"]["budget"]["max_queries"] = 7
    issue = parity.admit_world_view(state, arm_name="bad-schema")

    assert issue.reason == "budget-mismatch"
    assert issue.arm_names == ("bad-schema",)
    assert issue.details == {
        "view_max_queries": 8,
        "schema_max_queries": 7,
    }

    state["action_schema"]["budget"]["max_queries"] = 8
    state["action_schema"]["actions"].pop("commit")
    state["action_schema"]["actions"]["teleport"] = {}
    issue = parity.admit_world_view(state, arm_name="bad-schema")
    assert issue.reason == "non-contract-action-kind"
    assert issue.details["action_kind"] == "teleport"


def test_missing_unknown_and_duplicate_registrations_are_refused_as_outcomes():
    registry = parity.ArmRegistry()
    missing = registry.register(
        name="missing", representation_kind=None,
        driver_factory=_factory(), policy_record={})
    unknown = registry.register(
        name="unknown", representation_kind="prompt-tree",
        driver_factory=_factory(), policy_record={})
    assert missing.reason == "undeclared-representation-kind"
    assert unknown.reason == "unknown-representation-kind"
    assert registry.names == ()

    _register_double(registry, "test-double:ast", "stop", parity.TYPED_AST)
    duplicate = registry.register(
        name="test-double:ast", representation_kind=parity.ACTION_GRAPH,
        driver_factory=_factory(), policy_record={})
    assert duplicate.reason == "duplicate-arm-name"
    assert registry.names == ("test-double:ast",)

    result = parity.compare_arms(
        registry, ("test-double:ast", "missing"), _conditions())
    assert result.status == "incomparable"
    assert result.incompatibilities[0].reason == "unregistered-arm"
    assert result.incompatibilities[0].arm_names == ("missing",)


def test_two_doubles_receive_byte_identical_views_and_record_world_scoring():
    registry = parity.ArmRegistry()
    _register_double(registry, "test-double:step", "stop", parity.PYTHON_STEP)
    _register_double(registry, "test-double:ast", "stop", parity.TYPED_AST)

    result = parity.compare_arms(
        registry,
        ("test-double:step", "test-double:ast"),
        _conditions(),
    )

    assert result.status == "incomparable"
    assert [issue.reason for issue in result.incompatibilities] == [
        "insufficient-arms"]
    first, second = result.records
    expected = hashlib.sha256(parity.serialize_view(
        parity.contract_view(_state()))).hexdigest()
    assert first.view_digest == second.view_digest == expected
    assert first.initial_state_digest == second.initial_state_digest
    assert first.query_budget == second.query_budget == 8
    assert first.queries_spent == second.queries_spent == 0
    assert first.turns_taken == second.turns_taken == 1
    assert first.score == second.score is None
    assert first.split == second.split == "dev"
    assert first.seed == second.seed == 4
    assert first.step_budget == second.step_budget == parity.StepBudget()


def test_registration_marks_test_doubles_and_keeps_the_real_step_arm_visible():
    """A registered double stays a double even once three kinds are real."""
    registry = parity.ArmRegistry()
    _register_double(registry, "test-double:ast", "stop", parity.TYPED_AST)
    real = parity.register_python_step(
        registry, name="real-python-step", policy_record={"source": "unused"})

    assert isinstance(real, parity.ArmRegistration)
    assert real.representation_kind == parity.PYTHON_STEP
    assert real.is_test_double is False
    assert registry.real_arm_names() == ("real-python-step",)
    assert parity.REAL_REPRESENTATION_KINDS == frozenset({
        parity.PYTHON_STEP, parity.TYPED_AST, parity.ACTION_GRAPH})


def test_all_three_representations_register_a_real_arm():
    """CS-03, closed: the comparison is no longer one executor.

    Each kind has a registration helper and a driver factory behind the one
    shared contract view, and none of them is a labelled double.
    """
    registry = parity.ArmRegistry()

    for name, kind, register in (
            ("real-step", parity.PYTHON_STEP, parity.register_python_step),
            ("real-ast", parity.TYPED_AST, parity.register_typed_ast),
            ("real-graph", parity.ACTION_GRAPH, parity.register_action_graph)):
        arm = register(registry, name=name,
                       policy_record={"source": "unused"})
        assert isinstance(arm, parity.ArmRegistration), name
        assert arm.representation_kind is kind
        assert arm.is_test_double is False

    assert registry.real_arm_names() == ("real-step", "real-ast", "real-graph")


def test_the_real_python_step_and_test_double_run_and_are_scored_by_the_world():
    source = '''def STEP(view, state):
    return {"action": {
        "kind": "stop", "target": "boolean.task", "inputs": {},
        "evidence_refs": [], "requested_resources": {}},
        "state": {}}
'''
    record = policy_step.make_policy_artifact(
        source, origin="authored-control", instruments=["boolean-rule-v1"])
    registry = parity.ArmRegistry()
    real = parity.register_python_step(
        registry, name="real-python-step", policy_record=record)
    assert isinstance(real, parity.ArmRegistration)
    _register_double(registry, "test-double:ast", "stop", parity.TYPED_AST)

    result = parity.compare_arms(
        registry, ("real-python-step", "test-double:ast"), _conditions())

    assert result.status == "comparable"
    assert [record.is_test_double for record in result.records] == [False, True]
    assert result.records[0].view_digest == result.records[1].view_digest
    assert result.records[0].queries_spent == 0
    assert result.records[0].score is None
    assert result.records[0].turns_taken == 1


def test_an_arm_emitting_a_private_action_kind_is_reported_not_normalized():
    registry = parity.ArmRegistry()
    _register_double(
        registry, "test-double:ast", "teleport", parity.TYPED_AST)
    _register_double(registry, "test-double:graph", "stop", parity.ACTION_GRAPH)

    result = parity.compare_arms(
        registry,
        ("test-double:ast", "test-double:graph"),
        _conditions(),
    )

    assert result.status == "incomparable"
    assert [issue.reason for issue in result.incompatibilities] == [
        "private-action-kind", "insufficient-arms"]
    issue = result.incompatibilities[0]
    assert issue.arm_names == ("test-double:ast",)
    assert issue.details == {"action_kind": "'teleport'"}


def test_view_mutation_does_not_rescue_a_mismatched_arm():
    registry = parity.ArmRegistry()
    _register_double(
        registry, "test-double:ast", "stop", parity.TYPED_AST,
        mutate_view=True)
    _register_double(registry, "test-double:graph", "stop", parity.ACTION_GRAPH)

    result = parity.compare_arms(
        registry,
        ("test-double:ast", "test-double:graph"),
        _conditions(),
    )

    assert result.status == "incomparable"
    assert [issue.reason for issue in result.incompatibilities] == [
        "view-mutated", "insufficient-arms"]
    assert result.incompatibilities[0].arm_names == ("test-double:ast",)


def test_a_view_mutation_and_raw_schema_rewrite_within_one_arm_are_both_reported():
    registry = parity.ArmRegistry()
    _register_double(
        registry, "test-double:ast", "stop", parity.TYPED_AST,
        mutate_view=True)
    _register_double(registry, "test-double:graph", "stop", parity.ACTION_GRAPH)

    result = parity.compare_arms(
        registry,
        ("test-double:ast", "test-double:graph"),
        _conditions(),
    )

    assert [issue.reason for issue in result.incompatibilities] == [
        "view-mutated", "insufficient-arms"]
    assert result.as_dict()["status"] == "incomparable"


def test_real_step_registration_requires_the_real_policy_record_boundary():
    registry = parity.ArmRegistry()
    outcome = parity.register_python_step(
        registry, name="real-python-step", policy_record={"source": "unused"})

    assert isinstance(outcome, parity.ArmRegistration)
    result = parity.compare_arms(
        registry, ("real-python-step", "missing"), _conditions())
    assert result.incompatibilities[0].reason == "unregistered-arm"
