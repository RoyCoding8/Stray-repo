"""E2 experience contrasts: relevant, no experience, and the matched control.

The relevance contrast is only interpretable when the two arms differ in
relevance and in nothing else. A shorter control would confound semantic
relevance with context volume, so the equal-length pair is built by
construction and any attempt to make the lengths differ is refused at the
point of construction rather than reported afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import packet, worlds
from experiments.ad01.learner import TreatmentRefused
from experiments.ad01.learner import equal_length_experience_pair
from experiments.ad01.learner import irrelevant_control_for
from experiments.ad01.learner import matched_experience_arms
from experiments.ad01.learner import no_experience_experience
from experiments.ad01.learner import relevant_experience
from experiments.ad01.learner import treatment_prompt

TARGET = "ad01-w1-dev-sw-01"
SAME_FAMILY = ["ad01-w1-dev-sw-00", "ad01-w1-dev-sw-02"]
OTHER_FAMILY = ["ad01-w0-dev-gr-00", "ad01-w0-dev-gr-01", "ad01-w0-dev-gr-02",
                "ad01-w1-dev-gr-00", "ad01-w1-dev-gr-01", "ad01-w1-dev-gr-02",
                "ad01-w2-dev-gr-00", "ad01-w2-dev-gr-01", "ad01-w2-dev-gr-02"]
BUDGET = {"model_calls": 2, "queries": 8, "steps": 4}
ARM = {"family": "software", "budget": BUDGET}


def _task(task_id: str) -> dict:
    return worlds.load_task(worlds.FROZEN_DIR, task_id)


def test_relevant_and_no_experience_arms_differ_only_in_experience():
    task = _task(TARGET)
    relevant = relevant_experience(task, SAME_FAMILY, [task], BUDGET)
    bare = no_experience_experience(task, SAME_FAMILY, [task], BUDGET)

    assert relevant["observations"], "the relevant arm carries experience"
    assert bare["observations"] == [], "the control carries no experience"

    prompt_relevant = treatment_prompt(ARM, task, relevant)
    prompt_bare = treatment_prompt(ARM, task, bare)
    assert prompt_relevant != prompt_bare

    def _without_experience(prompt: str) -> list:
        return [line for line in prompt.splitlines()
                if not line.startswith("Prior observations:")]

    assert _without_experience(prompt_relevant) == \
        _without_experience(prompt_bare), (
        "outside the experience line the two prompts must be byte-identical,"
        " or the contrast measures the construction path as much as the"
        " experience")


def test_the_arms_keep_the_same_task_in_the_view_and_the_same_budget():
    task = _task(TARGET)
    relevant = relevant_experience(task, SAME_FAMILY, [task], BUDGET)
    bare = no_experience_experience(task, SAME_FAMILY, [task], BUDGET)

    assert relevant["task"] == bare["task"] == task
    assert relevant["remaining"] == bare["remaining"] == BUDGET
    assert relevant["view"]["task_content"] == bare["view"]["task_content"]
    assert relevant["view"]["remaining"] == bare["view"]["remaining"]


def test_the_arms_are_in_the_shape_construct_policy_accepts():
    task = _task(TARGET)
    arm = relevant_experience(task, SAME_FAMILY, [task], BUDGET)
    for key in ("boundary", "task", "observations", "retained", "remaining"):
        assert key in arm, key
    assert arm["boundary"]["seq"] == 0
    assert isinstance(arm["view"]["task_content"], dict)


def test_the_relevance_control_is_the_same_number_of_characters():
    task = _task(TARGET)
    pair = matched_experience_arms(task, SAME_FAMILY, [task],
                                   task_ids=OTHER_FAMILY, budget=BUDGET)

    assert pair["relevant_chars"] == pair["irrelevant_chars"]
    assert pair["relevant_chars"] > 0
    assert pair["condition"] == "relevant-versus-shuffled"
    assert pair["differs_in"] == "semantic-relevance-only"
    assert len(pair["relevant"]["observations"]) == \
        len(pair["irrelevant"]["observations"])

    relevant_prompt = treatment_prompt(ARM, task, pair["relevant"])
    control_prompt = treatment_prompt(ARM, task, pair["irrelevant"])
    assert relevant_prompt != control_prompt
    assert _observations_line(control_prompt) != _observations_line(
        relevant_prompt)


def _observations_line(prompt: str) -> list:
    return [line for line in prompt.splitlines()
            if line.startswith("Prior observations:")]


def test_constructing_a_size_mismatched_pair_is_refused():
    relevant = {"observations": [
        {"observation_id": "a", "task_id": "t1", "verdict": "v",
         "detail": "a much longer detail than the other one"}]}
    control = {"observations": [
        {"observation_id": "b", "task_id": "t2", "verdict": "v",
         "detail": "short"}]}

    with pytest.raises(TreatmentRefused) as caught:
        equal_length_experience_pair(relevant, control)
    assert "equal character length" in str(caught.value)
    assert equal_length_experience_pair(relevant, control, enforce=False) \
        is False


def test_the_control_constructor_refuses_rather_than_returning_a_short_arm():
    relevant = relevant_experience(
        _task(TARGET), SAME_FAMILY, [_task(TARGET)], BUDGET)

    with pytest.raises(TreatmentRefused) as caught:
        irrelevant_control_for(relevant, filler_task_ids=[])
    assert "filler pool" in str(caught.value)


def test_the_control_cannot_be_built_when_the_pool_holds_no_loadable_task():
    task = _task(TARGET)
    with pytest.raises(TreatmentRefused) as caught:
        matched_experience_arms(task, SAME_FAMILY, [task],
                                task_ids=["ad01-w9-dev-gr-99"],
                                budget=BUDGET)
    assert "filler pool" in str(caught.value)


def test_the_control_records_are_marked_so_they_miss_the_real_ids():
    task = _task(TARGET)
    pair = matched_experience_arms(task, SAME_FAMILY, [task],
                                   task_ids=OTHER_FAMILY, budget=BUDGET)
    real = {o["observation_id"] for o in pair["relevant"]["observations"]}
    control = {o["observation_id"]
               for o in pair["irrelevant"]["observations"]}
    assert control, "the control carries records"
    assert not (real & control), (
        "a control record must not claim the identity of an observation the"
        " relevant arm actually has")
    assert all(i.startswith("ctrl-") for i in control)
    assert len(control) == len(set(control)), (
        "control records need distinct ids or a basis reference names two"
        " different pieces of evidence at once")
    assert not {o["task_id"] for o in pair["irrelevant"]["observations"]} \
        & {o["task_id"] for o in pair["relevant"]["observations"]}


def test_the_control_keeps_the_real_records_it_can_and_pads_the_rest():
    """The control is real irrelevant material, not filler alone.

    A control built entirely from padding would match the relevant arm's
    length while carrying none of the content volume the contrast is
    meant to hold constant, so every record it holds names a real task of
    the other family.
    """
    task = _task(TARGET)
    pair = matched_experience_arms(task, SAME_FAMILY, [task],
                                   task_ids=OTHER_FAMILY, budget=BUDGET)
    control = pair["irrelevant"]["observations"]
    assert control, "the control carries records"
    assert all(o["task_id"] in OTHER_FAMILY for o in control), (
        "a control record must name a real task of the other family")


def test_a_relevant_arm_of_no_experience_gets_an_empty_matched_control():
    task = _task(TARGET)
    relevant = no_experience_experience(task, SAME_FAMILY, [task], BUDGET)
    control = irrelevant_control_for(relevant, filler_task_ids=OTHER_FAMILY)
    assert relevant["observations"] == []
    assert control["observations"] == []
    assert equal_length_experience_pair(relevant, control)


def test_the_equal_length_check_is_on_the_serialised_experience_itself():
    relevant = matched_experience_arms(
        _task(TARGET), SAME_FAMILY, [_task(TARGET)],
        task_ids=OTHER_FAMILY, budget=BUDGET)["relevant"]
    control = matched_experience_arms(
        _task(TARGET), SAME_FAMILY, [_task(TARGET)],
        task_ids=OTHER_FAMILY, budget=BUDGET)["irrelevant"]

    assert equal_length_experience_pair(relevant, control)
    assert packet.canonical(relevant["observations"]) != \
        packet.canonical(control["observations"])


def test_the_fill_is_reproducible_for_the_same_frozen_pool():
    task = _task(TARGET)
    first = irrelevant_control_for(
        relevant_experience(task, SAME_FAMILY, [task], BUDGET),
        OTHER_FAMILY)
    second = irrelevant_control_for(
        relevant_experience(task, SAME_FAMILY, [task], BUDGET),
        OTHER_FAMILY)
    assert packet.canonical(first["observations"]) == \
        packet.canonical(second["observations"])
