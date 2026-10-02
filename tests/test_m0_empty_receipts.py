from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from settlement import broker, store
from settlement.broker import BrokerOp, LaunchOutcome, ReceiptProposal
from settlement.common import Command, ResultCode
from settlement.gateway import GatewayError, GatewayErrorKind


def _cmd(payload: dict) -> Command:
    return Command(request_id="req_%s" % uuid.uuid4().hex[:12], payload=payload)


def _setup(dsn, authorized=100_000):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu",
                                     "authorized": authorized}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1",
                                      "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1",
                                             "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _model_payload():
    return {"model": "probe-model",
            "messages": [{"role": "user", "content": "ping"}],
            "max_output_tokens": 16, "deadline_ms": 5_000}


def _chat_empty_body():
    return json.dumps(
        {"choices": [{"message": {}, "finish_reason": "stop"}],
         "model": "probe-model",
         "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()


def _responses_empty_body():
    return json.dumps(
        {"status": "completed", "output": [], "model": "probe-model",
         "usage": {"input_tokens": 3, "output_tokens": 0}}).encode()


class _ErrGateway:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def infer(self, request):
        self.calls += 1
        return self.error

    def cancel(self, operation_id):
        return False


class _ScriptLauncher:
    launcher_id = "fake-1"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.results = {}

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        receipt = ReceiptProposal(receipt_identity="fake:%s" % op.operation_id,
                                  content={"ok": True}, outcome="success",
                                  provenance=self.launcher_id)
        self.results[op.operation_id] = {"outcome": "success"}
        return LaunchOutcome(sent=True, receipt=receipt)

    def prior_send(self, operation_id: str) -> bool:
        return False

    def stop(self, operation_id: str) -> bool:
        return True

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str) -> dict | None:
        return self.results.get(operation_id)


def test_chat_decoder_preserves_usage_when_text_is_missing():
    from settlement.gateway_http import HttpGatewayAdapter

    result = HttpGatewayAdapter("http://unused")._decode_body(
        _chat_empty_body(), "op-x")
    assert isinstance(result, GatewayError)
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5


def test_responses_decoder_preserves_usage_when_text_is_missing():
    from settlement.gateway_http import HttpGatewayAdapter

    result = HttpGatewayAdapter("http://unused")._decode_responses_body(
        _responses_empty_body(), "op-x")
    assert isinstance(result, GatewayError)
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 0


def test_broker_unknown_receipt_preserves_gateway_usage(migrated_db):
    from settlement.gateway_http import HttpGatewayAdapter

    dsn = migrated_db
    gen = _setup(dsn)
    broker.ensure_operation(dsn, operation_id="op-unk", effect="model-inference",
                            payload=_model_payload(), allocation_id="a1",
                            attempt_id="att1")
    error = HttpGatewayAdapter("http://unused")._decode_body(
        _chat_empty_body(), "op-unk")
    status = broker.dispatch_operation(dsn, "op-unk",
                                       gateway=_ErrGateway(error),
                                       ownership_generation=gen)
    assert status.dispatch_state == "unresolved"
    receipts = store.operation_receipts(dsn, "op-unk")
    assert len(receipts) == 1
    assert receipts[0]["outcome"] == "unknown"
    usage = dict((receipts[0]["content"] or {}).get("usage") or {})
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 5


def test_broker_refuses_receipt_for_never_dispatched_operation(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    broker.ensure_operation(dsn, operation_id="op-prep", effect="model-inference",
                            payload=_model_payload(), allocation_id="a1",
                            attempt_id="att1")
    refused = broker.admit_launcher_receipt(
        dsn, "op-prep",
        ReceiptProposal(receipt_identity="gw:op-prep", content={"text": "hi"},
                        outcome="success", provenance="gateway"))
    assert refused.code == ResultCode.INVALID_INPUT
    assert "never dispatched" in refused.detail


def test_guard_records_incurred_cost_on_error_response():
    from scripts import s09_pilot
    from settlement.gateway import ModelRequest

    delegate = _ErrGateway(GatewayError(GatewayErrorKind.PROTOCOL,
                                       "gateway responses output has no text",
                                       False, "op-e"))
    delegate._s09_costs = [{"cost": 0.01}]
    guard = s09_pilot.StudyGatewayGuard(delegate, pinned_model="free-model",
                                        ceiling=100, already_spent=2)
    request = ModelRequest(model="free-model",
                           messages=({"role": "user", "content": "ping"},),
                           max_output_tokens=8, deadline_ms=5_000)
    result = guard.infer(request)
    assert isinstance(result, GatewayError)
    assert delegate.calls == 1
    assert guard.dispatch_count == 3
    assert "cost" in guard.refusal_reason


def test_guard_blocks_later_dispatch_after_incurred_cost():
    from scripts import s09_pilot
    from settlement.gateway import ModelRequest

    delegate = _ErrGateway(GatewayError(GatewayErrorKind.PROTOCOL, "empty",
                                       False, "op-e"))
    delegate._s09_costs = [{"cost": 0.01}]
    guard = s09_pilot.StudyGatewayGuard(delegate, pinned_model="free-model",
                                        ceiling=100, already_spent=2)
    request = ModelRequest(model="free-model",
                           messages=({"role": "user", "content": "ping"},),
                           max_output_tokens=8, deadline_ms=5_000)
    guard.infer(request)
    with pytest.raises(s09_pilot.StudyGuardRefusal):
        guard.infer(request)
    assert delegate.calls == 1


def test_guard_sees_nonzero_charge_carried_by_the_error_itself():
    from scripts import s09_pilot
    from settlement.gateway import ModelRequest, Usage

    delegate = _ErrGateway(GatewayError(
        GatewayErrorKind.PROTOCOL, "gateway response has no message content",
        False, "op-e",
        Usage(input_tokens=10, output_tokens=5, charge_units=5,
              charge_scale=None, provider_enforced_ceiling=None,
              billed=True)))
    guard = s09_pilot.StudyGatewayGuard(delegate, pinned_model="free-model",
                                        ceiling=100, already_spent=2)
    request = ModelRequest(model="free-model",
                           messages=({"role": "user", "content": "ping"},),
                           max_output_tokens=8, deadline_ms=5_000)
    result = guard.infer(request)
    assert isinstance(result, GatewayError)
    assert "cost" in guard.refusal_reason
    with pytest.raises(s09_pilot.StudyGuardRefusal):
        guard.infer(request)
    assert delegate.calls == 1


def test_reconcile_lever_classifies_live_bundle_without_touching_it(tmp_path):
    from scripts import reconcile_empty_receipts as lever

    bundle = Path(__file__).resolve().parents[1] / "evidence_s09_live_opus"
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(bundle.glob("*.json"))}
    out = tmp_path / "supplement.json"
    assert lever.main([str(bundle), str(out)]) == 0
    result = json.loads(out.read_text())
    assert result["counts"] == {
        "never-sent preparation": 0, "observed provider failure": 0,
        "unknown response": 7, "receipt-admission refusal": 0,
        "export omission": 0}
    assert sorted(entry["operation_id"]
                  for entry in result["buckets"]["unknown response"]) == [
        "ad01-ad01-w0-I-53-b0-ad01-w0-dev-gr-01-construct-l1-init",
        "ad01-ad01-w0-I-54-b1-ad01-w0-dev-sw-00-policy-policy-l1-init",
        "ad01-ad01-w1-I-60-b0-ad01-w1-dev-sw-00-construct-l1-repair",
        "ad01-ad01-w1-I-60-b0-ad01-w1-dev-sw-00-construct-l2-init",
        "ad01-ad01-w1-I-61-b0-ad01-w1-dev-gr-00-construct-l1-init",
        "ad01-ad01-w2-I-62-b0-ad01-w2-dev-sw-00-construct-l1-init",
        "ad01-ad01-w2-I-63-b0-ad01-w2-dev-gr-00-construct-l1-init"]
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(bundle.glob("*.json"))}
    assert after == before


def test_restart_keeps_consumed_authority(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    broker.ensure_operation(
        dsn, operation_id="op-sbx", effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 5_000, "max_output_bytes": 65_536},
        allocation_id="a1", attempt_id="att1")
    status = broker.dispatch_operation(dsn, "op-sbx",
                                       launchers={"local-process": _ScriptLauncher()},
                                       ownership_generation=gen)
    assert status.dispatch_state == "observed"
    before = store.allocation_status(dsn, "a1")
    assert before["consumed"] > 0
    state = store.restart_reconciliation(dsn)
    after = store.allocation_status(dsn, "a1")
    assert after["consumed"] == before["consumed"]
    assert after["reserved"] == before["reserved"]
    assert all(op["id"] != "op-sbx" for op in state["unfinished_operations"])
