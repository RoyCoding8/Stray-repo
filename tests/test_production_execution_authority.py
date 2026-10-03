"""The production executor call sites name their authority.

Lane A2 made `method_exec.run_step_out_of_process` refuse without `dsn`,
`allocation_id` and `operation_id`, and wrote the test-side answer in
`tests/execution_authority.py`. Nothing checked the production side, so a
production path could keep calling it bare and read the resulting refusal
as a result. `experiments/ad01/s09_bound_use_proof.py` was one: its only
call named none of the three, so every entry point raised before a child
ran, and the module's subject — that the bound policy executes in a fresh
interpreter and its action governs — could not be measured at all.

The census here is over the production trees only (`experiments/`,
`scripts/`, `src/`), which is why `tests/execution_authority.py` and the
twelve test files that adopted it are not this file's subject. It reads
each call by AST, so a docstring that names the executor, the citation in
`s09_plan_claims.py`, and the definition in `method_exec.py` are not
counted as calls.

Two properties, both of which failed before this lane:

1. No production call to the executor is reached without authority. A call
   is clean when it names `dsn` and `allocation_id` and `operation_id`
   literally, or when it splats a mapping the surrounding code already
   guards. A site that splats unguarded is reported, because a splat can
   be empty and the guard that would stop it may not exist.

2. A production call that has no authority in scope says so by refusing
   before it stages anything, rather than executing against whatever store
   is visible. This is the property `s09_bound_use_proof.py` restored: it
   executes policy source, so it names an authority or it raises
   `PolicyNotProved`; it never reaches the executor bare.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_ROOTS = ("experiments", "scripts", "src")
EXECUTOR = "run_step_out_of_process"
AUTHORITY_KEYWORDS = ("dsn", "allocation_id", "operation_id")

# `experiments/ad01/s09_plan_claims.py` cites the executor by name and
# `method_exec.py` defines it; neither is a call. The census matches the
# callee by attribute or bare name, so a definition is not a `Call` node and
# a citation is a string constant, and neither can appear here.
CALLERS = {
    "experiments/ad01/construct.py",
    "experiments/ad01/experience_axis_run.py",
    "experiments/ad01/improve_channel.py",
    "experiments/ad01/learner.py",
    "experiments/ad01/policy_step.py",
    "experiments/ad01/s09_bound_use_proof.py",
    "experiments/ad01/s09_causal_proof.py",
    "experiments/ad01/s09_e2_scored.py",
}


def _python_files() -> list:
    return [path for root in PRODUCTION_ROOTS
            for path in sorted((ROOT / root).rglob("*.py"))]


def _executor_calls(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id \
            if isinstance(func, ast.Name) else ""
        if name == EXECUTOR:
            found.append(node)
    return found


def _caller_files() -> list:
    return [(path, _executor_calls(path)) for path in _python_files()
            if _executor_calls(path)]


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_the_census_is_a_census_and_not_a_grep():
    """The walk reached the production trees and found the known callers.

    A census that returns nothing would satisfy "no call is bare" while
    proving nothing, so this pins the file count high enough to show the
    walk ran and the caller set high enough to show it found the sites.
    """
    files = _python_files()
    callers = {path for path, _ in _caller_files()}

    assert len(files) > 400, "the production walk reached only %d files" % len(files)
    assert callers == {
        ROOT / name for name in CALLERS}, (
        "the caller set changed; a new caller needs classifying and a "
        "removed caller needs its record corrected. found: %s"
        % sorted(_relative(p) for p in callers))


def test_no_production_call_executes_with_no_authority():
    """Every production call names all three measures or guards the splat.

    The three conditional sites (`learner`, `experience_axis_run`,
    `s09_causal_proof`) splat a mapping they built only when the store is
    present, and each raises its own named refusal when it is not. They are
    reported here as guarded, and the reason is recorded rather than
    assumed: a splat with no guard would be indistinguishable from a
    guarded one to a name check, so the guard is the thing being pinned.
    """
    bare = []
    for path, calls in _caller_files():
        for call in calls:
            keywords = {keyword.arg for keyword in call.keywords}
            missing = [k for k in AUTHORITY_KEYWORDS if k not in keywords]
            if not missing:
                continue
            if any(keyword.arg is None for keyword in call.keywords):
                continue  # guarded splat, asserted by name below
            bare.append("%s:%d missing %s"
                        % (_relative(path), call.lineno, ",".join(missing)))

    assert bare == [], (
        "a production call to %s names no authority: %s"
        % (EXECUTOR, "; ".join(bare)))


def test_the_conditional_production_callers_refuse_before_executing():
    """The three guarded splats are guarded, not merely hoping for a store.

    Each builds its authority only from a store the caller named, and each
    raises by name before the executor is reached when the caller named
    none. The distinction matters because an unguarded splat sends an empty
    mapping, and the refusal the executor then raises is indistinguishable
    from a refusal the caller intended.
    """
    from experiments.ad01 import learner
    from experiments.ad01 import s09_causal_proof

    run = s09_causal_proof.PolicyRun(
        policy_source="def STEP(view, state):\n    return view, state\n",
        view={"task_content": {"task_id": "t"}, "observations": [],
              "open_questions": [], "last_result": None,
              "eligible_methods": [],
              "remaining": {"steps": 1, "queries": 1}},
        state={}, entry="STEP", dsn=None, allocation_id=None)

    assert s09_causal_proof._authority(run) == {}

    named = s09_causal_proof.PolicyRun(
        policy_source=run.policy_source, view=run.view, state={},
        entry="STEP", dsn="postgresql:///named", allocation_id="alloc-1")
    authority = s09_causal_proof._authority(named)

    assert authority["dsn"] == "postgresql:///named"
    assert authority["allocation_id"] == "alloc-1"
    assert authority["operation_id"].startswith("qualify-pre-launch-")

    with pytest.raises(learner.TreatmentRefused, match="durable store"):
        learner._action_of(
            "def STEP(view, state):\n    return {}\n", {}, [],
            authority=None)


def test_the_experience_axis_authority_is_empty_without_a_store():
    """The third guarded splat builds nothing when no store is named.

    `experience_axis_run` keeps the same shape as the other two, and it is
    the one whose empty mapping reaches the executor most quietly, because
    what it builds is a study arm rather than a refusal subject.
    """
    import inspect

    from experiments.ad01 import experience_axis_run

    signature = inspect.signature(experience_axis_run._step_policy)

    assert {"dsn", "allocation_id"} <= set(signature.parameters)
    assert signature.parameters["dsn"].default is None
    assert signature.parameters["allocation_id"].default is None


def test_the_bound_use_proof_refuses_without_authority_rather_than_executing():
    """The repaired proof executes policy source, so it names a store.

    Before this lane the same call reached the executor bare and raised
    there. The consequence is the same refusal either way, but the subject
    differs: this module proves that the bound policy runs in a fresh
    interpreter, so a refusal inside it is a missing argument rather than a
    demonstrated refusal.
    """
    from experiments.ad01 import s09_bound_use_proof as proof

    binding = proof.PolicyBinding_(
        source=proof.seed_policy_source(proof.BASELINE_METHOD),
        recorded_digest=proof.sha256_of(
            proof.seed_policy_source(proof.BASELINE_METHOD)),
        origin="fixture-stand-in")

    with pytest.raises(proof.PolicyNotProved, match="needs a store"):
        proof.execute_bound_policy(binding, {}, {})

    with pytest.raises(proof.PolicyNotProved, match="needs a store"):
        proof.execute_bound_policy(
            binding, {}, {}, authority={"dsn": "postgresql:///nowhere"},
            operation_id="op-1")

    with pytest.raises(proof.PolicyNotProved, match="needs a store"):
        proof.admitted_actions(binding, {})

    with pytest.raises(proof.PolicyNotProved, match="needs a store"):
        proof.substitute(proof.SEED_POLICY_SOURCE % proof.BASELINE_METHOD,
                         proof.SEED_POLICY_SOURCE % proof.SUBSTITUTE_METHOD)


def test_the_operation_identity_distinguishes_the_steps_it_names():
    """A step sequence is not one execution.

    Under a single identity the second step reads back the first step's
    settled receipt and reports the first step's action, which would read
    as a policy that stopped advancing when nothing ran twice.
    """
    from experiments.ad01 import s09_bound_use_proof as proof

    source = proof.seed_policy_source(proof.BASELINE_METHOD)
    binding = proof.PolicyBinding_(
        source=source, recorded_digest=proof.sha256_of(source),
        origin="fixture-stand-in")
    view = {"task_content": {"task_id": "t"}}

    first = proof._operation_id(binding, view, "step0")
    second = proof._operation_id(binding, view, "step1")
    report = proof._operation_id(binding, view, "report")

    assert len({first, second, report}) == 3
    assert proof._operation_id(binding, view, "step0") == first
    assert proof._operation_id(binding, {"task_content": {"task_id": "u"}},
                               "step0") != first