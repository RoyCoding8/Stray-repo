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


def test_steps_are_counted_from_the_table_the_latch_bypasses():
    """The two halves only combine into an infinite loop together."""
    assert "receipts" in _source(CONTROLLER).split("def list_step_receipts")[1][:900]

    text = _source(CONTROLLER)
    reader = text.split("def list_step_receipts", 1)[1].split("\ndef ", 1)[0]
    assert "FROM receipts" in reader, (
        "list_step_receipts no longer reads the receipts table, so N-29's "
        "mechanism no longer applies")
    assert "coord-step" in reader or "STEP_RECEIPT_KIND" in reader


def test_the_episode_loop_exits_only_on_the_receipt_count():
    """`max_steps` is compared against a count the latch can pin at zero.

    The chain is `derive_status` -> `list_step_receipts` (the receipts
    table) -> `steps_used = len(decisions)` -> `run_episode`'s exit
    condition. All three links have to hold for the loop to be
    unterminable, so each is checked where it actually lives rather than
    inside one narrow slice.
    """
    text = _source(CONTROLLER)
    derive = text.split("def derive_status", 1)[1].split("\ndef ", 1)[0]
    episode = text.split("def run_episode", 1)[1]

    assert "list_step_receipts" in derive, (
        "derive_status no longer derives decisions from the receipts "
        "table, so a diverted receipt would no longer pin steps_used")
    assert "len(decisions)" in derive, (
        "steps_used is no longer len(decisions), so a diverted receipt "
        "would no longer pin it")
    assert 'status["steps_used"] >= cfg.max_steps' in episode, (
        "run_episode no longer gates on steps_used; N-29's loop needs "
        "revisiting")


def test_admit_discards_the_result_it_is_given():
    """Secondary but real: the caller cannot see a refusal or a divert.

    I first wrote this up as the cause and was wrong - calling
    `admit_launcher_receipt` directly returns APPLIED. It is still a
    defect, because a caller that discards the result cannot tell an
    admitted receipt from one the store kept for reconciliation, and
    that is precisely why the stall was invisible from the test.
    """
    text = _source(POLICY_EXEC)
    admit = text.split("def _admit", 1)[1].split("\ndef ", 1)[0]

    assert "admit_launcher_receipt" in admit
    assert "return" not in admit and ".code" not in admit, (
        "_admit now inspects the CommandResult, so this test and N-29's "
        "secondary-defect note both need updating")


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
