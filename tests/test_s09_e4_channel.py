"""E4's two entry points have no test, and the "no headroom" claim is a number.

`classify_revision` and `admit_revision_under_freeze` are the functions
an E4 run would call, and nothing in `tests/` names either. The module
has callers elsewhere, so it is wired rather than dead - but the two
functions that decide whether a revision is an eligible intervention are
unexercised, which means a refusal reason that has never fired is
indistinguishable from one that cannot.

Separately the status line claimed E4 has "no headroom in the channel".
That is measurable rather than rhetorical. The measurement used to be
    channel_headroom(split="dev", seeds=[0, 1, 2])
      headroom      -0.0222   a whole-cohort spread minus a half-cohort one
      noise_floor    0.0667   resample spread
      measurable    false
and asserting `headroom < 0` read as a property of the substrate. It was
not. A spread measured on n/2 samples is structurally larger than one
measured on n, so that difference was negative at every cohort size
whatever the substrate was doing, and the test was pinning an artefact of
the estimator's own sample sizes. The estimator has been rebuilt as a
paired comparison on one cohort, and the claim is now tested where it is
actually decidable: against the measured ceiling over every input the
instrument accepts. A test that would pass under a broken estimator is
worse than no test, so the assertion here is on the raw magnitude and not
on the estimator's verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel


PROSE = "I would like to improve the learner by reasoning about it."


def _view(observations=None) -> dict:
    """A view in the shape `_step_view` builds, not the shape I assumed.

    `_step_view` materialises the policy envelope and then updates it
    with the caller's view, so the real fields are `experience` and
    `frontier`. A fixture with `observations` and no `frontier` parses
    fine and every step raises inside the child, which `revision_evidence_
    choices` swallows into an empty list - so the revision is admitted as
    eligible having selected nothing. Two of these tests were passing or
    failing for that reason before the fixture came from the module.
    """
    return {
        "frontier": [{"task": "t", "capability": "c"}],
        "experience": list(observations or []),
        "authority_remaining": {"queries": 8, "steps": 6},
    }


def _probe_step(x_expression: str) -> str:
    """A revision in the vocabulary `improve_channel` actually executes.

    Two action vocabularies exist and they are disjoint:
    `policy_step.ACTION_KINDS` is the use-phase ABI
    (diagnose / construct_method / use_method / request_model /
    propose_revision / stop) and `policy_action.ACTION_KINDS` is the
    frontier one (probe / observe / construct / use / check / stop).
    A bare `{'kind': 'probe'}` is refused by `validate_step_result`, and
    the frontier action travels as `inputs.frontier_action` inside an
    outer step action - which is what `revision_evidence_choices`
    unwraps.
    """
    return (
        "def STEP(view, state):\n"
        "    task = view['task_content']['task_id']\n"
        "    if state.get('done'):\n"
        "        return {'action': {'kind': 'diagnose', 'target': task,\n"
        "                         'inputs': {}, 'evidence_refs': [],\n"
        "                         'requested_resources': {}}, 'state': state}\n"
        "    return {'action': {'kind': 'diagnose', 'target': task,\n"
        "                     'inputs': {'frontier_action': {\n"
        "                         'kind': 'probe', 'target': task,\n"
        "                         'inputs': {'x': %s, 'y': 0},\n"
        "                         'evidence_refs': [],\n"
        "                         'requested_resources': {}}},\n"
        "                     'evidence_refs': [],\n"
        "                     'requested_resources': {'queries': 1}},\n"
        "            'state': {'done': True}}\n" % x_expression)


def test_prose_is_refused_as_not_executable():
    verdict = channel.classify_revision(PROSE, views=[_view()])

    assert verdict["eligibility"] != channel.ELIGIBLE
    assert verdict["reason"]


def test_eligibility_needs_at_least_one_learner_view():
    """Decided before the revision is measured, so an empty boundary refuses.

    A revision eligible under no view has never been shown to choose
    anything; admitting it would measure the channel rather than a
    revision of it.
    """
    verdict = channel.classify_revision(_probe_step("0"), views=[])

    assert verdict["eligibility"] != channel.ELIGIBLE
    assert "view" in verdict["reason"]


def test_a_fixed_input_is_refused_as_a_solver_not_a_selector():
    """The refusal that matters most for E4: answering, not observing.

    A revision that probes a constant picks the same x whatever the
    learner has seen. It might well score well, and admitting it would
    credit the improve round with a fixed guess.
    """
    verdict = channel.classify_revision(
        _probe_step("3"), views=[_view()])

    assert verdict["eligibility"] == channel.INELIGIBLE_SOLVER


def test_a_data_dependent_input_is_admitted_as_eligible():
    """The mirror of the previous test, so the guard is a real check.

    Without this, a guard that refused everything would pass. A
    `reason` key appears only on a refusal - the eligible verdict
    carries `selected_evidence` instead - so this asserts on the
    eligibility key rather than on the absence of a complaint.
    """
    data_dependent = _probe_step("view['experience'][0]['x']")

    verdict = channel.classify_revision(
        data_dependent, views=[_view([{"x": 2, "y": 1}])])

    assert verdict["eligibility"] == channel.ELIGIBLE, (
        "a revision that reads the learner's own observations is a "
        "selector and was refused: %r" % (verdict,))
    assert verdict["informs_decision"] is True


def test_an_admitted_revision_really_selects_evidence():
    """The verdict's own payload must be non-empty.

    `revision_evidence_choices` catches every exception from the step and
    `break`s, so a revision whose bytes fail validation returns an empty
    list rather than raising. `classify_revision` admits on eligibility
    and reports that list verbatim - so a revision that selects nothing
    is admitted as eligible, having selected nothing, and a caller that
    trusted `informs_decision` would read it as a working improvement.

    This is the same class of bug as the world's task-id leak: the
    verdict is well formed and carries a claim that is false. It is
    latent rather than active - nothing in the tree reads
    `selected_evidence` or `informs_decision` yet, because E4 has no
    caller - so the fix belongs wherever the first consumer appears.
    """
    verdict = channel.classify_revision(
        _probe_step("view['experience'][0]['x']"),
        views=[_view([{"x": 2, "y": 1}])])

    assert verdict["selected_evidence"] == [[2]], (
        "an admitted revision selected %r; the step is failing and the "
        "empty list is being reported as a decision"
        % (verdict.get("selected_evidence"),))


def test_a_refusal_carries_a_reason_and_an_admission_does_not():
    """The two verdict shapes, so neither is read as the other.

    `_refused` sets `reason` to a detail string while the eligible path
    sets `selected_evidence`. A caller that reads `verdict["reason"]`
    unconditionally raises on every admitted revision, and a caller
    that reads `verdict.get("reason", "eligible")` reports an admitted
    revision as having no stated reason. Both are wrong and neither
    shows up unless the two shapes are pinned.
    """
    admitted = channel.classify_revision(
        _probe_step("view['experience'][0]['x']"),
        views=[_view([{"x": 2, "y": 1}])])
    refused = channel.classify_revision(
        _probe_step("3"), views=[_view()])

    assert "reason" not in admitted
    assert refused["reason"]


def test_the_channel_has_no_measurable_headroom():
    """Why E4 is blocked, against the measured ceiling rather than a sign.

    The claim under test is that no input the instrument accepts beats the
    incumbent by more than the ceiling. That is decidable from the
    estimator's own raw magnitude, so this asserts on `delta` and on the
    incumbent's own mean, and not on `measurable`. An estimator that
    cannot report a positive number would also pass a `measurable is
    False` assertion, which is why the previous version of this test was
    removed rather than re-run: it asserted the output of an instrument
    that could not return the other answer.

    The ceiling is 0.00267 over 1500 seeds, measured on the same cohort
    as the artifact's paired difference, so a revision that beat the
    incumbent by more than that would be a real effect and this fails.
    """
    headroom = channel.channel_headroom(split="dev", seeds=list(range(400)))
    ceiling = 0.00267

    assert headroom["delta"] <= ceiling, (
        "the best reachable probe beats the incumbent by %.5f, which is "
        "above the measured ceiling of %.5f over every input the instrument "
        "accepts, so the channel does have reachable headroom and E4 is no "
        "longer blocked: %r" % (headroom["delta"], ceiling, headroom))
    assert headroom["incumbent_mean"] > 0.0, (
        "the incumbent scored nothing on this cohort, so nothing here is a "
        "measurement of anything: %r" % (headroom,))
    assert headroom["delta"] <= headroom["paired_se"], (
        "the paired gap %.5f exceeds its own standard error %.5f on %d "
        "seeds, so the channel does carry a reachable effect: %r" % (
            headroom["delta"], headroom["paired_se"], headroom["n"],
            headroom))


def test_the_noise_floor_is_not_the_headroom_measurement():
    """The old estimator's two terms are not silently the same quantity.

    `noise_floor` splits a cohort and recomputes the reachable range on
    each half, so `resample_spread` is a spread measured on n/2 samples.
    It is a useful diagnostic and it is still here. It is not a
    comparison partner for a spread measured on n seeds, and the rebuilt
    `channel_headroom` no longer uses it. This pins the separation so the
    two cannot drift back into being subtracted from one another.
    """
    floor = channel.noise_floor(split="dev", seeds=[0, 1, 2])
    headroom = channel.channel_headroom(split="dev", seeds=[0, 1, 2])

    assert floor["half_a"]["n"] + floor["half_b"]["n"] == floor["n"], (
        "the two halves no longer account for the whole cohort, so "
        "`noise_floor` is measuring something other than the cohort it was "
        "given: %r" % (floor,))
    assert floor["half_a"]["n"] < floor["n"], (
        "a half-cohort measurement has been replaced by a whole one, so "
        "`noise_floor` can no longer be the diagnostic it documents: %r"
        % (floor,))
    assert "noise_floor" not in headroom, (
        "channel_headroom is comparing against a half-cohort measurement "
        "again, which is the defect: %r" % (headroom,))
    assert "reachable_spread" not in headroom, (
        "channel_headroom is reporting the whole-cohort term that was "
        "being compared against the half-cohort one: %r" % (headroom,))
