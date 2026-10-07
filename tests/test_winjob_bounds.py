"""Windows child bounds are enforced, not just declared.

Each test runs a real child that tries to exceed its bound and asserts the
observed outcome. Skipped off Windows, where POSIX rlimits are tested instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows Job Object bounds")

from settlement import exec_profile  # noqa: E402

PY = sys.executable


def test_unbounded_child_runs_and_reports_output():
    result = exec_profile.run_local_process([PY, "-c", "print('hello')"], timeout_ms=30_000)
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"
    assert result.timed_out is False


def test_memory_bound_stops_an_allocation_past_it():
    code = "x = bytearray(512 * 1024 * 1024); print('allocated')"
    result = exec_profile.run_local_process(
        [PY, "-c", code], timeout_ms=30_000, memory_bytes=64 * 1024 * 1024)
    assert result.returncode != 0
    assert "allocated" not in result.stdout
    assert "MemoryError" in result.stderr


def test_same_allocation_succeeds_under_a_larger_bound():
    code = "x = bytearray(32 * 1024 * 1024); print('allocated')"
    result = exec_profile.run_local_process(
        [PY, "-c", code], timeout_ms=30_000, memory_bytes=512 * 1024 * 1024)
    assert result.returncode == 0
    assert result.stdout.strip() == "allocated"


def test_cpu_bound_terminates_a_busy_loop_promptly():
    started = time.monotonic()
    result = exec_profile.run_local_process(
        [PY, "-c", "while True: pass"], timeout_ms=60_000, cpu_seconds=1)
    elapsed = time.monotonic() - started
    assert result.timed_out is False
    assert result.detail["cpu_limit_exceeded"] is True
    assert result.returncode == 0xC0000044
    assert elapsed < 10, elapsed


def test_wall_timeout_kills_a_sleeping_child():
    result = exec_profile.run_local_process(
        [PY, "-c", "import time; time.sleep(60)"], timeout_ms=1_000)
    assert result.timed_out is True
    assert result.wall_ms < 15_000


def test_grandchild_dies_with_the_job():
    code = ("import subprocess, sys;"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
            "print(p.pid)")
    result = exec_profile.run_local_process([PY, "-c", code], timeout_ms=30_000)
    assert result.returncode == 0
    grandchild = int(result.stdout.strip())
    from settlement import winjob
    deadline = time.monotonic() + 5
    while winjob.pid_alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not winjob.pid_alive(grandchild)


def test_pid_alive_does_not_signal():
    proc = subprocess.Popen([PY, "-c", "import time; time.sleep(30)"])
    try:
        from settlement import winjob
        assert winjob.pid_alive(proc.pid)
        assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait()
