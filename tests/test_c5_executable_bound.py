"""The live gate must refuse a program that cannot produce an action.

The only live acquisition this system completed
(`reports/evidence/invl02-r123/e0-run.json`) retained and bound a
66-character STEP that returned `{"action": None, "state": state}`. That
value is not a policy action: `policy_step.validate_action` refuses it as
`policy action must be an object`, so the program could not produce a step
result at any input. It was recorded as `disposition: "bound"` with an
empty `reason`.

`method_exec.verify_step_source` was the whole gate on that path, and it
asked only whether the source parses and is well-formed. These tests pin the
repair at that gate: the earliest point where the truth is known from the
bytes alone, before any package is built, retained or bound.

The scope is bounded and the tests below say where the bound is, because a
check that refuses more than it proves is the failure mode here, not a
safety net.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.ad01 import method_exec, policy_step

REPO = Path(__file__).resolve().parent.parent
LIVE_STORE = REPO / "reports" / "evidence" / "invl02-r123" / "frontier-live.json"
BOUND_CONTROL_ID = "acquired-live-live-r1"


def recorded_acquired_source() -> str:
    """The imp_source of the one retained live acquisition, read from evidence.

    Read from the archived store rather than pasted, so this test cannot
    drift from the artifact it is about. If the file is missing the lane has
    no acquisition to reason about and the tests should fail loudly.
    """
    document = json.loads(LIVE_STORE.read_text(encoding="utf-8"))
    packages = document["treatment_arms"]["acquired"]
    matched = [package for package in packages
               if package.get("control_id") == BOUND_CONTROL_ID]
    assert len(matched) == 1, (
        "expected exactly one %s in %s, found %d"
        % (BOUND_CONTROL_ID, LIVE_STORE, len(matched)))
    return matched[0]["imp_source"]


def acting_step(extra: str = "") -> str:
    """A STEP that builds a real policy action, the shape the gate admits."""
    return (
        "def STEP(view, state):\n"
        "    action = {\"kind\": \"stop\", \"target\": \"ad01.task\",\n"
        "              \"inputs\": {}, \"evidence_refs\": [],\n"
        "              \"requested_resources\": {}}" + extra + "\n"
        "    return {\"action\": action, \"state\": state}\n")


# --- the recorded failure --------------------------------------------------


def test_the_recorded_program_is_the_one_this_lane_is_about():
    """The bytes under test are the bytes the run actually bound."""
    source = recorded_acquired_source()

    assert source == 'def STEP(view, state):\n    return {"action": None, "state": state}'
    assert len(source) == 66


def test_the_recorded_program_cannot_produce_a_step_result():
    """What the program returns is refused by the action contract itself.

    This is the claim the recorded `bound` disposition contradicts, and it is
    asserted against `validate_action` rather than against the new gate, so
    it would still hold if the gate were deleted.
    """
    with pytest.raises(ValueError, match="policy action must be an object"):
        policy_step.validate_step_result({"action": None, "state": {}})


def test_the_gate_refuses_the_recorded_program():
    """The repair: the one gate that stood on the live path now refuses.

    This is the test that is red on `5349dab` and green here.
    """
    source = recorded_acquired_source()

    with pytest.raises(method_exec.MethodExecutionError) as refusal:
        method_exec.verify_step_source(source, "STEP")

    assert "entry-can-produce-no-action" in str(refusal.value)


def test_the_refusal_carries_a_reason_that_names_the_defect():
    """A refusal a reader cannot act on is not a usable boundary."""
    source = recorded_acquired_source()

    with pytest.raises(method_exec.MethodExecutionError) as refusal:
        method_exec.verify_step_source(source, "STEP")

    message = str(refusal.value)
    assert "STEP" in message
    assert "policy action" in message


def test_the_recorded_response_reproduces_the_archived_source():
    """The archived `bound` came from these bytes, so the gate is on that path.

    The run ledger records `response_digest 549321f5...` at `text_chars 84`
    for `invl02-live-imp-live`. Reconstructing the response envelope from the
    archived source and hashing it reproduces both. Without this the test
    above would only prove that a string fails a gate, not that the retained
    program did.
    """
    import hashlib

    response = json.dumps({"entry": recorded_acquired_source()})

    assert len(response) == 84
    assert hashlib.sha256(response.encode("utf-8")).hexdigest() == (
        "549321f51523651873ecd36acf967889e6642c22de55b94b852f1506f28dd003")


# --- the shape of the check ------------------------------------------------


@pytest.mark.parametrize("literal", [
    "None", "False", "0", "0.0", "''", "[]", "{}",
    '"probe"', "7",
])
def test_every_refused_action_literal_is_refused_at_the_gate(literal):
    """The check asks the action contract, so it tracks it exactly.

    `None` is the recorded shape. The others are the falsy and bare-scalar
    returns a hand-rolled STEP reaches for. Each is a dict literal binding
    `action` to a literal the contract refuses, so each is provably inert.
    """
    source = (
        "def STEP(view, state):\n"
        "    return {\"action\": %s, \"state\": state}" % literal)

    with pytest.raises(method_exec.MethodExecutionError,
                       match="entry-can-produce-no-action"):
        method_exec.verify_step_source(source, "STEP")


def test_a_program_with_no_return_at_all_is_admitted():
    """The limit of the check, stated as a test.

    A body with no `return` falls through to `None` and cannot produce an
    action either, but nothing in its bytes says when or whether it ends. A
    `while True` is the CPU bound's job and `test_s09step_arm.py` proves that
    bound kills one; refusing it at admission would delete that boundary's
    only coverage. So this gate admits it and execution catches it.
    """
    source = "def STEP(view, state):\n    x = 1\n"

    assert method_exec.verify_step_source(source, "STEP") == "STEP"


def test_a_spinning_policy_is_still_left_to_the_cpu_bound():
    """The exact inherited case, admitted here on purpose."""
    source = ("def STEP(view, state):\n"
              "    total = 0\n"
              "    while True:\n"
              "        total = total + 1\n")

    assert method_exec.verify_step_source(source, "STEP") == "STEP"


def test_a_program_whose_every_branch_is_inert_is_refused():
    """Conditional shapes are read, not assumed: both arms inert is inert."""
    source = (
        "def STEP(view, state):\n"
        "    if view:\n"
        "        return {\"action\": None, \"state\": state}\n"
        "    return {\"action\": 0, \"state\": state}\n")

    with pytest.raises(method_exec.MethodExecutionError,
                       match="entry-can-produce-no-action"):
        method_exec.verify_step_source(source, "STEP")


# --- the boundary of the check, stated -------------------------------------


def test_an_action_assigned_to_a_name_is_admitted():
    """A name could carry a real action, so the gate does not judge it.

    This is the honest limit. The check refuses only what the bytes prove;
    everything else waits for execution, one step later. A gate that
    refused this would be guessing.
    """
    assert method_exec.verify_step_source(acting_step(), "STEP") == "STEP"


def test_an_action_built_by_a_call_is_admitted():
    source = (
        "def STEP(view, state):\n"
        "    return {\"action\": dict(view), \"state\": state}\n")

    assert method_exec.verify_step_source(source, "STEP") == "STEP"


def test_one_real_return_among_inert_ones_is_admitted():
    """A single path that can act is enough to admit the program."""
    source = (
        "def STEP(view, state):\n"
        "    if view:\n"
        "        return {\"action\": None, \"state\": state}\n"
        "    return {\"action\": {\"kind\": \"stop\", \"target\": \"ad01.task\",\n"
        "                      \"inputs\": {}, \"evidence_refs\": [],\n"
        "                      \"requested_resources\": {}}, \"state\": state}\n")

    assert method_exec.verify_step_source(source, "STEP") == "STEP"


def test_an_action_with_an_unknown_kind_is_refused_at_the_gate():
    """What the gate decides by asking the contract, not by its own list.

    A real action object carrying a kind the contract does not carry is inert
    *as far as the contract is concerned* -- `validate_action` refuses it as
    `unknown policy action kind` -- so this gate refuses it here, at
    admission, rather than one step later at execution.

    That is a consequence of deriving the rule from the validator instead of
    restating it, and it is the reason this version is not the
    "only catch `action: None`" check: the bound is "the contract accepts no
    value this program can return as an action", which is broader and still
    sound. A narrower gate would need a second spelling of `ACTION_KINDS` and
    would drift the first time a kind was added.
    """
    source = (
        "def STEP(view, state):\n"
        "    return {\"action\": {\"kind\": \"teleport\", \"target\": \"t\",\n"
        "                      \"inputs\": {}, \"evidence_refs\": [],\n"
        "                      \"requested_resources\": {}}, \"state\": state}\n")

    with pytest.raises(method_exec.MethodExecutionError,
                       match="entry-can-produce-no-action"):
        method_exec.verify_step_source(source, "STEP")
    with pytest.raises(ValueError, match="unknown policy action kind"):
        policy_step.validate_step_result({
            "action": {"kind": "teleport", "target": "t", "inputs": {},
                       "evidence_refs": [], "requested_resources": {}},
            "state": {}})


def test_a_return_that_is_not_a_dict_literal_is_admitted():
    """Only a dict literal naming `action` is read; nothing else is inferred."""
    source = (
        "def STEP(view, state):\n"
        "    payload = build()\n"
        "    return payload\n")

    assert method_exec.verify_step_source(source, "STEP") == "STEP"


def test_a_dict_without_an_action_key_is_admitted():
    """No `action` binding is no evidence of an inert action."""
    source = (
        "def STEP(view, state):\n"
        "    return {\"state\": state}\n")

    assert method_exec.verify_step_source(source, "STEP") == "STEP"


# --- it does not disturb the surrounding gates -----------------------------


def test_a_program_the_gate_refuses_still_gets_its_reason_from_the_contract():
    """The refusal names the contract's own reason, so the two agree."""
    source = recorded_acquired_source()

    with pytest.raises(ValueError, match="policy action must be an object"):
        policy_step.validate_action(None)
    with pytest.raises(method_exec.MethodExecutionError) as refusal:
        method_exec.verify_step_source(source, "STEP")
    assert "policy action" in str(refusal.value)


def test_the_gate_still_refuses_the_defects_it_refused_before():
    """A new check must not displace the old ones.

    Each source below already failed `verify_step_source` on base, and each
    still does. The two-argument case does not: `return {}` is well-formed
    for this gate's own purposes and `verify_step_source` has never claimed
    to check the arity of a returned envelope, only the arity of the entry.
    `run_step_out_of_process` is the caller that catches it.
    """
    for source, token in (
        ("", "empty-policy-source"),
        ("def OTHER(view, state):\n    return None\n",
         "missing-entry-function"),
        ("def STEP(view, state):\n    import os\n    return None\n",
         "imports-forbidden"),
        ("def STEP(view, state):\n    return state._x\n",
         "dunder-access-forbidden"),
    ):
        with pytest.raises(method_exec.MethodExecutionError) as refusal:
            method_exec.verify_step_source(source, "STEP")
        assert token in str(refusal.value), (
            "%r refused as %r, not %r" % (source, str(refusal.value), token))


def test_entry_arity_is_still_refused():
    source = "def STEP(view, state, extra):\n    return None\n"

    with pytest.raises(method_exec.MethodExecutionError, match="entry-arity"):
        method_exec.verify_step_source(source, "STEP")


def test_a_nested_helpers_return_is_not_an_exit_of_the_entry():
    """Only the entry's own returns are its exits.

    `ast.walk` descends into a nested function, and a helper's `return` is
    not a return of the entry. A program that acts through a helper stays
    admitted rather than being refused on the helper's inert return.
    """
    source = (
        "def STEP(view, state):\n"
        "    def pick():\n"
        "        return {\"action\": None, \"state\": state}\n"
        "    return pick()\n")

    assert method_exec.verify_step_source(source, "STEP") == "STEP"


def test_every_authored_control_is_still_admitted():
    """The gate may not narrow the campaign's own controls."""
    from experiments.ad01 import channel_controls

    for role in sorted(channel_controls.CONTROL_BUILDERS):
        source = channel_controls.build_control(role)["source"]
        assert method_exec.verify_step_source(source, "STEP") == "STEP", (
            "the %s control was refused by the executable bound: %s"
            % (role, source))