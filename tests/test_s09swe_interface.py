"""The SWE world must answer the same world interface as the two incumbents.

Lane I registers the world by calling these names, so the shape is pinned by
test rather than by convention.
"""

from __future__ import annotations

import inspect

import pytest

from experiments.ad01 import boolean_active as boolean
from experiments.ad01 import policy_action as contract
from experiments.ad01 import second_active as active
from experiments.ad01 import s09_swe_policy as policy
from experiments.ad01 import s09_swe_tasks as tasks
from experiments.ad01 import s09_swe_world as world

WORLD_FUNCTIONS = ("run_episode", "public_state", "apply_action",
                   "as_shared_action", "is_terminal")


def test_the_swe_world_matches_the_incumbent_world_signatures():
    for name in WORLD_FUNCTIONS:
        actual = inspect.signature(getattr(world, name))
        for incumbent in (active, boolean):
            expected = inspect.signature(getattr(incumbent, name))
            assert [(item.name, item.kind, item.default)
                    for item in actual.parameters.values()] == \
                   [(item.name, item.kind, item.default)
                    for item in expected.parameters.values()], name
            assert actual.return_annotation == expected.return_annotation, name


def test_public_state_is_the_policy_view_for_a_live_session():
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    session = world.SweSession(record)

    assert world.public_state(session) == session.policy_view()


def test_as_shared_action_round_trips_through_the_shared_contract():
    for kind in contract.ACTION_KINDS:
        action = _action(kind, "swe.task")

        parsed = contract.parse_action(world.as_shared_action(action))

        assert parsed.kind == kind
        assert parsed.target == "swe.task"


def test_the_world_uses_only_the_shared_action_vocabulary():
    for kind in world.ACTION_TARGETS:
        assert kind in contract.ACTION_KINDS

    schema = world.action_schema()
    for kind in schema["actions"]:
        assert kind in contract.ACTION_KINDS


def test_an_episode_is_deterministic_for_a_fixed_split_and_seed():
    def driver(_view):
        return _action("observe", "test.run", {"test": "case-01"})

    first = world.run_episode(driver, split="held_out", seed=3)
    second = world.run_episode(driver, split="held_out", seed=3)

    assert first == second


def test_the_split_and_seed_select_the_instance_and_never_the_answer():
    for index, record in enumerate(tasks.enumerate_instances("held_out")):
        result = world.run_episode(lambda _state: _action("stop", "swe.task"),
                                   split="held_out", seed=index)

        assert result["task_id"] == record["task_id"]
        assert result["trace"][-1]["effect"]["kind"] == "stop"
        assert result["final"]["outcome"] == "unrepaired"


def test_malformed_actions_are_refused_at_the_shared_contract_boundary():
    session = world.SweSession(tasks.instance(
        "held_out", tasks.HELD_OUT_TEMPLATES[0], tasks.HELD_OUT_MECHANISMS[0]))
    malformed = _action("observe", "test.observe")
    malformed["inputs"] = []

    with pytest.raises(world.ActionRefused, match="inputs must be an object") \
            as caught:
        world.apply_action(session, malformed)

    assert isinstance(caught.value.__cause__, contract.ActionRefused)


def test_a_shared_kind_with_no_world_operation_is_refused():
    result = world.run_episode(lambda _state: _action("use", "swe.task"),
                               split="held_out", seed=3)

    assert result["final"]["outcome"] == "unrepaired"
    assert "refused" in result["trace"][-1]
    assert result["trace"][-1]["refused"] == "use target must be code.repair"


def test_registering_a_world_takes_no_new_machinery():
    module = world

    assert isinstance(module.INSTRUMENT_ID, str) and module.INSTRUMENT_ID
    assert module.SPLITS == ("dev", "held_out")
    assert callable(module.run_episode)
    assert callable(module.action_schema)
    assert isinstance(module.action_schema()["actions"], dict)
    assert module.action_schema()["budget"] == world.action_schema()["budget"]


def _action(kind, target, inputs=None):
    return {
        "kind": kind,
        "target": target,
        "inputs": {} if inputs is None else inputs,
        "evidence_refs": [],
        "requested_resources": {},
    }
