"""What the policy is allowed to see, pinned to the exact field list.

The campaign's claim is that a representation is comparable only if every
arm gets the same observations and none of them can read the answer. Both
halves are asserted here against the literal field list, so widening the
view, or slipping the hidden truth table in under a new key, breaks this
file rather than quietly changing what an arm knows.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_ast_policy as ast_policy
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import policy_action
from experiments.ad01 import s09_arm_parity as parity

# The exact surface a policy sees. Anything here is fair game for a branch;
# anything absent is an answer the arm must not be able to read.
LEGITIMATE_FIELDS = frozenset({
    "instrument", "task_id", "observed", "remaining", "public_world",
    "action_schema",
})

PUBLIC_WORLD_FIELDS = frozenset({"split", "max_queries", "hypothesis_class"})

# The world holds all three of these. A policy holds none of them.
SECRET_KEYS = frozenset({
    "tables", "seed", "order", "comparisons", "committed",
    "final", "queried", "score", "tables", "_task", "_comparisons",
    "_committed", "fault", "fault_label", "injected", "grader", "grade",
    "answer", "solution", "label", "task",
})


def _const(value):
    return {"op": "const", "value": value}


def _field(scope, name):
    return {"op": "field", "scope": scope, "name": name}


def _index(value, key):
    return {"op": "index", "value": value, "key": key}


def _record(document):
    encoded = json.dumps(document, allow_nan=False, ensure_ascii=False,
                         separators=(",", ":"), sort_keys=True).encode()
    return {"artifact": {
        "kind": "learning-policy", "representation": "typed-ast",
        "version": "boolean-typed-ast-v1",
        "policy_id": document["policy_id"],
        "ast_digest": hashlib.sha256(encoded).hexdigest(),
    }, "policy_ast": document}


def _public(seed=4, **overrides):
    session = rules.RuleSession(rules.make_task("dev", seed))
    public = active.public_state(session)
    public.update(overrides)
    return public


def _view(seed=4, **overrides):
    return ast_policy._shared_view(_public(seed, **overrides))


def _paths(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _paths(item, "%s.%s" % (prefix, key) if prefix else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _paths(item, "%s[%d]" % (prefix, index))
    else:
        yield prefix, value


def test_the_policy_view_is_exactly_the_legitimate_field_list():
    view = _view()

    assert set(view) == LEGITIMATE_FIELDS
    assert set(view) == set(policy_action.view_contract()["fields"])
    assert set(view) == set(parity.contract_view(
        active.public_state(rules.RuleSession(rules.make_task("dev", 4)))))
    assert set(view["public_world"]) == PUBLIC_WORLD_FIELDS


def test_no_path_in_the_view_names_the_hidden_target_the_grader_or_a_fault():
    view = _view()
    named = {path for path, _ in _paths(view)}
    leaves = {path.rsplit(".", 1)[-1].split("[")[0] for path in named}

    assert leaves & SECRET_KEYS == set()
    serialized = json.dumps(view, sort_keys=True)
    for secret in ("tables", "seed", "fault", "grader", "grade", "answer"):
        assert '"%s"' % secret not in serialized, secret


def test_the_view_never_carries_a_value_from_the_hidden_tables():
    task = rules.make_task("dev", 4)
    view = _view(4)
    serialized = json.dumps(view, sort_keys=True)
    hidden = list(task["tables"])

    for table in hidden:
        assert str(table) not in serialized or table == 0
    assert "tables" not in view


def test_the_shared_view_refuses_a_public_state_that_exposes_hidden_tables():
    public = active.public_state(rules.RuleSession(rules.make_task("dev", 4)))
    public["tables"] = [0, 1, 2, 3]

    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        ast_policy._shared_view(public)
    assert "exposes hidden tables" in str(raised.value)


def test_the_shared_view_refuses_a_public_state_missing_a_public_field():
    public = active.public_state(rules.RuleSession(rules.make_task("dev", 4)))
    del public["hypothesis_class"]

    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        ast_policy._shared_view(public)
    assert "missing: hypothesis_class" in str(raised.value)


def test_a_policy_cannot_name_a_view_field_that_does_not_exist():
    """The grammar is closed over the view, so a secret cannot be spelled.

    A program that tried to read the hidden tables would have to name a
    view field the contract does not publish. The loader refuses the
    name, which is the check that keeps the surface above honest.
    """
    document = {"policy_id": "peek", "entry": {
        "op": "return_action", "kind": "stop", "target": "boolean.task",
        "inputs": {"op": "obj", "fields": {
            "v": _field("view", "tables")}},
        "evidence_refs": [], "requested_resources": {},
        "state": _const({})}}
    with pytest.raises(ast_policy._LoadRefused) as raised:
        ast_policy.load_policy(_record(document), expected_policy_id="peek")
    assert "unknown view field 'tables'" in str(raised.value)

    state_document = {"policy_id": "peek-state", "entry": {
        "op": "return_action", "kind": "stop", "target": "boolean.task",
        "inputs": {"op": "obj", "fields": {
            "v": _field("state", "_tables")}},
        "evidence_refs": [], "requested_resources": {},
        "state": _const({})}}
    with pytest.raises(ast_policy._LoadRefused) as raised:
        ast_policy.load_policy(_record(state_document),
                               expected_policy_id="peek-state")
    assert "must not start with underscore" in str(raised.value)


def test_every_view_field_the_grammar_admits_is_published_by_the_contract():
    assert set(ast_policy._VIEW_TYPES) == LEGITIMATE_FIELDS


def test_the_contract_view_and_the_ast_view_agree_field_for_field():
    """Two independent projections of the same public state.

    `s09_arm_parity.contract_view` is what a registered arm is handed and
    `_shared_view` is what the AST child is handed. If they ever drift,
    an AST arm and a STEP arm would be compared on different
    observations, which is the whole thing the harness exists to stop.
    """
    for seed in range(4):
        public = active.public_state(rules.RuleSession(rules.make_task("dev", seed)))
        contract = parity.contract_view(public)
        shared = ast_policy._shared_view(public)
        assert parity.view_digest(contract) == parity.view_digest(shared), seed


def test_the_digest_of_the_view_is_stable_across_equal_public_states():
    public = active.public_state(rules.RuleSession(rules.make_task("dev", 4)))
    first = ast_policy._shared_view(dict(public))
    second = ast_policy._shared_view(dict(public))
    assert parity.view_digest(first) == parity.view_digest(second)


def test_every_published_field_is_reachable_from_the_program():
    """Readable is the claim; this is what makes it one.

    A field can be in the view and still be unreachable, if no
    combination of `field` and `index` names it. Echoing each one back
    out as an action input proves the grammar can carry every published
    value to the world, which is the other half of "a policy may branch
    on the observation".
    """
    observed = _field("view", "observed")
    world = _field("view", "public_world")
    hypothesis = _index(world, _const("hypothesis_class"))
    document = {"policy_id": "read-all", "entry": {
        "op": "return_action", "kind": "stop", "target": "boolean.task",
        "inputs": {"op": "obj", "fields": {
            "instrument": _field("view", "instrument"),
            "task_id": _field("view", "task_id"),
            "remaining": _field("view", "remaining"),
            "observed": observed,
            "split": _index(world, _const("split")),
            "max_queries": _index(world, _const("max_queries")),
            "n_inputs": _index(hypothesis, _const("n_inputs")),
            "actions": _index(_field("view", "action_schema"),
                              _const("actions"))}},
        "evidence_refs": [], "requested_resources": {},
        "state": _const({})}}
    loaded, _entry = ast_policy._load(_record(document))
    result = ast_policy._execute_document(
        loaded, ast_policy._shared_view(_public()), {})
    inputs = result["action"]["inputs"]

    assert set(inputs) == {"instrument", "task_id", "observed", "remaining",
                           "split", "max_queries", "n_inputs", "actions"}
    assert inputs["instrument"] == "boolean-rule-v1"
    assert inputs["remaining"] == 8
    assert inputs["observed"] == []
    assert inputs["split"] == "dev"
    assert inputs["max_queries"] == 8
    assert inputs["n_inputs"] == 4
    assert set(inputs["actions"]) == {"probe", "construct", "stop"}
