from __future__ import annotations

import uuid

import pytest

from settlement import broker, store
from settlement.broker import BrokerOp, DispatchStatus, LaunchOutcome, ReceiptProposal
from settlement.exec_profile import STOP_SETTLE_S
from settlement.common import Command, CommandResult, ResultCode
from settlement.gateway import FakeGatewayAdapter, GatewayError, GatewayErrorKind


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _setup(dsn, authorized=1000):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": authorized}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _sandbox_payload(argv=None, timeout_ms=5_000):
    return {"profile": "local-process", "argv": argv or ["/bin/true"],
            "timeout_ms": timeout_ms, "max_output_bytes": 65_536}


class ScriptLauncher:
    launcher_id = "fake-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.sends: list[str] = []
        self.sent_set: set[str] = set()
        self.stops: list[str] = []
        self.live: set[str] = set()
        self.results: dict[str, dict] = {}

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        if op.operation_id in self.sent_set:
            raise AssertionError(f"duplicate send of {op.operation_id}")
        self.sends.append(op.operation_id)
        self.sent_set.add(op.operation_id)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        receipt = ReceiptProposal(receipt_identity=f"fake:{op.operation_id}",
                                  content={"ok": True}, outcome="success",
                                  provenance=self.launcher_id)
        self.results[op.operation_id] = {"outcome": "success"}
        return LaunchOutcome(sent=True, receipt=receipt)

    def prior_send(self, operation_id: str) -> bool:
        return operation_id in self.sent_set

    def stop(self, operation_id: str) -> bool:
        self.stops.append(operation_id)
        self.live.discard(operation_id)
        return True

    def live_ids(self) -> list[str]:
        return sorted(self.live)

    def is_live(self, operation_id: str) -> bool:
        return operation_id in self.live

    def read_result(self, operation_id: str) -> dict | None:
        return self.results.get(operation_id)


def _launchers(fake):
    return {"local-process": fake}


def _ensure(dsn, op_id="op1", effect="sandbox-exec", payload=None, gen=None):
    return broker.ensure_operation(dsn, operation_id=op_id, effect=effect,
                                   payload=payload or _sandbox_payload(),
                                   allocation_id="a1", attempt_id="att1")


def test_receipt_command_identity_routes_outcome_conflict_to_store(monkeypatch):
    admitted = []

    monkeypatch.setattr(
        broker,
        "read_operation",
        lambda *args, **kwargs: {
            "dispatch_state": "dispatching",
            "payload": {"_dispatch_generation": 1},
        },
    )

    def admit_receipt(_dsn, command):
        admitted.append(command)
        return CommandResult(
            code=ResultCode.APPLIED,
            request_id=command.request_id,
            data={"operation_id": command.payload["operation_id"],
                  "conflict": command.payload["outcome"] == "failure"},
        )

    monkeypatch.setattr(broker.store, "admit_receipt", admit_receipt)
    content = {"status": "complete"}

    def submit(outcome, provenance):
        return broker.admit_launcher_receipt(
            "unused",
            "op-conflict",
            ReceiptProposal(
                receipt_identity="receipt-conflict",
                content=content,
                outcome=outcome,
                provenance=provenance,
            ),
        )

    first = submit("success", "source-a")
    conflict = submit("failure", "source-b")
    replay = submit("success", "source-a")

    assert conflict.data["conflict"] is True
    assert admitted[0].request_id == admitted[2].request_id
    assert admitted[0].request_id != admitted[1].request_id


def test_dispatch_sandbox_end_to_end_settles_once(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    fake = ScriptLauncher()
    status = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                       ownership_generation=gen)
    assert status.dispatch_state == "observed" and status.sent_this_call is True
    assert fake.sends == ["op1"]
    assert store.scan_outbox(dsn) == []
    assert store.allocation_status(dsn, "a1")["reserved"] == 0
    repeat = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                       ownership_generation=gen)
    assert repeat.sent_this_call is False and fake.sends == ["op1"]


def test_crash_before_advance_dispatches_once_on_recovery(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "prepared"
    fake = ScriptLauncher()
    status = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                       ownership_generation=gen)
    assert status.sent_this_call is True and fake.sends == ["op1"]
    assert status.dispatch_state == "observed"


def test_death_after_send_never_resends_receipt_reconciles(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    fake = ScriptLauncher()
    crashed = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                        ownership_generation=gen, _crash_after_send=True)
    assert crashed.dispatch_state == "dispatching" and crashed.sent_this_call is True
    assert fake.sends == ["op1"]
    recovered = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                          ownership_generation=gen)
    assert recovered.sent_this_call is False and fake.sends == ["op1"]
    assert recovered.dispatch_state == "dispatching"
    admitted = broker.admit_launcher_receipt(dsn, "op1", ReceiptProposal(
        receipt_identity="fake:op1", content={"ok": True}, outcome="success",
        provenance="fake-1"))
    assert admitted.code == ResultCode.APPLIED and admitted.data["settled"] is True


def test_lost_response_retains_exposure_and_blocks_resend(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    fake = ScriptLauncher(outcomes=[LaunchOutcome(sent=True, lost=True)])
    status = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                       ownership_generation=gen)
    assert status.dispatch_state == "unresolved"
    assert store.allocation_status(dsn, "a1")["reserved"] == 5 + STOP_SETTLE_S + 1
    again = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                      ownership_generation=gen)
    assert again.sent_this_call is False and fake.sends == ["op1"]
    assert again.dispatch_state == "unresolved"


def test_cancel_while_dispatched_keeps_uncertain_charges(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    fake = ScriptLauncher(outcomes=[LaunchOutcome(sent=True, lost=True)])
    broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                              ownership_generation=gen)
    requested = broker.request_cancel(dsn, "op1", launchers=_launchers(fake))
    assert requested.code == ResultCode.APPLIED
    assert fake.stops == ["op1"]
    row = broker.read_operation(dsn, "op1")
    assert row["cancel_state"] == "requested" and row["settled"] is False
    stopped = broker.note_worker_stopped(dsn, "op1")
    assert stopped.code == ResultCode.APPLIED
    assert broker.read_operation(dsn, "op1")["cancel_state"] == "worker_stopped"
    late = broker.admit_launcher_receipt(dsn, "op1", ReceiptProposal(
        receipt_identity="fake:op1-late", content={"ok": True}, outcome="success",
        provenance="fake-1"))
    assert late.code == ResultCode.APPLIED and late.data["settled"] is True
    confirmed = broker.confirm_cancel(dsn, "op1")
    assert confirmed.code == ResultCode.APPLIED
    assert broker.read_operation(dsn, "op1")["cancel_state"] == "confirmed"


def test_stale_ownership_dispatch_refused_without_send(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    _ensure(dsn)
    fake = ScriptLauncher()
    status = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                       ownership_generation=999)
    assert status.dispatch_state == "prepared" and status.sent_this_call is False
    assert status.next_decision == "stale-ownership"
    assert fake.sends == []


def test_unsupported_profile_returns_incompatible(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    _ensure(dsn, payload={"profile": "gvisor", "argv": ["/bin/true"],
                          "timeout_ms": 1_000, "max_output_bytes": 64})
    fake = ScriptLauncher()
    status = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake))
    assert status.next_decision == "incompatible-profile" and fake.sends == []


def test_restored_db_predating_effect_enters_reconciliation(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    fake = ScriptLauncher()
    broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                              ownership_generation=gen)
    assert fake.sends == ["op1"]
    from settlement import db as _db

    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE operations SET dispatch_state = 'prepared', launcher_id = '',"
                        " receipt_provenance = '', updated_at = now() WHERE id = 'op1'")
            cur.execute("DELETE FROM outbox WHERE workflow_identity = 'dispatch:op1'")
        conn.commit()
    revived = broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                                        ownership_generation=gen)
    assert revived.sent_this_call is False and fake.sends == ["op1"]
    assert revived.next_decision == "needs-reconciliation"


def test_model_op_uses_gateway_usage_for_settlement(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    payload = {"model": "m1", "messages": [{"role": "user", "content": "hi"}],
               "max_output_tokens": 16, "deadline_ms": 10_000}
    ensured = broker.ensure_operation(dsn, operation_id="opm", effect="model-inference",
                                      payload=payload, allocation_id="a1", attempt_id="att1")
    assert ensured.data["budget_kind"] == "estimated-budget"
    gateway = FakeGatewayAdapter(text="answer")
    status = broker.dispatch_operation(dsn, "opm", launchers={}, gateway=gateway,
                                       ownership_generation=gen)
    assert status.dispatch_state == "observed" and status.sent_this_call is True
    assert store.allocation_status(dsn, "a1")["reserved"] == 0


def test_model_lost_response_stays_unresolved(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    payload = {"model": "m1", "messages": [{"role": "user", "content": "hi"}],
               "max_output_tokens": 16, "deadline_ms": 10_000}
    broker.ensure_operation(dsn, operation_id="opm", effect="model-inference",
                            payload=payload, allocation_id="a1", attempt_id="att1")
    gateway = ScriptGateway([None])
    status = broker.dispatch_operation(dsn, "opm", launchers={}, gateway=gateway,
                                       ownership_generation=gen)
    assert status.dispatch_state == "unresolved"
    assert gateway.calls == ["opm"]
    again = broker.dispatch_operation(dsn, "opm", launchers={}, gateway=gateway,
                                      ownership_generation=gen)
    assert gateway.calls == ["opm"] and again.dispatch_state == "unresolved"


class ScriptGateway:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[str] = []

    def infer(self, request):
        self.calls.append(request.operation_id)
        action = self.script.pop(0)
        if action is None:
            return None
        if isinstance(action, Exception):
            return action
        from settlement.gateway import ModelResponse, Usage
        return ModelResponse(request.operation_id, action, {"simulated": True},
                             Usage(charge_units=3, provider_enforced_ceiling=False), "stop")


def test_heartbeat_drives_outbox_and_repair_without_inference(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    payload = {"model": "m1", "messages": [{"role": "user", "content": "hi"}],
               "max_output_tokens": 16, "deadline_ms": 10_000}
    broker.ensure_operation(dsn, operation_id="opm", effect="model-inference",
                            payload=payload, allocation_id="a1", attempt_id="att1")
    store.advance_dispatch(dsn, _cmd({"operation_id": "opm", "launcher_id": "gateway",
                                      "ownership_generation": gen}))
    fake = ScriptLauncher()
    gateway = StrictGateway()
    report = broker.heartbeat(dsn, launchers=_launchers(fake), gateway=gateway,
                              ownership_generation=gen, repair_due=True)
    assert "op1" in report.dispatched and "opm" in report.deferred_model
    assert gateway.calls == []
    assert broker.read_operation(dsn, "opm")["dispatch_state"] == "dispatching"


class StrictGateway:
    def __init__(self):
        self.calls: list[str] = []

    def infer(self, request):
        self.calls.append(request.operation_id)
        raise AssertionError("heartbeat must not run inference")


def test_duplicate_receipt_after_commit_settles_once(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    _ensure(dsn)
    fake = ScriptLauncher()
    broker.dispatch_operation(dsn, "op1", launchers=_launchers(fake),
                              ownership_generation=gen)
    before = store.allocation_status(dsn, "a1")
    dup = broker.admit_launcher_receipt(dsn, "op1", ReceiptProposal(
        receipt_identity="fake:op1", content={"ok": True}, outcome="success",
        provenance="fake-1"))
    assert dup.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    after = store.allocation_status(dsn, "a1")
    assert after["consumed"] == before["consumed"]
