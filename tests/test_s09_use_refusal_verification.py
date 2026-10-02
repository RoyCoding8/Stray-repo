"""A use that never ran must verify as a refusal, not as a bad record.

`verify_use_records` checked only the four execution verdicts, so the
refusal record `run_use` produces read as `bad-verdict` — a refusal reported
as corrupt evidence. The tests that hit it were rewritten to assert the
refusal contract rather than the old incumbent fallback, and the verifier
had to learn the difference between "ran and was scored" and "never ran".

A refusal is now checked for the fields that make it honest: it carries a
reason, its executed fields all read `refused`, and it names no operation.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import checker, worlds


def _own(record) -> list:
    """Problems about this record, ignoring the absent rest of the panel.

    `verify_use_records` also reports every expected cell it did not see, so
    a single-record check drowns in missing-record noise that says nothing
    about the record under test.
    """
    problems = []
    unevaluable: list = []
    return checker._verify_record(record, worlds.FROZEN_DIR, unevaluable)


def _refusal(**overrides) -> dict:
    from experiments.ad01 import trajectory
    base = trajectory._policy_refused_record(
        {"campaign_id": "ad01-w0-I-00"}, 0, "I",
        "ad01-w0-within-sw-00", "software", None,
        "use ran with no policy")
    base.update(overrides)
    return base


def test_a_refusal_verifies_clean():
    assert _own(_refusal()) == []


def test_a_refusal_without_a_reason_is_a_problem():
    """An empty reason is indistinguishable from a crash."""
    problems = _own(_refusal(fallback_reason=""))

    assert any("refusal-without-reason" in problem
               for problem in problems), problems


def test_a_refusal_that_also_names_a_method_is_a_problem():
    """The shape the distinct `status` was added to prevent."""
    problems = _own(_refusal(selected="seed-sw-greedy"))

    assert any("refused-record-claims-execution" in problem
               for problem in problems), problems


def test_a_refusal_carrying_operations_is_a_problem():
    problems = _own(_refusal(operation_ids=["ad01-op-1"]))

    assert any("refused-record-has-operations" in problem
               for problem in problems), problems


def test_an_execution_record_is_still_held_to_the_four_verdicts():
    executed = _refusal(status="admitted", verdict="mostly-ok",
                        selected="seed-sw-greedy",
                        executed="seed-sw-greedy",
                        executed_source="def m(): pass")

    problems = _own(executed)

    assert any("bad-verdict" in problem
               for problem in problems), problems
