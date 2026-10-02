from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import child_limits
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


def _child_session(cpu_seconds: int | None, memory_bytes: int | None) -> None:
    child_limits.apply_child_limits(
        child_limits.ChildLimits(cpu_seconds=cpu_seconds,
                                 memory_bytes=memory_bytes))
    os.setsid()


def _kill_group(pid: int, grace_ms: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    deadline = time.monotonic() + max(int(grace_ms), 0) / 1000
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except (ProcessLookupError, PermissionError, OSError):
            return
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def run_local_process(
    argv: list[str],
    timeout_ms: int = 30_000,
    cpu_seconds: int | None = None,
    memory_bytes: int | None = None,
    max_output_bytes: int = 1_048_576,
    extra_env: dict[str, str] | None = None,
    cwd: str | None = None,
    grace_ms: int = 2000,
) -> ExecResult:
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=scrub_env(extra_env),
            cwd=cwd,
            preexec_fn=lambda: _child_session(cpu_seconds, memory_bytes),
        )
    except (OSError, ValueError) as exc:
        # ValueError is CPython refusing `preexec_fn` on Windows, raised by
        # `Popen` before any child exists. It is caught here because the
        # function is going to refuse this child either way: an unbounded one
        # is what the refusal exists to prevent, and the refusal belongs in the
        # result this call returns rather than in a traceback out of it.
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
    if proc.stdout is None or proc.stderr is None:
        try:
            raw_out, raw_err = proc.communicate(timeout=timeout_ms / 1000)
            timed_out = False
        except subprocess.TimeoutExpired:
            _kill_group(proc.pid, grace_ms)
            raw_out, raw_err = proc.communicate()
            timed_out = True
        out, out_truncated = _cap(raw_out or b"", max_output_bytes)
        err, err_truncated = _cap(raw_err or b"", max_output_bytes)
    else:
        threads, slots = _start_pumps(proc, max_output_bytes)
        try:
            proc.wait(timeout=timeout_ms / 1000)
            timed_out = False
        except subprocess.TimeoutExpired:
            _kill_group(proc.pid, grace_ms)
            proc.wait()
            timed_out = True
        out, out_truncated, err, err_truncated = _finish_pumps(
            threads, slots, 35.0)
        _close_pipes(proc)
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


def _derived_name(image: str, argv: list[str]) -> str:
    digest = hashlib.sha1(f"{image}\0{json.dumps(argv)}".encode()).hexdigest()[:16]
    return f"gvisor-{digest}"


def build_gvisor_argv(
    argv: list[str],
    *,
    image: str,
    runtime: str = "runsc",
    network: str = "none",
    memory_bytes: int | None = None,
    cpu_seconds: int | None = None,
    scratch_bytes: int | None = None,
    mounts: list[tuple[str, str, bool]] | tuple[tuple[str, str, bool], ...] = (),
    name: str | None = None,
    extra_env: dict[str, str] | None = None,
    docker: str = "docker",
) -> list[str]:
    cmd = [docker, "run", "--rm", f"--runtime={runtime}", f"--network={network}"]
    if memory_bytes is not None:
        cmd.append(f"--memory={int(memory_bytes)}")
    if cpu_seconds is not None:
        cmd += ["--ulimit", f"cpu={int(cpu_seconds)}:{int(cpu_seconds)}"]
    if scratch_bytes is not None:
        cmd += ["--storage-opt", f"size={int(scratch_bytes)}"]
    for host, container, readonly in mounts:
        cmd += ["-v", f"{host}:{container}:{'ro' if readonly else 'rw'}"]
    cmd.append(f"--name={name or _derived_name(image, argv)}")
    for key, value in scrub_env(extra_env).items():
        cmd += ["-e", f"{key}={value}"]
    return cmd + [image, *argv]


def container_name(container_argv: list[str]) -> str:
    for arg in container_argv:
        if arg.startswith("--name="):
            return arg.split("=", 1)[1]
    return ""


DOCKER_STOP_TIMEOUT_S = 30
DOCKER_INSPECT_TIMEOUT_S = 15
DOCKER_KILL_TIMEOUT_S = 15
SUPERVISOR_REAP_TIMEOUT_S = 5.0
STOP_SETTLE_S = (DOCKER_STOP_TIMEOUT_S + 2 * DOCKER_INSPECT_TIMEOUT_S
                 + DOCKER_KILL_TIMEOUT_S + int(SUPERVISOR_REAP_TIMEOUT_S))


def docker_stop(docker: str, name: str, grace_s: int) -> bool:
    if not name:
        return False
    try:
        proc = subprocess.run([docker, "stop", "--time", str(grace_s), name],
                              capture_output=True, text=True,
                              timeout=DOCKER_STOP_TIMEOUT_S)
    except (subprocess.SubprocessError, OSError):
        return False
    return proc.returncode == 0


def terminate_verified(docker: str, name: str, grace_s: int) -> bool | None:
    if not name:
        return None
    docker_stop(docker, name, grace_s)
    if docker_container_running(docker, name):
        try:
            subprocess.run([docker, "kill", name],
                           capture_output=True, text=True,
                           timeout=DOCKER_KILL_TIMEOUT_S)
        except (subprocess.SubprocessError, OSError):
            pass
    return docker_container_running(docker, name)


def docker_container_running(docker: str, name: str) -> bool | None:
    try:
        proc = subprocess.run([docker, "inspect", "-f", "{{.State.Running}}", name],
                              capture_output=True, text=True,
                              timeout=DOCKER_INSPECT_TIMEOUT_S)
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().lower() == "true"


_READ_CHUNK = 65536

_SUPERVISOR_SCRIPT = (
    "import subprocess,sys,time\n"
    "docker=sys.argv[1]\n"
    "name=sys.argv[2]\n"
    "wait=float(sys.argv[3])\n"
    "grace=sys.argv[4]\n"
    "time.sleep(max(wait,0.0))\n"
    "try:\n"
    "    subprocess.run([docker,'stop','--time',grace,name],"
    "capture_output=True,timeout=30)\n"
    "except Exception:\n"
    "    pass\n"
    "running=True\n"
    "try:\n"
    "    probe=subprocess.run([docker,'inspect','-f',"
    "'{{.State.Running}}',name],capture_output=True,text=True,timeout=15)\n"
    "    running=probe.returncode==0 and probe.stdout.strip().lower()=='true'\n"
    "except Exception:\n"
    "    running=True\n"
    "if running:\n"
    "    try:\n"
    "        subprocess.run([docker,'kill',name],"
    "capture_output=True,timeout=15)\n"
    "    except Exception:\n"
    "        pass\n"
)


def spawn_supervisor(docker: str, name: str, wait_s: float,
                     grace_s: int = 1) -> Any:
    try:
        return subprocess.Popen(
            [sys.executable, "-c", _SUPERVISOR_SCRIPT,
             docker, name, repr(float(wait_s)), str(grace_s)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def proc_starttime(pid: int) -> str | None:
    try:
        with open(f"/proc/{int(pid)}/stat") as handle:
            fields = handle.read().rsplit(")", 1)[1].split()
    except (ValueError, OSError):
        return None
    return fields[19] if len(fields) > 19 else None


_LOCAL_SUPERVISOR_SCRIPT = (
    "import os,signal,sys,time\n"
    "pid=int(sys.argv[1])\n"
    "pgid=int(sys.argv[2])\n"
    "start=sys.argv[3]\n"
    "done=sys.argv[4]\n"
    "wait=float(sys.argv[5])\n"
    "grace=float(sys.argv[6])\n"
    "def _settled():\n"
    "    try:\n"
    "        return os.path.exists(done)\n"
    "    except OSError:\n"
    "        return False\n"
    "def _alive():\n"
    "    try:\n"
    "        with open('/proc/%d/stat' % pid) as h:\n"
    "            cur=h.read().rsplit(')',1)[1].split()\n"
    "    except (ValueError,OSError):\n"
    "        return False\n"
    "    if len(cur) <= 19 or (start != 'none' and cur[19] != start):\n"
    "        return False\n"
    "    try:\n"
    "        os.kill(pid,0)\n"
    "    except OSError:\n"
    "        return False\n"
    "    return True\n"
    "deadline=time.monotonic()+max(wait,0.0)\n"
    "while time.monotonic() < deadline:\n"
    "    if _settled() or not _alive():\n"
    "        sys.exit(0)\n"
    "    time.sleep(min(0.2,max(deadline-time.monotonic(),0.0)))\n"
    "if _settled() or not _alive():\n"
    "    sys.exit(0)\n"
    "try:\n"
    "    os.killpg(pgid,signal.SIGTERM)\n"
    "except OSError:\n"
    "    pass\n"
    "quiet=time.monotonic()+max(grace,0.0)\n"
    "while time.monotonic() < quiet:\n"
    "    if _settled() or not _alive():\n"
    "        sys.exit(0)\n"
    "    time.sleep(min(0.2,max(quiet-time.monotonic(),0.0)))\n"
    "if _settled() or not _alive():\n"
    "    sys.exit(0)\n"
    "try:\n"
    "    os.killpg(pgid,signal.SIGKILL)\n"
    "except OSError:\n"
    "    pass\n"
)


def spawn_deadline_supervisor(pid: int, pgid: int, starttime: str | None,
                              done_file: str, wait_s: float,
                              grace_s: float = 1.0) -> Any:
    try:
        return subprocess.Popen(
            [sys.executable, "-c", _LOCAL_SUPERVISOR_SCRIPT,
             str(int(pid)), str(int(pgid)), starttime or "none",
             str(done_file), repr(float(wait_s)), repr(float(grace_s))],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def reap_supervisor(proc: Any, timeout_s: float = SUPERVISOR_REAP_TIMEOUT_S) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=timeout_s)
        except (subprocess.SubprocessError, OSError):
            pass
    except (subprocess.SubprocessError, OSError):
        pass


def _pump(stream: Any, slot: dict, cap: int) -> None:
    kept = bytearray()
    total = 0
    try:
        while True:
            chunk = stream.read(_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if len(kept) < cap:
                kept += chunk[:cap - len(kept)]
    except (OSError, ValueError):
        pass
    slot["kept"] = bytes(kept)
    slot["total"] = total


def _start_pumps(proc: Any, max_bytes: int) -> tuple[list, tuple[dict, dict]]:
    slots: tuple[dict, dict] = ({}, {})
    threads = []
    for stream, slot in zip((proc.stdout, proc.stderr), slots):
        thread = threading.Thread(target=_pump, args=(stream, slot, max_bytes))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    return threads, slots


def _finish_pumps(threads: list, slots: tuple[dict, dict],
                  join_timeout: float) -> tuple[bytes, bool, bytes, bool]:
    partial = False
    for thread in threads:
        thread.join(timeout=join_timeout)
        partial = partial or thread.is_alive()
    out = bytes(slots[0].get("kept", b""))
    err = bytes(slots[1].get("kept", b""))
    out_cut = partial or slots[0].get("total", 0) > len(out)
    err_cut = partial or slots[1].get("total", 0) > len(err)
    return out, out_cut, err, err_cut


def _close_pipes(proc: Any) -> None:
    for stream in (getattr(proc, "stdout", None), getattr(proc, "stderr", None)):
        if stream is None:
            continue
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def run_gvisor(
    argv: list[str],
    *,
    image: str,
    timeout_ms: int = 30_000,
    cpu_seconds: int | None = None,
    memory_bytes: int | None = None,
    scratch_bytes: int | None = None,
    mounts: list[tuple[str, str, bool]] | tuple[tuple[str, str, bool], ...] = (),
    max_output_bytes: int = 1_048_576,
    extra_env: dict[str, str] | None = None,
    runtime: str = "runsc",
    network: str = "none",
    name: str | None = None,
    docker: str = "docker",
    grace_ms: int = 2000,
    supervise: bool = True,
) -> ExecResult:
    container_argv = build_gvisor_argv(
        argv, image=image, runtime=runtime, network=network,
        memory_bytes=memory_bytes, cpu_seconds=cpu_seconds,
        scratch_bytes=scratch_bytes, mounts=mounts,
        name=name, extra_env=extra_env, docker=docker)
    cname = container_name(container_argv)
    grace_s = max(int(grace_ms // 1000), 1)
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            container_argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=scrub_env(None),
        )
    except OSError as exc:
        return ExecResult(
            profile=GVISOR,
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
    supervisor = None
    supervision_error = None
    stop_verified: bool | None = None
    try:
        if getattr(proc, "stdout", None) is None or getattr(
                proc, "stderr", None) is None:
            raw_out, raw_err, timed_out = _legacy_collect(
                proc, timeout_ms / 1000, grace_ms, docker, cname)
            out, out_truncated = _cap(raw_out or b"", max_output_bytes)
            err, err_truncated = _cap(raw_err or b"", max_output_bytes)
        else:
            threads, slots = _start_pumps(proc, max_output_bytes)
            if supervise and cname:
                supervisor = spawn_supervisor(
                    docker, cname, timeout_ms / 1000, grace_s)
            if supervise and cname and supervisor is None:
                supervision_error = "supervision-unavailable"
                stop_verified = terminate_verified(docker, cname, grace_s)
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=max(grace_ms / 1000, 1))
                except (subprocess.SubprocessError, OSError):
                    pass
                timed_out = False
            else:
                try:
                    proc.wait(timeout=timeout_ms / 1000)
                    timed_out = False
                    stop_verified = True
                except subprocess.TimeoutExpired:
                    stop_verified = terminate_verified(docker, cname, grace_s)
                    try:
                        proc.wait(timeout=max(grace_ms / 1000, 1))
                    except subprocess.TimeoutExpired:
                        try:
                            proc.kill()
                        except OSError:
                            pass
                        proc.wait()
                    timed_out = True
            out, out_truncated, err, err_truncated = _finish_pumps(
                threads, slots, max(grace_ms / 1000, 1) + 30)
            _close_pipes(proc)
    finally:
        reap_supervisor(supervisor)
    detail = {"image": image, "runtime": runtime, "network": network,
              "container": cname, "timeout_ms": timeout_ms,
              "cpu_seconds": cpu_seconds, "memory_bytes": memory_bytes,
              "scratch_bytes": scratch_bytes,
              "supervised": supervisor is not None,
              "stop_verified": stop_verified,
              "argv": container_argv}
    if supervision_error is not None:
        detail["error"] = supervision_error
    return ExecResult(
        profile=GVISOR,
        containment=True,
        simulated=False,
        returncode=proc.returncode,
        stdout=out.decode("utf-8", "replace"),
        stderr=err.decode("utf-8", "replace"),
        timed_out=timed_out,
        truncated=out_truncated or err_truncated,
        wall_ms=int((time.monotonic() - started) * 1000),
        detail=detail,
    )


def _legacy_collect(proc: Any, budget_s: float, grace_ms: int,
                    docker: str, cname: str) -> tuple[bytes, bytes, bool]:
    try:
        raw_out, raw_err = proc.communicate(timeout=budget_s)
        return raw_out, raw_err, False
    except subprocess.TimeoutExpired:
        docker_stop(docker, cname, max(int(grace_ms // 1000), 1))
        try:
            raw_out, raw_err = proc.communicate(timeout=max(grace_ms / 1000, 1))
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            raw_out, raw_err = proc.communicate()
        return raw_out, raw_err, True


def dispatch(profile: str, argv: list[str], **kwargs: Any) -> ExecResult:
    if profile == GVISOR:
        probe = probe_gvisor()
        if not probe.available:
            raise IncompatibleVersion(probe.reason)
        image = kwargs.get("image")
        if not (isinstance(image, str) and image.startswith("sha256:")):
            raise SettlementError("gvisor dispatch needs a pinned sha256 image")
        return run_gvisor(
            argv, image=image,
            timeout_ms=kwargs.get("timeout_ms", 30_000),
            cpu_seconds=kwargs.get("cpu_seconds"),
            memory_bytes=kwargs.get("memory_bytes"),
            scratch_bytes=kwargs.get("scratch_bytes"),
            mounts=kwargs.get("mounts", ()),
            max_output_bytes=kwargs.get("max_output_bytes", 1_048_576),
            extra_env=kwargs.get("extra_env"),
            runtime=kwargs.get("runtime", "runsc"),
            network=kwargs.get("network", "none"),
            name=kwargs.get("name"),
            docker=kwargs.get("docker", "docker"),
            grace_ms=kwargs.get("grace_ms", 2000),
        )
    if profile == LOCAL_PROCESS:
        return run_local_process(argv, **kwargs)
    if profile == SIMULATED:
        return run_simulated(argv)
    raise SettlementError(f"unknown execution profile: {profile}")
