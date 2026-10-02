"""The candidate tie is two findings, and the walk is what separates them.

`control_distinct` refused every task whose two arms returned byte-identical
candidates. That conflated two things:

    same_walk      two ids taking the same questions in the same order. The
                   C15 shape, one program under two names.
    same_answer    two different methods reaching one preserved minimum. A
                   property of the problem, and on a panel whose minimum is
                   unique it is what a correct run produces.

The second is not a defect in the arm. These reducers are deletion-only
over a legal-subobject order, and `reports/evidence/inv_r1_e1_control_
distinct_mechanism/agreement_split.json` measured the minimum unique on
18 of 18 tasks under 40 random deletion orders. Refusing the convergence
makes the gate unsatisfiable on any panel with a unique solution, which is
a gate that cannot pass rather than a strict one.

So the run now records the walk per arm per task, and the gate reads it.
These tests assert both directions, and each mutation is checked for
having landed. A prior lane here had a mutation report green because a
string replace hit an identical block in another branch, so every
mutation below asserts on the digest of the thing it changed rather than
on the gate's answer alone.

The panel is not touched. `distinct_minima_under_40_random_orders: 1 on
18/18` is the property that makes the split necessary, and tuning the
panel until the gate opens would be tuning the evidence to the verdict.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import control_distinctness as gates  # noqa: E402

DDMIN = "def ENTRY(t, o):\n    return reducers.reduce_software(t, o, method='ddmin')\n"
GREEDY = "def ENTRY(t, o):\n    return reducers.reduce_software(t, o, method='greedy')\n"
SILENT = "def ENTRY(t, o):\n    return {'candidate': {}, 'queries': 0}\n"


def _step(digest: str, verdict: str = "preserved",
          reason: str = "ok-preserved") -> dict:
    return {"candidate_digest": digest, "verdict": verdict, "reason": reason}


def _row(task_id: str, capability_id: str, source: str, output,
         trace) -> dict:
    return {"task_id": task_id, "executed": capability_id,
            "executed_source": source, "output": output,
            "query_trace": trace, "costs": {"witness_queries": 4}}


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


# Two walks that share their first question and part company afterwards.
# This is the shape the recorded run's software agreements have: the same
# opening probe, a different second trial, a different third, and the same
# answer at the end.
WALK_CONTROL = [_step("aaaa0000aaaa0000", "preserved", "ok-incumbent"),
                _step("bbbb0000bbbb0000", "preserved", "ok-preserved"),
                _step("cccc0000cccc0000", "not_preserved", "observation-missing"),
                _step("dddd0000dddd0000", "preserved", "ok-preserved")]
WALK_ACQUIRED = [_step("aaaa0000aaaa0000", "preserved", "ok-incumbent"),
                 _step("dddd0000dddd0000", "preserved", "ok-preserved"),
                 _step("eeee0000eeee0000", "not_preserved", "witness-lost-agree"),
                 _step("ffff0000ffff0000", "not_preserved", "witness-lost-agree")]

# One walk, walked twice. Different ids, byte-identical source, and the
# same four questions in the same order with the same four answers.
WALK_SHARED = [_step("1111000011110000", "preserved", "ok-incumbent"),
               _step("2222000022220000", "preserved", "ok-preserved"),
               _step("3333000033330000", "not_preserved", "observation-missing"),
               _step("4444000044440000", "preserved", "ok-preserved")]

ANSWER = {"family": "software", "task_id": "t-0", "ops": []}


def test_two_different_walks_to_one_answer_are_not_a_refusal():
    """The finding the gate used to get wrong.

    Byte-identical candidates, and the arms disagree about how they got
    there. The candidate leg fires and is reported; the pair is classified
    as a convergence and is not refused, because nothing about it says the
    two arms are the same method.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, WALK_CONTROL)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER, WALK_ACQUIRED)]

    verdict = gates.control_distinct(control, acquired)

    assert verdict["same_candidate"], verdict
    assert verdict["converged"], (
        "the walks differ, so the tie must be classified as a convergence "
        "rather than left as an unexplained tie")
    assert verdict["converged"][0]["task_id"] == "t-0"
    assert verdict["converged"][0]["queries"] == {"control": 4, "acquired": 4}
    assert verdict["same_walk"] == [], verdict["same_walk"]
    assert verdict["distinct"] is True, verdict.get("refusal")


def test_one_walk_taken_twice_is_still_refused():
    """The direction that must not move.

    Same answers, same order, same questions, different ids. This is the
    C15 shape and it refuses on the walk even when nothing else fires.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, WALK_SHARED)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER,
                     copy.deepcopy(WALK_SHARED))]

    verdict = gates.control_distinct(control, acquired)

    assert len(verdict["same_walk"]) == 1, verdict["same_walk"]
    assert verdict["same_walk"][0]["task_id"] == "t-0"
    assert verdict["same_walk"][0]["queries"] == 4
    assert verdict["converged"] == [], (
        "a tie whose walks are identical is not a convergence")
    assert verdict["distinct"] is False
    assert "same walk" in verdict["refusal"]


def test_the_walk_leg_alone_refuses_when_nothing_else_fires():
    """The walk is load bearing, not a decoration on the other legs.

    Two ids, two byte-different sources naming two different strategies,
    and two different candidates. Every leg the gate had before the walk
    passes, so a pair like this reported `distinct: True`. Giving both
    arms one walk is what makes it the same method twice.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, {"ops": [1]},
                    WALK_SHARED)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, {"ops": [2]},
                     copy.deepcopy(WALK_SHARED))]

    verdict = gates.control_distinct(control, acquired)

    assert verdict["same_source"] == []
    assert verdict["same_strategy"] == []
    assert verdict["same_candidate"] == []
    assert verdict["distinct"] is False
    assert "same walk" in verdict["refusal"]


def test_a_tie_whose_walk_was_never_observed_is_refused():
    """Absence of the walk is not evidence of a different walk.

    A record that predates the field, a durable-receipt replay, and a
    host seed short-circuit all report no walk. On a task where the
    candidates tied, that is exactly the pair the walk was added to
    classify, and guessing would be the whole defect the field fixes.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, None)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER, None)]

    verdict = gates.control_distinct(control, acquired)

    assert len(verdict["unmeasured_walk"]) == 1, verdict["unmeasured_walk"]
    assert verdict["unmeasured_walk"][0]["candidates_tied"] is True
    assert verdict["converged"] == []
    assert verdict["distinct"] is False
    assert "did not observe" in verdict["refusal"]


def test_an_unmeasured_walk_does_not_hold_hostage_a_proven_pair():
    """A missing walk refuses a tie, not a pair the other legs settle.

    Every other leg already disagrees here: different ids, different
    sources, different strategies, different candidates. Refusing that
    over a field an older record does not carry would make the gate
    refuse pairs it can prove, which is a different defect from waving
    them through.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, {"ops": [1]}, None)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, {"ops": [2]}, None)]

    verdict = gates.control_distinct(control, acquired)

    assert len(verdict["unmeasured_walk"]) == 1
    assert verdict["unmeasured_walk"][0]["candidates_tied"] is False
    assert verdict["distinct"] is True, verdict.get("refusal")


def test_an_empty_walk_is_not_an_absent_one():
    """`[]` is an arm that asked nothing. `null` is an arm not watched.

    Collapsing them is how two unobserved arms would read as a match
    against each other, which is the one thing the field must not do.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, [])]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER, None)]

    verdict = gates.control_distinct(control, acquired)

    assert len(verdict["unmeasured_walk"]) == 1, (
        "an empty list and a null are different claims and must not match")
    assert verdict["converged"] == []
    assert verdict["distinct"] is False


def test_the_order_of_the_questions_is_part_of_the_walk():
    """A walk is a sequence, not a set.

    Both arms ask the same four questions and get the same four answers.
    Only the order differs. Swapping the two middle rows changes the walk,
    and the pair is a convergence rather than a repeat.
    """
    reordered = [WALK_SHARED[0], WALK_SHARED[2], WALK_SHARED[1],
                 WALK_SHARED[3]]
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, WALK_SHARED)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER, reordered)]

    verdict = gates.control_distinct(control, acquired)

    assert sorted(_digest(w) for w in (WALK_SHARED, reordered)) != [
        _digest(WALK_SHARED)], "the reorder must actually produce a new walk"
    assert verdict["same_walk"] == [], verdict["same_walk"]
    assert verdict["converged"], verdict


def test_the_grade_of_each_question_is_part_of_the_walk():
    """Two identical questions graded two different ways are two walks.

    The same candidate asked twice, with the same digest, is the same
    question. The answer is not part of it, and a comparison that reads
    only the questions would call these one walk.
    """
    other_grade = [dict(row) for row in WALK_SHARED]
    other_grade[1] = dict(WALK_SHARED[1], verdict="not_preserved",
                          reason="witness-lost-agree")
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, WALK_SHARED)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER, other_grade)]

    verdict = gates.control_distinct(control, acquired)

    assert verdict["same_walk"] == [], verdict["same_walk"]
    assert verdict["converged"], verdict


def test_a_fallback_reports_no_walk_even_when_it_carries_one():
    """A member that did not run did not walk.

    `run_use` copies the selected member's body onto a record even when
    execution failed, and a trace attached to such a row would be the
    walk of a program that never asked anything.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, WALK_SHARED)]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER,
                     copy.deepcopy(WALK_SHARED))]
    acquired[0]["fallback_reason"] = "member execution failed: boom"

    verdict = gates.control_distinct(control, acquired)

    assert verdict["same_walk"] == [], (
        "a fallback must not be read as having taken a walk")
    assert len(verdict["unnamed_executed_policy"]) == 1
    assert verdict["distinct"] is False


def test_the_refusal_names_the_split_not_the_raw_tie_count():
    """A reader told "12 tasks tied" cannot act on it.

    The split is the actionable number: how many ties were one walk taken
    twice, and how many were two methods meeting on the same answer.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, WALK_CONTROL),
               _row("t-1", "ctl-graph-greedy", GREEDY, ANSWER,
                    copy.deepcopy(WALK_SHARED))]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER, WALK_ACQUIRED),
                _row("t-1", "acquired-gr-0000", GREEDY, ANSWER,
                     copy.deepcopy(WALK_SHARED))]

    verdict = gates.control_distinct(control, acquired)

    assert len(verdict["same_candidate"]) == 2
    assert len(verdict["converged"]) == 1
    assert len(verdict["same_walk"]) == 1
    text = verdict["refusal"]
    assert "2 task(s) returned a byte-identical candidate" in text
    assert "of which 1 took different walks" in text, text
    assert "1 task(s) took the same walk" in text, text


def test_mutating_the_acquired_walk_changes_the_verdict_in_both_directions():
    """Both mutations, on the same pair, with the landing confirmed.

    The pair starts as a convergence and ends as a repeat. Every row is
    checked for having actually changed before the gate is asked, because
    a mutation that did not land produces a green that means nothing.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN, ANSWER, WALK_CONTROL),
               _row("t-1", "ctl-graph-greedy", GREEDY, ANSWER,
                    copy.deepcopy(WALK_SHARED))]
    acquired = [_row("t-0", "acquired-sw-0000", GREEDY, ANSWER, WALK_ACQUIRED),
                _row("t-1", "acquired-gr-0000", GREEDY, ANSWER,
                     copy.deepcopy(WALK_SHARED))]

    before = gates.control_distinct(control, acquired)
    assert len(before["converged"]) == 1, before["converged"]
    assert len(before["same_walk"]) == 1, before["same_walk"]

    mutated = copy.deepcopy(acquired)
    by_task = {row["task_id"]: row for row in control}
    for row in mutated:
        row["query_trace"] = copy.deepcopy(by_task[row["task_id"]]["query_trace"])

    unchanged = [row["task_id"] for row, source in zip(mutated, acquired)
                 if _digest(row["query_trace"]) == _digest(source["query_trace"])]
    assert unchanged == ["t-1"], (
        "t-1 already shared the control's walk and must come out of the "
        "mutation unchanged. Naming the row is the point: a mutation that "
        "silently changed every row would leave the next assertions "
        "measuring a pair that never existed")

    after = gates.control_distinct(control, mutated)

    assert len(after["converged"]) == 0, after["converged"]
    assert len(after["same_walk"]) == 2, after["same_walk"]
    assert after["distinct"] is False


def test_the_recorded_run_is_still_refused_and_its_ties_are_unmeasured():
    """The run that produced twelve byte-identical candidates.

    `reports/evidence/inv_r1_e1_control_arm/use_records.json` predates the
    trace field, so every walk on it is unobserved. All twelve ties
    therefore stay refused, which is the honest reading: the run cannot
    say which mechanism produced them, and a gate that guessed would be
    the defect the field was added to remove.
    """
    path = (ROOT / "reports" / "evidence" / "inv_r1_e1_control_arm"
            / "use_records.json")
    if not path.exists():
        return
    records = json.loads(path.read_text(encoding="utf-8"))
    control = [r for r in records if r.get("arm") == "C"]
    acquired = [r for r in records if r.get("arm") == "I"]

    verdict = gates.control_distinct(control, acquired)

    assert len(verdict["paired_tasks"]) == 18, verdict["paired_tasks"]
    assert len(verdict["same_candidate"]) == 12, verdict["same_candidate"]
    assert len(verdict["same_walk"]) == 0
    assert len(verdict["converged"]) == 0
    assert len([row for row in verdict["unmeasured_walk"]
                if row["candidates_tied"]]) == 12
    assert verdict["distinct"] is False
    assert "did not observe" in verdict["refusal"]
