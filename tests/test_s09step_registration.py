"""What lane I must call to register STEP as a real arm, and what it costs.

CS-03 says the representation comparison is not yet the common comparison
because only one representation is real. The AST and graph executors exist.
This file does not register them and does not edit the registry; it pins the
STEP side of the seam so the wiring has something exact to call, and it pins
the two ways the wiring can go wrong without looking wrong.

The one that matters: registration does not validate the policy record. A
record of the wrong shape registers, runs, and reports a scored arm that
never executed a policy. Every record here is built by `make_policy_artifact`
so a refusal surfaces at registration rather than three comparisons later.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import policy_step
from experiments.ad01 import policy_action
from experiments.ad01 import s09_arm_parity as parity
from settlement import child_limits
from settlement.child_limits import ChildLimits

REQUIRES_BOUNDED_CHILD = pytest.mark.skipif(
    child_limits.child_setup_refusal(ChildLimits(cpu_seconds=10)) is not None,
    reason="requires a host that can install the declared child CPU limit")


# Probes x=0, then commits the truth table it read at that input. The query
# sequence and the score are what the world produced, not what this file wants.
PROBE_THEN_COMMIT = '''def STEP(view, state):
    observed = view["observed"]
    if not observed:
        action = {"kind": "probe", "target": "boolean.query",
                  "inputs": {"x": 0}, "evidence_refs": [],
                  "requested_resources": {"queries": 1}}
    else:
        y = observed[-1]["y"]
        action = {"kind": "construct", "target": "boolean.commit",
                  "inputs": {"specs": [{"const": bit, "mask": 0, "pair": None}
                                       for bit in y]},
                  "evidence_refs": [], "requested_resources": {}}
    return {"action": action, "state": {"seen": len(observed)}}
'''


def _record(source: str = PROBE_THEN_COMMIT) -> dict:
    return policy_step.make_policy_artifact(
        source, origin="authored-control", instruments=["boolean-rule-v1"])


def _stopping_driver(_record, **_budget):
    return lambda _view: {
        "kind": "stop", "target": "boolean.task", "inputs": {},
        "evidence_refs": [], "requested_resources": {}}


def _conditions() -> parity.ComparisonConditions:
    return parity.ComparisonConditions(split="dev", seed=4, max_queries=8)


def test_registering_a_step_arm_returns_the_registration_lane_i_needs():
    """The call, and everything it hands back.

    `register_python_step(registry, *, name, policy_record)` takes the
    registry, a name and a record from `policy_step.make_policy_artifact`. It
    returns an `ArmRegistration` on success, an `Incomparability` on refusal,
    and the caller must check which. On success the registration carries the
    representation kind, the driver factory the harness will call, its own
    copy of the record, and `is_test_double=False`.
    """
    registry = parity.ArmRegistry()
    outcome = parity.register_python_step(
        registry, name="step-real", policy_record=_record())

    assert isinstance(outcome, parity.ArmRegistration)
    assert outcome.name == "step-real"
    assert outcome.representation_kind == parity.PYTHON_STEP
    assert outcome.is_test_double is False
    assert callable(outcome.driver_factory)
    assert outcome.policy_record == _record()
    assert outcome.policy_record is not _record()
    assert outcome.policy_record_digest
    assert registry.names == ("step-real",)
    assert registry.real_arm_names() == ("step-real",)


@REQUIRES_BOUNDED_CHILD
def test_the_registered_step_arm_runs_the_world_and_is_graded_for_real():
    """End to end through the harness, against a registered double.

    The STEP arm spends a query and commits a predictor, so its record
    carries a real score and a real query count. The double stops
    immediately. Both are `comparable`, which is the shape lane I needs for
    the third arm to slot into.
    """
    registry = parity.ArmRegistry()
    step_arm = parity.register_python_step(
        registry, name="step-real", policy_record=_record())
    assert isinstance(step_arm, parity.ArmRegistration)
    registry.register(
        name="ast-double", representation_kind=parity.TYPED_AST,
        driver_factory=_stopping_driver, policy_record={"source": "x"},
        is_test_double=True)

    result = parity.compare_arms(
        registry, ("step-real", "ast-double"), _conditions())

    assert result.status == "comparable"
    assert result.incompatibilities == ()
    step_record, double_record = result.records
    assert step_record.representation_kind == parity.PYTHON_STEP
    assert step_record.is_test_double is False
    assert step_record.queries_spent == 1
    assert step_record.turns_taken == 2
    assert step_record.score == {
        "overall": 0.0625, "queried": 1.0, "unqueried": 0.0, "n_queried": 1}
    assert step_record.step_budget == parity.StepBudget()
    assert step_record.query_budget == 8
    assert double_record.queries_spent == 0
    assert double_record.score is None


def test_registration_does_not_validate_the_record_it_is_given():
    """Finding: a malformed record registers and then reports a scored arm.

    `ArmRegistry.register` checks only that the record is a dict, so
    `{"source": "unused"}` passes. The failure surfaces when the driver runs,
    and the bridge turns it into a recorded refusal stop. The arm is then
    reported as `comparable`, non-test-double, with a trace and a turn count,
    exactly as a working arm is. Nothing in the record marks it as having
    executed no policy.

    This is why the record must come from `make_policy_artifact` and why
    `verify_policy_record` runs inside the driver rather than at registration.
    Lane I should not rely on registration to catch a bad record.
    """
    registry = parity.ArmRegistry()
    outcome = parity.register_python_step(
        registry, name="junk", policy_record={"source": "unused"})

    assert isinstance(outcome, parity.ArmRegistration)
    assert outcome.is_test_double is False

    registry.register(
        name="ast-double", representation_kind=parity.TYPED_AST,
        driver_factory=_stopping_driver, policy_record={"source": "x"},
        is_test_double=True)
    result = parity.compare_arms(
        registry, ("junk", "ast-double"), _conditions())

    assert result.status == "comparable"
    junk = result.records[0]
    assert junk.arm_name == "junk"
    assert junk.representation_kind == parity.PYTHON_STEP
    assert junk.is_test_double is False
    assert junk.turns_taken == 1
    assert junk.queries_spent == 0
    assert junk.score is None

    from experiments.ad01 import boolean_active as active
    from experiments.ad01 import boolean_policy
    public_state = active.public_state(
        active.rules.RuleSession(active.rules.make_task("dev", 4)))
    decision = boolean_policy.choose_action({"source": "unused"})(public_state)
    assert decision["kind"] == "stop"
    assert decision["inputs"]["bridge_refusal"]["reason"] == \
        "policy record needs artifact plus source bytes"


@REQUIRES_BOUNDED_CHILD
def test_the_driver_factory_takes_the_record_and_the_step_budget_as_keywords():
    """The harness's call site, so the seam is pinned from both ends.

    `_run_arm` invokes `driver_factory(policy_record, **step_budget_kwargs)`.
    The factory returns a `decide(view)` callable which is handed the shared
    contract view and must return a shared contract action. The budget
    defaults to the three `policy_step` constants with no memory limit.
    """
    factory = parity._python_step_factory
    decide = factory(_record(), **parity.StepBudget().as_driver_kwargs())

    assert callable(decide)
    assert parity.StepBudget().as_driver_kwargs() == {
        "timeout_ms": policy_step.STEP_TIMEOUT_MS,
        "cpu_seconds": policy_step.STEP_CPU_SECONDS,
        "max_output_bytes": policy_step.STEP_MAX_OUTPUT_BYTES,
        "memory_bytes": None}

    from experiments.ad01 import boolean_active as active
    session = active.rules.RuleSession(active.rules.make_task("dev", 4))
    view = parity.contract_view(active.public_state(session))
    action = decide(view)

    assert action == {
        "kind": "probe", "target": "boolean.query", "inputs": {"x": 0},
        "evidence_refs": [], "requested_resources": {"queries": 1}}
    assert parity.admit_action(view, action) is None


def test_a_step_action_naming_the_step_abi_vocabulary_is_refused_by_the_arm():
    """The one thing lane I must not do when authoring a STEP arm.

    A policy written against `policy_step.ACTION_KINDS` is refused at the
    action boundary with `unknown action kind`, on every kind except `stop`,
    which the two vocabularies happen to share. The arm's usable vocabulary
    is the Boolean schema's: `probe`, `construct`, `stop`.
    """
    from experiments.ad01 import boolean_active as active
    from experiments.ad01 import boolean_policy

    public_state = active.public_state(
        active.rules.RuleSession(active.rules.make_task("dev", 4)))
    for step_kind in policy_step.ACTION_KINDS:
        payload = {"kind": step_kind, "target": "boolean.query",
                   "inputs": {}, "evidence_refs": [],
                   "requested_resources": {}}
        if step_kind == "stop":
            action = policy_action.parse_action(payload)
            with pytest.raises(policy_action.ActionRefused,
                               match="stop target must be boolean.task"):
                boolean_policy._validate_boolean_action(action, public_state)
        else:
            with pytest.raises(policy_action.ActionRefused,
                               match="unknown action kind"):
                policy_action.parse_action(payload)
