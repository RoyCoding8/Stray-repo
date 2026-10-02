from __future__ import annotations

import uuid

import pytest

from settlement import artifacts, context, evidence, store
from settlement.common import Command, ResultCode


def _cmd(payload=None, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload or {}, **kw)


def _setup(dsn):
    store.admit_commitment(dsn, _cmd({"investigation_id": "inv9", "objective": "o",
                                      "obligations": {"finish": True}}))
    return store.acquire_work(
        dsn, _cmd({"attempt_id": "attA", "investigation_id": "inv9"})).data["ownership_generation"]


def test_context_is_versioned_and_stages_on_missing_mandatory(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    full = context.build_context(
        dsn, _cmd(), {"task": "t", "budget": 3}, [], governing_refs=["grant-v1"],
        caller_scope="evaluator", mandatory=["task", "budget"])
    assert full.code == ResultCode.APPLIED
    assert full.data["staged"] is False and full.data["version"] == 1
    short = context.build_context(
        dsn, _cmd(), {"task": "t"}, [], caller_scope="evaluator",
        mandatory=["task", "budget"])
    assert short.data["staged"] is True
    assert short.data["missing"] == ["budget"]
    assert short.data["narrowed_decision"] == {"task": "t"}


def test_candidate_context_withholds_hidden_sources(migrated_db, tmp_roots):
    dsn = migrated_db
    _setup(dsn)
    evidence.propose_claim(dsn, _cmd(), "c-hid", {"text": "sealed"}, access_label="hidden")
    refs = [{"claim_id": "c-hid"}, {"claim_id": "nope"}]
    candidate = context.build_context(dsn, _cmd(), {"task": "t"}, refs, caller_scope="candidate")
    assert candidate.data["staged"] is True
    assert sorted(candidate.data["withheld"]) == ["c-hid", "nope"]
    assert candidate.data["sources"] == []
    evaluator = context.build_context(dsn, _cmd(), {"task": "t"}, [{"claim_id": "c-hid"}],
                                      caller_scope="evaluator")
    assert evaluator.data["staged"] is False


def test_fresh_worker_resumes_with_pending_effects_and_retraction(migrated_db, tmp_roots):
    dsn = migrated_db
    gen_a = _setup(dsn)
    receipt = evidence.register_observation(
        dsn, _cmd(), "attA", {"finding": "signal"}, source_identity="sensor-1").data["receipt_id"]
    evidence.propose_claim(dsn, _cmd(), "c-resume", {"text": "signal holds"})
    evidence.admit_warrant(dsn, _cmd(), "d-resume", "c-resume", "review", "v1",
                           [[(receipt, "observation")]])
    store.prepare_operation(dsn, _cmd({"operation_id": "op-pending", "attempt_id": "attA",
                                       "operation": {"kind": "infer"}}))
    store.advance_dispatch(dsn, _cmd({"operation_id": "op-pending", "launcher_id": "L1",
                                      "ownership_generation": gen_a}))
    saved = context.save_continuation(
        dsn, _cmd(), tmp_roots["artifacts"], "inv9", "attA", "comp-v1",
        {"node": 2}, [receipt], ["op-pending"], {"finish": True},
        {"next": "verify signal"}, ownership_generation=gen_a)
    assert saved.code == ResultCode.APPLIED
    assert artifacts.artifact_available(dsn, tmp_roots["artifacts"], saved.data["continuation_id"])
    store.suspend_attempt(dsn, _cmd({"attempt_id": "attA", "ownership_generation": gen_a}))
    evidence.retract(dsn, _cmd(), receipt, "sensor recalibrated")
    worker_b = store.acquire_work(
        dsn, _cmd({"attempt_id": "attB", "investigation_id": "inv9"})).data["ownership_generation"]
    assert worker_b == gen_a + 1
    package = context.resume_package(dsn, "inv9")
    assert package["continuation"]["composition_version"] == "comp-v1"
    assert package["continuation"]["next_decision"] == {"next": "verify signal"}
    assert "op-pending" in package["continuation"]["unresolved_ops"]
    assert [op["id"] for op in package["pending_operations"]] == ["op-pending"]
    assert package["observations"] == [{"attempt_id": "attA",
                                        "content": {"finding": "signal"}}]
    assert package["support"]["c-resume"]["supported"] is False
    assert set(package["live_attempts"]) == {"attA", "attB"}
