"""The study must acquire the policy the use phase actually runs.

The first completed M3 run produced twenty-four use records and every one
refused with `use ran with no policy`. Two causes, and only one is a wiring
mistake. The study acquired methods, which are `ENTRY` functions, while the
use phase runs a `STEP` policy that selects a `capability_id` out of
`eligible_methods`. Those are different artifacts doing different jobs, and
wrapping one in the other's signature would make the evidence claim a policy
governed the use when a different function did.

So the study has to acquire the second artifact too, from the model, under its
own prompt and its own freeze.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_the_study_builds_a_use_phase_prompt():
    """The prompt states the job: choose a capability, not write a method."""
    from scripts import inv01_study as S

    prompt = S._v1_use_policy_prompt(
        ["acquired-sw-2074657c", "acquired-gr-9911abcd"],
        {"task_id": "ad01-w0-within-sw-00", "family": "software"})

    assert "STEP" in prompt
    assert "use_method" in prompt
    assert "method_id" in prompt
    assert "acquired-sw-2074657c" in prompt
    assert "ENTRY" not in prompt, (
        "the use phase runs a selector, not a method implementation")


@pytest.fixture(scope="module")
def execution_store():
    from execution_authority import execution_store as make_store

    with make_store("ci-invr1policy") as store:
        yield store


def test_an_acquired_use_policy_selects_from_the_eligible_methods(
        execution_store):
    """A compiled policy must admit a use_method naming a real member."""
    from experiments.ad01 import policy_step
    from scripts import inv01_study as S

    source = S._v1_use_policy_fallback(["acquired-sw-2074657c"])
    policy = policy_step.compile_step(source, origin="<test>")

    assert callable(policy), "the fallback must compile to a STEP callable"
    decision = policy.run({
        "task_content": {"task_id": "ad01-w0-within-sw-00"},
        "observations": [], "open_questions": [], "last_result": None,
        "eligible_methods": ["acquired-sw-2074657c"],
        "remaining": {},
    }, {}, dsn=execution_store["dsn"],
        allocation_id=execution_store["allocation_id"],
        operation_id="invr1-use-policy")

    assert decision["action"]["kind"] == "use_method"
    assert decision["action"]["inputs"]["method_id"] == "acquired-sw-2074657c"


def test_the_fallback_refuses_rather_than_inventing_a_member():
    """No eligible members means no policy, not a made-up capability id."""
    from scripts import inv01_study as S

    assert S._v1_use_policy_fallback([]) == ""
