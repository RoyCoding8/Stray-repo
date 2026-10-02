from __future__ import annotations

import pytest

from settlement import broker, store, trials
from settlement.common import Command, SettlementError
from settlement.launcher_local import LocalLauncher

from test_s3_helpers import acquire, seed_env

GROUPS = [{"name": "development", "kind": "development"},
          {"name": "visible", "kind": "visible-regression"},
          {"name": "panel", "kind": "protected-eval"}]


def _freeze(dsn, tag, pid="p"):
    return trials.freeze_protocol(
        dsn, Command(request_id=f"{tag}-{pid}-frz"), protocol_id=f"{tag}-{pid}",
        candidate_version="cand", reference_version="ref", evaluator_version="v1",
        task_groups=GROUPS, budgets={"amortization_horizon": {"tasks": 20}},
        metrics=["success_rate"], stopping={}, exclusions=[], uncertainty={})


def _op(dsn, launcher, env, tag):
    broker.ensure_operation(dsn, operation_id=tag, effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process", "argv": ["true"],
                                     "timeout_ms": 30_000, "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"])
    broker.dispatch_operation(dsn, tag, launchers={"local-process": launcher})
    return tag


def test_frozen_protocol_immutable(migrated_db):
    from settlement import db

    dsn = migrated_db
    _freeze(dsn, "s3fr")
    with pytest.raises(Exception, match="frozen"):
        with db.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE trial_protocols SET candidate_version = 'x'"
                            " WHERE id = 's3fr-p'")
    trials.amend_protocol(dsn, Command(request_id="s3fr-amd", payload={}),
                          protocol_id="s3fr-p2", supersedes="s3fr-p",
                          candidate_version="cand2")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT candidate_version, supersedes FROM trial_protocols"
                        " WHERE id IN ('s3fr-p', 's3fr-p2') ORDER BY id")
            rows = cur.fetchall()
            conn.commit()
    assert rows[0] == ("cand", "")
    assert rows[1] == ("cand2", "s3fr-p")


def test_outcome_rules_and_verdict_gate(migrated_db, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "s3oc")
    launcher = LocalLauncher(tmp_path / "runs")
    _freeze(dsn, "s3oc")
    op = _op(dsn, launcher, env, "s3oc-op")
    trials.assign(dsn, Command(request_id="s3oc-a1", payload={}), "s3oc-p",
                  "t1", "panel", "candidate", {})
    with pytest.raises(SettlementError):
        trials.record_result(dsn, Command(request_id="s3oc-bad", payload={}),
                             assignment_id="s3oc-p:candidate:t1", outcome="success",
                             invocation_ref="no-such-op")
    with pytest.raises(SettlementError):
        trials.record_result(dsn, Command(request_id="s3oc-bad2", payload={}),
                             assignment_id="s3oc-p:candidate:t1", outcome="maybe")
    trials.assign(dsn, Command(request_id="s3oc-a2", payload={}), "s3oc-p",
                  "t1", "panel", "reference", {})
    with pytest.raises(SettlementError, match="without outcomes"):
        trials.verdict(dsn, "s3oc-p")
    trials.record_result(dsn, Command(request_id="s3oc-r1", payload={}),
                         assignment_id="s3oc-p:candidate:t1", outcome="timeout",
                         invocation_ref=op, cost={"sandbox": 36})
    trials.record_result(dsn, Command(request_id="s3oc-r2", payload={}),
                         assignment_id="s3oc-p:reference:t1", outcome="invalid",
                         invocation_ref=op)
    assert trials.verdict(dsn, "s3oc-p")["label"] == "inconclusive"


def test_verdict_labels(migrated_db):
    dsn = migrated_db

    def build(tag, cand_wins, ref_wins):
        _freeze(dsn, tag)
        for idx in range(cand_wins):
            trials.assign(dsn, Command(request_id=f"{tag}-c{idx}", payload={}),
                          f"{tag}-p", f"c{idx}", "panel", "candidate", {})
            trials.record_result(
                dsn, Command(request_id=f"{tag}-cr{idx}", payload={}),
                assignment_id=f"{tag}-p:candidate:c{idx}", outcome="success")
        for idx in range(ref_wins):
            trials.assign(dsn, Command(request_id=f"{tag}-f{idx}", payload={}),
                          f"{tag}-p", f"f{idx}", "panel", "reference", {})
            trials.record_result(
                dsn, Command(request_id=f"{tag}-fr{idx}", payload={}),
                assignment_id=f"{tag}-p:reference:f{idx}", outcome="success")
        return trials.verdict(dsn, f"{tag}-p")

    assert build("s3vg", 2, 1)["label"] == "observed-gain"
    assert build("s3vr", 1, 2)["label"] == "regression"
    assert build("s3vi", 1, 1)["label"] == "inconclusive"


def test_matched_expenditure_adds_up(migrated_db, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "s3ex")
    launcher = LocalLauncher(tmp_path / "runs")
    _freeze(dsn, "s3ex")
    charges = [("construction", 100, "build"), ("retrieval", 20, "lookup"),
               ("evaluation", 36, "grade"), ("failed_trials", 36, "failed run"),
               ("use", 10, "serving")]
    for category, amount, note in charges:
        _op(dsn, launcher, env, f"s3ex-{category}")
        trials.record_expenditure(dsn, "s3ex-p", category, amount, note,
                                  operation_id=f"s3ex-{category}")
    totals = trials.development_expenditure(dsn, "s3ex-p")
    assert totals["by_category"] == {**{category: amount
                                        for category, amount, _ in charges},
                                     "coordination": 0, "selection": 0}
    assert totals["development_total"] == 100 + 20 + 36 + 36
    assert totals["use_total"] == 10
    assert totals["grand_total"] == totals["development_total"] + 10
    assert totals["amortization_horizon"] == {"tasks": 20}
    with pytest.raises(SettlementError):
        trials.record_expenditure(dsn, "s3ex-p", "guessing", 5,
                                  operation_id="s3ex-construction")


def test_learn6_inferential_path_refuses(migrated_db):
    from settlement import db

    dsn = migrated_db
    _freeze(dsn, "s3l6")
    with pytest.raises(trials.UnverifiedProcedure, match="no validated LEARN-6"):
        trials.inferential_claim(dsn, "s3l6-p", "wilson-interval")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM inferential_gates WHERE protocol_id = %s",
                        ("s3l6-p",))
            assert cur.fetchone()[0] == "unverified"
            conn.commit()


def test_opportunity_allocated_to_distinguishing_investigation(migrated_db):
    from settlement import db

    dsn = migrated_db
    trials.register_opportunity(
        dsn, Command(request_id="s3op-reg", payload={}), opportunity_id="opp-1",
        question="does the fixer transfer?",
        hypothesis="bound rewrites fail on operators",
        basis="panel gain without transfer gain", desired_observation="transfer panel",
        cap={"units": 200})
    result = trials.allocate_opportunity(dsn, Command(request_id="s3op-all",
                                                      payload={}),
                                         "opp-1", "s3op-inv",
                                         objective="transfer probe")
    assert result.data["investigation_id"] == "s3op-inv"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, investigation_id FROM development_opportunities"
                        " WHERE id = 'opp-1'")
            assert cur.fetchone() == ("allocated", "s3op-inv")
            cur.execute("SELECT objective FROM investigations WHERE id = 's3op-inv'")
            assert cur.fetchone()[0] == "transfer probe"
            conn.commit()
    with pytest.raises(SettlementError):
        trials.allocate_opportunity(dsn, Command(request_id="s3op-all2",
                                                 payload={}),
                                    "opp-1", "s3op-inv2")


def _ledger(dsn, protocol_id):
    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT category, amount FROM expenditure_ledger"
                        " WHERE protocol_id = %s ORDER BY id", (protocol_id,))
            rows = cur.fetchall()
            conn.commit()
    return [tuple(row) for row in rows]


def test_replaying_one_charge_does_not_double_apply(migrated_db, tmp_path):
    """The same operation, charged twice, must land in the ledger once.

    This is the property every other property in this file depends on. If a
    retry can insert a second row, then the sum in
    ``test_matched_expenditure_adds_up`` is not a measurement of anything and a
    widened digest is a licence to charge twice.
    """
    dsn = migrated_db
    env = seed_env(dsn, "s3rp")
    launcher = LocalLauncher(tmp_path / "runs")
    _freeze(dsn, "s3rp")
    _op(dsn, launcher, env, "s3rp-op")

    first = trials.record_expenditure(dsn, "s3rp-p", "construction", 41, "build",
                                      operation_id="s3rp-op")
    second = trials.record_expenditure(dsn, "s3rp-p", "construction", 41, "build",
                                       operation_id="s3rp-op")
    third = trials.record_expenditure(dsn, "s3rp-p", "construction", 41, "build",
                                      operation_id="s3rp-op")

    assert first == second == third
    assert _ledger(dsn, "s3rp-p") == [("construction", 41)]


def test_a_corrected_charge_is_booked_beside_the_first(migrated_db, tmp_path):
    """A re-measured charge is a second row, not a refusal and not a mutation.

    The amount in a charge is measured from an operation's receipts, and a
    run killed mid-flight leaves that measurement provisional. When the real
    figure is known later, booking it must not raise, and must not rewrite
    the row that was wrong.
    """
    dsn = migrated_db
    env = seed_env(dsn, "s3rq")
    launcher = LocalLauncher(tmp_path / "runs")
    _freeze(dsn, "s3rq")
    _op(dsn, launcher, env, "s3rq-op")

    first = trials.record_expenditure(dsn, "s3rq-p", "construction", 12, "build",
                                      operation_id="s3rq-op")
    corrected = trials.record_expenditure(dsn, "s3rq-p", "construction", 99, "rebuild",
                                          operation_id="s3rq-op")

    assert first["amount"] == 12
    assert corrected["amount"] == 99
    assert _ledger(dsn, "s3rq-p") == [("construction", 12), ("construction", 99)]


def test_recording_the_corrected_charge_twice_still_books_it_once(migrated_db, tmp_path):
    """Widening the identity must not make a correction chargeable twice."""
    dsn = migrated_db
    env = seed_env(dsn, "s3rc")
    launcher = LocalLauncher(tmp_path / "runs")
    _freeze(dsn, "s3rc")
    _op(dsn, launcher, env, "s3rc-op")

    trials.record_expenditure(dsn, "s3rc-p", "construction", 12, "build",
                              operation_id="s3rc-op")
    trials.record_expenditure(dsn, "s3rc-p", "construction", 99, "rebuild",
                              operation_id="s3rc-op")
    trials.record_expenditure(dsn, "s3rc-p", "construction", 99, "rebuild",
                              operation_id="s3rc-op")

    assert _ledger(dsn, "s3rc-p") == [("construction", 12), ("construction", 99)]


def test_one_operation_may_be_charged_in_two_categories(migrated_db, tmp_path):
    """A mis-categorised charge is correctable without touching the original."""
    dsn = migrated_db
    env = seed_env(dsn, "s3rx")
    launcher = LocalLauncher(tmp_path / "runs")
    _freeze(dsn, "s3rx")
    _op(dsn, launcher, env, "s3rx-op")

    trials.record_expenditure(dsn, "s3rx-p", "construction", 30, "build",
                              operation_id="s3rx-op")
    trials.record_expenditure(dsn, "s3rx-p", "evaluation", 30, "graded",
                              operation_id="s3rx-op")

    assert _ledger(dsn, "s3rx-p") == [("construction", 30), ("evaluation", 30)]
    totals = trials.development_expenditure(dsn, "s3rx-p")
    assert totals["by_category"]["construction"] == 30
    assert totals["by_category"]["evaluation"] == 30


def test_the_ledger_has_no_way_to_retract_a_charge(migrated_db, tmp_path):
    """Pin the property the docstring leans on: corrections accumulate.

    Every reader of this table is a plain ``SUM(amount) GROUP BY category``,
    and ``amount`` is ``CHECK (amount >= 0)``, so a correction is counted in
    full next to the charge it corrects. That is a fact about the schema
    rather than a choice made here, and a test that noticed it later would
    be the only way to find out it had changed.
    """
    dsn = migrated_db
    env = seed_env(dsn, "s3ry")
    launcher = LocalLauncher(tmp_path / "runs")
    _freeze(dsn, "s3ry")
    _op(dsn, launcher, env, "s3ry-op")

    trials.record_expenditure(dsn, "s3ry-p", "construction", 12, "build",
                              operation_id="s3ry-op")
    trials.record_expenditure(dsn, "s3ry-p", "construction", 99, "rebuild",
                              operation_id="s3ry-op")

    assert trials.development_expenditure(dsn, "s3ry-p")["development_total"] == 111
    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(amount) FROM expenditure_ledger"
                        " WHERE protocol_id = 's3ry-p'")
            assert cur.fetchone()[0] == 12
            conn.commit()


def test_blinded_assignments_hide_arm(migrated_db):
    dsn = migrated_db
    _freeze(dsn, "s3bl")
    result = trials.assign(dsn, Command(request_id="s3bl-a", payload={}), "s3bl-p",
                           "t9", "panel", "candidate", {"entry_fn": "f"})
    blind = trials.blinded_assignment(dsn, result.data["blind_key"])
    assert blind["task_id"] == "t9"
    assert "arm" not in blind and "candidate" not in blind.values()
    assert trials.resolve_blind(dsn, result.data["blind_key"])["arm"] == "candidate"
