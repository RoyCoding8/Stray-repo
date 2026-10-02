from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest
from scripts import s09_pilot


class _Provider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def infer(self, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result

    def check_discovery(self):
        return None

    def check_auth(self):
        return None

    def cancel(self, operation_id):
        return False


def _request(model="free-model"):
    from settlement.gateway import ModelRequest
    return ModelRequest(model=model, messages=({"role": "user", "content": "ping"},),
                        max_output_tokens=8, deadline_ms=5_000)


def _body(costs):
    body = {
        "output": [{"type": "message", "content": [{
            "type": "output_text", "text": "ok"}]}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    if costs is not None:
        body["usage"].update(costs)
    return body


def _gateway(costs):
    from scripts import s09_pilot

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(
                int(self.headers["Content-Length"]))))
            encoded = json.dumps(_body(costs)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    adapter = s09_pilot._http_gateway(
        "http://127.0.0.1:%d" % server.server_port)
    guard = s09_pilot.StudyGatewayGuard(
        adapter, pinned_model="free-model", ceiling=100, already_spent=2)
    return server, thread, guard, seen


def _close(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_materialized_policy_view_strips_sealed_task_content():
    from experiments.ad01.policy_step import materialize_view

    view = materialize_view(
        task={"task_id": "task-1", "family": "software",
              "public": {"name": "visible"},
              "hidden_answer": "sealed-value",
              "nested": {"blind_key": "nested-sealed"}},
        observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={})

    serialized = json.dumps(view, sort_keys=True)
    assert "sealed-value" not in serialized
    assert "nested-sealed" not in serialized
    assert view["task_content"]["task_id"] == "task-1"
    assert view["task_content"]["family"] == "software"


def test_guard_refuses_dispatch_above_ceiling_and_counts_dispatches():
    from scripts import s09_pilot
    from settlement.gateway import ModelResponse, Usage

    provider = _Provider(ModelResponse(
        "op", "ok", {"providerMetadata": {"gateway": {"cost": 0}}},
        Usage(), "stop"))
    guard = s09_pilot.StudyGatewayGuard(
        provider, pinned_model="free-model", ceiling=3, already_spent=2)

    guard.infer(_request())
    with pytest.raises(s09_pilot.StudyGuardRefusal, match="ceiling 3"):
        guard.infer(_request())
    assert provider.calls == 1
    assert guard.dispatch_count == 3
    assert guard.refusal_reason == "study model-call ceiling 3 reached"


def test_guard_refuses_model_other_than_pinned_one():
    from scripts import s09_pilot

    provider = _Provider()
    guard = s09_pilot.StudyGatewayGuard(
        provider, pinned_model="free-model", ceiling=100, already_spent=2)

    with pytest.raises(s09_pilot.StudyGuardRefusal, match="pinned model"):
        guard.infer(_request(model="other-model"))
    assert provider.calls == 0
    assert guard.dispatch_count == 2


def test_guard_raises_for_nonzero_usage_cost():
    server, thread, guard, _seen = _gateway({"cost": 0.01})
    try:
        with pytest.raises(s09_pilot.StudyGuardRefusal, match="nonzero cost"):
            guard.infer(_request())
        assert guard.dispatch_count == 3
    finally:
        _close(server, thread)


def test_guard_raises_when_every_cost_field_is_absent():
    server, thread, guard, _seen = _gateway(None)
    try:
        with pytest.raises(s09_pilot.StudyGuardRefusal, match="cost is unverified"):
            guard.infer(_request())
        assert guard.dispatch_count == 3
    finally:
        _close(server, thread)


def test_guard_permits_zero_cost_and_increments_count():
    server, thread, guard, _seen = _gateway({"cost": 0})
    try:
        response = guard.infer(_request())
        assert response.text == "ok"
        assert guard.dispatch_count == 3
        assert guard.refusal_reason == ""
    finally:
        _close(server, thread)


def test_guard_counts_failed_dispatch_attempt():
    from scripts import s09_pilot

    provider = _Provider(error=RuntimeError("controlled failure"))
    guard = s09_pilot.StudyGatewayGuard(
        provider, pinned_model="free-model", ceiling=100, already_spent=2)

    with pytest.raises(RuntimeError, match="controlled failure"):
        guard.infer(_request())
    assert provider.calls == 1
    assert guard.dispatch_count == 3


def test_guard_delegates_to_real_http_gateway_adapter():
    from scripts import s09_pilot
    from settlement.gateway_http import HttpGatewayAdapter

    server, thread, guard, seen = _gateway({"cost": 0})
    try:
        assert isinstance(guard.delegate, HttpGatewayAdapter)
        guard.infer(_request())
        assert len(seen) == 1
        assert seen[0]["model"] == "free-model"
    finally:
        _close(server, thread)
