"""The typed AST is contingent, and the suite can tell a reducer from a policy.

A closed interpreter that replays a fixed schedule looks identical to one that
reads the world if a test only compares action kinds. Every episode here is
judged on the *content* of the actions the world admitted, and a deliberately
fixed-schedule control is run through the same judge and must be classified
the other way. If the judge stops separating them, this file fails.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_ast_policy as ast_policy
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import policy_action

SEEDS = tuple(range(8))


def _const(value):
    return {"op": "const", "value": value}


def _field(scope, name):
    return {"op": "field", "scope": scope, "name": name}


def _index(value, key):
    return {"op": "index", "value": value, "key": key}


def _eq(left, right):
    return {"op": "eq", "left": left, "right": right}


def _obj(**fields):
    return {"op": "obj", "fields": {
        name: value if isinstance(value, dict) and "op" in value
        else _const(value)
        for name, value in fields.items()}}


def _action(kind, target, inputs=None, state=None, resources=None):
    return {"op": "return_action", "kind": kind, "target": target,
            "inputs": _obj(**(inputs or {})),
            "evidence_refs": [], "requested_resources": resources or {},
            "state": _const({} if state is None else state)}


def _record(document):
    encoded = json.dumps(document, allow_nan=False, ensure_ascii=False,
                         separators=(",", ":"), sort_keys=True).encode()
    return {"artifact": {
        "kind": "learning-policy", "representation": "typed-ast",
        "version": "boolean-typed-ast-v1",
        "policy_id": document["policy_id"],
        "ast_digest": hashlib.sha256(encoded).hexdigest(),
    }, "policy_ast": document}


def _observation_bit(probe_index, output_index):
    observed = _field("view", "observed")
    return _index(_index(_index(observed, _const(probe_index)),
                         _const("y")), _const(output_index))


def _derived_specs(probe_index=0):
    return {"op": "list", "items": [
        _obj(const=_observation_bit(probe_index, output_index),
             mask=0, pair=None)
        for output_index in range(rules.N_OUTPUTS)]}


def _fixed_specs():
    return {"op": "list", "items": [
        _obj(const=0, mask=0, pair=None) for _ in range(rules.N_OUTPUTS)]}


def _episode(document, seeds=SEEDS, **limits):
    return {seed: active.run_episode(
        ast_policy.choose_action(_record(document), **limits),
        split="dev", seed=seed) for seed in seeds}


def _admitted(episode):
    """What the world actually admitted, as comparable text.

    A refusal carries no world effect, so it is excluded: a policy that
    simply failed everywhere is not contingent either.
    """
    return [json.dumps(step["action"], sort_keys=True)
            for step in episode["trace"] if "effect" in step]


def _truth(episode):
    return (episode["queried"], episode["final"])


def _consts(episode):
    """The four committed constant bits, as a hashable value."""
    return tuple(spec["const"] for spec in
                 episode["trace"][-1]["action"]["inputs"]["specs"])


def _is_contingent(episodes):
    """Whether the admitted actions vary with the world.

    Two readings of the same policy: one that fixes its schedule and its
    payload, and one that reads what the world told it. Only the second
    produces more than one distinct admitted action across seeds.
    """
    return len({tuple(_admitted(ep)) for ep in episodes.values()}) > 1


def _fixed_schedule_document():
    """The control. Identical bytes out for every world, on purpose."""
    return {"policy_id": "fixed-schedule", "entry": {
        "op": "if", "cond": _eq(_field("view", "observed"), _const([])),
        "then": _action("probe", "boolean.query", {"x": 5}, {"step": 1},
                        {"queries": 1}),
        "else": _action("construct", "boolean.commit",
                        {"specs": _fixed_specs()}, {"step": 2}),
    }}


def _contingent_document():
    """Probe once, then commit what that probe returned, bit for bit."""
    return {"policy_id": "contingent-select", "entry": {
        "op": "if", "cond": _eq(_field("view", "observed"), _const([])),
        "then": _action("probe", "boolean.query", {"x": 5}, {"step": 1},
                        {"queries": 1}),
        "else": _action("construct", "boolean.commit",
                        {"specs": _derived_specs()}, {"step": 2}),
    }}


def test_the_suite_separates_a_fixed_schedule_from_a_reader():
    fixed = _episode(_fixed_schedule_document())
    contingent = _episode(_contingent_document())

    assert not _is_contingent(fixed), (
        "the control is meant to replay one schedule for every world")
    assert _is_contingent(contingent)


def test_a_fixed_schedule_produces_the_same_action_for_every_world():
    fixed = _episode(_fixed_schedule_document())

    committed = {seed: episode["trace"][-1]["action"]["inputs"]["specs"]
                 for seed, episode in fixed.items()}
    assert len({json.dumps(specs, sort_keys=True)
                for specs in committed.values()}) == 1
    assert all(episode["queried"] == [5]
               for episode in fixed.values())


def test_a_reader_commits_a_different_predictor_for_a_different_observation():
    episodes = _episode(_contingent_document())

    committed = {seed: _consts(episode)
                 for seed, episode in episodes.items()}
    assert len(set(committed.values())) > 1
    for seed, episode in episodes.items():
        observed = rules.RuleSession(rules.make_task("dev", seed)).query(5)
        assert committed[seed] == tuple(observed), seed


def test_substituting_the_observation_changes_the_actual_effect():
    """A different effect, not just a different recorded action.

    Every seed here runs the same policy through the same code path, and
    every one of them commits, so `effect["kind"]` and `committed` are
    identical across the panel. What differs is the predictor the world
    holds afterwards and the score it computes, both read back from the
    session rather than from the arm's own action dict.
    """
    episodes = _episode(_contingent_document())

    world_effects = {seed: _truth(episode)
                     for seed, episode in episodes.items()}
    assert len({json.dumps(effect, default=str, sort_keys=True)
                for effect in world_effects.values()}) > 1
    assert all(episode["committed"] for episode in episodes.values())
    assert all(episode["final"]["queried"] == 1.0
               for episode in episodes.values())
    scores = {episode["final"]["overall"] for episode in episodes.values()}
    assert len(scores) > 1, "the world's own scoring did not move"

    for seed, episode in episodes.items():
        others = [other for other in SEEDS if other != seed]
        assert _truth(episode) != _truth(episodes[others[0]]), seed


def test_a_reader_needs_no_memory_across_steps_to_stay_contingent():
    """The view alone carries what the policy branches on.

    `state_contract` calls the step state the policy's own working
    state. This policy keeps the world's own `observed` list instead,
    which already holds every fact a two-step reader needs, and varies
    by world anyway. Memory is therefore not the mechanism, which is
    what makes this the cheapest expression of contingency the frozen
    node set allows.
    """
    document = _contingent_document()
    episodes = _episode(document)

    assert _is_contingent(episodes)
    assert len({_consts(episode) for episode in episodes.values()}) > 1

    with_state_dropped = []
    for seed in SEEDS:
        session = rules.RuleSession(rules.make_task("dev", seed))
        first = ast_policy.ast_step(
            _record(document), active.public_state(session), {})
        assert first["action"]["kind"] == policy_action.PROBE
        session.query(first["action"]["inputs"]["x"])
        second = ast_policy.ast_step(
            _record(document), active.public_state(session), {})
        assert second["action"]["kind"] == policy_action.CONSTRUCT
        with_state_dropped.append(second["action"]["inputs"]["specs"])
    assert len({_consts(episode)
                for episode in episodes.values()}) > 1
    assert with_state_dropped == [
        episode["trace"][-1]["action"]["inputs"]["specs"]
        for episode in episodes.values()]


@pytest.mark.parametrize("seed", SEEDS)
def test_every_admitted_action_came_from_the_typed_program(seed):
    """No hidden path from the document to the world.

    Re-running the loaded program on the same view must produce the
    action the world admitted, so nothing may act between the
    interpreter and the world.
    """
    document = _contingent_document()
    episode = active.run_episode(
        ast_policy.choose_action(_record(document)), split="dev", seed=seed)
    session = rules.RuleSession(rules.make_task("dev", seed))
    state = {}
    for step in episode["trace"]:
        public = active.public_state(session)
        result = ast_policy.ast_step(_record(document), public, state)
        assert result["action"] == step["action"]
        if "effect" not in step:
            break
        if result["action"]["kind"] == policy_action.PROBE:
            session.query(result["action"]["inputs"]["x"])
        state = result["state"]
