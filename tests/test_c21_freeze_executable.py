"""A program that cannot execute is refused by the branch that says so.

C19 measured five non-executable STEP sources - an empty action, an
unconditional raise, a bare pass, a bare return and `return 42` - and
found all five passing `verify_step_source` with an empty frozen-write
reason. On the base this lane was assigned that was true, and the lane
confirmed it directly before changing anything. It is no longer true,
and saying so plainly matters more than any fix did: C5's rule,
integrated at d421c58, refuses a STEP whose every written exit provably
binds `action` to something the action contract refuses, and it derives
that bound by asking `policy_step.validate_action` rather than restating
its contract.

So the first question this file answers is whether the hole is still
open, and the answer is measured rather than assumed. Two of C19's five
are refused at the static gate by that rule. Three are not: a raise, a
pass and a `return 42` are not `return` statements binding an inert
action, so nothing in them is a statement the rule reads. All three are
refused later, at `no-boundary-action`, because their bytes select no
diagnostic evidence. That is a correct refusal and it is not the same
branch, which is why this file pins the branches individually instead of
asserting that the five are all refused - the assertion that matters
for a guard is that the *named* branch is the one that fired.

What C5's rule does not decide is stated in its own docstring and
reproduced here as a test, because a boundary nobody wrote down is a
boundary the next reader will narrow to a guarantee. The rule reads
`return` statements. It does not read a body that raises before reaching
one. A program built from the real template with an unconditional raise
on its first line passes the static gate, passes the frozen-write check,
passes `_emits_probe` and passes `_x_is_data_dependent` - every check the
admission path makes before it would execute anything - and then cannot
execute at all. The refusal does arrive, at execution, inside a bounded
child. The admission path is not wrong about that program; the verdict it
returns is the thing to read.

What is genuinely still wrong is not executability. It is that an
admission recorded with no stated reason cannot be audited. `trajectory`
projects `episode.get("reason", "")` into the observation detail for
every disposition, so the one disposition that legitimately carries no
reason - `bound`, where nothing was refused - is written to the record
as `"reason": ""`. `records._policy_refusal` was measured here and is
*not* a second site: it guards on `disposition in ("rejected",
"unavailable")` and returns `None` for a binding, so the projection at
`trajectory.py:1171` is the only one that can write the empty reason.
The archived evidence in `reports/evidence/invl02-r123/e0-run.json`
carries exactly that shape, and an auditor reading it cannot tell a
binding that was decided from one that was defaulted into place. That
defect is independent of executability: an admission with an empty
reason is unauditable whether or not its bytes can run.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel
from experiments.ad01 import method_exec as exec_module
from experiments.ad01 import records
from experiments.ad01 import trajectory


C19_VARIANTS = {
    "empty-action": 'def STEP(view, state):\n    return {"action": None, "state": state}\n',
    "empty-dict-action": 'def STEP(view, state):\n    return {"action": {}, "state": state}\n',
    "unconditional-raise": 'def STEP(view, state):\n    raise ValueError("nope")\n',
    "bare-pass": 'def STEP(view, state):\n    pass\n',
    "return-42": 'def STEP(view, state):\n    return 42\n',
    "bare-return": 'def STEP(view, state):\n    return\n',
}


def _step(source: str):
    return [node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "STEP"][0]


def _gate_error(source: str) -> str:
    try:
        exec_module.verify_step_source(source, "STEP")
    except Exception as exc:
        return str(exc)
    return ""


def _refusal_branch(source: str) -> str:
    verdict = channel.classify_revision(
        source, views=[{"frontier": [{"task": "t", "capability": "c"}],
                        "experience": [],
                        "authority_remaining": {"queries": 8, "steps": 6}}])
    return str(verdict.get("eligibility"))


def test_the_two_inert_action_returns_are_refused_at_the_static_gate():
    """The branch C5 integrated, pinned by name rather than by outcome.

    Asserting only `!= ELIGIBLE` is what let this defect survive an audit:
    a test that passes for any refusal at all cannot tell a working guard
    from a broken one. So each of these two asserts the specific refusal
    string the static gate produces, and the next test asserts the other
    three are *not* that refusal - otherwise a single changed message
    would satisfy both.
    """
    for name in ("empty-action", "empty-dict-action"):
        source = C19_VARIANTS[name]
        error = _gate_error(source)

        assert "entry-can-produce-no-action" in error, (
            "%s is no longer refused as unable to produce an action; the "
            "gate said %r" % (name, error))


def test_the_three_returns_c5_cannot_see_are_refused_by_the_boundary_check():
    """A raise, a pass and a `return 42` carry no `return` binding an action.

    This is the honest limit of the static rule, and it is why the
    executability requirement does not belong in `verify_step_source`:
    the rule reads `return` statements, and there is nothing in these
    three for it to read. They are refused, and refused correctly, one
    gate later - by `_emits_probe`, which asks whether the bytes select
    diagnostic evidence at all.

    A bare `return` is deliberately absent from this group. It reads as
    one of C19's five, but `_return_binds_inert_action` treats a return
    with no value at all as inert, so the static gate does refuse it.
    Asserting otherwise was a mistake this file records by getting it
    right: the measured split is two inert-action returns, one bare
    return, and three bodies the rule cannot see at all.
    """
    for name in ("unconditional-raise", "bare-pass", "return-42"):
        source = C19_VARIANTS[name]
        error = _gate_error(source)

        assert error == "", (
            "%s is now refused at the static gate, so the boundary check "
            "this test names is no longer the one that refuses it: %r"
            % (name, error))
        assert _refusal_branch(source) == channel.INELIGIBLE_NO_BOUNDARY, (
            "%s is no longer refused for selecting no evidence" % name)


def test_a_bare_return_is_refused_at_the_static_gate_as_inert():
    """The third inert exit, pinned so the split above stays honest."""
    assert "entry-can-produce-no-action" in _gate_error(
        C19_VARIANTS["bare-return"])


def test_the_frozen_write_check_is_not_what_refuses_any_of_them():
    """The premise of the original report, re-measured rather than assumed.

    A non-executable program is not a frozen-write attempt, and if the
    frozen-write reason were what refused these, the freeze would be
    doing work it was never asked to do. Every one of the five carries
    an empty frozen-write reason on the tip as well as on the assigned
    base.
    """
    for name, source in C19_VARIANTS.items():
        assert channel._frozen_write_reason(source) == "", (
            "%s now trips the frozen-write check, which is a different "
            "boundary from the one under test" % name)


def test_a_program_that_raises_before_returning_escapes_every_static_gate():
    """The residual blind spot, written down so it is not rediscovered.

    C5's rule reads returns. A body that raises on its first line has a
    real return and no path to it, so the static gate admits it and so
    does every check the admission path makes before executing anything.
    Asserted here so that whoever narrows the rule to a guarantee has to
    delete this test rather than inherit a false one.
    """
    real = channel._revision_source('view["experience"][0]["x"]')
    dead = real.replace(
        "def STEP(view, state):",
        "def STEP(view, state):\n    raise ValueError('never reached')", 1)

    assert _gate_error(dead) == ""
    assert channel._frozen_write_reason(dead) == ""
    assert channel._emits_probe(dead)
    assert channel._x_is_data_dependent(dead)


def test_a_program_that_really_executes_is_not_refused_by_any_of_this():
    """The non-regression half, without which a guard that refuses all
    would pass every test above."""
    real = channel._revision_source('view["experience"][0]["x"]')

    assert _gate_error(real) == ""
    assert channel._frozen_write_reason(real) == ""
    assert not exec_module._produces_no_action(_step(real))


def test_a_bound_episode_records_the_disposition_rather_than_an_empty_reason():
    """The empty-reason defect, repaired independently of executability.

    `bound` is the one disposition that legitimately carries no reason -
    nothing was refused - and projecting it as `""` writes an outcome
    with no stated reason into the record, which is what an auditor
    cannot act on. The reason for a binding is the binding itself, so it
    is stated rather than defaulted.
    """
    episode = {"kind": "policy_revision", "disposition": "bound",
               "release_id": "r1", "bound_digest": "d" * 64,
               "scope": {"family": "f"}, "construction_calls": 1}

    recorded = trajectory._disposition_reason(episode)

    assert recorded, (
        "a bound episode projected no reason: %r" % (recorded,))
    assert "bound" in recorded


def test_a_refused_episode_keeps_the_reason_it_was_given():
    """The other half of the repair: a real reason is not overwritten."""
    episode = {"kind": "policy_revision", "disposition": "rejected",
               "reason": "assessment outcome was reject",
               "construction_calls": 1}

    recorded = trajectory._disposition_reason(episode)

    assert recorded == "assessment outcome was reject"
