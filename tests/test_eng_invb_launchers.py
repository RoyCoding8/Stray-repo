from __future__ import annotations

import os
import time

import pytest

from settlement.broker import BrokerOp
from settlement.exec_profile import run_local_process
from settlement.launcher_local import LocalLauncher


def _op(op_id="op1", gen=0, version="v1"):
    return BrokerOp(
        operation_id=op_id, effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 5_000, "max_output_bytes": 64},
        execution_version=version, dispatch_generation=gen)


def test_stale_generation_refusal_keeps_live_generation_sendable(tmp_path):
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    (run_dir / "op1_v1.gen").write_text("5")
    launcher = LocalLauncher(run_dir=run_dir)
    stale = launcher.dispatch(_op(gen=3))
    assert stale.sent is False
    assert "superseded" in stale.refused_reason
    live = launcher.dispatch(_op(gen=5))
    assert live.sent is True, live.refused_reason
    assert live.receipt is not None and live.receipt.outcome == "success"


def _wait_gone(pid: int, deadline_s: float = 10.0) -> bool:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError, OSError):
            return True
        time.sleep(0.05)
    return False


def test_run_local_process_reaps_grandchildren_on_timeout(tmp_path):
    child_pid_file = tmp_path / "child.pid"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    argv = ["python3", "-c",
            "import os, subprocess, time; "
            f"open({str(child_pid_file)!r}, 'w').write(str(os.getpid())); "
            "p = subprocess.Popen(['python3', '-c', "
            f"\"import os, time; open({str(grandchild_pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(120)\"]); "
            "time.sleep(120)"]
    started = time.monotonic()
    result = run_local_process(argv, timeout_ms=800, max_output_bytes=4096)
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert elapsed < 60.0, f"timeout of 0.8s blocked for {elapsed:.1f}s"
    assert grandchild_pid_file.exists(), "grandchild never started; test is void"
    grandchild = int(grandchild_pid_file.read_text().strip())
    assert _wait_gone(grandchild), f"grandchild {grandchild} survived timeout kill"
    child = int(child_pid_file.read_text().strip())
    assert _wait_gone(child, 2.0), f"child {child} survived timeout kill"
