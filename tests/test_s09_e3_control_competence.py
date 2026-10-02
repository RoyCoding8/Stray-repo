"""C18: the control a result is measured against has to be qualified, per budget.

`test_s09sel_divergence.test_the_control_is_the_best_rule_of_its_shape` is
a real competence test over all 196 constant pairs. It passes. It also
passes at `BUDGET = 40` and nowhere else, and `STAGE-09-CONNECTED-STATUS.md`
reported it unqualified -- so a reader who followed the citation found a
green test and concluded the control was competent across the ladder. That
is the failure this file exists to close: a check narrower than the claim
made from it, which is worse than no check because it reads as coverage.

Measured here, counting the constant rules that beat each fixed arm on
`held_out_reduction`. The counts depend on the world set, so both are
given -- over the three qualified worlds, and over world 0 alone:

| budget | 8 | 14 | 20 | 30 | 40 | 60 |
|---|---|---|---|---|---|---|
| beats `DEFAULT_RULE`, 3 worlds | 0 | 0 | **96** | **94** | 0 | 4 |
| beats `DEFAULT_RULE`, world 0 | 0 | 0 | **96** | **10** | 0 | 4 |
| beats the fitted control, 3 worlds | 0 | 0 | 0 | 0 | 8 | 84 |

The world-set dependence at 30 is not a rounding artefact and not a
correction to anyone else's arithmetic -- the same search over the same
196 rules gives 10 on one world and 94 on three, because a rule that ties
the default on two worlds and beats it on one is counted or not depending
on the average. **So the counts in the report table are properties of a
world set, not of the control, and any threshold pinned to them tests the
world set instead of the finding.** What is stable across both: the
default is non-optimal at 20, 30 and 60 and optimal at 8, 14 and 40, and
the fitted control is optimal at 20 and 30 and non-optimal at 40 and 60.
The two arms fail at *different* budgets, which is the measurement that
decides the design question below.

So this file does not assert that some control is optimal across the
ladder. It could not: no constant rule in the space is, and a test
demanding one would have to name a budget and call it the ladder, which is
the defect wearing a new hat.

The property asserted is the one that is true and worth having: **every
reported result names the control it was measured against, and every
budget where that control was handicapped reports the best-in-space score
beside it.** A disclosed handicap with the yardstick next to it is a
bounded claim. An invisible one is C18.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import agenda_policy
from experiments.ad01 import s09_e3_selection as e3
from experiments.ad01 import selection

# The budgets the study reports, and the budgets whose sign is claimed.
LADDER = e3.BUDGETS
CONTROLLED = e3.TIGHT + e3.LOOSE

# The qualified worlds, because the claims under test are made over them.
# Narrowing to one world would be cheaper and would quietly change what is
# being asserted: on world 0 alone the agenda does *not* lead the control
# at 30 (0.112 against 0.167), while over the three qualified worlds it
# does. A per-world count and a per-ladder sign are different questions,
# and only the second is the one the report answers.
WORLDS = selection.WORLDS


@pytest.fixture(scope="module")
def sweep() -> dict:
    """`control_competence` for every reported budget, on `WORLDS`."""
    return {budget: agenda_policy.control_competence(budget, worlds=WORLDS)
            for budget in LADDER}


@pytest.fixture(scope="module")
def ladder() -> dict:
    """The published ladder, with each arm's strength at its own budget."""
    return e3.qualified_ladder(worlds=WORLDS)


def _arm(row: dict, name: str) -> dict:
    for arm in row["arms"]:
        if arm["policy"] == name:
            return arm
    raise AssertionError("budget %d reports no %r arm" % (row["budget"], name))


def _mean(arm: dict) -> float:
    return arm["held_out_reduction_mean"]


def test_every_reported_budget_is_qualified_not_just_one(ladder, sweep):
    """The scope defect, as an assertion over the budgets the report publishes.

    `control_competence` answers per budget, so this is the claim the
    single-budget test could not make. If a budget were added to `BUDGETS`
    and left unqualified, this goes red instead of leaving the reader to
    assume the new point inherits the old check.
    """
    for budget in LADDER:
        assert budget in sweep, (
            "the ladder publishes budget %d and the competence search "
            "covers %r; a reported budget with no qualification is exactly "
            "the C18 defect" % (budget, sorted(sweep)))
    for step in ladder["ladder"]:
        assert step["control_qualification"], (
            "budget %d reports arms %r and no control qualification"
            % (step["budget"], sorted(a["policy"] for a in step["arms"])))


def test_no_constant_rule_is_optimal_across_the_whole_ladder(sweep):
    """Why the assertions are per-budget, as a measured fact.

    The winners at 20 and at 40 are different rules scoring differently, so
    the per-budget scoping in this file describes the space rather than
    narrowing the question. If a future substrate admits one globally
    optimal rule this goes red and someone re-scopes on purpose.
    """
    best_by_budget = {budget: sweep[budget]["best_held_out_reduction"]
                      for budget in LADDER}
    distinct = {round(value, 12) for value in best_by_budget.values()}

    assert len(distinct) > 1, (
        "every budget now shares one best score (%r), so a single globally "
        "optimal rule may exist; re-scope this file's per-budget "
        "assertions and record why" % best_by_budget)


def test_a_handicapped_control_never_appears_without_the_yardstick(ladder):
    """The binding half: a handicap has to arrive with the best-in-space.

    At 20 and 30 the historical control retains nothing and the agenda
    leads on held-out quality. That lead is real against `DEFAULT_RULE` and
    absent against the best constant rule in the space, so a ladder
    reporting it without the yardstick reports a win over a control that 96
    of 196 rules beat.
    """
    handicapped = {}
    for step in ladder["ladder"]:
        for record in step["control_qualification"]:
            if record["optimal_here"]:
                continue
            handicapped.setdefault(step["budget"], []).append(record["arm"])
            assert step.get("best_rule_held_out_reduction") is not None, (
                "budget %d reports arm %r with %d of %d constant rules "
                "beating it and no best-in-space score beside it, so the "
                "result reads as a win over a control of unstated strength"
                % (step["budget"], record["arm"], record["rules_beating_it"],
                   step["rules_searched"]))
            assert step["best_rule_is_an_arm"] is False, (
                "budget %d promoted the yardstick rule into the arm list; "
                "it ranks rules on the reported metric and a control that "
                "reads that metric is an oracle for the comparison"
                % step["budget"])
    assert handicapped, (
        "no budget reported a handicapped control, so the yardstick "
        "assertion never ran; the ladder and the rule space disagree and "
        "one of them is stale")


def test_the_agenda_never_beats_the_best_rule_where_any_rule_qualifies(
        ladder):
    """The ceiling, stated over the budgets where it can bind.

    Selection cannot beat exhaustive search over a constant it is free to
    pick, and holding that is what makes "the agenda led at 20" a bounded
    claim rather than a benefit.

    The condition matters. At budget 14 every constant rule scores exactly
    0.0 -- no constant can qualify anything in a 14-unit envelope -- so
    the best rule in the space is 0.0 and the agenda's lead there is real
    rather than paradoxical: it is a lead over an opponent the envelope
    never let play. Asserting the ceiling unconditionally would fail on
    that budget for the right physical reason and would have to be
    weakened everywhere to accommodate it, so the ceiling is asserted
    exactly where a constant could have won.
    """
    vacuous = []
    for step in ladder["ladder"]:
        best = step["best_rule_held_out_reduction"]
        if best <= 0.0:
            vacuous.append(step["budget"])
            continue
        assert _mean(_arm(step, "agenda")) <= best + 1e-12, (
            "at budget %d the agenda held out %.6f against the best of %d "
            "constant rules at %.6f, so selection now beats exhaustive "
            "search over its own family and every negative result here "
            "needs revisiting"
            % (step["budget"], _mean(_arm(step, "agenda")),
               step["rules_searched"], best))
    assert vacuous == [8, 14], (
        "the budgets where no constant rule qualifies anything are %r, not "
        "[8, 14]; if a constant can now win at one of these, the ceiling "
        "above covers a budget it was being excused from" % vacuous)


def test_the_agenda_lead_at_20_and_30_is_a_lead_over_a_handicapped_rule(
        ladder):
    """The finding this row was opened for, asserted rather than described.

    The crossover reports the agenda ahead on held-out quality at 20 and 30.
    Both are true and neither is the result the report reads as: at both
    budgets the arm it leads is beaten by other rules in the same family,
    and the agenda is behind the best constant rule at both. This is the
    direct answer to "does the ladder-wide search change E3's result at
    20 and 30" -- the sign survives, the meaning does not.

    The handicap is asserted as "some rule beats it", not as a count. The
    count is world-set dependent in a way that makes it a bad pin: the
    same search reports 96 rules beating the default at 20 on one world
    and on three, but 10 at 30 on one world and 94 on three. A threshold
    like "> 50" passes on the three-world number and fails on the
    one-world one for the same substrate, so it would be testing the world
    set rather than the control. What is stable is the finding itself --
    non-optimal at 20, 30 and 60, optimal at 8, 14 and 40.
    """
    handicapped_at = []
    for step in ladder["ladder"]:
        control = {r["arm"]: r for r in step["control_qualification"]}
        if step["budget"] in (20, 30):
            handicapped_at.append(step["budget"])
            assert control["control"]["rules_beating_it"] > 0, (
                "at budget %d no constant rule beats the control; the "
                "handicap this test records has closed and the reported "
                "lead needs re-measuring rather than re-stating"
                % step["budget"])
            assert _mean(_arm(step, "agenda")) > _mean(_arm(step, "control")), (
                "at budget %d the agenda no longer leads the control, so "
                "the sign the crossover reports has moved" % step["budget"])
            assert _mean(_arm(step, "agenda")) \
                <= step["best_rule_held_out_reduction"] + 1e-12, (
                "at budget %d the agenda now beats the best constant rule, "
                "so the handicap stopped being the whole story and this "
                "row's conclusion is stale" % step["budget"])
    assert handicapped_at == [20, 30], (
        "the budgets at which the agenda leads a handicapped control are "
        "%r, not [20, 30]; the crossover's crossover has moved and the "
        "claim written about it needs re-reading" % handicapped_at)


def test_the_30_lead_does_not_survive_on_a_single_world(sweep):
    """The lead at 30 is an average, and one world is enough to see it go.

    Over the three qualified worlds the agenda leads the control at 30
    (0.335 against 0.333). On world 0 alone it does not: 0.112 against
    0.167. The three-world lead is real and it is the one the report
    states, but it is two hundredths wide on a substrate where a single
    world reverses it, so "the agenda leads at 30" should not be read as
    "the agenda leads at 30 wherever you happen to run it".

    This is why the handicap count and the sign have to be read together.
    On world 0 only 10 of 196 rules beat the control at 30, against 94 of
    196 over three worlds -- a count that moves by a factor of nine with
    the averaging, in the same direction as the sign.
    """
    control_three = {row["arm"]: row for row in sweep[30]["arms"]}
    control_one = {row["arm"]: row
                   for row in agenda_policy.control_competence(
                       30, worlds=(0,))["arms"]}

    assert control_three["control"]["rules_beating_it"] > \
        control_one["control"]["rules_beating_it"], (
        "the count of rules beating the control at 30 is %d over three "
        "worlds and %d over one; the counts no longer diverge with the "
        "world set, so whatever this test recorded about them has changed"
        % (control_three["control"]["rules_beating_it"],
           control_one["control"]["rules_beating_it"]))


def test_the_hardcoded_single_budget_check_still_agrees_with_the_sweep(sweep):
    """The committed test is narrow, not wrong. Pin that it is right.

    `test_s09sel_divergence` asserts the default is unbeaten at 40. The
    sweep agrees at 40 and disagrees at 20, 30 and 60. If the two ever stop
    agreeing *at 40* then one is measuring something other than
    competence, and that needs reading rather than resolving by editing
    whichever file is inconvenient.

    What this pins is optimality, not identity. Changing `DEFAULT_RULE`
    from software depth 5 to depth 4 leaves it optimal at 40 and this test
    stays green, which is the right answer -- a different but equally
    strong constant is not a defect. The mutation was run and recorded as
    **inert** rather than counted as a verification: a mutation that cannot
    be observed is not a mutation, and a test that pins identity instead
    would be pinning an accident of the search rather than the property the
    report cites.
    """
    at_40 = {row["arm"]: row for row in sweep[40]["arms"]}

    assert at_40["control"]["rules_beating_it"] == 0, (
        "the ladder sweep finds %d rules beating the default at budget 40 "
        "while test_s09sel_divergence asserts none do; the two "
        "measurements have diverged and the competence test is no longer "
        "evidence for the claim cited to it"
        % at_40["control"]["rules_beating_it"])
    assert at_40["control"]["optimal_here"], (
        "the default is not optimal at the one budget where the committed "
        "competence test runs, so the report's citation no longer points "
        "at a budget where its claim holds")


def test_the_qualification_scores_the_measure_the_study_reports(sweep):
    """The yardstick has to read the same column the conclusion does.

    Competence measured on a column nobody reports would leave the
    handicap unmeasured in the only currency the result is stated in, and
    the arm could be optimal there and lose on the reported measure.
    """
    assert "held_out_reduction" in selection.YIELD_MEASURES, (
        "the measure this study reports is no longer in the frozen set, so "
        "the competence search is scoring something the result ignores")

    for budget in LADDER:
        assert sweep[budget]["arms"], (
            "budget %d reported no qualified arm" % budget)
    assert any(not row["optimal_here"]
               for budget in LADDER for row in sweep[budget]["arms"]), (
        "every arm is now optimal at every budget; the handicap this file "
        "exists to record has closed and the qualified ladder should be "
        "re-read as a plain crossover")
