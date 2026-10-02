from __future__ import annotations

import json

import httpx
import pytest

from experiments.ad01.live_construct import output_operation_id
from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    ModelRequest,
    ModelResponse,
)
from settlement.gateway_http import HttpGatewayAdapter

FROZEN_ENDPOINT = "http://localhost:4000/v1"
RETURNED_ENDPOINT = "http://127.0.0.1:4000/v1"
EXPECTED_ROUTE = {
    "endpoint": FROZEN_ENDPOINT,
    "requested_model": "vendor/request-model",
    "resolved_model": "vendor/resolved-model",
    "provider": "vendor",
    "tier": "free",
}


def _request() -> ModelRequest:
    return ModelRequest(
        model=EXPECTED_ROUTE["requested_model"],
        messages=({"role": "user", "content": "hello"},),
        max_output_tokens=16,
        deadline_ms=10_000,
        operation_id="op-round-namespace",
    )


def _catalog() -> dict:
    return {"data": [
        {"id": EXPECTED_ROUTE["requested_model"],
         "pricing": {"prompt": 0, "completion": 0}},
        {"id": EXPECTED_ROUTE["resolved_model"],
         "pricing": {"prompt": 0, "completion": 0}},
    ]}


def _adapter(endpoint: str, expected_route: dict, handler) -> tuple[
        HttpGatewayAdapter, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    adapter = HttpGatewayAdapter(
        endpoint=endpoint,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(record)),
        expected_route=expected_route,
    )
    return adapter, requests


def test_different_frozen_rounds_have_different_output_operation_ids() -> None:
    first = output_operation_id(
        "P1", "audit", 23, 1, round_run_id="freeze-run-one")
    second = output_operation_id(
        "P1", "audit", 23, 1, round_run_id="freeze-run-two")

    assert first != second


def test_resume_of_same_frozen_round_reuses_output_operation_id() -> None:
    first = output_operation_id(
        "P1", "audit", 23, 1, round_run_id="freeze-run-one")
    resumed = output_operation_id(
        "P1", "audit", 23, 1, round_run_id="freeze-run-one")

    assert first == resumed


def test_local_endpoint_aliases_compare_equal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=_catalog())
        body = {
            "endpoint": "http://[::1]:4000/v1",
            "model": EXPECTED_ROUTE["resolved_model"],
            "provider": EXPECTED_ROUTE["provider"],
            "tier": EXPECTED_ROUTE["tier"],
            "choices": [{"message": {"content": "hello"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }
        raw = json.dumps(body).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter, requests = _adapter(
        RETURNED_ENDPOINT, EXPECTED_ROUTE, handler)

    preflight = adapter.preflight_route(EXPECTED_ROUTE)
    response = adapter.infer(_request())

    assert preflight == EXPECTED_ROUTE
    assert isinstance(response, ModelResponse)
    assert response.text == "hello"
    assert [request.method for request in requests] == ["GET", "POST"]


def test_local_endpoint_alias_does_not_cross_ports() -> None:
    route = {**EXPECTED_ROUTE, "endpoint": "http://localhost:4001/v1"}
    adapter, requests = _adapter(
        FROZEN_ENDPOINT, route,
        lambda request: httpx.Response(200, json=_catalog()))

    result = adapter.preflight_route(route)

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.route_error is None
    assert requests == []


def test_local_endpoint_alias_does_not_cross_hosts() -> None:
    route = {**EXPECTED_ROUTE, "endpoint": "http://192.0.2.1:4000/v1"}
    adapter, requests = _adapter(
        FROZEN_ENDPOINT, route,
        lambda request: httpx.Response(200, json=_catalog()))

    result = adapter.infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.route_error == GatewayRouteError.ENDPOINT
    assert requests == []


def test_malformed_frozen_endpoint_fails_closed() -> None:
    route = {**EXPECTED_ROUTE, "endpoint": "not-a-url"}
    adapter, requests = _adapter(
        FROZEN_ENDPOINT, route,
        lambda request: httpx.Response(200, json=_catalog()))

    result = adapter.infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.route_error == GatewayRouteError.ENDPOINT
    assert requests == []


@pytest.mark.parametrize(("field", "value"), [
    ("model", "vendor/other-model"),
    ("provider", "other-provider"),
    ("tier", "paid"),
])
def test_endpoint_alias_does_not_alias_model_provider_or_tier(
        field: str, value: str) -> None:
    body = {
        "endpoint": FROZEN_ENDPOINT,
        "model": EXPECTED_ROUTE["resolved_model"],
        "provider": EXPECTED_ROUTE["provider"],
        "tier": EXPECTED_ROUTE["tier"],
        "choices": [{"message": {"content": "hello"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    body[field] = value
    raw = json.dumps(body).encode()
    adapter, _ = _adapter(
        FROZEN_ENDPOINT, EXPECTED_ROUTE,
        lambda request: httpx.Response(
            200, stream=httpx.ByteStream(raw)))

    result = adapter.infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is True
