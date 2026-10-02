from __future__ import annotations

import hashlib
import json
import threading
import time

import httpx
import pytest

from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    ModelRequest,
    Usage,
)
from settlement.gateway_http import HttpGatewayAdapter

ENDPOINT = "http://127.0.0.1:4999/v1"
ROUTE = {
    "endpoint": ENDPOINT,
    "requested_model": "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "resolved_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "nvidia",
    "tier": "free",
}


def request(operation_id: str = "op-final-route") -> ModelRequest:
    return ModelRequest(
        model=ROUTE["requested_model"],
        messages=({"role": "user", "content": "hello"},),
        max_output_tokens=16,
        deadline_ms=10_000,
        operation_id=operation_id,
    )


def test_direct_infer_without_expected_route_refuses_before_post() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raw = json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.infer(request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.route_error == GatewayRouteError.EXPECTED_ROUTE
    assert result.response_received is False
    assert calls == []


def test_free_mode_refuses_paid_expected_route_before_post() -> None:
    calls: list[httpx.Request] = []
    paid_route = {**ROUTE, "tier": "paid"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raw = json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=paid_route,
    )

    result = adapter.infer(request())

    assert isinstance(result, GatewayError)
    assert result.route_error == GatewayRouteError.EXPECTED_ROUTE
    assert calls == []


def test_explicit_paid_mode_allows_unconstrained_inference() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raw = json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        route_mode="paid",
    )

    result = adapter.infer(request("op-explicit-paid"))

    assert not isinstance(result, GatewayError)
    assert calls[0].method == "POST"


def test_preflight_route_refusal_preserves_response_evidence() -> None:
    raw = json.dumps({"data": []}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=ROUTE,
    )

    result = adapter.preflight_route(ROUTE)

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.response_received is True
    assert result.response_status == 200
    assert result.response_digest == hashlib.sha256(raw).hexdigest()


def test_preflight_transport_refusal_has_no_response_evidence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=ROUTE,
    )

    result = adapter.preflight_route(ROUTE)

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.TRANSPORT
    assert result.response_received is False
    assert result.response_status is None
    assert result.response_digest is None


def test_preflight_http_refusal_retains_status_and_digest() -> None:
    raw = b"upstream refused"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=ROUTE,
    )

    result = adapter.preflight_route(ROUTE)

    assert isinstance(result, GatewayError)
    assert result.response_received is True
    assert result.response_status == 503
    assert result.response_digest == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("api", ["chat", "responses"])
def test_non_200_response_preserves_received_usage_and_charge(api: str) -> None:
    usage = {
        "prompt_tokens" if api == "chat" else "input_tokens": 3,
        "completion_tokens" if api == "chat" else "output_tokens": 4,
        "charge_units": 7,
        "charge_scale": 1000,
        "billed": True,
    }
    body = (
        {"choices": [{"message": {"content": "refused"}}], "usage": usage}
        if api == "chat"
        else {"status": "failed", "error": {"message": "refused"}, "usage": usage}
    )
    raw = json.dumps(body).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api=api,
        expected_route=ROUTE,
    )

    result = adapter.infer(request(f"op-non-200-{api}"))

    assert isinstance(result, GatewayError)
    assert result.usage == Usage(
        input_tokens=3, output_tokens=4, charge_units=7,
        charge_scale=1000, billed=True,
    )
    assert result.response_received is True
    assert result.response_status == 400
    assert result.response_digest == hashlib.sha256(raw).hexdigest()


def test_local_cancellation_is_worker_stopped_not_provider_confirmed() -> None:
    started = threading.Event()

    class BlockingStream(httpx.SyncByteStream):
        def __iter__(self):
            started.set()
            yield b"{"
            time.sleep(1)
            yield b"}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=BlockingStream())

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=ROUTE,
    )
    operation_id = "op-local-cancel"
    outcome: list[GatewayError] = []
    worker = threading.Thread(
        target=lambda: outcome.append(adapter.infer(request(operation_id))),
        daemon=True,
    )
    worker.start()
    assert started.wait(2)
    adapter.cancel(operation_id)
    worker.join(2)

    assert not worker.is_alive()
    assert isinstance(outcome[0], GatewayError)
    assert outcome[0].kind == GatewayErrorKind.CANCELLED
    assert adapter.cancel_status(operation_id) == "worker_stopped"


def test_provider_cancellation_response_is_external_confirmation() -> None:
    body = {
        "status": "cancelled",
        "usage": {"input_tokens": 1, "output_tokens": 0, "billed": False},
    }
    raw = json.dumps(body).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api="responses",
        expected_route=ROUTE,
    )
    operation_id = "op-provider-cancelled"

    result = adapter.infer(request(operation_id))

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.CANCELLED
    assert result.response_received is True
    assert result.response_status == 200
    assert result.response_digest == hashlib.sha256(raw).hexdigest()
    assert adapter.cancel_status(operation_id) == "confirmed"


def test_precancelled_operation_remains_requested() -> None:
    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(500, stream=httpx.ByteStream(b"unused"))
        )),
        expected_route=ROUTE,
    )
    operation_id = "op-requested-cancel"
    adapter.cancel(operation_id)

    result = adapter.infer(request(operation_id))

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.CANCELLED
    assert adapter.cancel_status(operation_id) == "requested"
