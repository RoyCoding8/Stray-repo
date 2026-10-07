"""Bounded child processes on Windows through Job Objects.

The child is created suspended, assigned to a job that carries its bounds, and
only then resumed, so it never executes an instruction outside the job. The
job is created with KILL_ON_JOB_CLOSE: when the owning handle closes, including
when the launcher itself dies, every process in the tree is terminated.

Bounds, as measured on Windows 11 / CPython 3.13:

- memory_bytes -> JOB_OBJECT_LIMIT_JOB_MEMORY (committed memory of the whole
  tree). An allocation past it fails inside the child (MemoryError).
- cpu_seconds -> JOB_OBJECT_LIMIT_JOB_TIME (user time of the whole tree). The
  kernel enforces it only at a coarse interval (a 1 s limit killed a busy loop
  after about 5 s of wall time), so `wait`/`communicate` also poll the job's
  accounted user+kernel time and terminate the job as soon as it is exceeded.
  The kernel limit remains as the backstop if the parent stops polling.
"""

from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes as _w

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
_LIMIT_JOB_TIME = 0x00000004
_LIMIT_JOB_MEMORY = 0x00000200
_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_EXTENDED_LIMIT_INFORMATION = 9
_BASIC_ACCOUNTING_INFORMATION = 1
_POLL_S = 0.05
# Exit code a job terminated for exceeding its CPU bound reports.
CPU_LIMIT_EXIT_CODE = 0xC0000044  # STATUS_QUOTA_EXCEEDED, what the kernel limit reports too


class _Basic(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", _w.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", _w.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", _w.DWORD),
                ("SchedulingClass", _w.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]


class _Extended(ctypes.Structure):
    _fields_ = [("Basic", _Basic), ("Io", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_int64),
                ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", _w.DWORD),
                ("TotalProcesses", _w.DWORD),
                ("ActiveProcesses", _w.DWORD),
                ("TotalTerminatedProcesses", _w.DWORD)]


def _api():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    k32.CreateJobObjectW.restype = _w.HANDLE
    k32.CreateJobObjectW.argtypes = [_w.LPVOID, _w.LPCWSTR]
    k32.SetInformationJobObject.restype = _w.BOOL
    k32.SetInformationJobObject.argtypes = [_w.HANDLE, ctypes.c_int, _w.LPVOID, _w.DWORD]
    k32.QueryInformationJobObject.restype = _w.BOOL
    k32.QueryInformationJobObject.argtypes = [_w.HANDLE, ctypes.c_int, _w.LPVOID,
                                              _w.DWORD, _w.LPVOID]
    k32.AssignProcessToJobObject.restype = _w.BOOL
    k32.AssignProcessToJobObject.argtypes = [_w.HANDLE, _w.HANDLE]
    k32.TerminateJobObject.restype = _w.BOOL
    k32.TerminateJobObject.argtypes = [_w.HANDLE, _w.UINT]
    k32.CloseHandle.argtypes = [_w.HANDLE]
    ntdll.NtResumeProcess.argtypes = [_w.HANDLE]
    return k32, ntdll


class JobError(OSError):
    """The job could not be created, bounded or joined; no child ran."""


class Job:
    """One Job Object holding one bounded child tree."""

    def __init__(self, *, cpu_seconds: int | None = None,
                 memory_bytes: int | None = None) -> None:
        self._k32, self._ntdll = _api()
        self.cpu_seconds = cpu_seconds
        self.cpu_exceeded = False
        handle = self._k32.CreateJobObjectW(None, None)
        if not handle:
            raise JobError(ctypes.get_last_error(), "CreateJobObjectW failed")
        self._handle = handle
        info = _Extended()
        flags = _LIMIT_KILL_ON_JOB_CLOSE | _LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        if cpu_seconds is not None:
            flags |= _LIMIT_JOB_TIME
            info.Basic.PerJobUserTimeLimit = int(cpu_seconds) * 10_000_000
        if memory_bytes is not None:
            flags |= _LIMIT_JOB_MEMORY
            info.JobMemoryLimit = int(memory_bytes)
        info.Basic.LimitFlags = flags
        if not self._k32.SetInformationJobObject(
                handle, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.get_last_error()
            self.close()
            raise JobError(error, "SetInformationJobObject failed")

    def spawn(self, argv: list[str], **popen_kwargs) -> subprocess.Popen:
        """Start `argv` suspended, join it to this job, then let it run."""
        flags = int(popen_kwargs.pop("creationflags", 0))
        proc = subprocess.Popen(argv, creationflags=flags | CREATE_SUSPENDED
                                | CREATE_NEW_PROCESS_GROUP, **popen_kwargs)
        if not self._k32.AssignProcessToJobObject(self._handle, int(proc._handle)):
            error = ctypes.get_last_error()
            proc.kill()  # still suspended: it has not executed anything
            proc.communicate()
            raise JobError(error, "AssignProcessToJobObject failed")
        self._ntdll.NtResumeProcess(int(proc._handle))
        return proc

    def cpu_used(self) -> float:
        """User plus kernel CPU seconds consumed by every process in the job."""
        acct = _Accounting()
        if not self._k32.QueryInformationJobObject(
                self._handle, _BASIC_ACCOUNTING_INFORMATION, ctypes.byref(acct),
                ctypes.sizeof(acct), None):
            raise JobError(ctypes.get_last_error(), "QueryInformationJobObject failed")
        return (acct.TotalUserTime + acct.TotalKernelTime) / 10_000_000

    def terminate(self, exit_code: int = 1) -> None:
        if self._handle:
            self._k32.TerminateJobObject(self._handle, exit_code)

    def close(self) -> None:
        """Close the job; KILL_ON_JOB_CLOSE ends anything still running in it."""
        if self._handle:
            self._k32.CloseHandle(self._handle)
            self._handle = None

    def _over_cpu(self) -> bool:
        if self.cpu_seconds is not None and self.cpu_used() > self.cpu_seconds:
            self.cpu_exceeded = True
            self.terminate(CPU_LIMIT_EXIT_CODE)
            return True
        return False

    def wait(self, proc: subprocess.Popen, timeout_s: float) -> bool:
        """Wait for `proc` while enforcing the CPU bound. True when it timed out.

        For callers that drain the pipes themselves. On timeout the whole tree
        is terminated before returning.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                proc.wait(timeout=min(_POLL_S, max(deadline - time.monotonic(), 0)))
                return False
            except subprocess.TimeoutExpired:
                if self._over_cpu():
                    proc.wait()
                    return False
                if time.monotonic() >= deadline:
                    self.terminate()
                    proc.wait()
                    return True

    def communicate(self, proc: subprocess.Popen,
                    timeout_s: float) -> tuple[bytes, bytes, bool]:
        """`proc.communicate` with the CPU bound enforced. Returns (out, err, timed_out)."""
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                out, err = proc.communicate(
                    timeout=min(_POLL_S, max(deadline - time.monotonic(), 0)))
                return out or b"", err or b"", False
            except subprocess.TimeoutExpired:
                if self._over_cpu():
                    out, err = proc.communicate()
                    return out or b"", err or b"", False
                if time.monotonic() >= deadline:
                    self.terminate()
                    out, err = proc.communicate()
                    return out or b"", err or b"", True

    def __enter__(self) -> "Job":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def pid_alive(pid: int) -> bool:
    """Whether a process with `pid` is running (never signals it)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = _w.HANDLE
    k32.OpenProcess.argtypes = [_w.DWORD, _w.BOOL, _w.DWORD]
    k32.GetExitCodeProcess.argtypes = [_w.HANDLE, ctypes.POINTER(_w.DWORD)]
    handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = _w.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def kill_tree(pid: int) -> None:
    """Terminate `pid` and its descendants (for a launcher other than the owner)."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(int(pid))],
                   capture_output=True, timeout=30)
