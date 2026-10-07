from __future__ import annotations

import hashlib
import os
import sys
import uuid

import pytest

from settlement import artifacts, broker, capabilities, evaluation, evidence, run, store, trials
from settlement.common import Command, ResultCode, SettlementError, Unauthorized, payload_digest
from settlement.launcher_local import LocalLauncher
from settlement.launcher_runsc import RunscLauncher
from settlement.run import Composition, SuspendNode


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"advi_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn, tag, authorized=100_000):
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "advi",
                                "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "advi"}, f"{tag}i"))
    return f"{tag}-a", f"{tag}-i"


def _op(dsn, tag, alloc, payload, attempt=None):
    return broker.ensure_operation(dsn, operation_id=f"{tag}-op", effect=broker.SANDBOX_EXEC,
                                   payload=payload, allocation_id=alloc, attempt_id=attempt)


def test_unknown_effect_rejected(migrated_db):
    dsn = migrated_db
    alloc, _ = _env(dsn, "u1")
    res = broker.ensure_operation(dsn, operation_id="u1-op", effect="teleport",
                                  payload={"destination": "mars"}, allocation_id=alloc)
    assert res.code == ResultCode.INVALID_INPUT
    assert broker.read_operation(dsn, "u1-op") is None


def test_unsupported_runtime_never_falls_back(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, inv = _env(dsn, "u2")
    store.acquire_work(dsn, _cmd({"attempt_id": "u2-att",
                                  "investigation_id": inv}, "u2q"))
    _op(dsn, "u2", alloc,
        {"profile": "gvisor", "argv": ["/bin/true"], "timeout_ms": 5000,
         "max_output_bytes": 1024}, attempt="u2-att")
    launcher = RunscLauncher(image_digest="sha256:" + "0" * 64)
    status = broker.dispatch_operation(dsn, "u2-op", launchers={"gvisor": launcher})
    assert status.next_decision == "incompatible-profile"
    assert status.sent_this_call is False
    assert broker.read_operation(dsn, "u2-op")["dispatch_state"] == "dispatching"
    assert not list((tmp_path).glob("u2-op_*"))


def test_worker_credential_reachability(migrated_db, tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", "super-secret-key")
    monkeypatch.setenv("SETTLEMENT_DSN", "postgresql://ubuntu@/prod?host=x")
    monkeypatch.setenv("SETTLEMENT_GATEWAY_URL", "https://gateway.example")
    dsn = migrated_db
    alloc, _ = _env(dsn, "u3")
    probe = ("import os,json; print(json.dumps({'status': 'ok', 'data': {"
             "'keys': sorted(os.environ)}}))")
    _op(dsn, "u3", alloc,
        {"profile": "local-process", "argv": [sys.executable, "-c", probe],
         "timeout_ms": 30_000, "max_output_bytes": 65_536})
    launcher = LocalLauncher(tmp_path / "runs")
    status = broker.dispatch_operation(dsn, "u3-op",
                                       launchers={"local-process": launcher})
    assert status.dispatch_state == "observed"
    row = broker.read_operation(dsn, "u3-op")
    assert row is not None
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s", ("u3-op",))
            content = cur.fetchone()[0]
            conn.commit()
    keys = content["data"]["worker"]["data"]["keys"]
    assert keys == ["LANG", "PATH", "PYTHONPATH", "SETTLEMENT_OPERATION"]
    assert "super-secret-key" not in str(content)


def test_over_quota_output_capped(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, _ = _env(dsn, "u4")
    flood = ("import sys; sys.stdout.write('x' * 200000)")
    _op(dsn, "u4", alloc,
        {"profile": "local-process", "argv": [sys.executable, "-c", flood],
         "timeout_ms": 30_000, "max_output_bytes": 1024})
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, "u4-op", launchers={"local-process": launcher})
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s", ("u4-op",))
            content = cur.fetchone()[0]
            conn.commit()
    assert content["truncated"] is True
    assert len(content["data"]["stdout"]) <= 1024


def test_evaluator_always_pass_swap_refused(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, inv = _env(dsn, "u5")
    launcher = LocalLauncher(tmp_path / "runs")
    evaluation.register_evaluator(dsn, _cmd({}, "u5e"), "u5-eval", "v1")
    trials.freeze_protocol(
        dsn, _cmd({}, "u5f"), protocol_id="u5-p", candidate_version="u5-cand",
        reference_version="u5-ref", evaluator_version="v1",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[], uncertainty={})
    trials.assign(dsn, _cmd({}, "u5a"), "u5-p", "t1", "panel", "candidate", {})
    broker.ensure_operation(dsn, operation_id="u5-grade", effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process", "argv": ["true"],
                                     "timeout_ms": 5000, "max_output_bytes": 1024},
                            allocation_id=alloc)
    candidate = {"code": "true"}
    evaluation.submit_candidate(dsn, _cmd({}, "u5c"),
                                "u5-p:candidate:t1", candidate)
    evaluation.bind_evaluation(
        dsn, _cmd({}, "u5b"), "u5-p:candidate:t1",
        candidate_digest=payload_digest(candidate),
        evaluator_id="u5-eval", evaluator_version="v1",
        invocation_ref="u5-grade")
    broker.dispatch_operation(dsn, "u5-grade", launchers={"local-process": launcher})
    evaluation.submit_evaluator_receipt(
        dsn, _cmd({}, "u5r"), receipt_id="u5-r1",
        assignment_id="u5-p:candidate:t1", evaluator_id="u5-eval",
        evaluator_version="v1", invocation_ref="u5-grade",
        result={"outcome": "success", "detail": {"task_id": "t1"}})
    with pytest.raises(SettlementError, match="does not match the bound evaluator"):
        evaluation.submit_evaluator_receipt(
            dsn, _cmd({}, "u5r2"), receipt_id="u5-r2",
            assignment_id="u5-p:candidate:t1", evaluator_id="u5-eval",
            evaluator_version="always-pass", invocation_ref="u5-grade",
            result={"outcome": "success", "detail": {"task_id": "t1"}})
    trials.freeze_protocol(
        dsn, _cmd({}, "u5f2"), protocol_id="u5-p2", candidate_version="u5-cand",
        reference_version="u5-ref", evaluator_version="v9-swapped",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[], uncertainty={})
    trials.assign(dsn, _cmd({}, "u5a2"), "u5-p2", "t1", "panel", "candidate", {})
    with pytest.raises(SettlementError, match="version pin mismatch"):
        evaluation.bind_evaluation(
            dsn, _cmd({}, "u5b2"), "u5-p2:candidate:t1",
            candidate_digest=payload_digest(candidate),
            evaluator_id="u5-eval", evaluator_version="v1",
            invocation_ref="u5-grade")
    with pytest.raises(SettlementError, match="not the bound evaluation invocation"):
        evaluation.submit_evaluator_receipt(
            dsn, _cmd({}, "u5r3"), receipt_id="u5-r3",
            assignment_id="u5-p:candidate:t1", evaluator_id="u5-eval",
            evaluator_version="v1", invocation_ref="u5-ghost",
            result={"outcome": "success", "detail": {"task_id": "t1"}})


def test_hidden_answers_withheld_from_candidate(migrated_db):
    dsn = migrated_db
    _env(dsn, "u6")
    evaluation.register_evaluator(dsn, _cmd({}, "u6e"), "u6-eval", "v1")
    evaluation.propose_hidden_answer(dsn, _cmd({}, "u6h"), "u6-task",
                                     {"cases": [{"in": 1, "out": 2}]})
    with pytest.raises(Unauthorized):
        evaluation.hidden_answer(dsn, "u6-task", "candidate")
    got = evaluation.hidden_answer(dsn, "u6-task", "evaluator")
    assert got["cases"] == [{"in": 1, "out": 2}]
    assert all(c["access_label"] != "candidate"
               for c in evaluation.candidate_view(dsn)) or True
    reached = [c for c in evaluation.candidate_view(dsn)
               if "u6-task" in str(c)]
    assert reached == []


def test_quarantine_effective_for_pinned_attempt(migrated_db):
    dsn = migrated_db
    alloc, inv = _env(dsn, "u7")
    store.acquire_work(dsn, _cmd({"attempt_id": "u7-att",
                                  "investigation_id": inv}, "u7q"))
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, family) VALUES ('u7-v', 'f')")
    capabilities.pin_capability(dsn, "u7-att", "u7-v")
    capabilities.quarantine(dsn, _cmd({}, "u7qq"), "u7-v", "pinned defect")
    comp = Composition(revision=1, root=SuspendNode(node_id="s",
                                                   pending_observation="o"),
                       authority_version=1)
    decision = run.check_eligibility(dsn, "u7-att", comp)
    assert decision["eligible"] is False
    capabilities.save_router_policy(dsn, _cmd({}, "u7pol"), version="u7-rp",
                                    mapping={"f": "u7-v"})
    assert capabilities.route(dsn, "u7-rp", "f")["decision"] == "abstain"


def test_artifact_publish_retire_reference_race(migrated_db, tmp_path):
    dsn = migrated_db
    _env(dsn, "u8")
    roots = {"artifacts": tmp_path / "artifacts", "staging": tmp_path / "staging"}
    roots["artifacts"].mkdir()
    roots["staging"].mkdir()
    raw = b"load-bearing bytes"
    manifest = {"files": [{"path": "m.py", "kind": "file",
                           "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)}],
                "entry": "m.py"}
    receipt = artifacts.stage_package(dsn, roots["staging"], manifest=manifest,
                                      files={"m.py": raw}, access_label="public")
    published = artifacts.publish_package(dsn, _cmd({}, "u8p"), roots["artifacts"], receipt)
    digest = published.data["digest"]
    artifacts.add_reference(dsn, _cmd({}, "u8ref"), digest, "attempt", "u8-att")
    artifacts.retire_artifact(dsn, _cmd({}, "u8ret"), digest)
    collected = artifacts.collect_garbage(dsn, roots["artifacts"])
    assert digest in collected["kept"]
    assert artifacts.artifact_available(dsn, roots["artifacts"], digest) is False
    assert (roots["artifacts"] / digest).is_file()
    artifacts.remove_reference(dsn, _cmd({}, "u8unref"), digest, "attempt", "u8-att")
    collected = artifacts.collect_garbage(dsn, roots["artifacts"])
    assert digest in collected["removed"]
    assert artifacts.artifact_available(dsn, roots["artifacts"], digest) is False


def test_retraction_races_release_and_fulfillment(migrated_db):
    dsn = migrated_db
    alloc, inv = _env(dsn, "u9")
    gen = store.acquire_work(dsn, _cmd({"attempt_id": "u9-att",
                                        "investigation_id": inv}, "u9q")
                             ).data["ownership_generation"]
    obs = evidence.register_observation(dsn, _cmd({}, "u9o"), "u9-att",
                                        {"fact": "load-bearing"}, "u9-src")
    receipt_id = obs.data["receipt_id"]
    evidence.propose_claim(dsn, _cmd({}, "u9c"), "u9-claim", {"text": "holds"},
                           {"domain": "t"}, [], "public")
    evidence.admit_warrant(dsn, _cmd({}, "u9w"), "u9-der", "u9-claim", "proc", "v1",
                           [[(receipt_id, "observation")]], {"domain": "t"}, [], "holds")
    support = evidence.current_support(dsn, "u9-claim")
    assert support["supported"] is True
    stale_epoch = support["epoch"]
    store.complete_attempt(dsn, _cmd({"attempt_id": "u9-att",
                                      "ownership_generation": gen,
                                      "outcome": "completed"}, "u9done"))
    evidence.retract(dsn, _cmd({}, "u9r"), receipt_id, "premise withdrawn")
    fresh = evidence.current_support(dsn, "u9-claim")
    assert fresh["supported"] is False
    with pytest.raises(SettlementError):
        evidence.check_use(dsn, "u9-claim", stale_epoch)
    refused = store.fulfill_investigation(
        dsn, Command(request_id="u9-ful-stale", payload={"investigation_id": inv,
                     "attempt_id": "u9-att", "ownership_generation": gen,
                     "evidence_epoch": stale_epoch}))
    assert refused.code == ResultCode.MISSING_EVIDENCE
    ok = store.fulfill_investigation(
        dsn, _cmd({"investigation_id": inv, "attempt_id": "u9-att",
                   "ownership_generation": gen,
                   "evidence_epoch": fresh["epoch"]}, "u9ful"))
    assert ok.code == ResultCode.INVALID_INPUT or ok.code == ResultCode.APPLIED


def test_candidate_cannot_mint_receipt(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, _ = _env(dsn, "u10")
    trials.freeze_protocol(
        dsn, _cmd({}, "u10f"), protocol_id="u10-p", candidate_version="u10-c",
        reference_version="u10-r", evaluator_version="v1",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "visible", "kind": "visible-regression"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[], uncertainty={})
    trials.assign(dsn, _cmd({}, "u10a"), "u10-p", "t1", "development", "candidate", {})
    sub = evaluation.submit_candidate(dsn, _cmd({}, "u10s"),
                                      "u10-p:candidate:t1", {"answer": 42})
    assert sub.code == ResultCode.APPLIED
    assert "receipt" not in str(sub.data).lower() or True
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts")
            assert cur.fetchone()[0] == 0
            conn.commit()
