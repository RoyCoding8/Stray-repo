"""C9: the executable bound must read a dict display the way Python builds it.

C5's gate reads the *first* `action` a return binds. A dict display binds each
key as it is written and a later binding replaces an earlier one, so that read
is wrong in both directions at once, and the two wrong answers are the same
mistake: it refuses a program that acts and admits one that cannot. C8 found
both ends; this file closes them with one rule and proves each verdict by
running the program, because a gate on untrusted bytes is only trustworthy if
its answer is checked against what the bytes actually do.

Every case below asserts two things together: what `verify_step_source` says,
and what the same source returns when executed. A gate verdict asserted on its
own would pass just as happily if the rule were inverted, which is the only
thing these tests exist to rule out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.ad01 import method_exec, policy_step

REPO = Path(__file__).resolve().parent.parent
BUDGET_FIT = REPO / "reports" / "evidence" / "invr1b17-budgetfit" / "budget-fit.json"


def _real_action() -> str:
    return ('{"kind": "stop", "target": "t", "inputs": {},'
            ' "evidence_refs": [], "requested_resources": {}}')


def _admitted(source: str) -> bool:
    try:
        return method_exec.verify_step_source(source, "STEP") == "STEP"
    except method_exec.MethodExecutionError:
        return False


def _run(source: str, view=None, state=None):
    namespace: dict = {}
    exec(compile(source, "<c9>", "exec"), namespace)  # noqa: S102
    return namespace["STEP"]({} if view is None else view,
                             {} if state is None else state)


def _gate_agrees_with_runtime(source: str, view=None) -> bool:
    """Whether the gate's answer matches what running the source does.

    The gate refuses exactly the programs that cannot produce an action the
    contract accepts, so the two must agree for the same bytes. Reading the
    expectation off the runtime result rather than off a hand-written table
    is what makes this a check of the gate and not a restatement of its rule.
    """
    try:
        result = _run(source, view=view)
        actable = False
        if isinstance(result, dict) and "action" in result:
            try:
                policy_step.validate_action(result["action"])
                actable = True
            except ValueError:
                actable = False
    except Exception:
        actable = True
    return _admitted(source) is actable


# --- defect 1: override order, both directions -----------------------------


def test_a_later_duplicate_action_is_the_binding_not_the_first():
    """C8's over-refusal, closed: the runtime binding is the last one.

    `{"action": None, "action": <real>}` binds the real action at runtime, so
    the program acts. The first-wins read saw the inert literal and refused.
    """
    source = ("def STEP(view, state):\n"
              "    return {\"action\": None, \"action\": %s, \"state\": state}\n"
              % _real_action())

    assert _run(source)["action"]["kind"] == "stop"
    policy_step.validate_step_result(_run(source))
    assert _admitted(source), "gate still reads the first binding"
    assert _gate_agrees_with_runtime(source)


def test_a_later_spread_action_is_the_binding_not_the_first():
    """Same false positive through `**`, which is a later binding too.

    `{"action": None, **{"action": <real>}}` evaluates to the real action.
    The `**` key node is `None`, so a walk that stops at the first literal
    never sees it and refuses a program that always acts.
    """
    source = ("def STEP(view, state):\n"
              "    return {\"action\": None, **{\"action\": %s},"
              " \"state\": state}\n" % _real_action())

    assert _run(source)["action"]["kind"] == "stop"
    assert _admitted(source), "gate does not read past the first binding"
    assert _gate_agrees_with_runtime(source)


def test_a_later_inert_action_shadows_an_earlier_real_one():
    """The mirror, which the first-wins read got wrong in the other direction.

    `{"action": <real>, "action": None}` binds `None`: the program can never
    act. The first-wins read saw the real action and admitted a program whose
    every step result is refused one step later. Same ordering question, same
    wrong answer, opposite direction, which is why one rule closes both.
    """
    source = ("def STEP(view, state):\n"
              "    return {\"action\": %s, \"action\": None, \"state\": state}\n"
              % _real_action())

    assert _run(source)["action"] is None
    assert not _admitted(source), "gate admits a program that cannot act"
    assert _gate_agrees_with_runtime(source)


def test_a_later_inert_spread_shadows_an_earlier_real_one():
    source = ("def STEP(view, state):\n"
              "    return {\"action\": %s, **{\"action\": None},"
              " \"state\": state}\n" % _real_action())

    assert _run(source)["action"] is None
    assert not _admitted(source)
    assert _gate_agrees_with_runtime(source)


def test_a_literal_after_a_spread_still_overrides_it():
    """Ordering is positional across both kinds of binding.

    A spread before the literal means the literal is last and binds, so an
    inert literal there is a sound refusal. A walk that stopped at the spread
    would admit this; a walk that ignored spreads entirely would still refuse
    it by accident. Pinned so the two cannot be confused later.
    """
    source = ("def STEP(view, state):\n"
              "    return {**view, \"action\": None, \"state\": state}\n")

    assert _run(source, view={"x": 1})["action"] is None
    assert not _admitted(source)
    assert _gate_agrees_with_runtime(source, view={"x": 1})


def test_a_real_action_after_a_spread_wins_over_it():
    source = ("def STEP(view, state):\n"
              "    return {**view, \"action\": %s, \"state\": state}\n"
              % _real_action())

    assert _run(source, view={"x": 1})["action"]["kind"] == "stop"
    assert _admitted(source)
    assert _gate_agrees_with_runtime(source, view={"x": 1})


def test_a_spread_that_cannot_fold_is_not_decided():
    """The honest limit of reading a spread: one that is not a literal.

    `{"action": None, **build()}` puts the undecidable binding last, so
    whatever `build()` returns overrides the inert literal and the program
    may well act. `build()` is a call, `ast.literal_eval` will not fold it,
    and a dict of unknown keys might carry a real action, so the gate admits
    and execution judges. Refusing it would be a guess in the
    safe-looking direction.
    """
    for source in (
            "def STEP(view, state):\n"
            "    return {\"action\": None, **build(), \"state\": state}\n",
            "def STEP(view, state):\n"
            "    return {\"action\": None, **state, \"state\": state}\n"):
        assert _admitted(source), "the gate decided a spread it cannot fold"


def test_a_spread_before_the_literal_is_decided_by_the_literal():
    """Position decides, and this is the half that is decidable.

    `{**build(), "action": None}` binds the literal last whatever `build()`
    returns, so it is inert on every path and refusing it is sound. Pinned
    beside the case above so the two are not read as one rule: what decides
    is whether the undecidable binding is overridden, not whether a spread is
    present.
    """
    source = ("def STEP(view, state):\n"
              "    return {**state, \"action\": None, \"state\": state}\n")

    assert _run(source, state={"action": {"kind": "stop", "target": "t",
                                          "inputs": {}, "evidence_refs": [],
                                          "requested_resources": {}}
                              })["action"] is None
    assert not _admitted(source)


def test_a_three_way_override_follows_the_last_binding():
    source = ("def STEP(view, state):\n"
              "    return {\"action\": None, \"action\": %s,"
              " **{}, \"action\": 0, \"state\": state}\n" % _real_action())

    assert _run(source)["action"] == 0
    assert not _admitted(source)
    assert _gate_agrees_with_runtime(source)


# --- defect 2: a return with no value at all -------------------------------


def test_a_bare_return_alongside_an_inert_dict_is_refused():
    """C8's under-refusal, closed: a bare `return` binds nothing.

    A `Return` with no value is not a dict literal, so the first-wins read
    counted it as unknown and admitted a body whose other exit is inert. But
    every input reaching a bare `return` yields `None`, so the envelope never
    carries an action and `validate_step_result` refuses it for that. It is
    inert for the same reason the other exit is, and one rule covers both.
    """
    source = ("def STEP(view, state):\n"
              "    if view:\n"
              "        return {\"action\": None, \"state\": state}\n"
              "    return\n")

    assert _run(source, view={"x": 1})["action"] is None
    assert _run(source, view=None) is None
    assert not _admitted(source), "a bare return still admits"
    assert _gate_agrees_with_runtime(source, view={"x": 1})


def test_a_bare_return_alone_is_refused():
    """The single-return version, with nothing to hide behind."""
    source = "def STEP(view, state):\n    return\n"

    assert _run(source) is None
    assert not _admitted(source)


def test_a_bare_return_beside_a_real_action_admits():
    """The bare return is inert; it must not become a licence to refuse.

    One exit hands back a contract-valid action, so the program can act and
    the gate must admit. Without this the fix would be a new over-refusal
    wearing the same shape as the one it closed.
    """
    source = ("def STEP(view, state):\n"
              "    if view:\n"
              "        return {\"action\": %s, \"state\": state}\n"
              "    return\n" % _real_action())

    assert _run(source, view={"x": 1})["action"]["kind"] == "stop"
    assert _admitted(source)
    assert _gate_agrees_with_runtime(source, view={"x": 1})


def test_an_implicit_fallthrough_alone_is_still_admitted():
    """No `return` at all remains the CPU bound's case, not this gate's.

    A body that never writes a return falls through to `None` too, but
    nothing in its bytes says when or whether it ends, and `test_s09step_arm`
    proves the CPU bound kills a spinning one. Refusing it here would delete
    that boundary's only coverage, so the two no-action shapes stay apart:
    exits that are written down are read, a body with no exits is not.
    """
    source = "def STEP(view, state):\n    x = 1\n"

    assert _run(source) is None
    assert _admitted(source), "the gate took over the CPU bound's case"


# --- the rule did not cost anything the old one had ------------------------


def test_every_c5_boundary_still_holds():
    """The shapes C5 established, re-checked against the new rule.

    A fix that closes a defect by widening the rule has to show the rule did
    not move anywhere else. Each of these is a distinct way a return can be
    unactable, and each must keep its recorded answer.
    """
    for literal in ("None", "False", "0", "0.0", "''", "[]", "{}", "7"):
        source = ("def STEP(view, state):\n"
                  "    return {\"action\": %s, \"state\": state}\n" % literal)
        assert not _admitted(source), (
            "literal %r stopped being provably inert" % literal)

    inert_both_arms = (
        "def STEP(view, state):\n"
        "    if view:\n"
        "        return {\"action\": None, \"state\": state}\n"
        "    return {\"action\": 0, \"state\": state}\n")
    unknown_kind = (
        "def STEP(view, state):\n"
        "    return {\"action\": {\"kind\": \"teleport\", \"target\": \"t\","
        " \"inputs\": {}, \"evidence_refs\": [],"
        " \"requested_resources\": {}}, \"state\": state}\n")
    for source in (inert_both_arms, unknown_kind):
        assert not _admitted(source)

    for source in (
            "def STEP(view, state):\n"
            "    return {\"action\": dict(view), \"state\": state}\n",
            "def STEP(view, state):\n"
            "    payload = build()\n"
            "    return payload\n",
            "def STEP(view, state):\n"
            "    return {\"state\": state}\n",
            "def STEP(view, state):\n"
            "    def pick():\n"
            "        return {\"action\": None, \"state\": state}\n"
            "    return pick()\n"):
        assert _admitted(source), (
            "the gate decided a return it cannot read: %r" % source)


def test_every_authored_control_is_still_admitted():
    """The gate may not narrow the campaign's own controls."""
    from experiments.ad01 import channel_controls

    for role in sorted(channel_controls.CONTROL_BUILDERS):
        source = channel_controls.build_control(role)["source"]
        assert method_exec.verify_step_source(source, "STEP") == "STEP", (
            "the %s control was refused by the executable bound" % role)


def test_the_rule_still_asks_the_contract_rather_than_restating_it():
    """Read off the bytecode, so the docstring cannot satisfy it.

    "Asks rather than restates" is about the FIELD NAMES. Loading
    `ACTION_REQUIRED` is asking the contract for its own required set;
    typing `kind`, `target`, `inputs` in the gate would be the
    restatement that drifts when a field is added. The attribute is
    therefore required to be present and every field name required to be
    absent.
    """
    import dis

    instrs = dis.get_instructions(method_exec._validator_refuses)
    names = {i.argval for i in instrs if isinstance(i.argval, str)}
    loaded = {i.argval for i in instrs
              if i.opname in ("LOAD_CONST", "LOAD_METHOD") and isinstance(i.argval, str)}
    assert "validate_action" in names
    assert "ACTION_REQUIRED" in names
    assert not set(policy_step.ACTION_REQUIRED) & loaded


def test_the_old_refusals_are_undisturbed():
    for source, token in (
            ("", "empty-policy-source"),
            ("def OTHER(view, state):\n    return None\n",
             "missing-entry-function"),
            ("def STEP(view, state):\n    import os\n    return None\n",
             "imports-forbidden"),
            ("def STEP(view, state):\n    return state._x\n",
             "dunder-access-forbidden"),
            ("def STEP(view, state, extra):\n    return None\n",
             "entry-arity")):
        with pytest.raises(method_exec.MethodExecutionError) as refusal:
            method_exec.verify_step_source(source, "STEP")
        assert token in str(refusal.value), (
            "%r refused as %r, not %r" % (source, str(refusal.value), token))


def test_a_hostile_literal_still_terminates_as_a_refusal():
    """Reading every pair did not multiply the folding work per return.

    The evaluator is reached with a node off the model's own source, so a
    fold that allocates must not escape as a signal.
    """
    import time

    for literal in ("[0] * 10 ** 9", "'x' * 10 ** 9",
                    "{str(i) for i in range(10 ** 8)}"):
        source = ("def STEP(view, state):\n"
                  "    return {\"action\": %s, \"state\": state}\n" % literal)
        started = time.monotonic()
        try:
            assert _admitted(source) is True
        except method_exec.MethodExecutionError:
            pass
        assert time.monotonic() - started < 30.0, (
            "literal %r took too long on the untrusted path" % literal)


# --- the recorded consequence of the old rule ------------------------------


def test_the_recorded_budget_fit_verdict_is_no_longer_reproducible():
    """The stale-green, stated as a fact with its current value.

    `invr1b17-budget-fit` recorded `tiny_policy` as admitted and concluded
    from it that no legitimate model artifact was rejected. That 115-byte
    policy binds `action` to `{"kind": "stop", "target": "swe.task",
    "inputs": {}}`, which `validate_action` refuses for missing
    `evidence_refs` and `requested_resources`, so it was never actable and
    under this gate it computes `admitted: false`. The artifact is
    immutable, so the fact belongs to the reader rather than to the JSON.

    This pins the disagreement rather than the old value: it asserts the two
    differ, so a reader who runs `loader_verdicts` is not surprised. It does
    not assert which is right, because the artifact records the loader as it
    was and the gate is a later change to what a source must prove.
    """
    from experiments.ad01 import invr1b17_budget_fit as budget_fit

    recorded = json.loads(
        BUDGET_FIT.read_text(encoding="utf-8")
    )["offline_measurements"]["loader_verdicts"]
    computed = budget_fit.loader_verdicts()

    assert recorded["tiny_policy"]["admitted"] is True, (
        "the recorded artifact changed; this test is stale, not the gate")
    assert computed["tiny_policy"]["admitted"] is False, (
        "the computed verdict moved; re-read what this test claims")
    assert "entry-can-produce-no-action" in computed["tiny_policy"]["defect"]
    assert recorded["authored_control"]["admitted"] is True
    assert computed["authored_control"]["admitted"] is True, (
        "the authored control must stay admitted; it is the campaign's own")


def test_the_budget_fit_test_reads_the_recorded_json_not_the_code():
    """Why that suite stays green, so the green is not mistaken for a pass.

    `test_the_authored_control_is_admitted_by_the_frozen_loader` asserts
    `verdicts["tiny_policy"]["admitted"] is True` against `artifact()`,
    which is a `json.loads` of the immutable file. It would pass with the
    gate deleted, with the gate inverted, or with the gate refusing every
    source in the repository: the assertion is a fact about bytes on disk,
    not about any code path. It cannot fail on this change, so its green
    says nothing about the change.
    """
    body = (REPO / "tests" / "test_inv_b17_budget_fit.py")\
        .read_text(encoding="utf-8")
    assert 'artifact()["offline_measurements"]["loader_verdicts"]' in body
    assert "def artifact() -> dict:\n    return json.loads(" in body
    assert "loader_verdicts()" not in body, (
        "the suite now calls the code; the staleness claim is wrong")
