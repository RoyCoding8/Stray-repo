from __future__ import annotations

import copy
import json

import pytest

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_graph_policy as graph
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step


def _action(kind, target, inputs=None, resources=None):
    return {
        "kind": kind,
        "target": target,
        "inputs": {} if inputs is None else inputs,
        "evidence_refs": [],
        "requested_resources": {} if resources is None else resources,
    }


def _probe(x):
    return _action("probe", "boolean.query", {"x": x}, {"queries": 1})


def _commit(y):
    return _action("construct", "boolean.commit", {
        "specs": [
            {"const": bit, "mask": 0, "pair": None}
            for bit in y
        ],
    })


def _stop():
    return _action("stop", "boolean.task")


def _arm(guard, action, next_node, progress=1):
    return {
        "guard": guard,
        "action": action,
        "next": next_node,
        "progress": progress,
    }


def _record(start="probe", nodes=None):
    if nodes is None:
        nodes = {
            "probe": {
                "kind": "action",
                "arms": [
                    _arm({"field": "observed.count", "op": "eq", "value": 0},
                         _probe(3), "decision", 1),
                    _arm({"always": True}, _stop(), "stop", 0),
                ],
            },
            "decision": {
                "kind": "action",
                "arms": [
                    _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                         _commit((1, 0, 0, 1)), "done", 1),
                    _arm({"always": True}, _stop(), "stop", 0),
                ],
            },
            "done": {
                "kind": "action",
                "arms": [_arm({"always": True}, _stop(), "done", 0)],
            },
            "stop": {
                "kind": "action",
                "arms": [_arm({"always": True}, _stop(), "stop", 0)],
            },
        }
    return {
        "policy_id": "probe-3-commit",
        "start": start,
        "nodes": nodes,
    }


def _run(record, seed=4):
    return active.run_episode(
        graph.choose_action(record), split="dev", seed=seed)


def _refusal(result):
    return result["trace"][-1]["action"]["inputs"]["bridge_refusal"]


def test_graph_arms_choose_the_probe_and_construct_a_scored_predictor():
    record = _record()

    result = _run(record)

    assert result["trace"][0]["action"] == _probe(3)
    assert result["trace"][0]["effect"] == {
        "kind": "probe", "x": 3, "observation": (1, 0, 0, 1),
    }
    assert result["trace"][1]["action"] == _commit([1, 0, 0, 1])
    assert result["trace"][1]["effect"] == {
        "kind": "commit", "committed": True,
    }
    assert result["queried"] == [3]
    assert result["committed"] is True
    assert result["final"] == {
        "overall": 0.1875,
        "queried": 1.0,
        "unqueried": 0.13333333333333333,
        "n_queried": 1,
    }


def test_a_terminal_arm_stops_without_spending_a_query():
    record = {
        "policy_id": "stop-now",
        "start": "stop",
        "nodes": {
            "stop": {
                "kind": "action",
                "arms": [_arm({"always": True}, _stop(), "stop", 0)],
            },
        },
    }

    result = _run(record)

    assert result["queried"] == []
    assert result["trace"] == [{
        "action": _stop(),
        "effect": {"kind": "stop", "remaining": 8},
        "state_before": {"remaining": 8, "queried": []},
    }]
    assert result["committed"] is False


def test_every_graph_action_uses_the_shared_contract_and_world_adapter():
    record = _record()
    loaded = graph.load_policy(record)
    probe = loaded.nodes["probe"].arms[0].action.as_dict()
    effect = active.apply_action(active.rules.RuleSession(
        active.rules.make_task("dev", 4)), probe)

    assert policy_action.parse_action(probe).kind == policy_action.PROBE
    assert active.as_shared_action(effect) == probe
    assert {arm.action.kind for node in loaded.nodes.values()
            for arm in node.arms} <= set(policy_action.ACTION_KINDS)


def test_the_graph_view_is_a_serialized_subset_of_public_state():
    public = active.public_state(active.rules.RuleSession(
        active.rules.make_task("dev", 4)))
    view = graph.make_view(public)
    raw = json.dumps(view, sort_keys=True)

    assert set(view) == {
        "instrument", "task_id", "observed", "remaining", "public_world",
        "action_schema",
    }
    assert set(view) - set(public) == {"public_world"}
    assert set(view["public_world"]) <= set(public)
    assert "tables" not in raw
    assert "seed" not in raw
    assert "\"seed\"" not in raw


@pytest.mark.parametrize("mutate, fragment", [
    (lambda p: p["nodes"].update({
        "orphan": {"kind": "action", "arms": [
            _arm({"always": True}, _stop(), "orphan", 0)]}}), "unreachable node"),
    (lambda p: p["nodes"]["probe"]["arms"].__setitem__(0, {
        "guard": {"field": "private.tables", "op": "eq", "value": 1},
        "action": _probe(3), "next": "commit", "progress": 1}),
     "unknown field"),
    (lambda p: p["nodes"]["probe"]["arms"].pop(), "fallback"),
    (lambda p: p.__setitem__("policy_id", "different"), None),
])
def test_invalid_graphs_are_rejected_at_load_time(mutate, fragment):
    record = _record()
    mutate(record)

    with pytest.raises(graph.GraphPolicyRefused) as caught:
        graph.load_policy(record, expected_policy_id="probe-3-commit")

    if fragment is not None:
        assert fragment in str(caught.value)


def test_a_cycle_that_cannot_reach_stop_is_rejected_at_load_time():
    record = {
        "policy_id": "closed-loop",
        "start": "loop",
        "nodes": {
            "loop": {
                "kind": "action",
                "arms": [
                    _arm({"always": True}, _probe(3), "loop", 0)],
            },
        },
    }

    with pytest.raises(graph.GraphPolicyRefused, match="cycle cannot reach"):
        graph.load_policy(record)


def test_a_rejected_world_action_becomes_a_legal_traceable_stop():
    record = {
        "policy_id": "rejected-probe",
        "start": "start",
        "nodes": {
            "start": {
                "kind": "action",
                "arms": [
                    _arm({"field": "observed.count", "op": "eq", "value": 1},
                         _probe(3), "next", 1),
                    _arm({"always": True}, _stop(), "start", 0),
                ],
            },
            "next": {
                "kind": "action",
                "arms": [
                    _arm({"always": True}, _stop(), "next", 0)],
            },
        },
    }
    decide = graph.choose_action(record)
    public = active.public_state(active.rules.RuleSession(
        active.rules.make_task("dev", 4)))
    public["observed"] = [{"x": 3, "y": [0, 0, 0, 0]}]

    first = decide(public)
    second = decide(public)

    assert first["kind"] == policy_action.STOP
    assert first["inputs"]["bridge_refusal"]["stage"] == "graph-step"
    assert "already queried" in first["inputs"]["bridge_refusal"]["reason"]
    assert second == first
    session = active.rules.RuleSession(active.rules.make_task("dev", 4))
    effect = active.apply_action(session, first)
    assert effect == {"kind": "stop", "remaining": 8}
    assert session.remaining == 8


def test_policy_state_is_carried_and_capped():
    decide = graph.choose_action(_record())
    public = active.public_state(active.rules.RuleSession(
        active.rules.make_task("dev", 4)))
    public_after_probe = copy.deepcopy(public)
    public_after_probe["observed"] = [{"x": 3, "y": [1, 0, 0, 1]}]

    first = decide(public)
    second = decide(public_after_probe)

    assert first == _probe(3)
    assert second == _commit([1, 0, 0, 1])
    assert policy_step.STATE_LIMIT_BYTES == 4096

    long_node = "s" * 5000
    record = {
        "policy_id": "oversized-state",
        "start": "first",
        "nodes": {
            "first": {
                "kind": "action",
                "arms": [
                    _arm({"always": True}, _probe(3), long_node, 1),
                ],
            },
            long_node: {
                "kind": "action",
                "arms": [
                    _arm({"always": True}, _stop(), long_node, 0)],
            },
        },
    }
    capped = graph.choose_action(record)
    first = capped(public)

    assert first["inputs"]["bridge_refusal"]["reason"].startswith(
        "policy state exceeds 4096 bytes")


def test_choose_action_never_calls_the_legacy_policy_step():
    source = "experiments/ad01/boolean_graph_policy.py".replace(
        "experiments/ad01/", "")
    module = __import__(
        "experiments.ad01.boolean_graph_policy", fromlist=["__name__"])
    root = __import__("pathlib").Path(module.__file__).parent
    recorded = []
    original = policy_step.run_policy_step

    def forbidden(*args, **kwargs):
        recorded.append(True)
        return original(*args, **kwargs)

    policy_step.run_policy_step = forbidden
    try:
        result = _run(_record())
    finally:
        policy_step.run_policy_step = original

    assert result["committed"] is True
    assert recorded == []
    assert "run_policy_step" not in (
        root / "boolean_graph_policy.py").read_text()
