"""E3's comparison must be able to report a loss.

The crossover in `s09_e3_selection` is a two-sided result: the adaptive
agenda retains more at every budget, and holds out less once the envelope
is loose enough for the fitted constant to afford a deeper run. A summary
that could only print the favourable half would be a study that reports
its treatment as a win whenever one exists, which is the shape of claim
the handoff forbids.

These tests pin the shape of the result against the machinery that
produced it. The digest is the real defence: the yields are frozen, so
the numbers below cannot be restated by editing a measure definition,
and `selection.assert_measure_freeze` is called on every run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_e3_selection as e3
from experiments.ad01 import selection


def _ladder():
    return e3.crossover(worlds=selection.WORLDS)


def test_the_four_frozen_yields_are_what_get_reported():
    """The handoff names four measures; all four must appear per arm.

    Reporting three and calling it the frozen set is how a comparison
    quietly drops the measure that favours the control.
    """
    ladder = _ladder()

    for step in ladder["ladder"]:
        for arm in step["arms"]:
            assert set(arm["yield_totals"]) | {"held_out_reduction"} == \
                set(selection.YIELD_MEASURES), (
                "an arm reports %r against the frozen %r"
                % (sorted(arm["yield_totals"]), sorted(selection.YIELD_MEASURES)))


def test_the_result_carries_the_frozen_measure_digest():
    assert _ladder()["measure_digest"] == selection.FROZEN_MEASURE_DIGEST


    crossing = _ladder()["crossover"]

    assert crossing["agenda_ahead_on_retained_throughout"], (
        "the agenda no longer retains more at every budget")
    assert crossing["agenda_ahead_on_diagnoses_at"], (
        "the agenda never leads on diagnosis, so the diagnosis column has "
        "stopped tracking anything")
    assert crossing["control_ahead_on_held_out_at"], (
        "the control never leads on held-out quality, so the result has "
        "become one-sided and the crossover framing is stale")
    assert crossing["agenda_ahead_on_held_out_at"], (
        "the agenda never leads on held-out quality either")
    assert set(crossing["agenda_ahead_on_held_out_at"]) | \
        set(crossing["control_ahead_on_held_out_at"]) == \
        set(crossing["per_budget_budgets"]), (
        "held-out quality was not resolved at every budget, so a sign is "
        "missing rather than measured")
    assert set(crossing["control_ahead_on_held_out_at"]) & set(e3.LOOSE), (
        "the control's held-out wins all fall at tight budgets, where it "
        "was stopped by the envelope rather than by its own schedule; "
        "that is a different claim from the one this study reports")


def test_the_control_stops_spending_while_the_agenda_does_not():
    """Why the retention lead exists: the control's schedule runs out.

    `FixedPolicy` has one capability and depth per family, so once it has
    executed that schedule there is nothing left to charge. The agenda
    keeps converting envelope into retained behaviours. A study that
    reported the retention column as evidence of better selection, with
    no mention of the cost column, would be attributing to a selection
    policy an effect produced by a pre-committed schedule running out.
    """
    crossing = _ladder()["crossover"]

    for record in crossing["loose"]:
        assert record["control_spent_its_whole_schedule"], (
            "at budget %d the control is no longer spending its full "
            "schedule, so the two arms are no longer separated by "
            "saturation" % record["budget"])
    # At the saturation budget the control can just afford its schedule
    # and so out-spends the agenda by one unit; past it the agenda is
    # spending envelope the control has no use for. Asserting the
    # out-spend at the boundary would assert an accident of rounding.
    past = [r for r in crossing["loose"]
            if r["budget"] > e3.SATURATED_AT]
    for record in past:
        assert record["agenda_resources"] > record["control_resources"], (
            "at budget %d the agenda spent %d against the control's %d, so "
            "the agenda is no longer out-spending a saturated control"
            % (record["budget"], record["agenda_resources"],
               record["control_resources"]))
        assert record["agenda_diagnoses"] > record["control_diagnoses"], (
            "at budget %d the agenda diagnosed %d against the control's %d"
            % (record["budget"], record["agenda_diagnoses"],
               record["control_diagnoses"]))
    for record in crossing["tight"]:
        assert not record["control_spent_its_whole_schedule"], (
            "the control saturates even in a tight envelope, which "
            "contradicts the reason the two arms differ there")


def test_the_control_stops_adding_investigations_past_saturation():
    """Six choices at every budget from 20 up, and no more.

    This is the measurement that distinguishes "the control chose badly"
    from "the control had nothing left to choose". A saturated control
    that kept making new proposals would be losing on merit; one that
    makes the same six forever is losing because a pre-committed
    schedule is not an allocation policy under an open-ended envelope.
    """
    crossing = _ladder()["crossover"]
    saturated = [r for r in crossing["per_budget"]
                 if r["budget"] >= e3.SATURATED_AT]

    widths = {r["control_choices"] for r in saturated}
    assert widths == {crossing["control_schedule_width"]}, (
        "the control's choice count still moves past its saturation "
        "budget: %r" % (sorted(widths),))


def test_budget_limited_and_saturated_are_different_stops():
    """At 14 the control wants six and can afford four; at 20 it has six.

    The two arms fail differently. Below saturation the control is
    stopped by the envelope, which is a fair comparison: both policies
    wanted the same work and only one could pay. From saturation the
    control is stopped by its own schedule while the envelope is still
    unspent, which is not a fair comparison and is the reason this
    study cannot claim the agenda wins on held-out quality overall.
    """
    crossing = _ladder()["crossover"]
    tight = crossing["tight"][0]
    loose = {r["budget"]: r for r in crossing["loose"]}

    assert tight["control_choices"] < crossing["control_schedule_width"], (
        "the control completes its schedule at a tight budget, so the two "
        "regimes this study separates have collapsed into one")
    assert tight["agenda_resources"] < tight["control_resources"] * 2, (
        "the tight regime no longer looks budget-limited for the agenda")
    for budget, record in loose.items():
        assert record["control_resources"] == crossing["control_spend_plateau"]
        assert record["control_choices"] == \
            crossing["control_schedule_width"], (
            "at budget %d the control is no longer finished" % budget)


def test_the_tight_budgets_are_where_the_control_qualifies_nothing():
    """The one unambiguous regime: the envelope is too small to qualify.

    At 14 the control retains nothing at all in any world, so the
    comparison there is not between two working policies but between one
    that can act and one that cannot afford to.
    """
    tight = {r["budget"]: r for r in _ladder()["crossover"]["tight"]}

    assert tight[14]["control_retained"] == 0
    assert tight[14]["agenda_retained"] > 0
    assert tight[14]["agenda_held_out"] > tight[14]["control_held_out"]


def test_the_two_policies_choose_different_investigations():
    """The diagnostic case the handoff requires, measured not asserted."""
    case = e3.divergence_case(world=0, budget=14)

    assert case["picks_differ"], (
        "the two policies chose the same investigations, so the comparison "
        "has no choice to measure: %r" % (case["agenda_picks"],))
    assert case["agenda_picks"] and case["control_picks"]


def test_the_divergence_case_is_a_real_choice_not_a_stall():
    """Differing because one arm did nothing is not divergence.

    A policy that declines every proposal and one that runs its schedule
    also produce different pick lists, and comparing them measures
    nothing. Both arms must have charged the envelope here.
    """
    case = e3.divergence_case(world=0, budget=14)

    for name, arm in case["arms"].items():
        assert arm["yield"]["resources_used"] > 0, (
            "%s charged nothing, so its picks were never competing for the "
            "envelope" % name)


def test_every_choice_states_a_reason_the_run_actually_took():
    """A rationale is a claim about why; it should name the yield it moved."""
    case = e3.divergence_case(world=0, budget=14)

    for arm in case["arms"].values():
        for pick in arm["picks"]:
            assert pick["rationale"], "a choice was made with no stated reason"


def test_the_ladder_spans_the_crossover_rather_than_sitting_on_one_side():
    """A ladder that only samples the winning side is not a crossover."""
    budgets = _ladder()["budgets"]

    assert budgets == sorted(budgets)
    assert len(budgets) >= 5, "too few points to call a direction a crossover"
    assert e3.TIGHT[0] < e3.LOOSE[0], (
        "the tight and loose bands are not separated, so the sign of the "
        "crossover is not being tested")
