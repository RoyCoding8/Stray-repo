from __future__ import annotations

import pytest

from experiments.ad01 import policy_action as contract


def test_the_contract_is_one_vocabulary_not_six():
    assert contract.ACTION_KINDS == (
        "probe", "observe", "construct", "use", "check", "stop")


def test_a_well_formed_action_parses():
    action = contract.parse_action({
        "kind": "probe", "target": "boolean.query",
        "inputs": {"x": 3}, "evidence_refs": [],
        "requested_resources": {"queries": 1}})

    assert action.kind == "probe"
    assert action.inputs == {"x": 3}
    assert action.requested_resources == {"queries": 1}


def test_round_trips_through_its_dict_form():
    original = contract.parse_action({
        "kind": "construct", "target": "method",
        "inputs": {"source": "x"}, "evidence_refs": ["obs-1"]})

    assert contract.parse_action(original.as_dict()) == original


@pytest.mark.parametrize("payload, fragment", [
    ({}, "action kind must be a string"),
    (None, "must be an object"),
    ({"kind": "teleport"}, "unknown action kind"),
    ({"kind": 7}, "must be a string"),
    ({"kind": "probe", "unknown": 1}, "unknown action fields"),
    ({"kind": "probe", "target": "t", "inputs": []}, "must be an object"),
    ({"kind": "probe", "target": "t", "evidence_refs": "obs-1"}, "must be a list"),
    ({"kind": "probe", "target": "t", "evidence_refs": [3]}, "must be a string"),
])
def test_malformed_actions_fail_explicitly(payload, fragment):
    with pytest.raises(contract.ActionRefused, match=fragment):
        contract.parse_action(payload)


def test_the_existing_vocabularies_do_not_fully_cover_the_contract_yet():
    """Naming the gap is the point: an adapter must still be written for each.

    The contract is deliberately minimal. Anything an existing vocabulary
    expresses but the contract does not name is migration work, not a
    reason to widen the contract before the arms exist.
    """
    from experiments.ad01 import frontier, improve_channel, policy_step

    step = set(policy_step.ACTION_KINDS)
    operate = set(frontier.OPERATE_KINDS)
    improve = set(improve_channel.IMPROVE_KINDS)
    shared = set(contract.ACTION_KINDS)

    assert "stop" in step & shared
    assert step - shared == {"construct_method", "diagnose",
                             "propose_revision", "request_model",
                             "use_method"}
    assert operate - shared == {"investigate", "reuse", "revise", "wait"}
    assert improve - shared == {"select", "wait"}
    assert "construct" in operate & improve & shared
    assert "probe" in improve & shared


def test_the_view_contract_names_what_is_withheld():
    declared = contract.view_contract()

    assert "excluded" in declared
    assert "public_task_view" in declared["excluded"]


def test_every_vocabulary_in_the_repository_is_recorded_as_unmerged():
    """A future arm must not assume the six vocabularies already agree."""
    from src.settlement import loop, representation

    legacy = {"diagnostic", "development", "use_method", "stop"}
    instruments = {loop.DIAGNOSTIC, loop.CONSTRUCTION, loop.REPAIR,
                   loop.USE, loop.PROBE, loop.STOP}
    stages = set(representation.ACTIONS)
    shared = set(contract.ACTION_KINDS)

    assert legacy - shared, "legacy learner actions remain unmerged"
    assert stages - shared, "representation stages remain unmerged"
    assert instruments & shared


def test_policy_state_is_not_the_frontier_campaign_state():
    """The two must never share a name or the arms will not be comparable."""
    declared = contract.state_contract()

    assert declared["step_state_key"] == "state"
    assert declared["campaign_private_state_key"] == "private_state"
    assert declared["distinct"] is True


def test_step_result_returns_action_and_policy_state():
    action, state = contract.parse_step_result({
        "action": {"kind": "probe", "target": "boolean.query",
                   "inputs": {"x": 1}},
        "state": {"asked": [1]}})

    assert action.kind == "probe"
    assert state == {"asked": [1]}


@pytest.mark.parametrize("payload, fragment", [
    ({"action": {"kind": "probe"}}, "must carry action and state"),
    ({"action": {"kind": "probe", "target": "t"}, "state": {}, "extra": 1},
     "unknown step result fields"),
    ({"action": {"kind": "probe", "target": "t"}, "state": []}, "must be an object"),
    ("nope", "must be an object"),
])
def test_malformed_step_results_fail_explicitly(payload, fragment):
    with pytest.raises(contract.ActionRefused, match=fragment):
        contract.parse_step_result(payload)


def test_a_step_policy_using_the_frontier_name_would_be_rejected():
    """A representation cannot smuggle campaign state through the contract."""
    with pytest.raises(contract.ActionRefused, match="unknown step result fields"):
        contract.parse_step_result({
            "action": {"kind": "probe", "target": "t"}, "private_state": {"seen": 2}})


def test_the_step_abi_agrees_with_the_contract_on_the_state_key():
    from experiments.ad01 import policy_step

    accepted = policy_step.validate_step_result({
        "action": {"kind": "stop", "target": "campaign", "inputs": {},
                   "evidence_refs": [], "requested_resources": {}},
        "state": {}})

    assert "state" in accepted
