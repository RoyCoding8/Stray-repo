from __future__ import annotations

import pytest

from experiments.ad01 import boolean_rule as rules
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


def test_effect_cannot_settle_before_a_durable_charge(tmp_path):
    store = _store(tmp_path)
    effect = store.accept("opp-probe", store.active_digest)
    store._doc["pending_effects"][0]["charged"] = False
    store._doc["pending_effects"][0]["charged_resources"] = {}
    store.save()
    observation = _observation(effect)

    with pytest.raises(frontier.Refused, match="charge"):
        store.settle(effect["effect_id"], observation)

    assert store.settled_effects == []
    assert store.authority["queries_used"] == 1


def test_attributed_observation_cannot_reuse_an_unattributed_identity(tmp_path):
    store = _store(tmp_path)
    store.observe({"observation_id": "obs-shared", "task": "unattributed",
                   "verdict": "observed"})
    effect = store.admit_and_spend(
        "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-probe"})

    with pytest.raises(frontier.Refused, match="observation.*identity"):
        store.complete_effect(effect["effect_id"], {
            **_observation(effect), "observation_id": "obs-shared"})

    assert len(store.observations) == 1
    assert store.settled_effects == []


def test_restart_rejects_duplicate_observation_identity(tmp_path):
    store = _store(tmp_path)
    store._doc["observations"] = [
        {"observation_id": "obs-shared", "task": "one", "verdict": "observed"},
        {"observation_id": "obs-shared", "task": "two", "verdict": "observed"},
    ]
    store.save()

    with pytest.raises(frontier.Refused, match="observation.*identity"):
        frontier.FrontierStore(str(store.path))


def test_restart_rejects_two_observations_for_one_settled_effect(tmp_path):
    store = _store(tmp_path)
    effect = store.admit_and_spend(
        "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-probe"})
    first = _observation(effect)
    store.complete_effect(effect["effect_id"], first)
    second = {**first, "observation_id": "obs-second"}
    store._doc["observations"].append(second)
    store.save()

    with pytest.raises(frontier.Refused, match="observation.*effect"):
        frontier.FrontierStore(str(store.path))


def test_write_path_rejects_two_observations_for_one_effect(tmp_path):
    store = _store(tmp_path)
    effect = store.admit_and_spend(
        "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-probe"})
    first = _observation(effect)
    store.complete_effect(effect["effect_id"], first)

    with pytest.raises(frontier.Refused, match="observation.*effect"):
        store.observe({**first, "observation_id": "obs-second"})

    assert len(store.observations) == 1


@pytest.mark.parametrize("resources", [
    {},
    {"queries": 0},
    {"queries": -1},
    {"queries": True},
    {"queries": float("inf")},
    {"unknown": 1},
])
@pytest.mark.parametrize("record_kind", ["effect", "round-journal"])
def test_restart_rejects_invalid_charged_resource_projection(
        tmp_path, resources, record_kind):
    store = _store(tmp_path)
    if record_kind == "effect":
        store.admit_and_spend(
            "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
            effect_identity={"operation_id": "op-probe"})
        charged = store._doc["pending_effects"][0]
    else:
        channel.drive_improve_round(
            store, rules.make_task("dev", 4), round_no=1,
            admit_probes=True)
        charged = next(
            entry for entry in store._doc["round_journal"]
            if entry["charged"])
    charged["charged_resources"] = resources
    store.save()

    with pytest.raises(frontier.Refused, match="resource|charge"):
        frontier.FrontierStore(str(store.path))


@pytest.mark.parametrize("record_kind", ["effect", "round-journal"])
def test_restart_rejects_missing_charged_resource_projection(
        tmp_path, record_kind):
    store = _store(tmp_path)
    if record_kind == "effect":
        store.admit_and_spend(
            "opp-probe", store.active_digest, {"queries": 1, "steps": 1},
            effect_identity={"operation_id": "op-probe"})
        charged = store._doc["pending_effects"][0]
    else:
        channel.drive_improve_round(
            store, rules.make_task("dev", 4), round_no=1,
            admit_probes=True)
        charged = next(
            entry for entry in store._doc["round_journal"]
            if entry["charged"])
    del charged["charged_resources"]
    store.save()

    with pytest.raises(frontier.Refused, match="resource|charge"):
        frontier.FrontierStore(str(store.path))


def test_restart_rejects_tampered_historical_round_result(tmp_path):
    store = _store(tmp_path)
    channel.drive_improve_round(
        store, rules.make_task("dev", 4), round_no=1, admit_probes=True)
    store._doc["round_results"][0]["log"][0]["result"] = "forged"
    store.save()

    with pytest.raises(frontier.Refused, match="round result|identity"):
        frontier.FrontierStore(str(store.path))


@pytest.mark.parametrize("field", ["rounds", "improvement_log"])
def test_restart_rejects_removed_dead_round_projection(tmp_path, field):
    store = _store(tmp_path)
    store._doc[field] = [{"forged": True}]
    store.save()

    with pytest.raises(frontier.Refused, match="round|projection"):
        frontier.FrontierStore(str(store.path))


def test_restart_rejects_malformed_evidence_record_as_refusal(tmp_path):
    store = _store(tmp_path)
    store._doc["evidence"] = [[]]
    store.save()

    with pytest.raises(frontier.Refused, match="evidence.*object|projection"):
        frontier.FrontierStore(str(store.path))


def test_restart_rejects_malformed_accepted_revision_as_refusal(tmp_path):
    store = _store(tmp_path)
    store._doc["accepted_revisions"] = [[]]
    store.save()

    with pytest.raises(frontier.Refused, match="accepted revision"):
        frontier.FrontierStore(str(store.path))
