from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from settlement.child_limits import ChildLimits, child_setup_refusal

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_ast_policy as ast_policy
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step

_CHILD_REFUSAL = child_setup_refusal(ChildLimits(cpu_seconds=10))
REQUIRES_BOUNDED_CHILD = pytest.mark.skipif(
    _CHILD_REFUSAL is not None,
    reason=("requires bounded child execution: "
            + (_CHILD_REFUSAL.reason if _CHILD_REFUSAL else "")),
)


def _host_setup_was_refused(result):
    if _CHILD_REFUSAL is None or _CHILD_REFUSAL.kind != "child-setup-unavailable":
        return False
    reason = ast_policy.child_limit_support().reason
    assert result["trace"][-1]["action"]["inputs"]["bridge_refusal"]["reason"] == reason
    return True


def _const(value):
    return {"op": "const", "value": value}


def _field(scope, name):
    return {"op": "field", "scope": scope, "name": name}


def _index(value, key):
    return {"op": "index", "value": value, "key": key}


def _add(left, right):
    return {"op": "add", "left": left, "right": right}


def _eq(left, right):
    return {"op": "eq", "left": left, "right": right}


def _lt(left, right):
    return {"op": "lt", "left": left, "right": right}


def _not(value):
    return {"op": "not", "value": value}


def _list(*items):
    return {"op": "list", "items": list(items)}


def _obj(*args, **fields):
    if args:
        pairs = dict(*args, **fields)
    else:
        pairs = fields
    return {"op": "obj", "fields": {
        key: value if isinstance(value, dict) and "op" in value
        else _const(value)
        for key, value in pairs.items()
    }}


def _raw_obj(fields):
    return {"op": "obj", "fields": fields}


def _return_action(*, kind="stop", target="boolean.task", inputs=None,
                    state=None, evidence_refs=None, requested_resources=None):
    if inputs is None:
        inputs_expression = _const({"x": 0})
    elif isinstance(inputs, dict) and "op" in inputs:
        inputs_expression = inputs
    else:
        inputs_expression = _raw_obj({
            key: value if isinstance(value, dict) and "op" in value
            else _const(value)
            for key, value in inputs.items()
        })
    return {
        "op": "return_action",
        "kind": kind,
        "target": target,
        "inputs": inputs_expression,
        "evidence_refs": list(evidence_refs or []),
        "requested_resources": dict(requested_resources or {}),
        "state": _const({} if state is None else state),
    }


def _canonical_digest(document):
    encoded = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record(document):
    return {
        "artifact": {
            "kind": "learning-policy",
            "representation": "typed-ast",
            "version": "boolean-typed-ast-v1",
            "policy_id": document["policy_id"],
            "ast_digest": _canonical_digest(document),
        },
        "policy_ast": document,
    }


def _stop_document(policy_id="stop-immediately"):
    return {
        "policy_id": policy_id,
        "entry": _return_action(inputs={}),
    }


def _derived_specs(bits):
    return _list(*[
        _obj(const=_index(bits, _const(index)), mask=0, pair=None)
        for index in range(4)
    ])


def _probe_then_commit_document(policy_id="probe-three-then-commit"):
    observed = _field("view", "observed")
    last = _index(observed, _const(0))
    bits = _list(*[_index(_index(last, _const("y")), _const(index))
                    for index in range(4)])
    return {
        "policy_id": policy_id,
        "entry": {
            "op": "if",
            "cond": _eq(observed, _const([])),
            "then": _return_action(
                kind="probe",
                target="boolean.query",
                inputs={"x": 3},
                requested_resources={"queries": 1},
                state={"probed": False},
            ),
            "else": _return_action(
                kind="construct",
                target="boolean.commit",
                inputs={"specs": _derived_specs(bits)},
                state={"probed": True},
            ),
        },
    }


def _run(document, seed=4, **limits):
    return active.run_episode(
        ast_policy.choose_action(_record(document), **limits),
        split="dev",
        seed=seed,
    )


def _public_state():
    return active.public_state(active.rules.RuleSession(
        active.rules.make_task("dev", 4)))


def _refusal(result):
    return result["trace"][-1]["action"]["inputs"]["bridge_refusal"]


def test_blocks_sequence_assignments_before_an_action():
    document = _stop_document("sequence")
    document["entry"] = {
        "op": "block",
        "stmts": [
            {"op": "assign", "name": "next_x", "value": _const(4)},
            _return_action(inputs={}),
        ],
    }
    loaded, _entry = ast_policy._load(_record(document))
    action = ast_policy._execute_document(
        loaded, ast_policy._shared_view(_public_state()), {})["action"]

    assert action == {
        "kind": "stop", "target": "boolean.task", "inputs": {},
        "evidence_refs": [], "requested_resources": {},
    }


def test_a_block_is_a_bounded_nonempty_sequence():
    empty = _stop_document("empty-block")
    empty["entry"] = {"op": "block", "stmts": []}
    with pytest.raises(ast_policy._LoadRefused) as refused:
        ast_policy.choose_action(_record(empty))
    assert str(refused.value) == (
        "$.policy_ast.entry.stmts: block stmts must be a nonempty list")

    too_long = _stop_document("long-block")
    too_long["entry"] = {
        "op": "block",
        "stmts": [_return_action(inputs={}) for _ in range(65)],
    }
    with pytest.raises(ast_policy._LoadRefused) as refused:
        ast_policy.choose_action(_record(too_long))
    assert str(refused.value) == (
        "$.policy_ast.entry.stmts: block exceeds 64 statements")


def test_structural_limits_reject_documents_at_load_time():
    deep = _const(True)
    for _ in range(40):
        deep = {"op": "not", "value": deep}
    deep_document = _stop_document("too-deep")
    deep_document["entry"] = {
        "op": "if",
        "cond": deep,
        "then": _return_action(inputs={}),
        "else": _return_action(inputs={}),
    }
    with pytest.raises(ast_policy._LoadRefused) as refused:
        ast_policy.choose_action(_record(deep_document))
    assert str(refused.value).endswith("policy exceeds depth 32")

    wide_document = _stop_document("too-wide")
    wide_document["entry"] = {
        "op": "block",
        "stmts": [
            {"op": "if", "cond": _const(index < 99),
             "then": {"op": "assign", "name": "value_%d" % index,
                      "value": _const(index)},
             "else": _return_action(inputs={})}
            for index in range(40)
        ],
    }
    with pytest.raises(ast_policy._LoadRefused) as refused:
        ast_policy.choose_action(_record(wide_document))
    assert str(refused.value).endswith("policy exceeds 256 nodes")

    integer_document = _stop_document("wide-integer")
    integer_document["entry"]["inputs"] = _const({
        "x": 1 << 65,
    })
    with pytest.raises(ast_policy._LoadRefused) as refused:
        ast_policy.choose_action(_record(integer_document))
    assert str(refused.value).endswith("integer exceeds 64 bits")


@REQUIRES_BOUNDED_CHILD
def test_typed_ast_drives_the_existing_world_to_a_real_commit():
    document = _probe_then_commit_document()
    document["entry"] = {
        "op": "block",
        "stmts": [
            {
                "op": "assign",
                "name": "next_x",
                "value": _const(3),
            },
            {
                "op": "if",
                "cond": _eq(_field("view", "observed"), _const([])),
                "then": _return_action(
                    kind="probe",
                    target="boolean.query",
                    inputs={"x": 3},
                    requested_resources={"queries": 1},
                    state={"probed": False},
                ),
                "else": document["entry"]["else"],
            },
        ],
    }
    result = _run(document)

    assert result["queried"] == [3]
    assert result["trace"][0]["action"]["kind"] == policy_action.PROBE
    assert result["trace"][0]["effect"] == {
        "kind": "probe",
        "x": 3,
        "observation": (1, 0, 0, 1),
    }
    assert result["trace"][1]["action"]["kind"] == policy_action.CONSTRUCT
    assert result["trace"][1]["effect"] == {"kind": "commit", "committed": True}
    assert result["trace"][1]["action"]["inputs"]["specs"] == [
        {"const": 1, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 1, "mask": 0, "pair": None},
    ]
    assert result["committed"] is True
    assert result["final"] == {
        "overall": 0.1875,
        "queried": 1.0,
        "unqueried": 0.13333333333333333,
        "n_queried": 1,
    }


@REQUIRES_BOUNDED_CHILD
def test_the_program_derives_a_different_predictor_from_different_observations():
    document = _probe_then_commit_document("derived")
    first = _run(document, seed=4)
    second = _run(document, seed=3)

    assert first["trace"][1]["action"]["inputs"]["specs"] != \
        second["trace"][1]["action"]["inputs"]["specs"]
    assert [spec["const"] for spec in first["trace"][1]["action"]["inputs"]["specs"]] \
        == [1, 0, 0, 1]
    assert [spec["const"] for spec in second["trace"][1]["action"]["inputs"]["specs"]] \
        == [0, 1, 0, 0]
    assert first["final"]["queried"] == second["final"]["queried"] == 1.0


@REQUIRES_BOUNDED_CHILD
def test_probe_comes_from_the_evaluated_typed_program():
    document = _probe_then_commit_document()
    result = _run(document)
    loaded, entry = ast_policy._load(_record(document))
    session = active.rules.RuleSession(active.rules.make_task("dev", 4))
    view = ast_policy._shared_view(active.public_state(session))

    evaluated = ast_policy._execute_document(loaded, view, {})

    assert result["trace"][0]["action"] == evaluated["action"]
    assert evaluated["action"]["inputs"] == {"x": 3}


@REQUIRES_BOUNDED_CHILD
def test_the_same_ast_policy_can_stop_without_spending_a_query():
    result = _run(_stop_document())

    assert len(result["trace"]) == 1
    assert result["trace"][0]["action"] == {
        "kind": "stop",
        "target": "boolean.task",
        "inputs": {},
        "evidence_refs": [],
        "requested_resources": {},
    }
    assert result["trace"][0]["effect"] == {"kind": "stop", "remaining": 8}
    assert result["queried"] == []
    assert result["committed"] is False


def test_every_emitted_action_is_parsed_by_the_shared_contract():
    results = []
    for document in (_probe_then_commit_document(), _stop_document()):
        loaded, _entry = ast_policy._load(_record(document))
        results.append(ast_policy._execute_document(
            loaded, ast_policy._shared_view(_public_state()), {}))

    for result in results:
        parsed = policy_action.parse_action(result["action"])
        assert parsed.as_dict() == result["action"]
        assert parsed.kind in policy_action.ACTION_KINDS


@pytest.mark.parametrize("mutate, path", [
    (
        lambda document: document["entry"]["then"].update({"op": "teleport"}),
        "$.policy_ast.entry.then: unknown statement op 'teleport'",
    ),
    (
        lambda document: document["entry"]["then"].update({
            "inputs": {"op": "add", "left": _const("not-a-number"),
                       "right": _const(1)}
        }),
        "$.policy_ast.entry.then.inputs: add requires two numeric operands",
    ),
    (
        lambda document: document["entry"]["then"].pop("requested_resources"),
        "$.policy_ast.entry.then: missing required field: requested_resources",
    ),
    (
        lambda document: document["entry"].update({"op": "field"}),
        "$.policy_ast.entry: unknown statement op 'field'",
    ),
])
def test_invalid_documents_fail_at_load_with_the_node_path(mutate, path):
    document = _probe_then_commit_document()
    mutate(document)

    with pytest.raises(ast_policy._LoadRefused) as refused:
        ast_policy.choose_action(_record(document))

    assert path in str(refused.value)


def test_policy_id_mismatch_fails_at_load():
    document = _probe_then_commit_document()
    record = _record(document)
    record["artifact"]["policy_id"] = "different-policy"

    with pytest.raises(ast_policy._LoadRefused, match=r"\$\.policy_ast\.policy_id"):
        ast_policy.choose_action(record)

    with pytest.raises(ast_policy._LoadRefused, match=r"expected policy id"):
        ast_policy.load_policy(_record(document), "different-policy")


def test_one_bad_deep_node_preserves_the_rest_of_the_valid_document():
    document = _stop_document("deep-type-error")
    bad_action = _return_action(inputs={})
    bad_action["inputs"] = _index(
        _const({"bad": 3}), _add(_const(1), _const("two"))
    )
    document["entry"] = {
        "op": "if",
        "cond": _const(False),
        "then": _return_action(inputs={}),
        "else": bad_action,
    }
    repaired = copy.deepcopy(document)
    repaired["entry"]["else"]["inputs"] = _const({})
    invalid = _record(document)
    valid = _record(repaired)

    with pytest.raises(ast_policy._LoadRefused) as refused:
        ast_policy.choose_action(invalid)

    assert refused.value.args[0] == (
        "$.policy_ast.entry.else.inputs.key: add requires two numeric operands")
    loaded, _entry = ast_policy._load(valid)
    assert ast_policy._execute_document(
        loaded, ast_policy._shared_view(_public_state()), {})["action"] == {
        "kind": "stop",
        "target": "boolean.task",
        "inputs": {},
        "evidence_refs": [],
        "requested_resources": {},
    }


def test_a_failing_ast_step_becomes_a_legal_recorded_stop():
    document = _stop_document("runtime-failure")
    document["entry"] = {
        "op": "if",
        "cond": _const(True),
        "then": {
            "op": "if",
            "cond": _const(True),
            "then": {
                "op": "return_action",
                "kind": "stop",
                "target": "boolean.task",
                "inputs": _index(_const([]), _const(0)),
                "evidence_refs": [],
                "requested_resources": {},
                "state": _const({}),
            },
            "else": _return_action(),
        },
        "else": _return_action(),
    }
    # The budget must clear the child's cold import before it can reach the
    # program at all. A bare import of the AST policy measured 0.36-0.89 s on
    # this host, so 1000 ms put the wall timeout between the launch and the
    # IndexError the test is about, and the refusal named the wrong cause.
    # The product default is 10 s; the CPU limit below is what actually
    # bounds the program, and there is a separate test for the timeout.
    result = _run(document, timeout_ms=10000, cpu_seconds=2)

    if _host_setup_was_refused(result):
        assert result["trace"][-1]["action"]["kind"] == policy_action.STOP
        assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
        return

    assert len(result["trace"]) == 1
    assert result["trace"][0]["action"]["kind"] == policy_action.STOP
    assert result["trace"][0]["effect"] == {"kind": "stop", "remaining": 8}
    assert _refusal(result)["stage"] == "ast-policy-step"
    assert "list index is out of range" in _refusal(result)["reason"]
    assert result["queried"] == []


def test_timeout_becomes_a_legal_recorded_stop():
    result = _run(_stop_document("timeout"), timeout_ms=1, cpu_seconds=1)

    if _host_setup_was_refused(result):
        assert result["trace"][-1]["action"]["kind"] == policy_action.STOP
        assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
        return

    assert result["trace"][-1]["action"]["kind"] == policy_action.STOP
    assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
    assert _refusal(result)["reason"] == "wall timeout after 1 ms"
    assert result["queried"] == []


def test_the_serialized_view_is_a_public_subset_without_tables_or_seed():
    public_state = _public_state()
    view = ast_policy._shared_view(public_state)
    serialized = json.dumps(view, sort_keys=True)

    assert "tables" not in view
    assert "seed" not in view
    assert '"tables"' not in serialized
    assert '"seed"' not in serialized
    assert set(view) == {
        "instrument", "task_id", "observed", "remaining", "public_world",
        "action_schema",
    }
    assert view["observed"] == public_state["observed"]
    assert view["public_world"]["max_queries"] == 8


def test_state_is_capped_and_only_advances_after_action_validation():
    oversized = _stop_document("oversized-state")
    oversized["entry"]["state"] = _const({"data": "x" * 5000})
    loaded, _entry = ast_policy._load(_record(oversized))
    evaluated = ast_policy._execute_document(
        loaded, ast_policy._shared_view(_public_state()), {})
    with pytest.raises(ValueError, match="policy state exceeds 4096 bytes"):
        policy_step.validate_state(evaluated["state"])

    rejected = _stop_document("rejected-state")
    rejected["entry"] = {
        "op": "if",
        "cond": _eq(_field("state", "probed"), _const(True)),
        "then": _return_action(),
        "else": _return_action(
            kind="probe",
            target="boolean.query",
            inputs={"x": 99},
            requested_resources={"queries": 1},
            state={"probed": True},
        ),
    }
    decision = ast_policy.choose_action(_record(rejected))
    public_state = _public_state()
    first = decision(public_state)
    second = decision(public_state)

    if _CHILD_REFUSAL is not None \
            and _CHILD_REFUSAL.kind == "child-setup-unavailable":
        assert first["kind"] == policy_action.STOP
        assert "child" in first["inputs"]["bridge_refusal"]["reason"]
        assert second == first
        return

    assert first["kind"] == policy_action.STOP
    assert "probe x must be an integer in 0..15" in \
        first["inputs"]["bridge_refusal"]["reason"]
    assert second == first


def test_the_closed_interpreter_never_calls_eval_exec_import_or_reflection():
    source = Path(ast_policy.__file__)
    text = source.read_text(encoding="utf-8")

    assert "eval(" not in text
    assert "exec(" not in text
    assert "__import__(" not in text
    assert "getattr(" not in text



@REQUIRES_BOUNDED_CHILD
def test_the_closed_interpreter_runs_inside_the_bounded_child():
    result = _run(_probe_then_commit_document())
    assert result["committed"] is True


def _return_stop():
    return _return_action(inputs={})


@pytest.mark.parametrize("document", [
    {"op": "block", "stmts": [
        {"op": "assign", "name": "x", "value": {"op": "const", "value": 1}}]},
    {"op": "assign", "name": "z", "value": {"op": "const", "value": 3}},
    {"op": "if", "cond": {"op": "const", "value": True},
     "then": _return_stop(),
     "else": {"op": "assign", "name": "y", "value": {"op": "const", "value": 2}}},
    {"op": "block", "stmts": [
        _return_stop(),
        {"op": "assign", "name": "z", "value": {"op": "const", "value": 1}}]},
])
def test_a_program_that_can_complete_without_an_action_is_refused_at_load(document):
    with pytest.raises(ast_policy._LoadRefused) as refusal:
        ast_policy.load_policy(
            _record({"policy_id": "no-return", "entry": document}),
            expected_policy_id="no-return")
    assert "$.policy_ast.entry" in str(refusal.value)


@pytest.mark.parametrize("document", [
    _return_stop(),
    {"op": "block", "stmts": [
        {"op": "assign", "name": "x", "value": {"op": "const", "value": 1}},
        _return_stop()]},
    {"op": "block", "stmts": [
        {"op": "assign", "name": "a", "value": {"op": "const", "value": 1}},
        {"op": "assign", "name": "b", "value": {"op": "const", "value": 2}},
        _return_stop()]},
])
def test_a_program_that_returns_on_every_path_still_loads(document):
    ast_policy.load_policy(
        _record({"policy_id": "returns", "entry": document}),
        expected_policy_id="returns")


def _inputs_program(expression):
    return _record({"policy_id": "typed-expr", "entry": {
        "op": "return_action", "kind": "stop", "target": "boolean.task",
        "inputs": {"op": "obj", "fields": {"v": expression}},
        "evidence_refs": [], "requested_resources": {},
        "state": {"op": "const", "value": {}}}})


def _add_of(left, right):
    return _add(_const(left), _const(right))


def _eq_of(left, right):
    return _eq(_const(left), _const(right))


@pytest.mark.parametrize("expression", [
    _add_of(True, 1), _add_of(False, True), _add_of(1, True),
    _add(_eq_of(1, 1), _const(1)),
    _add(_eq_of(1, 1), _eq_of(1, 1)),
])
def test_add_refuses_a_boolean_operand_because_bool_is_an_int_subclass(expression):
    with pytest.raises(ast_policy._LoadRefused) as refusal:
        ast_policy.load_policy(_inputs_program(expression),
                               expected_policy_id="typed-expr")
    assert "add requires two numeric operands" in str(refusal.value)


@pytest.mark.parametrize("expression", [
    _add_of(1, 1), _add_of(1.5, 1), _add_of(-3, 4),
])
def test_add_still_accepts_numeric_operands(expression):
    ast_policy.load_policy(_inputs_program(expression),
                           expected_policy_id="typed-expr")


@pytest.mark.parametrize("left,right", [
    (True, 1), (1, True), (False, 0), (0, False), ("1", 1),
])
def test_json_equality_does_not_cross_the_boolean_numeric_line(left, right):
    assert ast_policy._json_equal(left, right) is False


@pytest.mark.parametrize("left,right", [
    (True, True), (False, False), (1, 1), (1, 1.0), ([1, 2], [1, 2]),
    ({"a": 1}, {"a": 1}), (None, None),
])
def test_json_equality_agrees_within_a_type(left, right):
    assert ast_policy._json_equal(left, right) is True


def test_equality_of_reordered_sequences_is_false():
    assert ast_policy._json_equal([1, 2], [2, 1]) is False
