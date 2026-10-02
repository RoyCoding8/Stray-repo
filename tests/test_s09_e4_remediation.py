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


def _planted_effect(gain_input, spread):
    """The real substrate with one reachable input made worth choosing.

    A revision's only lever is choosing a better probe, so the way to ask
    whether the estimator can see a real effect is to give it a substrate
    where one probe really is better than another. The lever is the
    substrate's own scorer rather than a published table of what each
    strategy gathers: `_STRATEGY_EVIDENCE` is gone, because a descendant
    is now built from its parent's bytes and what it gathers is derived
    from the evidence the round observed (`construction_from_evidence`)
    rather than resolved from a two-member dict.

    The gain varies with the seed. That is deliberate and it is what makes
    the planted case worth having. A constant gain would make the paired
    difference identical on every seed, the standard error would be
    exactly zero, and `measurable` would pass on a number its own noise
    could never contradict. A gain that varies gives the planted effect a
    real standard error, so the flag has to clear it on magnitude the way
    it would have to clear any other effect's.
    """
    module = sys.modules[channel.__name__]
    scored = module.descendant_score

    def planted(evidence, split, seed):
        score = scored(list(evidence), split, int(seed))
        if int(evidence[-1]) != gain_input:
            return score
        return {**score, "unqueried": score["unqueried"] + spread(
            int(seed))}

    return module, scored, planted


def _broken_comparison(module):
    """The old estimator, rebuilt locally so this file can contrast with it."""
    def broken(split, seeds) -> dict:
        seeds = list(seeds)
        means = {p: module.evaluate_lineage(
            [p], split=split, seeds=seeds)["mean"] for p in range(16)}
        halves = []
        for half in (seeds[0::2], seeds[1::2]):
            half_means = [module.evaluate_lineage(
                [p], split=split, seeds=half)["mean"] for p in range(16)]
            halves.append(max(half_means) - min(half_means))
        spread = max(means.values()) - min(means.values())
        return {"reachable_spread": spread, "noise_floor": max(halves),
                "headroom": spread - max(halves),
                "measurable": spread > max(halves)}
    return broken


#: The reachable input the planted effect is worth choosing, and a gain that
#: varies with the seed. `spread` is the whole of the planting: four seeds in
#: five gain 1, the fifth gains 2, so the effect is real on every seed and
#: carries a standard error.
GAINED_INPUT = 6
GAIN = {True: 2, False: 1}


def _gains(seed: int) -> int:
    return GAIN[seed % 5 == 0]


def test_a_substrate_with_a_real_effect_is_reported_as_measurable():
    """The mirror, so `measurable` is a measurement and not a constant.

    The old estimator could not return true at any cohort size, so the
    flag was structural. This plants an effect in the substrate and
    requires the corrected estimator to find it. A `measurable` that
    stayed false here would mean the flag is still reporting the
    estimator's shape rather than the substrate.
    """
    module, scored, planted = _planted_effect(GAINED_INPUT, _gains)
    module.descendant_score = planted
    try:
        report = module.channel_headroom(split="dev", seeds=list(range(48)))
    finally:
        module.descendant_score = scored

    assert report["reachable_evidence"] == [
        str(x) for x in channel.INCUMBENT_EVIDENCE], (
        "reachable_evidence is what the incumbent's own bytes probe, and it "
        "no longer reports a menu a construction can install from, so it "
        "has moved: %r" % (report,))
    assert report["best_probe"] == GAINED_INPUT, (
        "the estimator chose %r rather than the planted input, so the "
        "planted effect is not where the estimator looks: %r"
        % (report["best_probe"], report))
    assert report["incumbent_mean"] < report["best_mean"], (
        "the incumbent was not made worse, so there is no real effect to "
        "find: %r" % (report,))
    assert report["delta"] > 0.0, (
        "a probe that really is better than the incumbent read as a "
        "non-positive paired gap, so the estimator is still inverted: %r"
        % (report,))
    assert report["paired_se"] > 0.0, (
        "the planted gain is identical on every seed, so the paired "
        "difference has no standard error and `measurable` would be "
        "reading a constant rather than a measurement: %r" % (report,))
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

    This is a real point in the space rather than a contrivance, and it no
    longer needs an out-of-menu incumbent to reach. The descendant the
    incumbent inherits probes input 3 and gathers one observation, so every
    reachable probe differs from it only in the evidence it ends up with.
    Probe 6 does beat it on this cohort, by less than its own standard
    error, so the flag has to go back to false.

    It used to ask for incumbent `(16,)`, an input the instrument refuses,
    which made the gap come from a descendant no construction can install.
    That point has moved: the incumbent is `INCUMBENT_EVIDENCE` and a
    cohort of 48 puts the real gap inside its own noise. Cohort 96 is
    checked too, so the assertion is not balanced on one cohort size. At 48
    the old `(16,)` gap now clears its own standard error by 2%, which is
    why that fixture can no longer demonstrate the guard at all.
    """
    for cohort in (48, 96):
        report = channel.channel_headroom(
            split="dev", seeds=list(range(cohort)))

        assert report["incumbent_evidence"] == list(
            channel.INCUMBENT_EVIDENCE), (
            "the incumbent is no longer the one the construction installs, "
            "so this is not the case the noise guard is about: %r"
            % (report,))
        assert report["best_beats_incumbent"] is True, (
            "the best probe did not beat the incumbent, so the noise guard "
            "has nothing to refuse on %d seeds: %r" % (cohort, report))
        assert report["delta"] > 0.0, (
            "the gap is not positive, so this is not the case the noise "
            "guard is for on %d seeds: %r" % (cohort, report))
        assert report["delta"] < report["paired_se"], (
            "the gap clears its own standard error on %d seeds, so the "
            "noise guard has nothing to refuse: %r" % (cohort, report))
        assert report["measurable"] is False, (
            "a gap that its own standard error does not clear was reported "
            "as a measurement on %d seeds: %r" % (cohort, report))


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
    module, scored, planted = _planted_effect(GAINED_INPUT, _gains)
    broken = _broken_comparison(module)

    seeds = list(range(48))
    module.descendant_score = planted
    try:
        real_broken = broken("dev", seeds)
        real_fixed = module.channel_headroom(split="dev", seeds=seeds)
    finally:
        module.descendant_score = scored

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


#: Two revisions of the channel's own improvement source, each differing
#: from it only at the probed input, which is the one decision a revision is
#: authorised to move. `INHERITS` reads the learner's last observation, so it
#: probes what the view carries. `MUTES` reads that observation's bits, so
#: the step runs, returns an action, and selects no probe input at all.
INHERITS = channel.IMPROVE_LOW_SOURCE.replace(
    '{"kind": "probe", "inputs": {"x": 3},',
    '{"kind": "probe", "inputs": {"x": view["experience"][-1]["x"]},')
MUTES = channel.IMPROVE_LOW_SOURCE.replace(
    '{"kind": "probe", "inputs": {"x": 3},',
    '{"kind": "probe", "inputs": {"x": view["experience"][-1]["y"]},')

SEEDED_VIEWS = [{"frontier": [{"task": "t", "capability": "c"}],
                 "experience": [{"x": 2, "y": [1, 0, 0, 1]}],
                 "authority_remaining": {"queries": 8, "steps": 6}}]


def test_a_non_empty_evidence_set_is_what_makes_the_admission_say_it_informed():
    """N-26. The flag is derived, not declared.

    `classify_revision` returned `"informs_decision": True` as a literal,
    after the eligibility checks and before anything had been measured. A
    revision whose bytes fail to execute selects no evidence at all and
    was still reported as having informed a decision. Nothing consumed the
    flag yet, so the defect was latent; any future E4 run has to inherit
    the fix rather than the literal.

    Both fixtures are revisions of `IMPROVE_LOW_SOURCE` moving nothing but
    the probed input, because eligibility is now a property of the bytes. A
    revision that changed the allocation, the construction or the step
    skeleton is refused as `changes-an-unauthorised-decision` before
    `informs_decision` is ever read, and the pair this test used to carry
    was written before that check existed. It was refused at the eligibility
    assertion rather than exercising the flag at all.

    The two arms still differ in the only way that matters here. One is
    admissible and probes; it selects evidence, so it informs. The other is
    admissible and probes nothing, because it runs and picks something that
    is not a probe input; it is admitted on the strength of its static shape
    having selected nothing, and reporting that as a decision would be the
    verdict asserting a measurement it never made.
    """
    for fixture in (INHERITS, MUTES):
        assert channel.unauthorised_change(
            channel.IMPROVE_LOW_SOURCE, fixture) == {}, (
            "the fixture moves a decision the interface does not authorise, "
            "so eligibility would refuse it before `informs_decision` is "
            "read: %r" % (channel.unauthorised_change(
                channel.IMPROVE_LOW_SOURCE, fixture),))

    healthy = channel.classify_revision(INHERITS, views=SEEDED_VIEWS)

    assert healthy["eligibility"] == channel.ELIGIBLE, (
        "the healthy fixture was refused as %r, so the two arms of this "
        "test are not comparable" % (healthy["eligibility"],))
    assert healthy["selected_evidence"] == [[2]], (
        "the healthy fixture selected %r, so the two arms of this test are "
        "not comparable" % (healthy["selected_evidence"],))
    assert healthy["informs_decision"] is True, (
        "a revision that selected evidence was reported as not informing "
        "anything: %r" % (healthy,))

    silent = channel.classify_revision(MUTES, views=SEEDED_VIEWS)

    assert silent["eligibility"] == channel.ELIGIBLE, (
        "the mute arm was refused as %r, so the premise of this test is "
        "that these bytes are admissible and select nothing"
        % (silent["eligibility"],))
    assert silent["selected_evidence"] == [[]], (
        "the premise of this test is that the bytes select nothing and are "
        "still admitted: %r" % (silent["selected_evidence"],))
    assert silent["informs_decision"] is False, (
        "a revision that selected no evidence reported that it informed a "
        "decision: %r" % (silent,))
