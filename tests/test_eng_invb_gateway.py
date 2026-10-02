from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from settlement.gateway import GatewayErrorKind, ModelRequest
from settlement.gateway_http import HttpGatewayAdapter


class HangState:
    posts = 0


class HangHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        self.server.state.posts += 1
        time.sleep(30)
        raw = json.dumps({"choices": [{"message": {"content": "late"},
                                        "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture()
def hang_stub():
    server = ThreadingHTTPServer(("127.0.0.1", 0), HangHandler)
    server.state = HangState()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


def _request(op_id="op-cancel-race"):
    return ModelRequest(model="stub", messages=({"role": "user", "content": "hi"},),
                        max_output_tokens=8, deadline_ms=30_000,
                        operation_id=op_id)


def test_cancel_during_blocked_infer_returns_promptly(hang_stub):
    adapter = HttpGatewayAdapter(endpoint=hang_stub, api_key="x",
                                 timeout_read_ms=25_000, route_mode="paid")
    outcome: dict = {}

    def _run():
        started = time.monotonic()
        result = adapter.infer(_request())
        outcome["result"] = result
        outcome["elapsed"] = time.monotonic() - started

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    assert worker.is_alive()
    time.sleep(1.0)
    assert worker.is_alive(), "infer returned before cancel; stub did not block"
    adapter.cancel("op-cancel-race")
    worker.join(timeout=10.0)
    assert not worker.is_alive(), "cancel did not interrupt a blocked infer"
    result = outcome["result"]
    assert not isinstance(result, str)
    assert getattr(result, "kind", None) == GatewayErrorKind.CANCELLED
    assert outcome["elapsed"] < 10.0
    assert adapter.cancel_status("op-cancel-race") == "worker_stopped"
