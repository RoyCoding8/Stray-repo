from __future__ import annotations

import pytest
from psycopg.types.json import Json

from settlement import broker, capabilities, db, evaluation, store, trials
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_local import LocalLauncher

from test_s3_helpers import bind_assignment, seed_env

CAND, REF, EVAL = "cap-A", "cap-R", "v1"
SCOPE = {"family": "off_by_one"}


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _cap_row(dsn, version_id):
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, family, applicability,"
                        " scope) VALUES (%s, %s, %s, %s)"
                        " ON CONFLICT (id) DO NOTHING",
                        (version_id, "off_by_one", Json(SCOPE), Json(SCOPE)))


def _protocol(dsn, tag, cand=CAND):
    trials.freeze_protocol(
        dsn, Command(request_id=f"{tag}-frz"), protocol_id=f"{tag}-p",
        candidate_version=cand, reference_version=REF, evaluator_version=EVAL,
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[],
        uncertainty={})
    return f"{tag}-p"


def _grade(dsn, launcher, env, tag, ok=True, assignment_id=None):
    op = f"{tag}-g"
    broker.ensure_operation(dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process",
                                     "argv": ["true"] if ok else ["false"],
                                     "timeout_ms": 30_000,
                                     "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"])
    if assignment_id is not None:
        bind_assignment(dsn, tag, assignment_id, op)
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher})
    return op


def _receipt(dsn, tag, assignment_id, op, outcome):
    return evaluation.submit_evaluator_receipt(
        dsn, Command(request_id=f"{tag}-{assignment_id}"), receipt_id=f"{tag}-r",
        assignment_id=assignment_id, evaluator_id="s3-eval",
        evaluator_version=EVAL, invocation_ref=op,
        result={"outcome": outcome,
                "detail": {"task_id": assignment_id.rsplit(":", 1)[-1]}})


def _setup(dsn, launcher, env, tag):
    evaluation.register_evaluator(dsn, Command(request_id=f"{tag}-eval"),
                                  "s3-eval", EVAL)
    _cap_row(dsn, CAND)
    _cap_row(dsn, REF)
    _cap_row(dsn, "cap-B")
    pid = _protocol(dsn, tag)
    trials.assign(dsn, Command(request_id=f"{tag}-a1", payload={}), pid,
                  "t1", "panel", "candidate", {})
    trials.assign(dsn, Command(request_id=f"{tag}-a2", payload={}), pid,
                  "t1", "panel", "reference", {})
    return pid


def _gain(dsn, launcher, env, tag):
    pid = _setup(dsn, launcher, env, tag)
    _receipt(dsn, f"{tag}-c", f"{pid}:candidate:t1",
             _grade(dsn, launcher, env, f"{tag}-c",
                    assignment_id=f"{pid}:candidate:t1"), "success")
    _receipt(dsn, f"{tag}-f", f"{pid}:reference:t1",
             _grade(dsn, launcher, env, f"{tag}-f", False,
                    assignment_id=f"{pid}:reference:t1"), "failure")
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    return pid


def _release(dsn, tag, pid, versions, scope=SCOPE, disposition="limited",
             evaluator_version=EVAL):
    return capabilities.scoped_release(
        dsn, Command(request_id=f"{tag}-rel", payload={}), release_id=f"{tag}-rel",
        protocol_id=pid, versions=list(versions), scope=dict(scope),
        disposition=disposition, fallback=REF, policy_version="sel-v1",
        invalidation={}, evidence_refs=[], evaluator_version=evaluator_version)


def test_direct_outcome_rows_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01d"), "r01d"
    pid = _setup(dsn, launcher, env, tag)
    trials.record_result(dsn, Command(request_id=f"{tag}-r1", payload={}),
                         assignment_id=f"{pid}:candidate:t1", outcome="success",
                         invocation_ref=_grade(dsn, launcher, env, f"{tag}-c"))
    trials.record_result(dsn, Command(request_id=f"{tag}-r2", payload={}),
                         assignment_id=f"{pid}:reference:t1", outcome="failure",
                         invocation_ref=_grade(dsn, launcher, env, f"{tag}-f",
                                               False))
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    with pytest.raises(SettlementError, match="empty evaluator-receipt set"):
        _release(dsn, tag, pid, [CAND])
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []


def test_empty_evaluator_set_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01e"), "r01e"
    pid = _setup(dsn, launcher, env, tag)
    with pytest.raises(SettlementError, match="without outcomes"):
        _release(dsn, tag, pid, [CAND])
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []


def test_direct_rows_marked_synthetic(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01m"), "r01m"
    pid = _setup(dsn, launcher, env, tag)
    trials.record_result(dsn, Command(request_id=f"{tag}-r1", payload={}),
                         assignment_id=f"{pid}:candidate:t1", outcome="success")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invocation_ref, detail FROM trial_results"
                        " WHERE assignment_id = %s",
                        (f"{pid}:candidate:t1",))
            ref, detail = cur.fetchone()
            conn.commit()
    assert ref == ""
    assert dict(detail)["origin"] == "direct-caller-outcome"


def test_marked_fixture_insert_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01s"), "r01s"
    pid = _setup(dsn, launcher, env, tag)
    op_ok = _grade(dsn, launcher, env, f"{tag}-c",
                   assignment_id=f"{pid}:candidate:t1")
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO trial_results (assignment_id, outcome,"
                        " invocation_ref, detail) VALUES (%s, %s, %s, %s)",
                        (f"{pid}:candidate:t1", "success", op_ok,
                         Json({"origin": "synthetic-fixture"})))
    _receipt(dsn, f"{tag}-f", f"{pid}:reference:t1",
             _grade(dsn, launcher, env, f"{tag}-f", False,
                    assignment_id=f"{pid}:reference:t1"), "failure")
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    with pytest.raises(SettlementError, match="authenticated evaluator results"):
        _release(dsn, tag, pid, [CAND])


def test_simulated_receipt_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01sim"), "r01sim"
    pid = _gain(dsn, launcher, env, tag)
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE evaluator_receipts SET result = result ||"
                        " '{\"simulated\": true}' WHERE assignment_id = %s",
                        (f"{pid}:candidate:t1",))
    with pytest.raises(SettlementError, match="synthetic fixture"):
        _release(dsn, tag, pid, [CAND])


def test_diverged_receipt_row_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01div"), "r01div"
    pid = _setup(dsn, launcher, env, tag)
    trials.assign(dsn, Command(request_id=f"{tag}-a3", payload={}), pid,
                  "t2", "panel", "candidate", {})
    _receipt(dsn, f"{tag}-c1", f"{pid}:candidate:t1",
             _grade(dsn, launcher, env, f"{tag}-c1",
                    assignment_id=f"{pid}:candidate:t1"), "success")
    _receipt(dsn, f"{tag}-c2", f"{pid}:candidate:t2",
             _grade(dsn, launcher, env, f"{tag}-c2",
                    assignment_id=f"{pid}:candidate:t2"), "success")
    _receipt(dsn, f"{tag}-f", f"{pid}:reference:t1",
             _grade(dsn, launcher, env, f"{tag}-f", False,
                    assignment_id=f"{pid}:reference:t1"), "failure")
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE trial_results SET outcome = 'success'"
                        " WHERE assignment_id = %s",
                        (f"{pid}:reference:t1",))
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    with pytest.raises(SettlementError, match="diverges"):
        _release(dsn, tag, pid, [CAND])


def test_unrelated_observed_operation_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01u"), "r01u"
    pid = _setup(dsn, launcher, env, tag)
    op = f"{tag}-c-g"
    broker.ensure_operation(dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process", "argv": ["true"],
                                     "timeout_ms": 30_000, "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"])
    bind_assignment(dsn, f"{tag}-c", f"{pid}:candidate:t1", op)
    with pytest.raises(SettlementError, match="already backs"):
        bind_assignment(dsn, f"{tag}-f", f"{pid}:reference:t1", op)
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher})
    _receipt(dsn, f"{tag}-c", f"{pid}:candidate:t1", op, "success")
    trials.record_result(dsn, Command(request_id=f"{tag}-r2", payload={}),
                         assignment_id=f"{pid}:reference:t1", outcome="failure")
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    with pytest.raises(SettlementError, match="authenticated evaluator results"):
        _release(dsn, tag, pid, [CAND])


def test_failed_operation_labeled_success_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01f"), "r01f"
    pid = _setup(dsn, launcher, env, tag)
    with pytest.raises(SettlementError, match="never succeeded"):
        _receipt(dsn, f"{tag}-c", f"{pid}:candidate:t1",
                 _grade(dsn, launcher, env, f"{tag}-c", False,
                        assignment_id=f"{pid}:candidate:t1"), "success")
    trials.record_result(dsn, Command(request_id=f"{tag}-r1", payload={}),
                         assignment_id=f"{pid}:candidate:t1", outcome="success")
    trials.record_result(dsn, Command(request_id=f"{tag}-r2", payload={}),
                         assignment_id=f"{pid}:reference:t1", outcome="failure")
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    with pytest.raises(SettlementError, match="empty evaluator-receipt set"):
        _release(dsn, tag, pid, [CAND])


def test_mismatched_evaluator_version_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01v"), "r01v"
    pid = _gain(dsn, launcher, env, tag)
    with pytest.raises(SettlementError, match="pin mismatch"):
        _release(dsn, tag, pid, [CAND], evaluator_version="v9")


def test_unrelated_version_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01b"), "r01b"
    pid = _gain(dsn, launcher, env, tag)
    with pytest.raises(SettlementError, match="pin mismatch"):
        _release(dsn, tag, pid, ["cap-B"])
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []


def test_mixed_version_set_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01ab"), "r01ab"
    pid = _gain(dsn, launcher, env, tag)
    with pytest.raises(SettlementError, match="pin mismatch"):
        _release(dsn, tag, pid, [CAND, "cap-B"])
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []


def test_widened_scope_refused(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01w"), "r01w"
    pid = _gain(dsn, launcher, env, tag)
    with pytest.raises(SettlementError, match="broadening release refused"):
        _release(dsn, tag, pid, [CAND], scope={"family": "other"})
    with pytest.raises(SettlementError, match="broadening release refused"):
        _release(dsn, tag, pid, [CAND], scope={})
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []


def test_incumbent_preserved_after_refusals(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01i"), "r01i"
    pid = _gain(dsn, launcher, env, tag)
    capabilities.save_router_policy(
        dsn, Command(request_id=f"{tag}-pol", payload={}), version="rp-inc",
        mapping={"off_by_one": REF})
    for bad_versions, bad_scope in ((["cap-B"], SCOPE), ([CAND], {"family": "x"})):
        with pytest.raises(SettlementError):
            _release(dsn, f"{tag}-{bad_versions[0]}", pid, bad_versions,
                      scope=bad_scope)
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []
    assert capabilities.route(dsn, "rp-inc", "off_by_one")["version_id"] == REF


def test_exact_bound_release_applies(migrated_db, launcher):
    dsn, env, tag = migrated_db, seed_env(migrated_db, "r01g"), "r01g"
    pid = _gain(dsn, launcher, env, tag)
    result = _release(dsn, tag, pid, [CAND])
    assert result.code == ResultCode.APPLIED
    assert [r["id"] for r in capabilities.releases_for_scope(
        dsn, "off_by_one")] == [f"{tag}-rel"]
