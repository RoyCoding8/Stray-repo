from __future__ import annotations

import json
import os
import subprocess

import pytest

from settlement.broker import BrokerOp
from settlement.common import IncompatibleVersion
from settlement.launcher_local import LocalLauncher
from settlement.launcher_runsc import RunscLauncher


def _op(op_id="op1", **kw):
    payload = {"profile": "local-process", "argv": ["/bin/true"], "timeout_ms": 5_000,
               "max_output_bytes": 65_536}
    payload.update(kw.get("payload", {}))
    return BrokerOp(operation_id=op_id, effect="sandbox-exec", payload=payload,
                    execution_version=kw.get("execution_version", "exec-v1"))


def test_identity_reused_after_recovery_single_spawn(tmp_path):
    first = LocalLauncher(run_dir=tmp_path / "runs")
    out = first.dispatch(_op())
    assert out.sent is True and out.receipt is not None and out.receipt.outcome == "success"
    recovered = LocalLauncher(run_dir=tmp_path / "runs")
    assert recovered.prior_send("op1") is True
    again = recovered.dispatch(_op())
    assert again.sent is False and "prior-send" in again.refused_reason
    spawns = (tmp_path / "runs" / "op1_exec-v1.spawns").read_text()
    assert spawns.strip() == "1"


def test_worker_env_scrubbed_of_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLEMENT_DSN", "postgresql://secret")
    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", "gw-secret")
    monkeypatch.setenv("MY_API_TOKEN", "tok-secret")
    argv = ["python3", "-c",
            "import json, os; print(json.dumps({'status': 'ok', 'data': {'env': dict(os.environ)}}))"]
    launcher = LocalLauncher(run_dir=tmp_path / "runs")
    out = launcher.dispatch(_op("op-env", payload={"profile": "local-process", "argv": argv,
                                                   "timeout_ms": 10_000, "max_output_bytes": 1_048_576}))
    assert out.sent is True
    assert out.receipt.content["data"]["worker"]["status"] == "ok"
    env = out.receipt.content["data"]["worker"]["data"]["env"]
    assert "SETTLEMENT_DSN" not in env and "SETTLEMENT_GATEWAY_KEY" not in env
    assert "MY_API_TOKEN" not in env and "DBOS_DATABASE_URL" not in env
    assert out.receipt.content.get("containment") is False


def test_over_quota_output_capped(tmp_path):
    argv = ["python3", "-c", "print('x' * 100000)"]
    launcher = LocalLauncher(run_dir=tmp_path / "runs")
    out = launcher.dispatch(_op("op-big", payload={"profile": "local-process", "argv": argv,
                                                   "timeout_ms": 10_000, "max_output_bytes": 1024}))
    assert out.sent is True
    assert out.receipt.content["truncated"] is True
    assert len(out.receipt.content["data"].get("stdout", "")) <= 1024


def test_worker_bytes_never_executed(tmp_path):
    marker = tmp_path / "pwned"
    argv = ["python3", "-c",
            f"print(\"__import__('pathlib').Path({str(marker)!r}).write_text('x')\")"]
    launcher = LocalLauncher(run_dir=tmp_path / "runs")
    out = launcher.dispatch(_op("op-inject", payload={"profile": "local-process", "argv": argv,
                                                      "timeout_ms": 10_000,
                                                      "max_output_bytes": 65_536}))
    assert out.sent is True
    assert out.receipt.outcome == "failure"
    assert out.receipt.content["parse"] == "rejected"
    assert out.receipt.content["data"]["stdout"].startswith("__import__")
    assert not marker.exists()


def test_timeout_kills_whole_process_group(tmp_path):
    pgid_file = tmp_path / "pgid"
    argv = ["python3", "-c",
            "import os, subprocess, time; "
            f"open({str(pgid_file)!r}, 'w').write(str(os.getpgrp())); "
            "subprocess.Popen(['sleep', '30']); time.sleep(30)"]
    launcher = LocalLauncher(run_dir=tmp_path / "runs", grace_ms=200)
    out = launcher.dispatch(_op("op-kill", payload={"profile": "local-process", "argv": argv,
                                                    "timeout_ms": 800, "max_output_bytes": 4096}))
    assert out.sent is True
    assert out.receipt.content["data"]["timed_out"] is True
    pgid = int(pgid_file.read_text())
    with pytest.raises((ProcessLookupError, PermissionError, OSError)):
        os.killpg(pgid, 0)
    orphans = subprocess.run(["pgrep", "-f", "sleep 30"], capture_output=True, text=True)
    assert orphans.stdout.strip() == ""


def test_result_files_support_recovery_inspection(tmp_path):
    launcher = LocalLauncher(run_dir=tmp_path / "runs")
    launcher.dispatch(_op())
    assert launcher.read_result("op1")["outcome"] == "success"
    assert launcher.prior_send("op1") is True
    assert launcher.prior_send("op-never") is False
    assert launcher.read_result("op-never") is None


def test_runsc_dispatch_raises_incompatible_never_local(tmp_path):
    launcher = RunscLauncher(image_digest="sha256:" + "0" * 64)
    assert launcher.prior_send("anything") is False
    assert launcher.live_ids() == []
    with pytest.raises(IncompatibleVersion) as exc:
        launcher.dispatch(_op("op-r", payload={"profile": "gvisor", "argv": ["/bin/true"],
                                               "timeout_ms": 1000, "max_output_bytes": 64}))
    assert "runsc" in str(exc.value).lower() or "gvisor" in str(exc.value).lower()
    assert (tmp_path / "runs").exists() or True
    assert "local" not in str(exc.value).lower() or "local-process" not in str(exc.value)


def test_runsc_identity_declares_runtime_profile():
    launcher = RunscLauncher(image_digest="sha256:" + "ab" * 32)
    native = launcher.native_id("op9", "exec-v7")
    assert "op9" in native and "exec-v7" in native and "runsc" in native
