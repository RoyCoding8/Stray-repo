"""Local-process launcher: bounded subprocess execution for diagnosis and tests.

Identity is derived from the operation, never fresh randomness: recovery
inspects the run directory (pid and result files) before any new spawn.
Every result is labeled containment=False. Worker bytes are parsed as typed
JSON only, never executed. Stops use process-group kill.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .broker import BrokerOp, LaunchOutcome, ReceiptProposal
from .exec_profile import scrub_env

PROFILE = "local-process"


class WorkerOutput(BaseModel):
    status: str
    data: dict[str, Any] = {}
    error: str = ""

    model_config = {"extra": "forbid"}


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def native_id(operation_id: str, execution_version: str) -> str:
    return f"{_sanitize(operation_id)}_{_sanitize(execution_version or 'exec-default')}"


class LocalLauncher:
    launcher_id = "local-1"
    profile = PROFILE
    idempotent_resend = False

    def __init__(self, run_dir: str | Path, grace_ms: int = 2000) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.grace_ms = grace_ms

    def native_id(self, operation_id: str, execution_version: str) -> str:
        return native_id(operation_id, execution_version)

    def _paths(self, operation_id: str, execution_version: str) -> dict[str, Path]:
        base = self.run_dir / self.native_id(operation_id, execution_version)
        return {"pid": base.with_suffix(".pid"), "result": base.with_suffix(".result.json"),
                "spawns": base.with_suffix(".spawns")}

    def prior_send(self, operation_id: str) -> bool:
        if any(self.run_dir.glob(f"{_sanitize(operation_id)}_*.pid")):
            return True
        return self.read_result(operation_id) is not None

    def live_ids(self) -> list[str]:
        alive = []
        for pid_file in self.run_dir.glob("*.pid"):
            try:
                os.kill(int(pid_file.read_text().strip()), 0)
                alive.append(pid_file.stem)
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                continue
        return sorted(alive)

    def is_live(self, operation_id: str) -> bool:
        for pid_file in self.run_dir.glob(f"{_sanitize(operation_id)}_*.pid"):
            try:
                os.kill(int(pid_file.read_text().strip()), 0)
                return True
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                continue
        return False

    def read_result(self, operation_id: str) -> dict[str, Any] | None:
        for result_file in self.run_dir.glob(f"{_sanitize(operation_id)}_*.result.json"):
            try:
                return json.loads(result_file.read_text())
            except (ValueError, OSError):
                return {"outcome": "unknown", "parse": "stored-result-unreadable"}
        return None

    def _pgid_dead(self, pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return False
        except (ProcessLookupError, PermissionError, OSError):
            return True

    def stop(self, operation_id: str) -> bool:
        targets = []
        for pid_file in self.run_dir.glob(f"{_sanitize(operation_id)}_*.pid"):
            try:
                targets.append(int(pid_file.read_text().strip()))
            except (ValueError, OSError):
                continue
        if not targets:
            return self.read_result(operation_id) is not None
        for pgid in targets:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                continue
        deadline = time.monotonic() + self.grace_ms / 1000
        pending = [pgid for pgid in targets if not self._pgid_dead(pgid)]
        while pending and time.monotonic() < deadline:
            time.sleep(0.05)
            pending = [pgid for pgid in pending if not self._pgid_dead(pgid)]
        for pgid in pending:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                continue
        return all(self._pgid_dead(pgid) for pgid in targets)

    def _claim(self, pid_path: Path) -> bool:
        try:
            fd = os.open(pid_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.close(fd)
            return True
        except FileExistsError:
            return False
        except OSError:
            return False

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        paths = self._paths(op.operation_id, op.execution_version)
        if paths["result"].exists():
            return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
        if not self._claim(paths["pid"]):
            return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
        payload = op.payload
        timeout_ms = int(payload.get("timeout_ms", 30_000))
        max_bytes = int(payload.get("max_output_bytes", 1_048_576))
        argv = list(payload["argv"])
        try:
            seen = int(paths["spawns"].read_text().strip()) if paths["spawns"].exists() else 0
        except (ValueError, OSError):
            seen = 0
        paths["spawns"].write_text(str(seen + 1))
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=scrub_env({"SETTLEMENT_OPERATION": op.operation_id}),
                preexec_fn=_child_setup(payload),
            )
        except OSError as exc:
            return LaunchOutcome(sent=True, receipt=ReceiptProposal(
                receipt_identity=f"local:{paths['result'].stem}", content=_base(False, argv, {
                    "spawn_error": str(exc)}), outcome="failure", provenance=self.launcher_id))
        paths["pid"].write_text(str(proc.pid))
        try:
            raw_out, raw_err = proc.communicate(timeout=timeout_ms / 1000)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                raw_out, raw_err = proc.communicate(timeout=self.grace_ms / 1000)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
                raw_out, raw_err = proc.communicate()
            timed_out = True
        wall_ms = int((time.monotonic() - started) * 1000)
        out, out_cut = _cap(raw_out or b"", max_bytes)
        err, err_cut = _cap(raw_err or b"", max_bytes)
        content = _interpret(proc.returncode or 0, out.decode("utf-8", "replace"),
                             err.decode("utf-8", "replace"), out_cut or err_cut,
                             timed_out, wall_ms, argv)
        paths["result"].write_text(json.dumps({"outcome": content["_verdict"], **content}))
        try:
            paths["pid"].unlink()
        except OSError:
            pass
        receipt = ReceiptProposal(
            receipt_identity=f"local:{paths['result'].stem}", content=content,
            outcome=content["_verdict"], provenance=self.launcher_id)
        return LaunchOutcome(sent=True, receipt=receipt)


def _child_setup(payload: dict[str, Any]):
    def _setup() -> None:
        import resource

        cpu = payload.get("cpu_seconds")
        mem = payload.get("memory_bytes")
        if cpu is not None:
            resource.setrlimit(resource.RLIMIT_CPU, (int(cpu), int(cpu)))
        if mem is not None:
            resource.setrlimit(resource.RLIMIT_AS, (int(mem), int(mem)))
        os.setsid()

    return _setup


def _cap(raw: bytes, limit: int) -> tuple[bytes, bool]:
    if len(raw) > limit:
        return raw[:limit], True
    return raw, False


def _base(containment: bool, argv: list[str], data: dict[str, Any]) -> dict[str, Any]:
    return {"containment": containment, "profile": PROFILE, "argv": argv, "data": data}


def _interpret(returncode: int, stdout: str, stderr: str, truncated: bool,
               timed_out: bool, wall_ms: int, argv: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {"stdout": stdout, "returncode": returncode,
                            "timed_out": timed_out, "wall_ms": wall_ms}
    if stderr:
        data["stderr"] = stderr
    verdict = "failure"
    parse = "rejected"
    if not timed_out and returncode == 0 and not stdout.strip():
        parse = "empty"
        verdict = "success"
    elif not timed_out and returncode == 0:
        try:
            worker = WorkerOutput.model_validate(json.loads(stdout))
            if worker.status in ("ok", "error"):
                parse = "typed-json"
                data = {"worker": worker.model_dump(), "timed_out": timed_out, "wall_ms": wall_ms}
                verdict = "success" if worker.status == "ok" else "failure"
        except (ValueError, TypeError):
            parse = "rejected"
    content = _base(False, argv, data)
    content.update({"truncated": truncated, "parse": parse, "_verdict": verdict})
    return content
