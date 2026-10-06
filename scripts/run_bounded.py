#!/usr/bin/env python3
"""Run one command under a hard wall-clock bound and report a definite outcome.

Lanes in this repository have been killed mid-investigation four times by one
shape of mistake: a process that watches other work by pattern-matching
process names or log text instead of owning that work's lifetime.

1. A pytest file was run under a cap too low for it, and both attempts were
   lost when the cap fired.
2. A 50-minute timeout swallowed its output through a pipe, so the run left no
   result to diagnose afterwards.
3. Thirteen waiters ran `until ! pgrep -f ad01_r3_compare`. The waiter's own
   command line carried the string it was grepping for, so every waiter matched
   every other waiter and the set deadlocked. Five were still spinning twenty
   minutes later.
4. A waiter declared completion on `grep -E "passed|failed|error"`, which
   matches the word inside the `plugins: hypothesis-6.168.0, ...` header line
   emitted seconds into a run. It nearly reported nine of fifty-seven tests as
   a finished run.

So the answer here is never "no process matches this name". It is one of five
outcomes, and every one of them comes from the child's own exit status or from
a line the child actually wrote.

    exited       the child exited, carrying its own status
    timeout      our bound was reached; the child's process group was killed
    refused      we declined to start: bad arguments, a slow file, or no slot
    startfail    the command could not be exec'd at all
    incomplete   the child exited 0 but wrote no completion summary

Nothing here polls. A test pins that, by asserting the absence of every
mechanism that could match an observer. Liveness comes from a pid this process
wrote into a lock directory it created with `os.mkdir`, so there is no pattern
in any argv that a second waiter could collide with.

    scripts/run_bounded.py --timeout 280 -- python -m pytest tests/test_x.py
    scripts/run_bounded.py --timeout 60 --allow-slow -- pytest tests/test_r02_exec.py

The exit code is the child's own status, except for four reserved values and a
remap that keeps a child status of 124-127 recoverable. The table is in
`docs/LONG-RUNNING-TESTS.md`, which also carries the slow-file triage this
tool refuses on.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK = 0
EXIT_TIMEOUT = 124
EXIT_REFUSED = 125
EXIT_STARTFAIL = 126
EXIT_INCOMPLETE = 127

# A child that exits with one of the four values this tool reserves is shifted
# up by 128, so its real status stays recoverable from the code alone. Without
# this, a child exiting 124 would be indistinguishable from our own timeout,
# which is the one ambiguity a caller cannot be asked to resolve by reading
# more output.
RESERVED = (EXIT_TIMEOUT, EXIT_REFUSED, EXIT_STARTFAIL, EXIT_INCOMPLETE)

DEFAULT_TIMEOUT_S = 280.0
DEFAULT_SLOTS = 2
DEFAULT_KILL_GRACE_S = 5.0
# A slot whose holder wrote no pid this long ago is treated as abandoned. It
# bounds the damage a crash between mkdir and the holder write can do.
DEFAULT_STALE_S = 3600.0

# A pytest terminal summary is a whole line: some counts, then `in <elapsed>`.
# The elapsed clause is what makes this a completion test rather than a
# keyword search. `plugins: hypothesis-6.168.0, timeout-2.4.0, anyio-4.15.1`
# has no elapsed clause, and a `-v` progress line naming a passing test has
# neither.
_SUMMARY = re.compile(
    r"^(?P<prefix>.+?)\s+in\s+\d+(?:\.\d+)?s"
    r"(?:\s+\(\d+:\d{2}(?::\d{2})?\))?$"
)
_COUNT = re.compile(
    r"\b\d+\s+(?:passed|failed|error|errors|skipped|xfailed|xpassed"
    r"|deselected|warning|warnings)\b"
)

# Files that cost minutes by nature, with the band and the reason. This is the
# triage from `docs/LONG-RUNNING-TESTS.md`; a test asserts the two agree, so
# the table cannot drift from the prose a lane reads. The bands are `measured`
# when a timed run on this host backs them and `read` when they come from
# reading the file's own source, which is the only evidence available for a
# file nobody has yet run to completion.
SLOW_FILES: dict[str, tuple[str, str]] = {
    "test_ag01_state.py": (
        "measured",
        "71 migrated_db references across 20 tests; each one applies every "
        "migration and truncates every table"),
    "test_d02live_episode.py": (
        "read",
        "36 migrated_db references plus a real subprocess spawn"),
    "test_ec02ad_verif.py": (
        "measured",
        "28 tests and 11 real subprocess spawns; timed at 175s inside a "
        "six-file group"),
    "test_eng_invb_gateway.py": (
        "read",
        "a 30s sleep in the test's own process, in a one-test file"),
    "test_eng_invb_launchers.py": (
        "read",
        "writes 120s and 30s sleeps into grandchild scripts it then kills"),
    "test_invr2_correction.py": (
        "read",
        "relaunches itself as a child and waits on a 300s deadline before "
        "killing the child's process group"),
    "test_invr2_diagnostic.py": (
        "read",
        "relaunches itself as a child and waits on a 300s deadline before "
        "killing the child's process group"),
    "test_launchers.py": (
        "read",
        "writes 30s sleeps into launched children it then kills"),
    "test_r01_fulfill.py": ("read", "34 migrated_db references"),
    "test_r02_authority.py": ("read", "38 migrated_db references"),
    "test_r02_evalbind.py": ("read", "36 migrated_db references"),
    "test_r02_exec.py": (
        "read",
        "53 tests, real subprocesses, and a 1000s sleep written into a "
        "launcher script it kills"),
    "test_r03_sup.py": (
        "read",
        "8 tests, each writing a 1000s sleep into a supervised child"),
    "test_s09_e3_ladder.py": ("read", "50 migrated_db references"),
    "test_s09_swe_experiment.py": (
        "read",
        "101 test definitions, no subprocess, no sleep, no database; "
        "compute-bound on in-process generated-source execs under a 100k-step "
        "alarm, and already carries the repo's own swe_matrix marker"),
    "test_s09iso_stale_sweep.py": (
        "read",
        "61 tests, real subprocesses waited on for 30s each, and a 600s sleep "
        "written into a holder script"),
    "test_team_runtime.py": ("read", "46 migrated_db references"),
}


@dataclass
class Outcome:
    """The sum of what can be known about a run, in one of five shapes.

    A `kind` and the fields that kind populates, rather than a set of booleans,
    so an impossible report cannot be constructed. `exited` is the only kind
    carrying a child status, and only `exited` can claim the run completed.
    """

    kind: str
    detail: str = ""
    status: int | None = None
    limit_s: float | None = None
    summary: str | None = None
    elapsed_s: float = 0.0
    log: str | None = None
    slot: str | None = None
    signal_sent: tuple[int, int] | None = None

    def as_dict(self) -> dict:
        out = {"outcome": self.kind, "detail": self.detail,
               "elapsed_s": round(self.elapsed_s, 3)}
        if self.status is not None:
            out["status"] = self.status
        if self.limit_s is not None:
            out["limit_s"] = self.limit_s
        if self.summary is not None:
            out["summary"] = self.summary
        if self.log is not None:
            out["log"] = self.log
        if self.slot is not None:
            out["slot"] = self.slot
        if self.signal_sent is not None:
            out["signals"] = list(self.signal_sent)
        return out

    def report(self) -> str:
        parts = ["run_bounded: outcome=%s" % self.kind]
        for key in ("status", "limit_s", "elapsed_s", "log", "slot"):
            value = getattr(self, key)
            if value is not None:
                parts.append("%s=%s" % (key, value))
        if self.detail:
            parts.append("detail=%r" % self.detail)
        return " ".join(parts)


class SummaryScanner:
    """Decide whether a pytest run has written its terminal summary.

    Fed whole lines as they arrive, and answers from the line alone. A line
    that merely mentions a passing test, or names a passing plugin, is not a
    summary: pytest's summary is a count, a comma-separated list of more
    counts, and an elapsed time, and nothing else.
    """

    def __init__(self) -> None:
        self.summary: str | None = None
        self.seen = 0

    @staticmethod
    def is_summary(line: str) -> bool:
        core = line.strip().strip("= \t")
        if not core or "::" in core:
            return False
        match = _SUMMARY.match(core)
        if match is None:
            return False
        prefix = match.group("prefix")
        if prefix == "no tests ran":
            return True
        return prefix[0].isdigit() and _COUNT.search(prefix) is not None

    def feed(self, line: str) -> bool:
        if not self.is_summary(line):
            return False
        self.summary = line.strip()
        self.seen += 1
        return True

    @property
    def completed(self) -> bool:
        return self.summary is not None


@dataclass
class Slot:
    """A bounded number of concurrent runners, held by a directory it created.

    The holder records its own pid. Liveness is that pid, read back and probed
    with signal 0, so a waiting lane is asking "is the process that took this
    slot still running" rather than searching for a name. Two waiters cannot
    collide because they never share a search string.
    """

    name: str
    base: Path
    stale_s: float = DEFAULT_STALE_S
    limit: int = DEFAULT_SLOTS

    @property
    def path(self) -> Path:
        return self.base / self.name

    def _holder(self) -> dict:
        try:
            raw = (self.path / "holder.json").read_text()
            value = json.loads(raw)
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _alive(pid: int) -> bool:
        return _pid_alive(pid)

    def _reclaim(self) -> str | None:
        """Clear a slot whose holder cannot be running. Returns why, or None."""
        holder = self._holder()
        pid = holder.get("pid")
        if isinstance(pid, int) and pid > 0 and pid != os.getpid():
            if self._alive(pid):
                return None
            return "holder pid %d is not running" % pid
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return None
        if age <= self.stale_s:
            return None
        return "no live holder recorded and the slot is %ds old" % int(age)

    def acquire(self, label: str = "") -> str | None:
        """Take the slot, or return the refusal a caller should report."""
        self.base.mkdir(parents=True, exist_ok=True)
        for attempt in (0, 1):
            try:
                self.path.mkdir()
            except FileExistsError:
                why = self._reclaim()
                if attempt == 0 and why is not None:
                    self._clear()
                    continue
                holder = self._holder()
                held = holder.get("label") or holder.get("pid") or "unknown"
                return ("slot %r is held by %s; the cap is %d concurrent "
                        "runner(s) per slot" % (self.name, held, self.limit))
            except OSError as exc:
                return "cannot create slot %r: %s" % (self.name, exc)
            self._write_holder(label)
            return None
        return "slot %r could not be acquired" % self.name

    def _write_holder(self, label: str) -> None:
        payload = {"pid": os.getpid(), "label": label,
                   "started": time.time()}
        target = self.path / "holder.json"
        try:
            target.write_text(json.dumps(payload))
        except OSError:
            pass

    def _clear(self) -> None:
        try:
            (self.path / "holder.json").unlink()
        except OSError:
            pass
        try:
            self.path.rmdir()
        except OSError:
            pass

    def release(self) -> None:
        if self._holder().get("pid") == os.getpid():
            self._clear()


@dataclass
class _Killed(Exception):
    """Raised inside the signal handler to unwind to a cleanup point."""

    signum: int = field(default=0)


def slow_files_named(argv: list[str]) -> list[str]:
    """Which of the named paths are on the triage list."""
    hits = []
    for item in argv:
        name = os.path.basename(item)
        if name in SLOW_FILES and name not in hits:
            hits.append(name)
    return hits


def _signal_group(pid: int, signum: int, proc=None, *, force: bool = False) -> bool:
    """Signal the child's whole process group, falling back to the child.

    The child was started with `start_new_session=True`, so it leads a group
    holding nothing but its own descendants. That is what makes this safe
    under concurrency on POSIX. Windows has no `killpg` and uses process
    termination for the child; its process-group qualification stays POSIX-only.
    """
    if os.name == "nt":
        try:
            if proc is None:
                os.kill(pid, signal.SIGTERM)
            elif force:
                proc.kill()
            else:
                proc.terminate()
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False

    for target in (lambda: os.killpg(os.getpgid(pid), signum),
                   lambda: os.kill(pid, signum)):
        try:
            target()
            return True
        except (ProcessLookupError, PermissionError, OSError):
            continue
    return False


def _pid_alive(pid: int) -> bool:
    """Check a pid without sending it a signal, on either supported host."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError, ValueError):
        return False
    except PermissionError:
        return True
    return True


def _terminate(proc, grace_s: float) -> int:
    """Stop a process group and reap it, within a time this function bounds.

    SIGTERM first so the child can flush what it has, SIGKILL after a bounded
    grace so a child that ignores the first signal still cannot outlive us.
    Returns the last signal that was delivered.
    """
    sent = 0
    if _signal_group(proc.pid, signal.SIGTERM, proc):
        sent = signal.SIGTERM
    try:
        proc.wait(timeout=max(grace_s, 0.1))
        return sent
    except subprocess.TimeoutExpired:
        pass
    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    if _signal_group(proc.pid, kill_signal, proc, force=True):
        sent = kill_signal
    try:
        proc.wait(timeout=max(grace_s, 0.1))
    except subprocess.TimeoutExpired:
        pass
    return sent


def _drain(stream, sink, log_file, scanner: SummaryScanner) -> None:
    """Copy the child's output onward while deciding, line by line, when it ends.

    Running the completion check here rather than on the finished file means
    the verdict comes from lines the child actually wrote in order, and cannot
    be reached by a file some other process rewrites afterwards.
    """
    try:
        for raw in stream:
            line = raw.decode("utf-8", "replace")
            scanner.feed(line)
            if log_file is not None:
                log_file.write(line)
                log_file.flush()
            sink.write(line)
            sink.flush()
    except (OSError, ValueError):
        return
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _remap(status: int) -> int:
    if status in RESERVED:
        return 128 + RESERVED.index(status)
    return status


def exit_code(outcome: Outcome) -> int:
    if outcome.kind == "exited":
        if outcome.status is None:
            # `Popen.returncode` stays `None` when a child is never reaped, and
            # `None` is not a zero. Reporting 0 here would be the one false
            # pass this tool exists to prevent, so it refuses instead.
            raise ValueError(
                "an exited outcome carries no status; the child was never "
                "reaped, so nothing can be said about how it went")
        return _remap(outcome.status)
    if outcome.kind == "timeout":
        return EXIT_TIMEOUT
    if outcome.kind == "refused":
        return EXIT_REFUSED
    if outcome.kind == "startfail":
        return EXIT_STARTFAIL
    if outcome.kind == "incomplete":
        return EXIT_INCOMPLETE
    raise ValueError("unknown outcome kind %r" % (outcome.kind,))


def run(argv: list[str], *, timeout_s: float = DEFAULT_TIMEOUT_S,
        log_path: str | None = None, expect: str = "auto",
        allow_slow: bool = False, slot: Slot | None = None,
        kill_grace_s: float = DEFAULT_KILL_GRACE_S,
        cwd: str | None = None, sink=None) -> Outcome:
    """Run `argv` and return what is certainly true about how it went."""
    started = time.monotonic()
    if not argv:
        return Outcome("refused", "no command given", elapsed_s=0.0)
    if timeout_s <= 0:
        return Outcome("refused", "--timeout must be positive, got %r"
                       % (timeout_s,), elapsed_s=0.0)

    slow = slow_files_named(argv)
    if slow and not allow_slow:
        listed = "; ".join(
            "%s (%s: %s)" % (name, SLOW_FILES[name][0], SLOW_FILES[name][1])
            for name in slow)
        return Outcome(
            "refused",
            "%s is on the slow-file list. Re-run with --allow-slow once you have "
            "chosen a --timeout that fits it, or scope the run to the test. %s"
            % (", ".join(slow), listed),
            limit_s=timeout_s, elapsed_s=0.0)

    if slot is not None:
        refusal = slot.acquire(" ".join(argv[:3]))
        if refusal is not None:
            return Outcome("refused", refusal, limit_s=timeout_s,
                           slot=slot.name, elapsed_s=0.0)
    try:
        return _run_child(argv, timeout_s=timeout_s, log_path=log_path,
                          expect=expect, kill_grace_s=kill_grace_s, cwd=cwd,
                          sink=sink, started=started, slot=slot)
    finally:
        if slot is not None:
            slot.release()


def _run_child(argv, *, timeout_s, log_path, expect, kill_grace_s, cwd,
               sink, started, slot) -> Outcome:
    scanner = SummaryScanner()
    sink = sink if sink is not None else sys.stdout
    handle = None
    if log_path:
        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            handle = open(log_path, "a", encoding="utf-8")
        except OSError as exc:
            return Outcome("refused", "cannot open log %s: %s" % (log_path, exc),
                           limit_s=timeout_s, elapsed_s=0.0,
                           slot=slot.name if slot else None)
    log_file = handle if handle is not None else None

    installed = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            installed.append((signum, signal.getsignal(signum)))
            signal.signal(signum, _raise_killed)
        except (ValueError, OSError):
            pass

    try:
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, start_new_session=True)
        except FileNotFoundError as exc:
            return Outcome("startfail", "cannot execute %r: %s"
                           % (argv[0], exc), limit_s=timeout_s,
                           log=log_path, slot=slot.name if slot else None,
                           elapsed_s=time.monotonic() - started)
        except (OSError, ValueError) as exc:
            return Outcome("startfail", "cannot start %r: %s" % (argv[0], exc),
                           limit_s=timeout_s, log=log_path,
                           slot=slot.name if slot else None,
                           elapsed_s=time.monotonic() - started)

        reader = threading.Thread(
            target=_drain, args=(proc.stdout, sink, log_file, scanner),
            daemon=True)
        reader.start()

        signum_sent = 0
        reached_bound = False
        try:
            status = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            reached_bound = True
            signum_sent = _terminate(proc, kill_grace_s)
            status = proc.returncode
        except _Killed as killed:
            signum_sent = _terminate(proc, kill_grace_s)
            status = proc.returncode
            reader.join(timeout=kill_grace_s + 1.0)
            target = "child process" if os.name == "nt" else "child's process group"
            return Outcome(
                "refused", "interrupted by signal %d; the %s was terminated"
                " so nothing is left running" % (killed.signum, target),
                status=status, limit_s=timeout_s, summary=scanner.summary,
                elapsed_s=time.monotonic() - started, log=log_path,
                slot=slot.name if slot else None, signal_sent=(signum_sent, 0))
        reader.join(timeout=kill_grace_s + 1.0)
        elapsed = time.monotonic() - started
    finally:
        for signum, previous in installed:
            try:
                signal.signal(signum, previous)
            except (ValueError, OSError):
                pass
        if log_file is not None:
            log_file.close()

    shared = {"elapsed_s": elapsed, "log": log_path,
              "slot": slot.name if slot else None}

    if reached_bound:
        target = "child process" if os.name == "nt" else "child's process group"
        return Outcome(
            "timeout", "the bound was reached and the %s was terminated "
            "with %s; this is not a pass"
            % (target, signal.Signals(signum_sent).name if signum_sent else "no signal"),
            status=status, limit_s=timeout_s, summary=scanner.summary,
            signal_sent=(signum_sent, 0), **shared)

    if expect == "auto":
        expect = "pytest" if _looks_like_pytest(argv) else "none"
    if expect == "pytest" and status == 0 and not scanner.completed:
        return Outcome(
            "incomplete",
            "the child exited 0 without writing a pytest summary, so the run "
            "did not finish and the zero is not a pass", status=status,
            limit_s=timeout_s, **shared)

    return Outcome("exited", status=status, summary=scanner.summary, **shared)


def _looks_like_pytest(argv: list[str]) -> bool:
    """Whether `argv` names pytest in a form this tool will recognise.

    Deliberately literal. Guessing from a log line is how a waiter learned to
    read `plugins: hypothesis-...` as `passed`, so a command that does not say
    `pytest` is taken at its word and gets no summary requirement. A lane
    wrapping pytest in its own script passes `--expect pytest` explicitly.
    """
    return any(item == "pytest" or item.endswith("/pytest")
               or "pytest" in item for item in argv)


def _raise_killed(signum, frame):
    raise _Killed(signum)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_bounded.py", description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="The exit code is the child's own, except 124 (our bound), "
               "125 (we refused), 126 (it could not start), 127 (it exited 0 "
               "with no summary), and 128-131 (a child status of 124-127, "
               "shifted).")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help="wall-clock bound in seconds (default %(default)s)")
    parser.add_argument("--log", default=None,
                        help="append the child's output to this file as well")
    parser.add_argument("--expect", choices=("auto", "pytest", "none"),
                        default="auto",
                        help="require a pytest terminal summary before calling "
                             "a zero exit complete (default %(default)s)")
    parser.add_argument("--allow-slow", action="store_true",
                        help="permit a file on the slow-file list")
    parser.add_argument("--slot", default=None,
                        help="name this lane's concurrency slot")
    parser.add_argument("--slot-dir", default=None,
                        help="where slot locks live (default a temp dir)")
    parser.add_argument("--max-slots", type=int, default=DEFAULT_SLOTS,
                        help="concurrent runners a slot admits; over this "
                             "the slot is refused (default %(default)s)")
    parser.add_argument("--kill-grace", type=float, default=DEFAULT_KILL_GRACE_S,
                        help="seconds between SIGTERM and SIGKILL "
                             "(default %(default)s)")
    parser.add_argument("--json", action="store_true",
                        help="print the outcome as one JSON line")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw:
        split = raw.index("--")
        options, command = raw[:split], raw[split + 1:]
    else:
        options, command = raw, []
    parser = build_parser()
    try:
        args = parser.parse_args(options)
    except SystemExit:
        raise
    if not command:
        parser.error("no command; put it after --")

    slot = None
    if args.slot:
        base = Path(args.slot_dir) if args.slot_dir else \
            Path(tempfile.gettempdir()) / "run_bounded_slots"
        slot = Slot(args.slot, base)
        slot.limit = args.max_slots

    outcome = run(command, timeout_s=args.timeout, log_path=args.log,
                  expect=args.expect, allow_slow=args.allow_slow, slot=slot,
                  kill_grace_s=args.kill_grace)
    if args.json:
        print(json.dumps(outcome.as_dict()))
    else:
        print(outcome.report())
        if outcome.kind != "exited" and outcome.detail:
            print("run_bounded: %s" % outcome.detail, file=sys.stderr)
    try:
        return exit_code(outcome)
    except ValueError as exc:
        print("run_bounded: %s" % exc, file=sys.stderr)
        return EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
