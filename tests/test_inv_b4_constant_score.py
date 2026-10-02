"""B4: a rule's score measures the arm, not the number of worlds it ran on.

`_score_constant_rules` returned `sum(...)` over `worlds` while every arm row
it is read beside is a mean over the same worlds (`e3_ladder._aggregate` and
`s09_e3_selection.qualified_ladder` both divide by the cell count). Two
consequences, both measured rather than argued.

**The scale was three times the scale it was read on.** `held_out_reduction`
is a rate in `[0, 1]` (`selection.Yield.__init__` refuses anything else), so
summing three of them lands near 3.0, and dividing by 3 to recover the mean
is an identity. That is where "the ratio is exactly 3.0 at every non-zero
budget" came from (`reports/workstreams/w3-reproduce.md:48-59`). It could not
fail, so confirming it confirmed nothing.

**The count depended on the world set.** A sum over N worlds grows with N, so
a three-world search and a one-world search of the identical rule scored
different numbers for the identical arm. `rules_beating_it` and `gap_to_best`
in `control_competence` are read off those numbers, so the handicap count
that qualifies every reported E3 arm was partly a count of worlds.

The fix is one aggregation, `sum(...) / len(worlds)`. The regression is here.

## What the old 3.0 does and does not mean

The archived `w3-reproduce.md` and `reports/STAGE-09-COMPLETION-MATRIX.md:193`
keep the 3.0, and it stays. It is true, it was true at the commit that
produced it, and it is a correct statement that `SUM == 3 * MEAN` over three
worlds. What it is not is a measurement: it holds for any inputs, so it never
supported anything.

**The direction survives.** The agenda's held-out lead over the specified
control at 14 and its deficit from 20 upward are signs, and dividing every
score by the same three is monotone, so no sign can move. The archived
direction claim stands on its own reasoning.

**Ratios, gaps and counts do not transfer.** The `2.7x` oracle figure, the
`gap_to_best` column and every cross-scale `rules_beating_it` were computed by
mixing a sum with a mean. They are wrong and stay wrong. Nothing here
re-derives them on the old scale, because a corrected scale is not
comparable to a wrong one and a reader placing the two side by side would be
comparing units.

## Why the freeze is a pinned artifact and not a computed fixture

`control_competence(budget)` sweeps 196 rules over 3 worlds and refits
`fitted_fixed_rule` over the same space. Measured at this tip it costs 893.6 s
at budget 20 alone, so the six-budget ladder is roughly 90 minutes. A test
module cannot re-derive it inside a gate, and a fixture that quietly skipped
the expensive half would be the same vacuous assertion this lane exists to
remove.

So the crossover is re-derived once, offline, at **one budget**, and written
to `reports/evidence/invr1b4-mean-score/b4-crossover-mean.json`. The cheap
regression below re-derives the score itself from the instrument on every
run; the artifact tests pin what the single sweep found. One budget yields a
sign and a gap, not a first-crossing budget, and the artifact says so rather
than widening the sweep to manufacture a crossing. The re-derivation command
and its wall time are recorded in `reports/workstreams/b4-score.md`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import agenda_policy
from experiments.ad01 import e3_ladder
from experiments.ad01 import selection

# The world values below were read off the instrument at this tip, one
# `run_investigations` call per world, and are written down as literals so a
# change in the substrate is visible rather than absorbed into a
# recomputation. At budget 40 `DEFAULT_RULE` holds out 0.31746031746031744,
# 0.3014069264069264 and 0.45897435897435895 on worlds 0, 1 and 2; their mean
# is 0.35928053428053425, which `reports/evidence/
# inv_r1_e3_fitted_control/RESULT.md:42` already reports the default at under
# the name MEAN.
DEFAULT_RULE = {"software": ("ddmin", 5), "graph": ("ddmin", 1)}
DEFAULT_WORLD_VALUES_AT_40 = (0.31746031746031744, 0.3014069264069264,
                              0.45897435897435895)
DEFAULT_MEAN_AT_40 = 0.35928053428053425
DEFAULT_SUM_AT_40 = 1.0778416028416027

# A second rule so the first is not the only number the fix owes. At budget
# 40 it differs from the default by more than a factor of two.
GREEDY_RULE = {"software": ("greedy", 3), "graph": ("greedy", 2)}
GREEDY_WORLD_VALUES_AT_40 = (0.13124805477746654, 0.12848230201171376,
                             0.1312073547367665)
GREEDY_MEAN_AT_40 = 0.13031257050864894

BUDGET_40 = 40

# The archived directories this freeze must not touch. Listed so the
# path test names them rather than asserting a directory is untouched by
# absence, and so a reader can see what "byte-identical" is measured
# against.
ARCHIVED_E3 = (
    "reports/evidence/inv_r1_e3_selection",
    "reports/evidence/inv_r1_e3_ladder",
    "reports/evidence/inv_r1_e3_fitted_control",
    "reports/evidence/inv_r1_e3_selection_regen_v2",
)


def _score_one_rule(rule: dict, worlds, budget: int) -> float:
    """The score the search assigns one named rule, at one budget.

    `depths` narrows the depth ladder for both families, so the space it
    leaves is 2x2 methods at one depth each. The rule under test is then
    picked out of that list by identity rather than by position, and the
    whole scored list is searched for it -- so the returned number is the
    function's own score for that rule and not a re-derivation of it. The
    expected value is a literal in this file either way.
    """
    depths = (rule["software"][1], rule["graph"][1])
    scored = agenda_policy._score_constant_rules(
        budget, tuple(worlds), depths, "held_out_reduction")
    wanted = {family: tuple(value) for family, value in rule.items()}
    found = [score for score, candidate in scored
             if {family: tuple(value) for family, value
                 in candidate.items()} == wanted]
    assert len(found) == 1, (
        "the search space at depths %r should hold %r exactly once, and the "
        "scorer returned %d scores for it"
        % (depths, wanted, len(found)))
    return found[0]


def test_the_score_is_the_mean_of_the_world_values_not_their_sum():
    """The defect, against a literal rather than against itself.

    The mean is 0.35928053428053425. The sum the function used to return is
    1.0778416028416027. The two differ by a factor of three at this world
    count, so this cannot pass under the old code, and the expected value is
    a literal rather than anything the function supplies.
    """
    scored = _score_one_rule(DEFAULT_RULE, (0, 1, 2), BUDGET_40)

    assert scored == pytest.approx(DEFAULT_MEAN_AT_40), (
        "the constant-rule score at budget 40 is %r; the three world values "
        "%r have mean %r, so this is a sum and not a mean"
        % (scored, list(DEFAULT_WORLD_VALUES_AT_40), DEFAULT_MEAN_AT_40))
    assert scored != pytest.approx(DEFAULT_SUM_AT_40), (
        "the score is %r, which is the sum this lane replaced; a mean and a "
        "sum over three worlds are the same number only if every world "
        "scored zero" % scored)


def test_the_score_does_not_grow_with_the_number_of_worlds():
    """The invariance the sum broke, and the test that would have caught it.

    Repeating a world is the only world-set change a mean has to ignore: the
    rule, the budget and every value entering the score are identical, and
    only the number of summands differs. Under a sum the same rule scored
    0.31746031746031744 over `(0,)` and 0.6349206349206349 over `(0, 0)`, so
    this goes red the moment the mean is replaced by the sum again, at any
    world count and at any budget.

    Adding a *different* world is not part of this assertion, and the
    distinction is the point. A mean over `(0, 1, 2)` is 0.35928053428053425
    and a mean over `(0,)` is world 0's own 0.31746031746031744. Those
    differ because the value sets differ, which is what averaging is. Only
    repetition leaves the value set alone, so only repetition is invariant.
    """
    one = _score_one_rule(DEFAULT_RULE, (0,), BUDGET_40)
    twice = _score_one_rule(DEFAULT_RULE, (0, 0), BUDGET_40)
    thrice = _score_one_rule(DEFAULT_RULE, (0, 0, 0), BUDGET_40)

    assert one == pytest.approx(twice) == pytest.approx(thrice), (
        "the same rule at the same budget scored %r, %r and %r over one, two "
        "and three copies of the same world; the score is still a function of "
        "how many times a value was folded in, so every cross-world-set "
        "comparison it feeds is partly a count of worlds"
        % (one, twice, thrice))
    assert one == pytest.approx(DEFAULT_WORLD_VALUES_AT_40[0]), (
        "one world of the default rule at budget 40 scores %r, which is not "
        "that world's own held-out value %r; a single-world mean is the value"
        % (one, DEFAULT_WORLD_VALUES_AT_40[0]))


def test_the_score_is_a_mean_and_not_a_sum_on_a_repeated_world():
    """The same property, stated as a literal rather than as an equality.

    Two assertions of the same idea, one of them pinned to a number written
    down here. Under the sum, `(0, 0)` is 0.6349206349206349 and this goes
    red on the printed value rather than on a comparison, so a reader can
    check the arithmetic by hand without running the search.
    """
    twice = _score_one_rule(DEFAULT_RULE, (0, 0), BUDGET_40)
    twice_sum = 2 * DEFAULT_WORLD_VALUES_AT_40[0]

    assert twice == pytest.approx(DEFAULT_WORLD_VALUES_AT_40[0]), (
        "two copies of world 0 scored %r; world 0's own held-out value is %r "
        "and the sum the old scorer returned was %r"
        % (twice, DEFAULT_WORLD_VALUES_AT_40[0], twice_sum))
    assert twice != pytest.approx(twice_sum), (
        "the score is %r, which is the sum over the repeated world; the mean "
        "over two copies of one value is that value" % twice)


def test_a_second_rule_lands_on_its_own_literal_mean():
    """A second anchor, so the first is not the only number the fix owes.

    One rule at one budget is one data point, and a scorer that returned some
    fixed or degenerate value could satisfy it. `GREEDY_RULE` at 40 has three
    world values of its own, averaging 0.13031257050864894.
    """
    scored = _score_one_rule(GREEDY_RULE, (0, 1, 2), BUDGET_40)

    assert scored == pytest.approx(GREEDY_MEAN_AT_40), (
        "the greedy constant rule scored %r over worlds 0, 1 and 2; its "
        "world values %r average to %r"
        % (scored, list(GREEDY_WORLD_VALUES_AT_40), GREEDY_MEAN_AT_40))


def test_the_scorer_agrees_with_the_instrument_on_every_world():
    """The mean is the mean: recomputed from the runs, not from the scorer.

    This one is deliberately derived, and it is the test that catches a fix
    that changed the aggregation while leaving the measurement alone. The
    score has to equal the arithmetic mean of the same quantity read straight
    off `run_investigations` per world, because those are the numbers an arm
    row is built from.
    """
    for rule, expected in ((DEFAULT_RULE, DEFAULT_MEAN_AT_40),
                           (GREEDY_RULE, GREEDY_MEAN_AT_40)):
        per_world = [
            selection.run_investigations(
                None, agenda_policy.FixedPolicy(dict(rule)),
                selection.Allocation(authorized=BUDGET_40),
                world=world).yield_.held_out_reduction
            for world in selection.WORLDS]
        scored = _score_one_rule(rule, selection.WORLDS, BUDGET_40)
        instrument_mean = sum(per_world) / len(per_world)

        assert scored == pytest.approx(instrument_mean), (
            "rule %r at budget %d scored %r while its per-world held-out "
            "values %r average to %r"
            % (rule, BUDGET_40, scored, per_world, instrument_mean))
        assert scored == pytest.approx(expected), (
            "rule %r at budget %d no longer scores its recorded literal %r"
            % (rule, BUDGET_40, expected))


def test_the_yardstick_search_reports_on_the_arm_scale():
    """The public consumer of the score, on the same scale as an arm row.

    `constant_rule_search` is the yardstick every reported advantage is read
    against, and it publishes `best_score` straight off the scorer. It is
    exercised on a one-rule space so the number it owes is the literal mean of
    a known rule rather than a 196-rule sweep nobody can re-derive by hand.
    The bound asserted is the one that catches a sum: `held_out_reduction` is
    typed a rate in `[0, 1]` and this module refuses anything else.
    """
    search = agenda_policy.constant_rule_search(
        BUDGET_40, worlds=selection.WORLDS,
        depths=(DEFAULT_RULE["software"][1], DEFAULT_RULE["graph"][1]),
        objective="held_out_reduction")

    assert search["searched"] == 16, (
        "two methods per family at one depth each is a 16-rule space, not "
        "%d" % search["searched"])
    assert 0.0 <= search["best_score"] <= 1.0, (
        "the yardstick reports best_score %r, outside the [0, 1] rate "
        "held_out_reduction is typed as; the search is still summing"
        % search["best_score"])
    assert search["best_score"] == pytest.approx(
        _score_one_rule(search["best_rule"], selection.WORLDS, BUDGET_40)), (
        "the yardstick's best_score %r is not the score the same function "
        "assigns the rule it names, %r"
        % (search["best_score"], search["best_rule"]))
    assert search["best_score"] >= DEFAULT_MEAN_AT_40, (
        "the best of 16 rules at depths (5, 1) scores %r, below the default's "
        "%r, which is in that space; the search is not ranking the space"
        % (search["best_score"], DEFAULT_MEAN_AT_40))


def test_the_agenda_arm_and_the_scorer_agree_on_the_same_rule():
    """One scale for the two sides of the comparison being qualified.

    `e3_ladder._aggregate` divides by the cell count and the scorer now takes
    a mean over the same worlds, so an arm's `held_out_reduction_mean` and the
    score beside it are in the same units. That is what makes "the agenda is
    behind the best rule in the space" a comparison rather than a ratio of two
    currencies.
    """
    arm = e3_ladder._run_arm("control", BUDGET_40, selection.WORLDS,
                             shared=False)
    scored = _score_one_rule(DEFAULT_RULE, selection.WORLDS, BUDGET_40)

    assert arm["held_out_reduction_mean"] == pytest.approx(scored), (
        "the ladder reports the control arm's mean at %r and the scorer "
        "reports the same rule at %r for the same budget and the same three "
        "worlds" % (arm["held_out_reduction_mean"], scored))
    assert 0.0 <= arm["held_out_reduction_mean"] <= 1.0, (
        "the arm mean is %r, outside the [0, 1] rate held_out_reduction is "
        "typed as" % arm["held_out_reduction_mean"])


# --- the new freeze --------------------------------------------------------

# The one budget the freeze measures. 40 is where the committed competence
# test runs and where the specified control ties the best rule in its own
# space, so the yardstick discriminates rather than reporting a gap the
# default cannot close.
FREEZE_PATH = "reports/evidence/invr1b4-mean-score/b4-crossover-mean.json"


@pytest.fixture(scope="module")
def freeze() -> dict:
    path = ROOT / FREEZE_PATH
    if not path.exists():
        pytest.fail(
            "the new freeze is not committed at %s. It is re-derived offline "
            "by experiments.ad01.b4_constant_score.build(budget=40), which "
            "calls agenda_policy.control_competence once; the command and its "
            "wall time are in reports/workstreams/b4-score.md. That call "
            "costs about 894 s, which is why it is a module and a committed "
            "artifact rather than a fixture." % FREEZE_PATH)
    return json.loads(path.read_text())


def test_the_crossover_is_frozen_in_a_new_namespace(freeze):
    """The freeze exists, under a path of its own, on the mean scale.

    The path is new, so the archived E3 evidence cannot be overwritten even
    by accident. Every reported score is inside the rate bound, which is the
    signature that separates a mean from the sum it replaced.
    """
    assert freeze["freeze"] == (
        "new-freeze, not comparable to the archived E3 figures")
    assert freeze["score_scale"] == (
        "mean held_out_reduction over the qualified worlds")
    assert freeze["worlds"] == list(selection.WORLDS)
    assert freeze["budgets"] == [BUDGET_40], (
        "the freeze reports budgets %r; it is single-budget by construction, "
        "and a multi-budget freeze claiming a first-crossing budget would be "
        "claiming a measurement it did not make" % freeze["budgets"])
    assert freeze["measure_digest"] == selection.assert_measure_freeze(), (
        "the freeze was taken against measure digest %r and the frozen set "
        "now hashes to %r, so its row was scored on a different measure set "
        "than the one this tip reports"
        % (freeze["measure_digest"], selection.assert_measure_freeze()))
    assert freeze["policy_instance_scope"] == "one-per-cell", (
        "the freeze reports policy instance scope %r; a shared instance "
        "reproduces N-80, which reports/evidence/inv_r1_e3_selection/"
        "RETRACTED.md withdraws" % freeze["policy_instance_scope"])

    for row in freeze["rows"]:
        assert row["budget"] == BUDGET_40
        assert 0.0 <= row["best_rule_held_out_mean"] <= 1.0, (
            "budget %d reports a best rule score of %r, outside the [0, 1] "
            "rate held_out_reduction is typed as; the freeze was written off "
            "a sum" % (row["budget"], row["best_rule_held_out_mean"]))
        for name, arm in row["arms"].items():
            assert 0.0 <= arm["held_out_mean"] <= 1.0, (
                "arm %r at budget %d reports %r, outside the [0, 1] rate "
                "held_out_reduction is typed as"
                % (name, row["budget"], arm["held_out_mean"]))
        assert row["rules_searched"] == 196, (
            "budget %d searched %d constant rules, not the 196 the space "
            "contains" % (row["budget"], row["rules_searched"]))
        assert 0 <= row["control_rules_beating_it"] <= row["rules_searched"], (
            "budget %d reports %d of %d rules beating the control, which is "
            "not a count" % (row["budget"], row["control_rules_beating_it"],
                             row["rules_searched"]))
        assert row["control_gap_to_best"] >= -1e-12, (
            "the control's gap to the best in the space is %r; the best is by "
            "construction the maximum over it" % row["control_gap_to_best"])


def test_the_re_derived_crossover_is_the_documented_value(freeze):
    """The crossover, as a value, rather than as a recomputation.

    One budget, so this is a sign and a gap, not a first-crossing budget. The
    artifact says so in `crossover_scope` and this asserts it, because a
    single-budget freeze that quietly reported a crossing budget would be
    claiming a measurement nobody could re-derive.
    """
    crossover = freeze["crossover"]
    measured = freeze["rows"][0]

    assert "single budget" in freeze["crossover_scope"], (
        "the freeze does not state that it is single-budget; its scope field "
        "reads %r" % freeze["crossover_scope"])
    assert crossover["budgets_measured"] == [BUDGET_40]
    assert crossover["first_budget_behind_is_claimed"] is False, (
        "the freeze claims a first-crossing budget of %r from a single-budget "
        "measurement, which is a number no one can re-derive"
        % crossover["first_budget_behind_the_best_constant_rule"])
    assert crossover["first_budget_behind_the_best_constant_rule"] is None
    assert crossover["agenda_beats_the_best_constant_rule"] is False, (
        "the agenda now holds out %r against the best of %d constant rules at "
        "budget %d, so it beats exhaustive search over its own family and "
        "every negative E3 result needs revisiting"
        % (measured["arms"]["agenda"]["held_out_mean"],
           measured["rules_searched"], BUDGET_40))
    assert crossover["agenda_held_out_mean"] == pytest.approx(
        measured["arms"]["agenda"]["held_out_mean"]), (
        "the crossover block reports %r and the row reports %r for the same "
        "arm at the same budget"
        % (crossover["agenda_held_out_mean"],
           measured["arms"]["agenda"]["held_out_mean"]))
    assert crossover["best_rule_held_out_mean"] == pytest.approx(
        measured["best_rule_held_out_mean"]), (
        "the crossover block reports a best of %r and the row reports %r"
        % (crossover["best_rule_held_out_mean"],
           measured["best_rule_held_out_mean"]))
    assert measured["best_rule_held_out_mean"] >= max(
        arm["held_out_mean"] for arm in measured["arms"].values()), (
        "the best rule in the space scores below one of the arms in it, so "
        "the yardstick and the arms were scored on different scales")


def test_the_archived_figures_are_not_restated_here(freeze):
    """The freeze says what it is not, so a reader cannot read it as a
    replacement.

    The new numbers are on a corrected scale. Placing them in the same column
    as the archived ones would invite exactly the mixed-denominator comparison
    this lane removed, so the artifact names each retired figure and the
    reason it does not carry over. The retention cost ledger is named
    separately because a reader could mistake this crossover freeze for a
    retraction of a *different* crossover.
    """
    refusals = " ".join(freeze["what_this_is_not"]).lower()

    assert "inv_r1_e2_retention" in refusals, (
        "the freeze does not disclaim the retention cost ledger, whose "
        "crossover_uses of 5.0 is a reservation-unit crossover on a "
        "different question and is not touched by this repair; a reader could "
        "mistake this freeze for a retraction of it")
    assert "3.0" in refusals, (
        "the freeze does not disclaim the 3.0 ratio; that figure is true and "
        "stays, it is an identity rather than a measurement")
    assert "2.7x" in refusals, (
        "the freeze does not disclaim the 2.7x oracle ratio, which paired a "
        "sum with a mean and is wrong on either scale")
    for directory in ARCHIVED_E3:
        assert directory in refusals, (
            "the freeze does not name %s among the artifacts it does not "
            "replace" % directory)
    assert "not comparable" in freeze["freeze"].lower(), (
        "the freeze does not label itself as not comparable to the archived "
        "figures, which is the whole point of writing it to a new namespace")
    assert "direction" in freeze["direction_survives"].lower(), (
        "the freeze does not record what the archived direction claim does "
        "and does not survive, which is the part a reader has to carry "
        "forward")


def test_the_handicap_is_a_measurement_and_not_a_world_count(freeze):
    """The defect's second half: the count has to depend on the arm.

    A sum made `rules_beating_it` partly a count of worlds. On the mean it is
    a property of the control, and at budget 40 the committed record has the
    specified control optimal in its own space:
    `inv_r1_e3_fitted_control/RESULT.md:42` reports a tie at 40, and
    `tests/test_s09sel_divergence.py` asserts none of the 196 rules beats it
    there. This pins that, which is what makes the handicap claim a
    measurement rather than a scale artefact. It does not pin a count above
    zero, because `test_s09_e3_control_competence.py:12-20` shows the counts
    are world-set dependent and a threshold on them tests the world set.
    """
    measured = freeze["rows"][0]

    assert measured["control_rules_beating_it"] == 0, (
        "%d of 196 constant rules beat the specified control at budget 40, "
        "where the committed record has it optimal; on the mean scale that "
        "count is zero, and a nonzero value means the freeze was written off "
        "a sum" % measured["control_rules_beating_it"])
    assert measured["control_optimal_here"] is True
    assert measured["control_gap_to_best"] == pytest.approx(0.0, abs=1e-12), (
        "the control's gap to the best in the space is %r at budget 40, where "
        "it is recorded as tying; a gap near 0.36 would be the sum's scale "
        "and the mean's is 0" % measured["control_gap_to_best"])
