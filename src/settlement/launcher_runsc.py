"""gVisor/runsc launcher: probe-gated contained execution, broker interface.

Dispatch refuses with IncompatibleVersion while the probe reports the host
incompatible. When the probe succeeds it runs the operation under
``docker --runtime=runsc`` with the pinned image digest, scrubbed
environment, resource flags and a host-side deadline, then records a typed
receipt. Identity is operation-derived, never fresh randomness: recovery
inspects run-dir state and docker before any new spawn.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .broker import BrokerOp, LaunchOutcome, ReceiptProposal
from .common import IncompatibleVersion
from .exec_profile import (
    docker_container_running,
    probe_gvisor,
    run_gvisor,
    terminate_verified,
)
from .launcher_local import WorkerOutput

PROFILE = "gvisor"
RUNTIME = "runsc"
WORK_INPUTS = "/work/inputs"
WORK_OUTPUTS = "/work/outputs"


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _check_relpath(relpath: str) -> str:
    if (not isinstance(relpath, str) or not relpath or relpath.startswith("/")
            or ".." in relpath.split("/")):
        raise ValueError(f"refusing unsafe artifact relpath {relpath!r}")
    return relpath


def _interpret(result: Any, argv: list[str], image: str, runtime: str,
               container: str, timeout_ms: int) -> dict[str, Any]:
    data: dict[str, Any] = {"stdout": result.stdout, "returncode": result.returncode,
                            "timed_out": result.timed_out, "wall_ms": result.wall_ms,
                            "image_digest": image, "runtime": runtime,
                            "container": container, "timeout_ms": timeout_ms,
                            "supervised": bool(result.detail.get("supervised", False)),
                            "stop_verified": result.detail.get("stop_verified", True)}
    if result.stderr:
        data["stderr"] = result.stderr
    verdict, parse = "failure", "rejected"
    error = result.detail.get("error") if isinstance(result.detail, dict) else None
    if error is not None:
        parse = str(error)
    elif result.returncode is None:
        parse = "spawn-failed"
    elif not result.timed_out and result.returncode == 0 and not result.stdout.strip():
        parse, verdict = "empty", "success"
    elif not result.timed_out and result.returncode == 0:
        try:
            worker = WorkerOutput.model_validate(json.loads(result.stdout))
            if worker.status in ("ok", "error"):
                parse = "typed-json"
                data = {"worker": worker.model_dump(), "timed_out": result.timed_out,
                        "wall_ms": result.wall_ms, "image_digest": image,
                        "runtime": runtime, "container": container,
                        "timeout_ms": timeout_ms}
                verdict = "success" if worker.status == "ok" else "failure"
        except (ValueError, TypeError):
            parse = "rejected"
    content = {"containment": True, "profile": PROFILE, "argv": argv, "data": data}
    content.update({"truncated": result.truncated, "parse": parse, "_verdict": verdict})
    return content


class RunscLauncher:
    launcher_id = "runsc-1"
    profile = PROFILE
    idempotent_resend = False

    def __init__(self, image_digest: str, runtime: str = RUNTIME,
                 network: str = "none", scratch_bytes: int = 100 * 1024 * 1024,
                 run_dir: str | Path | None = None, grace_ms: int = 2000,
                 docker: str = "docker",
                 image_python: str | None = None) -> None:
        if not (isinstance(image_digest, str) and image_digest.startswith("sha256:")):
            raise ValueError("image_digest must be a pinned sha256 digest")
        self.image_digest = image_digest
        self.runtime = runtime
        self.network = network
        self.scratch_bytes = scratch_bytes
        self.grace_ms = grace_ms
        self.image_python = image_python or "python3"
        self.run_dir = Path(run_dir) if run_dir is not None else None
        if self.run_dir is not None:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        self._probe = probe_gvisor()
        detail = getattr(self._probe, "detail", None) or {}
        self.docker = docker if docker != "docker" else detail.get("docker") or "docker"

    @property
    def reason(self) -> str:
        return self._probe.reason

    @property
    def available(self) -> bool:
        return self._probe.available

    def native_id(self, operation_id: str, execution_version: str) -> str:
        return f"{_sanitize(operation_id)}_{_sanitize(execution_version or 'exec-default')}_{RUNTIME}"

    def declaration(self) -> dict[str, Any]:
        return {"profile": PROFILE, "runtime": self.runtime, "image_digest": self.image_digest,
                "network": self.network, "scratch_bytes": self.scratch_bytes,
                "inputs": "read-only", "credentials": "none"}

    def _paths(self, operation_id: str, execution_version: str) -> dict[str, Path]:
        base = self.run_dir / self.native_id(operation_id, execution_version)
        return {"container": base.with_suffix(".container"),
                "result": base.with_suffix(".result.json"),
                "spawns": base.with_suffix(".spawns"),
                "generation": base.with_suffix(".gen"),
                "supervise": base.with_suffix(".supervise.json"),
                "work": base.with_suffix(".work")}

    def _recorded_generation(self, path: Path) -> int | None:
        try:
            return int(path.read_text().strip())
        except (ValueError, OSError):
            return None

    def _work_dirs(self, operation_id: str,
                   execution_version: str) -> dict[str, Path]:
        work = self._paths(operation_id, execution_version)["work"]
        return {"work": work, "inputs": work / "inputs", "outputs": work / "outputs"}

    def stage_input(self, operation_id: str, execution_version: str,
                    relpath: str, data: bytes) -> Path:
        if self.run_dir is None:
            raise ValueError("artifact staging needs a run directory")
        if len(data) > self.scratch_bytes:
            raise ValueError("staged input exceeds the container scratch bound")
        target = self._work_dirs(operation_id, execution_version)["inputs"]
        target.mkdir(parents=True, exist_ok=True)
        dest = target / _check_relpath(relpath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def exec_dirs(self, operation_id: str,
                  execution_version: str) -> tuple[str, str]:
        return (WORK_INPUTS, WORK_OUTPUTS)

    def staged_python(self) -> str:
        return self.image_python

    def read_output(self, operation_id: str, execution_version: str,
                    relpath: str) -> bytes:
        return (self._work_dirs(operation_id, execution_version)["outputs"]
                / _check_relpath(relpath)).read_bytes()

    def _mounts(self, operation_id: str,
                execution_version: str) -> list[tuple[str, str, bool]]:
        if self.run_dir is None:
            return []
        dirs = self._work_dirs(operation_id, execution_version)
        if not dirs["work"].exists():
            return []
        dirs["inputs"].mkdir(parents=True, exist_ok=True)
        dirs["outputs"].mkdir(parents=True, exist_ok=True)
        return [(str(dirs["inputs"]), WORK_INPUTS, True),
                (str(dirs["outputs"]), WORK_OUTPUTS, False)]

    def _supervise_state(self, operation_id: str, execution_version: str,
                         name: str, timeout_ms: int) -> dict[str, Any]:
        grace_s = max(int(self.grace_ms // 1000), 1)
        return {"container": name, "operation_id": operation_id,
                "execution_version": execution_version,
                "deadline_epoch": time.time() + timeout_ms / 1000 + grace_s,
                "grace_s": grace_s}

    def _drop_supervise(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    def enforce_deadlines(self) -> dict[str, list[str]]:
        stopped: list[str] = []
        unverified: list[str] = []
        if self.run_dir is None or not self.run_dir.is_dir():
            return {"stopped": stopped, "unverified": unverified}
        for state_file in sorted(self.run_dir.glob("*.supervise.json")):
            try:
                state = json.loads(state_file.read_text())
            except (ValueError, OSError):
                unverified.append(state_file.name)
                continue
            operation_id = str(state.get("operation_id", ""))
            retained = bool(self._results(operation_id)) and bool(
                self._tracked(operation_id))
            if self._results(operation_id) and not retained:
                self._drop_supervise(state_file)
                continue
            try:
                expired = time.time() >= float(state.get("deadline_epoch", 0))
            except (TypeError, ValueError):
                unverified.append(state_file.name)
                continue
            if not expired and not retained:
                continue
            final = terminate_verified(
                self.docker, str(state.get("container", "")),
                int(state.get("grace_s", 1)))
            if final is False:
                self._drop_supervise(state_file)
                if retained:
                    for track in self._tracked(operation_id):
                        try:
                            track.unlink()
                        except OSError:
                            pass
                stopped.append(str(state.get("container", "")))
            else:
                unverified.append(str(state.get("container", "")))
        return {"stopped": stopped, "unverified": unverified}

    def _tracked(self, operation_id: str) -> list[Path]:
        if self.run_dir is None:
            return []
        return sorted(self.run_dir.glob(f"{_sanitize(operation_id)}_*.container"))

    def _results(self, operation_id: str) -> list[Path]:
        if self.run_dir is None:
            return []
        return sorted(self.run_dir.glob(f"{_sanitize(operation_id)}_*.result.json"))

    def _ps_names(self, prefix: str) -> list[str] | None:
        try:
            proc = subprocess.run(
                [self.docker, "ps", "-q", "--filter", f"name={prefix}"],
                capture_output=True, text=True, timeout=15)
        except (subprocess.SubprocessError, OSError):
            return None
        if proc.returncode != 0:
            return None
        return [line for line in proc.stdout.split() if line]

    def _tracked_names(self, operation_id: str) -> list[str]:
        names = []
        for track in self._tracked(operation_id):
            try:
                name = track.read_text().strip()
            except OSError:
                return [""]
            names.append(name)
        return names

    def prior_send(self, operation_id: str) -> bool:
        if self.run_dir is not None:
            return bool(self._tracked(operation_id) or self._results(operation_id))
        return bool(self._ps_names(_sanitize(operation_id)))

    def prove_never_sent(self, operation_id: str) -> bool:
        if self.run_dir is None or not self.run_dir.is_dir():
            return False
        base = _sanitize(operation_id)
        if self._tracked(operation_id) or self._results(operation_id):
            return False
        if any(self.run_dir.glob(f"{base}_*.spawns")):
            return False
        if any(self.run_dir.glob(f"{base}_*.gen")):
            return False
        if any(self.run_dir.glob(f"{base}_*.supervise.json")):
            return False
        found = self._ps_names(base)
        return found is not None and not found

    def read_result(self, operation_id: str) -> dict[str, Any] | None:
        for result_file in self._results(operation_id):
            try:
                return json.loads(result_file.read_text())
            except (ValueError, OSError):
                return {"outcome": "unknown", "parse": "stored-result-unreadable"}
        return None

    def live_ids(self) -> list[str]:
        if self.run_dir is None:
            return []
        alive = []
        for track in self.run_dir.glob("*.container"):
            stem = track.stem
            if (self.run_dir / f"{stem}.result.json").exists():
                continue
            try:
                name = track.read_text().strip()
            except OSError:
                continue
            if not name or docker_container_running(self.docker, name) is not False:
                alive.append(stem)
        return sorted(alive)

    def is_live(self, operation_id: str) -> bool:
        if self._results(operation_id) and not self._tracked(operation_id):
            return False
        if self.run_dir is not None:
            names = self._tracked_names(operation_id)
            if names:
                return any(not n or docker_container_running(self.docker, n) is not False
                           for n in names)
        found = self._ps_names(_sanitize(operation_id))
        if found is None:
            return self._probe.available
        return bool(found)

    def _supervise_files(self, operation_id: str) -> list[Path]:
        if self.run_dir is None:
            return []
        return sorted(self.run_dir.glob(
            f"{_sanitize(operation_id)}_*.supervise.json"))

    def stop(self, operation_id: str) -> bool:
        if self.run_dir is not None:
            names = self._tracked_names(operation_id)
        else:
            names = self._ps_names(_sanitize(operation_id)) or []
        targets = [name for name in names if name]
        if not targets:
            return self.read_result(operation_id) is not None
        grace_s = max(int(self.grace_ms // 1000), 1)
        finals = [terminate_verified(self.docker, name, grace_s)
                  for name in targets]
        if all(final is False for final in finals):
            if self.run_dir is not None:
                for track in self._tracked(operation_id):
                    try:
                        track.unlink()
                    except OSError:
                        pass
                for state_file in self._supervise_files(operation_id):
                    self._drop_supervise(state_file)
            return True
        return False

    def _claim(self, container_path: Path) -> bool:
        try:
            fd = os.open(container_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.close(fd)
            return True
        except FileExistsError:
            return False
        except OSError:
            return False

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        if not self._probe.available:
            raise IncompatibleVersion(f"{PROFILE} unavailable: {self._probe.reason}")
        self.enforce_deadlines()
        payload = op.payload
        argv = list(payload["argv"])
        timeout_ms = int(payload.get("timeout_ms", 30_000))
        max_bytes = int(payload.get("max_output_bytes", 1_048_576))
        generation = int(op.dispatch_generation or 0)
        name = self.native_id(op.operation_id, op.execution_version)
        paths = None
        if self.run_dir is not None:
            paths = self._paths(op.operation_id, op.execution_version)
            if paths["result"].exists():
                return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
            if not self._claim(paths["container"]):
                recorded = self._recorded_generation(paths["generation"])
                if (recorded is not None and recorded != generation
                        and generation > recorded):
                    paths["generation"].write_text(str(generation))
                    return LaunchOutcome(sent=False, refused_reason="superseded-claim")
                return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
            recorded = self._recorded_generation(paths["generation"])
            if recorded is not None and recorded > generation:
                try:
                    paths["container"].unlink()
                except OSError:
                    pass
                return LaunchOutcome(sent=False, refused_reason="superseded-generation")
            paths["generation"].write_text(str(generation))
            paths["container"].write_text(name)
            try:
                seen = int(paths["spawns"].read_text().strip()) if paths["spawns"].exists() else 0
            except (ValueError, OSError):
                seen = 0
            paths["spawns"].write_text(str(seen + 1))
            paths["supervise"].write_text(json.dumps(
                self._supervise_state(op.operation_id, op.execution_version,
                                     name, timeout_ms)))
            if self._recorded_generation(paths["generation"]) != generation:
                try:
                    paths["container"].unlink()
                except OSError:
                    pass
                self._drop_supervise(paths["supervise"])
                return LaunchOutcome(sent=False, refused_reason="superseded-generation")
        result = run_gvisor(
            argv, image=self.image_digest, timeout_ms=timeout_ms,
            cpu_seconds=payload.get("cpu_seconds"), memory_bytes=payload.get("memory_bytes"),
            scratch_bytes=self.scratch_bytes,
            mounts=self._mounts(op.operation_id, op.execution_version),
            max_output_bytes=max_bytes,
            extra_env={"SETTLEMENT_OPERATION": op.operation_id},
            runtime=self.runtime, network=self.network, name=name,
            docker=self.docker, grace_ms=self.grace_ms)
        content = _interpret(result, argv, self.image_digest, self.runtime, name, timeout_ms)
        if content["data"].get("stop_verified") is False:
            content["_verdict"] = "failure"
        if paths is not None:
            paths["result"].write_text(json.dumps({"outcome": content["_verdict"], **content}))
            if content["data"].get("stop_verified", True) is not None:
                try:
                    paths["container"].unlink()
                except OSError:
                    pass
                self._drop_supervise(paths["supervise"])
        receipt = ReceiptProposal(
            receipt_identity=f"runsc:{name}", content=content,
            outcome=content["_verdict"], provenance=self.launcher_id)
        return LaunchOutcome(sent=True, receipt=receipt)
