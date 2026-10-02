from __future__ import annotations

import pytest

from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel


def _store(tmp_path):
    store = frontier.create_store(
        tmp_path / "frontier.json", namespace=frontier.NAMESPACE,
        mission={"objective": "atomic frontier",
                 "environments": [{"instrument": "boolean-rule-v1",
                                   "split": "dev", "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    store.bind_active(channel.make_control("low"))
    store.propose({
        "opportunity_id": "opp-probe",
        "mission_link": "atomic frontier",
        "question": "observe input 3",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}})
    return store


def _observation(effect):
    return {
        "observation_id": "obs-probe",
        "task": "opp-probe",
        "verdict": "observed",
        "x": 3,
        "y": [1, 0, 0, 1],
        "effect_id": effect["effect_id"],
        **effect["expected_identity"],
    }


def test_admission_charge_and_completion_replay_converge(tmp_path):
    store = _store(tmp_path)
    package = store.active_digest
    first = store.admit_and_spend(
        "opp-probe", package, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-probe"})
    second = store.admit_and_spend(
        "opp-probe", package, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-probe"})
    observation = _observation(first)

    assert second == first
    assert store.authority["queries_used"] == 1
    assert store.authority["steps_used"] == 1
    assert len(store.pending_effects) == 1

    store.complete_effect(
        first["effect_id"], observation,
        action_key={"instrument": "boolean-rule-v1", "inputs": {"x": 3},
                    "environment": store.environment_digest},
        outcome={"y": observation["y"]})
    restarted = frontier.FrontierStore(str(store.path))
    restarted.complete_effect(first["effect_id"], observation)

    assert len(restarted.observations) == 1
    assert len(restarted.settled_effects) == 1
    assert restarted.authority["queries_used"] == 1
    assert restarted.authority["steps_used"] == 1


def test_completion_recovers_an_observation_saved_before_settlement(tmp_path):
    store = _store(tmp_path)
    effect = store.admit_and_spend(
        "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-probe"})
    observation = _observation(effect)
    store.observe(observation)
    restarted = frontier.FrontierStore(str(store.path))

    restarted.complete_effect(effect["effect_id"], observation)

    assert len(restarted.observations) == 1
    assert len(restarted.settled_effects) == 1
    assert restarted.authority["queries_used"] == 1


def test_conflicting_effect_identity_cannot_create_a_second_charge(tmp_path):
    store = _store(tmp_path)
    first = store.admit_and_spend(
        "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-one"})

    with pytest.raises(frontier.Refused, match="not admissible|identity"):
        store.admit_and_spend(
            "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
            effect_identity={"operation_id": "op-two"})

    assert len(store.pending_effects) == 1
    assert store.pending_effects[0]["effect_id"] == first["effect_id"]
    assert store.authority["queries_used"] == 1


def test_foreign_observation_cannot_settle_a_bound_effect(tmp_path):
    store = _store(tmp_path)
    effect = store.admit_and_spend(
        "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-probe"})
    foreign = _observation(effect)
    foreign["task"] = "opp-other"

    with pytest.raises(frontier.Refused, match="target"):
        store.complete_effect(effect["effect_id"], foreign)

    assert store.observations == []
    assert len(store.pending_effects) == 1
    assert store.authority["queries_used"] == 1


def test_incomplete_round_receipt_is_refused(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(frontier.Refused, match="receipt"):
        store.record_round_command(
            1, 0, action={"kind": "wait", "inputs": {}, "requested_resources": {}},
            state={}, receipt={}, executed_digest="a" * 64)
