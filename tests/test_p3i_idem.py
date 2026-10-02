from __future__ import annotations

import threading
import uuid

from settlement import broker, db, store
from settlement.broker import BrokerOp, LaunchOutcome, ReceiptProposal
from settlement.common import Command, ResultCode
from settlement.gateway import ModelResponse, Usage


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"p3i_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _setup(dsn, authorized=1000):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": authorized}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _sandbox(dsn, op_id="op1"):
    return broker.ensure_operation(
        dsn, operation_id=op_id, effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 5_000, "max_output_bytes": 65_536},
        allocation_id="a1", attempt_id="att1")


def _model(dsn, op_id="opm"):
    return broker.ensure_operation(
        dsn, operation_id=op_id, effect="model-inference",
        payload={"model": "m1", "messages": [{"role": "user", "content": "hi"}],
                 "max_output_tokens": 16, "deadline_ms": 10_000},
        allocation_id="a1", attempt_id="att1")


class ScriptLauncher:
    launcher_id = "fake-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.sends: list[str] = []
        self.sent_set: set[str] = set()
        self.lock = threading.Lock()
        self.results: dict[str, dict] = {}

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        with self.lock:
            self.sends.append(op.operation_id)
            self.sent_set.add(op.operation_id)
        receipt = ReceiptProposal(receipt_identity=f"fake:{op.operation_id}",
                                  content={"ok": True}, outcome="success",
                                  provenance=self.launcher_id)
        self.results[op.operation_id] = {"outcome": "success"}
        return LaunchOutcome(sent=True, receipt=receipt)

    def prior_send(self, operation_id: str) -> bool:
        return operation_id in self.sent_set

    def prove_never_sent(self, operation_id: str, dispatch_generation: int | None = None) -> bool:
        return operation_id not in self.sent_set

    def stop(self, operation_id: str) -> bool:
        return True

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str) -> dict | None:
        return self.results.get(operation_id)


class CountingGateway:
    def __init__(self):
        self.calls: list[str] = []

    def infer(self, request):
        self.calls.append(request.operation_id)
        return ModelResponse(request.operation_id, f"answer-{len(self.calls)}",
                             {"simulated": True},
                             Usage(input_tokens=3, output_tokens=2, charge_units=3,
                                   charge_scale=1000, billed=True), "stop")


def _rewind_to_prepared(dsn, op_id):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE operations SET dispatch_state = 'prepared', launcher_id = '',"
                        " receipt_provenance = '', updated_at = now() WHERE id = %s", (op_id,))
            cur.execute("DELETE FROM outbox WHERE workflow_identity = %s", (f"dispatch:{op_id}",))
        conn.commit()


def test_p3i_model_rewind_never_reinfers(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _model(dsn)
    gateway = CountingGateway()
    first = broker.dispatch_operation(dsn, "opm", launchers={}, gateway=gateway,
                                      ownership_generation=gen)
    assert first.dispatch_state == "observed" and gateway.calls == ["opm"]
    settled_once = store.allocation_status(dsn, "a1")["consumed"]
    assert settled_once == 3, "a billed model call settles its measured charge once"
    _rewind_to_prepared(dsn, "opm")
    retry = broker.dispatch_operation(dsn, "opm", launchers={}, gateway=gateway,
                                      ownership_generation=gen)
    assert retry.sent_this_call is False
    assert retry.next_decision == "needs-reconciliation"
    assert gateway.calls == ["opm"]
    assert store.allocation_status(dsn, "a1")["consumed"] == settled_once


def test_p3i_billed_model_without_token_counts_never_settles(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _model(dsn)

    class Uncounted(CountingGateway):
        def infer(self, request):
            self.calls.append(request.operation_id)
            return ModelResponse(request.operation_id, "answer",
                                 {"simulated": True},
                                 Usage(charge_units=3, billed=True), "stop")

    gateway = Uncounted()
    status = broker.dispatch_operation(dsn, "opm", launchers={}, gateway=gateway,
                                       ownership_generation=gen)
    assert gateway.calls == ["opm"]
    assert status.next_decision == "receipt-admission-refused"
    assert broker.read_operation(dsn, "opm")["settled"] is False
    assert store.allocation_status(dsn, "a1")["consumed"] == 0
    _rewind_to_prepared(dsn, "opm")
    retry = broker.dispatch_operation(dsn, "opm", launchers={}, gateway=gateway,
                                      ownership_generation=gen)
    assert retry.next_decision != "terminal"
    assert store.allocation_status(dsn, "a1")["consumed"] == 0


def test_p3i_sandbox_rewind_fresh_launcher_never_resends(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _sandbox(dsn)
    broker.dispatch_operation(dsn, "op1", launchers={"local-process": ScriptLauncher()},
                              ownership_generation=gen)
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "observed"
    _rewind_to_prepared(dsn, "op1")
    fresh = ScriptLauncher()
    retry = broker.dispatch_operation(dsn, "op1", launchers={"local-process": fresh},
                                      ownership_generation=gen)
    assert retry.sent_this_call is False
    assert retry.next_decision == "needs-reconciliation"
    assert fresh.sends == []


def test_p3i_cross_identity_success_receipt_settles_once(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _sandbox(dsn)
    broker.dispatch_operation(dsn, "op1", launchers={"local-process": ScriptLauncher()},
                              ownership_generation=gen)
    before = store.allocation_status(dsn, "a1")
    dup = broker.admit_launcher_receipt(dsn, "op1", ReceiptProposal(
        receipt_identity="fake:op1-late", content={"ok": True, "late": True},
        outcome="success", provenance="fake-1"))
    assert dup.code == ResultCode.APPLIED
    after = store.allocation_status(dsn, "a1")
    assert (after["consumed"], after["reserved"]) == (before["consumed"], before["reserved"])
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "observed"


def test_p3i_concurrent_dispatch_sends_once(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _sandbox(dsn)
    launcher = ScriptLauncher()
    barrier = threading.Barrier(2)
    results: list = []

    def _run():
        barrier.wait()
        results.append(broker.dispatch_operation(
            dsn, "op1", launchers={"local-process": launcher}, ownership_generation=gen))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert launcher.sends == ["op1"]
    assert all(r.sent_this_call is False or r.dispatch_state == "observed" for r in results)


def test_p3i_concurrent_redispatch_sends_once(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _sandbox(dsn)
    store.advance_dispatch(dsn, _cmd({"operation_id": "op1", "launcher_id": "fake-1",
                                      "provider_id": ""}))
    assert broker.reconcile(dsn, "op1", {}).decision == "unresolved-liability"
    generation = int(broker.read_operation(dsn, "op1")["payload"]["_dispatch_generation"])
    launchers = {"local-process": ScriptLauncher()}
    barrier = threading.Barrier(2)
    results: list = []

    def _run():
        barrier.wait()
        results.append(broker.redispatch_after_reset(
            dsn, "op1", launchers, ownership_generation=gen,
            expected_generation=generation))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(launchers["local-process"].sends) == 1
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "observed"
    assert sum(r.sent_this_call for r in results) == 1


def test_p3i_redispatch_refused_when_no_launcher_can_attest(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _sandbox(dsn)
    store.advance_dispatch(dsn, _cmd({"operation_id": "op1", "launcher_id": "gone",
                                      "provider_id": ""}))
    assert broker.reconcile(dsn, "op1", {}).decision == "unresolved-liability"
    generation = int(broker.read_operation(dsn, "op1")["payload"]["_dispatch_generation"])
    launchers = {"local-process": ScriptLauncher()}
    status = broker.redispatch_after_reset(
        dsn, "op1", launchers, ownership_generation=gen,
        expected_generation=generation)
    assert status.next_decision == "refused-never-sent-proof"
    assert status.sent_this_call is False
    assert launchers["local-process"].sends == []
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "unresolved"
    assert int(broker.read_operation(dsn, "op1")["payload"]["_dispatch_generation"]) == generation


def test_p3i_redispatch_refused_when_launcher_already_sent(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _sandbox(dsn)
    store.advance_dispatch(dsn, _cmd({"operation_id": "op1", "launcher_id": "fake-1",
                                      "provider_id": ""}))
    assert broker.reconcile(dsn, "op1", {}).decision == "unresolved-liability"
    generation = int(broker.read_operation(dsn, "op1")["payload"]["_dispatch_generation"])
    launcher = ScriptLauncher()
    launcher.sent_set.add("op1")
    status = broker.redispatch_after_reset(
        dsn, "op1", {"local-process": launcher}, ownership_generation=gen,
        expected_generation=generation)
    assert status.next_decision == "refused-never-sent-proof"
    assert status.sent_this_call is False
    assert launcher.sends == []
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "unresolved"


def test_p3i_reset_refuses_dispatching_with_unknown_receipt(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    _sandbox(dsn)
    store.advance_dispatch(dsn, _cmd({"operation_id": "op1", "launcher_id": "fake-1",
                                      "provider_id": ""}))
    lost = broker.admit_launcher_receipt(dsn, "op1", ReceiptProposal(
        receipt_identity="lost:op1", content={"lost": True},
        outcome="unknown", provenance="broker"))
    assert lost.code == ResultCode.APPLIED
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "unresolved"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE operations SET dispatch_state = 'dispatching',"
                        " updated_at = now() WHERE id = 'op1'")
        conn.commit()
    refused = store.reset_dispatch(dsn, _cmd({"operation_id": "op1"}))
    assert refused.code == ResultCode.INVALID_INPUT
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "dispatching"
