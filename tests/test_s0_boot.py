from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from settlement.config import GatewayConfig, Settings


class OkHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, payload):
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._send({"data": []})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        self._send(
            {
                "choices": [{"message": {"content": "boot-probe"}, "finish_reason": "stop"}],
                "model": "stub",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        )


@pytest.fixture()
def live_endpoint():
    server = ThreadingHTTPServer(("127.0.0.1", 0), OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


def _settings(endpoint: str, tmp_path, dsn: str) -> Settings:
    return Settings(
        dsn=dsn,
        artifact_root=str(tmp_path / "artifacts"),
        staging_root=str(tmp_path / "staging"),
        gateway=GatewayConfig(endpoint=endpoint),
    )


def _ensure_migrations_table(dsn: str) -> None:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations"
                " (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )


def test_boot_full_stack_reports_exercised(tmp_path, live_endpoint):
    from settlement import boot
    from settlement.gateway_http import HttpGatewayAdapter

    dsn = os.environ["SETTLEMENT_TEST_DSN"]
    _ensure_migrations_table(dsn)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "staging").mkdir()
    settings = _settings(live_endpoint, tmp_path, dsn)
    adapter = HttpGatewayAdapter(endpoint=live_endpoint, api_key="k")
    report = boot.validate(settings, gateway_adapter=adapter, exercise_gateway=True)
    by_name = {entry.name: entry for entry in report.entries}
    assert by_name["database"].exercised is True
    assert by_name["artifacts"].exercised is True
    assert by_name["gateway"].authenticated is True
    assert by_name["gateway"].exercised is True
    assert report.models_available is True
    assert "model-inference" in report.available_operations


def test_boot_gateway_down_narrows_to_inspection(tmp_path, live_endpoint):
    from settlement import boot
    from settlement.gateway_http import HttpGatewayAdapter

    dsn = os.environ["SETTLEMENT_TEST_DSN"]
    _ensure_migrations_table(dsn)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "staging").mkdir()
    settings = _settings("http://127.0.0.1:1", tmp_path, dsn)
    adapter = HttpGatewayAdapter(endpoint="http://127.0.0.1:1", api_key="k")
    report = boot.validate(settings, gateway_adapter=adapter)
    by_name = {entry.name: entry for entry in report.entries}
    assert by_name["gateway"].reachable is False
    assert report.models_available is False
    assert "model-inference" not in report.available_operations
    assert "inspect" in report.available_operations
    assert "mechanical-recovery" in report.available_operations


def test_boot_gvisor_unavailable_on_this_host(tmp_path, live_endpoint):
    from settlement import boot
    from settlement.gateway_http import HttpGatewayAdapter

    dsn = os.environ["SETTLEMENT_TEST_DSN"]
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "staging").mkdir()
    settings = _settings(live_endpoint, tmp_path, dsn)
    adapter = HttpGatewayAdapter(endpoint=live_endpoint, api_key="k")
    report = boot.validate(settings, gateway_adapter=adapter, admitted_profile="gvisor")
    by_name = {entry.name: entry for entry in report.entries}
    assert by_name["sandbox"].reachable is False
    assert "sandbox-exec:gvisor" not in report.available_operations
    assert "simulated-demonstration" in report.available_operations


def test_boot_fake_gateway_never_enables_live_inference(tmp_path):
    from settlement import boot
    from settlement.gateway import FakeGatewayAdapter

    dsn = os.environ["SETTLEMENT_TEST_DSN"]
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "staging").mkdir()
    settings = _settings("", tmp_path, dsn)
    report = boot.validate(settings, gateway_adapter=FakeGatewayAdapter())
    assert report.models_available is False
    assert "model-inference" not in report.available_operations
    assert "simulated-demonstration" in report.available_operations


def test_boot_database_down_still_reports_structure(tmp_path):
    from settlement import boot
    from settlement.gateway import FakeGatewayAdapter

    (tmp_path / "artifacts").mkdir()
    (tmp_path / "staging").mkdir()
    settings = _settings("", tmp_path, "postgresql://ubuntu@/no_such_db?host=/var/run/postgresql")
    report = boot.validate(settings, gateway_adapter=FakeGatewayAdapter())
    by_name = {entry.name: entry for entry in report.entries}
    assert by_name["database"].configured is True
    assert by_name["database"].reachable is False
    assert report.ok is False
    assert "inspect" in report.available_operations
