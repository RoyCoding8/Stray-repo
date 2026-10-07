"""R01-005: gVisor launcher + recovery contract (S0, EFF-7).

Seams under test: the probe boundary (``probe_gvisor``) and the process
boundary (``subprocess.Popen``/``subprocess.run`` for docker CLI calls).
Containment itself is NOT established here: these tests prove the contained
argv is built and the recovery state machine behaves, using fakes at the
spawn boundary. Actual isolation needs a runsc host (see reports/workstreams/R2.md).
"""

from __future__ import annotations

import sys

import json
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from settlement import exec_profile, launcher_runsc
from settlement.broker import BrokerOp
from settlement.common import IncompatibleVersion, SettlementError

DIGEST = "sha256:" + "a" * 64


def _ok_probe(**kw):
    detail = {"docker": "docker", "runsc": "/usr/bin/runsc", "runtimes": ["runsc"]}
    detail.update(kw.pop("detail", {}))
    return SimpleNamespace(available=True, reason="test runsc present",
                           detail=detail, **kw)


def _op(op_id="op1", version="exec-v1", **payload_kw):
    payload = {"profile": "gvisor", "argv": [sys.executable, "-c", "pass"],
               "timeout_ms": 5_000, "max_output_bytes": 65_536}
    payload.update(payload_kw)
    return BrokerOp(operation_id=op_id, effect="sandbox-exec",
                    payload=payload, execution_version=version)


def _worker_ok():
    return json.dumps({"status": "ok", "data": {}}).encode()


class _SpawnLog:
    def __init__(self):
        self.argv = []
        self.timeouts = []
        self.behaviours = []


def _install_popen(monkeypatch, log):
    def factory(argv, **kw):
        log.argv.append((list(argv), kw))
        assert log.behaviours, "unexpected spawn"
        script = log.behaviours.pop(0)
        fake = SimpleNamespace(killed=False, returncode=None)

        def communicate(timeout=None):
            log.timeouts.append(timeout)
            out, code = script()
            fake.returncode = code
            return out, b""

        def kill():
            fake.killed = True

        fake.communicate, fake.kill = communicate, kill
        return fake

    monkeypatch.setattr(subprocess, "Popen", factory)
    return log


@pytest.fixture()
def spawns(monkeypatch):
    return _install_popen(monkeypatch, _SpawnLog())


@pytest.fixture()
def run_calls(monkeypatch):
    calls = []
    outputs = {"inspect": "", "ps": ""}

    def fake_run(argv, **kw):
        calls.append((list(argv), kw))
        if "inspect" in argv:
            return SimpleNamespace(returncode=0, stdout=outputs["inspect"], stderr="")
        return SimpleNamespace(returncode=0, stdout=outputs["ps"], stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls, outputs


def test_refuses_on_this_host_without_spawning(tmp_path, spawns):
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    assert launcher.available is False
    with pytest.raises(IncompatibleVersion, match="[Gg]visor|runsc"):
        launcher.dispatch(_op())
    assert spawns.argv == []
    assert list((tmp_path / "runs").glob("*")) == []


def test_refusal_carries_probe_reason_and_never_spawns(monkeypatch, spawns):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor",
                        lambda: SimpleNamespace(available=False, reason="no runsc here"))
    with pytest.raises(IncompatibleVersion, match="no runsc here"):
        launcher_runsc.RunscLauncher(DIGEST).dispatch(_op())
    assert spawns.argv == []


def test_dispatch_spawns_contained_command_with_resource_deadline_plumbing(
        monkeypatch, spawns, tmp_path):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)
    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", "gw-secret")
    spawns.behaviours.append(lambda: (_worker_ok(), 0))
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    out = launcher.dispatch(
        _op("op-res", timeout_ms=9_000, cpu_seconds=4, memory_bytes=512 * 1024 * 1024))
    assert out.sent is True and out.receipt is not None
    assert out.receipt.outcome == "success"
    assert out.receipt.content["containment"] is True
    assert out.receipt.content["profile"] == "gvisor"
    assert len(spawns.argv) == 1
    argv, kw = spawns.argv[0]
    assert argv[:2] == ["docker", "run"]
    assert "--runtime=runsc" in argv
    assert DIGEST in argv
    assert "--network=none" in argv
    assert "--memory=536870912" in argv
    assert "cpu=4:4" in " ".join(argv)
    assert f"--name={launcher.native_id('op-res', 'exec-v1')}" in argv
    assert argv[-3:] == [sys.executable, "-c", "pass"]
    assert "gw-secret" not in " ".join(argv)
    assert kw.get("env", {}).get("SETTLEMENT_GATEWAY_KEY") is None
    assert spawns.timeouts == [pytest.approx(9.0)]


def test_recovery_roundtrip_records_single_spawn(monkeypatch, spawns, tmp_path):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)
    spawns.behaviours.append(lambda: (_worker_ok(), 0))
    first = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    assert first.dispatch(_op()).sent is True
    recovered = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    assert recovered.prior_send("op1") is True
    stored = recovered.read_result("op1")
    assert stored is not None and stored["outcome"] == "success"
    assert stored["containment"] is True
    again = recovered.dispatch(_op())
    assert again.sent is False and "prior-send" in again.refused_reason
    assert (tmp_path / "runs" / "op1_exec-v1_runsc.spawns").read_text().strip() == "1"
    assert recovered.prove_never_sent("op1") is False
    assert len(spawns.argv) == 1


def test_prove_never_sent_needs_clean_tracked_state(monkeypatch, tmp_path, run_calls):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    assert launcher.prove_never_sent("op-fresh") is True
    assert launcher_runsc.RunscLauncher(DIGEST).prove_never_sent("op-fresh") is False


def test_prove_never_sent_fails_closed_when_docker_unreachable(
        monkeypatch, tmp_path):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)

    def _boom(argv, **kw):
        raise FileNotFoundError("no docker here")

    monkeypatch.setattr(subprocess, "run", _boom)
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    assert launcher.prove_never_sent("op-fresh") is False


def test_timeout_stops_container_and_records_failure(
        monkeypatch, tmp_path, run_calls):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)
    calls, _ = run_calls
    states = {"n": 0}
    log = _SpawnLog()

    def factory(argv, **kw):
        log.argv.append((list(argv), kw))
        fake = SimpleNamespace(killed=False, returncode=None)

        def communicate(timeout=None):
            states["n"] += 1
            if states["n"] == 1:
                raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)
            fake.returncode = 0
            return _worker_ok(), b""

        fake.communicate = communicate
        return fake

    monkeypatch.setattr(subprocess, "Popen", factory)
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    out = launcher.dispatch(_op("op-slow", timeout_ms=1_000))
    assert out.sent is True
    assert out.receipt.content["data"]["timed_out"] is True
    assert out.receipt.outcome == "failure"
    stopped = [argv for argv, _ in calls if "stop" in argv]
    assert stopped and any("op-slow" in " ".join(argv) for argv in stopped)


def test_is_live_mid_flight_and_quiet_after_completion(
        monkeypatch, tmp_path, run_calls):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)
    _, outputs = run_calls
    outputs["inspect"] = "true\n"
    release = threading.Event()

    def factory(argv, **kw):
        fake = SimpleNamespace(returncode=None)

        def communicate(timeout=None):
            release.wait(timeout=30)
            fake.returncode = 0
            return _worker_ok(), b""

        fake.communicate = communicate
        return fake

    monkeypatch.setattr(subprocess, "Popen", factory)
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    holder = {}
    worker = threading.Thread(target=lambda: holder.setdefault(
        "out", launcher.dispatch(_op("op-live"))))
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not list((tmp_path / "runs").glob("op-live_*.container")):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert launcher.is_live("op-live") is True
    finally:
        release.set()
        worker.join(timeout=30)
    assert holder["out"].sent is True
    outputs["inspect"] = ""
    assert launcher.is_live("op-live") is False
    assert launcher.is_live("op-never") is False


def test_stop_reports_result_backed_completion_without_docker(
        monkeypatch, spawns, tmp_path, run_calls):
    monkeypatch.setattr(launcher_runsc, "probe_gvisor", _ok_probe)
    spawns.behaviours.append(lambda: (_worker_ok(), 0))
    calls, _ = run_calls
    launcher = launcher_runsc.RunscLauncher(DIGEST, run_dir=tmp_path / "runs")
    assert launcher.dispatch(_op("op-done")).sent is True
    assert launcher.stop("op-done") is True
    assert calls == []
    assert launcher.stop("op-never") is False


def test_exec_profile_gvisor_proceeds_past_admission_when_probe_succeeds(
        monkeypatch, spawns):
    monkeypatch.setattr(exec_profile, "probe_gvisor", _ok_probe)
    spawns.behaviours.append(lambda: (b"hello\n", 0))
    result = exec_profile.dispatch("gvisor", ["/bin/echo", "hello"], image=DIGEST)
    assert result.profile == "gvisor"
    assert result.containment is True
    assert result.returncode == 0
    assert result.stdout == "hello\n"
    argv, _ = spawns.argv[0]
    assert "--runtime=runsc" in argv and DIGEST in argv


def test_exec_profile_gvisor_requires_pinned_image(monkeypatch, spawns):
    monkeypatch.setattr(exec_profile, "probe_gvisor", _ok_probe)
    with pytest.raises(SettlementError):
        exec_profile.dispatch("gvisor", ["/bin/true"])
    with pytest.raises(SettlementError):
        exec_profile.dispatch("gvisor", ["/bin/true"], image="latest")
    assert spawns.argv == []


def test_exec_profile_gvisor_still_refuses_on_this_host(spawns):
    with pytest.raises(IncompatibleVersion):
        exec_profile.dispatch("gvisor", ["/bin/true"], image=DIGEST)
    assert spawns.argv == []
