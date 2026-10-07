from __future__ import annotations

import sys

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
    assert fake_store.deliveries == ([] if outcome == "unknown" else ["dispatch:op-route"])


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
    fake_store.row["payload"]["_dispatch_generation"] = 1
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
    fake_store.row["payload"]["_dispatch_generation"] = 1
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
    fake_store.row["payload"]["_dispatch_generation"] = 1
    fake_store.install(monkeypatch)

    refused = broker.confirm_cancel("unused", "op-route", {"launcher-test": _Launcher(False)})
    allowed = broker.confirm_cancel("unused", "op-route", {"launcher-test": _Launcher(True)})

    assert refused.data["never_sent_proof"] is False
    assert allowed.data["never_sent_proof"] == {
        "claim": "never-sent",
        "subject": "op-route",
        "provenance": "launcher-test:prove_never_sent",
        "dispatch_generation": 1,
    }


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


def test_unknown_model_receipt_is_not_delivered_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.install(monkeypatch)

    status = broker.dispatch_operation(
        "unused", "op-route", gateway=_Gateway(None), ownership_generation=1
    )

    assert status.dispatch_state == "unresolved"
    assert status.next_decision == "needs-reconciliation"
    assert fake_store.deliveries == []


def test_settlement_refusal_is_not_reported_as_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.admission_results = [CommandResult(
        code=ResultCode.APPLIED,
        request_id="cost-refused",
        data={"settlement_refused": "actual cost conflicts with usage charge_units"},
    )]
    fake_store.install(monkeypatch)
    response = ModelResponse(
        "op-route",
        "answer",
        {"provider": "vendor"},
        Usage(input_tokens=1, output_tokens=1, charge_units=3, billed=True),
        "stop",
    )

    status = broker.dispatch_operation(
        "unused", "op-route", gateway=_Gateway(response), ownership_generation=1
    )

    assert status.dispatch_state == "dispatching"
    assert status.next_decision == "receipt-admission-refused"
    assert fake_store.deliveries == []


def test_reconcile_unknown_result_is_not_reported_as_receipt_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.install(monkeypatch)
    launcher = _Launcher(proof=True)
    launcher.result = {"outcome": "unknown", "text": "not received"}

    decision = broker.reconcile("unused", "op-route", {"launcher-test": launcher})

    assert decision.decision == "unresolved-liability"
    assert decision.next == "retry-later"
    assert fake_store.deliveries == []


def test_reset_passes_generation_bound_structured_never_sent_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.row["payload"]["_dispatch_generation"] = 4
    fake_store.install(monkeypatch)
    commands: list[dict[str, Any]] = []
    monkeypatch.setattr(
        broker.store,
        "reset_dispatch",
        lambda _dsn, command: commands.append(command.payload) or CommandResult(
            code=ResultCode.APPLIED, request_id=command.request_id,
            data={"dispatch_generation": 5},
        ),
    )
    launcher = _Launcher(proof=True)
    monkeypatch.setattr(
        broker,
        "dispatch_operation",
        lambda *_args, **_kwargs: DispatchStatus(
            operation_id="op-route", dispatch_state="observed", sent_this_call=True
        ),
    )

    status = broker.redispatch_after_reset(
        "unused", "op-route", {"launcher-test": launcher}, expected_generation=4
    )

    assert status.sent_this_call is True
    assert commands[0]["never_sent_proof"] == {
        "claim": "never-sent",
        "subject": "op-route",
        "provenance": "launcher-test:prove_never_sent",
        "dispatch_generation": 4,
    }


def test_cancellation_passes_generation_bound_structured_never_sent_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["launcher_id"] = "launcher-test"
    fake_store.row["payload"]["_dispatch_generation"] = 2
    fake_store.install(monkeypatch)

    result = broker.confirm_cancel("unused", "op-route", {"launcher-test": _Launcher(proof=True)})

    assert result.data["never_sent_proof"] == {
        "claim": "never-sent",
        "subject": "op-route",
        "provenance": "launcher-test:prove_never_sent",
        "dispatch_generation": 2,
    }


def test_workflow_replay_never_calls_dispatch_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from settlement import run as runmod

    monkeypatch.setitem(
        broker.ATTEMPT_WORKFLOW_RESOURCES,
        "att-route",
        {"launchers": {}, "gateway": None},
    )
    monkeypatch.setattr(
        runmod,
        "operation_outcome",
        lambda *_args: {
            "found": True,
            "outcome": "success",
            "dispatch_state": "observed",
        },
    )
    prepared: list[dict[str, Any]] = []

    def record_ensure(_dsn: str, **kwargs: Any) -> CommandResult:
        prepared.append(kwargs)
        return CommandResult(
            code=ResultCode.ALREADY_APPLIED,
            request_id="replayed",
            detail="operation already prepared",
            data={},
        )

    monkeypatch.setattr(broker, "ensure_operation", record_ensure)
    monkeypatch.setattr(
        broker,
        "dispatch_operation",
        lambda *_args, **_kwargs: pytest.fail("replay must not dispatch"),
    )

    op_args = {
        "operation_id": "op-route",
        "effect": broker.MODEL_INFERENCE,
        "payload": {
            "model": "m1",
            "messages": [{"role": "user", "content": "hello"}],
            "max_output_tokens": 8,
        },
        "allocation_id": "a1",
    }
    summary = broker.wf_ensure_dispatch(
        "unused",
        op_args,
        1,
        1,
        "node",
        "att-route",
    )

    assert summary["next_decision"] == "already-replayed"
    assert summary["replay"] is True
    assert len(prepared) == 1
    assert prepared[0] == {
        "operation_id": op_args["operation_id"],
        "effect": op_args["effect"],
        "payload": op_args["payload"],
        "allocation_id": op_args["allocation_id"],
        "attempt_id": None,
        "execution_version": "",
        "retries": 0,
    }


def test_workflow_does_not_advance_from_observed_status_without_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from settlement import run as runmod

    composition = {
        "version": "run/v1",
        "revision": 1,
        "allocation_id": "a1",
        "authority_version": 1,
        "root": {
            "kind": "invoke",
            "node_id": "n1",
            "effect": "sandbox-exec",
            "payload": {
                "profile": "local-process",
                "argv": [sys.executable, "-c", "pass"],
                "timeout_ms": 5_000,
                "max_output_bytes": 1_024,
            },
        },
    }
    continuation = runmod.fresh_continuation(
        runmod.Composition.model_validate(composition), "att-route"
    ).model_dump(mode="json")
    monkeypatch.setattr(
        runmod,
        "operation_outcome",
        lambda *_args: {"found": False, "outcome": "unknown", "dispatch_state": "unknown"},
    )
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        runmod,
        "record_continuation",
        lambda _dsn, _attempt, cont, _ref, _generation: recorded.append(cont) or
        CommandResult(code=ResultCode.APPLIED, request_id="recorded"),
    )

    result = broker.wf_record(
        "unused",
        "att-route",
        composition,
        continuation,
        {"node_id": "n1", "operation_id": "op-route", "dispatch_state": "observed"},
        "workflow:r1",
    )

    assert result["completed"] == {}
    assert result["unresolved_ops"] == ["n1:op-route"]


def test_receipt_identity_mismatch_is_refused_before_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "dispatching"
    fake_store.row["payload"]["_dispatch_generation"] = 1
    fake_store.install(monkeypatch)

    result = broker.admit_launcher_receipt(
        "unused",
        "op-route",
        ReceiptProposal(
            receipt_identity="forged-response",
            content={
                "operation_id": "op-route",
                "response_operation_id": "other-operation",
                "response_class": "observed-provider-failure",
            },
            outcome="failure",
            provenance="gateway",
        ),
    )

    assert result.code == ResultCode.INVALID_INPUT
    assert fake_store.receipts == []


def test_delivery_refusal_does_not_report_send_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _BrokerStore()
    fake_store.row["dispatch_state"] = "observed"
    fake_store.row["payload"]["_dispatch_generation"] = 1
    fake_store.install(monkeypatch)
    monkeypatch.setattr(
        broker.store,
        "record_delivery",
        lambda _dsn, _command: CommandResult(
            code=ResultCode.INVALID_INPUT, request_id="delivery-refused"
        ),
    )

    status = broker._finish_send(
        "unused",
        "op-route",
        LaunchOutcome(
            sent=True,
            receipt=ReceiptProposal(
                receipt_identity="fake:op-route",
                content={"ok": True},
                outcome="success",
                provenance="fake",
            ),
        ),
        admitted_generation=1,
    )

    assert status.sent_this_call is True
    assert status.next_decision == "needs-reconciliation"
    assert fake_store.deliveries == []


def test_workflow_finish_waits_when_store_refuses_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import inspect
    from types import SimpleNamespace

    from settlement import run as runmod

    composition = runmod.Composition.model_validate({
        "version": "run/v1",
        "revision": 1,
        "allocation_id": "a1",
        "authority_version": 1,
        "root": {"kind": "sequence", "node_id": "root", "steps": []},
    })
    continuation = runmod.fresh_continuation(composition, "att-finish")
    monkeypatch.setattr(
        broker,
        "wf_snapshot",
        lambda *_args: {
            "lifecycle": "running",
            "continuation": continuation.model_dump(mode="json"),
        },
    )
    monkeypatch.setattr(
        broker,
        "wf_finish",
        lambda *_args: {
            "code": "missing_evidence",
            "detail": "attempt has unresolved operation op",
        },
    )
    monkeypatch.setattr(
        broker,
        "DBOS",
        SimpleNamespace(run_step=lambda _ctx, fn, *args: fn(*args)),
    )

    result = inspect.unwrap(broker.attempt_workflow)(
        "unused", "att-finish", 1, composition.model_dump(mode="json"), 2
    )

    assert result["outcome"] == "waiting"
    assert result["finish"]["code"] == "missing_evidence"


def _refused() -> CommandResult:
    return CommandResult(code=ResultCode.INVALID_INPUT, request_id="unused")
