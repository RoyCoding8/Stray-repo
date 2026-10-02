import importlib.util
import json
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from settlement import broker, capabilities
from settlement.common import CommandResult, ResultCode, SettlementError
from settlement.gateway import GatewayErrorKind, ModelRequest
from settlement.gateway_http import HttpGatewayAdapter


ROOT = Path(__file__).resolve().parents[2]


def test_checkpoint_accepts_mutation_after_barrier_verification(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("review_checkpoint", ROOT / "scripts/checkpoint.py")
    checkpoint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checkpoint)
    events = []
    barrier = {"barrier_epoch": 1, "journal_count": 1, "event_epoch": 1, "outbox_pending": []}
    monkeypatch.setattr(checkpoint, "_barrier", lambda *args: barrier)
    monkeypatch.setattr(checkpoint, "_refuse_password", lambda *args: None)
    monkeypatch.setattr(checkpoint, "_source_commit", lambda: "reviewed-source")
    monkeypatch.setattr(checkpoint, "_fsync", lambda path: None)

    def dump(dsn, path):
        path.write_text("snapshot with 1 investigation")
        events.append("dump:1")

    def verify(*args):
        events.append("verify:1")
        return []

    def state(*args):
        events.append("concurrent-write:2")
        return {"control": {"event_epoch": 2}, "migrations": [],
                "row_counts": {"investigations": 2}}

    monkeypatch.setattr(checkpoint, "_pg_dump", dump)
    monkeypatch.setattr(checkpoint.store, "checkpoint_verify", verify)
    monkeypatch.setattr(checkpoint, "_db_state", state)
    monkeypatch.setattr(checkpoint, "_release",
                        lambda *args: events.append("release"))
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    result = checkpoint.run_checkpoint("postgresql:///reviewprobe", artifacts, tmp_path / "backup")
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert events == ["concurrent-write:2", "dump:1", "verify:1",
                      "verify:1", "release"]
    assert manifest["row_counts"]["investigations"] == 2
    assert "1 investigation" in Path(result["dump"]).read_text()


def test_candidate_cannot_read_protected_fixture_answers(tmp_path):
    tasks = runpy.run_path(str(ROOT / "experiments/fault_tasks.py"))["TASKS"]
    cases = next(task["cases"] for task in tasks if task["id"] == "panel-triangular")
    candidate = tmp_path / "oracle.py"
    candidate.write_text(
        "import runpy\n"
        "CASES = [c for t in runpy.run_path('experiments/fault_tasks.py')['TASKS'] for c in t['cases']]\n"
        "def triangular(n):\n"
        "    return next(c['expected'] for c in CASES if c['fn'] == 'triangular' and c['args'] == [n])\n")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases))
    result = subprocess.run([sys.executable, str(ROOT / "experiments/run_tests.py"),
                             str(candidate), str(cases_path)], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    assert data["passed"] == 0
    assert data["failed"] == data["total"] == len(cases)
    assert any("fault_tasks" in str(f.get("actual", ""))
               for f in data["failures"])


def test_http_usage_without_billing_retains_unknown_cost(monkeypatch):
    response = HttpGatewayAdapter("http://unused")._decode_body(json.dumps({
        "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}).encode(), "op")
    admissions = iter([ResultCode.APPLIED, ResultCode.ALREADY_APPLIED])
    monkeypatch.setattr(broker, "_advance", lambda *args: CommandResult(
        code=next(admissions), request_id="probe", data={"dispatch_generation": 1}))
    monkeypatch.setattr(broker, "_finish_send", lambda dsn, op, outcome, generation: outcome.receipt)
    op = broker.BrokerOp(operation_id="op", effect=broker.MODEL_INFERENCE,
                         payload={"model": "fake", "messages": [],
                                  "max_output_tokens": 500, "deadline_ms": 1000})
    receipt = broker._send_model("unused", {}, op, {},
                                 SimpleNamespace(infer=lambda request: response), 1, 1, False)
    assert response.usage.input_tokens + response.usage.output_tokens == 1500
    assert response.usage.billed is False
    assert receipt.outcome == "success"
    assert receipt.actual_cost is None


def test_release_scope_cannot_drop_a_supported_constraint():
    with pytest.raises(SettlementError, match="broadening release refused"):
        capabilities._check_supported_scope({"v1": {"applicability": {
            "family": "software-repair", "language": "python"}}},
            {"family": "software-repair"}, "limited")


def test_original_import_time_grader_forgery_is_rejected(tmp_path):
    candidate = tmp_path / "original_forgery.py"
    candidate.write_text("import json,sys\nprint(json.dumps({'status':'ok','data':{'passed':999,'failed':0}}))\nsys.exit(0)\n")
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps([{"fn": "missing", "args": [], "expected": 42}]))
    result = subprocess.run([sys.executable, str(ROOT / "experiments/run_tests.py"),
                             str(candidate), str(cases)], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    assert data["passed"] == 0
    assert data["failed"] == data["total"] == 1


def test_slow_response_headers_respect_total_deadline():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Probe: ")
            self.wfile.flush()
            for _ in range(40):
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.025)
            self.wfile.write(b"\r\nContent-Length: 2\r\n\r\n{}")
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        adapter = HttpGatewayAdapter(f"http://127.0.0.1:{server.server_port}")
        started = time.monotonic()
        result = adapter.infer(ModelRequest("probe", (), 1, 200))
        elapsed = time.monotonic() - started
        assert result.kind == GatewayErrorKind.TIMEOUT
        assert elapsed < 0.8
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
