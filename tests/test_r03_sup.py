"""R03-001/002 supervision and generation-fence repairs.

Scope: fail-closed supervision in exec_profile.run_gvisor, verified-stop
tracking retention in RunscLauncher, and the final pre-send generation fence.
All container behavior runs against an executable docker shim plus a runsc
stub on PATH: this host has no docker daemon, so real containment is NOT
established here. Each shim-dependent test restates that bound where its
assertion would otherwise imply isolation.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from settlement import exec_profile, launcher_runsc
from settlement.broker import BrokerOp, _sandbox_exposure

DIGEST = "sha256:" + "a" * 64

SHIM = r"""#!/usr/bin/env python3
import json, os, signal, sys, time
state = __STATE__

def _config():
    try:
        with open(os.path.join(state, "config.json")) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}

def emit(argv):
    with open(os.path.join(state, "calls.log"), "a") as fh:
        fh.write(json.dumps(argv) + "\n")

def main(argv):
    emit(argv)
    verb = argv[1] if len(argv) > 1 else ""
    if verb == "info":
        sys.stdout.write('{"runsc": {"path": "/usr/bin/runsc"}}')
        return 0
    if verb == "run":
        name = ""
        for item in argv:
            if item.startswith("--name="):
                name = item.split("=", 1)[1]
        with open(os.path.join(state, name + ".pid"), "w") as fh:
            fh.write(str(os.getpid()))
        if _config().get("mode") == "sleep":
            time.sleep(1000)
            return 0
        sys.stdout.write('{"status": "ok", "data": {}}\n')
        sys.stdout.flush()
        return 0
    if verb in ("stop", "kill"):
        if verb in _config().get("fail", []):
            return 1
        try:
            with open(os.path.join(state, argv[-1] + ".pid")) as fh:
                target = int(fh.read().strip())
        except OSError:
            return 1
        try:
            os.kill(target, signal.SIGTERM if verb == "stop" else signal.SIGKILL)
        except OSError:
            pass
        return 0
    if verb == "inspect":
        if "inspect" in _config().get("fail", []):
            return 1
        try:
            with open(os.path.join(state, argv[-1] + ".pid")) as fh:
                target = int(fh.read().strip())
        except OSError:
            return 1
        try:
            os.kill(target, 0)
            sys.stdout.write("true\n")
        except OSError:
            sys.stdout.write("false\n")
        return 0
    if verb == "ps":
        return 0
    return 1

raise SystemExit(main(sys.argv))
"""


def _configure(state, mode="ok", fail=()):
    (state / "config.json").write_text(json.dumps({"mode": mode, "fail": list(fail)}))


@pytest.fixture()
def shim_env(tmp_path, monkeypatch):
    binder = tmp_path / "bin"
    binder.mkdir()
    state = tmp_path / "shim-state"
    state.mkdir()
    docker = binder / "docker"
    docker.write_text(SHIM.replace("__STATE__", json.dumps(str(state))))
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    runsc = binder / "runsc"
    runsc.write_text("#!/bin/sh\nexit 0\n")
    runsc.chmod(runsc.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", str(binder) + os.pathsep + os.environ.get("PATH", ""))
    _configure(state)
    return {"docker": str(docker), "state": state, "run_dir": tmp_path / "runs",
            "configure": lambda **kw: _configure(state, **kw)}


def _op(generation=0, timeout_ms=5_000):
    return BrokerOp(operation_id="sup-op", effect="sandbox-exec",
                    execution_version="v1", dispatch_generation=generation,
                    payload={"profile": "gvisor", "argv": ["job"],
                             "timeout_ms": timeout_ms, "max_output_bytes": 1024})


def _launcher(shim_env):
    return launcher_runsc.RunscLauncher(
        DIGEST, run_dir=shim_env["run_dir"], docker=shim_env["docker"])


def _verbs(shim_env):
    log = shim_env["state"] / "calls.log"
    if not log.exists():
        return []
    return [json.loads(line)[1] for line in log.read_text().splitlines()]


def test_supervision_unavailable_fences_container(shim_env, monkeypatch):
    # No real container is involved beyond the shim process: proves the
    # orchestration refuses unsupervised success and issues the stop sequence.
    launcher = _launcher(shim_env)
    monkeypatch.setattr(exec_profile, "spawn_supervisor", lambda *a: None)
    outcome = launcher.dispatch(_op())
    assert outcome.sent and outcome.receipt.outcome == "failure"
    stored = launcher.read_result("sup-op")
    assert stored["data"]["supervised"] is False
    assert stored["parse"] == "supervision-unavailable"
    assert stored["outcome"] == "failure"
    verbs = _verbs(shim_env)
    assert "run" in verbs and "stop" in verbs and "inspect" in verbs


def test_unstoppable_container_retained_then_released(shim_env):
    # No real container is involved beyond the shim process: proves retention
    # while the stop sequence cannot verify, and release once it can.
    shim_env["configure"](mode="sleep", fail=("stop", "kill", "inspect"))
    launcher = _launcher(shim_env)
    outcome = launcher.dispatch(_op(timeout_ms=500))
    assert outcome.receipt.outcome == "failure"
    assert launcher.read_result("sup-op")["data"]["timed_out"] is True
    assert launcher._tracked("sup-op")
    assert launcher.is_live("sup-op") is True
    shim_env["configure"](mode="ok", fail=())
    report = launcher.enforce_deadlines()
    assert not launcher._tracked("sup-op")
    assert launcher.is_live("sup-op") is False
    assert report["stopped"]


def test_generation_fence_end_to_end(shim_env, monkeypatch):
    # No real container is involved beyond the shim process: proves the stale
    # sender never reaches the executor once a newer generation claims, and the
    # newer generation resumes afterward. Only the interleaving is scripted.
    launcher = _launcher(shim_env)
    original = launcher._supervise_state

    def interleave(*args):
        launcher.dispatch(_op(generation=2))
        return original(*args)

    monkeypatch.setattr(launcher, "_supervise_state", interleave)
    old = launcher.dispatch(_op(generation=1))
    assert not old.sent and old.refused_reason == "superseded-generation"
    monkeypatch.setattr(launcher, "_supervise_state", original)
    resumed = launcher.dispatch(_op(generation=2))
    assert resumed.sent and resumed.receipt.outcome == "success"
    assert _verbs(shim_env).count("run") == 1


def test_sandbox_exposure_covers_stop_settle():
    units, kind = _sandbox_exposure({"timeout_ms": 30_000}, 0)
    assert kind == "hard-ceiling"
    assert units == 30 + exec_profile.STOP_SETTLE_S + 1
