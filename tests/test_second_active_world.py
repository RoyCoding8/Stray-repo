from __future__ import annotations

import inspect
import itertools

import pytest

from experiments.ad01 import boolean_active as boolean
from experiments.ad01 import policy_action as contract
from experiments.ad01 import second_active as active


def _action(kind, target, inputs=None):
    return {
        "kind": kind,
        "target": target,
        "inputs": {} if inputs is None else inputs,
        "evidence_refs": [],
        "requested_resources": {},
    }


def _ordering_driver(state):
    observed = {
        (item["left"], item["right"]): item["earlier"]
        for item in state["observed"]
    }
    pairs = list(itertools.combinations(state["hypothesis_class"]["job_ids"], 2))
    pending = [pair for pair in pairs if pair not in observed]
    if pending:
        left, right = pending[0]
        return _action("probe", "schedule.compare", {"left": left, "right": right})

    later = {job: set() for job in state["hypothesis_class"]["job_ids"]}
    indegree = {job: 0 for job in state["hypothesis_class"]["job_ids"]}
    for (left, right), earlier in observed.items():
        after = right if earlier == left else left
        later[earlier].add(after)
        indegree[after] += 1
    ready = sorted(job for job, count in indegree.items() if count == 0)
    order = []
    while ready:
        job = ready.pop(0)
        order.append(job)
        for after in sorted(later[job]):
            indegree[after] -= 1
            if indegree[after] == 0:
                ready.append(after)
                ready.sort()
    return _action("construct", "schedule.commit", {"order": order})


def test_a_shared_driver_solves_a_full_episode_within_the_budget():
    result = active.run_episode(_ordering_driver, split="dev", seed=4)

    assert result["committed"] is True
    assert result["final"]["overall"] == 1.0
    assert result["final"]["exact"] is True
    assert result["final"]["n_comparisons"] == 6
    assert len(result["comparisons"]) == 6
    assert "refused" not in result["trace"][-1]


def test_the_public_view_exposes_only_the_named_jobs_and_observed_order():
    seen = []

    def spy(state):
        seen.append(state)
        return _action("stop", "schedule.task")

    active.run_episode(spy, split="dev", seed=4)

    assert len(seen) == 1
    assert set(seen[0]) == {
        "instrument", "task_id", "split", "max_queries", "remaining",
        "observed", "hypothesis_class", "action_schema",
    }
    assert "tables" not in seen[0]
    assert "seed" not in seen[0]
    assert seen[0]["action_schema"]["budget"] == {
        "max_queries": seen[0]["max_queries"],
    }
    assert set(seen[0]["action_schema"]["actions"]) == {
        "probe", "construct", "stop",
    }
    assert "commit" not in seen[0]["action_schema"]["actions"]


def test_malformed_actions_are_refused_at_the_shared_contract_boundary():
    session = active.ScheduleSession(active.make_task("dev", 4))
    malformed = _action("probe", "schedule.compare")
    malformed["inputs"] = []

    with pytest.raises(
            active.ActionRefused, match="inputs must be an object") as caught:
        active.apply_action(session, malformed)

    assert isinstance(caught.value.__cause__, contract.ActionRefused)


@pytest.mark.parametrize("kind", ["observe", "use", "check"])
def test_shared_kinds_without_a_world_operation_stop_terminally(kind):
    result = active.run_episode(
        lambda _state: _action(kind, "schedule.task"),
        split="dev", seed=4,
    )

    assert result["committed"] is False
    assert result["trace"] == [{
        "action": _action(kind, "schedule.task"),
        "effect": {"kind": "stop", "remaining": 8},
        "state_before": {"remaining": 8, "comparisons": []},
    }]


def test_identical_split_and_seed_produce_identical_traces():
    first = active.run_episode(_ordering_driver, split="dev", seed=4)
    second = active.run_episode(_ordering_driver, split="dev", seed=4)

    assert first == second


def test_a_boolean_hardcoded_strategy_does_not_solve_the_ordering_world():
    def boolean_strategy(state):
        if len(state["observed"]) < 8:
            x = len(state["observed"])
            return _action("probe", "schedule.compare", {"x": x})
        return _action("construct", "schedule.commit", {"specs": [0, 0, 0, 0]})

    result = active.run_episode(boolean_strategy, split="dev", seed=4)

    assert result["committed"] is False
    assert result["final"] is None
    assert result["trace"][-1]["refused"] == (
        "comparison jobs must be named job ids"
    )


def test_the_episode_callback_matches_the_boolean_world_signature():
    functions = (
        (active.run_episode, boolean.run_episode),
        (active.public_state, boolean.public_state),
        (active.apply_action, boolean.apply_action),
        (active.as_shared_action, boolean.as_shared_action),
        (active.is_terminal, boolean.is_terminal),
    )
    for actual, expected in functions:
        actual_signature = inspect.signature(actual)
        expected_signature = inspect.signature(expected)
        assert [
            (item.name, item.kind, item.default)
            for item in actual_signature.parameters.values()
        ] == [
            (item.name, item.kind, item.default)
            for item in expected_signature.parameters.values()
        ]
        assert (
            actual_signature.return_annotation
            == expected_signature.return_annotation
        )


def test_as_shared_action_preserves_the_campaign_vocabulary_without_renaming():
    for kind in contract.ACTION_KINDS:
        shared = contract.parse_action(active.as_shared_action(
            _action(kind, "schedule.task")))

        assert shared.kind == kind
        assert shared.target == "schedule.task"
