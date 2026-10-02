"""M3 Boolean-rule discovery instrument: query limit, privacy, legality.

Failing-first lane. These tests import the not-yet-written instrument
(experiments.ad01.boolean_rule) and baseline learner
(experiments.ad01.rule_learner) and must go red before the fix, green after.
Pure in-memory, deterministic, no network, no database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import boolean_rule as br
from experiments.ad01 import rule_learner as rl


def _dev_task(seed=0):
    return br.make_task("dev", seed)


def test_eighth_query_ok_ninth_refused():
    session = br.RuleSession(_dev_task())
    for x in range(8):
        y = session.query(x)
        assert len(y) == 4
        assert all(b in (0, 1) for b in y)
    assert session.remaining == 0
    try:
        session.query(8)
    except br.RuleRefused as exc:
        assert exc.reason == "query-budget-exhausted"
    else:
        raise AssertionError("ninth query was admitted")


def test_query_feedback_is_only_the_four_output_bits():
    task = _dev_task(seed=1)
    session = br.RuleSession(task)
    for x in (0, 5, 15):
        y = session.query(x)
        expected = tuple((task["tables"][b] >> x) & 1 for b in range(4))
        assert y == expected
    assert session.queried == {
        x: tuple((task["tables"][b] >> x) & 1 for b in range(4))
        for x in (0, 5, 15)}


def test_duplicate_query_returns_cached_without_spending_budget():
    session = br.RuleSession(_dev_task())
    first = session.query(3)
    assert session.remaining == br.MAX_QUERIES - 1
    assert session.query(3) == first
    assert session.remaining == br.MAX_QUERIES - 1


def test_invalid_inputs_refused():
    session = br.RuleSession(_dev_task())
    for bad in (-1, 16, 99):
        try:
            session.query(bad)
        except br.RuleRefused as exc:
            assert exc.reason == "illegal-input"
        else:
            raise AssertionError("input %r was admitted" % (bad,))


def test_private_tables_absent_from_every_learner_visible_view():
    task = _dev_task(seed=2)
    session = br.RuleSession(task)
    session.query(0)
    session.query(7)
    for view in (session.public_view(), session.model_input(),
                 session.child_view()):
        blob = json.dumps(view, sort_keys=True)
        for table in task["tables"]:
            assert str(table) not in blob
        assert set(view) <= br.PUBLIC_VIEW_KEYS
    queried_xs = {0, 7}
    for x in range(16):
        if x in queried_xs:
            continue
        y = tuple((task["tables"][b] >> x) & 1 for b in range(4))
        assert {"x": x, "y": list(y)} not in session.public_view()["observed"]


def test_learner_visible_observations_carry_no_sealed_keys():
    session = br.RuleSession(_dev_task(seed=3))
    session.query(1)
    view = session.public_view()
    blob = json.dumps(view, sort_keys=True)
    for token in ("hidden_answer", "sealed_answer", "judgment",
                  "assessment_answer", "use_answers", "tables"):
        assert token not in blob
    assert view["remaining"] == br.MAX_QUERIES - 1


def test_illegal_hypothesis_predictor_refused():
    session = br.RuleSession(_dev_task())
    outsider = next(t for t in range(65536) if t not in br.CLASS_INDEX)
    predictor = {"specs": (br.spec_for_table(
        next(iter(br.CLASS_TABLES))),) * 3 + ({"table": outsider},)}
    try:
        session.commit_predictor(predictor)
    except br.RuleRefused as exc:
        assert exc.reason == "illegal-hypothesis"
    else:
        raise AssertionError("non-member truth table was admitted")
    try:
        session.commit_predictor({"specs": ()})
    except br.RuleRefused as exc:
        assert exc.reason == "illegal-hypothesis"
    else:
        raise AssertionError("empty predictor was admitted")


def test_predictor_executes_on_all_sixteen_inputs():
    session = br.RuleSession(_dev_task(seed=4))
    for x in (0, 9, 15):
        session.query(x)
    learner = rl.VersionSpaceLearner(br.CLASS_TABLES, seed=11)
    for x, y in session.queried.items():
        learner.observe(x, y)
    predictor = learner.predict(session.queried)
    committed = session.commit_predictor(predictor)
    assert len(br.execute_all(committed)) == 16
    for x in range(16):
        y = br.execute_predictor(committed, x)
        assert len(y) == 4 and all(b in (0, 1) for b in y)


def test_version_space_shrinks_and_stays_consistent_with_queries():
    learner = rl.VersionSpaceLearner(br.CLASS_TABLES, seed=5)
    before = learner.version_space_sizes()
    assert before == [len(br.CLASS_TABLES)] * 4
    task = _dev_task(seed=6)
    session = br.RuleSession(task)
    for x in (2, 11):
        session.query(x)
        learner.observe(x, session.queried[x])
    after = learner.version_space_sizes()
    assert all(a < b for a, b in zip(after, before))
    predictor = learner.predict(session.queried)
    committed = session.commit_predictor(predictor)
    for x, y in session.queried.items():
        assert br.execute_predictor(committed, x) == y


def test_baseline_learner_beats_chance_on_unqueried_dev_inputs():
    task = _dev_task(seed=0)
    session = br.RuleSession(task)
    learner = rl.VersionSpaceLearner(br.CLASS_TABLES, seed=0)
    for _ in range(br.MAX_QUERIES):
        x = learner.choose_query(session.queried)
        assert x is not None and x not in session.queried
        learner.observe(x, session.query(x))
    assert learner.choose_query(session.queried) is None
    report = session.score(session.commit_predictor(
        learner.predict(session.queried)))
    assert report["n_queried"] == 8
    assert report["queried"] == 1.0
    assert report["unqueried"] >= 0.75
    assert report["overall"] == (8 * 1.0 + 8 * report["unqueried"]) / 16


def test_private_scoring_reports_queried_unqueried_separately():
    task = _dev_task(seed=1)
    session = br.RuleSession(task)
    learner = rl.VersionSpaceLearner(br.CLASS_TABLES, seed=1)
    for x in (0, 1):
        learner.observe(x, session.query(x))
    predictor = session.commit_predictor(learner.predict(session.queried))
    report = session.score(predictor)
    assert set(report) == {"overall", "queried", "unqueried", "n_queried"}
    assert report["n_queried"] == 2
    assert 0.0 <= report["queried"] <= 1.0
    assert 0.0 <= report["unqueried"] <= 1.0
    assert 0.0 <= report["overall"] <= 1.0


def test_split_generators_are_independent_and_disjoint():
    assert (br.make_task("dev", 0)["tables"] !=
            br.make_task("qual", 0)["tables"])
    assert (br.make_task("dev", 0)["tables"] !=
            br.make_task("audit", 0)["tables"])
    dev = [br.make_task("dev", s) for s in range(8)]
    qual = [br.make_task("qual", s) for s in range(8)]
    audit = [br.make_task("audit", s) for s in range(8)]
    assert br.find_cross_split_duplicates(
        {"dev": dev, "qual": qual, "audit": audit}) == []


def test_same_legal_class_and_budget_for_every_arm():
    specs = [br.instrument_spec(split) for split in
             ("dev", "qual", "audit")]
    assert specs[0] == specs[1] == specs[2]
    spec = br.instrument_spec("dev")
    assert spec["max_queries"] == 8
    assert spec["n_inputs"] == 4 and spec["n_outputs"] == 4
    assert spec["class_digest"] == br.class_digest()


def test_informative_queries_differ_across_targets_and_policies():
    firsts = set()
    for seed in range(4):
        learner = rl.VersionSpaceLearner(br.CLASS_TABLES, seed=seed)
        firsts.add(learner.choose_query({}))
    assert len(firsts) >= 2
    seen = set()
    for task_seed in range(4):
        session = br.RuleSession(_dev_task(seed=task_seed))
        learner = rl.VersionSpaceLearner(br.CLASS_TABLES, seed=0)
        seen.add(learner.choose_query(session.queried))
    assert br.make_task("dev", 0)["task_id"] != br.make_task("dev", 1)[
        "task_id"]


def test_scoring_unknown_predictor_refused():
    session = br.RuleSession(_dev_task())
    try:
        session.score({"specs": (br.spec_for_table(
            next(iter(br.CLASS_TABLES))),) * 4})
    except br.RuleRefused as exc:
        assert exc.reason == "prediction-not-committed"
    else:
        raise AssertionError("uncommitted predictor was scored")
