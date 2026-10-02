"""E4's remediation: the headroom estimator and the admission verdict.

Two defects are fixed here, and the tests are the reason they are fixed.

`channel_headroom` compared a spread measured on the whole cohort against a
spread measured on halves of it. A spread over n/2 samples is structurally
larger than a spread over n, so `headroom < 0` held at every cohort size
whatever the substrate was doing. The number was an artefact of the
estimator's own sample sizes. It is now a paired comparison of the best
reachable probe against the incumbent on one cohort, which is the quantity
the claim is actually about.

`classify_revision` returned `informs_decision: True` as a literal. A
revision whose bytes fail to execute selects no evidence and is admitted as
having made a decision. The flag is now derived from the payload rather
than asserted beside it.

The invariant in force throughout is that the honest negative must survive.
`tests/test_s09_e4_channel.py` and `tests/test_s09_e4_evidence.py` both
assert that no reachable probe beats the incumbent by more than the
measured ceiling. If either one of them has to be weakened to accommodate
this fix, the fix is wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel


# The cohort the evidence artifact uses for the measurement that
# discriminates, and the z a difference would have to clear to count.
REFERENCE_N = 1500
REFERENCE_Z = 1.96


def test_the_estimator_no_longer_compares_a_whole_cohort_against_its_halves():
    """The defect, stated as a property of the reported numbers.

    The old `headroom` was `reachable_spread - noise_floor`, where
    `reachable_spread` came from all n seeds and `noise_floor` from halves.
    Both terms shrink together as the cohort grows, so the difference
    stayed negative. The corrected estimator reports the paired difference
    between the best reachable probe and the incumbent on the same n seeds,
    so both terms are measured on the same sample and the comparison is
    like against like.
    """
    report = channel.channel_headroom(split="dev", seeds=list(range(24)))

    assert "reachable_spread" not in report, (
        "the report still carries a whole-cohort spread, which is the term "
        "that was being compared against a half-cohort one: %r" % (report,))
    assert "noise_floor" not in report, (
        "the report still carries a half-cohort resample spread, which is "
        "not the same measurement as the whole-cohort one: %r" % (report,))
    assert report["estimator"] == "paired best-reachable vs incumbent"
    assert report["half_cohort_comparison"] is False


def test_the_paired_estimate_matches_the_measurement_the_artifact_records():
    """The corrected estimator on the cohort that decides the question.

    The evidence artifact scored both reachable descendants on 1500 seeds
    and recorded -0.00138 with a standard error of 0.00123, which is the
    measurement that discriminates. The estimator is run here on the same
    cohort, and the two must agree on the conclusion: the gap is far
    inside any effect worth claiming.

    The exact value is not compared. The estimator splits the cohort to
    hold out the probe choice, and the artifact did not, so they are
    different estimators over the same cohort. The artefact's own
    `z` is -1.12, which is the number to compare against, and this
    requires the rebuilt estimator to be in the same place rather than to
    match to the last digit.
    """
    seeds = list(range(REFERENCE_N))
    report = channel.channel_headroom(split="dev", seeds=seeds)

    assert abs(report["delta"]) < 0.02, (
        "the paired best-versus-incumbent gap is %.5f on %d seeds; a gap "
        "this size would be a reachable effect, and the substrate is not "
        "what the evidence says it is: %r" % (
            report["delta"], REFERENCE_N, report))
    assert report["measurable"] is False, (
        "the channel was reported as measurable on the cohort that the "
        "artifact records as showing no reachable effect: %r" % (report,))
    if report["z"] is not None:
        assert abs(report["z"]) < REFERENCE_Z, (
            "the paired difference %.5f is %.2f standard errors from zero on "
            "%d seeds, so the channel does carry a reachable effect after "
            "all: %r" % (report["delta"], abs(report["z"]), REFERENCE_N,
                         report))
    else:
        assert report["delta"] == 0.0, (
            "the paired difference has no standard error because it is "
            "identically zero, and it is reported as %r" % (
                report["delta"],))


def test_the_measurement_is_carried_out_before_it_is_decided():
    """The best probe is chosen on one half and scored on the other.

    Picking the argmax of sixteen means over n seeds and then testing that
    same argmax on those same n seeds is a selection effect, and a
    channel with any range at all would be reported as measurable by it.
    The incumbent mean and the best-probe mean come from disjoint halves of
    the cohort, so the number being tested was not the number the choice
    was made from. This pins that: the two roles have to be reported
    separately, and each has to hold half the cohort.
    """
    seeds = list(range(REFERENCE_N))
    report = channel.channel_headroom(split="dev", seeds=seeds)

    assert set(report["split_half"]) == {"select", "score"}, (
        "the two roles are not reported separately, so the selection and "
        "the test cannot be told apart: %r" % (sorted(report["split_half"]),))
    for role in ("select", "score"):
        half = report["split_half"][role]
        assert half["n"] == REFERENCE_N // 2, (
            "the %r half is %d seeds, not half the cohort; the comparison is "
            "no longer like against like" % (role, half["n"]))
        assert 0 <= half["seeds"][0] <= half["seeds"][-1] < REFERENCE_N


def _substrate_with_a_real_effect():
    """The real module with one probe input made worth choosing.

    A revision's only lever is choosing a better probe, so the way to ask
    whether the estimator can see a real effect is to give it a substrate
    where one probe really is better than another. `_STRATEGY_EVIDENCE`
    is what `leaf_construct` installs and what the incumbent gathers, so
    remapping it to two inputs that differ is a change to the substrate
    and not a change to the estimator's plumbing.
    """
    module = sys.modules[channel.__name__]
    saved = module._STRATEGY_EVIDENCE.copy()
    low, high = saved["low"], saved["high"]
    module._STRATEGY_EVIDENCE["low"] = 16
    original = module._strategy_descendant

    def planted(strategy, split, seed):
        if strategy == "low":
            return module.descendant_score(
                list(channel.GENERAL_POSITION), split, int(seed))
        return original(strategy, split, seed)

    module._strategy_descendant = planted
    return module, low, high, lambda: (
        module._STRATEGY_EVIDENCE.update(saved),
        setattr(module, "_strategy_descendant", original))


def test_a_substrate_with_a_real_effect_is_reported_as_measurable():
    """The mirror, so `measurable` is a measurement and not a constant.

    The old estimator could not return true at any cohort size, so the
    flag was structural. This plants an effect in the substrate and
    requires the corrected estimator to find it. A `measurable` that
    stayed false here would mean the flag is still reporting the
    estimator's shape rather than the substrate.
    """
    module, low, high, restore = _substrate_with_a_real_effect()
    try:
        report = module.channel_headroom(split="dev", seeds=list(range(48)))
    finally:
        restore()

    assert report["reachable_evidence"] == [str(low), str(high)], (
        "the reachable menu moved, so the planted effect is not where the "
        "estimator looks: %r" % (report,))
    assert report["incumbent_mean"] < report["best_mean"], (
        "the incumbent was not made worse, so there is no real effect to "
        "find: %r" % (report,))
    assert report["delta"] > 0.0, (
        "a probe that really is better than the incumbent read as a "
        "non-positive paired gap, so the estimator is still inverted: %r"
        % (report,))
    assert report["measurable"] is True, (
        "a real effect inside the reachable set was reported as not "
        "measurable: %r" % (report,))


def test_a_gap_inside_its_own_noise_is_not_reported_as_measurable():
    """The second guard, shown to refuse a genuinely positive gap.

    `measurable` is two claims. The best probe has to beat the incumbent,
    and the gap has to exceed its own standard error. The second is what
    stops the first from being free: a gap that is positive purely because
    the cohort is small is not a measurement, and a flag that reported one
    would be reporting the cohort size.

    This is a real point in the space rather than a contrivance. The
    incumbent is a descendant the instrument refuses every input to, so
    the frozen reducer falls back to its default predictor and still gets
    one sixteenth of the unqueried inputs right. Every reachable probe
    beats that on this cohort, and the gap is small enough to be inside
    its own standard error, so the flag has to go back to false.
    """
    report = channel.channel_headroom(
        split="dev", seeds=list(range(48)), incumbent_evidence=(16,))

    assert report["incumbent_evidence"] not in (
            report["reachable_evidence"]), (
        "the incumbent is inside the menu, so this is not the out-of-menu "
        "case: %r" % (report,))
    assert report["best_beats_incumbent"] is True, (
        "the best probe did not beat the out-of-menu incumbent, so the "
        "noise guard has nothing to refuse: %r" % (report,))
    assert report["delta"] > 0.0, (
        "the gap is not positive, so this is not the case the noise guard "
        "is for: %r" % (report,))
    assert report["delta"] < report["paired_se"], (
        "the gap clears its own standard error, so the noise guard has "
        "nothing to refuse: %r" % (report,))
    assert report["measurable"] is False, (
        "a gap that its own standard error does not clear was reported as "
        "a measurement: %r" % (report,))


def test_the_old_estimator_would_have_missed_the_planted_effect():
    """The demonstration: the same comparison, the broken way, on one run.

    With an effect planted in the substrate, the old comparison still
    reports a negative headroom and `measurable: false`, because the
    resample spread of two half-cohorts is structurally larger than any
    spread measured on the whole. That is the defect the fix removes. The
    flag was reporting sample size, not substrate.

    A re-aimed test that passes under the old estimator would be a
    deletion rather than a re-aim, so this pins the difference on the
    very inputs where the two disagree.
    """
    module, low, high, restore = _substrate_with_a_real_effect()

    def broken(split, seeds) -> dict:
        seeds = list(seeds)
        means = {p: module.evaluate_lineage(
            [p], split=split, seeds=seeds)["mean"] for p in range(16)}
        halves = []
        for half in (seeds[0::2], seeds[1::2]):
            half_means = [module.evaluate_lineage(
                [p], split=split, seeds=half)["mean"] for p in range(16)]
            halves.append(max(half_means) - min(half_means))
        return {"reachable_spread": max(means.values()) - min(means.values()),
                "noise_floor": max(halves),
                "headroom": (max(means.values()) - min(means.values())
                             - max(halves)),
                "measurable": (max(means.values()) - min(means.values())
                               > max(halves))}

    seeds = list(range(48))
    try:
        real_broken = broken("dev", seeds)
        real_fixed = module.channel_headroom(split="dev", seeds=seeds)
    finally:
        restore()

    assert real_fixed["measurable"] is True, (
        "the fixed estimator did not recover the planted effect, so this "
        "demonstration has nothing to contrast: %r" % (real_fixed,))
    assert real_broken["measurable"] is False, (
        "the old estimator now saw the planted effect, so this file's "
        "diagnosis of the defect is wrong: %r" % (real_broken,))
    assert real_broken["headroom"] < 0.0
    assert real_broken["reachable_spread"] < real_broken["noise_floor"], (
        "the broken comparison is supposed to lose to its own half-cohort "
        "resample spread, and it did not: %r" % (real_broken,))


def test_a_non_empty_evidence_set_is_what_makes_the_admission_say_it_informed():
    """N-26. The flag is derived, not declared.

    `classify_revision` returned `"informs_decision": True` as a literal,
    after the eligibility checks and before anything had been measured. A
    revision whose bytes fail to execute selects no evidence at all and
    was still reported as having informed a decision. Nothing consumed the
    flag yet, so the defect was latent; any future E4 run has to inherit
    the fix rather than the literal.
    """
    healthy = channel.classify_revision(
        "def STEP(view, state):\n"
        "    x = view['experience'][0]['x']\n"
        "    task = view['task_content']['task_id']\n"
        "    if state.get('done'):\n"
        "        return {'action': {'kind': 'diagnose', 'target': task,\n"
        "                         'inputs': {}, 'evidence_refs': [],\n"
        "                         'requested_resources': {}},\n"
        "                'state': state}\n"
        "    return {'action': {'kind': 'diagnose', 'target': task,\n"
        "                     'inputs': {'frontier_action': {\n"
        "                         'kind': 'probe', 'target': task,\n"
        "                         'inputs': {'x': x, 'y': 0},\n"
        "                         'evidence_refs': [],\n"
        "                         'requested_resources': {}}},\n"
        "                     'evidence_refs': [],\n"
        "                     'requested_resources': {'queries': 1}},\n"
        "            'state': {'done': True}}\n",
        views=[{"frontier": [{"task": "t", "capability": "c"}],
                "experience": [{"x": 2, "y": 1}],
                "authority_remaining": {"queries": 8, "steps": 6}}])

    assert healthy["eligibility"] == channel.ELIGIBLE
    assert healthy["selected_evidence"] == [[2]], (
        "the healthy fixture selected %r, so the two arms of this test are "
        "not comparable" % (healthy["selected_evidence"],))
    assert healthy["informs_decision"] is True, (
        "a revision that selected evidence was reported as not informing "
        "anything: %r" % (healthy,))

    silent = channel.classify_revision(
        "def STEP(view, state):\n"
        "    x = view['experience'][0]['x']\n"
        "    if view.get('experience'):\n"
        "        probe = {'kind': 'probe', 'inputs': {'x': x, 'y': 0}}\n"
        "        raise RuntimeError('the step never reaches the return')\n"
        "    return {'action': {'kind': 'diagnose', 'target': 't',\n"
        "                     'inputs': {}, 'evidence_refs': [],\n"
        "                     'requested_resources': {}},\n"
        "            'state': state}\n",
        views=[{"frontier": [{"task": "t", "capability": "c"}],
                "experience": [{"x": 2, "y": 1}],
                "authority_remaining": {"queries": 8, "steps": 6}}])

    assert silent["eligibility"] == channel.ELIGIBLE, (
        "eligibility is unchanged by the flag repair and the test should "
        "not be asserting on it: %r" % (silent,))
    assert silent["selected_evidence"] == [[]], (
        "the premise of this test is that the bytes select nothing and are "
        "still admitted: %r" % (silent,))
    assert silent["informs_decision"] is False, (
        "a revision that selected no evidence reported that it informed a "
        "decision: %r" % (silent,))
