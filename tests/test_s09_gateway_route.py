from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import httpx

from settlement.gateway import (
    GatewayError,
    GatewayRouteError,
    ModelRequest,
    ModelResponse,
    RouteContract,
)
from settlement.gateway_http import HttpGatewayAdapter

from scripts import s09_pilot as pilot

ENDPOINT = "http://127.0.0.1:4999/v1"
ROUTE = {
    "endpoint": ENDPOINT,
    "requested_model": "controlled",
    "resolved_model": "controlled",
    "provider": "controlled",
    "tier": "free",
}


def _request(operation_id: str) -> ModelRequest:
    return ModelRequest(
        model="controlled",
        messages=({"role": "user", "content": "probe"},),
        max_output_tokens=8,
        deadline_ms=5_000,
        operation_id=operation_id,
    )


def test_default_free_route_refuses_and_explicit_route_proceeds() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "id": "gen-controlled",
            "object": "chat.completion",
            "model": ROUTE["resolved_model"],
            "provider": ROUTE["provider"],
            # The frozen model is `controlled`, which carries no `:free`
            # suffix, so this explicit tier is the only free statement
            # on the body. The responses stub below has no such tier,
            # which is why it cannot establish a free route at all.
            "tier": ROUTE["tier"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        raw = json.dumps(body).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    default = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        route_mode="free",
    )
    refused = default.infer(_request("op-default-route"))
    assert isinstance(refused, GatewayError)
    assert refused.route_error == GatewayRouteError.EXPECTED_ROUTE
    assert refused.response_received is False
    assert calls == []

    explicit = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=RouteContract.from_mapping(ROUTE),
    )
    result = explicit.infer(_request("op-explicit-route"))
    assert isinstance(result, ModelResponse)
    assert result.text == "ok"
    assert [call.method for call in calls] == ["POST"]


def test_an_explicit_route_is_still_refused_on_the_responses_surface() -> None:
    """The other half of the explicit route, and the reason it is chat.

    This file used to serve a responses body carrying `provider` and
    `tier`, which is a body the OpenAI Responses API does not produce.
    The test then asserted that an explicit route proceeds there, which
    is true of the stub and false of the gateway. A frozen route names a
    `provider`, and the responses surface publishes no `provider` to
    compare, so the call is refused before the wire. See
    `tests/test_w1_responses_route_contract.py`.
    """
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "id": "resp-controlled",
            "object": "response",
            "status": "completed",
            "model": ROUTE["resolved_model"],
            "output": [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "ok"}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        raw = json.dumps(body).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api="responses",
        expected_route=RouteContract.from_mapping(ROUTE),
    )
    result = adapter.infer(_request("op-responses-route"))

    assert isinstance(result, GatewayError)
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is False
    assert calls == []


def test_controlled_pilot_gateway_dispatches_without_a_frozen_live_route() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(
                int(self.headers["Content-Length"])))
            assert payload["model"] == "controlled"
            body = json.dumps({
                "status": "completed",
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "ok"}]}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        adapter = pilot._http_gateway(
            "http://127.0.0.1:%d" % server.server_port)
        result = adapter.infer(_request("op-pilot-controlled"))
        assert isinstance(result, ModelResponse)
        assert result.text == "ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
