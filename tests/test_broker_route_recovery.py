from __future__ import annotations

from typing import Any

import pytest

from settlement import broker
from settlement.broker import DispatchStatus, LaunchOutcome, ReceiptProposal
from settlement.common import CommandResult, ResultCode
from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    ModelResponse,
    Usage,
)


class _BrokerStore:
    def __init__(self, operation_id: str = "op-route") -> None:
        self.operation_id = operation_id
        self.receipts: list[dict[str, Any]] = []
        self.deliveries: list[str] = []
        self.resets: list[CommandResult] = []
        self.admission_results: list[CommandResult] = []
        self.row = {
            "id": operation_id,
            "dispatch_state": "prepared",
            "reconcile_state": "none",
            "cancel_state": "none",
            "settled": False,
            "launcher_id": "gateway",
            "execution_version": "",
            "attempt_id": "att-route",
            "payload": {
                "effect": broker.MODEL_INFERENCE,
                "payload": {
                    "model": "vendor/request-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_output_tokens": 8,
                    "deadline_ms": 1_000,
                },
                "retries": 0,
                "budget_kind": "estimated-budget",
            },
        }

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(broker, "read_operation", self.read_operation)
        monkeypatch.setattr(broker.store, "operation_receipts", self.operation_receipts)
        monkeypatch.setattr(broker.store, "advance_dispatch", self.advance_dispatch)
        monkeypatch.setattr(broker.store, "admit_receipt", self.admit_receipt)
        monkeypatch.setattr(broker.store, "record_delivery", self.record_delivery)
        monkeypatch.setattr(broker.store, "reset_dispatch", self.reset_dispatch)
        monkeypatch.setattr(broker.store, "confirm_cancellation", self.confirm_cancellation)

    def read_operation(self, _dsn: str, operation_id: str) -> dict[str, Any] | None:
        if operation_id != self.operation_id:
            return None
        return self.row

    def operation_receipts(self, _dsn: str, operation_id: str) -> list[dict[str, Any]]:
        if operation_id != self.operation_id:
            return []
        return list(self.receipts)

    def advance_dispatch(self, _dsn: str, command) -> CommandResult:
        payload = command.payload
        if self.row["dispatch_state"] == "prepared":
            self.row["dispatch_state"] = "dispatching"
            self.row["launcher_id"] = payload["launcher_id"]
            self.row["payload"]["_dispatch_generation"] = 1
            return CommandResult(
                code=ResultCode.APPLIED,
                request_id=command.request_id,
                data={"dispatch_generation": 1},
            )
        return CommandResult(
            code=ResultCode.ALREADY_APPLIED,
            request_id=command.request_id,
            data={"dispatch_generation": 1},
        )

    def admit_receipt(self, _dsn: str, command) -> CommandResult:
        if self.admission_results:
            return self.admission_results.pop(0)
        payload = dict(command.payload)
        self.receipts.append(payload)
        outcome = payload["outcome"]
        self.row["dispatch_state"] = (
            "observed" if outcome in ("success", "failure") else "unresolved"
        )
        self.row["reconcile_state"] = "none" if outcome in ("success", "failure") else "unresolved"
        return CommandResult(
            code=ResultCode.APPLIED,
            request_id=command.request_id,
            data={"operation_id": payload["operation_id"], "conflict": False},
        )

    def record_delivery(self, _dsn: str, command) -> CommandResult:
        self.deliveries.append(command.payload["workflow_identity"])
        return CommandResult(code=ResultCode.APPLIED, request_id=command.request_id)

    def reset_dispatch(self, _dsn: str, command) -> CommandResult:
        result = CommandResult(
            code=ResultCode.APPLIED,
            request_id=command.request_id,
            data={"dispatch_generation": 2},
        )
        self.resets.append(result)
        return result

    def confirm_cancellation(self, _dsn: str, command) -> CommandResult:
        self.resets.append(
            CommandResult(
                code=ResultCode.APPLIED,
                request_id=command.request_id,
                data={"never_sent_proof": command.payload.get("never_sent_proof", False)},
            )
        )
        return self.resets[-1]


class _Gateway:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[str] = []

    def infer(self, request):
        self.calls.append(request.operation_id)
        return self.response


class _Launcher:
    launcher_id = "launcher-test"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self, proof: bool | None) -> None:
        self.proof = proof
        self.proof_calls: list[str] = []
        self.result: dict[str, Any] | None = None

    def prove_never_sent(self, operation_id: str) -> bool:
        self.proof_calls.append(operation_id)
        if isinstance(self.proof, Exception):
            raise self.proof
        return bool(self.proof)

    def prior_send(self, _operation_id: str) -> bool:
        return False

    def stop(self, _operation_id: str) -> bool:
        return False

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, _operation_id: str) -> bool:
        return False

    def read_result(self, _operation_id: str) -> dict[str, Any] | None:
        return self.result

    def dispatch(self, _op) -> LaunchOutcome:
        raise AssertionError("redispatch must be stubbed in this boundary test")


def _route_response() -> GatewayError:
    return GatewayError(
        GatewayErrorKind.PROTOCOL,
        "requested model is not the frozen model",
        False,
        "op-route",
        response_received=False,
        route_error=GatewayRouteError.REQUESTED_MODEL,
    )


def _provider_response() -> GatewayError:
    return GatewayError(
        GatewayErrorKind.TIMEOUT,
        "provider returned an error response",
        True,
        "op-route",
        usage=Usage(input_tokens=3, output_tokens=0, billed=False),
        response_received=True,
        response_status=504,
        response_digest="response-digest",
    )


def _identity_response() -> ModelResponse:
    return ModelResponse(
        "different-operation",
        "response text must survive",
        {"provider": "vendor"},
        Usage(input_tokens=3, output_tokens=2, billed=False),
        "stop",
    )


@pytest.mark.parametrize(
    ("response", "response_class", "outcome", "actual_cost"),
    [
        (None, "lost-response", "unknown", None),
        (_route_response(), "pre-send-route-refusal", "failure", 0),
        (_provider_response(), "observed-provider-failure", "failure", None),
        (_identity_response(), "identity-failure", "unknown", None),
    ],
)
def test_model_receipts_distinguish_route_and_response_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    response,
    response_class: str,
    outcome: str,
    actual_cost: int | None,
) -> None:
    fake_store = _BrokerStore()
    fake_store.install(monkeypatch)

    status = broker.dispatch_operation(
        "unused", "op-route", gateway=_Gateway(response), ownership_generation=1
    )

    assert status.sent_this_call is (response_class != "pre-send-route-refusal")
    assert len(fake_store.receipts) == 1
    receipt = fake_store.receipts[0]
    assert receipt["content"]["response_class"] == response_class
    assert receipt["outcome"] == outcome
    assert receipt.get("actual_cost") == actual_cost
    assert fake_store.deliveries == ["dispatch:op-route"]


def test_identity_failure_retains_exact_response_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _BrokerStore()
    fake_store.install(monkeypatch)

    broker.dispatch_operation(
        "unused", "op-route", gateway=_Gateway(_identity_response()), ownership_generation=1
    )

    content = fake_store.receipts[0]["content"]
    assert content["operation_id"] == "op-route"
    assert content["response_operation_id"] == "different-operation"
    assert content["text"] == "response text must survive"
    assert content["model_meta"] == {"provider": "vendor"}
    assert content["stop_reason"] == "stop"


def test_gateway_error_identity_failure_is_receipted(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _BrokerStore()
    fake_store.install(monkeypatch)
    response = GatewayError(
        GatewayErrorKind.PROTOCOL,
        "response belongs to another operation",
        False,
        "different-operation",
        response_received=True,
        response_status=200,
        response_digest="identity-digest",
    )

    broker.dispatch_operation(
        "unused", "op-route", gateway=_Gateway(response), ownership_generation=1
    )

    assert len(fake_store.receipts) == 1
    assert fake_store.receipts[0]["content"]["response_class"] == "identity-failure"
    assert fake_store.receipts[0]["content"]["response_digest"] == "identity-digest"


def test_reconcile_does_not_claim_or_deliver_refused_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.install(monkeypatch)
    launcher = _Launcher(proof=True)
    launcher.result = {"outcome": "success", "text": "recovered"}
    monkeypatch.setattr(broker.store, "reconcile_operation", lambda *_args: _refused())
    fake_store.admission_results = [
        CommandResult(
            code=ResultCode.INVALID_INPUT,
            request_id="receipt-refused",
            detail="receipt validation failed",
        )
    ]

    decision = broker.reconcile("unused", "op-route", {"launcher-test": launcher})

    assert decision.decision == "receipt-admission-refused"
    assert decision.detail == "receipt validation failed"
    assert decision.next == "retry-later"
    assert fake_store.deliveries == []


def test_sweep_keeps_outbox_open_after_reconcile_admission_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.install(monkeypatch)
    launcher = _Launcher(proof=True)
    launcher.result = {"outcome": "success", "text": "recovered"}
    fake_store.admission_results = [
        CommandResult(code=ResultCode.INVALID_INPUT, request_id="receipt-refused")
    ]
    monkeypatch.setattr(broker.store, "attempts_with_continuations", lambda _dsn: [])
    monkeypatch.setattr(broker, "scan_prepared", lambda *_args: [])
    monkeypatch.setattr(
        broker.store,
        "scan_outbox",
        lambda _dsn, _limit: [{"workflow_identity": "dispatch:op-route"}],
    )
    monkeypatch.setattr(
        broker.store,
        "claim_outbox",
        lambda _dsn, command: CommandResult(
            code=ResultCode.APPLIED, request_id=command.request_id, data={"delivered": False}
        ),
    )

    report = broker.sweep("unused", {"launcher-test": launcher}, wake=False)

    assert report.delivered == []
    assert fake_store.deliveries == []


def test_late_receipt_admission_failure_never_delivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["payload"]["_dispatch_generation"] = 2
    fake_store.install(monkeypatch)
    fake_store.admission_results = [
        CommandResult(code=ResultCode.INVALID_INPUT, request_id="primary-refused"),
        CommandResult(code=ResultCode.APPLIED, request_id="fence-admitted"),
    ]
    outcome = LaunchOutcome(
        sent=True,
        receipt=ReceiptProposal(
            receipt_identity="late-response",
            content={"text": "late"},
            outcome="success",
            provenance="gateway",
        ),
    )

    status = broker._finish_send("unused", "op-route", outcome, admitted_generation=1)

    assert status.sent_this_call is False
    assert status.next_decision == "needs-reconciliation"
    assert fake_store.deliveries == []


@pytest.mark.parametrize("proof", [None, False, OSError("durable proof unavailable")])
def test_reset_refuses_without_positive_launcher_proof(
    monkeypatch: pytest.MonkeyPatch, proof: bool | OSError | None
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.install(monkeypatch)
    launcher = _Launcher(proof)

    status = broker.redispatch_after_reset(
        "unused", "op-route", {"launcher-test": launcher}, expected_generation=1
    )

    assert status.dispatch_state == "dispatching"
    assert status.sent_this_call is False
    assert status.next_decision == "refused-never-sent-proof"
    assert fake_store.resets == []
    assert launcher.proof_calls == ["op-route"]


def test_reset_calls_store_only_after_positive_launcher_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.install(monkeypatch)
    launcher = _Launcher(proof=True)
    expected = DispatchStatus(
        operation_id="op-route", dispatch_state="observed", sent_this_call=True
    )
    monkeypatch.setattr(broker, "dispatch_operation", lambda *_args, **_kwargs: expected)

    status = broker.redispatch_after_reset(
        "unused", "op-route", {"launcher-test": launcher}, expected_generation=1
    )

    assert status is expected
    assert launcher.proof_calls == ["op-route"]
    assert len(fake_store.resets) == 1


def test_cancellation_exposure_release_requires_launcher_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.install(monkeypatch)

    refused = broker.confirm_cancel("unused", "op-route", {"launcher-test": _Launcher(False)})
    allowed = broker.confirm_cancel("unused", "op-route", {"launcher-test": _Launcher(True)})

    assert refused.data["never_sent_proof"] is False
    assert allowed.data["never_sent_proof"] is True


def test_cancellation_never_releases_over_an_existing_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "unresolved"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.receipts = [{"outcome": "unknown", "content": {"lost": True}}]
    fake_store.install(monkeypatch)
    launcher = _Launcher(proof=True)

    result = broker.confirm_cancel("unused", "op-route", {"launcher-test": launcher})

    assert result.data["never_sent_proof"] is False
    assert launcher.proof_calls == []


def test_workflow_retries_use_distinct_operations_with_single_attempt_exposure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from settlement import run as runmod

    captured: list[dict[str, Any]] = []
    monkeypatch.setitem(
        broker.ATTEMPT_WORKFLOW_RESOURCES,
        "att-route",
        {"launchers": {}, "gateway": None},
    )
    monkeypatch.setattr(
        runmod,
        "operation_outcome",
        lambda *_args: {"found": False, "outcome": "unknown", "dispatch_state": "unknown"},
    )

    def ensure(_dsn, **kwargs):
        captured.append(kwargs)
        return CommandResult(code=ResultCode.APPLIED, request_id="prepared")

    monkeypatch.setattr(broker, "ensure_operation", ensure)
    monkeypatch.setattr(
        broker,
        "dispatch_operation",
        lambda *_args, **_kwargs: DispatchStatus(
            operation_id="op-route", dispatch_state="observed", sent_this_call=True
        ),
    )

    broker.wf_ensure_dispatch(
        "unused",
        {
            "operation_id": "op-route",
            "effect": broker.MODEL_INFERENCE,
            "payload": {
                "model": "m1",
                "messages": [{"role": "user", "content": "hello"}],
                "max_output_tokens": 8,
            },
            "allocation_id": "a1",
        },
        3,
        1,
        "node",
        "att-route",
    )

    assert captured[0]["retries"] == 0


def test_broker_refuses_retry_multiplier_it_does_not_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = []
    monkeypatch.setattr(broker.store, "prepare_operation", lambda *_args: prepared.append(_args))

    result = broker.ensure_operation(
        "unused",
        operation_id="op-route",
        effect=broker.MODEL_INFERENCE,
        payload={
            "model": "m1",
            "messages": [{"role": "user", "content": "hello"}],
            "max_output_tokens": 8,
        },
        allocation_id="a1",
        retries=1,
    )

    assert result.code == ResultCode.INVALID_INPUT
    assert result.detail == "retries must be zero; use distinct operation identities"
    assert prepared == []


def _refused() -> CommandResult:
    return CommandResult(code=ResultCode.INVALID_INPUT, request_id="unused")
