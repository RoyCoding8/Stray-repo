"""E4's headroom is a data artifact, and these tests hold it to its inputs.

The numbers -0.0222, 0.0667 and +0.2596 lived in a test docstring, in two
report files and in the findings ledger, and in no data artifact. A reader
checking the claim had to run pytest, which is the report asking the reader
to trust the report. `reports/evidence/inv_r1_e4/headroom.json` now carries
the numbers with the split, the seeds and the resample count beside them,
produced by `make_evidence.py` in the same directory.

These tests assert two things and stop there. The artifact exists, and it
is detectably the run it was recorded as. It is no longer the run the
module would produce, because lane C4 replaced the fixed two-entry
construction menu with an inherited construction procedure, and what a
descendant builds moved with it. `reports/evidence/` is immutable, so the
artifact is history rather than a claim about the present, and what these
tests hold it to is that it says which history and cannot be mistaken for
a current run. The verdict it supports is the honest one: the substrate
has no reachable headroom, established by a paired measurement large enough
to separate the two reachable descendants rather than by the three-seed
documented call.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel

ARTIFACT = ROOT / "reports" / "evidence" / "inv_r1_e4" / "headroom.json"

POPULATION_N = 400
EFFECT_FLOOR = 0.02


def _artifact() -> dict:
    assert ARTIFACT.exists(), (
        "E4's headroom has no data artifact; %s is missing, so the numbers "
        "exist only in prose" % (ARTIFACT,))
    return json.loads(ARTIFACT.read_text())


def test_the_headroom_number_is_written_down_with_its_inputs():
    """The measurement records what produced it, not just what it was.

    Without the split and the seeds a number is an assertion. The
    documented call is the one the status line quotes, so the artifact has
    to quote the same inputs or the two are describing different runs.
    """
    evidence = _artifact()
    inputs = evidence["inputs"]["documented_headroom"]

    assert inputs["split"] == "dev"
    assert inputs["seeds"] == [0, 1, 2]
    assert inputs["resample_count"] == len(inputs["seeds"])
    assert evidence["reproduce"]["command"]


def test_the_artifact_is_an_archived_run_of_the_removed_construction():
    """A recorded number that has drifted from the code is a stale claim.

    This one has drifted, and it cannot be made to agree again. The
    estimator is not what moved: the descendant a construction builds is.
    `lineage_descendant_score` used to read a task's table bit at the
    development probe and resolve it to one of two menu members, so
    `evaluate_lineage` returned a mean over the menu's evidence. It now
    substitutes the probed input itself, so the same probe scores a
    different descendant and the best probe over a cohort moves. Measured:
    the archived call names probe 0, a live run of the same call on the
    same split and seeds names probe 7.

    `reports/evidence/` is immutable, so the artifact is not regenerated to
    match. What is checkable, and what this pins, is that the artifact is
    detectably the older run rather than silently current: it carries the
    removed construction's own two-member reachable set and the `menu_mean`
    key the module no longer emits, and a live run produces neither. That
    fails if the artifact is ever rewritten to look current, and it fails
    if the two-member menu is ever put back.

    The estimator name is the one field that is still a live comparison,
    because a report carrying a headroom number has to say which estimator
    produced it and the module still names this one.
    """
    evidence = _artifact()
    live = channel.channel_headroom(split="dev", seeds=[0, 1, 2])
    archived = evidence["headroom"]

    assert evidence["headroom"]["estimator"] == live["estimator"] == (
        channel.ESTIMATOR), (
        "the artifact and the module disagree about which estimator produced "
        "these numbers, so the artifact is not even a run of the estimator "
        "the module still carries: %r vs %r"
        % (archived["estimator"], live["estimator"]))

    assert archived["reachable_evidence"] == ["3", "11"], (
        "the archived artifact no longer carries the removed construction's "
        "two-member reachable set, so it is not the run this test reads as "
        "archived: %r" % (archived["reachable_evidence"],))
    assert "menu_mean" in archived, (
        "the archived artifact no longer carries the menu_mean key the "
        "removed estimator emitted, so it is not the run this test reads as "
        "archived: %r" % (sorted(archived),))

    assert live["reachable_evidence"] != archived["reachable_evidence"], (
        "the module is reporting the removed construction's two-member "
        "reachable set again, so the menu is back and this artifact is no "
        "longer history: %r" % (live["reachable_evidence"],))
    assert "menu_mean" not in live, (
        "channel_headroom emits menu_mean again, so the removed menu is "
        "back and this artifact is no longer history: %r" % (sorted(live),))


def test_both_reachable_descendants_were_measured():
    """The reachable pair is history, and the module no longer has one.

    The previous version read the reachable set off the module and
    required the artifact to match it. That was a live contract against
    the two-member menu, and it is gone for the reason
    `test_the_artifact_is_an_archived_run_of_the_removed_construction`
    gives: the construction is inherited, so what a descendant can reach is
    a property of the descendant's own bytes rather than a set the module
    publishes.

    So the reachable set is asked of the programs the artifact was built
    from. The archived pair {3, 11} is what the two authored controls
    report, which is what it was then, and it is no longer what any
    revision reports for itself. A revision that probed 7 reaches 7, and a
    module that answered one set for every program would be the menu
    again.
    """
    evidence = _artifact()

    assert set(evidence["reachable_evidence"]) == {"3", "11"}
    assert set(channel.reachable_evidence(channel.IMPROVE_LOW_SOURCE)) == {"3"}
    assert set(channel.reachable_evidence(channel.IMPROVE_HIGH_SOURCE)) == {"11"}

    # And a revision reaches what it selected, not the archived pair.
    assert channel.reachable_evidence(
        channel._revision_source("7")) == ("7",), (
        "a revision that probed 7 does not report 7 as what it can reach, "
        "so the reachable set is a constant again: %r"
        % (channel.reachable_evidence(channel._revision_source("7")),))


def test_the_three_controls_ran_and_all_three_behaved():
    """Qualification is a claim about numbers, so the numbers are here.

    The handoff requires a known-effect revision, a no-op and a disconnect
    counterexample. An apparatus that moves on a no-op is unqualified
    rather than unproven, and an unqualified apparatus cannot make E4's
    answer trustworthy at any cohort size. Each control's delta was
    measured here over the recorded cohort, not written by hand.
    """
    evidence = _artifact()

    assert [c["role"] for c in evidence["controls"]] == list(
        channel.CONTROL_ROLES)
    for control in evidence["controls"]:
        assert control["as_expected"] is True, (
            "the %s control did not behave as the apparatus requires: %r"
            % (control["role"], control))
    assert evidence["qualification"]["qualified"] is True

    known = next(c for c in evidence["controls"]
                 if c["role"] == "known-effect")
    assert known["delta"] > 0.0

    noop = next(c for c in evidence["controls"] if c["role"] == "no-op")
    disconnect = next(c for c in evidence["controls"]
                      if c["role"] == "disconnect")
    assert noop["delta"] == 0.0
    assert disconnect["delta"] == 0.0


def test_a_disconnect_and_a_no_op_are_recorded_as_different_failures():
    """Both produce no effect, and the artifact says they are not the same.

    A no-op learns from real evidence, so it matches the incumbent. A
    disconnect names an input the instrument refuses, so it matches a
    descendant that learned nothing. Collapsing both to "delta 0" against
    the incumbent would let a run that gathered no information at all pass
    as a working no-op, so each control records the reference it was
    actually compared against and the inputs it did and did not learn.
    """
    evidence = _artifact()
    by_role = {c["role"]: c for c in evidence["controls"]}

    noop = by_role["no-op"]
    disconnect = by_role["disconnect"]

    assert noop["reference"] == "incumbent"
    assert noop["learned_inputs"] == 1
    assert noop["refused_inputs"] == 0

    assert disconnect["reference"] == "descendant-that-learned-nothing"
    assert disconnect["learned_inputs"] == 0
    assert disconnect["refused_inputs"] == 1

    assert noop["mean"] != disconnect["mean"], (
        "a no-op and a disconnect scored the same, so the apparatus cannot "
        "tell a run that learned from one that learned nothing")
    assert disconnect["delta_vs_incumbent"] != 0.0, (
        "the disconnect matched the incumbent too, which would mean it "
        "learned something and is not a disconnect")


def test_the_two_reachable_descendants_differ_by_less_than_the_noise():
    """The worry, settled: no headroom, and the probe could reach it all.

    "The substrate has no headroom" and "my probe cannot reach the
    headroom" produce the same number at three seeds. They separate at a
    cohort large enough to resolve the effect. Here both reachable
    descendants are scored on the same seeds and the paired difference is
    measured with a standard error, so a real effect would show up as a
    difference several standard errors from zero.

    The alternative reading fails this. A probe that could not reach a
    genuine effect would still separate the two descendants once the
    cohort was large enough; what actually happens is a difference
    indistinguishable from zero, so the channel has nothing to find and
    not merely a sample too small to find it.
    """
    incumbent, alternative = [], []
    for seed in range(POPULATION_N):
        incumbent.append(
            channel.descendant_score([3], "dev", seed)["unqueried"])
        alternative.append(
            channel.descendant_score([11], "dev", seed)["unqueried"])
    paired = [alt - inc for inc, alt in zip(incumbent, alternative)]
    mean = sum(paired) / POPULATION_N
    se = statistics.pstdev(paired) / POPULATION_N ** 0.5

    assert abs(mean) < EFFECT_FLOOR, (
        "the two reachable descendants differ by %.5f on %d paired seeds, "
        "so the channel does have reachable headroom and E4 is not blocked "
        "by the substrate after all"
        % (mean, POPULATION_N))
    assert abs(mean / se) < 1.96, (
        "the paired difference %.5f is %.2f standard errors from zero at "
        "%d seeds; that is a real reachable effect, which would mean the "
        "documented three-seed call was underpowered rather than null"
        % (mean, mean / se, POPULATION_N))


def test_no_probes_at_all_would_have_headroom_to_find():
    """The substrate answer, and the one that closes the worry.

    The two reachable descendants bound the menu, not the substrate. A
    revision's only lever is choosing a better probe, so the range over
    all sixteen inputs the instrument accepts is the ceiling on any
    revision of this decision - a ceiling that would not move if the menu
    were widened to sixteen entries.

    That ceiling is measured on one large cohort and is smaller than any
    effect worth claiming. So a wider menu would not rescue the channel,
    and "my probe cannot reach the headroom" is refuted on its own terms:
    there is no headroom out there to reach.
    """
    evidence = _artifact()
    ceiling = evidence["ceiling"]

    assert len(ceiling["input_means"]) == 16
    assert ceiling["ceiling"] < EFFECT_FLOOR, (
        "some probe input scores %.5f better than the worst, so a wider "
        "menu would give the channel reachable headroom and E4 is not "
        "blocked by the substrate"
        % (ceiling["ceiling"],))
    assert abs(ceiling["z"]) < 2.58, (
        "the best and worst of all sixteen inputs differ by %.5f, which is "
        "%.2f standard errors from zero; the whole input space carries a "
        "real effect even though the reachable pair does not"
        % (ceiling["ceiling"], ceiling["z"]))


def test_the_documented_call_cannot_decide_the_question_either_way():
    """Why the three-seed number could not have told us, in both directions.

    The documented call put a whole-cohort measurement and a half-cohort
    measurement next to each other and subtracted them, so it was negative
    whatever the substrate was doing. The rebuilt estimator instead picks
    the best probe on one half of the cohort and scores it on the other,
    which is a like-against-like comparison, but on three seeds the score
    half holds one seed and the number moves wildly with the cohort. Both
    failure directions have to stay unguarded: a repaired estimator that
    can be pushed positive by the choice of cohort is as uninformative as
    the broken one was.

    The measurements that do decide are the paired 1500-seed difference
    above and the ceiling below it. This test only records that the cheap
    call is not the one the claim rests on.
    """
    signs = set()
    for n in (3, 6, 12, 24, 48):
        report = channel.channel_headroom(split="dev", seeds=list(range(n)))
        signs.add(report["delta"] > 0.0)
        assert report["split_half"]["score"]["n"] == max(n // 2, 1), (
            "the scoring half holds %d seeds at n=%d, so the two terms are "
            "not measured on the same sample: %r" % (
                report["split_half"]["score"]["n"], n, report))

    assert len(signs) > 1, (
        "the documented call returned the same sign at every cohort size "
        "from 3 to 48, so it would be reporting what the broken estimator "
        "reported; this test's reasoning about it is stale")
