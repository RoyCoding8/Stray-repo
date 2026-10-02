from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .common import IncompatibleVersion, ResultCode, SettlementError

GVISOR = "gvisor"
LOCAL_PROCESS = "local-process"
SIMULATED = "simulated"

_SECRET_PATTERN = re.compile(r"secret|key|token|password|credential", re.IGNORECASE)


@dataclass(frozen=True)
class ProfileProbe:
    name: str
    available: bool
    code: ResultCode
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecResult:
    profile: str
    containment: bool
    simulated: bool
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    wall_ms: int
    detail: dict[str, Any] = field(default_factory=dict)


def _which(explicit: str | None, name: str) -> str | None:
    if explicit is not None:
        return explicit if os.path.exists(explicit) else None
    return shutil.which(name)


def probe_gvisor(
    runsc_path: str | None = None, docker_path: str | None = None
) -> ProfileProbe:
    runsc = _which(runsc_path, "runsc")
    docker = _which(docker_path, "docker")
    if runsc is None or docker is None:
        missing = [n for n, p in (("runsc", runsc), ("docker", docker)) if p is None]
        return ProfileProbe(
            name=GVISOR,
            available=False,
            code=ResultCode.INCOMPATIBLE_VERSION,
            reason=f"gvisor unavailable: missing {', '.join(missing)} on this host",
            detail={"runsc": runsc, "docker": docker},
        )
    try:
        info = subprocess.run(
            [docker, "info", "--format", "{{json .Runtimes}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return ProfileProbe(
            name=GVISOR,
            available=False,
            code=ResultCode.INCOMPATIBLE_VERSION,
            reason=f"gvisor unavailable: docker info failed: {exc}",
            detail={"runsc": runsc, "docker": docker},
        )
    try:
        runtimes = json.loads(info.stdout or "{}")
    except ValueError:
        runtimes = {}
    if "runsc" not in runtimes:
        return ProfileProbe(
            name=GVISOR,
            available=False,
            code=ResultCode.INCOMPATIBLE_VERSION,
            reason="gvisor unavailable: docker has no runsc runtime configured",
            detail={"runsc": runsc, "docker": docker, "runtimes": sorted(runtimes)},
        )
    return ProfileProbe(
        name=GVISOR,
        available=True,
        code=ResultCode.APPLIED,
        reason="runsc runtime is configured in docker",
        detail={"runsc": runsc, "docker": docker, "runtimes": sorted(runtimes)},
    )


def scrub_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    base = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    if extra:
        for key, value in extra.items():
            if not _SECRET_PATTERN.search(key):
                base[key] = value
    return base


def _limit_resources(cpu_seconds: int | None, memory_bytes: int | None) -> None:
    import resource

    if cpu_seconds is not None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    if memory_bytes is not None:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))


def run_local_process(
    argv: list[str],
    timeout_ms: int = 30_000,
    cpu_seconds: int | None = None,
    memory_bytes: int | None = None,
    max_output_bytes: int = 1_048_576,
    extra_env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> ExecResult:
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=scrub_env(extra_env),
            cwd=cwd,
            preexec_fn=lambda: _limit_resources(cpu_seconds, memory_bytes),
        )
    except OSError as exc:
        return ExecResult(
            profile=LOCAL_PROCESS,
            containment=False,
            simulated=False,
            returncode=None,
            stdout="",
            stderr=str(exc),
            timed_out=False,
            truncated=False,
            wall_ms=int((time.monotonic() - started) * 1000),
            detail={"error": "spawn-failed"},
        )
    try:
        raw_out, raw_err = proc.communicate(timeout=timeout_ms / 1000)
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        raw_out, raw_err = proc.communicate()
        timed_out = True
    out, out_truncated = _cap(raw_out, max_output_bytes)
    err, err_truncated = _cap(raw_err, max_output_bytes)
    return ExecResult(
        profile=LOCAL_PROCESS,
        containment=False,
        simulated=False,
        returncode=proc.returncode,
        stdout=out.decode("utf-8", "replace"),
        stderr=err.decode("utf-8", "replace"),
        timed_out=timed_out,
        truncated=out_truncated or err_truncated,
        wall_ms=int((time.monotonic() - started) * 1000),
        detail={"timeout_ms": timeout_ms, "max_output_bytes": max_output_bytes},
    )


def _cap(raw: bytes, limit: int) -> tuple[bytes, bool]:
    if len(raw) > limit:
        return raw[:limit], True
    return raw, False


def run_simulated(argv: list[str]) -> ExecResult:
    return ExecResult(
        profile=SIMULATED,
        containment=False,
        simulated=True,
        returncode=0,
        stdout="",
        stderr="",
        timed_out=False,
        truncated=False,
        wall_ms=0,
        detail={"note": "simulated: no command was executed", "argv": list(argv)},
    )


def dispatch(profile: str, argv: list[str], **kwargs: Any) -> ExecResult:
    if profile == GVISOR:
        probe = probe_gvisor()
        if not probe.available:
            raise IncompatibleVersion(probe.reason)
        raise IncompatibleVersion("gvisor runtime present but no admitted launcher is implemented")
    if profile == LOCAL_PROCESS:
        return run_local_process(argv, **kwargs)
    if profile == SIMULATED:
        return run_simulated(argv)
    raise SettlementError(f"unknown execution profile: {profile}")
