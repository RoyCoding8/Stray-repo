from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    ModelRequest,
    ModelResponse,
    Usage,
)
from settlement.gateway_http import HttpGatewayAdapter

_MISSING = object()


def _response_body(api: str, usage: object) -> dict[str, Any]:
    if api == "chat":
        body: dict[str, Any] = {
            "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}],
        }
    else:
        body = {
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "answer"}],
            }],
        }
    if usage is not _MISSING:
        body["usage"] = usage
    return body


def _gateway(api: str, usage: object) -> HttpGatewayAdapter:
    body = json.dumps(_response_body(api, usage)).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(body))

    return HttpGatewayAdapter(
        endpoint="http://127.0.0.1:4999/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api=api,
        route_mode="paid",
    )


def _usage(
    api: str, input_tokens: object, output_tokens: int, **charge: object,
) -> dict[str, object]:
    input_key = "prompt_tokens" if api == "chat" else "input_tokens"
    output_key = "completion_tokens" if api == "chat" else "output_tokens"
    return {input_key: input_tokens, output_key: output_tokens, **charge}


def _request(api: str) -> ModelRequest:
    return ModelRequest(
        model="probe",
        messages=({"role": "user", "content": "hi"},),
        max_output_tokens=8,
        deadline_ms=10_000,
        operation_id=f"public-{api}",
    )


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_public_missing_usage_is_explicitly_unknown(api):
    result = _gateway(api, _MISSING).infer(_request(api))

    assert isinstance(result, ModelResponse)
    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert result.usage.charge_units is None
    assert result.usage.billed is None


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_public_absent_billed_stays_unknown_even_with_charge_units(api):
    result = _gateway(
        api, _usage(api, 5, 3, charge_units=7)).infer(_request(api))

    assert isinstance(result, ModelResponse)
    assert result.usage.charge_units == 7
    assert result.usage.billed is None


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_public_explicit_billed_boolean_is_preserved(api):
    result = _gateway(
        api, _usage(api, 5, 3, charge_units=0, charge_scale=1000, billed=False)
    ).infer(_request(api))

    assert isinstance(result, ModelResponse)
    assert result.usage.charge_units == 0
    assert result.usage.charge_scale == 1000
    assert result.usage.billed is False


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_public_malformed_usage_preserves_partial_evidence(api):
    result = _gateway(
        api, _usage(api, "five", 3, charge_units=7, billed=True)).infer(_request(api))

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.usage == Usage(
        output_tokens=3, charge_units=7, charge_scale=1000, billed=True)


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_public_explicit_zero_charge_is_measured_zero(api):
    result = _gateway(
        api, _usage(api, 5, 3, charge_units=0, billed=True)).infer(_request(api))

    assert isinstance(result, ModelResponse)
    assert result.usage == Usage(
        input_tokens=5, output_tokens=3, charge_units=0,
        charge_scale=1000, billed=True)


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_public_nonzero_charge_units_are_preserved(api):
    result = _gateway(
        api, _usage(api, 5, 3, charge_units=7, billed=True)).infer(_request(api))

    assert isinstance(result, ModelResponse)
    assert result.usage == Usage(
        input_tokens=5, output_tokens=3, charge_units=7,
        charge_scale=1000, billed=True)


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_noncanonical_charge_scale_is_refused_before_settlement(api):
    result = _gateway(
        api, _usage(api, 5, 3, charge_units=7, charge_scale=7, billed=True)
    ).infer(_request(api))

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.usage == Usage(
        input_tokens=5, output_tokens=3, charge_units=7,
        charge_scale=7, billed=True)


def _prepare(dsn: str, operation_id: str) -> int:
    allocation_id = f"alloc-{operation_id}"
    seeded = store.seed_allocation(dsn, Command(
        request_id=f"seed-{operation_id}",
        payload={"allocation_id": allocation_id, "domain": "cpu", "authorized": 100},
    ))
    assert seeded.code == ResultCode.APPLIED
    prepared = broker.ensure_operation(
        dsn,
        operation_id=operation_id,
        effect=broker.MODEL_INFERENCE,
        payload={
            "model": "probe",
            "messages": [{"role": "user", "content": "hi"}],
            "max_output_tokens": 8,
            "deadline_ms": 10_000,
        },
        allocation_id=allocation_id,
    )
    assert prepared.code == ResultCode.APPLIED
    return int(prepared.data["exposure"])


def _dispatch(dsn: str, api: str, case: str, usage: object):
    operation_id = f"usage-{api}-{case}"
    exposure = _prepare(dsn, operation_id)
    gateway = _gateway(api, usage)
    status = broker.dispatch_operation(dsn, operation_id, gateway=gateway)
    receipts = store.operation_receipts(dsn, operation_id)
    assert len(receipts) == 1
    return status, receipts[0], store.allocation_status(
        dsn, f"alloc-{operation_id}"), exposure


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_missing_usage_stays_unknown_and_conserves_exposure(api, migrated_db):
    status, receipt, ledger, exposure = _dispatch(
        migrated_db, api, "missing", _MISSING)

    assert status.dispatch_state == "observed"
    assert receipt["outcome"] == "success"
    assert receipt["content"]["usage"]["input_tokens"] is None
    assert receipt["content"]["usage"]["output_tokens"] is None
    assert receipt["content"]["usage"]["charge_units"] is None
    assert receipt["content"]["usage"]["billed"] is None
    assert (ledger["consumed"], ledger["reserved"]) == (exposure, 0)


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_malformed_usage_preserves_partial_evidence_and_reservation(api, migrated_db):
    status, receipt, ledger, exposure = _dispatch(
        migrated_db, api, "malformed",
        _usage(api, "five", 3, charge_units=7, billed=True))

    assert status.dispatch_state == "unresolved"
    assert receipt["outcome"] == "unknown"
    assert receipt["content"]["usage"]["input_tokens"] is None
    assert receipt["content"]["usage"]["output_tokens"] == 3
    assert receipt["content"]["usage"]["charge_units"] == 7
    assert receipt["content"]["usage"]["billed"] is True
    assert (ledger["consumed"], ledger["reserved"]) == (0, exposure)


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_noncanonical_scale_does_not_settle_provider_charge(api, migrated_db):
    status, receipt, ledger, exposure = _dispatch(
        migrated_db, api, "noncanonical",
        _usage(api, 5, 3, charge_units=7, charge_scale=7, billed=True))

    assert status.dispatch_state == "unresolved"
    assert receipt["outcome"] == "unknown"
    assert receipt["content"]["usage"]["charge_units"] == 7
    assert receipt["content"]["usage"]["charge_scale"] == 7
    assert (ledger["consumed"], ledger["reserved"]) == (0, exposure)


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_explicit_zero_charge_is_measured_zero(api, migrated_db):
    status, receipt, ledger, _ = _dispatch(
        migrated_db, api, "zero", _usage(api, 5, 3, charge_units=0, billed=True))

    assert status.dispatch_state == "observed"
    assert receipt["outcome"] == "success"
    assert receipt["content"]["usage"]["input_tokens"] == 5
    assert receipt["content"]["usage"]["output_tokens"] == 3
    assert receipt["content"]["usage"]["charge_units"] == 0
    assert receipt["content"]["usage"]["billed"] is True
    assert (ledger["consumed"], ledger["reserved"]) == (0, 0)


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_nonzero_charge_units_settle_exact_provider_charge(api, migrated_db):
    status, receipt, ledger, _ = _dispatch(
        migrated_db, api, "charge",
        _usage(api, 5, 3, charge_units=7, billed=True))

    assert status.dispatch_state == "observed"
    assert receipt["outcome"] == "success"
    assert receipt["content"]["usage"]["input_tokens"] == 5
    assert receipt["content"]["usage"]["output_tokens"] == 3
    assert receipt["content"]["usage"]["charge_units"] == 7
    assert receipt["content"]["usage"]["billed"] is True
    assert (ledger["consumed"], ledger["reserved"]) == (7, 0)
