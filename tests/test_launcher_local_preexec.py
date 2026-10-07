"""A `preexec_fn` failure is contained: it cannot escape, and it cannot strand.

`dispatch` built its child setup unconditionally and caught `(OSError,
MemoryError)` around `Popen`. Neither half held. A `preexec_fn` runs in the
forked child, and CPython reports its failure to the parent as
`subprocess.SubprocessError` -- whose MRO is not `OSError` -- while discarding
the child's real exception, message and errno. So the declared-bound failure the
comment was written for escaped `dispatch` instead of becoming a receipt, and
the pid claim written before the spawn was never unwound: the next dispatch of
the same operation read its own claim back as `prior-send-recorded` and the
operation was stranded for work that never ran.

The platform is not incidental. CPython refuses `preexec_fn` on Windows with
`ValueError`, which the same tuple missed, so on that host the *unlimited*
dispatch escaped and the *limited* one was already refused by
`child_limits_unsupported_reason`. The guard was aimed at the wrong case.

Each test below calls `LocalLauncher.dispatch` the way a campaign calls it, and
asserts the two things that must hold together: nothing escapes, and a dispatch
that made no worker leaves nothing behind that reads as one.
"""

from __future__ import annotations

import os
import sys

import pytest

from settlement import child_limits
from settlement import launcher_local
from settlement.broker import BrokerOp
from settlement.child_limits import ChildLimits
from settlement.launcher_local import LocalLauncher

POSIX = os.name != "nt"
WINDOWS = os.name == "nt"


def _op(operation_id, argv, payload_extra=None, generation=1, execution_version="v1"):
    payload = {"argv": argv, "timeout_ms": 10_000}
    payload.update(payload_extra or {})
    return BrokerOp(operation_id=operation_id, effect="exec",
                    execution_version=execution_version,
                    dispatch_generation=generation, payload=payload)


def _markers(run_dir, operation_id):
    """Every marker a dispatch could leave, named the way `prior_send` finds them."""
    return sorted(p.name for p in run_dir.glob(f"{operation_id}_*")
                  if p.is_file() and not p.name.endswith(".work"))


def _assert_stranded_free(launcher, run_dir, operation_id, why):
    assert launcher.prior_send(operation_id) is False, (
        f"{why}: prior_send reports a send, so every retry is now refused")
    assert launcher.prove_never_sent(operation_id, 1) is True, (
        f"{why}: the operation can no longer be proved never sent")
    assert _markers(run_dir, operation_id) == [], (
        f"{why}: markers left behind: {_markers(run_dir, operation_id)}")


# -- (a) the platform case, on whichever host this is --------------------------


def test_an_unlimited_dispatch_on_this_platform_never_raises(tmp_path):
    """Whatever `preexec_fn` does here, `dispatch` must not let it escape.

    On Windows this is the defect: nothing is declared, so
    `child_limits_unsupported_reason` returns "", `Popen` is handed a
    `preexec_fn`, and CPython raises `ValueError: preexec_fn is not supported
    on Windows platforms` out of a call that had already written its pid claim.
    On POSIX the same call must keep working, so the assertion is that the call
    returns a `LaunchOutcome` rather than raising, on either platform.
    """
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(_op("op-plain", [sys.executable, "-c", "print(1)"]))
    assert isinstance(outcome.sent, bool), f"dispatch returned {outcome!r}"


@pytest.mark.skipif(not WINDOWS, reason="this host accepts preexec_fn")
def test_a_windows_dispatch_declares_no_bounds_is_refused_not_raised(tmp_path):
    """The unlimited case is the one Windows gets wrong, and it is the one fixed.

    Refusing pre-spawn is the honest outcome: a dispatch this platform cannot
    carry has no worker, so it must be re-admissible rather than stranding the
    operation behind markers of a spawn that never happened.
    """
    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(_op("op-win-plain", [sys.executable, "-c", "print(1)"]))
    assert outcome.sent is False
    assert outcome.refused_reason, "a refusal must say why"
    _assert_stranded_free(launcher, tmp_path / "run", "op-win-plain",
                          "a refused pre-spawn")


# -- (b) a preexec_fn that fails, on the host where that is reachable ----------


@pytest.mark.skipif(not POSIX, reason="a preexec_fn failure needs a POSIX fork")
def test_a_preexec_failure_is_reported_not_raised(tmp_path, monkeypatch):
    """The exact shape the old comment was written for, driven for real.

    `setrlimit(RLIMIT_CPU, (500, 500))` on a host whose hard limit is 3 raises
    `ValueError` inside the forked child. CPython relays that to the parent as
    `SubprocessError`, so before the fix the exception left `dispatch` with the
    pid claim still on disk and no receipt at all.
    """
    import resource

    hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
    if hard == resource.RLIM_INFINITY:
        pytest.skip("this host has no hard RLIMIT_CPU to exceed")

    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(
        _op("op-preexec", [sys.executable, "-c", "print(1)"],
            {"cpu_seconds": int(hard) + 500}))

    assert outcome.sent is False, (
        "a child that never exec'd made no send; claiming otherwise is the"
        " stranding the unwind exists to prevent")
    _assert_stranded_free(launcher, tmp_path / "run", "op-preexec",
                          "a preexec_fn that failed")


@pytest.mark.skipif(not POSIX, reason="a preexec_fn failure needs a POSIX fork")
def test_a_preexec_failure_says_which_boundary_stopped_the_child(tmp_path):
    """A refusal the caller can act on names the boundary and the fact.

    `SubprocessError: Exception occurred in preexec_fn.` on its own tells an
    operator nothing: the child's real exception, message and errno are
    discarded by CPython before the parent sees them. The receipt has to carry
    the dispatch's own answer instead, or a genuine platform fault is
    indistinguishable from a declared bound the host could not install.
    """
    import resource

    hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
    if hard == resource.RLIM_INFINITY:
        pytest.skip("this host has no hard RLIMIT_CPU to exceed")

    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(
        _op("op-preexec-said", [sys.executable, "-c", "print(1)"],
            {"cpu_seconds": int(hard) + 500}))

    assert outcome.sent is False
    reason = outcome.refused_reason or ""
    assert "cpu_seconds" in reason, (
        f"the refusal does not name the bound that stopped the child: {reason!r}")
    assert reason != "claim-not-durable", (
        "the ledger refused the claim; that is a different defect and this"
        " test is not about it")


# -- (c) the escape path a hostile preexec_fn would use ------------------------


@pytest.mark.skipif(not POSIX, reason="a preexec_fn only runs on a POSIX fork")
def test_a_preexec_fn_that_raises_does_not_reach_the_caller(tmp_path, monkeypatch):
    """Whatever the child raises, `dispatch` returns an outcome rather than raising.

    The type the parent sees for a `preexec_fn` failure is CPython's to choose,
    so the assertion is on containment, not on an exception class. A `Popen`
    whose own `preexec_fn` raises `OSError` is the same shape as the declared
    bound that raises `ValueError`, and both arrive as `SubprocessError`.
    """
    launcher = LocalLauncher(tmp_path / "run")

    def raising_setup(payload):
        def _setup() -> None:
            raise OSError("deliberate preexec failure")
        return _setup

    monkeypatch.setattr("settlement.launcher_local._child_setup", raising_setup)

    outcome = launcher.dispatch(_op("op-oserror", [sys.executable, "-c", "print(1)"]))
    assert isinstance(outcome.sent, bool), f"dispatch returned {outcome!r}"
    if not outcome.sent:
        _assert_stranded_free(launcher, tmp_path / "run", "op-oserror",
                              "a preexec_fn that raised")


# -- (c) the read_deny escape the same fix has to absorb -----------------------
#
# Confined read denial is a documented NOT PROVEN limit on WSL2, and this does
# not change that: the parent's `probe_landlock()` passes at ABI 7 while the
# child's `_landlock_restrict` fails with EINVAL. What matters here is only the
# launcher's response to a `preexec_fn` that raised, which is the same shape as
# the D1 case and must be answered the same way.


@pytest.mark.skipif(not POSIX, reason="a preexec_fn only runs on a POSIX fork")
def test_a_confinement_that_fails_to_install_is_contained_like_any_other(
        tmp_path, monkeypatch):
    """The read_deny escape path leaves no marker and no exception behind.

    The Landlock behaviour itself is not under test and is not fixed here. This
    is the claim that a child which failed to confine itself is reported as a
    dispatch that made no worker, rather than escaping `dispatch` with the pid
    claim it had already written.
    """
    launcher = LocalLauncher(tmp_path / "run")

    def failing_setup(payload):
        def _setup() -> None:
            # What the WSL2 child does: the kernel refuses the ruleset.
            raise OSError(22, "Invalid argument")
        return _setup

    monkeypatch.setattr("settlement.launcher_local._child_setup", failing_setup)

    # The read_deny refusal consults `landlock_available()`, and
    # `_no_new_privs_settable` answers that by SETTING PR_SET_NO_NEW_PRIVS on
    # this process. The flag is irreversible and any later assertion that it is
    # clear would be reading this test's own side effect, so it is stubbed to
    # the answer a capable host gives without touching the real one.
    monkeypatch.setattr(launcher_local, "_no_new_privs_settable", lambda: True)
    monkeypatch.setattr(launcher_local, "landlock_available", lambda: True)

    outcome = launcher.dispatch(
        _op("op-landlock", [sys.executable, "-c", "print(1)"],
            {"read_deny": [str(tmp_path)]}))
    assert isinstance(outcome.sent, bool), f"dispatch returned {outcome!r}"
    if not outcome.sent:
        _assert_stranded_free(launcher, tmp_path / "run", "op-landlock",
                              "a child that could not confine itself")


# -- (d) what must NOT change --------------------------------------------------

def test_a_refusal_is_still_re_admissible_on_a_platform_that_raises(tmp_path):
    """Retrying a refused dispatch must retry the dispatch, not the refusal.

    This is the property the stranding broke, stated independently of which
    host is running: after any refusal, the operation is still dispatchable and
    still provably never sent.
    """
    launcher = LocalLauncher(tmp_path / "run")
    op = _op("op-retry", [sys.executable, "-c", "print(1)"])

    first = launcher.dispatch(op)
    second = launcher.dispatch(op)

    if first.sent:
        pytest.skip("this host ran the dispatch; there was no refusal to retry")
    assert second.refused_reason == first.refused_reason, (
        f"a retry answered differently: {first.refused_reason!r} then "
        f"{second.refused_reason!r}")
    _assert_stranded_free(launcher, tmp_path / "run", "op-retry", "a retried refusal")


def test_a_platform_that_refuses_preexec_still_enforces_its_declared_bounds(tmp_path):
    """The refusal must not become a way to skip a bound.

    A host that cannot install `cpu_seconds` refuses. A host that cannot install
    `memory_bytes` refuses. Neither may pass the child through unbounded, and
    neither may report success for a child that ran with no ceiling.
    """
    launcher = LocalLauncher(tmp_path / "run")
    for name, payload in (("cpu_seconds", {"cpu_seconds": 2}),
                          ("memory_bytes", {"memory_bytes": 512 * 1024 * 1024})):
        op = _op(f"op-bound-{name}", [sys.executable, "-c", "print(1)"], payload)
        outcome = launcher.dispatch(op)
        if outcome.sent:
            assert outcome.receipt.outcome in ("success", "failure")
        elif sys.platform == "darwin" and name == "memory_bytes":
            assert outcome.refused_reason.startswith("child-setup-failed:"), (
                "Darwin's RLIMIT_AS setup refusal must remain a refusal: "
                f"{outcome.refused_reason!r}")
        else:
            assert name in outcome.refused_reason, (
                f"refusing {name} must name it, not something else: "
                f"{outcome.refused_reason!r}")


@pytest.mark.skipif(not POSIX, reason="RLIMIT_CPU is a POSIX enforcement mechanism")
def test_a_bound_above_this_hosts_hard_limit_is_refused_before_the_spawn(tmp_path):
    """A ceiling the host cannot install must be refused pre-spawn (D3).

    `RLIMIT_CPU`'s hard limit is inherited and cannot be raised by an
    unprivileged process, so declaring `cpu_seconds` above it is a promise the
    host cannot keep. Before the fix the platform arm returned "" for every
    POSIX host, the check passed, and the failure surfaced as the escaped
    `SubprocessError` of case (b) -- after the markers were already written.
    """
    import resource

    hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
    if hard == resource.RLIM_INFINITY:
        pytest.skip("this host imposes no hard RLIMIT_CPU, so there is nothing to exceed")

    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(
        _op("op-hard-cap", [sys.executable, "-c", "print(1)"],
            {"cpu_seconds": int(hard) + 500}))

    assert outcome.sent is False
    assert outcome.refused_reason.startswith("child-limit-unavailable:"), (
        "a bound above the host's hard limit is a host that CAN bound a child"
        " and cannot install this one, and must be refused as its own kind so a"
        " caller can tell it from a host that cannot run a child setup at all;"
        f" got {outcome.refused_reason!r}")
    _assert_stranded_free(launcher, tmp_path / "run", "op-hard-cap",
                          "a refused uninstallable bound")


@pytest.mark.skipif(not POSIX, reason="RLIMIT_CPU is a POSIX enforcement mechanism")
def test_a_bound_within_this_hosts_reach_is_not_refused(tmp_path):
    """The other direction, so the refusal cannot be a blanket refusal.

    A ceiling this host can install must dispatch, or the check is not
    answering whether the host can honour the bound.
    """
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
    reach = hard if hard != resource.RLIM_INFINITY else 5
    if reach == resource.RLIM_INFINITY or reach < 1:
        pytest.skip("this host has no usable CPU bound to declare")
    if soft != resource.RLIM_INFINITY and soft < reach:
        pytest.skip("the soft limit is below the value under test")

    launcher = LocalLauncher(tmp_path / "run")
    outcome = launcher.dispatch(
        _op("op-reachable", [sys.executable, "-c", "print(1)"],
            {"cpu_seconds": int(reach)}))
    assert outcome.sent is True, (
        f"a bound this host can install was refused: {outcome.refused_reason!r}")


def test_the_platform_question_is_asked_in_exactly_one_place():
    """The POSIX arm must answer from this host, not return "" for all of them.

    Two predicates is how the two branches of this file came to disagree: the
    copy in `launcher_local` said every POSIX host could enforce every bound,
    while the copy in `child_limits` enforced them properly. So the launcher's
    copy is deleted and the authority answers for the whole package.
    """
    import pathlib
    import settlement

    package = pathlib.Path(settlement.__file__).parent
    predicates = [p.name for p in package.glob("*.py")
                  if "os.name ==" in p.read_text(encoding="utf-8")]
    assert predicates == ["child_limits.py"], (
        "the platform decision is answered in %s; exactly one module may own it"
        % (predicates or "no module at all"))

    assert not hasattr(launcher_local, "child_limits_unsupported_reason"), (
        "the launcher answers the question itself again, which is the "
        "duplication that left the POSIX arm a constant")

    # The kind follows the host, and a host that cannot run a child setup
    # refuses every request for the same reason rather than only the bounded
    # ones. That is the D2 half: the empty request refuses here too.
    host = child_limits.current_execution_host()
    refusal = child_limits.child_setup_refusal(ChildLimits(cpu_seconds=1))
    assert (refusal is None) is host.child_setup, (
        f"the host says it can bound a child ({host.child_setup}) but answered"
        f" {refusal!r} for a request it declares, so the two disagree")
    if not host.child_setup:
        assert refusal.kind == "child-setup-unavailable"
        assert child_limits.child_setup_refusal(ChildLimits()).kind == (
            "child-setup-unavailable"), (
            "a dispatch that declared no bound escaped the guard; that is the"
            " case the bounds-only check short-circuited")
