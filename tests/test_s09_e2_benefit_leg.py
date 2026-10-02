"""E2's benefit statistic must be able to differ between two policies.

`reports/evidence/inv_r1_e2_replica_r2/report.json` records the campaign's
one paired contrast as `deltas: [0, 0, 0]`. That was not a finding. The
statistic was `evidence + quality`, and `quality` was
`QUALITY[verdict]` — a bit read off the checker's verdict. The verdict is a
fixpoint of two composed invariants: the oracle that accepts a reducer's
trial is the same function that grades the output, and `reducers` only ever
mutates `keep` on a line reading `if probe(trial)["verdict"] == PRESERVED`.
So every candidate reaching a Reading came back `preserved`, `quality` was
always 1.0, and `score` could only ever be 1.0 or 2.0.

The benefit leg is now the checker's *measure*: the fraction of the task's
initial measure the world-produced candidate removed. A reducer that
returned its input scores 0.0 and one that found a real reduction scores a
positive fraction, and the two differ without the oracle changing.

Nothing here steps a policy in a child. `method_exec` refuses on this host —
`child_limits.apply_child_limits` raises `UnsupportedChildLimit` on Windows
so the child never runs — and a test that needs a live child measures the
host, not the statistic. So these tests drive the leg where it lives: the
function that reads a graded report, the record the experience arms carry,
and the paired report that contrasts them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import e2_replication as replica
from experiments.ad01 import learner
from experiments.ad01 import s09_e2_scored as scored
from experiments.ad01 import worlds


def _report(verdict: str, initial: int, current: int) -> dict:
    return {"scored": True, "verdict": verdict, "initial_measure": initial,
            "measure": current, "reason": "ok-preserved"}


# ---------------------------------------------------------------------------
# the leg is not a constant
# ---------------------------------------------------------------------------


def test_the_benefit_leg_separates_a_reduction_from_handing_the_input_back():
    """The whole defect in one assertion.

    Two candidates, both graded `preserved`, because the oracle that let
    them through is the oracle that grades them. The old leg mapped that
    verdict to 1.0 for both and could not tell them apart. The new leg reads
    the measure, so the one that actually removed something scores above the
    one that removed nothing.
    """
    worked = scored.normalized_reduction(_report("preserved", 14, 3))
    idle = scored.normalized_reduction(_report("preserved", 14, 14))

    assert worked == pytest.approx(11 / 14)
    assert idle == 0.0
    assert worked != idle
    assert scored.normalized_reduction(_report("preserved", 14, 7)) \
        == pytest.approx(0.5)


def test_the_leg_is_not_the_verdict_bit_under_any_grade():
    """Every grade the checker can emit maps to a number that is not a bit.

    `QUALITY` was `{"preserved": 1, "not_preserved": 0, "invalid": 0,
    "unknown": 0}`. If the new leg is that table under another name, every
    preserved candidate scores the same again and the paired contrast is
    zero by construction, which is the defect this file exists to prevent.
    """
    grades = ("preserved", "not_preserved", "invalid", "unknown")
    values = {grade: scored.normalized_reduction(_report(grade, 14, 3))
              for grade in grades}

    assert values["preserved"] == pytest.approx(11 / 14)
    assert values["preserved"] not in (0.0, 1.0)
    assert values["not_preserved"] == values["invalid"] == values["unknown"] \
        == 0.0


def test_a_scheme_leg_taken_from_the_verdict_is_no_longer_reachable():
    """The constant is gone, not renamed.

    `QUALITY` was module-level and every study that used this scheme read
    it. A surviving export of the same table would be a second authority for
    the benefit leg, and a study could keep computing a constant score from
    it while the Reading carried a real one.
    """
    assert not hasattr(scored, "QUALITY")


# ---------------------------------------------------------------------------
# the leg is a precondition, not a reward
# ---------------------------------------------------------------------------


def test_an_unscored_reading_has_no_reduction_to_report():
    """A transport failure is not a zero reduction; it is an absent result.

    `normalized_reduction` reads `scored` first, so a reading that never
    governed cannot be read as a policy that governed and did nothing. The
    two report the same 0.0 and are told apart by the fields beside it.
    """
    unscored = scored.normalized_reduction(
        {"scored": False, "verdict": "", "initial_measure": 14, "measure": 0})
    idle = scored.normalized_reduction(_report("preserved", 14, 14))

    assert unscored == 0.0
    assert unscored == idle


def test_a_zero_initial_measure_is_not_a_division():
    """An empty task has nothing to reduce, and 0/0 is not a fraction."""
    assert scored.normalized_reduction(
        _report("preserved", 0, 0)) == 0.0


# ---------------------------------------------------------------------------
# the experience record carries a reason and a reduction
# ---------------------------------------------------------------------------


def test_a_measured_observation_records_the_reason_the_verdict_hides():
    """`preserved` alone says the oracle answered, not what it said.

    `ok-preserved` is a real reduction; `ok-incumbent` is the candidate
    handed straight back. Both are `preserved`, which is why the verdict
    was a dead field on every measured record.
    """
    body = replica.contrast_block()
    row = replica._measured_row(body["source_task_ids"][0])

    assert row["verdict"] == "preserved"
    assert row["reason"] == "ok-preserved"
    assert row["reduction"] > 0.0
    assert row["reduction"] < 1.0


def test_the_records_of_one_arm_do_not_all_carry_the_same_number():
    """A constant on the record side is the same defect as a constant leg.

    Every measured record reading the same reduction would mean the reducer
    did the same amount of work on every source task, and the arm would
    carry no information for a policy to read.
    """
    body = replica.contrast_block()
    reductions = [row["reduction"]
                  for row in replica.measured_observations(
                      body["source_task_ids"])]

    assert len(reductions) > 1
    assert len(set(reductions)) > 1


# ---------------------------------------------------------------------------
# the paired contrast is no longer a subtraction of a constant
# ---------------------------------------------------------------------------


def test_the_paired_contrast_moves_when_the_two_arms_reduced_differently():
    """The campaign's one comparison, with a difference in it.

    The recorded run produced `deltas: [0, 0, 0]` because both arms scored
    1.0. Here the treatment reduced and the control did not, and the
    contrast has to say so. Under the old arithmetic — one `score` minus
    the other's — this is `[1.0, 1.0]` because the scores are the bit, not
    the reduction.
    """
    readings = {
        replica.ARM_RELEVANT: {
            "t1": {"scored": True, "score": 1.0, "normalized_reduction": 0.5},
            "t2": {"scored": True, "score": 1.0, "normalized_reduction": 0.75},
        },
        replica.ARM_NONE: {
            "t1": {"scored": True, "score": 1.0, "normalized_reduction": 0.0},
            "t2": {"scored": True, "score": 1.0, "normalized_reduction": 0.0},
        },
    }
    report = replica.paired_report(readings)["relevant-minus-none"]

    assert report["deltas"] == [0.5, 0.75]
    assert report["paired"]["delta"] == pytest.approx(0.625)
    assert report["contrast_on"] == "normalized_reduction"


def test_the_paired_contrast_is_zero_when_neither_arm_reduced_differently():
    """A zero is still reported as a zero, and now means something.

    The two arms here have *different scores* and the *same* reduction, so
    the contrast is 0.0. Under the old arithmetic — one `score` minus the
    other's — this fixture returns 0.5, because the scores are the verdict
    bit and the bit is 1.0 for one of them and would be 2.0 for the other.
    So the test distinguishes a real zero from the constant one, which is
    the only way a zero in this report can be read.
    """
    readings = {
        replica.ARM_RELEVANT: {
            "t1": {"scored": True, "score": 2.0, "normalized_reduction": 0.5}},
        replica.ARM_NONE: {
            "t1": {"scored": True, "score": 1.0, "normalized_reduction": 0.5}},
    }
    report = replica.paired_report(readings)["relevant-minus-none"]

    assert report["deltas"] == [0.0]
    assert report["paired"]["delta"] == 0.0
    assert report["paired"]["measured"] is True


def test_the_report_names_the_estimator_it_actually_ran():
    """`ESTIMATOR` claimed a computation the code never performed.

    It read "paired best-reachable vs incumbent" while `paired_report`
    subtracted one arm's `score` from the other's. No reachability was
    computed and no incumbent was named, so a report carrying the string
    described an estimator it did not run.
    """
    body = replica.contrast_block()

    assert "best-reachable" not in replica.ESTIMATOR
    assert "incumbent" not in replica.ESTIMATOR
    assert "normalized_reduction" in replica.ESTIMATOR
    assert body["estimator"] == replica.ESTIMATOR


def test_the_paired_report_carries_the_decision_vector_beside_the_delta():
    """The choice the policy made is not in the delta, so it is reported.

    `VERBATIM` excludes `method_id` and `max_queries` from the evidence
    leg's denominator on purpose, so the evidence leg is blind to the one
    decision the policy makes. Two arms that reduced equally but chose
    differently are a real difference, and a delta of 0.0 does not say
    which it was.
    """
    readings = {
        replica.ARM_RELEVANT: {
            "t1": {"scored": True, "normalized_reduction": 0.5,
                   "action": {"inputs": {"method_id": "seed-sw-greedy",
                                         "max_queries": 8}}}},
        replica.ARM_NONE: {
            "t1": {"scored": True, "normalized_reduction": 0.5,
                   "action": {"inputs": {"method_id": "seed-sw-ddmin",
                                         "max_queries": 8}}}},
    }
    decisions = replica.paired_report(readings)["relevant-minus-none"]

    assert decisions["deltas"] == [0.0]
    assert decisions["decisions"]["t1"]["treatment"] == {
        "method_id": "seed-sw-greedy", "max_queries": 8}
    assert decisions["decisions"]["t1"]["control"] == {
        "method_id": "seed-sw-ddmin", "max_queries": 8}
    assert decisions["decisions"]["t1"]["differs"] is True


# ---------------------------------------------------------------------------
# the prompt shows the record's reason
# ---------------------------------------------------------------------------


def test_the_prompt_shows_a_record_reason_and_the_verdict_alone_hides_it():
    """A policy can only choose on what it was shown.

    The `Prior observations:` line carried `task_id` and `verdict`. For a
    measured record the verdict is `preserved` whatever the reducer did, so
    the line was a constant, and a policy reading it was reading nothing.
    The rendered block now carries the checker's reason.
    """
    body = replica.contrast_block()
    target = worlds.load_task(worlds.FROZEN_DIR, body["target_task_ids"][0])
    visible = learner.visible_opportunities(body["cohort_world"])
    arm = replica.build_arm(
        replica.ARM_RELEVANT, target,
        source_task_ids=body["source_task_ids"],
        filler_task_ids=body["filler_task_ids"], visible=visible)
    prompt = learner.treatment_prompt(dict(arm), dict(target), dict(arm))

    assert "ok-preserved" in prompt
    # The verdict is still shown; the reason is added beside it rather than
    # in place of it, so an older record without a reason still renders.
    assert '"verdict"' in prompt
    assert '"reason"' in prompt


def test_a_record_without_a_reason_still_renders():
    """A seed record carries no reason, and must not raise on the way in.

    `learner.seed_observations` is the other route into an arm, and its
    records have no `reason` key. Rendering reads the key, so a missing one
    has to read as absent rather than raise.
    """
    target = worlds.load_task(worlds.FROZEN_DIR, "ad01-w1-dev-sw-00")
    arm = {"task": dict(target), "family": "software", "visible": [],
           "retained": [], "remaining": {"queries": 8},
           "observations": [{"observation_id": "obs-1", "task_id": "t",
                             "verdict": "preserved", "detail": "ref o0"}]}
    prompt = learner.treatment_prompt(dict(arm), dict(target), dict(arm))

    assert "Prior observations:" in prompt
    assert "preserved" in prompt


# ---------------------------------------------------------------------------
# the size match survives the wider record
# ---------------------------------------------------------------------------


def test_the_irrelevant_control_still_matches_the_relevant_arm_in_characters():
    """The `reason` on every record makes both arms longer. The match holds.

    `irrelevant_control_for` pads the control's `detail` fields to the
    relevant arm's exact character count, so a wider record is a bigger
    target to fit, not a broken invariant — but that is a claim about the
    mechanism and this asserts the outcome, on every frozen target rather
    than the first one.
    """
    body = replica.contrast_block()
    visible = learner.visible_opportunities(body["cohort_world"])

    for task_id in body["target_task_ids"]:
        target = worlds.load_task(worlds.FROZEN_DIR, task_id)
        arms = replica.arms_for(
            target, source_task_ids=body["source_task_ids"],
            filler_task_ids=body["filler_task_ids"], visible=visible)
        relevant, irrelevant = arms[replica.ARM_RELEVANT], \
            arms[replica.ARM_IRRELEVANT]

        assert learner.equal_length_experience_pair(relevant, irrelevant), \
            task_id
        # And the match is on real content, not on two empty arms.
        assert relevant["observations"]
        assert learner._observation_chars(relevant["observations"]) > 400


def test_both_arms_carry_a_reason_and_the_match_still_holds():
    """The control's records are measured too, so it has reasons to match.

    `_irrelevant_observations` re-measures the filler records and re-fits
    the padding to the relevant arm's characters. If the two sides' records
    were different shapes, the re-fit would be fitting a different record
    and the equality would be arithmetic rather than a matched pair.
    """
    body = replica.contrast_block()
    target = worlds.load_task(worlds.FROZEN_DIR, body["target_task_ids"][0])
    visible = learner.visible_opportunities(body["cohort_world"])
    arms = replica.arms_for(
        target, source_task_ids=body["source_task_ids"],
        filler_task_ids=body["filler_task_ids"], visible=visible)

    for name in (replica.ARM_RELEVANT, replica.ARM_IRRELEVANT):
        for row in arms[name]["observations"]:
            assert row.get("reason"), (name, row)
            assert "reduction" in row, (name, row)


# ---------------------------------------------------------------------------
# the walk reaches the reading
# ---------------------------------------------------------------------------


def test_the_query_trace_reaches_the_serialized_reading():
    """`method_exec` assembles the walk and `dispatch` was dropping it.

    `queries` says how many questions a run asked. The trace says what they
    were, each with the candidate's digest and the verdict and reason the
    checker graded it, and that is the only thing that distinguishes a
    method that searched from one handed its answer. A Reading that
    serialized without it left the evidence in the executor's return value
    and nothing in the record a study reads.
    """
    reading = _reading_with_walk()

    assert reading.query_trace == [
        {"candidate_digest": "a" * 64, "verdict": "preserved",
         "reason": "ok-preserved"}]
    # The walk has to be in the artifact, not only on the dataclass, or a
    # study reading the serialized report gets the count and not the walk.
    assert reading.as_dict()["query_trace"] == reading.query_trace
    assert reading.queries == len(reading.query_trace)


def _reading_with_walk() -> scored.Reading:
    """A scored Reading carrying a one-question walk.

    Built through the constructor rather than by stepping a policy, because
    the step route needs a child and `child_limits` refuses one on this host.
    What is under test is that the field survives onto the Reading and into
    `as_dict`, not that a policy can produce a walk here.
    """
    return scored.Reading(
        scheme=scored.SCHEME, origin="authored-control", arm="e2",
        task_id="ad01-w1-dev-sw-00", family="software", control="seed-sw-ddmin",
        digest="d" * 64, executed_source="s", executed_digest="e" * 64,
        action={}, candidate={}, selected_identity="seed-sw-greedy",
        queries=1, verdict="preserved", reason="ok-preserved", quality=0.5,
        evidence=0.0, evidence_varied=0, evidence_total=1,
        evidence_sites=(scored.CANDIDATE_SITE,), control_inputs={},
        candidate_digest_scored="c" * 64, candidate_digest_alternate="a" * 64,
        control_verdict="preserved", initial_measure=14, candidate_measure=7,
        agreement=scored.PASS, score=0.5, scored=True, detail="",
        query_trace=[{"candidate_digest": "a" * 64, "verdict": "preserved",
                      "reason": "ok-preserved"}])


def test_an_unscored_reading_reports_no_walk_rather_than_an_empty_one():
    """`None` and `[]` are different claims and the gate depends on which.

    An unscored Reading admitted no action, so no method ran and there is
    no walk. `[]` would claim a method ran and asked nothing, which is what
    `method_exec` already writes when a durable receipt replays a settled
    operation, and the two must not be confused.
    """
    score = scored.Score({"policy_source": ""}, "authored-control", "e2")
    reading = scored._unscored(score, {"task_id": "t", "family": "software"},
                               scored.UNSCORED_GATE, "no source")

    assert reading.query_trace is None
    assert reading.as_dict()["query_trace"] is None


# ---------------------------------------------------------------------------
# no second authority for the leg
# ---------------------------------------------------------------------------


def test_the_instrument_table_reads_the_same_leg_and_holds_no_bit_of_its_own():
    """`experience_axis` computed the same sum and would have kept the bit.

    The reader-versus-echoer table summed `leg["ratio"] + QUALITY[verdict]`
    with the same `s09_e2_scored.QUALITY` this fix deleted. Left alone it
    would raise `AttributeError`; a caller that imported its own copy of the
    table would instead go on reporting a constant `score` and a `separable`
    flag derived from it.

    A build-time check rather than a call, because the table needs a live
    child to run and `child_limits` refuses one on this host. What is
    asserted is that the row reads the leg and holds no mapping of its own,
    with comments stripped so the prose explaining the deletion is not read
    as a reference to it.
    """
    module = ROOT / "experiments" / "ad01" / "experience_axis.py"
    body = module.read_text(encoding="utf-8")
    row = body[body.index('"evidence_sites": leg["sites"]'):][:700]
    code = "\n".join(line.split("#", 1)[0] for line in row.splitlines())

    assert "reduction" in code
    assert "QUALITY" not in code


def test_no_module_still_reaches_for_the_deleted_verdict_table():
    """A surviving reference raises `AttributeError` the first time it runs.

    The table was module-level and exported, so other modules could hold a
    copy of it. This walks the package for any executable reference to it,
    so a module that imported the table before this fix and was not caught
    by a test run is still caught.
    """
    import re

    pattern = re.compile(r"\bQUALITY\b")
    package = ROOT / "experiments"
    offenders = []
    for path in package.rglob("*.py"):
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if "s09_e2_scored" in code and pattern.search(code):
                offenders.append("%s:%d" % (path, number))

    assert offenders == []
