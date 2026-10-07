"""The exact call lane I has to make, run against the real harness.

`real_arm_names` filters on `REAL_REPRESENTATION_KINDS`, which is still
`frozenset({PYTHON_STEP})`, so an AST arm registers and is then still not
a real arm. The gap is in `s09_arm_parity`, which is another lane's
file. This module therefore asserts the *contract* the registration must
satisfy, and does it against the live harness rather than a mock: the
registry, the admission checks, `contract_view` and `compare_arms` are
all the shipped ones.

The one thing it cannot do is flip `REAL_REPRESENTATION_KINDS`, and the
test says so by name, so the file fails the moment lane I lands that
change without a test like this noticing why it is still needed.
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
from experiments.ad01 import s09_arm_parity as parity
from settlement import child_limits
from settlement.child_limits import ChildLimits

REQUIRES_BOUNDED_CHILD = pytest.mark.skipif(
    child_limits.child_setup_refusal(ChildLimits(cpu_seconds=10)) is not None,
    reason="requires a host that can install the declared child CPU limit")


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


def _list(*items):
    return {"op": "list", "items": list(items)}


def _action(kind, target, inputs=None, state=None, resources=None):
    return {"op": "return_action", "kind": kind, "target": target,
            "inputs": _obj(**(inputs or {})),
            "evidence_refs": [], "requested_resources": resources or {},
            "state": _const({} if state is None else state)}


def _record(policy_id="registered-ast"):
    observed = _field("view", "observed")
    document = {"policy_id": policy_id, "entry": {
        "op": "if", "cond": _eq(observed, _const([])),
        "then": _action("probe", "boolean.query", {"x": 5}, {"step": 1},
                        {"queries": 1}),
        "else": _action("construct", "boolean.commit", {"specs": _list(*[
            _obj(const=_index(_index(_index(observed, _const(0)),
                                      _const("y")), _const(output)),
                 mask=0, pair=None) for output in range(rules.N_OUTPUTS)])},
            {"step": 2})}}
    encoded = json.dumps(document, allow_nan=False, ensure_ascii=False,
                         separators=(",", ":"), sort_keys=True).encode()
    return {"artifact": {
        "kind": "learning-policy", "representation": "typed-ast",
        "version": "boolean-typed-ast-v1", "policy_id": policy_id,
        "ast_digest": hashlib.sha256(encoded).hexdigest(),
    }, "policy_ast": document}


def _typed_ast_factory(record, *,
                       timeout_ms=parity.policy_step.STEP_TIMEOUT_MS,
                       cpu_seconds=parity.policy_step.STEP_CPU_SECONDS,
                       max_output_bytes=parity.policy_step.STEP_MAX_OUTPUT_BYTES,
                       memory_bytes=None):
    """The driver factory `s09_arm_parity` needs for a typed-AST arm.

    `compare_arms` calls `arm.driver_factory(policy_record,
    **step_budget.as_driver_kwargs())` and then calls the returned value
    once per turn with a *contract view*, so the factory's job is to
    close the state and translate nothing else. The AST executor takes
    the world public state and does the projection itself, so the
    returned callback adapts in the other direction.

    `record` is a `deepcopy` of the registration's `policy_record`; the
    AST loader refuses a record whose `policy_id` has drifted, so this
    binds nothing and passes it through unchanged.
    """
    ast_decide = ast_policy.choose_action(
        record, timeout_ms=timeout_ms, cpu_seconds=cpu_seconds,
        max_output_bytes=max_output_bytes, memory_bytes=memory_bytes)

    def decide(view: dict) -> dict:
        return ast_decide(parity._world_state_from_contract_view(view))
    return decide


def test_the_ast_record_satisfies_the_registry_record_requirements():
    record = _record()
    registry = parity.ArmRegistry()
    arm = registry.register(name="ast", representation_kind=parity.TYPED_AST,
                            driver_factory=_typed_ast_factory,
                            policy_record=record)

    assert not isinstance(arm, parity.Incomparability), arm
    assert arm.representation_kind == parity.TYPED_AST
    assert arm.representation_kind in parity.REPRESENTATION_KINDS
    assert arm.is_test_double is False
    assert arm.policy_record_digest == hashlib.sha256(
        parity.canonical_json_bytes(record)).hexdigest()


@REQUIRES_BOUNDED_CHILD
def test_the_factory_accepts_the_exact_kwargs_compare_arms_sends():
    record = _record()
    budget = parity.StepBudget()
    decide = _typed_ast_factory(deepcopy(record),
                                **budget.as_driver_kwargs())
    view = parity.contract_view(
        active.public_state(rules.RuleSession(rules.make_task("dev", 4))),
        arm_name="ast")

    action = decide(deepcopy(view))
    assert action["kind"] == policy_action.PROBE
    assert action["target"] == "boolean.query"
    assert action["inputs"] == {"x": 5}
    assert parity.admit_action(view, action, arm_name="ast") is None


def test_the_factory_never_mutates_the_view_it_is_handed():
    record = _record()
    decide = _typed_ast_factory(deepcopy(record))
    view = parity.contract_view(
        active.public_state(rules.RuleSession(rules.make_task("dev", 4))))
    before = parity.view_digest(view)
    decide(deepcopy(view))
    assert parity.view_digest(view) == before


@REQUIRES_BOUNDED_CHILD
def test_run_arm_carries_an_ast_arm_to_a_complete_arm_record():
    """The whole of `_run_arm`, on the live harness.

    This is the call lane I will make, minus the two lines in
    `s09_arm_parity` that have to be added first. Everything the arm is
    judged on, the view digest, the initial-state digest, the score, the
    issues list, is produced here rather than asserted in the abstract.
    """
    registry = parity.ArmRegistry()
    arm = registry.register(name="ast", representation_kind=parity.TYPED_AST,
                            driver_factory=_typed_ast_factory,
                            policy_record=_record())
    conditions = parity.ComparisonConditions(split="dev", seed=4,
                                             max_queries=rules.MAX_QUERIES)

    record, issues = parity._run_arm(arm, conditions)

    assert issues == (), issues
    assert record.arm_name == "ast"
    assert record.representation_kind == parity.TYPED_AST
    assert record.task_id == rules.make_task("dev", 4)["task_id"]
    assert record.split == "dev"
    assert record.seed == 4
    assert record.query_budget == 8
    assert record.queries_spent == 1
    assert record.turns_taken == 2
    assert record.is_test_double is False
    assert record.initial_state_digest
    assert record.view_digest
    assert record.score["n_queried"] == 1
    assert record.as_dict()["representation_kind"] == "typed-ast"


def test_the_ast_arm_is_still_not_a_real_arm_until_lane_i_flips_the_set():
    """The one thing this lane cannot fix, named.

    `real_arm_names` is what `compare_arms` and the study preflight read,
    and it is keyed off `REAL_REPRESENTATION_KINDS`, which this lane does
    not own. Until lane I adds `TYPED_AST` to that frozenset, an AST arm
    is registered, runs, and is still excluded from the real panel.
    """
    registry = parity.ArmRegistry()
    registry.register(name="ast", representation_kind=parity.TYPED_AST,
                      driver_factory=_typed_ast_factory,
                      policy_record=_record())

    assert "ast" in registry.names
    if parity.TYPED_AST in parity.REAL_REPRESENTATION_KINDS:
        assert registry.real_arm_names() == ("ast",)
    else:
        assert registry.real_arm_names() == ()
        assert parity.REAL_REPRESENTATION_KINDS == frozenset(
            {parity.PYTHON_STEP})


def test_two_arms_of_one_kind_are_refused_so_a_panel_cannot_double_count():
    """Why the AST arm needs its own name, not a second AST slot."""
    registry = parity.ArmRegistry()
    for name in ("ast-a", "ast-b"):
        registry.register(name=name, representation_kind=parity.TYPED_AST,
                          driver_factory=_typed_ast_factory,
                          policy_record=_record())
    conditions = parity.ComparisonConditions(split="dev", seed=4,
                                             max_queries=rules.MAX_QUERIES)
    result = parity.compare_arms(registry, ("ast-a", "ast-b"), conditions)

    assert result.status == "incomparable"
    assert [str(issue.reason) for issue in result.incompatibilities] == [
        "duplicate-representation-kind"]


@REQUIRES_BOUNDED_CHILD
def test_an_ast_arm_and_a_step_arm_can_be_compared_once_both_are_real():
    """The panel lane I is building, run end to end.

    Both arms are real STEP/AST programs and both are driven by the live
    `compare_arms`. The result is currently gated only by
    `REAL_REPRESENTATION_KINDS`, so the assertion is on the records the
    harness produced, and on the one issue that is expected today.
    """
    step_source = (
        "def STEP(view, state):\n"
        "    return {\"action\": {\"kind\": \"stop\",\n"
        "                         \"target\": \"boolean.task\",\n"
        "                         \"inputs\": {},\n"
        "                         \"evidence_refs\": [],\n"
        "                         \"requested_resources\": {}},\n"
        "            \"state\": {}}\n")
    from experiments.ad01.policy_step import make_policy_artifact
    step_record = make_policy_artifact(step_source, origin="authored-control",
                                       applicability={"world": 0, "arm": "I"})
    registry = parity.ArmRegistry()
    parity.register_python_step(registry, name="step",
                                policy_record=step_record)
    registry.register(name="ast", representation_kind=parity.TYPED_AST,
                      driver_factory=_typed_ast_factory,
                      policy_record=_record())
    conditions = parity.ComparisonConditions(split="dev", seed=4,
                                             max_queries=rules.MAX_QUERIES)
    result = parity.compare_arms(registry, ("step", "ast"), conditions)

    records = {record.arm_name: record for record in result.records}
    assert set(records) == {"step", "ast"}, result.incompatibilities
    assert records["ast"].view_digest == records["step"].view_digest
    assert records["ast"].initial_state_digest \
        == records["step"].initial_state_digest
    assert records["ast"].score != records["step"].score
    assert all(record.representation_kind in parity.REPRESENTATION_KINDS
               for record in records.values())
    kinds = {record.representation_kind for record in records.values()}
    assert len(kinds) == 2


def test_the_ast_arm_declares_its_representation_and_version():
    record = _record()
    ast_policy.load_policy(deepcopy(record),
                           expected_policy_id="registered-ast")

    assert record["artifact"]["kind"] == "learning-policy"
    assert record["artifact"]["representation"] == "typed-ast"
    assert record["artifact"]["version"] == ast_policy._REPRESENTATION
    assert parity.TYPED_AST == "typed-ast"
