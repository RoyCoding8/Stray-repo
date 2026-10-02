"""The frozen AST node set, measured rather than described.

`expressivity_limits` is a claim about a closed interpreter, and a claim
about a limit is only worth as much as the refusal behind it. Every
`cannot` row is driven back through the loader here and asserted against
its refusal text, so a limit that stops being true breaks the suite
rather than quietly becoming a capability nobody tested.

The learner builder below is the "concrete attempted behavior" the
handoff asks for. It is written once, parameterised by how many output
bits it recovers and which input weights it probes, and the sweep is
what turns "the node budget is small" into a measured boundary.
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_ast_policy as ast_policy
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import policy_action
from experiments.ad01 import second_active as second


def _const(value):
    return {"op": "const", "value": value}


def _field(scope, name):
    return {"op": "field", "scope": scope, "name": name}


def _index(value, key):
    return {"op": "index", "value": value, "key": key}


def _eq(left, right):
    return {"op": "eq", "left": left, "right": right}


def _add(left, right):
    return {"op": "add", "left": left, "right": right}


def _lt(left, right):
    return {"op": "lt", "left": left, "right": right}


def _not(value):
    return {"op": "not", "value": value}


def _obj(**fields):
    return {"op": "obj", "fields": {
        name: value if isinstance(value, dict) and "op" in value
        else _const(value)
        for name, value in fields.items()}}


def _list(*items):
    return {"op": "list", "items": list(items)}


def _assign(name, value):
    return {"op": "assign", "name": name, "value": value}


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


def _load(document):
    return ast_policy.load_policy(_record(document),
                                  expected_policy_id=document["policy_id"])


def _refusal(document):
    with pytest.raises(ast_policy._LoadRefused) as raised:
        _load(document)
    return str(raised.value)


def _charge(document):
    """Nodes the loader charges, read from the loader's own counter."""
    budget = ast_policy._Budget()
    ast_policy._stmt(document["entry"], "$.entry", budget)
    return budget.nodes


def _observed(probe_index, output_index):
    return _index(_index(_index(_field("view", "observed"), _const(probe_index)),
                         _const("y")), _const(output_index))


def _learner(output_bits, weights):
    """Recover `c` and the weight bits for `output_bits` outputs.

    Input 0 has all four bits clear, so `y(0, b)` is the affine constant
    `c_b`. Each weight input then reveals whether that bit is set. The
    only way this node set can combine weight bits into one mask is an
    if-cascade over every case, so the mask costs a factor of the case
    count per output. That is the cost the sweep measures.
    """
    derive = []
    for output in range(output_bits):
        derive.append(_assign("c%d" % output, _observed(0, output)))
        for position, weight in enumerate(weights):
            derive.append({
                "op": "if",
                "cond": _eq(_observed(position + 1, output),
                            _field("state", "c%d" % output)),
                "then": _assign("w%d_%d" % (output, weight), _const(0)),
                "else": _assign("w%d_%d" % (output, weight), _const(1))})
        cascade = _assign("m%d" % output, _const(0))
        for case in range(2 ** len(weights)):
            condition = _const(True)
            for position, weight in enumerate(weights):
                term = _eq(_field("state", "w%d_%d" % (output, weight)),
                           _const(1 if case >> position & 1 else 0))
                condition = (_not(term) if case >> position & 1
                             else _not(_not(term)))
            cascade = {"op": "if", "cond": condition,
                       "then": _assign("m%d" % output,
                                       _const(sum(w for i, w in enumerate(weights)
                                                   if case >> i & 1))),
                       "else": cascade}
        derive.append(cascade)
    commit = _action("construct", "boolean.commit", {"specs": _list(*[
        _obj(const=_field("state", "c%d" % output),
             mask=_field("state", "m%d" % output), pair=None)
        for output in range(output_bits)])}, {"step": len(weights) + 1})
    plan = [0] + list(weights)
    ladder = {"op": "block", "stmts": derive + [commit]}
    for position in range(len(plan) - 1, 0, -1):
        ladder = {"op": "if",
                  "cond": _eq(_field("state", "step"), _const(position)),
                  "then": _action("probe", "boolean.query",
                                  {"x": _const(plan[position])},
                                  {"step": position + 1}, {"queries": 1}),
                  "else": ladder}
    return {"policy_id": "learn-%d-%d" % (output_bits, len(weights)),
            "entry": {"op": "block", "stmts": [
                {"op": "if",
                 "cond": _eq(_field("view", "observed"), _const([])),
                 "then": _action("probe", "boolean.query",
                                 {"x": _const(plan[0])}, {"step": 1},
                                 {"queries": 1}),
                 "else": ladder}]}}


def _world_view(seed=4, **overrides):
    session = rules.RuleSession(rules.make_task("dev", seed))
    public = active.public_state(session)
    public.update(overrides)
    return public


def test_the_measured_frontier_matches_the_reported_table():
    """Every node count in `expressivity_limits` is re-derived here.

    The table is the artifact a reviewer reads. If a builder changes and
    the reported node count drifts, this fails instead of leaving a
    plausible wrong number in the source.
    """
    reported = ast_policy.expressivity_limits()["measured_frontier"]["grid"]
    measured = []
    for row in reported:
        document = _learner(row["output_bits"],
                            (1, 2, 4, 8)[:row["probes"] - 1])
        try:
            _load(document)
        except ast_policy._LoadRefused:
            measured.append((row["output_bits"], row["probes"], None))
            continue
        measured.append((row["output_bits"], row["probes"], _charge(document)))
    assert measured == [(row["output_bits"], row["probes"], row["nodes"])
                        for row in reported]
    assert any(nodes is None for _, _, nodes in measured), (
        "a frontier with no refusal is a claim of totality, not a boundary")


def test_a_four_output_learner_over_three_weights_is_the_attempted_behavior():
    """The Boolean world commits four class members, so four outputs.

    This is the policy the handoff asks for: recover the affine
    parameters of every committed output. It is written out in full and
    refused, and the refusal names the node budget rather than a type
    error, so the limit is size and not expressibility of the step.
    """
    document = _learner(4, (1, 2, 4))
    message = _refusal(document)

    assert "policy exceeds 256 nodes" in message
    assert ast_policy.expressivity_limits()["frozen_limits"]["max_nodes"] == 256


def test_the_smallest_recoverable_mask_fits_and_the_next_one_does_not():
    """The boundary is a cliff, not a slope, and it is one probe wide."""
    two_probes = _learner(4, (1,))
    _load(two_probes)

    assert _charge(two_probes) <= ast_policy.MAX_NODES
    assert "policy exceeds 256 nodes" in _refusal(_learner(4, (1, 2)))


def test_the_two_probe_learner_runs_and_commits_for_every_seed():
    """A program at the frontier that does not merely load, but works.

    It recovers every committed output's affine constant from input 0
    and its bit-0 weight from input 1, and commits. It is not expected
    to score well: input 2, 3 and 8 are still unread, so a committed
    mask that needs them is wrong. The point is that the frontier
    program is a working learner at the edge of what loads, not a
    program that only passes the loader.
    """
    document = _learner(4, (1,))
    for seed in range(4):
        episode = active.run_episode(
            ast_policy.choose_action(_record(document)), split="dev", seed=seed)
        assert episode["committed"] is True, seed
        assert episode["queried"] == [0, 1], seed
        assert len(episode["trace"]) == 3, seed
        assert episode["trace"][-1]["effect"] == {"kind": "commit",
                                                   "committed": True}
        assert all("bridge_refusal" not in step["action"]["inputs"]
                   for step in episode["trace"]), seed


def test_a_state_value_cannot_be_compared_against_a_number():
    """The missing cell, isolated from the budget."""
    assert "lt requires two numeric operands" in _refusal(
        {"policy_id": "lt-state", "entry": _action(
            "stop", "boolean.task", {"v": _lt(_field("state", "m"), _const(8))})})
    assert "add requires two numeric operands" in _refusal(
        {"policy_id": "add-state", "entry": _action(
            "stop", "boolean.task", {"v": _add(_field("state", "m"), _const(1))})})
    assert "not operand must have boolean type" in _refusal(
        {"policy_id": "not-state", "entry": _action(
            "stop", "boolean.task", {"v": _not(_field("state", "m"))})})
    assert "if condition must have boolean type" in _refusal(
        {"policy_id": "cond-state", "entry": {
            "op": "if", "cond": _field("state", "done"),
            "then": _action("stop", "boolean.task"),
            "else": _action("stop", "boolean.task")}})


def test_a_conditional_value_is_expressible_by_branch_assignment():
    """The limit above is about arithmetic, not about conditionals.

    Without this, the refusal above reads as "state is inert", which
    would be the wrong lesson: the node set does produce values from
    branches, it just cannot fold two derived bits into one number.
    """
    document = {"policy_id": "conditional-value", "entry": {"op": "block",
               "stmts": [
        {"op": "if", "cond": _eq(_field("view", "remaining"), _const(8)),
         "then": _assign("v", _const(1)), "else": _assign("v", _const(0))},
        _action("stop", "boolean.task", {"flag": _field("state", "v")})]}}
    _load(document)
    assert ast_policy.ast_step(
        _record(document), _world_view(remaining=8), {})[
            "action"]["inputs"] == {"flag": 1}
    assert ast_policy.ast_step(
        _record(document), _world_view(remaining=3), {})[
            "action"]["inputs"] == {"flag": 0}


def test_an_observation_value_is_not_numeric_either():
    assert "add requires two numeric operands" in _refusal(
        {"policy_id": "add-observed", "entry": _action(
            "stop", "boolean.task",
            {"v": _add(_index(_field("view", "observed"), _const(0)),
                       _const(1))})})


def test_the_boolean_world_accepts_its_own_actions_under_the_contract():
    view = ast_policy._shared_view(_world_view())
    accepted = policy_action.parse_action(
        {"kind": "probe", "target": "boolean.query", "inputs": {"x": 3}})
    ast_policy._validate_action(accepted, view)


@pytest.mark.parametrize("payload, reason", [
    ({"kind": "probe", "target": "schedule.compare",
      "inputs": {"left": "analysis", "right": "build"}},
     "probe target must be boolean.query"),
    ({"kind": "construct", "target": "schedule.commit",
      "inputs": {"order": ["analysis", "build", "deploy", "verify"]}},
     "construct target must be boolean.commit"),
    ({"kind": "stop", "target": "schedule.task", "inputs": {}},
     "stop target must be boolean.task"),
])
def test_the_ordering_world_has_no_ast_arm(payload, reason):
    """The second world is out of reach, and it is not a spelling problem.

    `contract_view` renames the world's advertised `commit` to the
    contract's `construct` before any arm sees it. This test refuses the
    action with the schema rename already undone, so the refusal belongs
    to the executor rather than to the world's own vocabulary.
    """
    view = ast_policy._shared_view(_world_view())
    with pytest.raises(policy_action.ActionRefused) as raised:
        ast_policy._validate_action(policy_action.parse_action(payload), view)
    assert reason in str(raised.value)

    limits = ast_policy.expressivity_limits()
    assert limits["worlds"]["ordering-constraints"]["can"] == []
    assert limits["worlds"]["ordering-constraints"]["cannot"]


def test_the_ordering_world_is_refused_even_with_the_schema_rename_patched():
    """The refusal survives removing the first gate, so there are two.

    `monkeypatch` is deliberate: the point is that the second gate is
    independent, so the result does not depend on how the first one is
    spelled.
    """
    import experiments.ad01.boolean_ast_policy as module

    original = module._shared_schema
    module._shared_schema = lambda schema: {
        **deepcopy(schema),
        "actions": {("commit" if name == "construct" else name): spec
                    for name, spec in schema["actions"].items()}}
    try:
        record = _record({"policy_id": "second-world", "entry": _action(
            "probe", "schedule.compare",
            {"left": _const("analysis"), "right": _const("build")},
            {"queries": 1})})
        episode = second.run_episode(
            ast_policy.choose_action(record), split="dev", seed=1)
    finally:
        module._shared_schema = original

    refusal = episode["trace"][0]["action"]["inputs"]["bridge_refusal"]
    assert refusal["reason"] == "probe target must be boolean.query"
    assert episode["comparisons"] == []


def test_the_reported_can_and_cannot_are_either_measured_or_absent():
    """A claim in the limits table must point at something checkable."""
    limits = ast_policy.expressivity_limits()
    for world, entry in limits["worlds"].items():
        for claim in entry["can"]:
            assert isinstance(claim, str) and claim
        for claim in entry["cannot"]:
            assert set(claim) == {"behavior", "missing_cell", "witness"}
            assert all(claim.values())
    assert limits["frozen_limits"]["max_nodes"] == ast_policy.MAX_NODES
    assert limits["frozen_limits"]["max_depth"] == ast_policy.MAX_DEPTH
    assert limits["frozen_limits"]["max_integer_bits"] \
        == ast_policy.MAX_INTEGER_BITS
    assert limits["frozen_limits"]["max_block_statements"] \
        == ast_policy.MAX_BLOCK_STATEMENTS
