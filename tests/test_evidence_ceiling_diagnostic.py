"""Focused checks for the offline blind-versus-informed diagnostic."""

from __future__ import annotations

import pytest

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import evidence_ceiling_diagnostic as diagnostic
from experiments.ad01 import rule_learner


def _manual_score(evidence: list[int], seed: int) -> dict:
    task = rules.make_task(diagnostic.SPLIT, seed)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)
    for x in evidence:
        learner.observe(x, session.query(x))
    committed = session.commit_predictor(learner.predict(session.queried))
    predicted = committed["tables"]
    target = task["tables"]
    hits = [all(((predicted[bit] >> x) & 1) == ((target[bit] >> x) & 1)
                for bit in range(rules.N_OUTPUTS))
            for x in range(rules.N_STATES)]
    queried = set(evidence)
    unqueried = [x for x in range(rules.N_STATES) if x not in queried]
    return {
        "overall": sum(hits) / rules.N_STATES,
        "queried": sum(hits[x] for x in queried) / len(queried),
        "unqueried": sum(hits[x] for x in unqueried) / len(unqueried),
        "n_queried": len(queried),
    }


def test_diagnostic_score_matches_independent_rule_session_recompute():
    seed = 1000
    expected = _manual_score([3], seed)
    actual = diagnostic._score([3], seed)

    assert expected == {
        "overall": 3 / 16,
        "queried": 1.0,
        "unqueried": 2 / 15,
        "n_queried": 1,
    }

    for field in ("overall", "queried", "unqueried", "n_queried"):
        assert actual[field] == expected[field]


def test_blind_path_never_observes_but_informed_path_requires_observe(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("blind path called observe")

    monkeypatch.setattr(rule_learner.VersionSpaceLearner, "observe", fail)
    assert len(diagnostic._sequence(diagnostic.FRESH_SEEDS[0], informed=False)) == 8
    with pytest.raises(AssertionError, match="called observe"):
        diagnostic._sequence(diagnostic.FRESH_SEEDS[0], informed=True)


def test_blind_arm_is_one_fixed_subset_not_a_sample():
    """Measured. The blind column cannot be read as an average over subsets.

    Under the frozen tie-break the blind arm emits `[0..7]` on every seed.
    Before the freeze it drew a distinct subset per seed, so this assertion
    is what distinguishes a sample from a single subset.
    """
    result = diagnostic.run()

    assert result["blind_arm_is_seed_independent"] is True
    sequences = {tuple(row["sequences"]["blind8"])
                 for row in result["raw_rows"]}
    assert sequences == {tuple(range(rules.MAX_QUERIES))}


def test_historical_blind_reference_is_labelled_as_recomputed():
    """The withdrawn figure is 0.5017; the recomputed one is not.

    Reporting the recomputed value under the key `withdrawn_blind8` without
    saying so invites a reader to conclude the withdrawal corrected an error,
    when the freeze is what moved it.
    """
    result = diagnostic.run()
    historical = result["historical_e4_references"]

    assert historical["withdrawn_blind8"]["reducer_mean"] != 0.5017
    assert "RECOMPUTED" in historical["withdrawn_blind8_note"]
    assert historical["narrow_probe_ceiling"]["measured"] is True


def test_run_enforces_unique_fresh_cohort_and_primary_overall_contrast():
    result = diagnostic.run()
    cohort = result["fresh_cohort"]

    assert cohort["old_unique_task_ids"] == len(diagnostic.OLD_E4_SEEDS)
    assert cohort["fresh_unique_task_ids"] == len(diagnostic.FRESH_SEEDS)
    assert cohort["old_unique_truth_tables"] == len(diagnostic.OLD_E4_SEEDS)
    assert cohort["fresh_unique_truth_tables"] == len(diagnostic.FRESH_SEEDS)
    assert cohort["task_id_overlap_with_old_e4"] == 0
    assert cohort["truth_table_overlap_with_old_e4"] == 0
    primary = result["contrasts"]["primary_overall"][
        "informed8_vs_blind8_equal_cost"]
    assert primary["metric"] == "overall"
    assert primary["left"] == "informed8"
    assert primary["right"] == "blind8"
