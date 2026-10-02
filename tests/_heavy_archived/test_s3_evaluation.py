from __future__ import annotations

import pytest

from settlement import broker, evaluation, store, trials
from settlement.common import Command, SettlementError, Unauthorized
from settlement.launcher_local import LocalLauncher

from test_s3_helpers import acquire, bind_assignment, seed_env


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _protocol(dsn, tag, evaluator="v1"):
    trials.freeze_protocol(
        dsn, Command(request_id=f"{tag}-frz"), protocol_id=f"{tag}-p",
        candidate_version="cand", reference_version="ref",
        evaluator_version=evaluator,
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[],
        uncertainty={})
    return f"{tag}-p"


def _grade_op(dsn, launcher, env, tag, argv=None, assignment_id=None):
    op = f"{tag}-grade"
    broker.ensure_operation(dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process",
                                     "argv": argv or ["true"],
                                     "timeout_ms": 30_000,
                                     "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"])
    if assignment_id is not None:
        bind_assignment(dsn, tag, assignment_id, op)
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher})
    return op


def test_hidden_answers_scoped(migrated_db):
    dsn = migrated_db
    evaluation.propose_hidden_answer(dsn, Command(request_id="s3h-ans", payload={}),
                                     "task-1", {"cases": [{"fn": "f"}]})
    visible = [c["id"] for c in evaluation.candidate_view(dsn)]
    assert "s3-answer:task-1" not in visible
    with pytest.raises(Unauthorized):
        evaluation.hidden_answer(dsn, "task-1", "candidate")
    assert evaluation.hidden_answer(dsn, "task-1", "evaluator")["cases"] == \
        [{"fn": "f"}]


def test_hidden_answers_excluded_from_candidate_retrieval(migrated_db):
    from settlement import context

    dsn = migrated_db
    evaluation.propose_hidden_answer(dsn, Command(request_id="s3lr-ans",
                                                  payload={}),
                                     "task-9", {"cases": [{"fn": "g"}]})
    view = context.build_context(
        dsn, Command(request_id="s3lr-ctx", payload={}),
        {"task": "task-9"}, [{"claim_id": "s3-answer:task-9"}],
        caller_scope="candidate")
    assert view.data["staged"] is True
    assert view.data["withheld"] == ["s3-answer:task-9"]
    assert view.data["sources"] == []
    honest = context.build_context(
        dsn, Command(request_id="s3lr-ctx2", payload={}),
        {"task": "task-9"}, [{"claim_id": "s3-answer:task-9"}],
        caller_scope="evaluator")
    assert honest.data["withheld"] == []


def test_candidate_cannot_write_receipt(migrated_db, launcher):
    from settlement import db

    dsn = migrated_db
    env = seed_env(dsn, "s3cw")
    pid = _protocol(dsn, "s3cw")
    trials.assign(dsn, Command(request_id="s3cw-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    evaluation.submit_candidate(dsn, Command(request_id="s3cw-sub", payload={}),
                                f"{pid}:candidate:t1", {"code": "broken"})
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM candidate_submissions")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT COUNT(*) FROM evaluator_receipts")
            assert cur.fetchone()[0] == 0
            conn.commit()
    with pytest.raises(SettlementError):
        evaluation.submit_evaluator_receipt(
            dsn, Command(request_id="s3cw-r", payload={}), receipt_id="s3cw-r",
            assignment_id=f"{pid}:candidate:t1", evaluator_id="ghost",
            evaluator_version="v1", invocation_ref="no-op",
            result={"outcome": "success"})
    evaluation.register_evaluator(dsn, Command(request_id="s3cw-e", payload={}),
                                  "s3-eval", "v1")
    op = _grade_op(dsn, launcher, env, "s3cw",
                   assignment_id=f"{pid}:candidate:t1")
    with pytest.raises(SettlementError, match="evaluator replacement refused"):
        evaluation.submit_evaluator_receipt(
            dsn, Command(request_id="s3cw-r2", payload={}), receipt_id="s3cw-r2",
            assignment_id=f"{pid}:candidate:t1", evaluator_id="s3-eval",
            evaluator_version="v9", invocation_ref=op,
            result={"outcome": "success"})


def test_always_pass_swap_detected_and_release_refused(migrated_db, launcher):
    from settlement import capabilities, db

    dsn = migrated_db
    env = seed_env(dsn, "s3ap")
    acquire(dsn, "s3ap", "s3ap-att", env)
    pid = _protocol(dsn, "s3ap")
    evaluation.register_evaluator(dsn, Command(request_id="s3ap-e1", payload={}),
                                  "s3-eval", "v1")
    trials.assign(dsn, Command(request_id="s3ap-a1", payload={}), pid,
                  "t1", "panel", "candidate", {})
    trials.assign(dsn, Command(request_id="s3ap-a2", payload={}), pid,
                  "t1", "panel", "reference", {})
    good = _grade_op(dsn, launcher, env, "s3ap-good",
                     assignment_id=f"{pid}:candidate:t1")
    bad = _grade_op(dsn, launcher, env, "s3ap-bad", ["false"],
                    assignment_id=f"{pid}:reference:t1")
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id="s3ap-r1", payload={}), receipt_id="s3ap-r1",
        assignment_id=f"{pid}:candidate:t1", evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref=good,
        result={"outcome": "success", "detail": {"task_id": "t1"}})
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id="s3ap-r2", payload={}), receipt_id="s3ap-r2",
        assignment_id=f"{pid}:reference:t1", evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref=bad,
        result={"outcome": "failure", "detail": {"task_id": "t1"}})
    evaluation.register_evaluator(dsn, Command(request_id="s3ap-e2", payload={}),
                                  "always-pass", "v2")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, artifact_digest)"
                        " VALUES ('cap-ap', '')")
            conn.commit()
    with pytest.raises(SettlementError, match="pin mismatch"):
        capabilities.scoped_release(
            dsn, Command(request_id="s3ap-rel", payload={}), release_id="rel-ap",
            protocol_id=pid, versions=["cap-ap"], scope={"family": "off_by_one"},
            disposition="limited", fallback="cap-v0", policy_version="sel-v1",
            invalidation={}, evidence_refs=[], evaluator_version="v2")
