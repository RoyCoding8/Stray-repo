from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from settlement.gateway import GatewayErrorKind, ModelRequest


def _request(**overrides):
    args = {
        "model": "stub-model",
        "messages": ({"role": "user", "content": "hi"},),
        "max_output_tokens": 16,
        "deadline_ms": 1_000,
    }
    args.update(overrides)
    return ModelRequest(**args)


_OK_BODY = json.dumps(
    {
        "choices": [{"message": {"content": "trickle-answer"}, "finish_reason": "stop"}],
        "model": "stub-model",
        "usage": {"prompt_tokens": 7, "completion_tokens": 5},
    }
).encode()


class TrickleHandler(BaseHTTPRequestHandler):
    mode = "trickle"
    sleep_s = 6.0
    chunk_s = 0.06

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        if type(self).mode == "sleep":
            time.sleep(type(self).sleep_s)
            raw = _OK_BODY
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        raw = _OK_BODY
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        for i in range(0, len(raw), 1):
            time.sleep(type(self).chunk_s)
            try:
                self.wfile.write(raw[i : i + 1])
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return


def _trickle_server():
    from settlement import gateway_http

    server = ThreadingHTTPServer(("127.0.0.1", 0), TrickleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    # The adapter needs a route contract, and it has to agree with the
    # request on the model: `_request` below sends "stub-model" and the
    # stub server answers as "stub-model". `expected_route` defaults to
    # None and `route_mode` to "free", so without one
    # `_pre_dispatch_route_error` returns PROTOCOL *before any socket is
    # opened* and the deadline logic these tests exist to exercise is
    # never reached. The sibling file `test_gateway_final_routes.py` has
    # passed `expected_route=ROUTE` since the guard landed in 9682fb8;
    # this file was not updated, so all four deadline tests had been
    # asserting against a pre-dispatch refusal.
    route = {
        "endpoint": endpoint,
        "requested_model": "stub-model",
        "resolved_model": "stub-model",
        "provider": "stub",
        "tier": "free",
    }
    adapter = gateway_http.HttpGatewayAdapter(
        endpoint=endpoint, api_key="test-key", expected_route=route)
    return adapter, server, thread


def test_trickle_response_hits_deadline_promptly():
    adapter, server, thread = _trickle_server()
    try:
        TrickleHandler.mode = "trickle"
        started = time.monotonic()
        result = adapter.infer(_request(deadline_ms=1_000))
        elapsed = time.monotonic() - started
        assert result.kind == GatewayErrorKind.TIMEOUT
        assert result.retryable is True
        assert elapsed < 5.0
    finally:
        server.shutdown()
        thread.join()


def test_injected_client_receives_per_request_timeout():
    adapter, server, thread = _trickle_server()
    try:
        TrickleHandler.mode = "sleep"
        TrickleHandler.sleep_s = 6.0
        adapter._client = httpx.Client(timeout=30.0)
        try:
            started = time.monotonic()
            result = adapter.infer(_request(deadline_ms=1_000))
            elapsed = time.monotonic() - started
        finally:
            adapter._client.close()
            adapter._client = None
        assert result.kind == GatewayErrorKind.TIMEOUT
        assert elapsed < 4.0
    finally:
        server.shutdown()
        thread.join()


def test_cancel_during_trickle_reports_unknown_outcome():
    adapter, server, thread = _trickle_server()
    try:
        TrickleHandler.mode = "trickle"
        request = _request(deadline_ms=30_000)
        outcome: list = []

        def run():
            outcome.append(adapter.infer(request))

        worker = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        worker.start()
        time.sleep(0.5)
        assert adapter.cancel(request.operation_id) is True
        worker.join(timeout=10.0)
        elapsed = time.monotonic() - started
        assert outcome, "infer did not return after cancellation"
        assert outcome[0].kind == GatewayErrorKind.CANCELLED
        assert outcome[0].retryable is False
        assert "unknown" in outcome[0].message
        assert adapter.cancel_status(request.operation_id) == "worker_stopped"
        assert elapsed < 5.0
    finally:
        server.shutdown()
        thread.join()


def _seed_many_attempts(dsn, n=200, per_inv=50, tag="bulk"):
    import uuid

    from settlement import store
    from settlement.common import Command

    def cmd(payload: dict) -> Command:
        return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)

    store.seed_allocation(dsn, cmd({"allocation_id": f"{tag}-a1", "domain": "cpu",
                                    "authorized": 10_000_000, "max_occupancy": 10_000}))
    iids = []
    for i in range(n // per_inv):
        iid = f"{tag}-i{i}"
        store.admit_commitment(dsn, cmd({"investigation_id": iid, "objective": f"bulk-{i}"}))
        iids.append(iid)
    k = 0
    for iid in iids:
        for _ in range(per_inv):
            store.acquire_work(dsn, cmd({"attempt_id": f"{tag}-w{k}",
                                         "investigation_id": iid,
                                         "allocation_id": f"{tag}-a1"}))
            k += 1
    return iids


def _counted_dsn(monkeypatch):
    from settlement import db as _db

    counts = {"connects": 0, "executes": 0}
    real_connect = _db.connect

    class Cursor:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, *args, **kwargs):
            counts["executes"] += 1
            return self._cur.execute(*args, **kwargs)

        def __enter__(self):
            self._cur.__enter__()
            return self

        def __exit__(self, *exc):
            return self._cur.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self._cur, name)

    class Conn:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self, *args, **kwargs):
            return Cursor(self._conn.cursor(*args, **kwargs))

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc):
            return self._conn.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def counting_connect(*args, **kwargs):
        counts["connects"] += 1
        return Conn(real_connect(*args, **kwargs))

    monkeypatch.setattr(_db, "connect", counting_connect)
    return counts


def test_overview_uses_bounded_projection(migrated_db, monkeypatch):
    from settlement import api as _api

    dsn = migrated_db
    _seed_many_attempts(dsn)
    counts = _counted_dsn(monkeypatch)
    view = _api.overview_data(dsn)
    assert view["attempt_total"] == 200
    assert len(view["attempts"]) <= 50
    assert counts["connects"] <= 6
    assert counts["executes"] <= 18


def test_overview_query_cost_independent_of_history(migrated_db, monkeypatch):
    from settlement import api as _api

    dsn = migrated_db
    _seed_many_attempts(dsn, n=20, per_inv=10, tag="small")
    counts = _counted_dsn(monkeypatch)
    small = _api.overview_data(dsn)
    assert len(small["attempts"]) == 20
    small_cost = (counts["connects"], counts["executes"])
    _seed_many_attempts(dsn, n=200, per_inv=50, tag="big")
    counts["connects"] = 0
    counts["executes"] = 0
    big = _api.overview_data(dsn)
    assert len(big["attempts"]) <= 50
    assert (counts["connects"], counts["executes"]) == small_cost


def test_precancelled_operation_reports_unknown_outcome():
    adapter, server, thread = _trickle_server()
    try:
        request = _request(deadline_ms=30_000)
        adapter.cancel(request.operation_id)
        result = adapter.infer(request)
        assert result.kind == GatewayErrorKind.CANCELLED
        assert result.retryable is False
        assert "unknown" in result.message
        assert adapter.cancel_status(request.operation_id) == "requested"
    finally:
        server.shutdown()
        thread.join()
