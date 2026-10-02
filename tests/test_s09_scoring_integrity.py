"""The score is derived by the world, and the shared contract is the reason.

Stage 9 requires that the campaign score external task results rather than
anything a policy supplies. This pins the mechanism rather than the
conclusion: a policy cannot state its own result, because an action
carrying fields outside the declared vocabulary is refused at the
contract boundary before the world ever sees it.

Both worlds are exercised, and the ordering world is the newer of the
two and had no independent audit before it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_active as boolean_world
from experiments.ad01 import boolean_rule as boolean_rules
from experiments.ad01 import policy_action
from experiments.ad01 import second_active as ordering_world

TASK = ROOT / "experiments/ad01/worlds/world-0/dev/ad01-w0-dev-gr-00.json"

INJECTED = ("score", "final_measure", "overall", "exact", "reduced", "reward")


def _specs(values):
    return [{"const": value, "mask": 0, "pair": None} for value in values]


def test_a_policy_cannot_smuggle_a_score_through_the_shared_contract():
    payload = {
        "kind": "construct",
        "target": "boolean.commit",
        "inputs": {"specs": _specs([1, 0, 0, 1])},
        "evidence_refs": [],
        "requested_resources": {},
    }
    for field in INJECTED:
        smuggled = dict(payload, **{field: 1.0})
        try:
            policy_action.parse_action(smuggled)
        except policy_action.ActionRefused as refusal:
            assert field in str(refusal), refusal
        else:
            raise AssertionError(
                "an action carrying %r parsed, so a policy could claim a "
                "score of its own" % field)


def test_the_boolean_world_derives_its_result_itself():
    task = dict(json.loads(TASK.read_text()), split="dev")
    session = boolean_rules.RuleSession(task)
    view = boolean_world.public_state(session)
    committed = boolean_world.apply_action(session, {
        "kind": "construct",
        "target": "boolean.commit",
        "inputs": {"specs": _specs([1, 0, 0, 1])},
        "evidence_refs": [],
        "requested_resources": {},
    })
    result = boolean_world.as_shared_action(committed)
    assert "score" not in result and "overall" not in result
    assert view["action_schema"]["budget"]["max_queries"] == 8


def test_the_ordering_world_derives_its_result_itself():
    task = ordering_world.make_task("dev", 0)
    view = ordering_world.public_state(ordering_world.ScheduleSession(task))
    result = ordering_world.run_episode(
        lambda state: {
            "kind": "stop",
            "target": "order.stop",
            "inputs": {},
            "evidence_refs": [],
            "requested_resources": {},
            "score": 1.0,
            "final_measure": 1.0,
        },
        split="dev",
        seed=0)
    assert result["committed"] is False
    assert result["final"] is None
    assert "score" not in json.dumps(view)


def test_either_world_reports_an_identical_key_set():
    task = dict(json.loads(TASK.read_text()), split="dev")
    boolean_keys = set(boolean_world.public_state(
        boolean_rules.RuleSession(task)))
    ordering_keys = set(ordering_world.public_state(
        ordering_world.ScheduleSession(ordering_world.make_task("dev", 0))))
    assert boolean_keys == ordering_keys
    assert boolean_keys == {
        "action_schema", "hypothesis_class", "instrument", "max_queries",
        "observed", "remaining", "split", "task_id"}


def test_neither_view_carries_a_generator_seed_or_template():
    task = dict(json.loads(TASK.read_text()), split="dev")
    boolean_view = json.dumps(boolean_world.public_state(
        boolean_rules.RuleSession(task)), sort_keys=True)
    ordering_view = json.dumps(ordering_world.public_state(
        ordering_world.ScheduleSession(ordering_world.make_task("dev", 0))),
        sort_keys=True)
    for view in (boolean_view, ordering_view):
        assert "tables" not in view
        assert "seed" not in view
    assert str(task["seed"]) not in boolean_view
    assert task["template"] not in boolean_view
