"""`run_bounded.py` must be able to say "no", and must not say it by accident.

Every test here calls the tool the way a lane does, as a subprocess, and
asserts on what it printed and what it exited with. Nothing imports a private
helper to inspect it, because the claims being pinned are claims about the
interface: a lane reads the exit code and the outcome line, and nothing else.

Three of these are the demonstrations. `test_a_bound_that_is_reached_reports_a
_timeout_and_not_a_pass`, `test_a_child_that_fails_keeps_its_own_status`, and
`test_a_pytest_that_exits_zero_without_a_summary_is_not_a_pass` each spawn a
child that is this test's own to kill, and each waits seconds rather than
minutes.

`test_the_false_completion_log_is_rejected_and_the_real_one_is_not` is the one
that would have caught the defect where a waiter matched `passed|failed|error`
anywhere in a log and called a run finished off the word `passed` inside the
pytest `plugins:` header line.

The two tests that read the tool's source are pinned claims about this repo,
not about the tool: that the tool never names a process to find work, and that
the file this lane was told costs minutes does not. Both will go red when the
world changes, which is what they are for.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.run_bounded import SLOW_FILES, SummaryScanner, _pid_alive

TOOL = ROOT / "scripts" / "run_bounded.py"
PY = sys.executable
TOOL_PY = getattr(sys, "_base_executable", PY)

# The real header of a real pytest run on this repo, taken from an actual run
# rather than written from memory. The word `passed` is not in it. The plugin
# line carries `hypothesis`, and a lazy completion test greps for `error`.
REAL_PYTEST_HEADER = """\
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/ubuntu/AI/Agent-Society-v2
configfile: pyproject.toml
plugins: hypothesis-6.168.0, timeout-2.4.0, anyio-4.15.1
collected 57 items

tests/test_s09_study_preflight.py .......                            [ 15%]
"""

# Real `-v` progress lines, copied out of actual runs of real files in this
# repository. Both of the words the buggy grep looked for are here, and both
# are part of a test's own name rather than a report of the run. 58 test
# functions in `tests/` have `passed`, `failed` or `error` in their name.
MIDRUN_PASSED_LINE = (
    "tests/test_s09_study_preflight.py::"
    "test_a_database_with_no_frozen_moment_is_unknown_not_passed PASSED  [ 15%]")
MIDRUN_ERROR_LINE = (
    "tests/test_s09_study_preflight.py::"
    "test_a_gateway_error_does_not_refund_the_ceiling FAILED          [ 22%]")

REAL_PYTEST_SUMMARY = \
    "============================== 57 passed in 243.92s (0:04:03) =========="


def _run(*args, timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [TOOL_PY, str(TOOL), *args], capture_output=True, text=True,
        timeout=timeout, cwd=str(ROOT))


def _outcome(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError("no JSON outcome line in:\n%s" % stdout)


def _json_run(*args, timeout: float = 120.0) -> dict:
    return _outcome(_run(*args, "--json", timeout=timeout).stdout)


def test_a_command_that_succeeds_reports_its_own_zero():
    proc = _run("--timeout", "30", "--", PY, "-c", "print('hi')")
    assert proc.returncode == 0, proc.stderr
    assert "outcome=exited status=0" in proc.stdout


def test_a_child_that_fails_keeps_its_own_status():
    """The demonstration for "a definite answer".

    Nine is pytest's own "collection was interrupted", so this is a status the
    tool must neither swallow, invent, nor round to zero. The child's stderr
    is merged into stdout on purpose, so the assertion is on the one stream a
    caller actually receives.
    """
    proc = _run("--timeout", "30", "--", PY, "-c",
                "import sys; sys.stderr.write('boom\\n'); sys.exit(9)")
    assert proc.returncode == 9, proc.stdout + proc.stderr
    assert "outcome=exited status=9" in proc.stdout
    assert "boom" in proc.stdout, "the child's own output was swallowed"


def test_a_bound_that_is_reached_reports_a_timeout_and_not_a_pass(tmp_path):
    """The demonstration for the bound.

    The child is this test's own `sleep`, so it can never take down another
    lane's process. The child writes its pid before it blocks, and the test
    checks that pid afterwards, so the kill is observed rather than assumed.
    """
    pidfile = tmp_path / "victim.pid"
    child = ("import os, time, pathlib, sys; "
             "pathlib.Path(%r).write_text(str(os.getpid())); "
             "sys.stdout.flush(); time.sleep(120)" % str(pidfile))
    started = time.monotonic()
    proc = _run("--timeout", "3", "--kill-grace", "1", "--json", "--",
                PY, "-c", child)
    elapsed = time.monotonic() - started
    body = _outcome(proc.stdout)

    assert pidfile.exists(), "the child never ran, so nothing was timed out"
    assert proc.returncode == 124, proc.stdout + proc.stderr
    assert body["outcome"] == "timeout", body
    assert body["limit_s"] == 3.0, body
    assert "not a pass" in body["detail"], body
    assert elapsed < 30, "the bound did not bound: %.1fs" % elapsed

    pid = int(pidfile.read_text())
    time.sleep(0.5)
    assert not _alive(pid), "the child outlived the bound"


@pytest.mark.skipif(os.name == "nt",
                    reason="whole-process-group termination requires POSIX killpg")
def test_the_timeout_kills_the_whole_process_group_not_just_the_child(tmp_path):
    """A grandchild the child spawned must die too.

    A child that leaves descendants behind is how a "killed" run keeps burning
    the box, and how a later lane collides with a store the dead run still
    holds open. The grandchild here waits longer than the tool's whole bound
    before writing anything, so the only way to keep it from writing is for
    the group kill to have reached it. A shorter wait would pass by accident,
    because the grandchild would simply not have written yet.
    """
    out = tmp_path / "grandchild.txt"
    ready = tmp_path / "grandchild.ready"
    pidfile = tmp_path / "grandchild.pid"
    # The grandchild announces itself before it blocks, so the test can tell
    # "it was killed" from "it never started". Without that, the assertions
    # below pass just as well against a child that spawned nothing.
    #
    # Every path is stringified before interpolation. `%r` on a `PosixPath`
    # renders `PosixPath('...')`, which is a NameError in the child, and the
    # grandchild then dies before writing anything and the test blames the
    # tool for a kill that worked.
    grandchild = (
        "import time, pathlib, os; "
        "pathlib.Path(%r).write_text(str(os.getpid())); "
        "pathlib.Path(%r).write_text('ready'); "
        "time.sleep(60); pathlib.Path(%r).write_text('grandchild survived')"
        % (str(pidfile), str(ready), str(out)))
    child = ("import subprocess, sys, time; "
             "subprocess.Popen([sys.executable, '-c', %r]); time.sleep(120)"
             % grandchild)

    # The bound is 8s, not 3s, so the grandchild has room to start on a loaded
    # box before the bound fires. The grandchild's own 60s wait is what makes
    # the difference observable: a group kill has to stop it, and nothing
    # else here will.
    holder = subprocess.Popen(
        [TOOL_PY, str(TOOL), "--timeout", "8", "--kill-grace", "1", "--",
         PY, "-c", child],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=str(ROOT))
    deadline = time.monotonic() + 7
    while time.monotonic() < deadline and not ready.exists():
        time.sleep(0.05)
    assert ready.exists(), "the grandchild never started, so nothing was tested"
    grandchild_pid = int(pidfile.read_text())
    assert _alive(grandchild_pid), "the grandchild died before the bound"

    assert holder.wait(timeout=60) == 124, holder.stderr.read()
    time.sleep(1.0)
    assert not out.exists(), "the grandchild survived the group kill"
    assert not _alive(grandchild_pid), \
        "the grandchild's pid %d is still running" % grandchild_pid


def test_a_command_that_cannot_start_is_its_own_outcome():
    proc = _run("--timeout", "10", "--", "/nonexistent/binary")
    assert proc.returncode == 126, proc.stdout
    assert "outcome=startfail" in proc.stdout


def test_a_pytest_that_exits_zero_without_a_summary_is_not_a_pass():
    """A zero exit is a pass only when the run also said it finished.

    The child writes a real header, a real `-v` progress line, and a
    `short test summary info` banner, then exits 0 having written no terminal
    summary. That is what a crashed or killed pytest looks like from outside,
    and reporting it as a completed run is the defect this tool exists to
    prevent.

    The banner and the counts are in the fixture for a reason. Under a
    completion test reduced to a keyword search, a log carrying only a header
    and dots still fails to match, so the mutant would pass this test for the
    wrong reason. The banner and the progress line carrying `passed` and
    `error` in a test's own name are what make the keyword mutant match.
    """
    script = "\n".join([
        "print(%r)" % REAL_PYTEST_HEADER,
        "print(%r)" % MIDRUN_PASSED_LINE,
        "print(%r)" % MIDRUN_ERROR_LINE,
        "print('=========================== short test summary info ============================')",
        "print('.........')",
    ])
    proc = _run("--timeout", "30", "--expect", "pytest", "--", PY, "-c", script)
    assert proc.returncode == 127, proc.stdout + proc.stderr
    assert "outcome=incomplete" in proc.stdout
    assert "not a pass" in proc.stdout

    # And the same log under the keyword search the fourth lane used, which
    # is what makes this test able to catch that mutant.
    import re
    assert re.search(r"passed|failed|error", script), \
        "the fixture must match the buggy completion test"


def test_a_pytest_that_finishes_is_recognised_as_finished():
    proc = _run("--timeout", "150", "--", PY, "-m", "pytest", "-q",
                "-p", "no:cacheprovider", "tests/test_evidence_supersession.py")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "outcome=exited status=0" in proc.stdout
    assert "30 passed" in proc.stdout


def test_a_command_that_does_not_name_pytest_gets_no_summary_requirement():
    """`--expect auto` reads the command, never the log.

    A child that prints the plugin line and exits 0 is not a pytest run, so it
    is not judged by whether a summary followed. A lane wrapping pytest in its
    own script says `--expect pytest` and is held to it.
    """
    script = "print('plugins: hypothesis-6.168.0, timeout-2.4.0')"
    proc = _run("--timeout", "30", "--", PY, "-c", script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "outcome=exited status=0" in proc.stdout


# ---------------------------------------------------------------------------
# The completion test, pinned as a unit so both halves are visible.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "plugins: hypothesis-6.168.0, timeout-2.4.0, anyio-4.15.1",
    MIDRUN_PASSED_LINE,
    MIDRUN_ERROR_LINE,
    "collected 57 items",
    "tests/test_s09_study_preflight.py .......                            [ 15%]",
    "FAILED tests/test_x.py::test_a_thing - AssertionError: assert 0 == 1",
    "=========================== short test summary info ============================",
    "E   AssertionError: assert 'refused' == 'acquired-sw-alee01'",
    "57 passed",                            # a count with no elapsed time
    "in 243.92s",                           # an elapsed time with no count
    "S09ISO: dropped 38 database(s) for this run",
    "collected 0 items / 1 error",
])
def test_a_line_that_is_not_a_pytest_summary_is_not_told_apart(line):
    assert not SummaryScanner.is_summary(line), (
        "this line would satisfy a completion test without the run having "
        "finished: %r" % line)


@pytest.mark.parametrize("line", [
    REAL_PYTEST_SUMMARY,
    "16 failed, 63 passed, 2 warnings in 243.92s (0:04:03)",
    "= 1 failed, 2 passed in 0.43s =",
    "no tests ran in 0.01s",
    "57 passed, 1 xfailed in 0.01s",
    "=========== 2 passed, 1 error in 1.23s =============",
    "30 passed in 0.49s (0:00)",
])
def test_a_real_pytest_summary_is_recognised(line):
    assert SummaryScanner.is_summary(line), line


def test_the_false_completion_log_is_rejected_and_the_real_one_is_not():
    """The whole defect, quoted.

    The log below is a real pytest header followed by two real `-v` progress
    lines out of real files in this repository. It contains the substring
    `passed`, it contains the substring `error`, and it contains both inside
    the name of a single test rather than as a report about the run. A grep
    for `passed|failed|error` would call this a finished run a sixth of the
    way through a fifty-seven test file, which is the defect.

    Only the elapsed clause of a real summary tells the two apart, and that is
    what `is_summary` requires.
    """
    lines = (REAL_PYTEST_HEADER.rstrip("\n").split("\n")[:5]
             + [MIDRUN_PASSED_LINE, MIDRUN_ERROR_LINE])
    log = "\n".join(lines)

    assert "passed" in log, "the fixture must contain the word the bug matched"
    assert "error" in log, "the fixture must contain the other word too"
    assert re.search(r"passed|failed|error", log), (
        "the buggy completion test must match this log, or it is not the bug")

    assert not SummaryScanner.is_summary(lines[4]), "the plugin line matched"
    assert not SummaryScanner.is_summary(MIDRUN_PASSED_LINE), \
        "the mid-run PASSED line matched"
    assert not SummaryScanner.is_summary(MIDRUN_ERROR_LINE), \
        "the mid-run FAILED line matched"

    scanner = SummaryScanner()
    assert not any(scanner.feed(line) for line in lines), \
        "a header plus two progress lines satisfied the scanner"
    assert not scanner.completed

    assert SummaryScanner.is_summary(REAL_PYTEST_SUMMARY)
    scanner = SummaryScanner()
    assert scanner.feed(REAL_PYTEST_SUMMARY)
    assert scanner.completed
    assert scanner.summary == REAL_PYTEST_SUMMARY


def test_the_names_that_caught_it_are_real_names_in_this_repository():
    """The fixture is grounded, so it cannot drift into being convenient.

    Both names are quoted from the scanner's fixture lines, and both must name
    a test function that exists in `tests/` today. If a rename removes them,
    the fixture is updated rather than left quietly describing nothing.
    """
    repo = ROOT / "tests"
    for name in ("test_a_database_with_no_frozen_moment_is_unknown_not_passed",
                 "test_a_gateway_error_does_not_refund_the_ceiling"):
        found = any("def %s(" % name in path.read_text(errors="replace")
                    for path in repo.glob("test_*.py"))
        assert found, "no test named %s in tests/" % name


def test_a_summary_found_mid_log_is_still_a_summary():
    """Order does not matter for correctness, only for reporting.

    A lane that pipes a real run through a filter still gets a verdict, so a
    summary that is not the last line is not discarded.
    """
    lines = [MIDRUN_PASSED_LINE, "S09ISO: dropped 38 database(s)", REAL_PYTEST_SUMMARY]
    scanner = SummaryScanner()
    assert scanner.feed(lines[-1])
    assert scanner.completed


# ---------------------------------------------------------------------------
# The slow-file triage, and that the doc a lane reads agrees with the tool.
# ---------------------------------------------------------------------------

def test_a_slow_file_is_refused_before_it_starts():
    proc = _run("--timeout", "280", "--", PY, "-m", "pytest",
                "tests/test_r02_exec.py")
    assert proc.returncode == 125, proc.stdout
    assert "slow-file list" in proc.stderr
    assert "test_r02_exec.py" in proc.stderr


def test_a_refused_slow_file_runs_when_the_lane_opts_in():
    proc = _run("--timeout", "60", "--allow-slow", "--expect", "none", "--",
                PY, "-c", "print('scoped down to one test')")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_tool_never_names_a_process_to_find_work():
    """The defect this tool exists to prevent, pinned at the source level.

    A waiter that greps for a name can match itself, and did, thirteen times
    over. What must be absent is a *call* to one of these, not the words: the
    module docstring quotes the broken `pgrep` line on purpose, so a plain
    substring search would fail on the documentation of the bug.
    """
    tree = ast.parse(TOOL.read_text())
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    for banned in ("pgrep", "pkill", "psutil", "pidof", "killpg_by_name"):
        assert banned not in called, (
            "run_bounded.py must own its child's lifetime, not search for it; "
            "it calls %r" % banned)
    assert "psutil" not in TOOL.read_text(), "psutil would reintroduce a search"

    import_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            import_names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            import_names.add(node.module.split(".")[0])
    assert "psutil" not in import_names


def test_the_slow_file_list_and_the_doc_agree():
    """The table in the tool and the table a lane reads are one list.

    A lane reads the doc before it dispatches, and the tool decides whether to
    start. If those disagree, the doc is wrong at the exact moment a lane is
    about to spend an hour on the file.
    """
    doc = (ROOT / "docs" / "LONG-RUNNING-TESTS.md").read_text()
    listed = {line.split("`")[1] for line in doc.split("\n")
              if line.strip().startswith("| `test_") and "`" in line}
    listed = {name for name in listed if name in SLOW_FILES}
    assert listed == set(SLOW_FILES), (
        "doc-only=%r tool-only=%r"
        % (sorted(listed - set(SLOW_FILES)),
           sorted(set(SLOW_FILES) - listed)))
    for name, (basis, reason) in SLOW_FILES.items():
        assert basis in ("measured", "read"), name
        assert reason.strip(), name


def test_the_claim_about_the_swe_file_is_pinned_to_its_own_bytes():
    """The file this lane was told costs minutes does not.

    Two briefs described `test_s09_swe_experiment.py` as spawning real
    subprocess episodes. It spawns none: it imports no `subprocess`, sleeps
    nowhere, and opens no database. A full episode measured 0.11s here. The
    claim is pinned against the file's own bytes, so if someone really does add
    a spawn to it, this goes red instead of the triage quietly going stale.
    """
    source = (ROOT / "tests" / "test_s09_swe_experiment.py").read_text()
    assert "subprocess" not in source, "the claim no longer holds"
    assert "sleep(" not in source, "the claim no longer holds"
    assert "swe_matrix" in source, "it must keep carrying the repo's marker"
    assert "test_s09_swe_experiment.py" in SLOW_FILES, (
        "it stays on the list, on its compute cost, not a subprocess one")


# ---------------------------------------------------------------------------
# The slot cap.
# ---------------------------------------------------------------------------

def test_a_second_runner_on_a_held_slot_is_refused(tmp_path):
    holder = subprocess.Popen(
        [TOOL_PY, str(TOOL), "--timeout", "60", "--slot", "demo", "--slot-dir",
         str(tmp_path), "--", PY, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=str(ROOT))
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (tmp_path / "demo").exists():
            time.sleep(0.1)
        assert (tmp_path / "demo").exists(), "the first runner never took the slot"
        record = json.loads((tmp_path / "demo" / "holder.json").read_text())
        assert record["pid"] == holder.pid, "the holder is not this pid"

        second = _run("--timeout", "60", "--slot", "demo", "--slot-dir",
                      str(tmp_path), "--json", "--", PY, "-c", "pass")
        body = _outcome(second.stdout)
        assert second.returncode == 125, second.stdout
        assert body["outcome"] == "refused", body
        assert "held by" in body["detail"], body
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_a_slot_is_released_when_its_runner_exits(tmp_path):
    proc = _run("--timeout", "30", "--slot", "demo", "--slot-dir", str(tmp_path),
                "--", PY, "-c", "pass")
    assert proc.returncode == 0, proc.stdout
    assert not (tmp_path / "demo").exists(), "the slot leaked"


def test_a_slot_whose_holder_was_killed_is_reclaimed(tmp_path):
    """A crash between taking the slot and finishing it must not wedge a lane."""
    slot = tmp_path / "demo"
    slot.mkdir()
    (slot / "holder.json").write_text(
        json.dumps({"pid": 999_999_999, "label": "dead"}))
    proc = _run("--timeout", "30", "--slot", "demo", "--slot-dir",
                str(tmp_path), "--json", "--", PY, "-c", "pass")
    body = _outcome(proc.stdout)
    assert proc.returncode == 0, proc.stdout
    assert body["outcome"] == "exited", body


def test_a_slot_with_no_holder_record_is_reclaimed_only_once_it_is_stale(tmp_path):
    slot = tmp_path / "demo"
    slot.mkdir()
    proc = _run("--timeout", "30", "--slot", "demo", "--slot-dir", str(tmp_path),
                "--json", "--", PY, "-c", "pass")
    body = _outcome(proc.stdout)
    assert proc.returncode == 125, proc.stdout
    assert "held by unknown" in body["detail"], body
    os.utime(slot, (0, 0))
    stale = _run("--timeout", "30", "--slot", "demo", "--slot-dir",
                 str(tmp_path), "--json", "--", PY, "-c", "pass")
    assert stale.returncode == 0, stale.stdout


def test_a_refused_runner_leaves_a_foreign_slot_alone(tmp_path):
    """A runner turned away by a held slot must not clear it.

    `run` returns the refusal before it reaches the `finally` that releases,
    so this holds through the interface as well as through `Slot.release`
    itself, which `test_release_only_clears_a_slot_this_process_holds`
    exercises directly.
    """
    slot = tmp_path / "demo"
    slot.mkdir()
    (slot / "holder.json").write_text(
        json.dumps({"pid": os.getpid(), "label": "someone else"}))
    proc = _run("--timeout", "30", "--slot", "demo", "--slot-dir", str(tmp_path),
                "--", PY, "-c", "pass")
    assert proc.returncode == 125, proc.stdout
    assert slot.exists(), "a refused runner cleared a slot it did not hold"
    assert json.loads((slot / "holder.json").read_text())["label"] == "someone else"


def test_a_corrupt_holder_file_is_reclaimable_not_a_crash(tmp_path):
    """Cleanup code that crashes on a corrupt input cannot clean up.

    A pid that cannot be an address makes `os.kill` raise `OverflowError`,
    and a holder file is exactly the sort of file that is half-written when
    the process holding it was killed mid-write.
    """
    from scripts.run_bounded import Slot

    slot = tmp_path / "demo"
    slot.mkdir()
    (slot / "holder.json").write_text(json.dumps({"pid": 2 ** 70}))
    runner = Slot("demo", tmp_path)
    proc = _run("--timeout", "30", "--slot", "demo", "--slot-dir", str(tmp_path),
                "--json", "--", PY, "-c", "pass")
    body = _outcome(proc.stdout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert body["outcome"] == "exited", body
    assert runner._alive(2 ** 70) is False


def test_release_only_clears_a_slot_this_process_holds(tmp_path):
    """`release` is guarded on the holder's own pid, not on having refused.

    The guard is unreachable through the CLI, because `run` returns a refusal
    before the `finally` that calls `release`. It is kept because `release`
    clears a directory named by a caller, and a caller that invokes it after
    a partial failure would otherwise free a lane's slot. This test calls it
    directly, which is the only way to reach the branch.
    """
    from scripts.run_bounded import Slot

    held = Slot("held", tmp_path)
    assert held.acquire("mine") is None, "could not take the slot to release"

    other = Slot("held", tmp_path)
    record = json.loads((tmp_path / "held" / "holder.json").read_text())
    assert record["pid"] == os.getpid()

    # Pretend a different process holds it, by rewriting the holder record.
    (tmp_path / "held" / "holder.json").write_text(
        json.dumps({"pid": os.getpid() + 1, "label": "not me"}))
    other.release()
    assert (tmp_path / "held").exists(), \
        "release cleared a slot held by a different pid"

    # And it does clear its own.
    (tmp_path / "held" / "holder.json").write_text(
        json.dumps({"pid": os.getpid(), "label": "me"}))
    other.release()
    assert not (tmp_path / "held").exists(), "release left its own slot behind"


# ---------------------------------------------------------------------------
# Status remapping, so a child's reserved status stays recoverable.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("child,expected", [
    (0, 0), (1, 1), (9, 9), (123, 123),
    (124, 128), (125, 129), (126, 130), (127, 131),
    (130, 130), (200, 200),
])
def test_a_child_status_is_reported_unless_it_collides_with_ours(child, expected):
    proc = _run("--timeout", "30", "--", PY, "-c",
                "import sys; sys.exit(%d)" % child)
    assert proc.returncode == expected, (
        "child %d surfaced as %d" % (child, proc.returncode))


def test_a_bad_invocation_is_refused_not_run():
    proc = _run("--timeout", "30")
    assert proc.returncode != 0
    assert "no command" in proc.stderr
    assert _run("--timeout", "0", "--", PY, "-c", "pass").returncode == 125


def test_an_unreaped_child_is_never_reported_as_a_zero():
    """`Popen.returncode` is `None` until the child is reaped.

    A child that survives SIGKILL as an unkillable kernel thread leaves it
    `None`, and `None` is not a zero. This is the one path by which this tool
    could report a pass it has no evidence for, so it is pinned directly on
    the exit-code function rather than left to a subprocess that would have
    to be unkillable to reach it.
    """
    from scripts.run_bounded import Outcome, exit_code
    from scripts import run_bounded

    assert exit_code(Outcome("exited", status=0)) == 0
    with pytest.raises(ValueError):
        exit_code(Outcome("exited"))

    # And the CLI reports it as a refusal rather than a traceback.
    original = run_bounded.run
    run_bounded.run = lambda *a, **k: Outcome("exited", status=None)
    try:
        assert run_bounded.main(["--timeout", "5", "--", PY, "-c", "pass"]) == 127
    finally:
        run_bounded.run = original


def _alive(pid: int) -> bool:
    return _pid_alive(pid)
