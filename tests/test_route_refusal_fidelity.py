from __future__ import annotations

from types import SimpleNamespace

from scripts import invl02_live
from settlement.common import ResultCode
from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    ModelRequest,
)


ROUTE = {
    "endpoint": "http://gateway.test/v1",
    "requested_model": "provider/frozen-model",
    "resolved_model": "frozen-model",
    "provider": "frozen-provider",
    "tier": "frozen-tier",
}
OPERATION_ID = "route-refusal-fidelity"


def _infer(monkeypatch, receipt, *, already_applied=False):
    from settlement import broker, store

    monkeypatch.setattr(
        broker,
        "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.ALREADY_APPLIED if already_applied else ResultCode.APPLIED,
            data={"reservation_id": "reservation-1", "exposure": 0}),
    )
    monkeypatch.setattr(
        broker,
        "read_operation",
        lambda *args, **kwargs: {
            "reservation_id": "reservation-1",
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "settled": True,
        },
    )
    monkeypatch.setattr(
        broker,
        "dispatch_operation",
        lambda *args, **kwargs: SimpleNamespace(
            dispatch_state="observed",
            reconcile_state="none",
            settled=True,
            next_decision="terminal",
        ),
    )
    monkeypatch.setattr(
        store,
        "operation_receipts",
        lambda *args, **kwargs: [receipt],
    )
    monkeypatch.setattr(
        store,
        "operation_receipt_conflicts",
        lambda *args, **kwargs: [],
    )
    durable = invl02_live._DurableBrokerOutput(
        "unused",
        object(),
        allocation_id="allocation-1",
        expected_route=ROUTE,
    )
    request = ModelRequest(
        model=ROUTE["requested_model"],
        messages=({"role": "user", "content": "input"},),
        max_output_tokens=2048,
        deadline_ms=1000,
        operation_id=OPERATION_ID,
    )
    return durable.infer(request)


def _receipt(**content):
    return {
        "receipt_identity": "gw:route-refusal",
        "outcome": "failure",
        "content": {
            "error": "route response refused",
            "error_kind": GatewayErrorKind.PROTOCOL.value,
            "retryable": False,
            "response_received": True,
            "response_status": 200,
            "response_digest": "receipt-digest",
            "route_error": GatewayRouteError.RESPONSE_METADATA.value,
            "usage": {
                "input_tokens": 2,
                "output_tokens": 0,
                "charge_units": 0,
                "charge_scale": 100,
                "billed": False,
            },
            **content,
        },
    }


def test_route_receipt_fields_become_gateway_error(monkeypatch):
    receipt = _receipt()

    result = _infer(monkeypatch, receipt)

    assert type(result) is GatewayError
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is True
    assert result.response_status == 200
    assert result.response_digest == "receipt-digest"


def test_replayed_route_receipt_preserves_fields(monkeypatch):
    receipt = _receipt()

    result = _infer(monkeypatch, receipt, already_applied=True)

    assert type(result) is GatewayError
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is True
    assert result.response_status == 200
    assert result.response_digest == "receipt-digest"


def test_non_route_message_does_not_change_structured_route_field(monkeypatch):
    receipt = _receipt(
        error="route message without structured route refusal",
        route_error=None,
    )

    result = _infer(monkeypatch, receipt)

    assert type(result) is GatewayError
    assert result.route_error is None


def test_pre_send_refusal_is_not_reported_as_observed_success(monkeypatch):
    receipt = _receipt(
        response_received=False,
        response_status=None,
        response_digest=None,
    )
    receipt["receipt_identity"] = "gw:pre-send-route-refusal"

    result = _infer(monkeypatch, receipt)

    assert type(result) is GatewayError
    assert result.response_received is False
    assert result.response_status is None


def test_failure_error_never_carries_frozen_route_metadata(monkeypatch):
    receipt = _receipt(
        provider="observed-provider",
        tier="observed-tier",
    )

    result = _infer(monkeypatch, receipt)

    assert type(result) is GatewayError
    assert not hasattr(result, "model_meta")
    assert ROUTE["provider"] not in str(result)
    assert ROUTE["tier"] not in str(result)
