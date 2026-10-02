"""R02-006/011/012 execution, containment and gateway-deadline repairs.

Scope: RunscLauncher, exec_profile run_gvisor bounded I/O plus detached
deadline supervision, and HttpGatewayAdapter billing/deadline decoding.
All container behavior runs against an injected executable docker shim
plus PATH-provided runsc stub: this host has no docker daemon, so real
containment is NOT established here. Each shim-dependent test restates
that bound where its assertion would otherwise imply isolation.
"""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from settlement import launcher_runsc
from settlement.broker import BrokerOp
from settlement.gateway import GatewayErrorKind, ModelRequest
from settlement.gateway_http import HttpGatewayAdapter

DIGEST = "sha256:" + "a" * 64
ROOT = Path(__file__).resolve().parents[1]

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
        fh.write(json.dumps({"t": time.time(), "pid": os.getpid(),
                             "ppid": os.getppid(), "argv": argv}) + "\n")

def fails(word):
    return word in _config().get("fail", [])

def main(argv):
    emit(argv)
    verb = argv[1] if len(argv) > 1 else ""
    if verb == "info":
        sys.stdout.write(json.dumps({"runsc": {"path": "/usr/bin/runsc"}}))
        return 0
    if verb == "run":
        name = ""
        for item in argv:
            if item.startswith("--name="):
                name = item.split("=", 1)[1]
        with open(os.path.join(state, name + ".pid"), "w") as fh:
            fh.write(str(os.getpid()))
        with open(os.path.join(state, name + ".state"), "w") as fh:
            fh.write("running")
        mode = _config().get("mode", "ok")
        if mode == "sleep":
            time.sleep(1000)
            return 0
        if mode == "flood":
            left = int(_config().get("flood_bytes", 20000000))
            out = sys.stdout.buffer
            block = b"x" * 65536
            while left > 0:
                out.write(block[:min(left, 65536)])
                left -= 65536
            out.flush()
            return 0
        sys.stdout.write('{"status": "ok", "data": {}}\n')
        sys.stdout.flush()
        return 0
    if verb in ("stop", "kill"):
        if fails(verb):
            return 1
        name = argv[-1]
        try:
            with open(os.path.join(state, name + ".pid")) as fh:
                target = int(fh.read().strip())
        except OSError:
            return 1
        try:
            os.kill(target, signal.SIGTERM if verb == "stop" else signal.SIGKILL)
        except OSError:
            pass
        with open(os.path.join(state, name + ".state"), "w") as fh:
            fh.write("stopped")
        return 0
    if verb == "inspect":
        if fails("inspect"):
            return 1
        name = argv[-1]
        try:
            with open(os.path.join(state, name + ".pid")) as fh:
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


def _configure(state: Path, mode: str = "ok", fail: list[str] | None = None,
               flood_bytes: int = 20000000) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "config.json").write_text(json.dumps(
        {"mode": mode, "fail": fail or [], "flood_bytes": flood_bytes}))


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


def _calls(state: Path) -> list[dict]:
    log = state / "calls.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _runs(state: Path) -> list[list[str]]:
    return [entry["argv"] for entry in _calls(state)
            if entry["argv"][1:2] == ["run"]]


def _op(op_id: str = "op1", version: str = "exec-v1", generation: int = 0,
         **payload_kw) -> BrokerOp:
    payload: dict = {"profile": "gvisor", "argv": ["/bin/true"],
                     "timeout_ms": 5_000, "max_output_bytes": 65_536}
    payload.update(payload_kw)
    return BrokerOp(operation_id=op_id, effect="sandbox-exec",
                    payload=payload, execution_version=version,
                    dispatch_generation=generation)


def _launcher(shim_env, **kw) -> launcher_runsc.RunscLauncher:
    args = {"image_digest": DIGEST, "run_dir": shim_env["run_dir"],
            "docker": shim_env["docker"]}
    args.update(kw)
    return launcher_runsc.RunscLauncher(**args)


def _inspect(shim_env, name: str) -> str | None:
    proc = subprocess.run(
        [shim_env["docker"], "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True, text=True, timeout=15, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


BROKER_CHILD = (
    "import sys\n"
    "from settlement.broker import BrokerOp\n"
    "from settlement.launcher_runsc import RunscLauncher\n"
    "launcher = RunscLauncher(sys.argv[1], run_dir=sys.argv[2], "
    "docker=sys.argv[3], grace_ms=1000)\n"
    "op = BrokerOp(operation_id='op-watch', effect='sandbox-exec', "
    "payload={'profile': 'gvisor', 'argv': ['/bin/sleep', '30'], "
    "'timeout_ms': 3000, 'max_output_bytes': 4096}, "
    "execution_version='exec-v1', dispatch_generation=1)\n"
    "launcher.dispatch(op)\n"
)


def test_supervisor_terminates_container_after_broker_death(shim_env):
    shim_env["configure"](mode="sleep")
    run_dir: Path = shim_env["run_dir"]
    name = "op-watch_exec-v1_runsc"
    child = subprocess.Popen(
        [sys.executable, "-c", BROKER_CHILD, DIGEST, str(run_dir),
         shim_env["docker"]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        start_new_session=True)
    try:
        started = time.monotonic()
        pid_file = shim_env["state"] / (name + ".pid")
        deadline = started + 15
        while not pid_file.exists():
            assert time.monotonic() < deadline, "shim container never started"
            assert child.poll() is None, "broker child died before spawning"
            time.sleep(0.02)
        states = sorted(run_dir.glob("op-watch_*.supervise.json"))
        assert len(states) == 1, "supervision state must be recorded in run_dir"
        recorded = json.loads(states[0].read_text())
        assert recorded["container"] == name
        assert recorded["deadline_epoch"] > time.time()
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)
        killed_at = time.time()
        stopped_at = None
        while time.monotonic() - started < 25:
            if _inspect(shim_env, name) == "false":
                stopped_at = time.monotonic()
                break
            time.sleep(0.05)
        assert stopped_at is not None, "independent supervisor never stopped it"
        assert stopped_at - started < 15, "termination escaped the admitted bound"
        stops = [entry for entry in _calls(shim_env["state"])
                 if entry["argv"][1:2] == ["stop"]]
        assert stops, "no docker stop was ever issued"
        assert all(entry["t"] > killed_at - 1 for entry in stops)
        assert all(entry["pid"] != child.pid for entry in stops)
        recovered = _launcher(shim_env)
        time.sleep(max(recorded["deadline_epoch"] - time.time(), 0) + 0.2)
        swept = recovered.enforce_deadlines()
        assert swept["stopped"] == [name]
        assert swept["unverified"] == []
        assert list(run_dir.glob("op-watch_*.supervise.json")) == []
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_output_flood_never_accumulates_on_host(shim_env):
    shim_env["configure"](mode="flood", flood_bytes=100000000)
    code = (
        "from settlement import exec_profile\n"
        f"result = exec_profile.run_gvisor(['/bin/true'], image={DIGEST!r}, "
        f"docker={shim_env['docker']!r}, max_output_bytes=1024, "
        "timeout_ms=60000, supervise=False)\n"
        "print('TRUNC', result.truncated, len(result.stdout.encode()))\n"
        "peak = next(int(line.split()[1]) for line in "
        "open('/proc/self/status') if line.startswith('VmHWM'))\n"
        "print('PEAK', peak)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        timeout=120, cwd=str(ROOT), check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert proc.returncode == 0, proc.stderr
    assert "TRUNC True 1024" in proc.stdout
    peak = int(proc.stdout.split("PEAK")[1].split()[0])
    assert peak < 80000, f"host buffered the flood: image peak {peak} KiB"


def test_scratch_bound_reaches_container_command(shim_env):
    launcher = _launcher(shim_env)
    out = launcher.dispatch(_op("op-scratch"))
    assert out.sent is True
    runs = _runs(shim_env["state"])
    assert len(runs) == 1
    assert "--storage-opt" in runs[0]
    idx = runs[0].index("--storage-opt")
    assert runs[0][idx + 1] == f"size={100 * 1024 * 1024}"


def test_stop_reports_uncertain_until_termination_established(shim_env):
    launcher = _launcher(shim_env)
    (shim_env["run_dir"]).mkdir(parents=True, exist_ok=True)
    (shim_env["run_dir"] / "op-hung_exec-v1_runsc.container").write_text("c-hung")
    shim_env["configure"](fail=["stop", "kill", "inspect"])
    assert launcher.stop("op-hung") is False
    assert (shim_env["run_dir"] / "op-hung_exec-v1_runsc.container").exists()
    shim_env["configure"]()
    assert launcher.stop("op-missing") is False


def test_stop_uses_kill_fallback_and_clears_tracking(shim_env):
    shim_env["configure"](mode="sleep")
    launcher = _launcher(shim_env)
    holder: dict = {}

    def _flight() -> None:
        holder["out"] = launcher.dispatch(
            _op("op-kill", timeout_ms=30_000, max_output_bytes=1024))

    worker = threading.Thread(target=_flight, daemon=True)
    worker.start()
    try:
        name = "op-kill_exec-v1_runsc"
        deadline = time.monotonic() + 15
        while not (shim_env["state"] / (name + ".pid")).exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        shim_env["configure"](mode="sleep", fail=["stop"])
        assert launcher.stop("op-kill") is True
        kinds = [entry["argv"][1] for entry in _calls(shim_env["state"])]
        assert "kill" in kinds
        assert list(shim_env["run_dir"].glob("op-kill_*.container")) == []
    finally:
        shim_env["configure"](mode="sleep")
        worker.join(timeout=60)


def test_stale_generation_is_refused_without_spawn(shim_env):
    shim_env["configure"](mode="sleep")
    launcher = _launcher(shim_env)
    holder: dict = {}

    def _flight() -> None:
        holder["out"] = launcher.dispatch(_op("op-gen", generation=1))

    worker = threading.Thread(target=_flight, daemon=True)
    worker.start()
    try:
        name = "op-gen_exec-v1_runsc"
        deadline = time.monotonic() + 15
        while not (shim_env["state"] / (name + ".pid")).exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert launcher.dispatch(_op("op-gen", generation=1)).sent is False
        newer = launcher.dispatch(_op("op-gen", generation=3))
        assert newer.sent is False
        assert newer.refused_reason == "superseded-claim"
        assert (shim_env["run_dir"] / "op-gen_exec-v1_runsc.gen").read_text() == "3"
        stale = launcher.dispatch(_op("op-gen", generation=0))
        assert stale.sent is False
        assert len(_runs(shim_env["state"])) == 1
    finally:
        assert launcher.stop("op-gen") is True
        worker.join(timeout=60)
    assert holder["out"].sent is True


def test_fresh_claim_below_recorded_generation_never_spawns(shim_env):
    run_dir: Path = shim_env["run_dir"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "op-old_exec-v1_runsc.gen").write_text("5")
    launcher = _launcher(shim_env)
    refused = launcher.dispatch(_op("op-old", generation=2))
    assert refused.sent is False
    assert refused.refused_reason == "superseded-generation"
    assert _runs(shim_env["state"]) == []
    assert list(run_dir.glob("op-old_*.container")) == []


def test_artifact_staging_mounts_controlled_paths_only(shim_env):
    launcher = _launcher(shim_env)
    dest = launcher.stage_input("op-art", "exec-v1", "cases/input.json", b"{}")
    assert dest.is_file()
    out = launcher.dispatch(_op("op-art", argv=["/work/inputs"]))
    assert out.sent is True
    runs = _runs(shim_env["state"])
    assert len(runs) == 1
    volumes = [runs[0][idx + 1] for idx, item in enumerate(runs[0][:-1])
               if item == "-v"]
    assert len(volumes) == 2
    assert volumes[0].endswith(":/work/inputs:ro")
    assert volumes[1].endswith(":/work/outputs:rw")
    hosts = [spec.split(":")[0] for spec in volumes]
    assert all(Path(host).is_relative_to(shim_env["run_dir"]) for host in hosts)
    for bad in ("../escape.json", "/absolute.json", ""):
        with pytest.raises(ValueError):
            launcher.stage_input("op-art", "exec-v1", bad, b"x")
    assert not (shim_env["run_dir"].parent / "escape.json").exists()


def test_unstaged_operation_mounts_nothing(shim_env):
    launcher = _launcher(shim_env)
    assert launcher.dispatch(_op("op-plain")).sent is True
    assert "-v" not in _runs(shim_env["state"])[0]


def test_enforce_deadlines_sweeps_only_expired_unresolved(shim_env):
    launcher = _launcher(shim_env)
    run_dir: Path = shim_env["run_dir"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "op-done_exec-v1_runsc.result.json").write_text("{}")
    (run_dir / "op-done_exec-v1_runsc.supervise.json").write_text(json.dumps(
        {"container": "c-done", "operation_id": "op-done",
         "deadline_epoch": time.time() - 10, "grace_s": 1}))
    swept = launcher.enforce_deadlines()
    assert swept == {"stopped": [], "unverified": []}
    assert list(run_dir.glob("op-done_*.supervise.json")) == []
    verbs = [entry["argv"][1] for entry in _calls(shim_env["state"])]
    assert verbs == ["info"]
    (run_dir / "op-live_exec-v1_runsc.supervise.json").write_text(json.dumps(
        {"container": "c-live", "operation_id": "op-live",
         "deadline_epoch": time.time() + 3600, "grace_s": 1}))
    swept = launcher.enforce_deadlines()
    assert swept == {"stopped": [], "unverified": []}
    assert (run_dir / "op-live_exec-v1_runsc.supervise.json").exists()


def _body(choices_text: str, usage: dict) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"content": choices_text},
                      "finish_reason": "stop"}],
         "model": "probe-model", "usage": usage}).encode()


def test_unknown_billing_decode_keeps_zero_unbilled():
    response = HttpGatewayAdapter("http://unused")._decode_body(
        _body("answer", {"prompt_tokens": 1000, "completion_tokens": 500}), "op")
    assert response.usage.input_tokens + response.usage.output_tokens == 1500
    assert response.usage.charge_units == 0
    assert response.usage.billed is False


def test_explicit_priced_charge_decode_marks_billed():
    response = HttpGatewayAdapter("http://unused")._decode_body(
        _body("answer", {"prompt_tokens": 1000, "completion_tokens": 500,
                         "charge_units": 7}),
        "op")
    assert response.usage.charge_units == 7
    assert response.usage.billed is True


def test_noncanonical_charge_scale_is_protocol_error():
    result = HttpGatewayAdapter("http://unused")._decode_body(
        _body("answer", {"prompt_tokens": 1, "completion_tokens": 1,
                         "charge_units": 7, "charge_scale": 100}),
        "op")
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.retryable is False


def test_malformed_charge_decode_is_protocol_error():
    result = HttpGatewayAdapter("http://unused")._decode_body(
        _body("answer", {"prompt_tokens": 1, "completion_tokens": 1,
                         "charge_units": "seven"}),
        "op")
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.retryable is False


def test_header_wait_is_bounded_by_absolute_deadline():
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
        result = adapter.infer(ModelRequest("probe", (), 1, 200,
                                            operation_id="op-hdr"))
        elapsed = time.monotonic() - started
        assert result.kind == GatewayErrorKind.TIMEOUT
        assert result.retryable is True
        assert elapsed < 0.8, f"header wait escaped the budget: {elapsed:.2f}s"
        assert elapsed >= 0.1, "deadline returned before the budget elapsed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cancelled_inference_stays_distinct_from_timeout():
    adapter = HttpGatewayAdapter(endpoint="http://127.0.0.1:1", api_key="x")
    request = ModelRequest("m", ({"role": "user", "content": "hi"},),
                           8, 10_000, operation_id="op-cancel")
    adapter.cancel("op-cancel")
    result = adapter.infer(request)
    assert result.kind == GatewayErrorKind.CANCELLED
    assert adapter.cancel_status("op-cancel") == "confirmed"


def test_model_token_budget_defaults_without_env(monkeypatch):
    from settlement import experiment

    monkeypatch.delenv("SETTLEMENT_MODEL_TOKENS", raising=False)
    assert experiment.model_token_budget() == experiment.MODEL_TOKENS == 512


def test_model_token_budget_honors_env_override(monkeypatch):
    from settlement import experiment

    monkeypatch.setenv("SETTLEMENT_MODEL_TOKENS", "8192")
    assert experiment.model_token_budget() == 8192


def test_model_token_budget_refuses_bad_values(monkeypatch):
    from settlement import experiment
    from settlement.common import SettlementError

    for bad in ("nope", "0", "-5"):
        monkeypatch.setenv("SETTLEMENT_MODEL_TOKENS", bad)
        try:
            experiment.model_token_budget()
        except SettlementError:
            continue
        raise AssertionError(f"bad token budget {bad!r} was not refused")


def test_packet_budget_defaults_without_env(monkeypatch):
    from settlement import development

    monkeypatch.delenv("SETTLEMENT_PACKET_BUDGET_CHARS", raising=False)
    assert development.packet_budget() == {"input_chars": 24000, "output_reserve": 2000}


def test_packet_budget_honors_env_override(monkeypatch):
    from settlement import development

    monkeypatch.setenv("SETTLEMENT_PACKET_BUDGET_CHARS", "65536")
    assert development.packet_budget() == {"input_chars": 65536, "output_reserve": 2000}


def test_packet_budget_refuses_bad_values(monkeypatch):
    from settlement import development
    from settlement.common import SettlementError

    for bad in ("nope", "0", "-100"):
        monkeypatch.setenv("SETTLEMENT_PACKET_BUDGET_CHARS", bad)
        try:
            development.packet_budget()
        except SettlementError:
            continue
        raise AssertionError(f"bad packet budget {bad!r} was not refused")


def _accounting_cmd(payload):
    from settlement.common import Command

    _accounting_cmd.seq += 1
    return Command(request_id=f"eng-acct-{_accounting_cmd.seq}", payload=payload)


_accounting_cmd.seq = 0


def _seed_unbilled_op(dsn):
    from settlement import store

    store.seed_allocation(
        dsn, _accounting_cmd({"allocation_id": "eng-acct-a", "domain": "cpu",
                              "authorized": 5000}))
    store.prepare_operation(
        dsn, _accounting_cmd({"operation_id": "eng-acct-unbilled",
                              "allocation_id": "eng-acct-a",
                              "reservation_id": "res-eng-acct-unbilled",
                              "exposure": 1000, "operation": {"kind": "model"}}))
    store.admit_receipt(
        dsn, _accounting_cmd({"operation_id": "eng-acct-unbilled",
                              "receipt_identity": "rc-eng-acct-unbilled",
                              "content": {"text": "done", "usage": {
                                  "input_tokens": 10, "output_tokens": 20,
                                  "charge_units": 0, "billed": False}},
                              "outcome": "success"}))


def _seed_billed_op(dsn):
    from settlement import store

    store.seed_allocation(
        dsn, _accounting_cmd({"allocation_id": "eng-acct-b", "domain": "cpu",
                              "authorized": 5000}))
    store.prepare_operation(
        dsn, _accounting_cmd({"operation_id": "eng-acct-billed",
                              "allocation_id": "eng-acct-b",
                              "reservation_id": "res-eng-acct-billed",
                              "exposure": 1000, "operation": {"kind": "model"}}))
    store.admit_receipt(
        dsn, _accounting_cmd({"operation_id": "eng-acct-billed",
                              "receipt_identity": "rc-eng-acct-billed",
                              "content": {"text": "done", "usage": {
                                  "input_tokens": 5, "output_tokens": 7,
                                  "charge_units": 42, "billed": True}},
                              "outcome": "success", "actual_cost": 42}))


def test_unbilled_settlement_reports_conservative_debit(migrated_db):
    from settlement import experiment, store

    dsn = migrated_db
    _seed_unbilled_op(dsn)
    status = store.allocation_status(dsn, "eng-acct-a")
    assert (status["consumed"], status["reserved"]) == (1000, 0)
    entry = experiment._op_accounting(dsn, "eng-acct-unbilled")
    assert entry["reserved"] == 1000
    assert entry["settled"] == status["consumed"] == 1000
    assert entry["unresolved"] == 0
    assert entry["billed"] is False
    assert entry["provider_charge_units"] is None
    assert entry["tokens"] == {"input": 10, "output": 20}


def test_billed_settlement_reports_verified_charge(migrated_db):
    from settlement import experiment, store

    dsn = migrated_db
    _seed_billed_op(dsn)
    status = store.allocation_status(dsn, "eng-acct-b")
    assert (status["consumed"], status["reserved"]) == (42, 0)
    entry = experiment._op_accounting(dsn, "eng-acct-billed")
    assert entry["reserved"] == 1000
    assert entry["settled"] == status["consumed"] == 42
    assert entry["unresolved"] == 0
    assert entry["billed"] is True
    assert entry["provider_charge_units"] == 42
    assert entry["tokens"] == {"input": 5, "output": 7}
