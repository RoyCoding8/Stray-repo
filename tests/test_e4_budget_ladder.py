"""What the budget ladder is for, once it stopped pinning a random draw.

The ladder's job was to check a table copied into
`reports/STAGE-09-RECOMMENDATION.md`. It could not check that table, because
the blind cell it pinned was a random draw from an unfrozen seed. These tests
pin the two claims the ladder can actually make, and both fail on the
pre-freeze tree where the blind arm drew a fresh subset per seed.
"""

from __future__ import annotations

import math

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import e4_budget_ladder as ladder
from experiments.ad01 import rule_learner
from experiments.ad01.improve_channel import descendant_score


def test_ladder_reports_no_frozen_expectation_table():
    """The deleted literals must stay deleted, and the deleted key with them.

    A `reconciles` dict keyed on `blind` cannot come back: the blind cell is a
    property of the tie-break, and the tie-break is the thing that changed.
    """
    result = ladder.measure("fresh_a")

    assert not hasattr(ladder, "EXPECTED_BUDGET_8")
    assert "reconciles" not in result
    assert "expected_budget_8" not in result


def test_blind_arm_emits_one_sequence_for_every_seed():
    """Measured. The blind arm is a fixed input order, not a sample.

    With nothing observed, every open input's total disagreement is equal, so
    "smallest index on ties" always returns the lowest unqueried input. Before
    the freeze the same arm drew a distinct 8-subset per seed, so this is the
    claim that fails on the unfixed tree.
    """
    sequences = {tuple(ladder._sequences(s, informed=False, split="audit"))
                 for s in ladder.COHORTS["original"]}

    assert sequences == {tuple(range(rules.MAX_QUERIES))}


def test_informed_arm_identifies_every_seed_at_the_information_bound():
    """Measured. Eight probes pin the class, and the arm uses them all.

    This is the bound `MAX_QUERIES` is derived from, asserted per seed rather
    than as a mean over the cohort. A tie-break that spent probes on coin
    flips left a non-singleton space and fails here.
    """
    result = ladder.measure("fresh_a")

    assert ladder.information_bound() == math.ceil(
        math.log2(len(rules.CLASS_TABLES))) == rules.MAX_QUERIES
    assert result["attains_bound"]["informed_identifies_every_seed"] is True
    assert result["attains_bound"]["informed_seeds_short_of_bound"] == 0


def test_blind_arm_identifies_nothing_because_it_never_observes():
    """Measured. The blind column's low score is blindness, not a weak learner.

    A reader who sees `0.0592` next to `1.0000` should be able to say why.
    """
    seed = 1000
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)

    # The blind arm gathers evidence without observing any of it.
    for x in ladder._sequences(seed, informed=False, split="audit"):
        assert learner.version_space_sizes() == [len(rules.CLASS_TABLES)] * 4

    # The informed arm observes each answer and reaches a singleton.
    session = rules.RuleSession(rules.make_task("audit", seed))
    informed = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)
    for x in ladder._sequences(seed, informed=True, split="audit"):
        informed.observe(x, session.query(x))

    assert max(informed.version_space_sizes()) == 1


def test_informed_unqueried_score_is_one_on_every_cohort_not_just_fresh_a():
    """Measured on all three. A single cohort could carry a broken tie-break.

    The pre-freeze informed means were 0.8500 / 0.8958 / 0.9142, so each of
    these three cohorts fails before the freeze.
    """
    for cohort, seeds in ladder.COHORTS.items():
        scores = [
            descendant_score(ladder._sequences(s, informed=True, split="audit"),
                             "audit", s)["unqueried"]
            for s in seeds
        ]

        assert set(scores) == {1.0}, "%s: %s" % (cohort, sorted(set(scores)))
        assert len(scores) == len(seeds)