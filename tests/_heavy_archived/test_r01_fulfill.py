from __future__ import annotations

import concurrent.futures
import hashlib
import shutil
import threading
import uuid
from datetime import datetime, timezone

import pytest

from settlement import artifacts, broker, evidence, steward, store
from settlement.broker import BrokerOp, LaunchOutcome, ReceiptProposal
from settlement.common import Command, MissingEvidence, ResultCode
from settlement.launcher_local import LocalLauncher


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"r01b_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _env(dsn, tag="r01b"):
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 100000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i", "objective": "r01b"}))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                        "investigation_id": f"{tag}-i"})).data["ownership_generation"]
    return f"{tag}-a", f"{tag}-i", f"{tag}-att", gen


def _complete(dsn, attempt, gen):
    return store.complete_attempt(dsn, _cmd({"attempt_id": attempt,
                                             "ownership_generation": gen,
                                             "outcome": "completed"}))


def _control(dsn):
    return store.get_control(dsn)


def _fulfill(dsn, inv, attempt, gen, **over):
    payload = {"investigation_id": inv, "attempt_id": attempt,
               "ownership_generation": gen, "revision": 1,
               "authority_version": int(_control(dsn)["authority_version"]),
               "evidence_epoch": int(_control(dsn)["evidence_epoch"]),
               "obligations": {}}
    payload.update(over)
    return store.fulfill_investigation(dsn, _cmd(payload))


def _revoke(dsn):
    version = int(_control(dsn)["authority_version"])
    assert store.seed_grant(
        dsn, _cmd({"version": version + 1, "charter_text": "r01b revoke"})).code == ResultCode.APPLIED


def _sandbox(dsn, op, alloc, attempt):
    assert broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 10000, "max_output_bytes": 1024},
        allocation_id=alloc, attempt_id=attempt).code == ResultCode.APPLIED


class CountingLauncher:
    launcher_id = "count-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.sends: list[str] = []
        self._lock = threading.Lock()

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        with self._lock:
            self.sends.append(op.operation_id)
        return LaunchOutcome(sent=True, receipt=ReceiptProposal(
            receipt_identity=f"count:{op.operation_id}", content={"ok": True},
            outcome="success", provenance=self.launcher_id))

    def prior_send(self, operation_id: str) -> bool:
        return operation_id in self.sends

    def stop(self, operation_id: str) -> bool:
        return False

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str):
        return None


def test_fulfill_artifact_claim_requires_root_and_bytes(migrated_db, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    art.mkdir()
    staging.mkdir()
    raw = b"artifact premise bytes"
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {"files": [{"path": "doc.txt", "kind": "file",
                           "digest": digest, "size": len(raw)}],
                "entry": "doc.txt"}
    receipt = artifacts.stage_package(dsn, staging, manifest=manifest,
                                      files={"doc.txt": raw},
                                      access_label="public")
    published = artifacts.publish_package(dsn, _cmd({"t": 1}), art, receipt)
    assert published.code == ResultCode.APPLIED
    package = published.data["digest"]
    evidence.propose_claim(dsn, _cmd({"t": 2}), "c-art", {"text": "doc true"})
    evidence.admit_warrant(dsn, _cmd({"t": 3}), "d-art", "c-art", "review",
                           "v1", [[(package, "artifact")]])
    obligations = {"doc": {"claim": "c-art"}}
    store.seed_allocation(dsn, _cmd({"allocation_id": "fa-a", "domain": "cpu",
                                     "authorized": 1000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "fa-i",
                                      "objective": "fa",
                                      "obligations": obligations}))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": "fa-att",
                                        "investigation_id": "fa-i"})
                             ).data["ownership_generation"]
    assert _complete(dsn, "fa-att", gen).code == ResultCode.APPLIED

    def _try(root):
        payload = {"investigation_id": "fa-i", "attempt_id": "fa-att",
                   "ownership_generation": gen, "revision": 1,
                   "authority_version": int(_control(dsn)["authority_version"]),
                   "evidence_epoch": int(_control(dsn)["evidence_epoch"]),
                   "obligations": obligations}
        if root is not None:
            payload["artifacts_root"] = str(root)
        return store.fulfill_investigation(dsn, _cmd(payload))

    refused = _try(None)
    assert refused.code == ResultCode.MISSING_EVIDENCE
    assert "artifacts root" in refused.detail
    assert _try(art).code == ResultCode.APPLIED
    (art / package).write_bytes(b"tampered")
    with pytest.raises(MissingEvidence):
        evidence.check_use_verified(dsn, "c-art",
                                    int(_control(dsn)["evidence_epoch"]), art)


def test_fulfill_valid_payload_applies(migrated_db):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    first = _fulfill(dsn, inv, attempt, gen)
    assert first.code == ResultCode.APPLIED
    assert first.data["attempt_id"] == attempt
    again = _fulfill(dsn, inv, attempt, gen)
    assert again.code != ResultCode.APPLIED
    assert "already fulfilled" in again.detail


@pytest.mark.parametrize("drop", ["revision", "authority_version", "evidence_epoch",
                                  "attempt_id", "ownership_generation", "obligations"])
def test_fulfill_minimal_payloads_refused(migrated_db, drop):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    payload = {"investigation_id": inv, "attempt_id": attempt,
               "ownership_generation": gen, "revision": 1,
               "authority_version": int(_control(dsn)["authority_version"]),
               "evidence_epoch": int(_control(dsn)["evidence_epoch"]),
               "obligations": {}}
    del payload[drop]
    refused = store.fulfill_investigation(dsn, _cmd(payload))
    assert refused.code != ResultCode.APPLIED
    bare = store.fulfill_investigation(dsn, _cmd({"investigation_id": inv}))
    assert bare.code != ResultCode.APPLIED


def test_fulfill_unrelated_completed_attempt_refused(migrated_db):
    dsn = migrated_db
    _, inv_a, att_a, gen_a = _env(dsn, "r01bu1")
    _, inv_b, att_b, gen_b = _env(dsn, "r01bu2")
    assert _complete(dsn, att_a, gen_a).code == ResultCode.APPLIED
    assert _complete(dsn, att_b, gen_b).code == ResultCode.APPLIED
    crossed = _fulfill(dsn, inv_a, att_b, gen_b)
    assert crossed.code == ResultCode.INVALID_INPUT
    assert _fulfill(dsn, inv_a, att_a, gen_a).code == ResultCode.APPLIED
    assert _fulfill(dsn, inv_b, att_b, gen_b).code == ResultCode.APPLIED


def test_fulfill_stale_evidence_refused(migrated_db):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    epoch = int(_control(dsn)["evidence_epoch"])
    assert store.register_evidence_change(dsn, _cmd({})).code == ResultCode.APPLIED
    stale = _fulfill(dsn, inv, attempt, gen, evidence_epoch=epoch)
    assert stale.code == ResultCode.MISSING_EVIDENCE
    assert _fulfill(dsn, inv, attempt, gen).code == ResultCode.APPLIED


def test_fulfill_stale_authority_refused(migrated_db):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    pinned = int(_control(dsn)["authority_version"])
    _revoke(dsn)
    stale = _fulfill(dsn, inv, attempt, gen, authority_version=pinned)
    assert stale.code == ResultCode.UNAUTHORIZED
    assert _fulfill(dsn, inv, attempt, gen).code == ResultCode.APPLIED


def test_fulfill_stale_generation_and_revision_refused(migrated_db):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert steward.issue_lease(dsn, _cmd({"attempt_id": attempt})).code == ResultCode.APPLIED
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    assert steward.expire_lease(dsn, _cmd({"attempt_id": attempt})).code == ResultCode.APPLIED
    assert _fulfill(dsn, inv, attempt, gen).code == ResultCode.STALE_REVISION
    assert store.amend_commitment(
        dsn, _cmd({"investigation_id": inv, "objective": "next"}, expected_revision=1)
    ).code == ResultCode.APPLIED
    assert _fulfill(dsn, inv, attempt, gen + 1, revision=1).code == ResultCode.STALE_REVISION


def test_fulfill_obligations_pin_refused_on_change(migrated_db):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    assert _fulfill(dsn, inv, attempt, gen, obligations={"o1": "done"}).code == ResultCode.STALE_REVISION
    assert store.amend_commitment(
        dsn, _cmd({"investigation_id": inv, "obligations": {"o1": "done"}}, expected_revision=1)
    ).code == ResultCode.APPLIED
    gen2 = store.acquire_work(dsn, _cmd({"attempt_id": "r01b-att2",
                                         "investigation_id": inv})).data["ownership_generation"]
    assert _complete(dsn, "r01b-att2", gen2).code == ResultCode.APPLIED
    assert _fulfill(dsn, inv, "r01b-att2", gen2, revision=2,
                    obligations={}).code == ResultCode.STALE_REVISION
    unwitnessed = _fulfill(dsn, inv, "r01b-att2", gen2, revision=2,
                           obligations={"o1": "done"})
    assert unwitnessed.code == ResultCode.MISSING_EVIDENCE
    assert "witness" in unwitnessed.detail


def test_fulfill_running_attempt_refused(migrated_db):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert _fulfill(dsn, inv, attempt, gen).code == ResultCode.INVALID_INPUT
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    assert _fulfill(dsn, inv, attempt, gen).code == ResultCode.APPLIED


def test_override_needs_explicit_attribution(migrated_db):
    dsn = migrated_db
    _, inv, _, _ = _env(dsn)
    assert store.fulfill_investigation_override(
        dsn, _cmd({"investigation_id": inv, "revision": 1})).code != ResultCode.APPLIED
    assert store.fulfill_investigation_override(
        dsn, _cmd({"investigation_id": inv, "revision": 1,
                   "operator": "op", "override_reason": ""})).code != ResultCode.APPLIED
    done = store.fulfill_investigation_override(
        dsn, _cmd({"investigation_id": inv, "revision": 1,
                   "operator": "duty-officer", "override_reason": "charter waiver 7"}))
    assert done.code == ResultCode.APPLIED
    assert done.data["override"] is True
    events = store.read_events(dsn)["events"]
    assert any(e["kind"] == "commitment.fulfilled_override"
               and e["payload"]["operator"] == "duty-officer" for e in events)
    assert store.fulfill_investigation_override(
        dsn, _cmd({"investigation_id": inv, "revision": 1,
                   "operator": "duty-officer", "override_reason": "again"})) \
        .code != ResultCode.APPLIED


def test_steward_fulfillment_delegation(migrated_db):
    dsn = migrated_db
    _, inv, attempt, gen = _env(dsn)
    assert _complete(dsn, attempt, gen).code == ResultCode.APPLIED
    payload = {"investigation_id": inv, "attempt_id": attempt,
               "ownership_generation": gen, "revision": 1,
               "authority_version": int(_control(dsn)["authority_version"]),
               "evidence_epoch": int(_control(dsn)["evidence_epoch"]), "obligations": {}}
    assert steward.fulfill_investigation(dsn, _cmd(payload)).code == ResultCode.APPLIED
    assert steward.fulfill_investigation_override(
        dsn, _cmd({"investigation_id": inv, "revision": 1,
                   "operator": "o", "override_reason": "r"})).code != ResultCode.APPLIED


def _paused_dispatch(dsn, op, launcher, intervene, monkeypatch):
    real = broker._advance
    entered, release, calls = threading.Event(), threading.Event(), []
    decision = {}

    def gated(dsn_, op_, launcher_, provider_, gen_, grant_):
        calls.append(1)
        if len(calls) == 2:
            entered.set()
            assert release.wait(timeout=30)
        return real(dsn_, op_, launcher_, provider_, gen_, grant_)

    monkeypatch.setattr(broker, "_advance", gated)
    holder = {}
    worker = threading.Thread(
        target=lambda: holder.setdefault("status", broker.dispatch_operation(
            dsn, op, launchers={"local-process": launcher})))
    worker.start()
    assert entered.wait(timeout=30)
    intervene()
    release.set()
    worker.join(timeout=60)
    assert not worker.is_alive()
    decision["advances"] = len(calls)
    return holder["status"], decision


def test_paused_dispatcher_fenced_by_authority_change(migrated_db, monkeypatch):
    dsn = migrated_db
    alloc, _, attempt, _ = _env(dsn, "r01bf")
    _sandbox(dsn, "r01bf-op", alloc, attempt)
    launcher = CountingLauncher()
    status, _ = _paused_dispatch(
        dsn, "r01bf-op", launcher, lambda: _revoke(dsn), monkeypatch)
    assert status.sent_this_call is False
    assert status.next_decision == "stale-grant"
    assert launcher.sends == []
    assert store.operation_receipts(dsn, "r01bf-op") == []
    assert broker.read_operation(dsn, "r01bf-op")["dispatch_state"] == "dispatching"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0


def test_paused_dispatcher_never_resets_to_sendable(migrated_db, monkeypatch):
    dsn = migrated_db
    alloc, _, attempt, _ = _env(dsn, "r01bg")
    _sandbox(dsn, "r01bg-op", alloc, attempt)
    launcher = CountingLauncher()

    def intervene():
        decision = broker.reconcile(dsn, "r01bg-op", {"local-process": launcher})
        assert decision.decision == "unresolved-liability"
        _revoke(dsn)

    status, _ = _paused_dispatch(dsn, "r01bg-op", launcher, intervene, monkeypatch)
    assert status.sent_this_call is False
    assert launcher.sends == []
    assert store.operation_receipts(dsn, "r01bg-op") == []
    assert broker.read_operation(dsn, "r01bg-op")["dispatch_state"] == "unresolved"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0


def test_lost_launcher_state_and_double_recovery_stay_unresolved(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, _, attempt, _ = _env(dsn, "r01bh")
    _sandbox(dsn, "r01bh-op", alloc, attempt)
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    advanced = store.advance_dispatch(dsn, _cmd({"operation_id": "r01bh-op",
                                                 "launcher_id": launcher.launcher_id}))
    assert advanced.code == ResultCode.APPLIED
    assert int(advanced.data["dispatch_generation"]) == 1
    shutil.rmtree(run_dir)
    run_dir.mkdir()
    fresh = LocalLauncher(run_dir)
    assert fresh.prove_never_sent("r01bh-op") is True
    first = broker.reconcile(dsn, "r01bh-op", {"local-process": fresh})
    assert first.decision == "unresolved-liability"
    assert broker.read_operation(dsn, "r01bh-op")["dispatch_state"] == "unresolved"
    second = broker.reconcile(dsn, "r01bh-op", {"local-process": fresh})
    assert second.decision == "unresolved-liability"
    recovered = broker.recover(dsn, {"local-process": fresh})
    assert any("unresolved-liability" in entry for entry in recovered.repaired)
    assert broker.read_operation(dsn, "r01bh-op")["dispatch_state"] == "unresolved"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0


def test_explicit_reset_fences_prior_sender_and_readmits(migrated_db):
    dsn = migrated_db
    alloc, _, attempt, _ = _env(dsn, "r01bi")
    _sandbox(dsn, "r01bi-op", alloc, attempt)
    launcher = CountingLauncher()
    advanced = store.advance_dispatch(dsn, _cmd({"operation_id": "r01bi-op",
                                                 "launcher_id": launcher.launcher_id}))
    assert int(advanced.data["dispatch_generation"]) == 1
    stale = store.reset_dispatch(dsn, _cmd({"operation_id": "r01bi-op",
                                            "expected_generation": 99}))
    assert stale.code == ResultCode.STALE_REVISION
    unproven = store.reset_dispatch(dsn, _cmd({"operation_id": "r01bi-op",
                                               "expected_generation": 1}))
    assert unproven.code == ResultCode.MISSING_EVIDENCE
    assert broker.read_operation(dsn, "r01bi-op")["dispatch_state"] == "dispatching"
    assert int(broker.read_operation(dsn, "r01bi-op")["payload"]["_dispatch_generation"]) == 1
    forged = store.reset_dispatch(dsn, _cmd({"operation_id": "r01bi-op",
                                             "expected_generation": 1,
                                             "never_sent_proof": {
                                                 "claim": "never-sent",
                                                 "subject": "r01bi-op",
                                                 "provenance": "forged",
                                                 "dispatch_generation": 1}}))
    assert forged.code == ResultCode.MISSING_EVIDENCE
    assert broker.read_operation(dsn, "r01bi-op")["dispatch_state"] == "dispatching"
    reset = store.reset_dispatch(dsn, _cmd({"operation_id": "r01bi-op",
                                            "expected_generation": 1,
                                            "never_sent_proof": {
                                                "claim": "never-sent",
                                                "subject": "r01bi-op",
                                                "provenance": f"{launcher.launcher_id}"
                                                             ":prove_never_sent",
                                                "dispatch_generation": 1}}))
    assert reset.code == ResultCode.APPLIED
    assert int(reset.data["dispatch_generation"]) == 2
    assert broker.read_operation(dsn, "r01bi-op")["dispatch_state"] == "prepared"
    assert broker.read_operation(dsn, "r01bi-op")["payload"]["_never_sent_proof"]["provenance"] \
        == f"{launcher.launcher_id}:prove_never_sent"
    fenced = broker._finish_send(dsn, "r01bi-op", LaunchOutcome(
        sent=True, receipt=ReceiptProposal(receipt_identity="count:r01bi-op",
                                           content={"ok": True}, outcome="success",
                                           provenance=launcher.launcher_id)), 1)
    assert fenced.sent_this_call is False
    assert fenced.next_decision == "needs-reconciliation"
    assert broker.read_operation(dsn, "r01bi-op")["dispatch_state"] == "prepared"
    assert store.operation_receipts(dsn, "r01bi-op") == [], \
        "a reset operation is prepared and admits no receipt, fenced or otherwise"
    readmit = store.advance_dispatch(dsn, _cmd({"operation_id": "r01bi-op",
                                                "launcher_id": launcher.launcher_id}))
    assert readmit.code == ResultCode.APPLIED
    assert int(readmit.data["dispatch_generation"]) == 3
    settled = broker._finish_send(dsn, "r01bi-op", LaunchOutcome(
        sent=True, receipt=ReceiptProposal(receipt_identity="count:r01bi-op",
                                           content={"ok": True}, outcome="success",
                                           provenance=launcher.launcher_id)), 3)
    assert settled.sent_this_call is True
    assert broker.read_operation(dsn, "r01bi-op")["dispatch_state"] == "observed"
    receipts = {r["receipt_identity"] for r in store.operation_receipts(dsn, "r01bi-op")}
    assert receipts == {"count:r01bi-op"}
    repair = store.reconcile_operation(dsn, _cmd({"operation_id": "r01bi-op",
                                                  "resolution": "reconciled"}))
    assert repair.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    assert int(broker.read_operation(dsn, "r01bi-op")["payload"]["_dispatch_generation"]) == 3


def test_replayed_sandbox_and_inline_never_resend(migrated_db):
    dsn = migrated_db
    alloc, _, attempt, _ = _env(dsn, "r01bj")
    _sandbox(dsn, "r01bj-op", alloc, attempt)
    launcher = CountingLauncher()
    barrier = threading.Barrier(8)

    def go(_):
        barrier.wait(timeout=30)
        return broker.dispatch_operation(dsn, "r01bj-op",
                                         launchers={"local-process": launcher})

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(go, range(8)))
    assert launcher.sends == ["r01bj-op"]
    assert sum(s.sent_this_call for s in statuses) == 1
    assert broker.read_operation(dsn, "r01bj-op")["dispatch_state"] == "observed"
    inline = broker.ensure_operation(
        dsn, operation_id="r01bj-in", effect=broker.OBSERVATION_ADAPTER,
        payload={"adapter": "clock", "input": {}}, allocation_id=alloc, attempt_id=attempt)
    assert inline.code == ResultCode.APPLIED
    barrier2 = threading.Barrier(8)

    def go_inline(_):
        barrier2.wait(timeout=30)
        return broker.dispatch_operation(dsn, "r01bj-in", launchers={})

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        in_statuses = list(pool.map(go_inline, range(8)))
    assert sum(s.sent_this_call for s in in_statuses) == 1
    assert len(store.operation_receipts(dsn, "r01bj-in")) == 1
    repeat = broker.dispatch_operation(dsn, "r01bj-in", launchers={})
    assert repeat.sent_this_call is False


def test_lease_ttl_policy_shared_between_paths(migrated_db, monkeypatch):
    dsn = migrated_db
    assert store.seed_allocation(dsn, _cmd({"allocation_id": "r01bk-a", "domain": "cpu",
                                            "authorized": 100})).code == ResultCode.APPLIED
    assert store.admit_commitment(dsn, _cmd({"investigation_id": "r01bk-i",
                                             "objective": "o"})).code == ResultCode.APPLIED
    for attempt in ("r01bk-w1", "r01bk-w2", "r01bk-w3", "r01bk-w4"):
        store.acquire_work(dsn, _cmd({"attempt_id": attempt,
                                      "investigation_id": "r01bk-i"}))
    assert steward.issue_lease(dsn, _cmd({"attempt_id": "r01bk-w1",
                                          "ttl_ms": 0})).code != ResultCode.APPLIED
    assert steward.issue_lease(dsn, _cmd({"attempt_id": "r01bk-w1",
                                          "ttl_ms": -5})).code != ResultCode.APPLIED
    issued = steward.issue_lease(dsn, _cmd({"attempt_id": "r01bk-w1"}))
    assert issued.code == ResultCode.APPLIED
    before = datetime.now(timezone.utc).timestamp()
    expires = datetime.fromisoformat(issued.data["expires_at"]).timestamp()
    assert 590 <= expires - before <= 610
    assert steward.expire_lease(dsn, _cmd({"attempt_id": "r01bk-w1"})).code == ResultCode.APPLIED
    assert steward.reacquire_lease(dsn, _cmd({"attempt_id": "r01bk-w1",
                                              "ttl_ms": 0})).code != ResultCode.APPLIED
    reacquired = steward.reacquire_lease(dsn, _cmd({"attempt_id": "r01bk-w1"}))
    assert reacquired.code == ResultCode.APPLIED
    before = datetime.now(timezone.utc).timestamp()
    expires = datetime.fromisoformat(reacquired.data["expires_at"]).timestamp()
    assert 590 <= expires - before <= 610
    monkeypatch.setattr(steward, "_LEASE_DEFAULT_TTL_MS", 60_000)
    moved_issue = steward.issue_lease(dsn, _cmd({"attempt_id": "r01bk-w2"}))
    assert moved_issue.code == ResultCode.APPLIED
    before = datetime.now(timezone.utc).timestamp()
    expires = datetime.fromisoformat(moved_issue.data["expires_at"]).timestamp()
    assert 50 <= expires - before <= 70
    assert steward.issue_lease(dsn, _cmd({"attempt_id": "r01bk-w3"})).code == ResultCode.APPLIED
    assert steward.expire_lease(dsn, _cmd({"attempt_id": "r01bk-w3"})).code == ResultCode.APPLIED
    moved_reacquire = steward.reacquire_lease(dsn, _cmd({"attempt_id": "r01bk-w3"}))
    assert moved_reacquire.code == ResultCode.APPLIED
    before = datetime.now(timezone.utc).timestamp()
    expires = datetime.fromisoformat(moved_reacquire.data["expires_at"]).timestamp()
    assert 50 <= expires - before <= 70

