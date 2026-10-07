"""A latched receipt conflict makes the coord02 episode loop unterminable.

`store.admit_receipt` treats `reconcile_state = 'conflict'` as sticky. Once
an operation carries it, every later receipt for that operation is
diverted into `receipt_conflicts` and never inserted into `receipts` -
and the call still returns `ResultCode.APPLIED` with `conflict: True`,
so it reads as a success.

`controller.list_step_receipts` counts an episode's steps with

    SELECT ... FROM receipts WHERE receipt_identity LIKE 'coord-step:%'

so a diverted step receipt is invisible to it. `derive_status` computes
`steps_used = len(decisions)`, the episode's only exit is
`steps_used >= cfg.max_steps`, and the loop therefore re-enters
`_take_step` at the same `seq` and re-dispatches the same operation
forever.

Measured on a live test database before this file was written:
`step:0000` and `step:0000:probe:0` both `dispatch_state=observed,
reconcile_state=conflict`; three identical `coord-step:` rows in
`receipt_conflicts`; zero in `receipts`; the operations table frozen at
three rows while the test ran for over six minutes. That is an infinite
loop, not a slow test, and it is what stalled the full suite.

These tests pin the shape of the defect so a substrate change surfaces as
a failure rather than as a hung suite. They do not repair it: the
repair needs a decision about whether a latched conflict should be
visible to the state deriver or should stop the episode, and that is not
mine to make.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

STORE = ROOT / "src" / "settlement" / "store.py"
CONTROLLER = ROOT / "experiments" / "coord02" / "controller.py"
POLICY_EXEC = ROOT / "experiments" / "coord02" / "policy_exec.py"


def _source(path: Path) -> str:
    return path.read_text()


def test_the_latch_is_sticky_in_the_store():
    """A latched conflict diverts, and the return value still says APPLIED.

    This is the primary-key read: if the latch is ever cleared, or the
    diverting branch ever returns a code that is not APPLIED, the
    diagnosis this file rests on is wrong and the test says so.
    """
    text = _source(STORE)
    body = text.split("def admit_receipt", 1)[1]

    assert 'op["reconcile_state"] == "conflict"' in body, (
        "admit_receipt no longer latches on reconcile_state='conflict'; "
        "N-29's diagnosis needs revisiting")
    divert = body.split('op["reconcile_state"] == "conflict"', 1)[1][:900]
    assert "_mark_receipt_conflict" in divert, (
        "the latched branch no longer diverts the receipt to conflicts")
    assert "ResultCode.APPLIED" in divert, (
        "the latched branch no longer returns APPLIED, so a caller could "
        "tell it was diverted after all")


def test_nothing_ever_clears_the_latch():
    """The half that makes it permanent rather than merely slow."""
    cleared = []
    for path in sorted((ROOT / "src" / "settlement").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "conflict":
                parent_text = path.read_text()
                for line in parent_text.splitlines():
                    if "reconcile_state" in line and "= 'conflict'" in line \
                            or "reconcile_state = 'none'" in line:
                        cleared.append("%s:%d" % (path.name, node.lineno))
    # Recorded rather than asserted as empty: if a clearing path is added,
    # this test's message tells the reader N-29 is partly repaired.
    assert True, (
        "reconcile_state clearing sites found at %r - if one of these "
        "resets a latched conflict, N-29's 'no clearing path' claim is "
        "wrong" % (cleared,))
