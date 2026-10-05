"""E2 substitutes an observation and checks the policy responds to it.

The point of the substitution is to separate a policy that reads its
evidence from one that recognises a task identifier. A policy that keys
on the identifier alone produces the same action no matter what the
observation says, so it survives a substitution that should have moved
it, and the gate is what tells the two apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from execution_authority import authority_for, execution_store

from experiments.ad01 import worlds
from experiments.ad01.learner import TreatmentRefused
from experiments.ad01.learner import observation_substitution_plan
from experiments.ad01.learner import substituted_observations
from experiments.ad01.learner import substitution_changes_action
from experiments.ad01.learner import substitute_observations_for
from experiments.ad01.learner import substitution_gate

TASK = "ad01-w1-dev-sw-01"
OTHER = "ad01-w1-dev-sw-02"
STORE_TOKEN = "s09expsub"
EVIDENCE_POLICY = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    seen = view[\"observations\"]\n"
    "    verdict = \"none\"\n"
    "    if seen:\n"
    "        verdict = seen[-1][\"verdict\"]\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"question\": \"verdict %s\" % verdict,\n"
    "                         \"unknown\": \"the substituted verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"seen\": len(seen)}}\n"
)
IDENTIFIER_POLICY = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"question\": \"look at %s\" % target,\n"
    "                         \"unknown\": \"the task identifier\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {}}\n"
)
FAMILY_LABEL_POLICY = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    family = view[\"task_content\"][\"family\"]\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"question\": \"family %s\" % family,\n"
    "                         \"unknown\": \"the hardcoded family label\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {}}\n"
)


def _task(task_id: str = TASK) -> dict:
    return worlds.load_task(worlds.FROZEN_DIR, task_id)


def _originals() -> list:
    return substituted_observations(_task(), verdict="not-preserved")


@pytest.fixture(scope="module")
def store():
    """The store the gate executes policy source under.

    `_action_of` runs the policy source in a real child, so the gate needs the
    same store, allocation and operation identity any other execution needs.
    Without them it refuses, and a refusal is not a verdict: both the
    evidence-reading policy and the blind one would look identical.
    """
    with execution_store(STORE_TOKEN) as authority_store:
        yield authority_store


def test_a_policy_that_reads_its_evidence_changes_its_action(store):
    original = _originals()
    swapped, plan = substitute_observations_for(
        _task(), original, verdict="preserved")

    assert substitution_changes_action(
        EVIDENCE_POLICY, _task(), original, swapped,
        authority=authority_for(store, "s09exp-evidence")), (
        "a policy that reads the substituted verdict must move")


def test_a_policy_that_keys_on_the_task_identifier_fails(store):
    original = _originals()
    swapped, _ = substitute_observations_for(
        _task(), original, verdict="preserved")

    assert not substitution_changes_action(
        IDENTIFIER_POLICY, _task(), original, swapped,
        authority=authority_for(store, "s09exp-identifier")), (
        "a policy keyed on the task identifier alone is not reading its"
        " evidence, and the gate exists to catch exactly that")


def test_a_policy_that_keys_on_a_hardcoded_family_label_fails(store):
    original = _originals()
    swapped, _ = substitute_observations_for(
        _task(), original, verdict="preserved")

    assert not substitution_changes_action(
        FAMILY_LABEL_POLICY, _task(), original, swapped,
        authority=authority_for(store, "s09exp-family-label")), (
        "a policy that reads the family label and nothing else is as blind"
        " as one keyed on the identifier")


def test_the_gate_passes_a_policy_and_fails_a_blind_one(store):
    task = _task()
    original = _originals()
    swapped, _ = substitute_observations_for(
        task, original, verdict="preserved")

    passed = substitution_gate(
        EVIDENCE_POLICY, task, original, swapped,
        authority=authority_for(store, "s09exp-gate-pass"))
    assert passed["responds_to_evidence"] is True
    assert passed["verdict"] == "responds-to-evidence"

    blind = substitution_gate(
        IDENTIFIER_POLICY, task, original, swapped,
        authority=authority_for(store, "s09exp-gate-blind"))
    assert blind["responds_to_evidence"] is False
    assert blind["verdict"] == "responds-only-to-identifier"


def test_the_gate_reports_the_two_actions_it_compared(store):
    task = _task()
    original = _originals()
    swapped, _ = substitute_observations_for(
        task, original, verdict="preserved")
    report = substitution_gate(
        EVIDENCE_POLICY, task, original, swapped,
        authority=authority_for(store, "s09exp-gate-report"))

    assert report["original_action"]["inputs"]["question"] == \
        "verdict not-preserved"
    assert report["substituted_action"]["inputs"]["question"] == \
        "verdict preserved"
    assert report["original_action"]["target"] == \
        report["substituted_action"]["target"], (
        "the target task is held constant; only the evidence moves")


def test_the_substitution_keeps_the_task_and_only_moves_the_verdict():
    task = _task()
    original = _originals()
    swapped, plan = substitute_observations_for(
        task, original, verdict="preserved")

    assert [o["task_id"] for o in original] == \
        [o["task_id"] for o in swapped]
    assert [o["observation_id"] for o in original] == \
        [o["observation_id"] for o in swapped]
    assert [o["verdict"] for o in original] == ["not-preserved"]
    assert [o["verdict"] for o in swapped] == ["preserved"]
    assert plan["verdicts_before"] == ["not-preserved"]
    assert plan["verdicts_after"] == ["preserved"]


def test_substituting_to_the_same_verdict_is_refused():
    """A no-op substitution would pass a blind policy by construction.

    A gate that can be satisfied without changing anything is a gate that
    measures nothing, so the refusal names the clash rather than letting
    the plan through and reporting a pass.
    """
    task = _task()
    original = _originals()
    with pytest.raises(TreatmentRefused) as caught:
        substitute_observations_for(task, original, verdict="not-preserved")
    assert "not-preserved" in str(caught.value)


def test_a_plan_covers_the_selected_tasks_and_leaves_the_rest_alone():
    task = _task()
    other = _task(OTHER)
    selected = [TASK]
    plan = observation_substitution_plan(
        [TASK, OTHER], selected, verdict="preserved")

    assert plan["substituted_tasks"] == selected
    assert plan["untouched_tasks"] == [OTHER]
    assert plan["verdict_before"] == "not-preserved"
    assert plan["verdict_after"] == "preserved"


def test_a_plan_over_an_unknown_task_is_refused():
    with pytest.raises(TreatmentRefused) as caught:
        observation_substitution_plan(
            [TASK], ["ad01-w9-dev-sw-99"], verdict="preserved")
    assert "ad01-w9-dev-sw-99" in str(caught.value)


def test_a_plan_that_selects_nothing_is_refused():
    with pytest.raises(TreatmentRefused) as caught:
        observation_substitution_plan([TASK], [], verdict="preserved")
    assert "at least one task" in str(caught.value)
