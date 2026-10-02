"""E2 experience arms carry no held-out answer, and the freeze catches edits.

An answer leaking into either arm is a third condition nobody declared:
the arms would no longer differ in relevance, they would differ in
whether one of them already knew the result. The canary is planted in a
task's real private side, so a leak is a real leak rather than a search
for a marker that was never anywhere to be found.
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
from experiments.ad01.learner import canary_task
from experiments.ad01.learner import held_out_canary
from experiments.ad01.learner import matched_experience_arms
from experiments.ad01.learner import no_experience_experience
from experiments.ad01.learner import relevant_experience
from experiments.ad01.learner import require_no_held_out_answers
from experiments.ad01.learner import treatment_freeze
from experiments.ad01.learner import treatment_prompt
from experiments.ad01.learner import verify_treatment_freeze

TARGET = "ad01-w1-dev-sw-01"
SAME_FAMILY = ["ad01-w1-dev-sw-00", "ad01-w1-dev-sw-02"]
OTHER_FAMILY = ["ad01-w%d-dev-gr-0%d" % (world, index)
                for world in (0, 1, 2) for index in range(3)]
BUDGET = {"model_calls": 2, "queries": 8, "steps": 4}
ARM = {"family": "software", "budget": BUDGET}
CANARY = "canary-7f3a-held-out-answer"


def _task(task_id: str = TARGET) -> dict:
    return worlds.load_task(worlds.FROZEN_DIR, task_id)


def _pair(task: dict) -> dict:
    return matched_experience_arms(task, SAME_FAMILY, [task],
                                   task_ids=OTHER_FAMILY, budget=BUDGET)


def test_the_held_out_values_are_derived_not_guessed():
    """The held-out side is the difference between the two task views.

    `packet.public_task_view` is an allowlist, so the private side is
    whatever it drops. Naming the keys instead would be right about the
    software family and silently wrong about the graph one.
    """
    task = _task()
    assert "stale-clear" not in packet.held_out_values(task), (
        "this generator derives the fault name from the template, so the"
        " fault string is a substring of a public field and is not held"
        " out in any sense that matters")
    assert packet.held_out_values(_task("ad01-w1-dev-gr-00")) == []


def test_a_value_the_public_view_already_shows_is_not_held_out():
    """A leak check must not fire on the task's own visible content.

    The fault name is derivable from the public template, so treating it
    as an answer would refuse every arm, including one with no
    experience, and a gate that refuses everything is a gate nobody
    trusts.
    """
    task = _task()
    assert task["fault"] in task["template"]
    assert packet.leaked_answers(
        "family %s template %s" % (task["family"], task["template"]),
        task) == []


def test_a_canary_planted_in_the_private_side_is_actually_found():
    task = canary_task(_task(), CANARY)
    assert CANARY in packet.held_out_values(task)
    assert CANARY not in packet.canonical(packet.public_task_view(task))
    assert packet.leaked_answers("the answer is %s" % CANARY,
                                 task) == [CANARY]


def test_a_two_character_needle_is_not_treated_as_a_leak():
    """A short needle is a substring of ordinary text, not evidence.

    Matching on one would refuse every arm rather than the leaking one,
    and a gate that refuses everything is a gate nobody trusts.
    """
    assert "v3" not in packet.held_out_values(_task())


def test_the_guard_fires_on_a_canary_planted_in_what_a_model_reads():
    """The guard is proved against a needle, not just declared to work.

    A guard that has never been shown a canary has been shown nothing,
    and one that cannot see the canary is not looking in the right place.
    """
    task = canary_task(_task(), CANARY)
    arm = {**no_experience_experience(task, SAME_FAMILY, [task], BUDGET),
           "view": {"task_content": {"task_id": TARGET,
                                     "solution": CANARY}}}
    with pytest.raises(TreatmentRefused) as caught:
        require_no_held_out_answers({"relevant": arm}, task)
    assert CANARY in str(caught.value)


def test_neither_arm_carries_the_held_out_answer():
    task = _task()
    pair = _pair(task)
    for name in ("relevant", "irrelevant"):
        rendered = treatment_prompt(ARM, task, pair[name])
        assert packet.leaked_answers(rendered, task) == [], (
            "the %s arm quotes the held-out answer" % name)
    require_no_held_out_answers(pair, task)


def test_the_guard_refuses_a_leaking_control_and_names_the_value():
    task = canary_task(_task(), CANARY)
    pair = _pair(task)
    leaking = {**pair["irrelevant"],
               "observations": list(pair["irrelevant"]["observations"])
               + [{"observation_id": "ctrl-canary",
                   "task_id": TARGET, "capability_id": "ad01-sw",
                   "verdict": "not-preserved", "detail": CANARY}]}
    with pytest.raises(TreatmentRefused) as caught:
        require_no_held_out_answers({"irrelevant": leaking}, task)
    assert CANARY in str(caught.value)


def test_a_leak_in_the_relevant_arm_is_refused_too():
    """A leak in the benchmark arm is the same defect as one in the control.

    The point of the contrast is that neither arm knows the answer, so
    checking only the control would leave the relevant arm free to answer
    rather than reason.
    """
    task = canary_task(_task(), CANARY)
    arm = relevant_experience(task, SAME_FAMILY, [task], BUDGET)
    leaking = {**arm,
               "observations": list(arm["observations"])
               + [{"observation_id": "obs-canary", "task_id": TARGET,
                   "capability_id": "ad01-sw", "verdict": "not-preserved",
                   "detail": CANARY}]}
    with pytest.raises(TreatmentRefused) as caught:
        require_no_held_out_answers({"relevant": leaking}, task)
    assert CANARY in str(caught.value)


def test_the_canary_is_derived_from_the_task_not_hard_coded():
    task = _task()
    marker = held_out_canary(task)
    assert marker in packet.held_out_values(task)
    assert marker not in packet.canonical(packet.public_task_view(task))
    assert canary_task(task)["witness"]["canary"] == marker


def test_a_task_with_nothing_held_out_still_gets_a_needle():
    """A graph task holds no private answer, and still needs a proof.

    Without a needle the guard would have nothing to fire on for that
    family, and a check that cannot fail there has not cleared it.
    """
    graph = _task("ad01-w1-dev-gr-00")
    assert packet.held_out_values(graph) == []
    assert held_out_canary(graph) == ""
    planted = canary_task(graph)
    assert planted["witness"]["canary"] in packet.held_out_values(planted)
    assert packet.leaked_answers(planted["witness"]["canary"],
                                 planted) == [planted["witness"]["canary"]]


def test_the_freeze_is_content_addressed_and_survives_a_round_trip():
    task = _task()
    freeze = treatment_freeze(study_id="e2", pairs={"relevance":
                                                    _pair(task)}, uses=6)

    assert freeze["freeze_digest"] == treatment_freeze(
        study_id="e2", pairs={"relevance": _pair(task)},
        uses=6)["freeze_digest"]
    assert verify_treatment_freeze(freeze) == freeze


def test_altering_a_treatment_is_detected_by_the_freeze():
    task = _task()
    pair = _pair(task)
    freeze = treatment_freeze(study_id="e2", pairs={"relevance": pair},
                               uses=6)
    altered = {**pair, "irrelevant": {**pair["irrelevant"],
                                      "remaining": {"model_calls": 99}}}
    tampered = {**freeze, "pairs": {**freeze["pairs"],
                                    "relevance": altered}}

    with pytest.raises(TreatmentRefused) as caught:
        verify_treatment_freeze(tampered)
    assert "freeze_digest" in str(caught.value)


def test_changing_the_declared_number_of_uses_is_detected():
    """The use count is part of what the cost claim is about.

    A freeze that let it move after the fact would let a cold-reacquisition
    arm be re-costed against a number chosen after seeing the outcomes.
    """
    task = _task()
    freeze = treatment_freeze(study_id="e2", pairs={"relevance":
                                                    _pair(task)}, uses=6)

    with pytest.raises(TreatmentRefused) as caught:
        verify_treatment_freeze({**freeze, "uses": 40})
    assert "freeze_digest" in str(caught.value)


def test_a_stamp_outside_the_identity_does_not_break_the_digest():
    """A wall-clock field must not make an identical freeze look altered.

    The campaign's own verifier already had to learn that lesson, and a
    freeze that cannot be reproduced by re-freezing the same content is
    not a freeze.
    """
    task = _task()
    early = treatment_freeze(study_id="e2", pairs={"relevance":
                                                   _pair(task)}, uses=6,
                             frozen_at="2026-09-26T00:00:00Z")
    late = treatment_freeze(study_id="e2", pairs={"relevance": _pair(task)},
                            uses=6, frozen_at="2027-01-01T00:00:00Z")

    assert early["freeze_digest"] == late["freeze_digest"]
    assert verify_treatment_freeze(early) == early
    assert verify_treatment_freeze(late) == late


def test_a_freeze_needs_a_positive_declared_number_of_uses():
    task = _task()
    for bad in (0, -1, "6", None, 2.5):
        with pytest.raises(TreatmentRefused) as caught:
            treatment_freeze(study_id="e2", pairs={"relevance":
                                                   _pair(task)}, uses=bad)
        assert "uses" in str(caught.value)


def test_a_freeze_with_nothing_in_it_is_refused():
    task = _task()
    with pytest.raises(TreatmentRefused) as caught:
        treatment_freeze(study_id="", pairs={"a": _pair(task)}, uses=6)
    assert "identity" in str(caught.value)

    with pytest.raises(TreatmentRefused) as caught:
        treatment_freeze(study_id="e2", pairs={}, uses=6)
    assert "contrast" in str(caught.value)
