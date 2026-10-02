from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from settlement.gateway import (
    FakeGatewayAdapter,
    GatewayError,
    GatewayErrorKind,
    GatewayStatus,
    ModelRequest,
    ModelResponse,
)


class StubState:
    mode = "ok"
    posts = 0
    last_auth = ""


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.server.state.last_auth = self.headers.get("Authorization", "")
        if self.path == "/models":
            if self.server.state.mode == "unauthorized":
                return self._send(401, {"error": "bad key"})
            return self._send(200, {"data": [{"id": "stub-model"}]})
        return self._send(404, {"error": "nope"})

    def do_POST(self):
        state = self.server.state
        state.posts += 1
        state.last_auth = self.headers.get("Authorization", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        if state.mode == "sleep":
            import time

            time.sleep(5)
        if state.mode == "rate_limited":
            return self._send(429, {"error": "slow down"})
        if state.mode == "unauthorized":
            return self._send(401, {"error": "bad key"})
        if state.mode == "server_error":
            return self._send(500, {"error": "boom"})
        if state.mode == "bad_json":
            raw = b"{not json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        if state.mode == "empty_choices":
            return self._send(200, {"usage": {"prompt_tokens": 1, "completion_tokens": 1}})
        request = json.loads(body)
        if "messages" not in request or "model" not in request:
            return self._send(400, {"error": "bad request"})
        return self._send(
            200,
            {
                "choices": [{"message": {"content": "stub-answer"}, "finish_reason": "stop"}],
                "model": "stub-model",
                "usage": {"prompt_tokens": 7, "completion_tokens": 5},
            },
        )


@pytest.fixture()
def stub():
    from settlement import gateway_http

    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    server.state = StubState()
    server.state.mode = "ok"
    server.state.posts = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    adapter = gateway_http.HttpGatewayAdapter(endpoint=endpoint, api_key="test-key")
    yield adapter, server.state
    server.shutdown()
    thread.join()


def _request(**overrides):
    args = {
        "model": "stub-model",
        "messages": ({"role": "user", "content": "hi"},),
        "max_output_tokens": 16,
        "deadline_ms": 10_000,
    }
    args.update(overrides)
    return ModelRequest(**args)


def test_discovery_ok_when_endpoint_reachable(stub):
    adapter, _ = stub
    assert adapter.check_discovery() == GatewayStatus.REACHABLE


def test_discovery_fails_when_endpoint_unconfigured():
    from settlement import gateway_http

    adapter = gateway_http.HttpGatewayAdapter(endpoint="", api_key="x")
    result = adapter.check_discovery()
    assert isinstance(result, GatewayError)
    assert result.retryable is False


def test_discovery_transport_error_when_port_closed():
    from settlement import gateway_http

    adapter = gateway_http.HttpGatewayAdapter(endpoint="http://127.0.0.1:1", api_key="x")
    result = adapter.check_discovery()
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.TRANSPORT
    assert result.retryable is True


def test_auth_ok_with_valid_key(stub):
    adapter, _ = stub
    assert adapter.check_auth() == GatewayStatus.AUTHENTICATED


def test_auth_rejected_with_bad_key(stub):
    adapter, state = stub
    state.mode = "unauthorized"
    result = adapter.check_auth()
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.AUTH
    assert result.retryable is False


def test_infer_returns_stub_text_and_usage(stub):
    adapter, _ = stub
    result = adapter.infer(_request())
    assert isinstance(result, ModelResponse)
    assert result.text == "stub-answer"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (7, 5)
    assert result.usage.provider_enforced_ceiling is False
    assert result.model_meta.get("simulated") is not True


def test_infer_sends_bearer_key(stub):
    adapter, state = stub
    result = adapter.infer(_request())
    assert isinstance(result, ModelResponse)
    assert state.last_auth == "Bearer test-key"


def test_infer_rate_limit_is_retryable(stub):
    adapter, state = stub
    state.mode = "rate_limited"
    result = adapter.infer(_request())
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.RATE_LIMIT
    assert result.retryable is True


def test_infer_auth_failure_not_retryable(stub):
    adapter, state = stub
    state.mode = "unauthorized"
    result = adapter.infer(_request())
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.AUTH
    assert result.retryable is False


def test_infer_server_error_single_attempt(stub):
    adapter, state = stub
    state.mode = "server_error"
    result = adapter.infer(_request())
    assert isinstance(result, GatewayError)
    assert state.posts == 1


def test_infer_protocol_error_on_bad_payload(stub):
    adapter, state = stub
    state.mode = "bad_json"
    result = adapter.infer(_request())
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.retryable is False


def test_infer_protocol_error_on_missing_choices(stub):
    adapter, state = stub
    state.mode = "empty_choices"
    result = adapter.infer(_request())
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL


def test_infer_timeout_is_typed(stub):
    from settlement import gateway_http

    adapter, _ = stub
    adapter.timeouts["read"] = 0.2
    state_holder = stub[1]
    state_holder.mode = "sleep"
    result = adapter.infer(_request())
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.TIMEOUT
    assert result.retryable is True


def test_cancel_records_intent_without_confirming_external():
    from settlement import gateway_http

    adapter = gateway_http.HttpGatewayAdapter(endpoint="http://127.0.0.1:1", api_key="x")
    assert adapter.cancel("op_gone") is True
    assert adapter.cancel_status("op_gone") == "requested"


def test_cancelled_operation_reports_cancelled(stub):
    adapter, _ = stub
    request = _request()
    adapter.cancel(request.operation_id)
    result = adapter.infer(request)
    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.CANCELLED
    assert adapter.cancel_status(request.operation_id) == "confirmed"


def test_fake_adapter_never_reports_live():
    fake = FakeGatewayAdapter(text="simulated-text")
    result = fake.infer(_request())
    assert isinstance(result, ModelResponse)
    assert result.model_meta.get("simulated") is True
