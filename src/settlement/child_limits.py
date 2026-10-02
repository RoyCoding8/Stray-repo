"""One source of truth for how a child process is bounded.

Each execution path used to decide for itself whether it could bound a child.
A path that found no `resource` module crashed at import time, and a path that
swallowed the import error ran the child with no bound at all. This module is
the single place that decides which bounds the running platform can enforce,
so no caller repeats the question and no caller can quietly answer "none".

`current_execution_host` states this host's capability once, and everything
else here answers from it. There is no second platform predicate anywhere in
the package, because two predicates is how the POSIX arm came to be a
constant: the copy in `launcher_local` said every POSIX host could enforce
every bound, while the copy here enforced them properly. The two agreed until
they did not.

Measured on this repository's hosts:

- POSIX enforces `RLIMIT_CPU` and `RLIMIT_AS` through `resource.setrlimit`,
  applied in the child between fork and exec. It enforces them only as far as
  the host's *hard* limits allow. Those limits are inherited by every child and
  an unprivileged process cannot raise them, so a declared bound above the hard
  limit is one this host cannot install.
- Windows enforces neither. `preexec_fn` is refused outright by CPython, so a
  child cannot limit itself before it execs. `JOB_OBJECT_LIMIT_JOB_TIME` is
  accepted by `SetInformationJobObject` and then ignored, so a Job Object buys
  no CPU time bound, and `JOB_OBJECT_LIMIT_JOB_MEMORY` only attaches after
  spawn, leaving the child an unbounded window to allocate.

A bound that cannot be enforced raises `UnsupportedChildLimit`. It never
degrades into an unbounded child and it is never a silent no-op. Wall-clock
and output bounds need no platform support and stay enforced everywhere; the
caller applies them in `exec_profile.run_local_process`.

## Two refusals, kept apart

There are two ways to be unable to run a child, and a caller has to tell them
apart because they are answered by different people. A host that cannot run a
child setup at all needs a different machine. A host that can run one but
cannot install the bound you declared needs a smaller number.

- `child-setup-unavailable` is about the host. It fires whatever you asked
  for, including nothing at all, because `preexec_fn` is refused before the
  question of which bound reaches how far.
- `child-limit-unavailable` is about the request. It fires only on a host that
  can bound a child, and it names the specific declared values the host's
  inherited hard limits cannot reach.

Collapsing them into one string loses the distinction, which is why the answer
is a typed `ChildSetupRefusal` and not a bare `str`. A caller that only reads
text cannot tell "go and find a Linux host" from "declare 300 seconds
instead", and the second one is a number the caller already chose.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .common import ResultCode, SettlementError


class UnsupportedChildLimit(SettlementError):
    """A requested child bound has no enforcement mechanism on this platform."""

    code = ResultCode.INCOMPATIBLE_VERSION


@dataclass(frozen=True)
class ChildLimits:
    """The bounds a caller requires on a child."""

    cpu_seconds: int | None = None
    memory_bytes: int | None = None

    def names(self) -> tuple[str, ...]:
        return tuple(name for name in ("cpu_seconds", "memory_bytes")
                     if getattr(self, name) is not None)


@dataclass(frozen=True)
class ChildSetupRefusal:
    """Why a child cannot be run as asked, and which kind of cannot that is.

    `kind` is the caller's dispatch. It is part of the value rather than a
    prefix on `reason` so that a reader can branch on it without matching text,
    and so the two refusals cannot be told apart by accident when only one of
    them happens to mention a platform.
    """

    kind: str
    reason: str


@dataclass(frozen=True)
class ExecutionHost:
    """The host a child would run on, and what that host can enforce.

    `kind` is the attribution a receipt carries, so a result names the process
    that produced it rather than only naming a profile. `child_setup` is the
    capability: installing any boundary needs `preexec_fn`, to run code in the
    child between fork and exec, and CPython refuses that call on Windows. So a
    host without it cannot run a bounded child at all, which is a stronger
    statement than a request-specific one and is the whole D2 fix: a dispatch
    that declares no bound still cannot run here, because the launcher would
    have to hand `preexec_fn` to `Popen` and `Popen` refuses it.

    `reason` says why the capability is absent, so the refusal can carry the
    host's own reason rather than a caller's guess at it.
    """

    kind: str
    child_setup: bool
    reason: str = ""

    def refuse(self, limits: ChildLimits) -> ChildSetupRefusal | None:
        """Why `limits` cannot be installed here, or None when they can.

        Answers both refusals, in the order a caller meets them. The capability
        comes first because it does not depend on the request: there is no
        bound that makes a `preexec_fn` work on a host that refuses it. The
        hard-limit reach comes second because it is the only question left once
        the host can bound a child at all.
        """
        if not self.child_setup:
            return ChildSetupRefusal("child-setup-unavailable", self.reason)
        return _beyond_hard_limits(limits)


def current_execution_host() -> ExecutionHost:
    """The host this process is running on, measured rather than configured.

    The one platform predicate in the package. It is a measurement rather
    than a configuration because a host that misreported its own capability
    would be indistinguishable from one that has it, and the difference shows
    up as an unbounded child.
    """
    if os.name == "nt":
        return ExecutionHost(
            kind="windows", child_setup=False,
            reason=("CPython refuses preexec_fn on Windows, so the child cannot"
                    " limit itself before exec, and this launcher installs every"
                    " boundary it has through it"))
    return ExecutionHost(kind="posix", child_setup=True)


def require_execution_host(expected: str | None) -> ExecutionHost:
    """The running host, refused unless it is the one the caller named.

    `expected` is the caller's demand, not a hint. There is no fallback branch
    here and none is wanted: a run that silently continued on a different host
    than the one it asked for would produce results that name neither, and
    every measurement taken from them afterwards would be unattributable.
    Refusing leaves the choice with the person who has to make it.

    `None` asks the question without demanding an answer, which is what a
    caller that only wants the host's name for a receipt wants.
    """
    host = current_execution_host()
    if expected is not None and host.kind != expected:
        raise UnsupportedChildLimit(
            f"execution host {host.kind!r} was required to be {expected!r}:"
            " this run did not fall back to another host, because a result that"
            " cannot name the host that produced it is not a measurement."
            + (f" This host: {host.reason}" if host.reason else ""))
    return host


def child_setup_refusal(limits: ChildLimits) -> ChildSetupRefusal | None:
    """Why a child cannot be run with `limits` here, or None when it can.

    A question, not an act. `apply_child_limits` both decides and enforces, so
    calling it to ask would lower THIS launcher's own `RLIMIT_AS` for every
    later dispatch: a `setrlimit` in the parent is permanent rather than scoped
    to a child. Measured, not inferred. A launcher that checked a 512MB bound
    reported that limit for its own next child, and could not raise it again.

    So the answer is computed from what the host already reports. Reading an
    rlimit is not installing one: `getrlimit` has no effect on this process or
    any other, so asking costs the caller nothing. That is what lets the
    question be asked in the parent at all.
    """
    return current_execution_host().refuse(limits)


def _beyond_hard_limits(limits: ChildLimits) -> ChildSetupRefusal | None:
    """The declared bounds this host's inherited hard limits cannot reach.

    `RLIMIT_CPU` and `RLIMIT_AS` are inherited by every child, and an
    unprivileged process cannot raise a hard limit it was given. So a hard CPU
    limit below the declared `cpu_seconds` is a ceiling the campaign would be
    budgeting against that is not the ceiling in force. That is the same class
    of error the refusal exists to prevent, and one that cannot be caught
    after the fact, because by then the child has run.

    Only the hard limit is consulted. A soft limit below the declared bound is
    not a defect: the child inherits it and `apply_child_limits` lowers its own
    soft limit to the declared value, which is what installing a bound means.
    Only the hard limit is a promise the host cannot keep, and a bound at or
    above it would fail to install in the child.
    """
    unreachable: list[str] = []
    for name, which in (("cpu_seconds", "RLIMIT_CPU"),
                        ("memory_bytes", "RLIMIT_AS")):
        requested = getattr(limits, name)
        if requested is None:
            continue
        import resource
        _soft, hard = resource.getrlimit(getattr(resource, which))
        if hard != resource.RLIM_INFINITY and requested > hard:
            unreachable.append(f"{name}={requested}")
    if not unreachable:
        return None
    return ChildSetupRefusal("child-limit-unavailable", (
        f"child limit(s) {', '.join(unreachable)} exceed this host's hard"
        " rlimit, which every child inherits and an unprivileged launcher"
        " cannot raise. A declared ceiling the host cannot install is not the"
        " ceiling in force. Run on a host that can install it, or declare a"
        " bound within reach. The child was NOT run unbounded."))


def apply_child_limits(limits: ChildLimits) -> None:
    """Enforce `limits` in the child, between fork and exec.

    Used as `preexec_fn`. Raises `UnsupportedChildLimit` rather than letting a
    child run unbounded on a platform that cannot apply the bounds. It raises
    even for an empty `ChildLimits` on a host without `preexec_fn`, because
    this runs inside a `preexec_fn` and such a host never got this far.

    The refusal names the bounds so a caller can see which of its declarations
    the host could not honour, and says "no bound requested" when there were
    none, so a host refusal is not mistaken for one about a ceiling.
    """
    refusal = child_setup_refusal(limits)
    if refusal is not None:
        raise UnsupportedChildLimit(
            "%s: %s" % (", ".join(limits.names()) or "no bound requested",
                        refusal.reason))
    import resource

    if limits.cpu_seconds is not None:
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
    if limits.memory_bytes is not None:
        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
