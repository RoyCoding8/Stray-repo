"""C14: a dict key is a binding, and an undecidable one might be `action`.

C9 made the gate read a dict display in the order Python builds it, and gave
`**` the treatment an undecidable binding deserves: it might carry any key, so
it admits. The same reasoning was not applied to a key. A key is not a
declaration, it is an expression Python evaluates before it writes the pair,
so `{"action": None, k: real}` with `k == "action"` binds the real action
last and hands it back. The gate skipped every key that was not the literal
`"action"`, which made the over-refusal invisible: the display looks like it
never names `action`, and it does, through an expression.

The dangerous direction here is the loud one. A model that writes one
f-string key is refused on the live acquisition path, nothing is retained and
no package is built, while the same program with the key written as a
constant is retained with its digest. Every case below asserts the gate's
verdict and what the same bytes do when executed, because a gate verdict
asserted alone would pass just as happily if the rule were inverted.
"""

from __future__ import annotations

import json

import pytest

from experiments.ad01 import live_construct, method_exec, policy_step

REAL_ACTION = ('{"kind": "stop", "target": "t", "inputs": {},'
               ' "evidence_refs": [], "requested_resources": {}}')


def _source(body: str, preamble: str = "k = 'action'\n") -> str:
    return preamble + "def STEP(view, state):\n" + body + "\n"


def _admitted(source: str) -> bool:
    try:
        return method_exec.verify_step_source(source, "STEP") == "STEP"
    except method_exec.MethodExecutionError:
        return False


def _runtime_verdict(source: str) -> str:
    """What the bytes do when they run, judged by the action contract.

    Read off the executed result rather than off a hand-written table, so a
    disagreement with the gate is a fact about the gate rather than about
    this file's expectations.
    """
    namespace: dict = {}
    exec(compile(source, "<c14>", "exec"), namespace)  # noqa: S102
    result = namespace["STEP"]({}, {})
    if not isinstance(result, dict) or "action" not in result:
        return "no-envelope"
    try:
        policy_step.validate_step_result(result)
    except ValueError:
        return "inert"
    return "acts"


OVER_REFUSALS = {
    "named": '    return {"action": None, k: %s, "state": state}' % REAL_ACTION,
    "concatenated": '    return {"action": None, "act" + "ion": %s,'
                    ' "state": state}' % REAL_ACTION,
    "fstring": '    return {"action": None, f"action": %s, "state": state}'
               % REAL_ACTION,
    "walrus": '    return {"action": None, (k := "action"): %s,'
              ' "state": state}' % REAL_ACTION,
    "format": '    return {"action": None, "{}".format("action"): %s,'
              ' "state": state}' % REAL_ACTION,
}

MIRROR = {
    "named": '    return {"action": %s, k: None, "state": state}' % REAL_ACTION,
    "concatenated": '    return {"action": %s, "act" + "ion": None,'
                    ' "state": state}' % REAL_ACTION,
    "fstring": '    return {"action": %s, f"action": None, "state": state}'
               % REAL_ACTION,
}


@pytest.mark.parametrize("name", sorted(OVER_REFUSALS))
def test_a_computed_key_that_binds_action_is_admitted(name):
    source = _source(OVER_REFUSALS[name])
    assert _runtime_verdict(source) == "acts", (
        "the premise: these bytes produce a contract-valid action")
    assert _admitted(source) is True, (
        "a key that is an expression may be 'action' at runtime, and this"
        " display writes it last, so the gate has no proof of inertness")


@pytest.mark.parametrize("name", sorted(MIRROR))
def test_the_mirror_is_admitted_because_it_is_inert_at_runtime(name):
    source = _source(MIRROR[name])
    assert _runtime_verdict(source) == "inert", (
        "the premise: the computed key overwrites the real action with None")
    assert _admitted(source) is True, (
        "the gate does not prove inertness here either, so admitting is the"
        " same answer the spread already gives")


@pytest.mark.parametrize("name", sorted(OVER_REFUSALS))
def test_the_live_acquisition_path_retains_a_computed_key(name):
    response = json.dumps({"entry": _source(OVER_REFUSALS[name])})
    record = live_construct.parse_live_improver(response)
    assert record["imp_source"] == _source(OVER_REFUSALS[name])
    assert record["imp_digest"], "a retained response carries its digest"


def test_a_constant_key_is_still_read_as_a_constant():
    """The repair is about undecidable keys, not about giving up on `k:`.

    `k` is a name the gate cannot resolve either, and it is a name whose
    value these bytes do pin down. The two differ in what the gate can
    prove: `"action"` is decidable from the bytes, `k` is not. If the repair
    had widened to every key, the decidable half would have gone with it.
    """
    computed = _source(
        '    return {"action": None, k: %s, "state": state}' % REAL_ACTION)
    constant = _source(
        '    return {"action": None, "action": %s, "state": state}'
        % REAL_ACTION)
    assert _runtime_verdict(computed) == "acts"
    assert _runtime_verdict(constant) == "acts"
    assert _admitted(computed) is _admitted(constant) is True


def test_a_computed_key_does_not_resurrect_a_provable_refusal():
    """The sound direction survives: a last literal `action` still decides.

    A computed key admits, so the walk continues and a later literal pair
    still binds `action`. This is the case that would be lost if the repair
    had returned on the first undecidable key rather than recording it.
    """
    source = _source(
        '    return {"action": None, k: None, "action": None,'
        ' "state": state}')
    assert _runtime_verdict(source) == "inert"
    assert _admitted(source) is False, (
        "the last binding of action is a literal the contract refuses, and"
        " no computed key after it reopens the question")


def test_a_computed_key_before_a_real_action_does_not_refuse():
    source = _source(
        '    return {k: None, "action": %s, "state": state}' % REAL_ACTION)
    assert _runtime_verdict(source) == "acts"
    assert _admitted(source) is True


def test_a_literal_key_other_than_action_still_decides_itself():
    source = ('def STEP(view, state):\n'
              '    return {"action": None, "state": state}\n')
    assert _admitted(source) is False, (
        "a literal key is decidable: 'state' provably does not bind action,"
        " so the inert literal is the last binding of it")


def test_the_two_keys_that_agree_are_both_read_as_action():
    source = _source(
        '    return {"action": None, k: None, "state": state}\n')
    assert _runtime_verdict(source) == "inert"
    assert _admitted(source) is True, (
        "every value either key can carry is inert, but the gate reads one"
        " binding at a time and an undecidable key is not a proof")


def test_the_gate_still_refuses_a_display_that_never_names_action():
    source = ('def STEP(view, state):\n'
              '    return {"note": 1, "state": state}\n')
    assert _runtime_verdict(source) == "no-envelope"
    assert _admitted(source) is True, (
        "a display with no action binding is not this gate's refusal; the"
        " envelope is refused for the missing key at execution")


def test_a_spread_and_a_computed_key_agree():
    spread = _source(
        '    return {"action": None, **{"action": %s}, "state": state}'
        % REAL_ACTION)
    computed = _source(
        '    return {"action": None, k: %s, "state": state}' % REAL_ACTION)
    assert _runtime_verdict(spread) == _runtime_verdict(computed) == "acts"
    assert _admitted(spread) == _admitted(computed), (
        "the docstring's own rule for an undecidable spread now names keys"
        " as well, and the two verdicts are the same verdict")
