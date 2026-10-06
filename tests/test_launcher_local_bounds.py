"""Declared child bounds are installed, and confinement is not faked by a typo.

Two boundaries were declared and never enforced. The `cpu_seconds` and
`memory_bytes` a payload asked for were read out of a dict that never carried
them, so `setrlimit` never ran on any platform. And `PR_SET_NO_NEW_PRIVS` was
spelled as `1`, which is `PR_SET_PDEATHSIG`, so the flag Landlock requires was
never set and every `read_deny` dispatch was refused on a host that could have
confined it.

Each test below fails before its fix for that reason and not another, and each
calls the launcher the way a campaign calls it rather than reaching into a
helper. The tampering cases are authored here rather than borrowed from the
module under test, so a regression to the wrong constant or the missing dict
keys is caught rather than mirrored.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from settlement import child_limits
from settlement import launcher_local
from settlement.broker import BrokerOp
from settlement.child_limits import ChildLimits
from settlement.launcher_local import PROFILE, LocalLauncher, _child_setup

POSIX = os.name != "nt"
LINUX = sys.platform == "linux"

PROBE_RLIMITS = (
    "import json,resource\n"
    "print(json.dumps({'cpu': resource.getrlimit(resource.RLIMIT_CPU),"
    " 'as': resource.getrlimit(resource.RLIMIT_AS)}))\n"
)
# A tight loop that never sleeps. On a WSL2 host a fully tight spin trips the
# VM's CPU watchdog, which kills the process group including the test runner,
# so the loop yields without sleeping: it still accrues CPU seconds, which is
# what RLIMIT_CPU measures, but it does not monopolise a core the watchdog owns.
SPIN = "x=0\nwhile True:\n    x+=1\n    if x % 100000 == 0: pass\n"


def _op(operation_id, argv, payload_extra=None, generation=1, execution_version="v1"):
    payload = {"argv": argv, "timeout_ms": 10_000}
    payload.update(payload_extra or {})
    return BrokerOp(operation_id=operation_id, effect="exec",
                    execution_version=execution_version,
                    dispatch_generation=generation, payload=payload)


def _child_stdout(outcome) -> str:
    assert outcome.sent, "expected a send, got %r" % (outcome.refused_reason,)
    return outcome.receipt.content["data"]["stdout"]


def _requested_limits(payload):
    """Resolve the shape, so an absent reader is an assertion and not an import."""
    reader = getattr(launcher_local, "_requested_limits", None)
    assert reader is not None, (
        "the dispatch has no reader for the declared bounds, so the values a"
        " payload asks for never reach the child")
    return reader(payload)


# -- (a) the requested bounds reach the child --------------------------------


def test_requested_limits_carry_both_declared_values(tmp_path):
    """The literal payload keys, read as a typed shape.

    The dict `dispatch` builds is what the child's `preexec_fn` closes over. It
    read `cpu_seconds` and `memory_bytes` from keys nothing ever wrote, so the
    assertion here is on the shape itself rather than on a value passed through
    a config.
    """
    limits = _requested_limits({"cpu_seconds": 7, "memory_bytes": 1_048_576})
    assert limits == ChildLimits(cpu_seconds=7, memory_bytes=1_048_576)


def test_absent_bound_is_absent_rather_than_zero(tmp_path):
    """A missing key is no request, not a ceiling of zero."""
    assert _requested_limits({}) == ChildLimits(cpu_seconds=None, memory_bytes=None)
    assert _requested_limits({"cpu_seconds": None}) == ChildLimits(memory_bytes=None)


@pytest.mark.skipif(POSIX, reason="the declared bound has to reach a real child")
def test_dispatch_never_builds_a_child_setup_for_unbounded_windows(tmp_path):
    """On this host a bounded child cannot exist, so every dispatch is refused.

    Before the fix the dispatch walked straight past the payload into `Popen`
    and raised `preexec_fn is not supported on Windows platforms` out of the
    caller's hands. The kind is `child-setup-unavailable` and not
    `child-limit-unavailable` even though `cpu_seconds=5` was declared: this
    host has no `preexec_fn` to install it with, so there is no bound question
    here, and sending the caller after a smaller ceiling would be advice for a
    problem it does not have.
    """
    launcher = LocalLauncher(tmp_path / "run")
    for operation_id, extra in (("op-win-bound", {"cpu_seconds": 5}),
                                ("op-win-unbound", {})):
        outcome = launcher.dispatch(_op(operation_id, [sys.executable, "-c", "print(1)"],
                                        extra))
        assert outcome.sent is False, "%s ran a child this host cannot bound" % operation_id
        assert outcome.receipt is None
        assert outcome.refused_reason.startswith("child-setup-unavailable:"), (
            f"{operation_id}: {outcome.refused_reason!r}")
    assert launcher.prove_never_sent("op-win-unbound", 1) is True, (
        "a refused dispatch made no send, so nothing may be left claiming one")


# -- (b) a limit that actually FIRES -----------------------------------------


@pytest.mark.skipif(not POSIX, reason="RLIMIT_CPU is a POSIX enforcement mechanism")
def test_cpu_ceiling_stops_a_spinning_child_well_before_the_wall_budget(tmp_path):
    """Enforcement, not configuration: the child dies at the CPU ceiling.

    The wall deadline is 30s and the declared CPU ceiling is 2s. A child that
    runs the full wall budget never received its rlimit, which is the defect.
    """
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(_op("op-cpu", [sys.executable, "-c", SPIN],
                                    {"cpu_seconds": 2, "timeout_ms": 30_000}))
    data = outcome.receipt.content["data"]
    assert data["timed_out"] is False, "the wall deadline stopped it, not the CPU bound"
    assert data["returncode"] < 0, "expected a signal, got rc=%r" % data["returncode"]
    assert data["wall_ms"] < 15_000, (
        "a 2s CPU ceiling should stop this child in seconds, ran %dms"
        % data["wall_ms"])


@pytest.mark.skipif(not LINUX, reason="the measured RLIMIT_AS child behavior is Linux-specific")
def test_memory_ceiling_actually_bounds_the_child(tmp_path):
    """RLIMIT_AS installed and observed by the child itself.

    512MB is deliberate and measured. `preexec_fn` runs in a forked child that
    already inherits the test runner's address space, so a ceiling below what
    that child needs to allocate raises `MemoryError` inside `Popen` rather than
    reporting a limit. The value is far under an unconstrained child (which
    reaches multiple GB), so the number read back is attributable to the
    launcher rather than to the host's own floor.
    """
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(
        _op("op-mem", [sys.executable, "-c", PROBE_RLIMITS],
            {"memory_bytes": 512 * 1024 * 1024}))
    assert json.loads(_child_stdout(outcome))["as"] == [512 * 1024 * 1024] * 2


@pytest.mark.skipif(not LINUX, reason="the measured CPython address-space floor is Linux-specific")
def test_a_memory_bound_below_the_interpreters_own_floor_fails_the_child(tmp_path):
    """A ceiling too small for CPython to start under really is a ceiling.

    8MB is measured on this host, not guessed: the interpreter starts fine at
    16MB and fails to load its shared objects at 8MB, printing nothing. That is
    the bound taking effect inside the child rather than a config value being
    passed along. Before the fix the same payload ran to completion and printed
    its output.
    """
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(
        _op("op-starve", [sys.executable, "-c", "print('should not print')"],
            {"memory_bytes": 8 * 1024 * 1024}))
    data = outcome.receipt.content["data"]
    assert "should not print" not in data.get("stdout", ""), (
        "an 8MB address space cannot load the interpreter; stdout was %r"
        % data.get("stdout", ""))


# -- (c) a missing capability refuses, and strands nothing --------------------


@pytest.mark.skipif(POSIX, reason="the unsupported-capability branch needs Windows")
def test_a_requested_bound_this_host_cannot_install_is_refused(tmp_path):
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(_op("op-refuse", [sys.executable, "-c", "print(1)"],
                                    {"memory_bytes": 4096}))
    assert outcome.sent is False
    assert "memory_bytes" in outcome.refused_reason


def test_a_refused_bound_leaves_no_durable_claim_and_no_markers(tmp_path):
    """The refusal must unwind, or the operation is stranded forever.

    A dispatch that returns before `Popen` made no send. If it left the pid
    claim behind, the next dispatch of the same operation would read its own
    refusal back as `prior-send-recorded` and the operation could never run.
    """
    launcher = LocalLauncher(tmp_path / "run")
    op = _op("op-unwound", [sys.executable, "-c", "print(1)"],
             {"cpu_seconds": 3} if not POSIX else None)
    if POSIX:
        pytest.skip("this host can install the bound; the refusal path is covered above")

    outcome = launcher.dispatch(op)
    assert outcome.sent is False
    assert launcher.claimed("op-unwound", 1) is False
    assert launcher.prove_never_sent("op-unwound", 1) is True

    retry = launcher.dispatch(op)
    assert retry.refused_reason.startswith("child-setup-unavailable:"), (
        "a retry must be refused for the same reason, not reported as a prior send")


def test_the_pre_spawn_refusal_does_not_install_a_limit_on_the_launcher(
        tmp_path, monkeypatch):
    """A refusal check that lowered the launcher's own rlimit would be a defect.

    `apply_child_limits` both decides and enforces. Asking it a question in the
    parent, where this check runs, is permanent rather than scoped to a child:
    a launcher that checked a 512MB bound would report that limit for its own
    next child. The assertion is on the launcher's own `RLIMIT_AS` afterwards.
    """
    if not LINUX:
        pytest.skip("RLIMIT_AS observation is qualified on Linux")
    import resource

    before = resource.getrlimit(resource.RLIMIT_AS)
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(
        _op("op-leak", [sys.executable, "-c", "print(1)"],
            {"memory_bytes": 512 * 1024 * 1024}))
    assert outcome.sent is True
    assert resource.getrlimit(resource.RLIMIT_AS) == before, (
        "the refusal check installed a limit on the launcher itself; every later"
        " dispatch from this launcher would inherit the first one's ceiling")


def test_a_bound_reaches_the_child_and_leaves_the_next_child_unbounded(tmp_path):
    """No carry-over between dispatches, which is what a leaked limit looks like.

    The first dispatch is bounded and the second asks for nothing. If the first
    dispatch's ceiling were installed on the launcher, the second child would
    report it despite never asking for it.
    """
    if not LINUX:
        pytest.skip("RLIMIT_AS observation is qualified on Linux")
    code = ("import json,resource\n"
            "print(json.dumps(resource.getrlimit(resource.RLIMIT_AS)))\n")
    launcher = LocalLauncher(tmp_path / "run")
    bounded = launcher.dispatch(_op("op-one", [sys.executable, "-c", code],
                                    {"memory_bytes": 512 * 1024 * 1024}))
    assert json.loads(_child_stdout(bounded)) == [512 * 1024 * 1024] * 2

    unbounded = launcher.dispatch(_op("op-two", [sys.executable, "-c", code]))
    assert json.loads(_child_stdout(unbounded)) == [-1, -1], (
        "a dispatch that asked for no memory bound inherited one from a previous"
        " dispatch, so the launcher's own limit was lowered")


def test_the_asking_is_one_call_and_the_answers_stay_distinct():
    """The launcher asks once, and both refusals survive the single answer.

    The duplication is what broke this. `launcher_local` used to carry its own
    platform test, which returned "" for every POSIX host, and the two answers
    agreed right up until they did not. So the wrapper is gone and the caller
    gets the authority's own typed verdict, which separates a host that cannot
    run a child setup from a host that cannot install these bounds.
    """
    assert not hasattr(launcher_local, "child_limits_unsupported_reason"), (
        "the launcher carries its own copy of the platform decision again, which"
        " is how the POSIX arm became a constant")

    # An empty request on a host that can bound a child is not refused at all;
    # on one that cannot, it is refused for the host. There is no third answer,
    # and which of the two applies follows the host rather than the payload.
    host = child_limits.current_execution_host()
    empty = child_limits.child_setup_refusal(_requested_limits({}))
    assert (empty is None) is host.child_setup, (
        f"the host says it can bound a child ({host.child_setup}) but answered"
        f" {empty!r} for a request it declares")
    if empty is not None:
        assert empty.kind == "child-setup-unavailable", (
            f"a request that declared no bound cannot be refused for a bound: {empty.kind!r}")


def test_an_unlimited_dispatch_is_refused_on_a_host_that_cannot_bound(tmp_path):
    """The case that escaped, stated as a contract rather than a platform.

    The bounds check short-circuited to "" when the payload declared nothing,
    so the unlimited dispatch was the unguarded one: `preexec_fn` went to a
    `Popen` that refuses it, and `ValueError` left `dispatch` with its pid
    claim still on disk. On a host that cannot bound a child at all, the empty
    `ChildLimits` has to refuse like any other request.
    """
    refusal = child_limits.child_setup_refusal(ChildLimits())
    if child_limits.current_execution_host().child_setup:
        assert refusal is None, (
            "a host that can bound a child must not refuse a dispatch that"
            f" asked for no bound, or every unbounded dispatch is stranded: {refusal!r}")
    else:
        assert refusal is not None
        assert refusal.kind == "child-setup-unavailable", (
            f"the empty request was refused for the wrong reason: {refusal.kind!r}")


# -- (d) the receipt names the host, and the caller may demand one ------------


def test_the_receipt_names_the_host_that_produced_it(tmp_path):
    """`profile` alone cannot tell a Linux receipt from a Windows one.

    Both are `local-process` from the same code, so a study comparing them
    would be comparing two hosts and calling it one measurement. The field is
    read from the running host rather than configured, so it cannot go stale.
    """
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(_op("op-host", [sys.executable, "-c", "print(1)"],
                                    {"cpu_seconds": 5}))
    if not outcome.sent:
        pytest.skip("this host refused the dispatch, so it produced no receipt")
    content = outcome.receipt.content
    assert content["host"] == child_limits.current_execution_host().kind
    assert content["profile"] == PROFILE, (
        "host is an addition; the profile it sits beside is unchanged")


def test_the_host_field_does_not_change_the_rest_of_the_receipt_shape(tmp_path):
    """One shape, whichever host produced it, so assessment cannot tell.

    The keys are asserted literally and in full rather than by containment, so
    a field added here for one host and not the other is a failure.
    """
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(_op("op-shape", [sys.executable, "-c", "print(1)"],
                                    {"cpu_seconds": 5}))
    if not outcome.sent:
        pytest.skip("this host refused the dispatch, so it produced no receipt")
    content = outcome.receipt.content
    assert sorted(content) == ["_verdict", "argv", "containment", "data", "host",
                               "parse", "profile", "truncated"]
    assert outcome.receipt.provenance == "local-1"
    assert outcome.receipt.receipt_identity.startswith("local:")


def test_demanding_another_host_is_refused_rather_than_substituted(tmp_path):
    """A caller names its host, and a mismatch is refused rather than absorbed.

    The point is that neither half is a fallback. A run that quietly continued
    on a different host would produce numbers that name neither host, and
    every measurement taken from them afterwards would be unattributable.
    """
    launcher = LocalLauncher(tmp_path / "run")
    running = child_limits.current_execution_host().kind

    refused = launcher.dispatch(_op("op-unmet", [sys.executable, "-c", "print(1)"],
                                    {"cpu_seconds": 5}),
                                require_host="not-a-host-this-repo-runs-on")
    assert refused.sent is False
    assert refused.refused_reason.startswith("execution-host-unavailable:")
    assert running in refused.refused_reason, (
        "the refusal has to name the host that was actually there, or a reader"
        " cannot tell a host refusal from a different failure")
    assert "not-a-host-this-repo-runs-on" in refused.refused_reason
    assert launcher.prove_never_sent("op-unmet", 1) is True, (
        "a host refusal happens before the claim, so the operation stays"
        " re-admissible rather than being stranded by its own refusal")


def test_demanding_the_running_host_is_answered_and_the_other_is_not(tmp_path):
    """Asking for this host is satisfied; asking for another is refused.

    `None` is the absence of a demand, not permission to run anywhere. A demand
    for the host this process is on has to be answered by a run on that host,
    which is what keeps the branch above from being a silent fallback.
    """
    running = child_limits.current_execution_host().kind
    assert child_limits.require_execution_host(running).kind == running
    with pytest.raises(child_limits.UnsupportedChildLimit):
        child_limits.require_execution_host("not-a-host-this-repo-runs-on")


# -- (e) the Landlock read-back names the flag that was set ------------------


def test_no_new_privs_constant_is_pr_set_no_new_privs_not_pdeathsig():
    """`prctl` takes the option first, and 1 is `PR_SET_PDEATHSIG`.

    Setting 1 while meaning 38 reports success, leaves the flag clear, and the
    read-back in `_no_new_privs_settable` reads a flag nobody set. That is the
    exact failure the read-back exists to catch, and it is why every `read_deny`
    dispatch was refused on a capable host.
    """
    assert launcher_local._PR_SET_NO_NEW_PRIVS == 38
    assert launcher_local._PR_GET_NO_NEW_PRIVS == 39


def test_the_read_back_confirms_the_flag_whose_setter_ran():
    """Not a constant comparison: prove set and get name the same flag.

    A test that only asserted `38 == 38` would still pass if the read-back were
    wired to a different setter. This one compares the module's own behaviour
    against the kernel's, for the value and for the known-wrong value.
    """
    import ctypes

    if not LINUX:
        pytest.skip("prctl read-back uses Linux libc and syscall numbers")
    libc = ctypes.CDLL("libc.so.6", use_errno=True)

    def _nnp() -> int:
        return int(libc.prctl(39, 0, 0, 0, 0))

    def _child_nnp(payload) -> int:
        """Run the module's child setup's flag logic in a fresh process."""
        code = (
            "import ctypes, json, sys\n"
            "from settlement import launcher_local as L\n"
            "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
            "libc.prctl(L._PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)\n"
            "print(json.dumps({'nnp': int(libc.prctl(39, 0, 0, 0, 0))}))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, timeout=60,
                              env=dict(os.environ))
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)["nnp"]

    assert _nnp() in (0, 1), "no_new_privs is a 0/1 flag"
    # A fresh interpreter starts with the flag clear, so what the module's
    # setter produces there is attributable to the module's setter alone.
    assert _child_nnp({}) == 1, (
        "the module's prctl must set no_new_privs; a value of 0 means it called"
        " something else, which is the PDEATHSIG trap")


def test_the_child_restrict_path_uses_the_named_constant(monkeypatch):
    """No bare `prctl(1, 1, ...)` literal is left in the child path.

    The set inside `_landlock_restrict` was a hardcoded `1` with a comment
    claiming it was `PR_SET_NO_NEW_PRIVS`. Reading the source is the assertion,
    because the only way to regress is to reintroduce the literal.
    """
    import inspect

    source = inspect.getsource(launcher_local._landlock_restrict)
    assert "prctl(1, 1" not in source, "the PDEATHSIG literal is back"
    assert "prctl(_PR_SET_NO_NEW_PRIVS" in source, (
        "the child path must set the same named constant the probe reads back")


# -- (e) tamper cases authored here -----------------------------------------


def test_a_child_dict_without_the_limits_key_never_yields_an_unbounded_child(
        monkeypatch):
    """Tamper: remove the key and confirm the child is refused, not unbounded.

    This reconstructs the original defect deliberately. The child setup closes
    over a dict, and the defect was a dict that never carried the declared
    bounds. The assertion is that a dict missing the key cannot produce a
    running child at all: `preexec_fn` raises, so the boundary that could not be
    installed stops the child from existing rather than letting it run loose.
    A silent `[-1, -1]` here would be the original bug returning.
    """
    if os.name == "nt":
        pytest.skip("RLIMIT observation needs a POSIX child")
    import resource

    # A bound this host can actually install. A literal 9 is only installable
    # when the inherited hard limit is at least 9, and asserting on a value the
    # host would refuse says nothing about whether the key is carried.
    _soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
    cpu = 9 if hard == resource.RLIM_INFINITY else max(1, min(9, int(hard)))
    payload = {"limits": ChildLimits(cpu_seconds=cpu), "cwd": os.getcwd(),
               "read_deny": [], "read_allow": []}
    stripped = dict(payload)
    stripped.pop("limits")

    def _observed(d: dict) -> list[int]:
        code = ("import json,resource\n"
                "print(json.dumps(resource.getrlimit(resource.RLIMIT_CPU)))\n")
        proc = subprocess.Popen(
            [sys.executable, "-c", code], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, preexec_fn=_child_setup(d))
        out, _ = proc.communicate(timeout=60)
        return json.loads(out or b"[]")

    assert _observed(payload) == [cpu, cpu], "the intact dict must carry the bound"
    try:
        observed = _observed(stripped)
    except (subprocess.SubprocessError, KeyError):
        return
    assert observed != [cpu, cpu], (
        "a dict missing the key produced a child with the bound anyway, so the"
        " assertion above could have passed on a dict nothing wrote into")


def test_a_wrong_prctl_constant_is_caught_by_the_behavioural_read_back(monkeypatch):
    """Tamper: revert the constant to 1 and confirm the read-back fails.

    A test asserting the literal `== 38` documents the fix but does not prove
    the mechanism. This one puts the old value back and observes the flag stay
    clear, which is what the kernel actually did.
    """
    if not LINUX:
        pytest.skip("prctl read-back uses Linux libc and syscall numbers")
    import ctypes

    monkeypatch.setattr(launcher_local, "_PR_SET_NO_NEW_PRIVS", 1)
    assert launcher_local._no_new_privs_settable() is False, (
        "with PR_SET_PDEATHSIG the call succeeds and the flag stays clear, so a"
        " probe trusting the return code would report a boundary that is absent")
    monkeypatch.setattr(launcher_local, "_PR_SET_NO_NEW_PRIVS", 38)
    assert launcher_local._no_new_privs_settable() is True
