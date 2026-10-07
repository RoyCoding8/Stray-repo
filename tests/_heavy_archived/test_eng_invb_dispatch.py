from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from settlement.broker import BrokerOp
from settlement.launcher_local import LocalLauncher


def _op(op_id="op1", **kw):
    payload = {"profile": "local-process", "argv": ["/bin/true"], "timeout_ms": 5_000,
               "max_output_bytes": 65_536}
    payload.update(kw.get("payload", {}))
    return BrokerOp(operation_id=op_id, effect="sandbox-exec", payload=payload,
                    execution_version=kw.get("execution_version", "exec-v1"))


def test_worker_cwd_isolated_from_run_state(tmp_path):
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    (run_dir / "victim-op_exec-v1.result.json").write_text('{"outcome": "success"}')
    probe = ("import os,json; print(json.dumps({'status': 'ok', 'data': {"
             "'cwd': os.getcwd(), 'entries': sorted(os.listdir('.'))}}))")
    out = launcher.dispatch(_op("snoop-op", payload={
        "profile": "local-process", "argv": [sys.executable, "-c", probe],
        "timeout_ms": 10_000, "max_output_bytes": 65_536}))
    assert out.sent is True
    data = out.receipt.content["data"]["worker"]["data"]
    assert Path(data["cwd"]).is_relative_to(run_dir)
    assert Path(data["cwd"]).name == "snoop-op_exec-v1.work"
    assert "victim-op_exec-v1.result.json" not in data["entries"]
    assert data["entries"] == ["inputs", "outputs"]


def test_worker_requested_cwd_still_honored(tmp_path):
    launcher = LocalLauncher(tmp_path / "runs")
    elsewhere = tmp_path / "isolated"
    elsewhere.mkdir()
    probe = ("import os,json; print(json.dumps({'status': 'ok', 'data': "
             "{'cwd': os.getcwd()}}))")
    op = _op("cwd-op", payload={
        "profile": "local-process", "argv": [sys.executable, "-c", probe],
        "timeout_ms": 10_000, "max_output_bytes": 65_536, "cwd": str(elsewhere)})
    out = launcher.dispatch(op)
    assert out.sent is True
    assert out.receipt.content["data"]["worker"]["data"]["cwd"] == str(elsewhere)


def test_read_output_refuses_traversal(tmp_path):
    launcher = LocalLauncher(tmp_path / "runs")
    out_dir = tmp_path / "runs" / "op1_exec-v1.work" / "outputs"
    out_dir.mkdir(parents=True)
    (out_dir / "fixed.py").write_bytes(b"ok")
    assert launcher.read_output("op1", "exec-v1", "fixed.py") == b"ok"
    for bad in ("/etc/hostname", "../escape.txt", "../../escape.txt", ""):
        with pytest.raises(ValueError):
            launcher.read_output("op1", "exec-v1", bad)
    for bad in ("../escape.txt", "/absolute.txt"):
        with pytest.raises(ValueError):
            launcher.stage_input("op1", "exec-v1", bad, b"x")


def test_normal_completion_records_supervision_and_cleans_up(tmp_path):
    launcher = LocalLauncher(tmp_path / "runs")
    out = launcher.dispatch(_op())
    assert out.sent is True and out.receipt.outcome == "success"
    assert out.receipt.content["data"]["supervised"] is True
    assert list((tmp_path / "runs").glob("*.supervise.json")) == []


def test_orphan_killed_after_broker_death(tmp_path):
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    repo = Path(__file__).parents[2]
    broker_code = (
        "import sys; sys.path.insert(0, %r);" % str(repo / "src") +
        "from settlement.launcher_local import LocalLauncher;"
        "from settlement.broker import BrokerOp;"
        "launcher = LocalLauncher(%r);" % str(run_dir) +
        "op = BrokerOp(operation_id='orphan-op', effect='sandbox-exec',"
        " payload={'profile': 'local-process', 'argv': ['/bin/sleep', '60'],"
        " 'timeout_ms': 3000, 'max_output_bytes': 1024},"
        " execution_version='exec-v1');"
        "launcher.dispatch(op)")
    proc = subprocess.Popen([sys.executable, "-c", broker_code])
    try:
        deadline = time.monotonic() + 10
        pid_files = []
        while time.monotonic() < deadline and not pid_files:
            pid_files = list(run_dir.glob("orphan-op_*.pid"))
            time.sleep(0.1)
        assert pid_files, "broker never spawned the worker"
        pgid = int(pid_files[0].read_text().strip())
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError, OSError):
                break
            time.sleep(0.2)
        with pytest.raises((ProcessLookupError, PermissionError, OSError)):
            os.killpg(pgid, 0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_proc_starttime_tracks_live_process_only():
    from settlement.exec_profile import proc_starttime

    assert proc_starttime(os.getpid()) is not None
    assert proc_starttime(1) is not None
    assert proc_starttime(2**30) is None


def _settings(endpoint):
    from settlement.config import GatewayConfig, Settings

    return Settings(dsn="", artifact_root="a", staging_root="s",
                    gateway=GatewayConfig(endpoint=endpoint))


def _stub_route(endpoint: str) -> dict[str, str]:
    from settlement.gateway import RouteContract

    return RouteContract.from_mapping({
        "endpoint": endpoint, "requested_model": "stub", "resolved_model": "stub",
        "provider": "stub-provider", "tier": "free"}).as_dict()


def test_from_settings_defaults_to_chat_shape(monkeypatch):
    from settlement import gateway_http

    monkeypatch.delenv("SETTLEMENT_GATEWAY_API", raising=False)
    adapter = gateway_http.HttpGatewayAdapter.from_settings(_settings("http://x"))
    assert adapter.api == "chat"


def test_from_settings_refuses_unattestable_responses_route(monkeypatch):
    from settlement import gateway_http
    from settlement.gateway import (GatewayError, GatewayErrorKind,
                                    GatewayRouteError, ModelRequest)

    monkeypatch.setenv("SETTLEMENT_GATEWAY_API", "responses")
    endpoint = "http://127.0.0.1:9"
    adapter = gateway_http.HttpGatewayAdapter.from_settings(
        _settings(endpoint), expected_route=_stub_route(endpoint))

    assert adapter.api == "responses"
    result = adapter.infer(ModelRequest(
        model="stub", messages=({"role": "user", "content": "hi"},),
        max_output_tokens=8, deadline_ms=10_000))

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is False
    assert "publishes no provider" in result.message


def test_from_settings_refuses_unknown_shape(monkeypatch):
    from settlement import gateway_http

    monkeypatch.setenv("SETTLEMENT_GATEWAY_API", "soap")
    with pytest.raises(ValueError):
        gateway_http.HttpGatewayAdapter.from_settings(_settings("http://x"))


def test_from_settings_explicit_arg_beats_env(monkeypatch):
    from settlement import gateway_http

    monkeypatch.setenv("SETTLEMENT_GATEWAY_API", "responses")
    adapter = gateway_http.HttpGatewayAdapter.from_settings(
        _settings("http://x"), api="chat")
    assert adapter.api == "chat"
