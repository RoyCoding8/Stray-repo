"""Child-limit enforcement is one decision, and it never degrades to unbounded.

Each test calls the layer the way `exec_profile` calls it and asserts literal
values. All of these fail before the change for the right reason: the
`settlement.child_limits` module did not exist, and the `RLIMIT` calls were
inlined in `exec_profile` behind an unguarded `import resource`.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from settlement import child_limits
from settlement.child_limits import ChildLimits, UnsupportedChildLimit, apply_child_limits
from settlement.common import ResultCode, SettlementError

POSIX = os.name != "nt"
RECORD = []


class _RecordingResource:
    """A stand-in for the stdlib `resource` module on the POSIX branch.

    It models `getrlimit` as well as `setrlimit` because the enforcement now
    asks the host a question before it acts, and the question is a read of the
    inherited hard limits. A stand-in that only implemented the write would
    have hidden that second call rather than failed on it.
    """

    RLIMIT_CPU = 0
    RLIMIT_AS = 1
    RLIM_INFINITY = -1

    def __init__(self, hard_cpu=RLIM_INFINITY, hard_as=RLIM_INFINITY):
        self._hard = {self.RLIMIT_CPU: hard_cpu, self.RLIMIT_AS: hard_as}

    def getrlimit(self, which):
        return (self._hard.get(which, self.RLIM_INFINITY), self._hard.get(which, self.RLIM_INFINITY))

    def setrlimit(self, which, pair):
        RECORD.append((which, pair))


def _apply_as_if(posix_os_name: str, limits: ChildLimits) -> None:
    """Run `apply_child_limits` as if the platform were `posix_os_name`."""
    original = os.name
    os.name = posix_os_name  # type: ignore[misc]
    RECORD.clear()
    try:
        apply_child_limits(limits)
    finally:
        os.name = original  # type: ignore[misc]


def test_posix_branch_calls_setrlimit_with_the_requested_values(monkeypatch):
    monkeypatch.setitem(sys.modules, "resource", _RecordingResource())
    _apply_as_if("posix", ChildLimits(cpu_seconds=7, memory_bytes=1048576))
    assert RECORD == [
        (_RecordingResource.RLIMIT_CPU, (7, 7)),
        (_RecordingResource.RLIMIT_AS, (1048576, 1048576)),
    ]


def test_posix_branch_omits_a_limit_that_was_not_requested(monkeypatch):
    monkeypatch.setitem(sys.modules, "resource", _RecordingResource())
    _apply_as_if("posix", ChildLimits(cpu_seconds=3))
    assert RECORD == [(_RecordingResource.RLIMIT_CPU, (3, 3))]


def test_posix_branch_applies_nothing_when_no_limit_is_requested(monkeypatch):
    monkeypatch.setitem(sys.modules, "resource", _RecordingResource())
    _apply_as_if("posix", ChildLimits())
    assert RECORD == []


# -- the question asked without the act ---------------------------------------
#
# `apply_child_limits` both decides and enforces, so a caller cannot ask it
# "can this host install these?" without lowering its OWN limits: a setrlimit in
# the parent is permanent rather than scoped to a child. These tests pin the
# side-effect-free answer, and the refusal it makes possible.


def _refusal_as_if(posix_os_name: str, limits: ChildLimits):
    """Ask the question as if the platform were `posix_os_name`."""
    original = os.name
    os.name = posix_os_name  # type: ignore[misc]
    try:
        return child_limits.child_setup_refusal(limits)
    finally:
        os.name = original  # type: ignore[misc]


def _supported_as_if(posix_os_name: str, limits: ChildLimits) -> str:
    """The refusal text for `limits`, or "" when this host can install them."""
    refusal = _refusal_as_if(posix_os_name, limits)
    return refusal.reason if refusal is not None else ""


def test_the_question_does_not_install_a_limit_on_the_asking_process(monkeypatch):
    """Reading the host's limits must leave them exactly as they were.

    The bug this shape exists to prevent: a launcher that learned a 512MB bound
    by applying it reported that limit for its own next child and could not
    raise it again. So the assertion is on the side effect, not on the answer.
    """
    monkeypatch.setitem(sys.modules, "resource", _RecordingResource())
    assert _supported_as_if("posix", ChildLimits(cpu_seconds=7, memory_bytes=1048576)) == ""
    assert RECORD == [], "asking the question wrote a limit instead of reading one"


def test_a_bound_above_the_hard_limit_is_refused_before_the_spawn(monkeypatch):
    """The host has the mechanism and cannot install this bound. Refuse it.

    `RLIMIT_CPU` is inherited by every child and an unprivileged launcher
    cannot raise the hard limit, so a declared ceiling above it is a promise
    the host cannot keep. Before the fix the POSIX arm of the platform test
    returned "" for every POSIX host, the check passed, and the child failed to
    install a bound nobody had checked.
    """
    monkeypatch.setitem(sys.modules, "resource",
                        _RecordingResource(hard_cpu=3, hard_as=_RecordingResource.RLIM_INFINITY))
    refusal = _refusal_as_if("posix", ChildLimits(cpu_seconds=500))
    assert refusal is not None, (
        "a POSIX host whose hard RLIMIT_CPU is 3 was told it can install"
        " cpu_seconds=500; that is the defect this refusal exists to prevent")
    assert refusal.kind == "child-limit-unavailable", (
        "a host that CAN bound a child must refuse for its own reason, not"
        f" for the platform's; got {refusal.kind!r}")
    assert "cpu_seconds" in refusal.reason
    assert "500" in refusal.reason, (
        f"the refusal does not name the declared value: {refusal.reason!r}")
    assert RECORD == [], "the refusal installed a limit on the asking process"

    with pytest.raises(UnsupportedChildLimit):
        _apply_as_if("posix", ChildLimits(cpu_seconds=500))
    assert RECORD == [], "a refused bound was installed anyway"


def test_a_bound_within_the_hard_limit_is_not_refused(monkeypatch):
    """The other direction, so the refusal cannot become a blanket refusal."""
    monkeypatch.setitem(sys.modules, "resource",
                        _RecordingResource(hard_cpu=500, hard_as=_RecordingResource.RLIM_INFINITY))
    assert _supported_as_if("posix", ChildLimits(cpu_seconds=500)) == ""
    assert _supported_as_if("posix", ChildLimits(cpu_seconds=499)) == ""


def test_an_unlimited_host_refuses_nothing(monkeypatch):
    """`RLIM_INFINITY` is not a low limit. It is the absence of one."""
    monkeypatch.setitem(sys.modules, "resource", _RecordingResource())
    for limits in (ChildLimits(cpu_seconds=10**9),
                   ChildLimits(memory_bytes=10**12),
                   ChildLimits(cpu_seconds=10**9, memory_bytes=10**12)):
        assert _supported_as_if("posix", limits) == ""


def test_a_low_soft_limit_is_not_a_refusal(monkeypatch):
    """Only the HARD limit is a promise the host cannot keep.

    A soft limit below the declared bound is not a defect: the child inherits
    it and the install lowers its own soft limit to the declared value, which
    is what installing a bound means. A check that read the soft limit would
    refuse a host that can in fact honour the bound, on a machine configured to
    be conservative.
    """
    class _LowSoft(_RecordingResource):
        def getrlimit(self, which):
            return (1, self._hard.get(which, self.RLIM_INFINITY))

    monkeypatch.setitem(sys.modules, "resource", _LowSoft(hard_cpu=500))
    assert _supported_as_if("posix", ChildLimits(cpu_seconds=500)) == ""


def test_the_two_refusals_are_distinguishable_by_kind_not_by_wording(monkeypatch):
    """A caller has to be able to tell "wrong host" from "wrong number".

    They are answered by different people. A host that cannot run a child setup
    at all needs a different machine. A host that can but cannot install the
    declared ceiling needs a smaller number, and the number is the caller's to
    choose. Collapsing them into one string loses the distinction, so the kind
    is part of the value and a reader can branch on it without matching text.
    """
    monkeypatch.setitem(sys.modules, "resource",
                        _RecordingResource(hard_cpu=3, hard_as=_RecordingResource.RLIM_INFINITY))

    no_setup = child_limits.ExecutionHost(
        kind="no-mechanism", child_setup=False,
        reason="this host has no way to bound a child").refuse(ChildLimits())
    assert no_setup is not None, (
        "a host that cannot bound any child must refuse even a dispatch that"
        " declared no bound; that is the case the old bounds-only check"
        " short-circuited to \"\"")
    assert no_setup.kind == "child-setup-unavailable"

    beyond_reach = _refusal_as_if("posix", ChildLimits(cpu_seconds=500))
    assert beyond_reach is not None
    assert beyond_reach.kind == "child-limit-unavailable"

    # Windows bounds through a Job Object, which has no inherited hard ceiling,
    # so the number a POSIX host cannot reach is not refused there.
    assert _refusal_as_if("nt", ChildLimits(cpu_seconds=500)) is None


def test_nothing_requested_is_nothing_to_refuse(monkeypatch):
    monkeypatch.setitem(sys.modules, "resource", _RecordingResource(hard_cpu=1))
    assert _supported_as_if("posix", ChildLimits()) == ""


def test_the_memory_bound_is_checked_against_its_own_hard_limit(monkeypatch):
    """The two bounds are checked independently, not as one verdict."""
    monkeypatch.setitem(
        sys.modules, "resource",
        _RecordingResource(hard_cpu=_RecordingResource.RLIM_INFINITY, hard_as=4096))
    reason = _supported_as_if("posix", ChildLimits(cpu_seconds=5, memory_bytes=8192))
    assert "memory_bytes" in reason
    assert "cpu_seconds=5" not in reason, (
        f"the reachable CPU bound was reported as unreachable: {reason!r}")


def test_exec_profile_child_session_delegates_to_child_limits(monkeypatch):
    seen = []
    monkeypatch.setattr(child_limits, "apply_child_limits", seen.append)
    monkeypatch.setattr(os, "setsid", lambda: None, raising=False)
    from settlement import exec_profile

    exec_profile._child_session(11, 4096)
    assert seen == [ChildLimits(cpu_seconds=11, memory_bytes=4096)]


def test_exec_profile_passes_the_caller_cpu_and_memory_bounds(monkeypatch):
    seen = []
    monkeypatch.setattr(child_limits, "apply_child_limits", seen.append)
    monkeypatch.setattr(os, "setsid", lambda: None, raising=False)
    from settlement import exec_profile

    exec_profile._child_session(cpu_seconds=9, memory_bytes=None)
    assert seen == [ChildLimits(cpu_seconds=9, memory_bytes=None)]


@pytest.mark.skipif(POSIX, reason="the unsupported-platform branch needs a Windows host")
def test_windows_refuses_a_cpu_bound_with_the_exact_typed_condition():
    with pytest.raises(UnsupportedChildLimit) as caught:
        apply_child_limits(ChildLimits(cpu_seconds=5))
    assert "cpu_seconds" in str(caught.value)
    assert caught.value.code is ResultCode.INCOMPATIBLE_VERSION


@pytest.mark.skipif(POSIX, reason="the unsupported-platform branch needs a Windows host")
def test_windows_refuses_rather_than_returning_silently():
    for limits in (ChildLimits(memory_bytes=4096),
                   ChildLimits(cpu_seconds=5, memory_bytes=4096)):
        with pytest.raises(UnsupportedChildLimit):
            apply_child_limits(limits)


@pytest.mark.skipif(POSIX, reason="the refusal must surface at the exec_profile entry point")
def test_exec_profile_child_session_refuses_on_windows_instead_of_pretending(monkeypatch):
    """The real user entry point, not a direct call to the module."""
    from settlement import exec_profile

    with pytest.raises(UnsupportedChildLimit):
        exec_profile._child_session(cpu_seconds=5, memory_bytes=4096)


def test_output_lock_is_held_against_a_second_process(tmp_path):
    """The bound this host genuinely enforces: cross-process mutual exclusion.

    Proves the `fcntl` fix preserved the lock rather than deleting it, and
    that the Windows branch blocks a competing process for real.
    """
    from scripts import invl02_live

    probe = (
        "import sys, msvcrt\n"
        f"f = open({str(tmp_path / '.output-run.lock')!r}, 'a+')\n"
        "try:\n"
        "    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)\n"
        "except OSError:\n"
        "    print('HELD'); sys.exit(0)\n"
        "print('FREE')\n"
    )
    if POSIX:
        probe = probe.replace("import sys, msvcrt", "import sys, fcntl").replace(
            "msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)",
            "fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)")

    def _probe() -> str:
        return subprocess.run([sys.executable, "-c", probe], capture_output=True,
                              text=True, timeout=60).stdout.strip()

    assert _probe() == "FREE", "nothing held the lock yet"
    lock = invl02_live._output_lock(tmp_path)
    try:
        assert _probe() == "HELD", "a second process took a held lock"
    finally:
        lock.close()
    assert _probe() == "FREE", "closing the lock did not release it"
