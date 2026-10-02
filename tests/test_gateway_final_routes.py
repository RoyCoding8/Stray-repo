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


@pytest.mark.parametrize(
    "timeout_error",
    [
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.WriteTimeout("write timed out"),
        httpx.PoolTimeout("pool timed out"),
    ],
    ids=["connect", "read", "write", "pool"],
)
def test_client_timeout_is_typed_without_response_evidence(
    timeout_error: httpx.TimeoutException,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise timeout_error

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT, client=client, route_mode="paid")

    result = adapter.infer(request("op-client-timeout"))

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.TIMEOUT
    assert result.retryable is True
    assert result.message == (
        f"gateway {type(timeout_error).__name__.removesuffix('Timeout').lower()}"
        " timed out"
    )
    assert result.response_received is False
    assert result.response_status is None
    assert result.response_digest is None


def test_caller_deadline_is_honored_before_dispatch() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    from settlement import gateway_http

    original = gateway_http._responses_input

    def slow_input(messages):
        time.sleep(0.05)
        return original(messages)

    gateway_http._responses_input = slow_input
    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api="responses",
        route_mode="paid",
    )
    try:
        result = adapter.infer(ModelRequest(
            model="model",
            messages=({"role": "user", "content": "hello"},),
            max_output_tokens=16,
            deadline_ms=10,
            operation_id="op-pre-dispatch-deadline",
        ))
    finally:
        gateway_http._responses_input = original

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.TIMEOUT
    assert result.response_received is False
    assert result.response_status is None
    assert result.response_digest is None
    assert calls == []


def test_completed_response_late_at_deadline_keeps_evidence(
    monkeypatch,
) -> None:
    raw = json.dumps({
        "choices": [{"message": {"content": "late"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }).encode()
    class BlockingStream(httpx.SyncByteStream):
        def __iter__(self):
            time.sleep(0.015)
            yield raw

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=BlockingStream())

    from settlement import gateway_http

    real_sha256 = gateway_http.hashlib.sha256

    def slow_sha256(value):
        time.sleep(0.02)
        return real_sha256(value)

    monkeypatch.setattr(gateway_http.hashlib, "sha256", slow_sha256)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT, client=client, route_mode="paid")
    try:
        result = adapter.infer(ModelRequest(
            model="model",
            messages=({"role": "user", "content": "hello"},),
            max_output_tokens=16,
            # This test asserts a response *was* received and only the
            # attempt deadline then expired. That needs the deadline to
            # expire after the response lands, so the value has to clear
            # the work this fixture induces.
            #
            # It used to be 20ms, which is not clear of anything: the
            # stream sleeps 15ms and the patched sha256 sleeps 20ms, and
            # that sleep actually costs ~37ms, so the work is ~52ms and
            # the deadline sat inside it. The adapter is correct either
            # way - when the stream lands after expiry it takes the
            # `status is None` branch, returns TIMEOUT, and has no digest
            # to record, so `response_received` is honestly False - which
            # is what made this a coin flip rather than a failure.
            #
            # Chosen by measurement, not by reasoning: a sweep of
            # 20/22/24/26/28/30/35ms over 8 runs each gave 5/6/7/6/5/7/8,
            # and 35ms then held 20 of 20. I first tried 10ms, which
            # expires before any response exists (0/12) and 25ms and
            # 40ms, which are both still inside the ~52ms of work.
            deadline_ms=35,
            operation_id="op-late-complete-response",
        ))
    finally:
        client.close()

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.TIMEOUT
    assert result.message == "total attempt deadline exceeded"
    assert result.response_received is True
    assert result.response_status == 200
    assert result.response_digest == hashlib.sha256(raw).hexdigest()


def test_caller_deadline_controls_transport_budget() -> None:
    seen: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        raw = json.dumps({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT, client=client, route_mode="paid",
        timeout_connect_ms=5_000, timeout_read_ms=60_000,
        timeout_write_ms=7_000, timeout_total_ms=300_000,
    )
    try:
        adapter.infer(ModelRequest(
            model="model",
            messages=({"role": "user", "content": "hello"},),
            max_output_tokens=16,
            deadline_ms=20_000,
            operation_id="op-budget-arithmetic",
        ))
    finally:
        client.close()

    assert len(seen) == 1
    assert seen[0]["connect"] == 5.0
    assert seen[0]["write"] == 7.0
    assert seen[0]["pool"] == 5.0
    assert 19.9 < seen[0]["read"] <= 20.0


def test_gateway_total_timeout_caps_longer_caller_deadline() -> None:
    release = threading.Event()
    started = threading.Event()

    class BlockingStream(httpx.SyncByteStream):
        def __iter__(self):
            started.set()
            release.wait(2)
            yield b"{}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=BlockingStream())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT, client=client, route_mode="paid",
        timeout_total_ms=50,
    )
    try:
        began = time.monotonic()
        result = adapter.infer(ModelRequest(
            model="model",
            messages=({"role": "user", "content": "hello"},),
            max_output_tokens=16,
            deadline_ms=1_000,
            operation_id="op-total-timeout",
        ))
        elapsed = time.monotonic() - began
        assert started.wait(1)
    finally:
        release.set()
        client.close()

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.TIMEOUT
    assert result.message == "total attempt deadline exceeded"
    assert result.response_received is False
    assert result.response_status is None
    assert result.response_digest is None
    assert elapsed < 0.5


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
    """Usage survives a non-200, on either surface.

    No route pin: the responses surface cannot attest one, so a pin
    here would refuse before the wire and this would assert about a
    refusal rather than about the usage that came back.
    `tests/test_w1_responses_route_contract.py` covers the refusal.
    """
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
        route_mode="paid",
    )

    result = adapter.infer(request(f"op-non-200-{api}"))

    assert isinstance(result, GatewayError)
    assert result.usage == Usage(
        input_tokens=3, output_tokens=4, charge_units=7,
        charge_scale=1000, provider_enforced_ceiling=None, billed=True,
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
        route_mode="paid",
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
