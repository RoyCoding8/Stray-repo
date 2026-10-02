from __future__ import annotations

import hashlib
import json

import httpx

from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    ModelRequest,
    ModelResponse,
    RouteContract,
    Usage,
)
from settlement.gateway_http import HttpGatewayAdapter

REQUEST_ENDPOINT = "http://127.0.0.1:4999/v1"
RETURNED_ENDPOINT = "http://localhost:4000/v1"
EXPECTED_ROUTE = {
    "endpoint": REQUEST_ENDPOINT,
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
        operation_id="op-route-check",
    )


def _adapter(
    response_body: dict,
    expected_route: dict,
) -> tuple[HttpGatewayAdapter, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raw = json.dumps(response_body).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = HttpGatewayAdapter(
        endpoint=REQUEST_ENDPOINT,
        api_key="test-key",
        client=client,
        expected_route=expected_route,
    )
    return adapter, requests


def _response_body(**overrides: object) -> dict:
    body = {
        "endpoint": REQUEST_ENDPOINT,
        "model": EXPECTED_ROUTE["resolved_model"],
        "provider": EXPECTED_ROUTE["provider"],
        "tier": EXPECTED_ROUTE["tier"],
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    body.update(overrides)
    return body


def test_response_endpoint_cannot_authorize_different_request_endpoint() -> None:
    expected_route = {**EXPECTED_ROUTE, "endpoint": RETURNED_ENDPOINT}
    adapter, requests = _adapter(_response_body(endpoint=RETURNED_ENDPOINT), expected_route)

    result = adapter.infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.message == "gateway endpoint is not the frozen endpoint"
    assert result.retryable is False
    assert result.route_error == GatewayRouteError.ENDPOINT
    assert result.response_received is False
    assert requests == []


def test_incomplete_expected_route_is_refused_before_post() -> None:
    adapter, requests = _adapter(_response_body(), {})

    result = adapter.infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.route_error == GatewayRouteError.EXPECTED_ROUTE
    assert requests == []


def test_wrong_request_model_is_refused_before_post() -> None:
    adapter, requests = _adapter(_response_body(), EXPECTED_ROUTE)

    result = adapter.infer(
        ModelRequest(
            model="other/request-model",
            messages=({"role": "user", "content": "hello"},),
            max_output_tokens=16,
            deadline_ms=10_000,
            operation_id="op-route-model-check",
        )
    )

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.message == "requested model is not the frozen model"
    assert result.route_error == GatewayRouteError.REQUESTED_MODEL
    assert result.response_received is False
    assert requests == []


def test_matching_route_preserves_request_and_returned_metadata() -> None:
    adapter, _ = _adapter(_response_body(), EXPECTED_ROUTE)

    result = adapter.infer(_request())

    assert isinstance(result, ModelResponse)
    assert result.text == "hello"
    assert result.model_meta["response_received"] is True
    assert result.model_meta["endpoint"] == REQUEST_ENDPOINT
    assert result.model_meta["request_endpoint"] == REQUEST_ENDPOINT
    assert result.model_meta["returned_endpoint"] == REQUEST_ENDPOINT
    assert result.model_meta["model"] == EXPECTED_ROUTE["resolved_model"]
    assert result.model_meta["provider"] == EXPECTED_ROUTE["provider"]
    assert result.model_meta["tier"] == EXPECTED_ROUTE["tier"]
    assert "route_error" not in result.model_meta


def test_missing_returned_route_metadata_is_refused() -> None:
    body = _response_body()
    del body["provider"]
    adapter, _ = _adapter(body, EXPECTED_ROUTE)

    result = adapter.infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.retryable is False
    assert result.usage == Usage(
        input_tokens=3, output_tokens=2, provider_enforced_ceiling=None
    )
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is True
    assert result.response_status == 200
    assert result.response_digest == hashlib.sha256(
        json.dumps(body).encode()
    ).hexdigest()


def test_route_contract_is_available_to_preflight_callers() -> None:
    contract = RouteContract.from_mapping(EXPECTED_ROUTE)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {"data": [
            {"id": contract.requested_model,
             "pricing": {"prompt": 0, "completion": 0}},
            {"id": contract.resolved_model,
             "pricing": {"prompt": 0, "completion": 0}},
        ]}
        return httpx.Response(200, json=body)

    adapter = HttpGatewayAdapter(
        endpoint=REQUEST_ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=contract,
    )

    assert adapter.route_contract == contract
    assert adapter.preflight_route(contract) == EXPECTED_ROUTE
    assert [request.method for request in calls] == ["GET"]


def test_decoder_failure_preserves_status_and_digest() -> None:
    raw = b"{not json"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=REQUEST_ENDPOINT,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        route_mode="paid",
    )

    result = adapter.infer(_request())

    assert isinstance(result, GatewayError)
    assert result.message == "gateway returned non-JSON body"
    assert result.response_received is True
    assert result.response_status == 200
    assert result.response_digest == hashlib.sha256(raw).hexdigest()
    assert requests[0].method == "POST"
