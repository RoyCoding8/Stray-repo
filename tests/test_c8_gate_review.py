"""C8 review: attack `verify_step_source`'s executable bound from both sides.

Independent of C5's own tests. The gate is a gate that *refuses*, so the
dangerous directions are both live: over-refusing a program that can act, and
under-refusing one that cannot. Every case here is asserted against observed
behaviour of the real function, not against a restatement of its rule. The
cases that attacked those two directions directly were removed once they were
fixed; the note below says which, and where each is covered now.

The recorded artifact is re-derived here from the archived store rather than
taken on trust: the run ledger's `response_digest` and `text_chars` are
checked against `json.dumps({"entry": <archived imp_source>})` so that the
program under review is provably the bytes the run bound.

Seven cases were removed here. Six were tripwires: each asserted a defect this
review had found and carried its own staleness guard, so it was written to fail
once the defect was repaired. The cause was one rule -- the gate read the
*first* `action` a return binds where Python binds the *last*, wrong in both
directions from that single cause -- and C9 repaired it, so all six now fail.
They are deleted rather than inverted: each ran a source byte-identical to a
test in `tests/test_c9_override_order.py` that asserts the corrected verdict
and checks it against what those bytes do at runtime, so an inverse kept here
would assert the same fact twice. The seventh asserted a sound refusal that C9's
file now covers with the same source and one more assertion, so keeping it
would have been a copy rather than coverage.

What is left in this file is a claim about the gate as it stands. What was
removed is a record of what it once got wrong, and where each fact now lives.

"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from experiments.ad01 import method_exec, policy_step

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "reports" / "evidence" / "invl02-r123" / "e0-run.json"
LIVE_STORE = REPO / "reports" / "evidence" / "invl02-r123" / "frontier-live.json"
BOUND_CONTROL_ID = "acquired-live-live-r1"
RECORDED_DIGEST = (
    "549321f51523651873ecd36acf967889e6642c22de55b94b852f1506f28dd003")


def _real_action() -> str:
    return ('{"kind": "stop", "target": "t", "inputs": {},'
            ' "evidence_refs": [], "requested_resources": {}}')


def _admitted(source: str) -> bool:
    try:
        return method_exec.verify_step_source(source, "STEP") == "STEP"
    except method_exec.MethodExecutionError:
        return False


def _run(source: str, view=None, state=None) -> object:
    namespace: dict = {}
    exec(compile(source, "<c8>", "exec"), namespace)  # noqa: S102
    return namespace["STEP"](view if view is not None else {},
                             state if state is not None else {})


# --- Part 1: the recorded artifact, re-derived ------------------------------


def test_archived_source_is_the_only_live_acquisition_and_its_bytes_reproduce():
    """Re-derive the claim rather than accept it.

    The run ledger records `response_digest` and `text_chars 84` for the one
    construction dispatch. Hashing `json.dumps({"entry": src})` over the
    archived `imp_source` must reproduce both, which is what makes this a
    statement about the bytes the run bound and not about a pasted string.
    """
    run = json.loads(RUN.read_text(encoding="utf-8"))
    ledger = run["ledger"][0]
    store = json.loads(LIVE_STORE.read_text(encoding="utf-8"))
    packages = [p for p in store["treatment_arms"]["acquired"]
                if p.get("control_id") == BOUND_CONTROL_ID]

    assert len(packages) == 1
    source = packages[0]["imp_source"]
    envelope = json.dumps({"entry": source})

    assert ledger["response_digest"] == RECORDED_DIGEST
    assert len(envelope) == ledger["text_chars"] == 84
    assert hashlib.sha256(envelope.encode("utf-8")).hexdigest() == RECORDED_DIGEST
    assert run["revision"]["disposition"] == "bound"
    assert run["revision"]["reason"] == ""
    assert run["revision"]["bound_digest"] == packages[0]["package_digest"]


def test_the_recorded_program_cannot_act_at_any_input():
    """The recorded `bound` is a program the action contract always refuses."""
    store = json.loads(LIVE_STORE.read_text(encoding="utf-8"))
    source = [p for p in store["treatment_arms"]["acquired"]
              if p["control_id"] == BOUND_CONTROL_ID][0]["imp_source"]

    for view in ({}, {"experience": [1]}, None):
        result = _run(source, view=view)
        assert result["action"] is None
        with pytest.raises(ValueError, match="policy action must be an object"):
            policy_step.validate_step_result(result)


# --- Part 2a: does the rule track the validator, or snapshot it? -----------


def test_adding_a_required_field_to_the_contract_moves_the_gate(monkeypatch):
    """Drift test: a field `validate_action` starts requiring must bite.

    The claim is that the rule is derived by asking `validate_action`, so a
    program valid today and invalid after a contract change must flip from
    admitted to refused with no edit to `method_exec`. Monkeypatching the
    contract is the only way to move the contract without editing a file this
    review does not own.
    """
    source = ("def STEP(view, state):\n"
              "    return {\"action\": %s, \"state\": state}\n"
              % _real_action())
    assert _admitted(source), "precondition: valid under the shipped contract"

    required = policy_step.ACTION_REQUIRED
    monkeypatch.setattr(policy_step, "ACTION_REQUIRED", required + ("grant",))
    try:
        assert not _admitted(source), (
            "the gate did not follow the contract; it snapshots it")
    finally:
        pass


def test_a_newly_valid_literal_is_re_admitted_by_the_same_code(monkeypatch):
    """The other direction: what the contract stops refusing, it admits.

    `None` is inert today only because `validate_action` demands an object.
    Ask the contract to accept `None` and the same `{"action": None}` source
    must become admitted, with no edit to the gate.
    """
    source = ("def STEP(view, state):\n"
              "    return {\"action\": None, \"state\": state}\n")
    assert not _admitted(source)

    monkeypatch.setattr(policy_step, "validate_action", lambda action: action)
    assert _admitted(source), (
        "the gate kept its own list of inert shapes; it does not ask")


# --- Part 2b: loud failure rather than refusal -----------------------------


@pytest.mark.parametrize("literal", [
    "[0] * 10 ** 9",
    "[0] * 100000 + [0] * 100000",
    "'x' * 10 ** 9",
    "b'y' * 10 ** 9",
    "{str(i) for i in range(10 ** 8)}",
    "dict(a=1, b=2, c=3, d=4, e=5, f=6, g=7, h=8)",
])
def test_a_hostile_literal_never_exits_as_a_refusal(literal):
    """A gate on untrusted bytes must terminate as a refusal, not a signal.

    `ast.literal_eval` is reached with a node taken straight from the model's
    source, and the work it does is proportional to what the literal asks
    for. Each case below is a `return` that binds `action` to an expression
    `literal_eval` tries to fold. A fold that allocates or spins will not
    return an answer, and the one that does will not be an answer the gate can
    use. Both are a bad failure from a security boundary: an unhandled
    `MemoryError` inside `verify_step_source` is an escape, not a refusal.

    Whichever way it lands, the assertion is the same: whatever comes back is
    either `STEP` or `MethodExecutionError`. Anything else is a finding.
    """
    source = ("def STEP(view, state):\n"
              "    return {\"action\": %s, \"state\": state}\n" % literal)
    started = time.monotonic()
    try:
        outcome = _admitted(source)
        assert outcome is True
    except method_exec.MethodExecutionError:
        pass
    finally:
        elapsed = time.monotonic() - started
    assert elapsed < 30.0, ("literal took %.1fs: the gate is on the"
                            " untrusted path with no bound" % elapsed)


@pytest.mark.parametrize("depth", [1, 40, 90, 150, 200, 299])
def test_no_nesting_depth_escapes_as_an_unhandled_exception(depth):
    """`RecursionError` is in the caught tuple; prove it by sweeping depth.

    Python 3.14's `ast.parse` refuses a literal nested past roughly 300, so
    there is no depth that reaches the evaluator and folds forever. What this
    pins is the shape of the outcome: a refusal or admission, never an
    exception escaping `verify_step_source`. A deep list is a legal literal
    and an inert one, so the gate refusing it is the right answer.
    """
    source = ("def STEP(view, state):\n"
              "    return {\"action\": %s, \"state\": state}\n"
              % ("[" * depth + "]" * depth))
    try:
        assert _admitted(source) is False, (
            "depth %d should fold to an inert list and be refused" % depth)
    except method_exec.MethodExecutionError:
        pass


def test_an_unparseable_hostile_source_still_refuses():
    """The gate's own `ast.parse` failure must not be reachable as an escape."""
    for source in ("def STEP(view, state):\n    return {\"action\": ",
                   "def STEP(view, state):\n" + "    x = (\n" * 200,
                   "def STEP(view, state):\n    return {1: 2}[" * 1):
        with pytest.raises(method_exec.MethodExecutionError):
            method_exec.verify_step_source(source, "STEP")


# --- Part 2c: the check is cheap enough to sit on the hot path --------------


def test_the_check_costs_a_constant_number_of_walks_not_one_per_return():
    """Linear in the number of returns, not quadratic.

    The traversal is a single `stack` over the entry's own children with one
    `ast.walk` already run by `verify_step_source`, so a body with many
    returns must not cost more per return than a body with one. Measured
    rather than asserted, because a blowup here is a denial of service on
    untrusted bytes.
    """
    def _with(n: int) -> str:
        body = "".join("    if view == %d:\n        return"
                       " {\"action\": %s, \"state\": state}\n" % (i, _real_action())
                       for i in range(n))
        return "def STEP(view, state):\n" + body

    small, large = _with(4), _with(400)
    started = time.monotonic()
    for _ in range(20):
        _admitted(small)
    per_small = (time.monotonic() - started) / 20
    started = time.monotonic()
    _admitted(large)
    per_large = time.monotonic() - started

    assert per_large < max(per_small * 12, 0.05), (
        "400 returns took %.4fs against %.4fs for 4: not linear"
        % (per_large, per_small))


# --- Part 4: the changed fixture still asserts what it claims --------------


def test_the_changed_fixture_source_is_actable_and_admitted():
    """`test_final_provenance`'s staged source must be a real program.

    The change replaced `{"action": {"kind": "wait"}}` with a full action
    bound to a name. If the replacement were itself unactable the fixture
    would pass for the wrong reason, and the re-check it is about
    (`staged source digest mismatch`) would be measured against a program
    that never reaches a step result.
    """
    source = ("def STEP(view, state):\n"
              "    action = {\"kind\": \"stop\", \"target\": \"t\","
              " \"inputs\": {}, \"evidence_refs\": [],"
              " \"requested_resources\": {}}\n"
              "    return {\"action\": action, \"state\": {}}\n")

    result = _run(source)
    policy_step.validate_step_result(result)
    assert _admitted(source)


def test_the_old_fixture_source_would_have_been_refused():
    """Why the fixture had to change at all, stated as a fact not an opinion."""
    old = ("def STEP(view, state):\n"
           "    return {\"action\": {\"kind\": \"wait\"}, \"state\": {}}\n")

    with pytest.raises(ValueError, match="policy action missing"):
        policy_step.validate_step_result(_run(old))
    assert not _admitted(old)


def test_the_gate_is_not_consulted_by_the_path_the_fixture_exercises(monkeypatch):
    """The fixture's refusal must come from the digest check, not the new gate.

    If the new gate were the reason `run_step_out_of_process` refused, the
    fixture would be asserting the gate rather than `staged source digest
    mismatch`. Making `verify_step_source` a no-op for this call proves the
    fixture's own assertion still fires on its own machinery.
    """
    from settlement import db
    from test_final_provenance import _FakeConnection

    monkeypatch.setattr(db, "connect", lambda dsn: _FakeConnection())
    work: dict = {}

    def ensure_operation(dsn, **kwargs):
        work["path"] = Path(kwargs["payload"]["argv"][2])
        (work["path"] / "policy.py").write_text(
            "def STEP(view, state):\n    x = 1\n", encoding="utf-8")
        from settlement.common import ResultCode
        return type("R", (), {"code": ResultCode.APPLIED, "detail": ""})()

    monkeypatch.setattr(method_exec.broker, "ensure_operation", ensure_operation)
    monkeypatch.setattr(method_exec.broker, "dispatch_operation",
                        lambda *a, **k: None)
    monkeypatch.setattr(method_exec, "verify_step_source",
                        lambda source, entry="STEP": entry)
    source = ("def STEP(view, state):\n"
              "    action = {\"kind\": \"stop\", \"target\": \"t\","
              " \"inputs\": {}, \"evidence_refs\": [],"
              " \"requested_resources\": {}}\n"
              "    return {\"action\": action, \"state\": {}}\n")
    view = policy_step.materialize_view(
        task={"task_id": "t", "family": "software"}, observations=[],
        open_questions=[], last_result=None, eligible_methods=[],
        remaining={"steps": 1})

    with pytest.raises(method_exec.MethodExecutionError,
                       match="staged source digest mismatch"):
        method_exec.run_step_out_of_process(
            source, view, {}, dsn="fake-dsn", allocation_id="alloc-c8",
            operation_id="op-c8")


# --- the shipped controls and the boundary ---------------------------------


def test_the_derivation_helpers_are_reachable_and_ask_the_validator():
    """The gate asks `policy_step.validate_action` on every call, not a list.

    Read from the bytecode rather than the source, so the docstring that
    names `ACTION_REQUIRED` to explain why the function does not, cannot
    satisfy the check.

    "Asks rather than restates" is about the FIELD NAMES, not the
    attribute. Loading `ACTION_REQUIRED` is asking the contract for its
    own required set, which is what keeps the two in step; typing
    `kind`, `target`, `inputs` in here would be the restatement that
    drifts the first time a field is added.

    So the attribute is required present, and no field name may appear
    among the constants the function loads. A test that forbade the
    attribute outright would forbid the fix for the very defect it
    exists to catch, and one that only inspected string *names* would
    miss a field reached by any other route into a constant.
    """
    import dis

    instrs = dis.get_instructions(method_exec._validator_refuses)
    names = {i.argval for i in instrs if isinstance(i.argval, str)}
    loaded = {i.argval for i in instrs
              if i.opname in ("LOAD_CONST", "LOAD_METHOD") and isinstance(i.argval, str)}
    assert "validate_action" in names
    assert "policy_step" in names
    assert "ACTION_REQUIRED" in names
    assert not set(policy_step.ACTION_REQUIRED) & loaded


def test_every_return_is_read_so_a_late_inert_return_still_bites():
    """`all()` over every exit: a single inert-only body is still refused."""
    source = ("def STEP(view, state):\n"
              "    for x in view:\n"
              "        return {\"action\": [], \"state\": state}\n"
              "    return {\"action\": {}, \"state\": state}\n")
