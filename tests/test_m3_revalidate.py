"""The re-derivation itself must be re-runnable, not asserted in prose.

`reports/workstreams/m3-revalidation.md` reports figures. These tests pin the
three that carry the report's conclusion, so a future freeze cannot quietly
move them the way `44ec6c52` moved the ladder.
"""

from __future__ import annotations

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import m3_revalidate as rv


def test_recorded_budget_8_figures_reproduce_under_the_pre_freeze_learner():
    """All six recorded figures come back exactly, under the old tie-break.

    This is what attributes them: if the reconstruction is faithful, the
    recommendation's numbers are a measurement of `PreFreezeLearner`, not a
    claim about the instrument.
    """
    rows = rv.reproduce()

    for cohort in rv.COHORTS:
        assert rows[cohort]["pre_freeze_reproduces"] is True, cohort


def test_no_recorded_figure_survives_under_the_frozen_learner():
    """Measured. The freeze moved all three cohorts, blind and informed.

    Asserting the negative as well as the positive: a re-derivation that
    confirmed the recorded numbers under the new learner would be a different
    claim from the one this report makes.
    """
    rows = rv.reproduce()

    for cohort in rv.COHORTS:
        assert rows[cohort]["frozen_reproduces"] is False, cohort
        assert rows[cohort]["frozen"]["informed"] == 1.0, cohort


def test_pre_freeze_random_miss_count_is_a_range_not_a_number():
    """The 64-of-224 figure needs the seed convention `always_zero` to appear.

    Under `class_index` it is 125 and under `class_table_value` it is 126, so
    a report that quoted 64 without the convention would be quoting a seed.
    """
    ident = rv.identification()
    by_convention = ident["pre_freeze_random"]["missed_by_seed_convention"]

    assert by_convention["always_zero"] == 64
    assert by_convention["class_index"] == 125
    assert set(by_convention.values()) != {64}


def test_blind_subset_is_the_tie_break_loser_not_a_typical_subset():
    """The blind arm's 0.06 is one unlucky subset, not what blindness scores.

    Every open input ties at zero observations, so the frozen rule returns the
    lowest unqueried input every time. Ranked exhaustively against all 12870
    eight-subsets, that subset sits near the bottom, far below the 0.5161 mean.
    """
    arm = rv.blind_arm_mechanism()

    assert arm["blind_sequences_distinct"] == 1
    assert arm["blind_sequence"] == list(range(rules.MAX_QUERIES))
    assert arm["blind_ties_with_every_open_input"] is True
    assert arm["subset_rank_exhaustive"]["blind_rank_from_worst"] < 100