from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from psycopg.types.json import Json
from test_s3_helpers import seed_env

from settlement import broker, capabilities, db, evaluation, trials
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_local import LocalLauncher

ROOT = Path(__file__).resolve().parents[2]
GRADER = str(ROOT / "experiments" / "run_tests.py")
GROUPS = [{"name": "development", "kind": "development"},
          {"name": "panel", "kind": "protected-eval"}]
CASES = [{"fn": "add", "args": [1, 2], "expected": 3},
         {"fn": "add", "args": [2, 3], "expected": 5}]
PASS_CODE = "def add(a, b):\n    return a + b\n"
FAIL_CODE = "def add(a, b):\n    return a - b\n"


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _freeze(dsn, tag, evaluator="v1", supported_scope=None):
    trials.freeze_protocol(
        dsn, Command(request_id=f"{tag}-frz"), protocol_id=f"{tag}-p",
        candidate_version=f"{tag}-cand", reference_version=f"{tag}-ref",
        evaluator_version=evaluator, task_groups=GROUPS,
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[],
        uncertainty={}, supported_scope=supported_scope or {})
    return f"{tag}-p"


def _cap_row(dsn, version_id, applicability):
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, family, applicability,"
                        " scope) VALUES (%s, %s, %s, %s)"
                        " ON CONFLICT (id) DO NOTHING",
                        (version_id, "software-repair", Json(applicability),
                         Json(applicability)))


def _submit(dsn, tag, assignment_id, code):
    return evaluation.submit_candidate(
        dsn, Command(request_id=f"{tag}-sub", payload={}),
        assignment_id, {"code": code})


def _ensure(dsn, env, op, argv=None, effect=None, payload=None):
    broker.ensure_operation(
        dsn, operation_id=op,
        effect=effect or broker.SANDBOX_EXEC,
        payload=payload if payload is not None else {
            "profile": "local-process", "argv": argv or ["true"],
            "timeout_ms": 30_000, "max_output_bytes": 1024},
        allocation_id=env["allocation_id"])
    return op


def _dispatch(dsn, launcher, op):
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher})
    return op


def _bind(dsn, tag, assignment_id, digest, op, evaluator="v1", eid=None):
    return evaluation.bind_evaluation(
        dsn, Command(request_id=f"{tag}-bind", payload={}),
        assignment_id, candidate_digest=digest,
        evaluator_id=eid or "s3-eval", evaluator_version=evaluator,
        invocation_ref=op)


def _receipt(dsn, tag, assignment_id, op, outcome, task_id="t1",
             evaluator="v1", eid=None):
    return evaluation.submit_evaluator_receipt(
        dsn, Command(request_id=f"{tag}-rc", payload={}),
        receipt_id=f"{tag}-r", assignment_id=assignment_id,
        evaluator_id=eid or "s3-eval", evaluator_version=evaluator,
        invocation_ref=op,
        result={"outcome": outcome, "detail": {"task_id": task_id}})


def _bound_pair(dsn, launcher, env, tag, cand_ok=True, ref_ok=False,
                scope=None, trial_scope=None):
    evaluation.register_evaluator(dsn, Command(request_id=f"{tag}-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, tag, supported_scope=trial_scope)
    declared = {"family": "software-repair"} if scope is None else scope
    _cap_row(dsn, f"{tag}-cand", declared)
    _cap_row(dsn, f"{tag}-ref", declared)
    aids = {}
    for arm, ok, code in (("candidate", cand_ok, PASS_CODE),
                          ("reference", ref_ok, FAIL_CODE)):
        aid = f"{pid}:{arm}:t1"
        trials.assign(dsn, Command(request_id=f"{tag}-a-{arm}", payload={}),
                      pid, "t1", "panel", arm, {})
        digest = _submit(dsn, f"{tag}-{arm}", aid, code).data["content_digest"]
        op = _ensure(dsn, env, f"{tag}-{arm}-op",
                     ["true"] if ok else ["false"])
        _bind(dsn, f"{tag}-{arm}", aid, digest, op)
        _dispatch(dsn, launcher, op)
        _receipt(dsn, f"{tag}-{arm}", aid, op,
                 "success" if ok else "failure")
        aids[arm] = aid
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    return pid, aids


def test_bound_invocation_accepted_and_released(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02b")
    pid, _ = _bound_pair(dsn, launcher, env, "r02b")
    out = capabilities.scoped_release(
        dsn, Command(request_id="r02b-rel", payload={}), release_id="r02b-rel",
        protocol_id=pid, versions=["r02b-cand"],
        scope={"family": "software-repair"}, disposition="limited",
        fallback="r02b-ref", policy_version="sel-v1", invalidation={},
        evidence_refs=[], evaluator_version="v1")
    assert out.code == ResultCode.APPLIED


def test_fresh_unrelated_success_refused_without_binding(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02u")
    evaluation.register_evaluator(dsn, Command(request_id="r02u-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, "r02u")
    trials.assign(dsn, Command(request_id="r02u-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    _submit(dsn, "r02u", f"{pid}:candidate:t1", PASS_CODE)
    op = _dispatch(dsn, launcher, _ensure(dsn, env, "r02u-op"))
    with pytest.raises(SettlementError, match="no immutable evaluation binding"):
        _receipt(dsn, "r02u", f"{pid}:candidate:t1", op, "success")


def test_wrong_invocation_refused_for_bound_assignment(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02w")
    _, aids = _bound_pair(dsn, launcher, env, "r02w")
    other = _dispatch(dsn, launcher, _ensure(dsn, env, "r02w-other"))
    with pytest.raises(SettlementError, match="not the bound evaluation invocation"):
        _receipt(dsn, "r02w-x", aids["candidate"], other, "success")


def test_grader_success_with_failed_cases_refused(migrated_db, launcher,
                                                  tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "r02g")
    evaluation.register_evaluator(dsn, Command(request_id="r02g-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, "r02g")
    aid = f"{pid}:candidate:t1"
    trials.assign(dsn, Command(request_id="r02g-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    digest = _submit(dsn, "r02g", aid, FAIL_CODE).data["content_digest"]
    cand = tmp_path / "cand.py"
    cases = tmp_path / "cases.json"
    cand.write_text(FAIL_CODE)
    cases.write_text(json.dumps(CASES))
    op = _ensure(dsn, env, "r02g-op",
                 [sys.executable, GRADER, str(cand), str(cases)])
    _bind(dsn, "r02g", aid, digest, op)
    _dispatch(dsn, launcher, op)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT outcome FROM receipts WHERE operation_id = %s",
                        (op,))
            assert cur.fetchone()[0] == "success"
            conn.commit()
    with pytest.raises(SettlementError, match="grader reported 2 failed"):
        _receipt(dsn, "r02g", aid, op, "success")
    assert _receipt(dsn, "r02g-f", aid, op, "failure").code == ResultCode.APPLIED


def test_real_grader_clean_pass_accepted(migrated_db, launcher, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "r02p")
    evaluation.register_evaluator(dsn, Command(request_id="r02p-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, "r02p")
    aid = f"{pid}:candidate:t1"
    trials.assign(dsn, Command(request_id="r02p-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    digest = _submit(dsn, "r02p", aid, PASS_CODE).data["content_digest"]
    cand = tmp_path / "cand.py"
    cases = tmp_path / "cases.json"
    cand.write_text(PASS_CODE)
    cases.write_text(json.dumps(CASES))
    op = _ensure(dsn, env, "r02p-op",
                 [sys.executable, GRADER, str(cand), str(cases)])
    _bind(dsn, "r02p", aid, digest, op)
    _dispatch(dsn, launcher, op)
    assert _receipt(dsn, "r02p", aid, op, "success").code == ResultCode.APPLIED
    with pytest.raises(SettlementError, match="diverges from the authenticated"):
        evaluation.submit_evaluator_receipt(
            dsn, Command(request_id="r02p-rc2", payload={}),
            receipt_id="r02p-r2", assignment_id=aid, evaluator_id="s3-eval",
            evaluator_version="v1", invocation_ref=op,
            result={"outcome": "failure", "detail": {"task_id": "t1"}})


def test_candidate_bytes_mismatch_refused(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02m")
    evaluation.register_evaluator(dsn, Command(request_id="r02m-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, "r02m")
    aid = f"{pid}:candidate:t1"
    trials.assign(dsn, Command(request_id="r02m-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    digest = _submit(dsn, "r02m", aid, PASS_CODE).data["content_digest"]
    op = _ensure(dsn, env, "r02m-op")
    _bind(dsn, "r02m", aid, digest, op)
    with pytest.raises(SettlementError, match="do not match the bound digest"):
        _submit(dsn, "r02m-2", aid, FAIL_CODE)
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO candidate_submissions (assignment_id, content)"
                        " VALUES (%s, %s)", (aid, Json({"code": FAIL_CODE})))
    _dispatch(dsn, launcher, op)
    with pytest.raises(SettlementError, match="does not match.*bound digest"):
        _receipt(dsn, "r02m", aid, op, "success")


def test_evaluator_replacement_refused(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02e")
    evaluation.register_evaluator(dsn, Command(request_id="r02e-e1"),
                                  "s3-eval", "v1")
    evaluation.register_evaluator(dsn, Command(request_id="r02e-e2"),
                                  "swap-eval", "v1")
    pid = _freeze(dsn, "r02e")
    aid = f"{pid}:candidate:t1"
    trials.assign(dsn, Command(request_id="r02e-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    digest = _submit(dsn, "r02e", aid, PASS_CODE).data["content_digest"]
    op = _ensure(dsn, env, "r02e-op")
    _bind(dsn, "r02e", aid, digest, op)
    _dispatch(dsn, launcher, op)
    with pytest.raises(SettlementError, match="evaluator replacement"):
        _receipt(dsn, "r02e", aid, op, "success", eid="swap-eval")
    with pytest.raises(SettlementError, match="rebinding refused"):
        _bind(dsn, "r02e-2", aid, digest, op, eid="swap-eval")


def test_task_identity_mismatch_refused(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02t")
    _, aids = _bound_pair(dsn, launcher, env, "r02t")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT evaluation_op FROM trial_assignments WHERE id = %s",
                        (aids["candidate"],))
            op = cur.fetchone()[0]
            conn.commit()
    with pytest.raises(SettlementError, match="task identity mismatch"):
        _receipt(dsn, "r02t-x", aids["candidate"], op, "success",
                 task_id="other-task")


def test_binding_rules(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02n")
    evaluation.register_evaluator(dsn, Command(request_id="r02n-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, "r02n")
    aid = f"{pid}:candidate:t1"
    trials.assign(dsn, Command(request_id="r02n-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    digest = _submit(dsn, "r02n", aid, PASS_CODE).data["content_digest"]
    with pytest.raises(SettlementError, match="no actual invocation"):
        evaluation.bind_evaluation(
            dsn, Command(request_id="r02n-bad", payload={}), aid,
            candidate_digest=digest, evaluator_id="s3-eval",
            evaluator_version="v1", invocation_ref="r02n-ghost")
    launched = _dispatch(dsn, launcher, _ensure(dsn, env, "r02n-op"))
    with pytest.raises(SettlementError, match="must precede launch"):
        evaluation.bind_evaluation(
            dsn, Command(request_id="r02n-late", payload={}), aid,
            candidate_digest=digest, evaluator_id="s3-eval",
            evaluator_version="v1", invocation_ref=launched)
    obs = _ensure(dsn, env, "r02n-obs", effect=broker.OBSERVATION_ADAPTER,
                  payload={"adapter": "clock", "input": {}})
    with pytest.raises(SettlementError, match="not a grader execution"):
        evaluation.bind_evaluation(
            dsn, Command(request_id="r02n-fx", payload={}), aid,
            candidate_digest=digest, evaluator_id="s3-eval",
            evaluator_version="v1", invocation_ref=obs)
    op = _ensure(dsn, env, "r02n-op2")
    assert _bind(dsn, "r02n", aid, digest, op).code == ResultCode.APPLIED
    again = evaluation.bind_evaluation(
        dsn, Command(request_id="r02n-again", payload={}), aid,
        candidate_digest=digest, evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref=op)
    assert again.code == ResultCode.ALREADY_APPLIED


def test_tampered_rows_refused_at_release(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02x")
    pid, aids = _bound_pair(dsn, launcher, env, "r02x")
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE evaluator_receipts SET result = result ||"
                        " '{\"outcome\": \"failure\"}'"
                        " WHERE assignment_id = %s", (aids["candidate"],))
    with pytest.raises(SettlementError, match="diverges from its evaluator receipt"):
        capabilities.scoped_release(
            dsn, Command(request_id="r02x-rel", payload={}),
            release_id="r02x-rel", protocol_id=pid, versions=["r02x-cand"],
            scope={"family": "software-repair"}, disposition="limited",
            fallback="r02x-ref", policy_version="sel-v1", invalidation={},
            evidence_refs=[], evaluator_version="v1")


def test_tampered_invocation_refused_at_release(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02y")
    pid, aids = _bound_pair(dsn, launcher, env, "r02y")
    stray = _dispatch(dsn, launcher, _ensure(dsn, env, "r02y-stray"))
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE evaluator_receipts SET invocation_ref = %s"
                        " WHERE assignment_id = %s", (stray, aids["candidate"]))
            cur.execute("UPDATE trial_results SET invocation_ref = %s"
                        " WHERE assignment_id = %s", (stray, aids["candidate"]))
    with pytest.raises(SettlementError, match="not bound to its evaluation invocation"):
        capabilities.scoped_release(
            dsn, Command(request_id="r02y-rel", payload={}),
            release_id="r02y-rel", protocol_id=pid, versions=["r02y-cand"],
            scope={"family": "software-repair"}, disposition="limited",
            fallback="r02y-ref", policy_version="sel-v1", invalidation={},
            evidence_refs=[], evaluator_version="v1")


def test_failure_claim_for_bare_success_refused(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02f")
    evaluation.register_evaluator(dsn, Command(request_id="r02f-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, "r02f")
    aid = f"{pid}:candidate:t1"
    trials.assign(dsn, Command(request_id="r02f-a", payload={}), pid,
                  "t1", "panel", "candidate", {})
    digest = _submit(dsn, "r02f", aid, PASS_CODE).data["content_digest"]
    op = _ensure(dsn, env, "r02f-op")
    _bind(dsn, "r02f", aid, digest, op)
    _dispatch(dsn, launcher, op)
    with pytest.raises(SettlementError, match="only success may be claimed"):
        _receipt(dsn, "r02f", aid, op, "failure")


def test_release_scope_drop_refused():
    with pytest.raises(SettlementError, match="drops supported constraint 'language'"):
        capabilities._check_supported_scope(
            {"v1": {"applicability": {"family": "software-repair",
                                      "language": "python"}}},
            {"family": "software-repair"}, "limited")


def test_release_scope_change_refused():
    with pytest.raises(SettlementError,
                       match="changes supported constraint 'language'"):
        capabilities._check_supported_scope(
            {"v1": {"applicability": {"family": "software-repair",
                                      "language": "python"}}},
            {"family": "software-repair", "language": "go"}, "limited")


def test_legitimate_narrowing_released(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02s")
    scope = {"family": "software-repair", "language": "python"}
    pid, _ = _bound_pair(dsn, launcher, env, "r02s", scope=scope)
    out = capabilities.scoped_release(
        dsn, Command(request_id="r02s-rel", payload={}), release_id="r02s-rel",
        protocol_id=pid, versions=["r02s-cand"],
        scope={"family": "software-repair", "language": "python",
               "channel": "stable"},
        disposition="limited", fallback="r02s-ref", policy_version="sel-v1",
        invalidation={}, evidence_refs=[], evaluator_version="v1")
    assert out.code == ResultCode.APPLIED
    with pytest.raises(SettlementError, match="drops supported constraint 'language'"):
        capabilities.scoped_release(
            dsn, Command(request_id="r02s-bad", payload={}),
            release_id="r02s-bad", protocol_id=pid, versions=["r02s-cand"],
            scope={"family": "software-repair"}, disposition="limited",
            fallback="r02s-ref", policy_version="sel-v1", invalidation={},
            evidence_refs=[], evaluator_version="v1")


def test_trial_supported_scope_enforced(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02v")
    trial_scope = {"family": "software-repair", "language": "python"}
    pid, _ = _bound_pair(dsn, launcher, env, "r02v",
                         scope={"family": "software-repair"},
                         trial_scope=trial_scope)
    with pytest.raises(SettlementError,
                       match="drops supported constraint 'language'.*trial protocol"):
        capabilities.scoped_release(
            dsn, Command(request_id="r02v-bad", payload={}),
            release_id="r02v-bad", protocol_id=pid, versions=["r02v-cand"],
            scope={"family": "software-repair"}, disposition="limited",
            fallback="r02v-ref", policy_version="sel-v1", invalidation={},
            evidence_refs=[], evaluator_version="v1")
    out = capabilities.scoped_release(
        dsn, Command(request_id="r02v-rel", payload={}), release_id="r02v-rel",
        protocol_id=pid, versions=["r02v-cand"],
        scope={"family": "software-repair", "language": "python",
               "suite": "panel"},
        disposition="limited", fallback="r02v-ref", policy_version="sel-v1",
        invalidation={}, evidence_refs=[], evaluator_version="v1")
    assert out.code == ResultCode.APPLIED


def test_trial_scope_change_refused(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02k")
    trial_scope = {"family": "software-repair", "language": "python"}
    pid, _ = _bound_pair(dsn, launcher, env, "r02k",
                         scope={"family": "software-repair"},
                         trial_scope=trial_scope)
    with pytest.raises(SettlementError,
                       match="changes supported constraint 'language'"):
        capabilities.scoped_release(
            dsn, Command(request_id="r02k-bad", payload={}),
            release_id="r02k-bad", protocol_id=pid, versions=["r02k-cand"],
            scope={"family": "software-repair", "language": "go"},
            disposition="limited", fallback="r02k-ref", policy_version="sel-v1",
            invalidation={}, evidence_refs=[], evaluator_version="v1")


def test_experimental_release_skips_scope(migrated_db):
    dsn = migrated_db
    seed_env(dsn, "r02x2")
    pid = _freeze(dsn, "r02x2")
    _cap_row(dsn, "r02x2-cand", {"family": "software-repair",
                                 "language": "python"})
    out = capabilities.scoped_release(
        dsn, Command(request_id="r02x2-rel", payload={}),
        release_id="r02x2-rel", protocol_id=pid, versions=["r02x2-cand"],
        scope={"family": "software-repair"}, disposition="experimental",
        fallback="r02x2-ref", policy_version="sel-v1", invalidation={},
        evidence_refs=[], evaluator_version="v1")
    assert out.code == ResultCode.APPLIED


def test_promotion_without_tested_applicability_refused(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02z")
    pid, _ = _bound_pair(dsn, launcher, env, "r02z", scope={})
    with pytest.raises(SettlementError, match="no tested applicability"):
        capabilities.scoped_release(
            dsn, Command(request_id="r02z-rel", payload={}),
            release_id="r02z-rel", protocol_id=pid, versions=["r02z-cand"],
            scope={"family": "software-repair"}, disposition="limited",
            fallback="r02z-ref", policy_version="sel-v1", invalidation={},
            evidence_refs=[], evaluator_version="v1")


def test_protocol_supported_scope_roundtrip(migrated_db):
    dsn = migrated_db
    pid = _freeze(dsn, "r02a",
                  supported_scope={"family": "software-repair"})
    assert trials._protocol(dsn, pid)["supported_scope"] == \
        {"family": "software-repair"}
    trials.amend_protocol(dsn, Command(request_id="r02a-amd", payload={}),
                          protocol_id="r02a-p2", supersedes=pid,
                          supported_scope={"family": "software-repair",
                                           "language": "python"})
    assert trials._protocol(dsn, "r02a-p2")["supported_scope"] == \
        {"family": "software-repair", "language": "python"}
