from __future__ import annotations

from experiments.representation.experiment import checker


def _record(result: dict, queries=None) -> dict:
    record = {"arm": "C", "task_id": "t1", "result": result}
    if queries is not None:
        record["oracle_queries"] = queries
    return record


def _problems(record: dict) -> list:
    problems: list = []
    checker._scores_derived(record, "C-t1", problems)
    return problems


def test_claimed_score_without_oracle_evidence_is_refused():
    problems = _problems(_record(
        {"verified": True, "best_measure": 50, "improvement_u": 0.5}))

    assert "score-without-oracle-evidence C-t1" in problems


def test_verified_true_with_no_preserved_query_is_refused():
    problems = _problems(_record(
        {"verified": True, "best_measure": 7, "improvement_u": 0.5},
        [{"verdict": "not_preserved", "measure": 7}]))

    assert any(p.startswith("verified-contradicts-oracle") for p in problems)


def test_best_measure_contradicting_the_queries_is_refused():
    problems = _problems(_record(
        {"verified": True, "best_measure": 3, "improvement_u": 0.1},
        [{"verdict": "preserved", "measure": 10}]))

    assert any(p.startswith("best-measure-contradicts-oracle") for p in problems)


def test_honest_preserved_record_is_accepted():
    problems = _problems(_record(
        {"verified": True, "best_measure": 10, "improvement_u": 0.2},
        [{"verdict": "preserved", "measure": 12},
         {"verdict": "not_preserved", "measure": 7},
         {"verdict": "preserved", "measure": 10}]))

    assert problems == []


def test_honest_failure_record_is_accepted():
    problems = _problems(_record(
        {"verified": False, "improvement_u": 0.0},
        [{"verdict": "not_preserved", "measure": 7}]))

    assert problems == []
