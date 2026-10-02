from __future__ import annotations

import pytest

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_rule as rules


def _probe(x):
    return {"kind": "probe", "target": "boolean.query", "inputs": {"x": x},
            "evidence_refs": [], "requested_resources": {"queries": 1}}


def _commit(specs):
    return {"kind": "construct", "target": "boolean.commit",
            "inputs": {"specs": specs}, "evidence_refs": [],
            "requested_resources": {}}


def _stop():
    return {"kind": "stop", "target": "boolean.task", "inputs": {},
            "evidence_refs": [], "requested_resources": {}}


def _chooser(*actions):
    queue = list(actions)

    def choose(_state):
        return queue.pop(0)
    return choose


def test_the_agent_chooses_every_probe():
    result = active.run_episode(
        _chooser(*[_probe(i) for i in (7, 2, 9, 0, 5)],
                 _stop()),
        split="dev", seed=4)

    assert result["queried"] == [0, 2, 5, 7, 9]
    assert [t["action"]["inputs"]["x"] for t in result["trace"][:5]] == [7, 2, 9, 0, 5]
    assert result["committed"] is False


def test_a_budget_emptied_without_committing_scores_nothing():
    result = active.run_episode(
        _chooser(*[_probe(i) for i in range(8)]),
        split="dev", seed=4)

    assert result["queried"] == list(range(8))
    assert result["committed"] is False
    assert result["final"] is None


def test_host_refuses_a_repeated_probe():
    result = active.run_episode(
        _chooser(_probe(3), _probe(3)),
        split="dev", seed=4)

    assert len(result["trace"]) == 2
    assert "refused" in result["trace"][1]
    assert "already queried" in result["trace"][1]["refused"]


@pytest.mark.parametrize("action, fragment", [
    ({"kind": "teleport", "target": "t", "inputs": {}, "evidence_refs": [], "requested_resources": {}}, "unknown action"),
    (_probe(99), "0..15"),
    (_probe("3"), "0..15"),
    (_commit([]), "illegal-hypothesis"),
])
def test_illegal_actions_fail_explicitly(action, fragment):
    result = active.run_episode(_chooser(action), split="dev", seed=4)

    assert "refused" in result["trace"][-1]
    assert fragment in result["trace"][-1]["refused"]


def test_committing_stops_the_episode_and_is_scored():
    from experiments.ad01 import boolean_rule

    task = boolean_rule.make_task("dev", 4)
    specs = [{"const": 0, "mask": 0, "pair": None} for _ in range(4)]
    result = active.run_episode(
        _chooser(_probe(1),
                 {"kind": "construct", "target": "boolean.commit",
                  "inputs": {"specs": specs}, "evidence_refs": [],
                  "requested_resources": {}}),
        split="dev", seed=4)

    assert result["committed"] is True
    assert result["queried"] == [1]
    assert len(result["trace"]) == 2
    assert result["final"] is not None
    assert result["final"]["n_queried"] == 1
    assert task["task_id"] == result["task_id"]


def test_the_view_never_carries_the_hidden_tables():
    seen = []

    def spy(state):
        seen.append(state)
        return _probe(len(seen))

    active.run_episode(spy, split="dev", seed=4)

    assert seen
    for state in seen:
        assert "tables" not in state
        assert set(state) == {
            "instrument", "task_id", "split", "max_queries", "remaining",
            "observed", "hypothesis_class", "action_schema"}


def test_the_view_reports_the_remaining_budget_to_the_agent():
    remaining = []
    active.run_episode(
        lambda s: (remaining.append(s["remaining"]),
                   _probe(len(s["observed"])))[1],
        split="dev", seed=4)

    assert remaining == [8, 7, 6, 5, 4, 3, 2, 1]


def test_the_frozen_output_round_remains_untouched():
    from experiments.ad01 import live_construct

    prompt = live_construct.OUTPUT_PROMPT_TEMPLATE
    assert "specs" in prompt
    assert "probe" not in prompt.lower()


def test_world_actions_convert_into_the_shared_campaign_contract():
    from experiments.ad01 import policy_action

    for world, want_kind, want_target in (
            (active.PROBE, policy_action.PROBE, "boolean.query"),
            (active.COMMIT, policy_action.CONSTRUCT, "boolean.commit"),
            (active.STOP, policy_action.STOP, "boolean.task")):
        shared = policy_action.parse_action(
            active.as_shared_action({"kind": world, "x": 1, "specs": []}))
        assert shared.kind == want_kind
        assert shared.target == want_target


def test_the_active_world_produces_no_seventh_vocabulary():
    """A world that invents its own action type is the failure being fixed."""
    from experiments.ad01 import policy_action

    state = active.public_state(active.rules.RuleSession(
        active.rules.make_task("dev", 4)))
    for kind in active.ACTION_VOCABULARY:
        shared = policy_action.parse_action(
            active.as_shared_action({"kind": kind, "x": 0, "specs": []}))
        assert shared.kind in policy_action.ACTION_KINDS
    assert state["action_schema"]["actions"]["probe"]
