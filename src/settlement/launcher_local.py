"""Local-process launcher: bounded subprocess execution for diagnosis and tests.

Identity is derived from the operation, never fresh randomness: recovery
inspects the run directory (pid and result files) before any new spawn.
Every result is labeled containment=False. Worker bytes are parsed as typed
JSON only, never executed. Stops use process-group kill. Children run with a scrubbed environment and
never inherit the controller working directory: payload `cwd` selects an
existing isolated directory, otherwise the operation work directory, which
keeps run state (pid, result, generation files) out of the worker's listing.
A detached deadline supervisor outlives the dispatching process and kills
the worker group past its admitted bound; it signals only a starttime-verified
process group. This profile is still explicitly not containment: use gvisor
where the threat model needs it.

What "not containment" was hiding (N-36). A policy here can read any file the
controller could, and the study worlds keep their task-id key in the
repository, so a policy could read the key and invert the published id to the
seed. Measured, not hypothesised: the seed is the recipe, so this yields the
answer outright rather than a key that is then subject to further checks. The
environment scrub protected the seed; it never protected the source.

`read_deny` on a dispatch payload is the boundary, and it is real rather than
documentary. A declared deny list installs a Landlock ruleset in the child
between fork and exec, so a denied path is unreadable to the child even though
the same bytes are readable by the controller. The ruleset is built before
`Popen` returns rather than after the child proves itself well behaved, and a
dispatch that asks for confinement the kernel cannot provide is refused rather
than run unbounded. `probe_landlock` measures that capability by reading
`no_new_privs` back instead of trusting the return code: a silently dropped
prctl would otherwise let a dispatch record a boundary that was never applied.
`prctl` takes the option as its first argument, and `PR_SET_NO_NEW_PRIVS` is 38
while 1 is `PR_SET_PDEATHSIG`; the read-back only proves the flag if the set and
the get name the same one.

A declared `cpu_seconds` or `memory_bytes` is the same kind of boundary and
gets the same treatment. The values are read out of the payload into a
`ChildLimits`, and `settlement.child_limits` is asked up front whether it can
install them; a host that cannot is refused pre-spawn with the same unwind the
read denial uses. That includes a POSIX host whose hard rlimit sits below the
declared bound, which the platform test alone could not see. `child_limits` is
the only function that enforces anything, and it runs where enforcement belongs:
in the child, between fork and exec. The refusal is a question, so it asks
without installing a limit of its own -- a `setrlimit` in this process would be
permanent rather than scoped to a child, and a launcher that asked its question
that way would carry the first dispatch's ceiling into every later one. Reading
an rlimit is not installing one, which is what lets the question be asked in the
parent at all.

Every child boundary here is installed through `preexec_fn`, so a host that
refuses `preexec_fn` cannot run this profile at all, declared bounds or not, and
says so before the spawn rather than by raising out of it. That is why the
refusal above asks one question rather than two. It used to ask one about the
declared bounds and one about the platform, each with its own `os.name` test.
The bounds one short-circuited to "" when the payload declared nothing, so the
unlimited dispatch was the unguarded one, and the platform one was a second copy
of the decision `child_limits` already owns. `current_execution_host` states
the capability once and `child_setup_refusal` answers both failures from it, as
a typed refusal whose `kind` tells the caller which one it is: a host that
cannot run a child at all is a different machine, and a host that cannot
install the ceiling you declared is a smaller number. No path here re-derives
the platform.

A receipt says which host produced it, because `profile` was the same string on
every host this file has run on and two hosts' receipts compared as one
measurement. `host` is read per receipt from `current_execution_host`, and a
caller that needs a particular host says so with `require_host`, which is
refused rather than substituted.

A `preexec_fn` that fails after that point is the same shape: CPython replaces
the child's real exception with a fixed `SubprocessError` and hands it to the
parent, so the failure is caught where it is contained, unwound through the
same path as every other refusal, and reported as a send that provably did not
happen rather than as a receipt for work that never ran.

The ruleset confines the filesystem. It is not gVisor, and receipts still say
containment=False: this profile remains a bounded subprocess, now carrying one
real boundary instead of a promise of one.

The run directory is a worker's own work tree, so erasing it is a write the
worker can already do. Every proof of a send therefore lives twice: as markers
in the run directory, and as claims in a launcher-held ledger keyed to the
operation and its dispatch generation and kept outside it. The ledger is not
unreachable by the worker; nothing here is. What it buys is that no dispatch
it performs erases the record of that dispatch.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import attestation
from . import child_limits
from .broker import BrokerOp, LaunchOutcome, ReceiptProposal
from .child_limits import ChildLimits
from .exec_profile import proc_starttime, reap_supervisor, scrub_env, spawn_deadline_supervisor

PROFILE = "local-process"

ATTEST_KEY_BYTES = 32
_NEVER_SENT_SUFFIXES = (".pid", ".result.json", ".spawns", ".gen", ".supervise.json")
CLAIM_LEDGER_ENV = "SETTLEMENT_CLAIM_LEDGER"

# Landlock syscall numbers and the filesystem access rights this profile can
# withhold. The kernel ABI is queried at runtime rather than assumed, because a
# boundary that silently degrades on an older kernel is the defect N-36 names.
_LANDLOCK_CREATE_RULESET = 444
_LANDLOCK_ADD_RULE = 445
_LANDLOCK_RESTRICT_SELF = 444
_LANDLOCK_RULE_PATH_BENEATH = 1
_LANDLOCK_CREATE_RULESET_VERSION = 1 << 0
# prctl(1) is PR_SET_PDEATHSIG and prctl(38) is PR_SET_NO_NEW_PRIVS. Setting the
# first while meaning the second reports success and leaves the flag clear, which
# is the read-back in `_no_new_privs_settable` built to catch.
_PR_SET_NO_NEW_PRIVS = 38
_PR_GET_NO_NEW_PRIVS = 39
_LANDLOCK_FS_ACCESS = (
    (1 << 0)    # EXECUTE
    | (1 << 1)  # WRITE_FILE
    | (1 << 2)  # READ_FILE
    | (1 << 3)  # READ_DIR
    | (1 << 4)  # REMOVE_DIR
    | (1 << 5)  # REMOVE_FILE
    | (1 << 8)  # MAKE_DIR
    | (1 << 9)  # MAKE_REG
    | (1 << 13)  # REFER
)


@dataclass(frozen=True)
class LandlockProbe:
    """What the running kernel can actually enforce, measured not assumed."""

    name: str
    available: bool
    reason: str
    abi_version: int


def _landlock_abi() -> tuple[int, str]:
    import ctypes

    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        abi = int(libc.syscall(ctypes.c_long(_LANDLOCK_CREATE_RULESET),
                               ctypes.c_void_p(0), ctypes.c_size_t(0),
                               ctypes.c_ulong(_LANDLOCK_CREATE_RULESET_VERSION)))
    except (OSError, AttributeError, ValueError) as exc:
        return 0, "landlock unavailable: %s" % (exc,)
    return abi, ""


def _no_new_privs_settable() -> bool:
    """Whether THIS process can set the flag Landlock requires.

    Landlock refuses to restrict a process that could regain privilege, so
    `PR_SET_NO_NEW_PRIVS` is a precondition rather than a detail. It is asked
    by reading the flag back, because a call that reports success without
    setting it is worse than a call that fails: it would let a dispatch
    record confinement that was never applied.
    """
    import ctypes

    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            return False
        return int(libc.prctl(_PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0)) == 1
    except (OSError, AttributeError, ValueError):
        return False


def probe_landlock() -> LandlockProbe:
    """Whether this kernel confines a child, and at which ABI.

    Reported rather than assumed because a deployment picks a profile from
    this answer, and because a boundary that silently degrades is the defect
    N-36 names. Three things have to hold, and each is asked separately so
    the reason names the one that failed:

    * the kernel implements the syscall at all (ABI >= 1);
    * the ABI is new enough to express a read denial (>= 2, which added
      READ_FILE -- denying reads is the whole point here);
    * this process can set `no_new_privs`, which Landlock requires.

    The third is measured by reading the flag back rather than trusting the
    return code. On a host where an LSM or container runtime silently drops
    the call, the return value is 0 and the flag stays 0, and a probe that
    believed the return code would report a boundary that does not exist.
    """
    import ctypes  # noqa: F401  (import failure is caught in _landlock_abi)

    abi, reason = _landlock_abi()
    if abi < 1:
        return LandlockProbe(
            "landlock", False,
            reason or "landlock unavailable: the kernel reports ABI 0, so no "
                      "ruleset can be created", abi)
    if abi < 2:
        return LandlockProbe(
            "landlock", False,
            "landlock unavailable: ABI %d predates READ_FILE (needs 2), so a "
            "read denial cannot be expressed" % abi, abi)
    if not _no_new_privs_settable():
        return LandlockProbe(
            "landlock", False,
            "landlock unavailable: this process cannot set no_new_privs, which "
            "Landlock requires before it will restrict. The call reports "
            "success and leaves the flag clear, so confinement would be "
            "recorded without being applied.", abi)
    return LandlockProbe("landlock", True, "landlock ABI %d" % abi, abi)


def landlock_available() -> bool:
    return probe_landlock().available


def _landlock_restrict(allow_read: list[str], deny_read: list[str]) -> None:
    """Confine this process to `allow_read`, minus everything under `deny_read`.

    Runs in the child between fork and exec, so a failure here raises inside
    `preexec_fn` and the child never becomes the operation. That ordering is
    the point: a boundary that could be skipped is not a boundary, so the
    ruleset is installed before `Popen` returns rather than after the child
    proves it is well behaved.

    Landlock is allowlist-shaped. A rule grants rights beneath a path, so
    denying a path means granting nothing that would reach it -- the caller
    passes the roots a child legitimately needs and the ones it must not see,
    and this builds the ruleset that separates them. Denied roots win: they are
    never added to the allowlist in the first place.

    Landlock cannot express "deny this one path while allowing its parent", so
    a denied root is subtracted from every allow root that contains it. If that
    subtraction would empty an allow root, the allow is dropped and the caller
    is left to notice that the child cannot read what it needs -- which is the
    honest outcome, and the test that names it is the census test.
    """
    import ctypes
    import errno as _errno

    probe = probe_landlock()
    if not probe.available:
        raise OSError(_errno.ENOSYS, probe.reason)

    denied = [os.path.realpath(p) for p in deny_read if p]
    if not denied:
        return

    kept: list[str] = []
    for raw in allow_read:
        if not raw:
            continue
        real = os.path.realpath(raw)
        if any(real == d or real.startswith(d + os.sep) for d in denied):
            continue
        kept.append(real)
    # Landlock rejects a rule nested inside another rule that was already
    # added, so a child that needs both /usr and /usr/lib/python3.12 would
    # fail to start. The outer root already grants everything the inner one
    # would, so the inner one is redundant and is dropped.
    kept.sort(key=len)
    minimal: list[str] = []
    for root in kept:
        if any(root == k or root.startswith(k + os.sep) for k in minimal):
            continue
        minimal.append(root)

    class _PathBeneath(ctypes.Structure):
        _fields_ = [("allowed_access", ctypes.c_uint64),
                    ("parent_fd", ctypes.c_int)]

    class _RulesetAttr(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    def _syscall(number, *args):
        converted = [ctypes.c_void_p(a) if isinstance(a, int) else a
                     for a in args]
        return libc.syscall(ctypes.c_long(number), *converted)

    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_NO_NEW_PRIVS) failed")
    attr = _RulesetAttr(handled_access_fs=_LANDLOCK_FS_ACCESS)
    ruleset = _syscall(_LANDLOCK_CREATE_RULESET, ctypes.byref(attr),
                       ctypes.sizeof(attr), 0)
    if ruleset < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset failed")
    for root in minimal:
        fd = os.open(root, os.O_PATH | os.O_CLOEXEC)
        try:
            rule = _PathBeneath(allowed_access=_LANDLOCK_FS_ACCESS,
                                parent_fd=fd)
            # landlock_add_rule(ruleset_fd, rule_type, rule_attr, flags). The
            # rule type is PATH_BENEATH; passing the attribute in its place
            # returns EINVAL and is worth naming, because the failure mode is
            # a child that never starts rather than a denial anyone reads.
            if _syscall(_LANDLOCK_ADD_RULE, ruleset,
                        _LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(rule), 0) < 0:
                raise OSError(ctypes.get_errno(),
                              "landlock_add_rule failed for %s" % root)
        finally:
            os.close(fd)
    # landlock_restrict_self(ruleset_fd, flags). Same syscall number as
    # create_ruleset, which is why it gets its own name here: calling
    # _LANDLOCK_CREATE_RULESET as the syscall number for the *restrict* call
    # happens to be the same value, but passing the create_ruleset flag set
    # here is what returns EINVAL.
    if _syscall(_LANDLOCK_RESTRICT_SELF, ruleset, 0) < 0:
        raise OSError(ctypes.get_errno(), "landlock_restrict_self failed")
    os.close(ruleset)


class WorkerOutput(BaseModel):
    status: str
    data: dict[str, Any] = {}
    error: str = ""

    model_config = {"extra": "forbid"}


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _check_relpath(relpath: str) -> str:
    if (not isinstance(relpath, str) or not relpath or relpath.startswith("/")
            or ".." in relpath.split("/")):
        raise ValueError(f"refusing unsafe artifact relpath {relpath!r}")
    return relpath


def native_id(operation_id: str, execution_version: str) -> str:
    return f"{_sanitize(operation_id)}_{_sanitize(execution_version or 'exec-default')}"


def mint_dispatch_capability(operation_id: str, dispatch_generation: int,
                             secret: bytes) -> str:
    """Bind one dispatch generation to the launcher's per-process secret.

    The store records the operation, its generation and the launcher it was
    admitted to, so a caller holding only the operation row can reproduce every
    one of those. What it cannot reproduce is ``secret``: it is drawn per
    launcher process and never leaves the launcher's memory or the run
    directory. A proof is therefore only spellable by someone who asked the
    launcher, which is what turns the store's provenance check from
    attribution into evidence.
    """
    if not isinstance(secret, bytes) or len(secret) < 16:
        raise ValueError("dispatch capability requires a launcher-held secret")
    material = f"{PROFILE}\0{operation_id}\0{int(dispatch_generation)}".encode()
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


class LocalLauncher:
    launcher_id = "local-1"
    profile = PROFILE
    idempotent_resend = False

    def __init__(self, run_dir: str | Path, grace_ms: int = 2000) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.grace_ms = grace_ms
        self._secret = secrets.token_bytes(ATTEST_KEY_BYTES)
        attestation.register(self.launcher_id, self.verify_capability)

    def native_id(self, operation_id: str, execution_version: str) -> str:
        return native_id(operation_id, execution_version)

    def _paths(self, operation_id: str, execution_version: str) -> dict[str, Path]:
        base = self.run_dir / self.native_id(operation_id, execution_version)
        return {"pid": base.with_suffix(".pid"), "result": base.with_suffix(".result.json"),
                "spawns": base.with_suffix(".spawns"), "generation": base.with_suffix(".gen"),
                "supervise": base.with_suffix(".supervise.json")}

    def _work_dirs(self, operation_id: str,
                   execution_version: str) -> dict[str, Path]:
        work = self.run_dir / f"{self.native_id(operation_id, execution_version)}.work"
        return {"work": work, "inputs": work / "inputs", "outputs": work / "outputs"}

    def stage_input(self, operation_id: str, execution_version: str,
                    relpath: str, data: bytes) -> Path:
        _check_relpath(relpath)
        target = self._work_dirs(operation_id, execution_version)["inputs"]
        target.mkdir(parents=True, exist_ok=True)
        dest = target / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def exec_dirs(self, operation_id: str,
                  execution_version: str) -> tuple[str, str]:
        dirs = self._work_dirs(operation_id, execution_version)
        dirs["inputs"].mkdir(parents=True, exist_ok=True)
        dirs["outputs"].mkdir(parents=True, exist_ok=True)
        return (str(dirs["inputs"]), str(dirs["outputs"]))

    def staged_python(self) -> str:
        return sys.executable

    def read_output(self, operation_id: str, execution_version: str,
                    relpath: str) -> bytes:
        return (self._work_dirs(operation_id, execution_version)["outputs"]
                / _check_relpath(relpath)).read_bytes()

    def _recorded_generation(self, path: Path) -> int | None:
        try:
            return int(path.read_text().strip())
        except (ValueError, OSError):
            return None

    def prior_send(self, operation_id: str) -> bool:
        if any(self.run_dir.glob(f"{_sanitize(operation_id)}_*.pid")):
            return True
        return self.read_result(operation_id) is not None

    # -- the claim ledger -------------------------------------------------
    #
    # A claim records that this launcher started this operation at this
    # dispatch generation, and it outlives the run directory. The location is
    # a process-wide state root because a run directory is worker-writable and
    # so is every sibling of it: production builds the launcher at
    # experiments/ad01/method_exec.py:498 as LocalLauncher(work / "launcher")
    # and runs the worker with cwd under `work`, same uid, containment=False.
    # The worker can reach the ledger. What it cannot do is reach it as a side
    # effect of erasing its own evidence, which is the write this defends
    # against. A claim forged here would strand an operation rather than
    # refund it, so the worst case is a denial the broker already reports as
    # unresolved-liability with the exposure retained.

    def claim_ledger(self) -> Path:
        override = os.environ.get(CLAIM_LEDGER_ENV, "").strip()
        if override:
            return Path(override)
        digest = hashlib.sha256(
            str(self.run_dir.resolve()).encode()).hexdigest()[:32]
        return Path(tempfile.gettempdir()) / "settlement-claims" / f"{digest}.jsonl"

    def _read_claims(self) -> list[dict[str, Any]]:
        """Every claim on disk, or nothing at all if the ledger is unreadable.

        An empty list for a read error would read as "no claim ever existed",
        which is the answer the ledger exists to stop giving.
        """
        ledger = self.claim_ledger()
        try:
            raw = ledger.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise OSError(f"claim ledger unreadable: {ledger}") from exc
        claims = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                claim = json.loads(line)
            except ValueError:
                continue
            if isinstance(claim, dict):
                claims.append(claim)
        return claims

    def _append_claim(self, *, operation_id: str, dispatch_generation: int,
                      execution_version: str, dispatched: bool = True) -> bool:
        """Record one claim, durably, before the worker exists.

        The fsync is the point. A claim that is buffered and lost on a crash is
        a send with no record of it, the state this ledger exists to make
        impossible.

        `dispatched` says whether the spawn that followed this claim reached a
        worker, and it is part of the same durable line rather than a separate
        record. The claim has to be written *before* the spawn -- a send with no
        record of it is the one state nothing may produce -- which means a claim
        that is then unwound would otherwise be indistinguishable from a claim
        that was honoured. Two lines would fix that by duplicating the key, so
        the outcome rides on the claim itself: a line saying `dispatched: false`
        is a claim that was made and then taken back, and `claimed` reports it
        as no claim at all. Appending the outcome later and rewriting the line
        would not survive a crash between the two writes, which is exactly the
        window this ledger exists to cover.

        It defaults to True, which is the claim about a send that did happen.
        A caller that has not yet learned the outcome writes the optimistic
        answer, because a ledger that under-reports a send is the one failure
        this file exists to make impossible.
        """
        ledger = self.claim_ledger()
        try:
            ledger.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps({
                "launcher_id": self.launcher_id,
                "operation_id": operation_id,
                "dispatch_generation": int(dispatch_generation),
                "execution_version": execution_version,
                "claimed_epoch": time.time(),
                "dispatched": bool(dispatched),
            }, sort_keys=True) + "\n"
            fd = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                os.write(fd, line.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            return False
        return True

    def claimed(self, operation_id: str, dispatch_generation: int | None = None
                ) -> bool | None:
        """True if this generation reached a worker, False if not, None if unknown.

        The generation is part of the key, not a filter applied after it. A
        claim for generation 1 must not silence generation 2, and it must not
        be readable as a claim about any other operation.

        A line recorded with `dispatched: false` is a claim that was made and
        then taken back, so it is not a claim. It is answered here rather than
        filtered at the read so that the question has one answer wherever it is
        asked -- a caller cannot see a claim this method would call False and
        some other reader call True.

        The LAST line for the key wins, not the first. The ledger is append-only
        and a generation may be attempted more than once, so the newest line is
        the one that says what most recently happened to it. A `dispatched: false`
        only ever retracts claims written before it, so a later `dispatched: true`
        is not undone by an earlier retraction.
        """
        try:
            claims = self._read_claims()
        except OSError:
            return None
        generation = int(dispatch_generation or 0)
        answer: bool | None = None
        for claim in claims:
            if claim.get("operation_id") != operation_id:
                continue
            if int(claim.get("dispatch_generation") or 0) == generation:
                answer = bool(claim.get("dispatched", True))
        return answer if answer is not None else False

    def _never_sent_on_disk(self, operation_id: str) -> bool:
        base = _sanitize(operation_id)
        for suffix in _NEVER_SENT_SUFFIXES:
            if any(self.run_dir.glob(f"{base}_*{suffix}")):
                return False
        return True

    def prove_never_sent(self, operation_id: str, dispatch_generation: int | None = None) -> bool:
        """True only with positive proof nothing was ever sent under this identity.

        A worker still running is a send, and its pid file is the one piece of
        evidence a stopped supervisor does not remove. This mirrors
        ``RunscLauncher.prove_never_sent``, which consults ``docker ps`` for the
        same reason: a live process is proof of a claim that the run directory
        alone cannot refute.

        The claim ledger is the other half. Every marker below lives in the run
        directory, and the run directory is a worker's own work tree, so
        erasing it is a write the worker can already do. A claim made before
        the spawn and kept outside that directory is what makes erasure an
        erasure of working notes rather than of the record.
        """
        if not self.run_dir.is_dir():
            return False
        if self.is_live(operation_id):
            return False
        if self.claimed(operation_id, dispatch_generation) is not False:
            return False
        return self._never_sent_on_disk(operation_id)

    def attest_never_sent(self, operation_id: str,
                          dispatch_generation: int) -> dict[str, Any] | None:
        """The never-sent proof, carrying a capability only this launcher can mint.

        The store sees ``claim``, ``subject``, ``provenance`` and
        ``dispatch_generation``, and all four are readable off the operation
        row. The capability is a keyed digest over the operation and its
        dispatch generation under a secret this process drew at construction,
        so a caller can copy the four fields the store checks and cannot
        produce the one it never sees.
        """
        generation = int(dispatch_generation or 0)
        if generation <= 0 or not self.prove_never_sent(operation_id, generation):
            return None
        return {
            "claim": "never-sent",
            "subject": operation_id,
            "provenance": f"{self.launcher_id}:prove_never_sent",
            "dispatch_generation": generation,
            "capability": mint_dispatch_capability(operation_id, generation, self._secret),
        }

    def verify_capability(self, operation_id: str, dispatch_generation: int,
                          capability: str) -> bool:
        if not isinstance(capability, str) or not capability:
            return False
        return hmac.compare_digest(
            capability,
            mint_dispatch_capability(operation_id, int(dispatch_generation or 0),
                                     self._secret))

    def live_ids(self) -> list[str]:
        alive = []
        for pid_file in self.run_dir.glob("*.pid"):
            try:
                os.kill(int(pid_file.read_text().strip()), 0)
                alive.append(pid_file.stem)
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                continue
        return sorted(alive)

    def is_live(self, operation_id: str) -> bool:
        for pid_file in self.run_dir.glob(f"{_sanitize(operation_id)}_*.pid"):
            try:
                os.kill(int(pid_file.read_text().strip()), 0)
                return True
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                continue
        return False

    def read_result(self, operation_id: str) -> dict[str, Any] | None:
        for result_file in self.run_dir.glob(f"{_sanitize(operation_id)}_*.result.json"):
            try:
                return json.loads(result_file.read_text())
            except (ValueError, OSError):
                return {"outcome": "unknown", "parse": "stored-result-unreadable"}
        return None

    def _pgid_dead(self, pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return False
        except (ProcessLookupError, PermissionError, OSError):
            return True

    def stop(self, operation_id: str) -> bool:
        targets = []
        for pid_file in self.run_dir.glob(f"{_sanitize(operation_id)}_*.pid"):
            try:
                targets.append(int(pid_file.read_text().strip()))
            except (ValueError, OSError):
                continue
        if not targets:
            return self.read_result(operation_id) is not None
        for pgid in targets:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                continue
        deadline = time.monotonic() + self.grace_ms / 1000
        pending = [pgid for pgid in targets if not self._pgid_dead(pgid)]
        while pending and time.monotonic() < deadline:
            time.sleep(0.05)
            pending = [pgid for pgid in pending if not self._pgid_dead(pgid)]
        for pgid in pending:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                continue
        return all(self._pgid_dead(pgid) for pgid in targets)

    def _claim(self, pid_path: Path) -> bool:
        try:
            fd = os.open(pid_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.close(fd)
            return True
        except FileExistsError:
            return False
        except OSError:
            return False

    def _unwind_claim(self, paths: dict[str, Path], prior_spawns: int,
                      prior_generation: int | None) -> None:
        """Undo the markers a refused dispatch wrote, so no send is implied.

        The pid file, spawn count and generation record are the launcher's own
        evidence that a worker exists. A dispatch that returned before
        ``Popen`` has no worker, so leaving them behind would turn a refused
        launch into a prior send and strand the operation for work that never
        ran. The work directory stays: it holds staged inputs that predated
        this dispatch, and ``prove_never_sent`` does not read it.
        """
        for key in ("pid", "supervise", "result"):
            try:
                paths[key].unlink()
            except OSError:
                pass
        try:
            if prior_spawns:
                paths["spawns"].write_text(str(prior_spawns))
            else:
                paths["spawns"].unlink()
        except OSError:
            pass
        try:
            if prior_generation is None:
                paths["generation"].unlink()
            else:
                paths["generation"].write_text(str(prior_generation))
        except OSError:
            pass

    def _supervise(self, paths: dict[str, Path], pid: int, timeout_ms: int) -> Any:
        grace_s = max(self.grace_ms / 1000, 1)
        try:
            paths["supervise"].write_text(json.dumps(
                {"pid": pid, "deadline_epoch": time.time() + timeout_ms / 1000 + grace_s,
                 "grace_s": grace_s, "result": paths["result"].name}))
        except OSError:
            return None
        return spawn_deadline_supervisor(
            pid, pid, proc_starttime(pid), str(paths["result"]),
            timeout_ms / 1000 + grace_s + 1, grace_s)

    def dispatch(self, op: BrokerOp, *, require_host: str | None = None) -> LaunchOutcome:
        """Send `op` to a child on the host this launcher runs on.

        `require_host` names the execution host the caller insists on. It is
        checked before anything durable is written, so a dispatch asked for a
        host it is not on is refused the same way a missing bound is, rather
        than being allowed to claim the operation and then fail somewhere less
        readable. `None` means the caller has no preference and is not asking
        this question; it is not a wildcard, because there is no branch here
        that substitutes one host for another.
        """
        paths = self._paths(op.operation_id, op.execution_version)
        if paths["result"].exists():
            return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
        try:
            child_limits.require_execution_host(require_host)
        except child_limits.UnsupportedChildLimit as exc:
            # Before the claim, so a demand this host cannot meet leaves the
            # operation as re-admissible as a missing bound does.
            return LaunchOutcome(sent=False, refused_reason="execution-host-unavailable: %s"
                                 % exc)
        generation = int(op.dispatch_generation or 0)
        # The spawn count as it stood before this dispatch touched anything.
        # Every refusal below returns a marker set the successful path writes,
        # and each one has to put the count back rather than leave a number
        # that implies a spawn this dispatch never made. It is read here,
        # before the claim, so the value is the genuine prior count and every
        # refusal can reach it: a name bound below the branch that uses it is a
        # crash on exactly the path where an absent capability makes that
        # branch the only one taken.
        seen = self._recorded_generation(paths["spawns"]) or 0
        if not self._claim(paths["pid"]):
            recorded = self._recorded_generation(paths["generation"])
            if recorded is not None and recorded != generation:
                if generation > recorded:
                    paths["generation"].write_text(str(generation))
                return LaunchOutcome(sent=False, refused_reason="superseded-claim")
            return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
        recorded = self._recorded_generation(paths["generation"])
        if recorded is not None and recorded > generation:
            try:
                paths["pid"].unlink()
            except OSError:
                pass
            return LaunchOutcome(sent=False, refused_reason="superseded-generation")
        paths["generation"].write_text(str(generation))
        if self._recorded_generation(paths["generation"]) != generation:
            # A generation that moved under this dispatch is a refusal, and a
            # refusal that keeps the pid claim strands the operation exactly as
            # the read-boundary refusal used to: the next dispatch of the same
            # operation reads its own claim back as a prior send.
            #
            # Only the claim is released. The generation file now holds the
            # *newer* dispatch's record, and `recorded` -- read before that
            # write -- is this dispatch's own stale view of it, so unwinding it
            # would delete a live generation's evidence. The spawn count has
            # not been incremented yet, so there is nothing there to restore
            # either. This is the same pid release as the branch above, and it
            # is what RunscLauncher does at this decision.
            try:
                paths["pid"].unlink()
            except OSError:
                pass
            return LaunchOutcome(sent=False, refused_reason="superseded-generation")
        prior_generation = recorded
        payload = op.payload
        timeout_ms = int(payload.get("timeout_ms", 30_000))
        max_bytes = int(payload.get("max_output_bytes", 1_048_576))
        argv = list(payload["argv"])
        work = self._work_dirs(op.operation_id, op.execution_version)
        work["inputs"].mkdir(parents=True, exist_ok=True)
        work["outputs"].mkdir(parents=True, exist_ok=True)
        requested = payload.get("cwd")
        child_cwd = str(requested) if isinstance(requested, str) and \
            Path(requested).is_dir() else str(work["work"])
        confinement = {"read_deny": list(payload.get("read_deny") or []),
                       "read_allow": list(payload.get("read_allow") or []),
                       "cwd": child_cwd,
                       "limits": _requested_limits(payload)}
        # The spawn count was read above, before the claim, so it is already
        # the value this dispatch has to restore.
        if confinement["read_deny"] and not landlock_available():
            # A boundary that cannot be enforced must not be silent. The
            # caller asked for confinement the kernel cannot provide, and
            # running anyway is the exact failure mode N-36 is about: the
            # protection looks present and is not.
            #
            # The unwind is the whole point of refusing rather than raising.
            # The pid claim above is already durable, so a refusal that left
            # it behind would answer the caller's retry with
            # prior-send-recorded and strand an operation that never ran.
            self._unwind_claim(paths, seen, prior_generation)
            return LaunchOutcome(
                sent=False,
                refused_reason="read-boundary-unavailable: %s"
                               % probe_landlock().reason)
        # One question, one answer, and the answer says which kind of cannot it
        # is. This used to be two guards: one about the declared bounds and one
        # about the platform, each with its own `os.name` test, and between them
        # they covered every case except the one that actually escaped.
        #
        # The bounds guard short-circuited to "" when the payload declared
        # nothing, so the UNLIMITED dispatch was the unguarded one: nothing
        # declared, nothing to refuse, and `preexec_fn` handed to a `Popen`
        # that CPython refuses on this platform -- `ValueError: preexec_fn is
        # not supported on Windows platforms`, also not in the caught tuple,
        # escaping with the markers above still on disk. On Windows the
        # *limited* dispatch already worked, because it was refused, and the
        # *unlimited* one was the one that broke. The check was aimed at the
        # wrong case.
        #
        # The platform guard was the right answer asked of the wrong shape: it
        # read `os.name` here, which is a second copy of the decision
        # `child_limits` already owns, and the copy is what left the POSIX arm
        # a constant. This launcher installs every boundary it has through
        # `preexec_fn`, so a host that refuses `preexec_fn` cannot run this
        # profile at all, declared bounds or not. `read_deny` is not an
        # exception to that: that branch needs the same `preexec_fn` to install
        # the Landlock ruleset, so it is refused by the guard above and cannot
        # reach here.
        #
        # Refusing keeps the dispatch re-admissible either way: same unwind,
        # so a refusal never strands an operation that never ran. The bound
        # names are prepended here rather than in `child_limits`, which answers
        # about the host and the reach, not about which key the caller used. A
        # caller reading this string needs to know which of its declared bounds
        # could not be installed, and that is the dispatch's information.
        refusal = child_limits.child_setup_refusal(confinement["limits"])
        if refusal is not None:
            self._unwind_claim(paths, seen, prior_generation)
            return LaunchOutcome(
                sent=False,
                refused_reason="%s: %s: %s"
                               % (refusal.kind,
                                  ", ".join(confinement["limits"].names())
                                  or "no bound requested",
                                  refusal.reason))
        paths["spawns"].write_text(str(seen + 1))
        if not self._append_claim(operation_id=op.operation_id,
                                  dispatch_generation=generation,
                                  execution_version=op.execution_version,
                                  dispatched=True):
            # A send whose claim could not be made durable is a send this
            # launcher can never prove it did not make, so it does not send.
            # The markers above came back with the refusal, leaving the
            # operation reclaimable rather than stranding on evidence of work
            # that never ran.
            self._unwind_claim(paths, seen, prior_generation)
            return LaunchOutcome(sent=False, refused_reason="claim-not-durable")
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=scrub_env({"SETTLEMENT_OPERATION": op.operation_id}),
                cwd=child_cwd,
                preexec_fn=_child_setup(confinement),
            )
        except Exception as exc:
            # A child that never became a worker. CPython reports every one of
            # these as a bare `SubprocessError: Exception occurred in
            # preexec_fn.` -- the child's real type, message and errno are
            # discarded in `_posixsubprocess.c` before the parent sees them --
            # and `ValueError: preexec_fn is not supported on Windows platforms`
            # arrives the same way, except that one is raised in the parent.
            #
            # The caught tuple used to be `(OSError, MemoryError)` and it caught
            # none of them: `SubprocessError` is not an `OSError`. So a declared
            # bound the child could not install left `dispatch` by exception,
            # with the markers written above still on disk. The next dispatch of
            # the same operation read its own claim back as
            # `prior-send-recorded` and the operation was stranded for work that
            # never ran -- the exact outcome `_unwind_claim` exists to prevent,
            # reached by the path that was supposed to prevent it.
            #
            # `Exception` and not `BaseException`, so that a `KeyboardInterrupt`
            # or `SystemExit` arriving at the spawn still propagates. Taking the
            # claim back is only honest when this process is certain no worker
            # exists, and an operator's interrupt says the opposite: the spawn's
            # outcome is unknown, which is precisely the case the durable claim
            # is there to cover. Every exception CPython raises here is an
            # `Exception`, so narrowing costs no coverage.
            #
            # The unwind is what makes `sent=False` honest here rather than a
            # guess. A child that raises in `preexec_fn` has not exec'd, so no
            # argv of this dispatch ever ran, and the launcher can prove that
            # instead of asserting it. That is strictly stronger than a spawn
            # failure, where the exec itself may be what failed, which is why
            # the two get different reason prefixes: the caller can tell a
            # boundary that stopped the child from a child that never started.
            #
            # The pre-spawn refusals above do not need this branch, and the
            # Windows one above is what keeps this branch off the common path
            # there: a host that cannot run `preexec_fn` cannot reach a spawn
            # that needs one.
            self._append_claim(operation_id=op.operation_id,
                               dispatch_generation=generation,
                               execution_version=op.execution_version,
                               dispatched=False)
            self._unwind_claim(paths, seen, prior_generation)
            return LaunchOutcome(
                sent=False,
                refused_reason="child-setup-failed: %s: %s"
                               % (type(exc).__name__, exc))
        paths["pid"].write_text(str(proc.pid))
        supervisor = self._supervise(paths, proc.pid, timeout_ms)
        try:
            raw_out, raw_err = proc.communicate(timeout=timeout_ms / 1000)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                raw_out, raw_err = proc.communicate(timeout=self.grace_ms / 1000)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
                raw_out, raw_err = proc.communicate()
            timed_out = True
        wall_ms = int((time.monotonic() - started) * 1000)
        out, out_cut = _cap(raw_out or b"", max_bytes)
        err, err_cut = _cap(raw_err or b"", max_bytes)
        content = _interpret(proc.returncode or 0, out.decode("utf-8", "replace"),
                             err.decode("utf-8", "replace"), out_cut or err_cut,
                             timed_out, wall_ms, argv)
        paths["result"].write_text(json.dumps({"outcome": content["_verdict"], **content}))
        content["data"]["supervised"] = supervisor is not None
        try:
            paths["pid"].unlink()
        except OSError:
            pass
        try:
            paths["supervise"].unlink()
        except OSError:
            pass
        reap_supervisor(supervisor)
        receipt = ReceiptProposal(
            receipt_identity=f"local:{paths['result'].stem}", content=content,
            outcome=content["_verdict"], provenance=self.launcher_id)
        return LaunchOutcome(sent=True, receipt=receipt)


def _requested_limits(payload: dict[str, Any]) -> ChildLimits:
    """The bounds this dispatch asked for, as the one typed shape.

    A payload key that is absent or null is no request, not a zero. Reading
    them here is what makes the child see the same numbers the caller declared
    rather than a dict that happens to be missing them.
    """
    def _int_or_none(key: str) -> int | None:
        value = payload.get(key)
        return int(value) if value is not None else None

    return ChildLimits(cpu_seconds=_int_or_none("cpu_seconds"),
                       memory_bytes=_int_or_none("memory_bytes"))


def _child_setup(payload: dict[str, Any]):
    def _setup() -> None:
        # Installed before the exec, so a boundary that cannot be enforced
        # stops the child from existing at all. Doing it after the child ran
        # would be a measurement, not a containment. `child_limits` owns the
        # platform decision and raises rather than degrading to unbounded.
        child_limits.apply_child_limits(payload["limits"])
        deny = payload.get("read_deny") or []
        if deny:
            _landlock_restrict(_child_read_allowlist(payload), list(deny))
        os.setsid()

    return _setup


def _child_read_allowlist(payload: dict[str, Any]) -> list[str]:
    """The roots a confined child may read, beside the ones it is denied.

    Defaults to the interpreter's own installation and the operation work
    tree: what a child needs to start Python and to read what the launcher
    staged for it. A caller that stages more declares more. The repository is
    NOT in this list, and that is the boundary rather than an omission --
    a policy that could read the source is a policy that can read the key it
    is measured against.
    """
    declared = payload.get("read_allow")
    if isinstance(declared, list) and declared:
        roots = [str(p) for p in declared]
    else:
        roots = [sys.prefix, sys.base_prefix, str(payload.get("cwd") or "")]
        roots.extend([os.path.dirname(os.__file__ or ""),
                      os.path.dirname(json.__file__ or "")])
    existing = [r for r in roots if r and os.path.isdir(r)]
    seen: list[str] = []
    for root in existing:
        if root not in seen:
            seen.append(root)
    return seen


def _cap(raw: bytes, limit: int) -> tuple[bytes, bool]:
    if len(raw) > limit:
        return raw[:limit], True
    return raw, False


def _base(containment: bool, argv: list[str], data: dict[str, Any]) -> dict[str, Any]:
    # `profile` names the mechanism and was the same string on every host this
    # file has run on, so a Linux receipt and a Windows receipt compared as one
    # measurement. `host` names the process that produced it, read per receipt
    # rather than configured, so it cannot go stale.
    return {"containment": containment, "profile": PROFILE, "host":
            child_limits.current_execution_host().kind, "argv": argv, "data": data}


def _interpret(returncode: int, stdout: str, stderr: str, truncated: bool,
               timed_out: bool, wall_ms: int, argv: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {"stdout": stdout, "returncode": returncode,
                            "timed_out": timed_out, "wall_ms": wall_ms}
    if stderr:
        data["stderr"] = stderr
    verdict = "failure"
    parse = "rejected"
    if not timed_out and returncode == 0 and not stdout.strip():
        parse = "empty"
        verdict = "success"
    elif not timed_out and returncode == 0:
        try:
            worker = WorkerOutput.model_validate(json.loads(stdout))
            if worker.status in ("ok", "error"):
                parse = "typed-json"
                data = {"worker": worker.model_dump(), "timed_out": timed_out, "wall_ms": wall_ms}
                verdict = "success" if worker.status == "ok" else "failure"
        except (ValueError, TypeError):
            parse = "rejected"
    content = _base(False, argv, data)
    content.update({"truncated": truncated, "parse": parse, "_verdict": verdict})
    return content
