"""S1 durable state: every consequential transition runs as one short SERIALIZABLE
transaction through the single locked control row (TX-1).

Conventions for T3/T4 callers: each mutating function takes ``(dsn, cmd)``
where ``cmd`` is a :class:`settlement.common.Command` whose ``payload`` dict
carries the named inputs. Each returns a :class:`CommandResult` whose ``code``
is one of the shared :class:`ResultCode` values. Request identity is bound to
a payload digest in ``command_journal``; a duplicate identity with the same
payload returns the stored result, with a different payload it is refused.
Serialization failures retry the whole transaction, bounded by the command
deadline (TX-2). Money is scaled integers only. No model calls, container
runs, or external writes happen inside a retried transaction.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from typing import Any, Callable

from psycopg import errors as _pgerrors
from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import attestation, db
from .common import (
    SUPERVISION_SCOPE,
    Command,
    CommandResult,
    ConflictPayload,
    InsufficientResources,
    MissingEvidence,
    ResultCode,
    SettlementError,
    StaleRevision,
    Unauthorized,
    payload_digest,
)

_RETRY = (_pgerrors.SerializationFailure, _pgerrors.DeadlockDetected)


def _connect_before(dsn: str, wait_s: float, orphan_s: float):
    """Open a connection, returning None when the wait outlasts the deadline.

    Fast failures (refused, unknown database) still raise. A wait that
    outlasts the caller's deadline returns None so the caller can report a
    bounded result; the orphaned attempt is daemonized and itself bounded by
    ``orphan_s``.
    """
    holder: dict[str, Any] = {}

    def _open() -> None:
        try:
            holder["conn"] = db.connect(dsn, connect_timeout=orphan_s)
        except Exception as exc:  # noqa: BLE001 - transported to the waiter
            holder["error"] = exc

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()
    thread.join(wait_s)
    if thread.is_alive():
        return None
    if "conn" not in holder:
        raise holder.get("error")
    return holder["conn"]


class _DeadlineCursor:
    """Re-arm statement timeouts from the remaining command budget per statement."""

    def __init__(self, cur: Any, deadline: float) -> None:
        self._cur = cur
        self._deadline = deadline

    def _rearm(self) -> None:
        remaining_ms = max(int((self._deadline - time.monotonic()) * 1000), 1)
        self._cur.execute(f"SET LOCAL statement_timeout = '{remaining_ms}ms'")

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self._rearm()
        return self._cur.execute(*args, **kwargs)

    def executemany(self, *args: Any, **kwargs: Any) -> Any:
        self._rearm()
        return self._cur.executemany(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cur, name)

_OUTCOMES = {"success", "failure", "unknown"}
# An outcome that decides an operation. The complement of `unknown`, named
# once because the multi-receipt guard below has to ask "does this receipt
# claim anything terminal" in three places and must not drift between them.
_DECIDED_OUTCOMES = {"success", "failure"}
_TERMINAL_ATTEMPT = {"completed", "failed", "cancelled"}
_TERMINAL_UNKNOWN = "unresolved-terminal"
CANONICAL_CHARGE_SCALE = 1000
CEILING_COUNTERS = {
    "operations": "operations",
    "model_calls": "model_calls",
    "model_dispatches": "model_calls",
    "construction_calls": "construction_calls",
    "sandbox_calls": "sandbox_calls",
    "sandbox_execs": "sandbox_calls",
    "execution_units": "execution_units",
    "sandbox_units": "execution_units",
    "calibration": "calibration",
    "development": "development",
    "repair": "repair",
    "use": "use",
}


# Ceilings a study declares that this layer records but does not count.
# A boundary is a trajectory-level decision and an oracle query is a child
# call, so neither appears as a durable operation row. Accepting the
# declaration keeps the sheet whole; refusing it made the study unstartable
# with a valid grant, which is the worse failure.
DECLARED_CEILINGS = frozenset({
    "boundaries", "witness_queries", "dev_episodes", "lineages",
    "deadline_s", "trajectories", "diagnostic_queries",
})


def is_ceiling_name(name: object) -> bool:
    """Whether a study may declare this ceiling, with or without `max_`."""
    text = str(name)
    bare = text.removeprefix("max_")
    return (text in CEILING_COUNTERS or bare in CEILING_COUNTERS
            or text in DECLARED_CEILINGS or bare in DECLARED_CEILINGS)


def is_ceiling_enforced(name: object) -> bool:
    """Whether this layer actually counts and checks the ceiling `name`.

    `is_ceiling_name` answers a different question, and answering only that one
    is what N-32 named. A name in `DECLARED_CEILINGS` is a legal declaration
    and is written to `study_authority.ceilings` as authoritative, but
    `_ceiling_counter` returns None for it, so the enforcement loop skips it
    and nothing ever checks it again. A live study declares two of them,
    `max_boundaries` and `max_witness_queries`
    (`scripts/inv01_study.py:1224`), and reads back a frozen ceiling this
    layer never enforces.

    Refusing the declaration is not available here. The comment above
    `DECLARED_CEILINGS` records that refusing one "made the study unstartable
    with a valid grant, which is the worse failure", and the live caller
    proves it. So the gap is made answerable instead: a caller that wants to
    know whether a bound is real asks this, and `trajectory.py`, which reads a
    campaign `caps` dict rather than the stored `ceilings`, is exactly the kind
    of caller that was reading two records for one quantity.
    """
    return _ceiling_counter(name) is not None


def unenforced_ceilings() -> list[str]:
    """Every ceiling name this layer accepts and will never check."""
    return sorted(DECLARED_CEILINGS)


def require_enforceable_ceilings(ceilings: dict[str, Any]) -> None:
    """Refuse a cap sheet that names a ceiling this layer cannot enforce.

    For a caller about to report a sheet as a set of enforced bounds. It is
    not a substitute for the `authorize_study` decision, which is where a
    declared-only ceiling should be refused outright if a study is going to be
    unstartable without it. It is the assertion a downstream consumer makes
    when it is about to treat a name as a bound it can rely on.
    """
    unbacked = [str(name) for name in dict(ceilings or {})
                if not is_ceiling_enforced(name)]
    if unbacked:
        raise MissingEvidence(
            "ceilings this layer does not count or enforce: %s"
            % ", ".join(sorted(unbacked)))


def _ceiling_counter(name: object) -> str | None:
    """The counter a ceiling names, tolerating a study's `max_` prefix.

    A cap sheet is written as `max_model_calls` and the counter is
    `model_calls`. Enforcement has to read the same name admission accepts,
    or a study that was authorized under one spelling fails at the first
    operation under the other, which reads as a resource bug rather than a
    naming one.
    """
    text = str(name)
    return CEILING_COUNTERS.get(text) or CEILING_COUNTERS.get(
        text.removeprefix("max_"))


def _j(value: Any) -> Json:
    return Json(dict(value) if isinstance(value, dict) else (value if value is not None else {}))


def _code(exc: BaseException) -> ResultCode:
    if isinstance(exc, SettlementError):
        return exc.code
    return ResultCode.INVALID_INPUT


def _stored(row: dict) -> CommandResult:
    return CommandResult(
        code=ResultCode(row["result_code"]),
        request_id=row["request_id"],
        detail=row["result_detail"],
        data=dict(row["result_data"] or {}),
    )


def _check_evidence(payload: dict, control: dict) -> None:
    epoch = payload.get("evidence_epoch")
    if epoch is not None and int(epoch) < int(control["evidence_epoch"]):
        raise MissingEvidence(f"stale evidence epoch {epoch} < {control['evidence_epoch']}")


def _finish(cur, control, cmd, digest, code, detail, data, events, outbox) -> CommandResult:
    epoch = None
    if events or outbox:
        cur.execute("UPDATE control SET event_epoch = event_epoch + 1 WHERE id = 1 RETURNING event_epoch")
        epoch = cur.fetchone()["event_epoch"]
        for ordinal, (kind, payload) in enumerate(events):
            cur.execute(
                "INSERT INTO domain_events (epoch, ordinal, kind, payload) VALUES (%s, %s, %s, %s)",
                (epoch, ordinal, kind, _j(payload)),
            )
        for kind, payload, identity in outbox:
            cur.execute(
                "INSERT INTO outbox (workflow_identity, intent_kind, payload, created_epoch, created_ordinal)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (workflow_identity) DO NOTHING",
                (identity, kind, _j(payload), epoch, 0),
            )
    cur.execute(
        "INSERT INTO command_journal (request_id, payload_digest, result_code, result_detail, result_data)"
        " VALUES (%s, %s, %s, %s, %s)",
        (cmd.request_id, digest, code.value, detail, _j(data)),
    )
    return CommandResult(code=code, request_id=cmd.request_id, detail=detail, data=data)


Handler = Callable[..., tuple[ResultCode, str, dict, list, list]]


def transact(dsn: str, cmd: Command, fn: Handler, *args: Any) -> CommandResult:
    """Run ``fn(cur, control, *args)`` once through the locked control row."""
    digest = payload_digest(cmd.payload)
    budget_ms = max(int(cmd.deadline_ms), 1)
    deadline = time.monotonic() + budget_ms / 1000.0
    orphan_s = max(2.0, min(30.0, math.ceil(budget_ms / 1000.0)))
    while True:
        if time.monotonic() >= deadline:
            return CommandResult(code=ResultCode.UNAVAILABLE_DEPENDENCY, request_id=cmd.request_id,
                                 detail="absolute command deadline exhausted", data={})
        remaining_s = max(deadline - time.monotonic(), 0.001)
        try:
            conn = _connect_before(dsn, remaining_s, orphan_s)
            if conn is None:
                return CommandResult(code=ResultCode.UNAVAILABLE_DEPENDENCY, request_id=cmd.request_id,
                                     detail="connection wait exceeded the command deadline", data={})
            with conn:
                with conn.cursor(row_factory=dict_row) as raw:
                    raw.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    remaining_ms = max(int((deadline - time.monotonic()) * 1000), 1)
                    raw.execute(f"SET LOCAL lock_timeout = '{remaining_ms}ms'")
                    cur = _DeadlineCursor(raw, deadline)
                    cur.execute("SELECT * FROM control WHERE id = 1 FOR UPDATE")
                    control = cur.fetchone()
                    if control is None:
                        cur.execute("INSERT INTO control (id) VALUES (1) ON CONFLICT DO NOTHING")
                        cur.execute("SELECT * FROM control WHERE id = 1 FOR UPDATE")
                        control = cur.fetchone()
                    cur.execute(
                        "SELECT request_id, payload_digest, result_code, result_detail, result_data"
                        " FROM command_journal WHERE request_id = %s",
                        (cmd.request_id,),
                    )
                    found = cur.fetchone()
                    if found is not None:
                        conn.commit()
                        if found["payload_digest"] != digest:
                            raise ConflictPayload(f"request identity {cmd.request_id} reused with different payload")
                        result = _stored(found)
                        result.request_id = cmd.request_id
                        if result.code == ResultCode.APPLIED:
                            result.code = ResultCode.ALREADY_APPLIED
                        return result
                    try:
                        _check_evidence(cmd.payload, control)
                        code, detail, data, events, outbox = fn(cur, control, *args)
                    except SettlementError as exc:
                        conn.rollback()
                        with conn.cursor(row_factory=dict_row) as raw2:
                            raw2.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                            cur2 = _DeadlineCursor(raw2, deadline)
                            result = CommandResult(code=_code(exc), request_id=cmd.request_id, detail=str(exc), data={})
                            cur2.execute(
                                "INSERT INTO command_journal (request_id, payload_digest, result_code,"
                                " result_detail, result_data) VALUES (%s, %s, %s, %s, %s)"
                                " ON CONFLICT (request_id) DO NOTHING",
                                (cmd.request_id, digest, result.code.value, result.detail, _j(result.data)),
                            )
                            conn.commit()
                        return result
                    result = _finish(cur, control, cmd, digest, code, detail, data, events, outbox)
                    conn.commit()
                    return result
        except ConflictPayload:
            raise
        except (_pgerrors.LockNotAvailable, _pgerrors.QueryCanceled):
            return CommandResult(code=ResultCode.UNAVAILABLE_DEPENDENCY, request_id=cmd.request_id,
                                 detail="control-row wait exceeded the command deadline", data={})
        except _RETRY:
            if time.monotonic() >= deadline:
                return CommandResult(code=ResultCode.UNAVAILABLE_DEPENDENCY, request_id=cmd.request_id,
                                     detail="serialization retry budget exhausted", data={})
        except _pgerrors.UniqueViolation as exc:
            if time.monotonic() >= deadline:
                raise
            if exc.diag is not None and exc.diag.constraint_name == "command_journal_pkey":
                continue
            raise


def _child_authorized(cur, parent_id: str) -> int:
    cur.execute("SELECT COALESCE(SUM(authorized), 0) AS total FROM allocations WHERE parent_id = %s", (parent_id,))
    return int(cur.fetchone()["total"])


def _alloc_available(row: dict, children: int) -> int:
    return int(row["authorized"]) - int(row["consumed"]) - int(row["reserved"]) - children


free_of = _alloc_available


def _get_alloc(cur, allocation_id: str) -> dict:
    cur.execute("SELECT * FROM allocations WHERE id = %s", (allocation_id,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown allocation {allocation_id}")
    return row


def _require_child_capacity(cur, parent_id: str, amount: int) -> dict:
    parent = _get_alloc(cur, parent_id)
    free = _alloc_available(parent, _child_authorized(cur, parent_id))
    if free < amount:
        raise InsufficientResources(
            f"parent {parent_id} has {free} free, child needs {amount}")
    return parent


def _require_allocation_within(cur, allocation_id: str, ancestor_id: str) -> None:
    cur.execute(
        "WITH RECURSIVE allocation_lineage (id) AS ("
        " SELECT id FROM allocations WHERE id = %s"
        " UNION SELECT a.id FROM allocations a"
        " JOIN allocation_lineage line ON a.parent_id = line.id)"
        " SELECT 1 FROM allocation_lineage WHERE id = %s",
        (allocation_id, ancestor_id),
    )
    if cur.fetchone() is None:
        raise ConflictPayload(
            f"allocation {allocation_id} is outside attempt allocation {ancestor_id}")


def _attempt_allocation(cur, attempt_id: str, allocation_id: str | None) -> dict:
    attempt = _get_attempt(cur, attempt_id)
    ancestor_id = attempt.get("allocation_id")
    if ancestor_id is not None:
        if allocation_id is None:
            raise ConflictPayload(f"attempt {attempt_id} requires its bound allocation")
        _require_allocation_within(cur, allocation_id, str(ancestor_id))
    return attempt


def _require_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SettlementError(f"{label} must be a non-negative integer")
    return int(value)


# The character class an execution_version is built from, and the ceiling on
# its length. Both are the store's own, because the property has to hold
# wherever the value is written and not wherever a consumer happens to filter.
# The class permits "/" because the values this repository actually passes
# include `run/v1` and the rule's own docstring names it. Omitting it made
# the rule contradict itself and broke production call sites, not just
# tests. Traversal is refused by the segment checks below, not by a ban
# on the separator: ".." is built from characters this class permits, so a
# narrower class would be theatre.
_EXEC_VERSION_CHARS = re.compile(r"\A[A-Za-z0-9._/:-]+\Z")
_EXEC_VERSION_MAX = 128


def _require_execution_version(value: Any) -> str:
    """Refuse an execution_version that would not survive being used as a name.

    The store wrote this column verbatim and left the safety to
    `launcher_local.native_id`, whose `_sanitize` maps every character outside
    `[A-Za-z0-9_.-]` to `_`. That is a filter in a consumer, and a consumer can
    change. A caller that reaches this store cannot rely on it, so the rule
    lives here, at the boundary that accepts the value.

    The rule is deliberately the narrowest one that refuses every traversal,
    because a stricter one breaks callers. The values this repository actually
    passes are `exec-v1`, `exec-v2`, `exec-default`, `v1`, `run/v1`, a
    `sha256:` digest and the empty string. `run/v1` carries a separator, so
    "no separator at all" is not available, and `..` is built from a character
    the class permits, so "no dots" is not available either. What is left is
    the property that actually matters: the value must resolve to a single
    path component under any reader that treats it as a name, which is exactly
    the absence of a `.` or `..` segment and of a leading separator.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SettlementError("execution_version must be a string")
    # No strip(). Trimming here would store a value the caller never sent,
    # and this column is compared verbatim by callers that reason about which
    # version actually ran. `' exec-v1 '` and `'  '` are therefore REFUSED
    # rather than silently normalised to `'exec-v1'` and `''` - a boundary that
    # accepts what it does not store is a boundary that lies.
    text = value
    if not text:
        return ""
    if len(text) > _EXEC_VERSION_MAX:
        raise SettlementError(
            f"execution_version must be at most {_EXEC_VERSION_MAX} characters")
    if not _EXEC_VERSION_CHARS.match(text):
        raise SettlementError(
            f"execution_version {value!r} holds a character outside "
            f"[A-Za-z0-9._/-]")
    if text.startswith("/"):
        raise SettlementError(f"execution_version {value!r} is an absolute path")
    for segment in text.split("/"):
        if segment in ("", ".", ".."):
            raise SettlementError(
                f"execution_version {value!r} has a path segment {segment!r}")
    return text


def _require_generation(value: Any, label: str = "dispatch generation") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SettlementError(f"{label} must be a positive integer")
    return int(value)


def _never_sent_proof(payload: dict[str, Any], subject: str,
                      generation: int | None = None,
                      attested_by: str | None = None) -> dict[str, str | int]:
    """Validate a caller-supplied never-sent proof, and refuse an unattested one.

    Shape alone never bought safety here. A proof saying "forged" is exactly
    as well-shaped as one saying "local-1:prove_never_sent", and consuming a
    shape-valid proof returns the operation to ``prepared`` — the state a
    second execution starts from. So the proof must also name something.

    Two things are checked, and neither substitutes for the other.
    ``_provenance_attested`` holds the proof to the launcher the operation was
    actually admitted to; a provenance naming any other launcher was not
    produced by the one that was given the work, and an operation admitted to no
    launcher has nothing that could attest for it. Both refuse. A subject with no
    operation at all passes ``None`` and keeps the shape check alone.

    The store cannot ask a launcher directly, so it reaches one through
    ``attestation``: a launcher registers its own capability check at
    construction, and this function requires that the proof carry a capability
    the admitted launcher's verifier accepts. A proof assembled from the
    operation row reproduces the subject, the generation and the provenance, and
    reproduces none of the capability, because the capability is an HMAC over a
    secret that never leaves the launcher's memory. A sandbox that really ran and
    one that never started still leave byte-identical store state; what separates
    them now is a value the store can check against something the caller does not
    have.

    Two limits travel with this. A launcher that registers no verifier is held to
    nothing, so a deployment using one gets attribution back rather than
    evidence. And registration is per-process, so the guarantee binds the
    launchers actually constructed in the process that consumes the proof.
    Substituting code that declines to attest is a different threat from
    supplying a payload, and this layer does not address it.
    """
    proof = payload.get("never_sent_proof")
    valid = (
        isinstance(proof, dict)
        and proof.get("claim") == "never-sent"
        and proof.get("subject") == subject
        and isinstance(proof.get("provenance"), str)
        and bool(proof["provenance"].strip())
    )
    supplied_generation = proof.get("dispatch_generation") if isinstance(proof, dict) else None
    if supplied_generation is not None:
        valid = valid and (
            isinstance(supplied_generation, int)
            and not isinstance(supplied_generation, bool)
            and supplied_generation > 0
        )
    if generation is not None:
        valid = valid and supplied_generation == generation
    if valid and not _provenance_attested(proof, attested_by):
        valid = False
    if valid and not _capability_attested(proof, subject, generation, attested_by):
        valid = False
    if not valid:
        raise MissingEvidence(
            "never-sent proof requires claim, subject, dispatch generation, and "
            f"provenance from the operation's own launcher {attested_by!r}")
    canonical = {
        "claim": "never-sent",
        "subject": subject,
        "provenance": proof["provenance"].strip(),
    }
    if isinstance(proof.get("capability"), str) and proof["capability"].strip():
        canonical["capability"] = proof["capability"].strip()
    if supplied_generation is not None:
        canonical["dispatch_generation"] = supplied_generation
    elif generation is not None:
        canonical["dispatch_generation"] = generation
    return canonical


def _capability_attested(proof: dict[str, Any], subject: str,
                         generation: int | None, attested_by: str | None) -> bool:
    """Whether this proof carries a capability the admitted launcher minted.

    The provenance check above holds a proof to the name of the launcher the
    operation was admitted to. That name is caller-written and, for the bundled
    launcher, a public class constant, so satisfying it costs a caller nothing
    it did not already have. This is the part that costs something: a capability
    is an HMAC over the operation, its generation and a secret that never leaves
    the launcher's memory, so a proof carrying a valid one could only have come
    from asking that launcher whether the work was ever sent.

    It is required, not merely preferred, for every launcher that can mint one.
    An optional capability field would be a second spelling rule, and the
    forgery would simply omit it.

    Two cases stand outside it, and both are about the launcher rather than the
    proof. A launcher that registered no verifier has no secret behind this id,
    so there is nothing to hold a proof to; the provenance check stands alone and
    the docstring above says so in terms. A subject with no operation behind it
    (``attested_by`` of ``None``) had no launcher to be given the work.

    The generation compared is the one the store derived from the operation row,
    never the one the proof supplies, so a proof cannot move the check onto a
    generation it likes.
    """
    if attested_by is None or not attested_by:
        return True
    if not attestation.attests(attested_by):
        return True
    if generation is None:
        return False
    return attestation.check(attested_by, subject, int(generation),
                             proof.get("capability"))


def _provenance_attested(proof: dict[str, Any], attested_by: str | None) -> bool:
    """True when the proof's provenance is the admitted launcher's own name.

    ``broker._structured_never_sent_proof`` writes ``<launcher id>:prove_never_sent``
    for every launcher that exposes the method, so the launcher id is the one
    part of a proof the store can hold the caller to.

    ``attested_by`` of ``None`` means the subject has no operation behind it —
    a reservation reserved without one, for instance. There is no launcher that
    could have been given the work, so there is nothing to hold the proof to and
    the shape check stands alone. An empty string is different: the operation
    exists and was admitted to no launcher, so nothing can attest for it and
    the proof is refused. Every real operation-bound proof passes its actual
    ``launcher_id``.

    What this does not do is decide whether a run started. The id it compares
    against is caller-written, caller-readable, and public for the bundled
    launcher, so a caller can satisfy it by reading the row rather than by
    asking a launcher. It excludes proofs aimed at the wrong launcher, which
    is a real narrowing over accepting any non-empty string and worth keeping.
    It does not exclude a forgery aimed at the right one.
    """
    if attested_by is None:
        return True
    if not attested_by:
        return False
    provenance = str(proof.get("provenance", "")).strip()
    return provenance == attested_by or provenance.startswith(f"{attested_by}:")


def _take_reservation(cur, allocation_id: str, reservation_id: str, amount: int, operation_id: str) -> None:
    if int(amount) <= 0:
        raise SettlementError("reservation amount must be a positive integer")
    alloc = _get_alloc(cur, allocation_id)
    if _alloc_available(alloc, _child_authorized(cur, allocation_id)) < int(amount):
        raise InsufficientResources(f"allocation {allocation_id} cannot cover {amount}")
    cur.execute(
        "UPDATE allocations SET reserved = reserved + %s WHERE id = %s",
        (int(amount), allocation_id),
    )
    cur.execute(
        "INSERT INTO reservations (id, allocation_id, operation_id, amount, state)"
        " VALUES (%s, %s, %s, %s, 'reserved')",
        (reservation_id, allocation_id, operation_id, int(amount)),
    )


def _reject_terminal_intent(body: Any) -> None:
    if isinstance(body, dict) and "_terminal_disposition" in body:
        raise ConflictPayload("operation body cannot set _terminal_disposition")


def _terminal_disposition(operation: dict[str, Any]) -> dict[str, Any] | None:
    stored = dict(operation.get("payload") or {})
    disposition = stored.get("_terminal_disposition")
    if isinstance(disposition, dict) and disposition.get("kind") == _TERMINAL_UNKNOWN:
        return disposition
    return None


def _refuse_terminal_unknown(operation: dict[str, Any], transition: str) -> None:
    if _terminal_disposition(operation) is not None:
        raise MissingEvidence(
            f"operation {operation['id']} is {_TERMINAL_UNKNOWN}; {transition} is not permitted")


def _settle_amount(cur, reservation_id: str, outcome: str, actual: Any = None) -> tuple[bool, str, int]:
    cur.execute("SELECT * FROM reservations WHERE id = %s", (reservation_id,))
    res = cur.fetchone()
    if res is None:
        raise SettlementError(f"unknown reservation {reservation_id}")
    if outcome not in _OUTCOMES:
        raise SettlementError(f"unknown outcome {outcome}")
    if res["state"] == "settled":
        return False, "already settled", 0
    if res["state"] == "released":
        raise SettlementError(f"reservation {reservation_id} was released")
    if outcome == "unknown":
        if res["state"] != "uncertain":
            cur.execute("UPDATE reservations SET state = 'uncertain' WHERE id = %s", (reservation_id,))
        return False, "uncertain exposure retained", 0
    amount = int(res["amount"])
    if actual is None:
        consumed = amount
    else:
        consumed = _require_nonnegative_int(actual, "actual cost")
        if consumed > amount:
            raise SettlementError(f"actual cost {actual} outside reserved {amount}")
    cur.execute(
        "UPDATE allocations SET reserved = reserved - %s, consumed = consumed + %s WHERE id = %s",
        (amount, consumed, res["allocation_id"]),
    )
    cur.execute("UPDATE reservations SET state = 'settled' WHERE id = %s", (reservation_id,))
    return True, "settled", consumed


def allocation_free(dsn: str, allocation_id: str) -> int:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM allocations WHERE id = %s", (allocation_id,))
            row = cur.fetchone()
            if row is None:
                raise SettlementError(f"unknown allocation {allocation_id}")
            cur.execute("SELECT COALESCE(SUM(authorized), 0) AS total FROM allocations"
                        " WHERE parent_id = %s", (allocation_id,))
            children = int(cur.fetchone()["total"])
            conn.commit()
            return free_of(dict(row), children)


def get_control(dsn: str) -> dict:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("INSERT INTO control (id) VALUES (1) ON CONFLICT DO NOTHING")
            cur.execute("SELECT * FROM control WHERE id = 1")
            conn.commit()
            return dict(cur.fetchone())


def allocation_status(dsn: str, allocation_id: str) -> dict:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM allocations WHERE id = %s", (allocation_id,))
            row = cur.fetchone()
            conn.commit()
            if row is None:
                raise SettlementError(f"unknown allocation {allocation_id}")
            return {k: (dict(v) if isinstance(v, dict) else v) for k, v in dict(row).items()}


def seed_grant(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        version = p["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
            raise SettlementError("grant version must be a positive integer")
        charter_text = p["charter_text"]
        authority_grant = dict(p.get("authority_grant", {}))
        envelopes = dict(p.get("envelopes", {}))
        cur.execute(
            "SELECT charter_text, authority_grant, envelopes FROM grants WHERE version = %s",
            (version,),
        )
        existing = cur.fetchone()
        if existing is not None:
            immutable = (
                existing["charter_text"] == charter_text
                and dict(existing["authority_grant"] or {}) == authority_grant
                and dict(existing["envelopes"] or {}) == envelopes
            )
            if not immutable:
                raise ConflictPayload(f"grant v{version} is immutable")
            return (ResultCode.ALREADY_APPLIED, f"grant v{version} already seeded",
                    {"version": version, "authority_version": int(control["authority_version"])},
                    [], [])
        cur.execute(
            "INSERT INTO grants (version, charter_text, authority_grant, envelopes)"
            " VALUES (%s, %s, %s, %s)",
            (version, charter_text, _j(authority_grant), _j(envelopes)),
        )
        if version > int(control["authority_version"]):
            cur.execute("UPDATE control SET authority_version = %s WHERE id = 1", (version,))
        return (ResultCode.APPLIED, f"grant v{version} seeded",
                {"version": version, "authority_version": max(version, int(control["authority_version"]))},
                [("grant.seeded", {"version": version})], [])
    return transact(dsn, cmd, _fn)


def admit_commitment(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        inv_id = p["investigation_id"]
        cur.execute("SELECT 1 FROM investigations WHERE id = %s", (inv_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"investigation {inv_id} already exists")
        cur.execute(
            "INSERT INTO investigations (id, revision, objective, scope, obligations, sponsor, origin, disposition)"
            " VALUES (%s, 1, %s, %s, %s, %s, %s, 'accepted')",
            (inv_id, p["objective"], _j(p.get("scope", {})), _j(p.get("obligations", {})),
             p.get("sponsor", ""), p.get("origin", "")),
        )
        cur.execute(
            "INSERT INTO investigation_revisions (investigation_id, revision, objective, obligations)"
            " VALUES (%s, 1, %s, %s)",
            (inv_id, p["objective"], _j(p.get("obligations", {}))),
        )
        return (ResultCode.APPLIED, f"investigation {inv_id} admitted",
                {"investigation_id": inv_id, "revision": 1},
                [("commitment.admitted", {"investigation_id": inv_id, "revision": 1})], [])
    return transact(dsn, cmd, _fn)


def amend_commitment(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        cur.execute("SELECT * FROM investigations WHERE id = %s", (p["investigation_id"],))
        inv = cur.fetchone()
        if inv is None:
            raise SettlementError(f"unknown investigation {p['investigation_id']}")
        if inv["disposition"] == "withdrawn":
            raise SettlementError(f"investigation {inv['id']} is withdrawn")
        if cmd.expected_revision is not None and int(cmd.expected_revision) != int(inv["revision"]):
            raise StaleRevision(f"expected revision {cmd.expected_revision}, current {inv['revision']}")
        nxt = int(inv["revision"]) + 1
        objective = p.get("objective", inv["objective"])
        obligations = p.get("obligations", inv["obligations"])
        cur.execute(
            "UPDATE investigations SET revision = %s, objective = %s, obligations = %s,"
            " disposition = 'amended', updated_at = now() WHERE id = %s",
            (nxt, objective, _j(obligations), inv["id"]),
        )
        cur.execute(
            "INSERT INTO investigation_revisions (investigation_id, revision, objective, obligations)"
            " VALUES (%s, %s, %s, %s)",
            (inv["id"], nxt, objective, _j(obligations)),
        )
        return (ResultCode.APPLIED, f"investigation {inv['id']} amended to r{nxt}",
                {"investigation_id": inv["id"], "revision": nxt},
                [("commitment.amended", {"investigation_id": inv["id"], "revision": nxt})], [])
    return transact(dsn, cmd, _fn)


def withdraw_commitment(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        cur.execute("SELECT * FROM investigations WHERE id = %s", (p["investigation_id"],))
        inv = cur.fetchone()
        if inv is None:
            raise SettlementError(f"unknown investigation {p['investigation_id']}")
        if inv["disposition"] == "withdrawn":
            raise SettlementError(f"investigation {inv['id']} already withdrawn")
        if cmd.expected_revision is not None and int(cmd.expected_revision) != int(inv["revision"]):
            raise StaleRevision(f"expected revision {cmd.expected_revision}, current {inv['revision']}")
        cur.execute(
            "UPDATE investigations SET disposition = 'withdrawn', updated_at = now() WHERE id = %s", (inv["id"],))
        return (ResultCode.APPLIED, f"investigation {inv['id']} withdrawn",
                {"investigation_id": inv["id"], "revision": int(inv["revision"])},
                [("commitment.withdrawn", {"investigation_id": inv["id"]})], [])
    return transact(dsn, cmd, _fn)


def seed_allocation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        if int(p["authorized"]) <= 0:
            raise SettlementError("seed authorized must be a positive integer")
        if int(p.get("amount_scale", 1)) <= 0:
            raise SettlementError("seed amount_scale must be a positive integer")
        if int(p.get("max_occupancy", 8)) < 0:
            raise SettlementError("seed max_occupancy must be a non-negative integer")
        cur.execute("SELECT 1 FROM allocations WHERE id = %s", (p["allocation_id"],))
        if cur.fetchone() is not None:
            raise SettlementError(f"allocation {p['allocation_id']} already exists")
        if p.get("parent_id") is not None:
            _require_child_capacity(cur, str(p["parent_id"]), int(p["authorized"]))
        cur.execute(
            "INSERT INTO allocations (id, parent_id, domain, epoch, authorized, amount_scale,"
            " max_occupancy, owner_scope) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (p["allocation_id"], p.get("parent_id"), p["domain"], int(p.get("epoch", 0)),
             int(p["authorized"]), int(p.get("amount_scale", 1)), int(p.get("max_occupancy", 8)),
             p.get("owner_scope", "")),
        )
        return (ResultCode.APPLIED, f"allocation {p['allocation_id']} seeded",
                {"allocation_id": p["allocation_id"], "authorized": int(p["authorized"])},
                [("allocation.seeded", {"allocation_id": p["allocation_id"]})], [])
    return transact(dsn, cmd, _fn)


def subdivide_allocation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        amount = int(p["authorized"])
        if amount <= 0:
            raise SettlementError("child authorized must be a positive integer")
        parent = _require_child_capacity(cur, str(p["parent_id"]), amount)
        cur.execute(
            "INSERT INTO allocations (id, parent_id, domain, epoch, authorized, amount_scale,"
            " max_occupancy, owner_scope) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (p["child_id"], p["parent_id"], p.get("domain", parent["domain"]), int(p.get("epoch", parent["epoch"])),
             amount, int(parent["amount_scale"]), int(p.get("max_occupancy", parent["max_occupancy"])),
             p.get("owner_scope", "")),
        )
        return (ResultCode.APPLIED, f"allocation {p['child_id']} subdivided with {amount}",
                {"allocation_id": p["child_id"], "authorized": amount},
                [("allocation.subdivided", {"parent_id": p["parent_id"], "child_id": p["child_id"]})], [])
    return transact(dsn, cmd, _fn)


def reserve(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        operation_id = str(p.get("operation_id") or "")
        # Refused here rather than at settle. `settle_reservation` and
        # `release_reservation` both require the operation to exist whenever
        # the id is non-empty, and neither creates one, so a reservation
        # naming an operation that does not exist can never be settled or
        # released. Committing that row spends allocation authority on an
        # exposure nothing can ever close.
        #
        # This guard is here and not in `_take_reservation` because the
        # internal callers reserve *before* they insert the operation, in the
        # same transaction: `_prepare_operation`, the study admission path,
        # `team._insert_operation` and both agenda probe sites. A check in the
        # shared helper would refuse all six. It is also not a foreign key:
        # `reservations.operation_id` carries the empty-string sentinel for a
        # reservation with no operation behind it, and agenda's
        # `_agenda_charge_decision` deliberately names a charge that is never
        # an operations row, so no constraint on this column can be satisfied
        # by all of its writers.
        if operation_id:
            cur.execute("SELECT 1 FROM operations WHERE id = %s", (operation_id,))
            if cur.fetchone() is None:
                raise SettlementError(f"unknown operation {operation_id}")
        _take_reservation(cur, p["allocation_id"], p["reservation_id"], int(p["amount"]), operation_id)
        return (ResultCode.APPLIED, f"reserved {p['amount']}",
                {"reservation_id": p["reservation_id"], "amount": int(p["amount"])},
                [("resources.reserved", {"reservation_id": p["reservation_id"]})], [])
    return transact(dsn, cmd, _fn)


def settle_reservation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT operation_id FROM reservations WHERE id = %s",
                    (cmd.payload["reservation_id"],))
        reservation = cur.fetchone()
        if reservation is None:
            raise SettlementError(f"unknown reservation {cmd.payload['reservation_id']}")
        operation_id = str(reservation.get("operation_id") or "")
        if operation_id:
            _refuse_terminal_unknown(_get_operation(cur, operation_id), "settlement")
        settled, detail, consumed = _settle_amount(
            cur, cmd.payload["reservation_id"], cmd.payload.get("outcome", "success"),
            cmd.payload.get("actual_cost"))
        code = ResultCode.APPLIED if settled else ResultCode.ALREADY_APPLIED
        data = {"reservation_id": cmd.payload["reservation_id"], "settled": settled, "consumed": consumed}
        return (code, detail, data,
                [("resources.settled", {"reservation_id": cmd.payload["reservation_id"], "settled": settled})], [])
    return transact(dsn, cmd, _fn)


def release_reservation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT * FROM reservations WHERE id = %s", (cmd.payload["reservation_id"],))
        res = cur.fetchone()
        if res is None:
            raise SettlementError(f"unknown reservation {cmd.payload['reservation_id']}")
        if res["state"] == "settled":
            raise SettlementError(f"reservation {res['id']} already settled")
        if res["state"] == "released":
            return (ResultCode.ALREADY_APPLIED, "already released", {"reservation_id": res["id"]}, [], [])
        proof = None
        if res["state"] == "uncertain" or "never_sent_proof" in cmd.payload:
            generation = None
            operation_id = str(res.get("operation_id") or "")
            if operation_id:
                cur.execute(
                    "SELECT id, launcher_id, payload FROM operations WHERE id = %s",
                    (operation_id,))
                operation = cur.fetchone()
                if operation is None:
                    raise MissingEvidence(
                        f"reservation {res['id']} has no operation for never-sent proof")
                _refuse_terminal_unknown(operation, "release")
                try:
                    generation = _require_generation(
                        dict(operation.get("payload") or {}).get("_dispatch_generation"),
                        "operation dispatch generation")
                except SettlementError as exc:
                    raise MissingEvidence(str(exc)) from exc
                proof = _never_sent_proof(cmd.payload, str(operation_id), generation,
                                          operation.get("launcher_id"))
            else:
                proof = _never_sent_proof(cmd.payload, str(res["id"]), generation)
        cur.execute(
            "UPDATE allocations SET reserved = reserved - %s WHERE id = %s",
            (int(res["amount"]), res["allocation_id"]),
        )
        cur.execute("UPDATE reservations SET state = 'released' WHERE id = %s", (res["id"],))
        evidence = {"reservation_id": res["id"], "never_sent_proof": proof}
        return (ResultCode.APPLIED, "released", {"reservation_id": res["id"]},
                [("resources.released", evidence)], [])
    return transact(dsn, cmd, _fn)


def _get_attempt(cur, attempt_id: str) -> dict:
    cur.execute("SELECT * FROM attempts WHERE id = %s", (attempt_id,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown attempt {attempt_id}")
    return row


def _check_owner(cur, attempt: dict, generation: Any) -> None:
    if generation is not None and int(generation) != int(attempt["ownership_generation"]):
        raise StaleRevision(
            f"attempt {attempt['id']} owned by generation {attempt['ownership_generation']}, not {generation}")


def _check_grant(control: dict, supplied: dict, stored: dict) -> None:
    current = control.get("authority_version")
    if isinstance(current, bool) or not isinstance(current, int) or current <= 0:
        raise Unauthorized("authority version is not a positive integer")
    pinned = stored.get("_authority_version")
    if isinstance(pinned, bool) or not isinstance(pinned, int):
        raise Unauthorized("operation has no immutable grant binding")
    if pinned != current:
        raise Unauthorized(
            f"operation prepared under authority v{pinned}, current v{current}")
    supplied_version = supplied.get("grant_version")
    if supplied_version is not None and (
            isinstance(supplied_version, bool)
            or not isinstance(supplied_version, int)
            or supplied_version != current):
        raise Unauthorized("stale dispatch grant")


def _check_release(cur, attempt_id: str) -> None:
    cur.execute("SELECT q.version_id, q.reason FROM attempt_capability_pins p"
                " JOIN quarantine_registry q ON q.version_id = p.version_id"
                " WHERE p.attempt_id = %s ORDER BY q.version_id LIMIT 1", (attempt_id,))
    hit = cur.fetchone()
    if hit is not None:
        raise Unauthorized(
            f"attempt pinned to quarantined capability {hit['version_id']}: {hit['reason']}")


def _admission_checks(cur, control, op, ownership_generation: Any, grant_version: Any) -> None:
    if bool(control.get("dispatch_paused", False)):
        raise SettlementError(
            f"dispatch paused for {control.get('paused_reason') or 'recovery'}: {op['id']} refused")
    _check_grant(control, {"grant_version": grant_version}, dict(op["payload"] or {}))
    if op["attempt_id"] is not None:
        attempt = _attempt_allocation(cur, op["attempt_id"], op.get("allocation_id"))
        _check_owner(cur, attempt, ownership_generation
                     if ownership_generation is not None else attempt["ownership_generation"])
        if attempt["lifecycle"] not in ("running", "suspended"):
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}")
        cur.execute("SELECT disposition, revision FROM investigations WHERE id = %s",
                    (attempt["investigation_id"],))
        inv = cur.fetchone()
        if inv is None:
            raise SettlementError(f"unknown investigation {attempt['investigation_id']}")
        if inv["disposition"] in ("withdrawn", "fulfilled"):
            raise SettlementError(
                f"investigation {attempt['investigation_id']} is {inv['disposition']}")
        if int(attempt["investigation_revision"]) != int(inv["revision"]):
            raise StaleRevision(
                f"attempt {attempt['id']} revision {attempt['investigation_revision']} !="
                f" current {inv['revision']}")
        _check_release(cur, op["attempt_id"])


def _acquire_work(cur, *, investigation_id: str, attempt_id: str,
                  allocation_id=None, composition: str = "", model: str = "",
                  env: str = "", deadline=None, owner: str = "",
                  kind: str = "task") -> dict:
    cur.execute("SELECT * FROM investigations WHERE id = %s", (investigation_id,))
    inv = cur.fetchone()
    if inv is None:
        raise SettlementError(f"unknown investigation {investigation_id}")
    if inv["disposition"] in ("withdrawn", "fulfilled"):
        raise SettlementError(f"investigation {inv['id']} is {inv['disposition']}")
    if allocation_id is not None:
        alloc = _get_alloc(cur, allocation_id)
        if int(alloc["occupancy"]) >= int(alloc["max_occupancy"]):
            raise InsufficientResources(f"allocation {allocation_id} occupancy exhausted")
        if str(alloc.get("owner_scope") or "") == SUPERVISION_SCOPE \
                and kind != "recovery":
            raise InsufficientResources(
                f"allocation {allocation_id} is protected supervision capacity")
        cur.execute("UPDATE allocations SET occupancy = occupancy + 1 WHERE id = %s",
                    (allocation_id,))
    cur.execute("SELECT COALESCE(MAX(ownership_generation), 0) AS g FROM attempts WHERE investigation_id = %s",
                (inv["id"],))
    generation = int(cur.fetchone()["g"]) + 1
    cur.execute(
        "INSERT INTO attempts (id, investigation_id, investigation_revision, allocation_id,"
        " ownership_generation, composition, model, env, lifecycle, deadline, owner)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'running', %s, %s)",
        (attempt_id, inv["id"], int(inv["revision"]), allocation_id, generation,
         composition, model, env, deadline, owner),
    )
    return {"attempt_id": attempt_id, "ownership_generation": generation,
            "investigation_revision": int(inv["revision"])}


def acquire_work(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        acquired = _acquire_work(
            cur, investigation_id=p["investigation_id"], attempt_id=p["attempt_id"],
            allocation_id=p.get("allocation_id"), composition=p.get("composition", ""),
            model=p.get("model", ""), env=p.get("env", ""),
            deadline=p.get("deadline"), owner=p.get("owner", ""),
            kind=p.get("kind", "task"))
        return (ResultCode.APPLIED,
                f"attempt {acquired['attempt_id']} acquired"
                f" at generation {acquired['ownership_generation']}",
                acquired,
                [("work.acquired", {"attempt_id": acquired["attempt_id"],
                                   "ownership_generation": acquired["ownership_generation"]})],
                [])
    return transact(dsn, cmd, _fn)


def submit_observation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        attempt = _get_attempt(cur, cmd.payload["attempt_id"])
        cur.execute("INSERT INTO attempt_observations (attempt_id, content) VALUES (%s, %s) RETURNING id",
                    (attempt["id"], _j(cmd.payload.get("content", {}))))
        oid = cur.fetchone()["id"]
        return (ResultCode.APPLIED, f"observation {oid} recorded",
                {"attempt_id": attempt["id"], "observation_id": oid},
                [("work.observed", {"attempt_id": attempt["id"], "observation_id": oid})], [])
    return transact(dsn, cmd, _fn)


def install_continuation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        attempt = _get_attempt(cur, p["attempt_id"])
        if attempt["lifecycle"] in _TERMINAL_ATTEMPT:
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}")
        _check_owner(cur, attempt, p.get("ownership_generation"))
        cur.execute("UPDATE attempts SET continuation_ref = %s, updated_at = now() WHERE id = %s",
                    (p["continuation_ref"], attempt["id"]))
        return (ResultCode.APPLIED, "continuation installed",
                {"attempt_id": attempt["id"], "continuation_ref": p["continuation_ref"]},
                [("work.continued", {"attempt_id": attempt["id"]})], [])
    return transact(dsn, cmd, _fn)


def _end_attempt(cur, attempt: dict, lifecycle: str) -> None:
    if attempt["lifecycle"] in _TERMINAL_ATTEMPT:
        raise SettlementError(f"attempt {attempt['id']} already {attempt['lifecycle']}")
    cur.execute("UPDATE attempts SET lifecycle = %s, updated_at = now() WHERE id = %s", (lifecycle, attempt["id"]))
    if attempt["allocation_id"] is not None:
        cur.execute("UPDATE allocations SET occupancy = GREATEST(occupancy - 1, 0) WHERE id = %s",
                    (attempt["allocation_id"],))


def complete_attempt(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        attempt = _get_attempt(cur, p["attempt_id"])
        _check_owner(cur, attempt, p.get("ownership_generation"))
        outcome = p.get("outcome", "completed")
        if outcome not in ("completed", "failed", "cancelled"):
            raise SettlementError(f"unknown attempt outcome {outcome}")
        if outcome == "completed":
            cur.execute(
                "SELECT id, dispatch_state, reconcile_state FROM operations"
                " WHERE attempt_id = %s AND (dispatch_state NOT IN"
                " ('observed', 'reconciled', 'cancelled') OR reconcile_state IN"
                " ('conflict', 'unresolved')) LIMIT 1",
                (attempt["id"],),
            )
            pending = cur.fetchone()
            if pending is not None:
                raise MissingEvidence(
                    f"attempt {attempt['id']} has unresolved operation {pending['id']}")
        _end_attempt(cur, attempt, outcome)
        return (ResultCode.APPLIED, f"attempt {attempt['id']} {outcome}",
                {"attempt_id": attempt["id"], "lifecycle": outcome},
                [(f"work.{outcome}", {"attempt_id": attempt["id"]})], [])
    return transact(dsn, cmd, _fn)


def suspend_attempt(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        attempt = _get_attempt(cur, cmd.payload["attempt_id"])
        _check_owner(cur, attempt, cmd.payload.get("ownership_generation"))
        if attempt["lifecycle"] != "running":
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}, not running")
        cur.execute("UPDATE attempts SET lifecycle = 'suspended', updated_at = now() WHERE id = %s", (attempt["id"],))
        return (ResultCode.APPLIED, "suspended", {"attempt_id": attempt["id"]},
                [("work.suspended", {"attempt_id": attempt["id"]})], [])
    return transact(dsn, cmd, _fn)


def resume_attempt(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        attempt = _get_attempt(cur, cmd.payload["attempt_id"])
        _check_owner(cur, attempt, cmd.payload.get("ownership_generation"))
        if attempt["lifecycle"] != "suspended":
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}, not suspended")
        cur.execute("UPDATE attempts SET lifecycle = 'running', updated_at = now() WHERE id = %s", (attempt["id"],))
        return (ResultCode.APPLIED, "resumed", {"attempt_id": attempt["id"]},
                [("work.resumed", {"attempt_id": attempt["id"]})], [])
    return transact(dsn, cmd, _fn)


def _fulfillment_target(cur, cmd: Command) -> tuple[dict, dict]:
    p = cmd.payload
    cur.execute("SELECT * FROM investigations WHERE id = %s", (p.get("investigation_id"),))
    inv = cur.fetchone()
    if inv is None:
        raise SettlementError(f"unknown investigation {p.get('investigation_id')}")
    if cmd.expected_revision is not None and int(cmd.expected_revision) != int(inv["revision"]):
        raise StaleRevision(f"expected revision {cmd.expected_revision}, current {inv['revision']}")
    if inv["disposition"] == "withdrawn":
        raise SettlementError(f"investigation {inv['id']} is withdrawn")
    if inv["disposition"] == "fulfilled" and inv["fulfilled_revision"] == inv["revision"]:
        raise SettlementError(f"investigation {inv['id']} revision {inv['revision']} already fulfilled")
    return inv, p


def _check_obligation_witnesses(dsn: str, cur, control, inv: dict, attempt: dict,
                               artifacts_root: str | None = None) -> None:
    from . import evidence as _evidence

    wanted = dict(inv["obligations"] or {})
    epoch = int(control["evidence_epoch"])
    for name, spec in wanted.items():
        if not isinstance(spec, dict) or set(spec) not in ({"success"}, {"claim"}):
            raise MissingEvidence(
                f"obligation {name!r} has no discharge witness:"
                " use {\"success\": operation_id} or {\"claim\": claim_id}")
        if "success" in spec:
            cur.execute("SELECT attempt_id, dispatch_state, reconcile_state FROM operations WHERE id = %s",
                        (spec["success"],))
            op = cur.fetchone()
            if op is None:
                raise MissingEvidence(f"obligation {name!r}: unknown operation {spec['success']!r}")
            if op["attempt_id"] != attempt["id"]:
                raise MissingEvidence(
                    f"obligation {name!r}: operation {spec['success']!r} is not this attempt's work")
            cur.execute("SELECT 1 FROM receipts WHERE operation_id = %s AND outcome = 'success'",
                        (spec["success"],))
            if cur.fetchone() is None:
                raise MissingEvidence(
                    f"obligation {name!r}: operation {spec['success']!r} never succeeded")
            if op["reconcile_state"] in ("conflict", "unresolved"):
                raise MissingEvidence(
                    f"obligation {name!r}: operation {spec['success']!r} is {op['reconcile_state']}")
            if op["dispatch_state"] not in ("observed", "reconciled"):
                raise MissingEvidence(
                    f"obligation {name!r}: operation {spec['success']!r} has no observed receipt")
        else:
            _evidence.check_use_verified(dsn, spec["claim"], epoch, artifacts_root)


def attempts_with_continuations(dsn: str) -> list[dict]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, ownership_generation FROM attempts"
                        " WHERE lifecycle IN ('running', 'suspended')"
                        " AND continuation_ref IS NOT NULL ORDER BY id")
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def fulfill_investigation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        inv, p = _fulfillment_target(cur, cmd)
        if not p.get("attempt_id"):
            raise SettlementError("fulfillment needs a completed attempt; use the override operation to bypass it")
        attempt = _get_attempt(cur, p["attempt_id"])
        if attempt["investigation_id"] != inv["id"]:
            raise SettlementError(
                f"attempt {attempt['id']} belongs to {attempt['investigation_id']}, not {inv['id']}")
        if p.get("ownership_generation") is None:
            raise SettlementError("fulfillment needs the attempt ownership generation")
        _check_owner(cur, attempt, p["ownership_generation"])
        if p.get("revision") is None:
            raise SettlementError("fulfillment needs the current investigation revision")
        if int(p["revision"]) != int(inv["revision"]):
            raise StaleRevision(f"fulfillment revision {p['revision']} != current {inv['revision']}")
        if p.get("authority_version") is None:
            raise SettlementError("fulfillment needs the current completion authority version")
        if int(p["authority_version"]) != int(control["authority_version"]):
            raise Unauthorized("stale completion authority")
        if p.get("evidence_epoch") is None:
            raise SettlementError("fulfillment needs the current evidence epoch")
        if int(p["evidence_epoch"]) != int(control["evidence_epoch"]):
            raise MissingEvidence(
                f"evidence epoch {p['evidence_epoch']} != current {control['evidence_epoch']}")
        if attempt["lifecycle"] != "completed":
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}, not completed")
        if int(attempt["investigation_revision"]) != int(inv["revision"]):
            raise StaleRevision(f"attempt revision {attempt['investigation_revision']} != {inv['revision']}")
        if not isinstance(p.get("obligations"), dict):
            raise SettlementError("fulfillment needs the current completion obligations")
        if dict(p["obligations"]) != dict(inv["obligations"] or {}):
            raise StaleRevision("completion obligations changed since this fulfillment was prepared")
        _check_obligation_witnesses(dsn, cur, control, inv, attempt,
                                   p.get("artifacts_root"))
        _check_release(cur, attempt["id"])
        cur.execute(
            "UPDATE investigations SET disposition = 'fulfilled', fulfilled_revision = %s,"
            " updated_at = now() WHERE id = %s",
            (int(inv["revision"]), inv["id"]),
        )
        return (ResultCode.APPLIED, f"investigation {inv['id']} r{inv['revision']} fulfilled",
                {"investigation_id": inv["id"], "revision": int(inv["revision"]),
                 "attempt_id": attempt["id"]},
                [("commitment.fulfilled", {"investigation_id": inv["id"], "revision": int(inv["revision"]),
                                           "attempt_id": attempt["id"]})], [])
    return transact(dsn, cmd, _fn)


def fulfill_investigation_override(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        inv, p = _fulfillment_target(cur, cmd)
        if p.get("revision") is None:
            raise SettlementError("override needs the current investigation revision")
        if int(p["revision"]) != int(inv["revision"]):
            raise StaleRevision(f"override revision {p['revision']} != current {inv['revision']}")
        operator = p.get("operator", "")
        reason = p.get("override_reason", "")
        if not (isinstance(operator, str) and operator.strip()):
            raise SettlementError("override needs an attributable operator")
        if not (isinstance(reason, str) and reason.strip()):
            raise SettlementError("override needs an explicit reason")
        cur.execute(
            "UPDATE investigations SET disposition = 'fulfilled', fulfilled_revision = %s,"
            " updated_at = now() WHERE id = %s",
            (int(inv["revision"]), inv["id"]),
        )
        return (ResultCode.APPLIED, f"investigation {inv['id']} r{inv['revision']} fulfilled by override",
                {"investigation_id": inv["id"], "revision": int(inv["revision"]),
                 "override": True, "operator": operator},
                [("commitment.fulfilled_override", {"investigation_id": inv["id"],
                                                   "revision": int(inv["revision"]),
                                                   "operator": operator, "reason": reason})], [])
    return transact(dsn, cmd, _fn)


def _get_operation(cur, operation_id: str) -> dict:
    cur.execute("SELECT * FROM operations WHERE id = %s", (operation_id,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown operation {operation_id}")
    return row


def _study_root_for_allocation(cur, allocation_id: str | None) -> str:
    if not allocation_id:
        return ""
    cur.execute(
        "WITH RECURSIVE allocation_lineage (id, parent_id, path) AS ("
        " SELECT id, parent_id, ARRAY[id] FROM allocations WHERE id = %s"
        # A study root is an ancestor, so the walk climbs `line.parent_id`.
        # The path runs from the operation's own allocation upward, so the
        # authority nearest the operation is the one at the *lowest* position
        # in it. Carrying the path also cuts a revisit: `UNION` cannot, because
        # a path differs on every pass, so the tuples never dedupe and a cycle
        # runs to the statement timeout. The walk is still linear, because
        # `parent_id` is a single column and every allocation has exactly one
        # path to its root.
        " UNION ALL SELECT a.id, a.parent_id, line.path || a.id FROM allocations a"
        " JOIN allocation_lineage line ON line.parent_id = a.id"
        " WHERE NOT a.id = ANY(line.path))"
        " SELECT study_authority.study_root,"
        " array_position(allocation_lineage.path, study_authority.allocation_id)"
        " AS depth FROM study_authority"
        " JOIN allocation_lineage ON allocation_lineage.id = study_authority.allocation_id",
        (allocation_id,))
    # A plain cursor yields tuples, and a tuple has no ``get``. Reading a
    # fixed column pair keeps the one-cursor caller and the `dict_row` caller
    # of this function agreeing, which is what keeps study_root off every
    # persisted operation when one of them guesses wrong.
    found = [(row["study_root"] if hasattr(row, "get") else row[0],
              int(row["depth"]) if hasattr(row, "get") else int(row[1]))
             for row in cur.fetchall()]
    if not found:
        return ""
    nearest = min(depth for _, depth in found)
    owners = {str(root) for root, depth in found if depth == nearest}
    if len(owners) > 1:
        # Two study roots on the one allocation. `study_authority` keys on
        # `study_root` and constrains nothing on `allocation_id`, so this is
        # reachable, and no ordering separates two roots on the same node.
        # Binding either leaves the other's ceilings unchecked for every
        # operation admitted below that allocation, so the walk refuses
        # rather than picks the row it happened to read first.
        raise ConflictPayload(
            "allocation %s is claimed by studies %s; no study owns it"
            % (allocation_id, sorted(owners)))
    return owners.pop()


def _bind_study_allocation(cur, allocation_id: str | None, stored: dict) -> None:
    study_root = _study_root_for_allocation(cur, allocation_id)
    if not study_root:
        return
    existing = stored.get("study_root")
    if existing is not None and existing != study_root:
        raise ConflictPayload("operation is bound to another study root")
    stored["study_root"] = study_root


def _require_study_operation_binding(cur, operation_id: str) -> None:
    cur.execute("SELECT allocation_id, payload FROM operations WHERE id = %s", (operation_id,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown operation {operation_id}")
    study_root = _study_root_for_allocation(cur, row.get("allocation_id"))
    if study_root and dict(row.get("payload") or {}).get("study_root") != study_root:
        raise MissingAuthority(
            f"operation {operation_id} is not bound to study {study_root}")


def _check_operation_replay(existing: dict[str, Any], *, digest: str,
                            attempt_id: str | None, allocation_id: str | None,
                            reservation_id: str | None, exposure: int,
                            execution_version: str, authority_version: int) -> None:
    stored = dict(existing.get("payload") or {})
    immutable = (
        existing.get("payload_digest") == digest
        and existing.get("attempt_id") == attempt_id
        and existing.get("allocation_id") == allocation_id
        and existing.get("reservation_id") == reservation_id
        and str(existing.get("execution_version") or "") == execution_version
        and int(existing.get("reservation_amount") or 0) == int(exposure)
        and stored.get("_authority_version") == authority_version
    )
    if not immutable:
        raise ConflictPayload(
            f"operation {existing['id']} replay changed immutable authority metadata")


def _counters_spent_by(stored: dict) -> frozenset[str]:
    """The counters one operation would move if it were admitted.

    A ceiling is a bound on a resource, so it is checked against the
    operations that actually draw on that resource. Counting every
    ceiling against every operation makes a ceiling of zero a refusal of
    all work: `max_model_calls: 0` is a statement that no model is
    called, and a `domain-command` draws on no model, so it has to be
    admitted. Refusing it there turned 42 admitted operations into 42
    refusals, and on a summary line a refused study is
    indistinguishable from one that made no model calls at all.
    """
    effect = (stored or {}).get("effect")
    spent = {"operations"}
    if effect == "model-inference":
        # A ceiling is a bound on a named resource, so it is charged only to
        # the operations that draw on it. `construction_calls` was charged to
        # every model call, which made it a second spelling of `model_calls`:
        # a phase that merely asks a model a question spent the construction
        # ceiling, and a study that ran its development phase first had no
        # authority left to construct anything. Charge and credit had to
        # become one predicate, so both read `resource` here.
        spent.add("model_calls")
        if (stored or {}).get("resource") == "construction_calls":
            spent.add("construction_calls")
    elif effect == "sandbox-exec":
        spent |= {"sandbox_calls", "execution_units"}
    kind = (stored or {}).get("kind")
    if isinstance(kind, str) and kind:
        spent.add(kind)
    return frozenset(spent)


def _check_study_ceilings(cur, study_root: Any, stored: dict) -> None:
    """Refuse a send the study's own frozen ceiling forbids.

    `admit_study_operation` read this column, but its only caller is
    `authority.admit_study_call` and no live dispatch reaches it. Every send
    goes through `prepare_operation`, which bound the study root and then
    never asked, so a study could authorize one send and dispatch any number.
    The check lives where the operation is actually admitted.

    It runs before the reservation is taken, so an over-ceiling send spends
    no exposure.
    """
    if not study_root:
        return
    cur.execute("SELECT ceilings FROM study_authority WHERE study_root = %s",
                (str(study_root),))
    row = cur.fetchone()
    if row is None:
        return
    ceilings = dict(row["ceilings"] or {})
    if not ceilings:
        return
    used = _count_study_operations(cur, str(study_root), stored)
    spent = _counters_spent_by(stored)
    for name, raw_limit in ceilings.items():
        if _ceiling_counter(name) not in spent:
            continue
        limit = _ceiling_value(raw_limit)
        counter = _ceiling_counter(name)
        if counter is None:
            # A declared-only ceiling names a quantity this layer records and
            # does not count, such as a wall deadline or a query budget. It is
            # authorized deliberately, so refusing it here would break every
            # study that declares one. It is not enforced, and saying so is
            # better than raising on a name the study may legally declare.
            continue
        if limit is None:
            raise SettlementError(f"unsupported study ceiling {name}")
        if used.get(counter, 0) + 1 > limit:
            raise InsufficientResources(
                f"study {study_root} ceiling {name}={limit} reached at "
                f"{used.get(counter, 0)}")


def _count_study_operations(cur, study_root: str, stored: dict) -> dict:
    """How many operations of each ceiling kind this study already has."""
    cur.execute("SELECT allocation_id FROM study_authority WHERE study_root = %s",
                (study_root,))
    study = cur.fetchone()
    if study is None:
        return {}
    return _study_operation_counts(cur, str(study["allocation_id"]))


def _prepare_operation(cur, authority_version: int, *, operation_id: str,
                       attempt_id=None, allocation_id=None, reservation_id=None,
                       exposure: int = 0, operation=None,
                       execution_version: str = "") -> dict:
    body = operation or {}
    _reject_terminal_intent(body)
    # Checked before the reservation is taken, so a refused value spends no
    # exposure, and before the replay read below, so the value is the same one
    # a replay is compared against.
    execution_version = _require_execution_version(execution_version)
    digest = payload_digest(body)
    cur.execute(
        "SELECT o.*, r.amount AS reservation_amount FROM operations o"
        " LEFT JOIN reservations r ON r.id = o.reservation_id WHERE o.id = %s",
        (operation_id,),
    )
    existing = cur.fetchone()
    if existing is not None:
        _check_operation_replay(
            existing, digest=digest, attempt_id=attempt_id,
            allocation_id=allocation_id, reservation_id=reservation_id,
            exposure=int(exposure), execution_version=execution_version,
            authority_version=int(authority_version))
        return {"operation_id": operation_id, "prepared": False}
    if attempt_id is not None:
        _attempt_allocation(cur, attempt_id, allocation_id)
    if int(exposure) > 0:
        if not reservation_id or not allocation_id:
            raise SettlementError("exposure needs reservation_id and allocation_id")
        _take_reservation(cur, allocation_id, reservation_id, int(exposure), operation_id)
    stored = dict(body) if isinstance(body, dict) else {}
    _bind_study_allocation(cur, allocation_id, stored)
    _check_study_ceilings(cur, stored.get("study_root"), stored)
    stored["_authority_version"] = int(authority_version)
    cur.execute(
        "INSERT INTO operations (id, attempt_id, allocation_id, reservation_id, payload_digest,"
        " payload, dispatch_state, execution_version)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'prepared', %s)",
        (operation_id, attempt_id, allocation_id, reservation_id, digest, _j(stored),
         execution_version),
    )
    return {"operation_id": operation_id, "reservation_id": reservation_id,
            "prepared": True}


def prepare_operation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        prepared = _prepare_operation(
            cur, int(control["authority_version"]),
            operation_id=p["operation_id"], attempt_id=p.get("attempt_id"),
            allocation_id=p.get("allocation_id"),
            reservation_id=p.get("reservation_id"),
            exposure=int(p.get("exposure", 0)), operation=p.get("operation", {}),
            execution_version=p.get("execution_version", ""))
        if not prepared["prepared"]:
            return (ResultCode.ALREADY_APPLIED, "operation already prepared",
                    {"operation_id": p["operation_id"]}, [], [])
        return (ResultCode.APPLIED, f"operation {p['operation_id']} prepared",
                {"operation_id": p["operation_id"],
                 "reservation_id": prepared["reservation_id"]},
                [("operation.prepared", {"operation_id": p["operation_id"]})], [])
    return transact(dsn, cmd, _fn)


def _empty_study_counts() -> dict[str, int]:
    """A zeroed counter for every name `CEILING_COUNTERS` can resolve to.

    Building the shape from the table rather than from a hand-written literal
    is what makes the two agree. A hand-written five-key dict is how
    `calibration`, `development`, `repair` and `use` came to read zero: they
    were in `CEILING_COUNTERS`, so a study could declare them, and the walker
    never incremented them.
    """
    return {counter: 0 for counter in set(CEILING_COUNTERS.values())}


def _study_operation_counts(cur, allocation_id: str) -> dict[str, int]:
    cur.execute(
        "WITH RECURSIVE study_allocs (id) AS ("
        " SELECT id FROM allocations WHERE id = %s"
        " UNION SELECT a.id FROM allocations a"
        " JOIN study_allocs s ON a.parent_id = s.id)"
        " SELECT id FROM study_allocs", (allocation_id,))
    allocation_ids = [row["id"] for row in cur.fetchall()]
    if not allocation_ids:
        return _empty_study_counts()
    cur.execute(
        "SELECT o.id, o.allocation_id, o.payload, COALESCE(r.amount, 0) AS exposure"
        " FROM operations o LEFT JOIN reservations r ON r.id = o.reservation_id"
        " WHERE o.allocation_id = ANY(%s) ORDER BY o.id", (allocation_ids,))
    rows = [dict(row) for row in cur.fetchall()]
    counts = _empty_study_counts()
    counts["operations"] = len(rows)
    for row in rows:
        payload = row.get("payload") or {}
        effect = payload.get("effect")
        if effect == "model-inference":
            counts["model_calls"] += 1
            if payload.get("resource") == "construction_calls":
                counts["construction_calls"] += 1
        elif effect == "sandbox-exec":
            counts["sandbox_calls"] += 1
            counts["execution_units"] += int(row.get("exposure") or 0)
        # The four study kinds, which are allocation-namespace counters rather
        # than effect counters. A study operation is admitted under the child
        # allocation `<parent>/<kind>/<operation>`, so the kind is one path
        # segment below the study's own allocation. The LIKE fallback counted
        # these by namespace and the walker could not, which is the
        # disagreement N-31 named; counting them here reconciles the two by
        # making one counter that reads both.
        kind = payload.get("kind")
        if kind in counts:
            counts[kind] += 1
    return counts


def _ceiling_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, dict):
        value = value.get("max", value.get("limit"))
        if isinstance(value, int) and not isinstance(value, bool):
            return int(value)
    return None


def admit_study_operation(
    dsn: str,
    cmd: Command,
) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        study_root = str(p["study_root"])
        kind = str(p["kind"])
        operation_id = str(p["operation_id"])
        child_id = str(p["allocation_id"])
        exposure = int(p["exposure"])
        # The same boundary rule `_prepare_operation` applies, on the second
        # site that writes the column. A check on one write site and not the
        # other is half a check.
        execution_version = _require_execution_version(
            p.get("execution_version", ""))
        body = dict(p["body"])
        _reject_terminal_intent(body)
        if (
                body.get("allocation_id") != child_id
                or body.get("study_root") != study_root
                or body.get("kind") != kind
                or body.get("budget_kind") != p.get("budget_kind")):
            raise ConflictPayload("study operation intent is not bound to its authority metadata")
        digest = payload_digest(body)
        cur.execute("SELECT * FROM study_authority WHERE study_root = %s FOR UPDATE",
                    (study_root,))
        study = cur.fetchone()
        if study is None:
            raise MissingEvidence(f"no authority for study {study_root}")
        parent_id = str(study["allocation_id"])
        if child_id != f"{parent_id}/{kind}/{operation_id}":
            raise ConflictPayload("study operation allocation is not bound to its study and kind")
        cur.execute(
            "SELECT o.*, r.amount AS reservation_amount FROM operations o"
            " LEFT JOIN reservations r ON r.id = o.reservation_id"
            " WHERE o.id = %s FOR UPDATE OF o", (operation_id,))
        existing = cur.fetchone()
        if existing is not None:
            _check_operation_replay(
                existing, digest=digest, attempt_id=p.get("attempt_id"),
                allocation_id=child_id, reservation_id=str(p["reservation_id"]),
                exposure=exposure, execution_version=execution_version,
                authority_version=int(control["authority_version"]))
            stored = dict(existing["payload"] or {})
            if existing["allocation_id"] != child_id \
                    or stored.get("study_root") != study_root \
                    or stored.get("kind") != kind:
                raise ConflictPayload(
                    f"operation {operation_id} is bound to another study, allocation, or kind")
            return (ResultCode.ALREADY_APPLIED, "study operation already admitted",
                    {"operation_id": operation_id, "allocation_id": child_id,
                     "exposure": exposure, "budget_kind": stored["budget_kind"],
                     "study_root": study_root, "kind": kind}, [], [])
        # One counter for both paths. This used to read a five-entry `counts`
        # dict and fall back to `WHERE allocation_id LIKE '<parent>/<counter>/%'`
        # for any counter the dict did not carry, which is N-31's two sources
        # of truth: the fallback counted one namespace, and the live path's
        # `_count_study_operations` counted the whole subtree. They disagreed,
        # and which one answered depended on which entry point ran. Now both
        # read `_study_operation_counts`, the walker behind
        # `_count_study_operations`, so there is one counter. The study row is
        # already locked above, so the allocation is passed rather than
        # re-read.
        used_counts = _study_operation_counts(cur, parent_id)
        ceilings = dict(study.get("ceilings") or {})
        spent = _counters_spent_by(body)
        for name, raw_limit in ceilings.items():
            if _ceiling_counter(name) not in spent:
                continue
            limit = _ceiling_value(raw_limit)
            counter = _ceiling_counter(name)
            if limit is None or counter is None:
                raise SettlementError(f"unsupported study ceiling {name}")
            used = used_counts.get(counter, 0)
            if used + 1 > limit:
                raise InsufficientResources(
                    f"study {study_root} ceiling {name}={limit} reached at {used}")
        cur.execute("SELECT * FROM allocations WHERE id = %s FOR UPDATE", (child_id,))
        child = cur.fetchone()
        if child is None:
            parent = _require_child_capacity(cur, parent_id, exposure)
            cur.execute(
                "INSERT INTO allocations (id, parent_id, domain, epoch, authorized, amount_scale,"
                " max_occupancy, owner_scope) VALUES (%s, %s, 'study', %s, %s, %s, %s, '')",
                (child_id, parent_id, int(parent["epoch"]), exposure,
                 int(parent["amount_scale"]), int(parent["max_occupancy"])),
            )
        elif int(child["authorized"]) != exposure or child["parent_id"] != parent_id:
            raise ConflictPayload(
                f"child {child_id} is already bound to another authority or exposure")
        if p.get("attempt_id") is not None:
            _attempt_allocation(cur, str(p["attempt_id"]), child_id)
        _bind_study_allocation(cur, child_id, body)
        reservation_id = str(p["reservation_id"])
        _take_reservation(cur, child_id, reservation_id, exposure, operation_id)
        stored_body = {**body, "_authority_version": int(control["authority_version"])}
        cur.execute(
            "INSERT INTO operations (id, attempt_id, allocation_id, reservation_id, payload_digest,"
            " payload, dispatch_state, execution_version) VALUES (%s, %s, %s, %s, %s, %s, 'prepared', %s)",
            (operation_id, p.get("attempt_id"), child_id, reservation_id, digest,
             _j(stored_body), execution_version),
        )
        return (ResultCode.APPLIED, f"study operation {operation_id} admitted",
                {"operation_id": operation_id, "allocation_id": child_id,
                 "exposure": exposure, "budget_kind": p["budget_kind"],
                 "study_root": study_root, "kind": kind},
                [("operation.prepared", {"operation_id": operation_id})], [])
    return transact(dsn, cmd, _fn)


def advance_dispatch(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        op = _get_operation(cur, p["operation_id"])
        launcher = p.get("launcher_id", op["launcher_id"])
        stored = dict(op["payload"] or {})
        if op["dispatch_state"] != "prepared":
            if op["launcher_id"] == launcher and op["dispatch_state"] == "dispatching":
                _admission_checks(cur, control, op, p.get("ownership_generation"), p.get("grant_version"))
                return (ResultCode.ALREADY_APPLIED, "already dispatching",
                        {"operation_id": op["id"], "admitted": False,
                         "dispatch_generation": int(stored.get("_dispatch_generation", 0)),
                         "admission_current": True}, [], [])
            raise SettlementError(f"operation {op['id']} is {op['dispatch_state']}, not prepared")
        _admission_checks(cur, control, op, p.get("ownership_generation"), p.get("grant_version"))
        generation = int(stored.get("_dispatch_generation", 0)) + 1
        stored.pop("_never_sent_proof", None)
        stored["_dispatch_generation"] = generation
        stored["_admitted_launcher"] = launcher
        cur.execute(
            "UPDATE operations SET dispatch_state = 'dispatching', launcher_id = %s,"
            " provider_id = %s, payload = %s, updated_at = now() WHERE id = %s",
            (launcher, p.get("provider_id", ""), _j(stored), op["id"]),
        )
        intent = {"operation_id": op["id"], "payload": stored, "launcher_id": launcher}
        return (ResultCode.APPLIED, f"operation {op['id']} dispatching",
                {"operation_id": op["id"], "admitted": True, "dispatch_generation": generation},
                [("operation.dispatching", {"operation_id": op["id"],
                                            "dispatch_generation": generation})],
                [("dispatch", intent, f"dispatch:{op['id']}")])
    return transact(dsn, cmd, _fn)


def receipt_actual_cost(payload: dict[str, Any]) -> int | None:
    explicit = payload.get("actual_cost")
    if explicit is not None:
        explicit = _require_nonnegative_int(explicit, "actual cost")
    content = payload.get("content") or {}
    if not isinstance(content, dict):
        raise SettlementError("receipt content must be an object")
    usage = content.get("usage")
    if usage is None:
        return explicit
    if not isinstance(usage, dict):
        if explicit is not None:
            raise SettlementError("actual cost conflicts with malformed usage")
        return None
    for token_name in ("input_tokens", "output_tokens"):
        token_count = usage.get(token_name)
        if token_count is not None and (
                isinstance(token_count, bool) or not isinstance(token_count, int)
                or token_count < 0):
            raise SettlementError("usage has malformed token counts")
    scale = usage.get("charge_scale")
    if scale is not None and (
            isinstance(scale, bool) or not isinstance(scale, int)
            or scale != CANONICAL_CHARGE_SCALE):
        if explicit is not None:
            raise SettlementError("actual cost conflicts with noncanonical charge scale")
        return None
    charge = usage.get("charge_units")
    if charge is not None and (
            isinstance(charge, bool) or not isinstance(charge, int) or charge < 0):
        if usage.get("billed") is True or explicit is not None:
            raise SettlementError("billed charge_units must be a non-negative integer")
        charge = None
    billed = usage.get("billed")
    if billed is True and charge is not None and (
            usage.get("input_tokens") is None or usage.get("output_tokens") is None):
        raise SettlementError("billed usage requires token counts")
    if billed is True and charge is None and explicit is not None:
        raise SettlementError("actual cost conflicts with unknown billed usage")
    if explicit is not None and charge is not None and explicit != charge:
        raise SettlementError("actual cost conflicts with usage charge_units")
    if explicit is not None and billed is False and explicit != 0:
        raise SettlementError("actual cost conflicts with unbilled usage")
    if explicit is not None:
        return explicit
    return charge if billed is True else None


def _receipt_metadata(op: dict[str, Any]) -> tuple[str, int | None, bool]:
    stored = dict(op.get("payload") or {})
    provenance = str(stored.get("_receipt_provenance", op.get("receipt_provenance", "")) or "")
    present = "_receipt_actual_cost" in stored
    cost = stored.get("_receipt_actual_cost") if present else None
    if cost is not None and (isinstance(cost, bool) or not isinstance(cost, int) or cost < 0):
        cost = None
    return provenance, cost, present


def _validate_receipt(op: dict[str, Any], payload: dict[str, Any]) -> None:
    identity = payload.get("receipt_identity")
    if not isinstance(identity, str) or not identity.strip():
        raise SettlementError("receipt identity must be a non-empty string")
    outcome = payload.get("outcome", "unknown")
    if not isinstance(outcome, str) or outcome not in _OUTCOMES:
        raise SettlementError(f"unknown receipt outcome {outcome!r}")
    if op.get("dispatch_state") == "prepared":
        raise SettlementError(f"operation {op['id']} was not dispatched")
    content = payload.get("content")
    if not isinstance(content, dict):
        raise SettlementError("receipt content must be an object")
    response_operation = content.get("operation_id")
    if response_operation is not None and response_operation != op["id"]:
        raise SettlementError(
            f"receipt operation identity {response_operation!r} does not match {op['id']!r}")
    provenance = payload.get("provenance")
    if not isinstance(provenance, str) or not provenance.strip():
        # Every outcome, not only a failure. A `success` receipt is the one a
        # reservation settles on, and it used to be the one free to name
        # nobody: nothing distinguished a receipt from the launcher that ran
        # the work from a receipt from a producer that never ran. N-302 is that
        # gap, and requiring the field is the whole of the admission half.
        raise SettlementError("receipt needs provenance")
    if outcome == "failure":
        # Two vocabularies, one rule. The first is a gateway's account of a
        # response it did not get. The second is a local launcher's account of
        # a process it ran, and it used to be unstateable: a LocalLauncher
        # receipt carries none of the first set, so when a checked program
        # genuinely failed, the one receipt that could have recorded it was
        # refused and the operation was left `dispatching` with no receipt at
        # all. The evidence requirement is unchanged - a failure is still
        # never admitted on a claim alone - it is only asking the producer
        # in vocabulary the producer can actually speak.
        #
        # `parse` is the launcher's account of how it reached a verdict and is
        # set on every path through `_interpret`; `returncode` is present on
        # every real execution; `spawn_error` is the one failure branch that
        # calls `_base` directly and therefore has neither of the others.
        data = content.get("data") if isinstance(content, dict) else None
        data = data if isinstance(data, dict) else {}
        if not any(value not in (None, "") for value in (
                content.get("response_operation_id"),
                content.get("response_class"),
                content.get("response_status"),
                content.get("response_digest"),
                content.get("error"),
                content.get("text"),
                content.get("response"),
                content.get("parse"),
                data.get("returncode"),
                data.get("spawn_error"))):
            raise SettlementError("failure receipt needs response evidence")
    effect = str((op.get("payload") or {}).get("effect", ""))
    if effect == "model-inference":
        if response_operation is None:
            raise SettlementError("model receipt needs the response operation identity")
        if outcome == "success" and (
                not isinstance(content.get("text"), str) or not content["text"].strip()):
            raise SettlementError("successful model receipt needs non-empty response text")
        if outcome == "unknown" and not content.get("error"):
            raise SettlementError("unknown model receipt needs error evidence")
    elif effect == "observation-adapter" and not content.get("adapter"):
        raise SettlementError("observation receipt needs its adapter")
    elif effect == "domain-command" and (
            not content.get("command") or not content.get("idempotency_key")):
        raise SettlementError("domain receipt needs command and idempotency identity")


def _mark_receipt_conflict(cur, operation_id: str, receipt_identity: str,
                           content_digest: str, content: dict[str, Any],
                           outcome: str, provenance: str,
                           actual_cost: int | None) -> None:
    cur.execute(
        "INSERT INTO receipt_conflicts (receipt_identity, operation_id, content_digest, content)"
        " VALUES (%s, %s, %s, %s)",
        (receipt_identity, operation_id, content_digest,
         _j({"receipt_content": content, "outcome": outcome,
             "provenance": provenance, "actual_cost": actual_cost})),
    )
    cur.execute(
        "UPDATE operations SET reconcile_state = 'conflict', updated_at = now()"
        " WHERE id = %s",
        (operation_id,),
    )


def admit_receipt(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        op = _get_operation(cur, p["operation_id"])
        _validate_receipt(op, p)
        content = p.get("content", {})
        digest = payload_digest(content)
        outcome = p.get("outcome", "unknown")
        provenance = str(p.get("provenance", "") or "")
        cost_error = None
        try:
            actual_cost = receipt_actual_cost(p)
        except SettlementError as exc:
            actual_cost = None
            cost_error = str(exc)
        cur.execute("SELECT * FROM receipts WHERE receipt_identity = %s", (p["receipt_identity"],))
        seen = cur.fetchone()
        if seen is not None:
            same_operation = seen["operation_id"] == op["id"]
            stored_provenance, stored_cost, stored_cost_present = _receipt_metadata(op)
            if same_operation and seen["content_digest"] == digest \
                    and seen["outcome"] == outcome \
                    and provenance == stored_provenance \
                    and actual_cost == (stored_cost if stored_cost_present else actual_cost):
                return (ResultCode.ALREADY_APPLIED, "duplicate receipt",
                        {"operation_id": op["id"], "settled": bool(op["settled"])}, [], [])
            _mark_receipt_conflict(cur, op["id"], p["receipt_identity"], digest,
                                   content, outcome, provenance, actual_cost)
            if not same_operation:
                cur.execute(
                    "UPDATE operations SET reconcile_state = 'conflict', updated_at = now()"
                    " WHERE id = %s",
                    (seen["operation_id"],),
                )
            return (ResultCode.APPLIED, "conflicting receipt preserved for reconciliation",
                    {"operation_id": op["id"], "conflict": True, "settled": bool(op["settled"])},
                    [("operation.receipt_conflict", {"operation_id": op["id"],
                                                     "receipt_identity": p["receipt_identity"]})], [])
        if op["reconcile_state"] == "conflict":
            _mark_receipt_conflict(cur, op["id"], p["receipt_identity"], digest,
                                   content, outcome, provenance, actual_cost)
            return (ResultCode.APPLIED, "conflicting receipt preserved for reconciliation",
                    {"operation_id": op["id"], "conflict": True, "settled": bool(op["settled"])},
                    [("operation.receipt_conflict", {"operation_id": op["id"],
                                                     "receipt_identity": p["receipt_identity"]})], [])
        cur.execute(
            "SELECT receipt_identity, outcome FROM receipts WHERE operation_id = %s"
            " ORDER BY created_at, receipt_identity FOR UPDATE",
            (op["id"],),
        )
        prior = cur.fetchall()
        resolves_unknown = (
            len(prior) == 1
            and prior[0]["outcome"] == "unknown"
            and outcome in ("success", "failure")
            and op["dispatch_state"] == "unresolved"
            and op["reconcile_state"] == "unresolved"
            and not bool(op["settled"])
            and _terminal_disposition(op) is None
        )
        # A second receipt on one operation is an additional observation
        # when it claims nothing terminal. `resolves_unknown` already
        # admits a decided receipt replacing a lone unknown, and it is
        # deliberately left exactly as it was: all seven conditions stay,
        # so a `success` and a `failure` on one operation remain
        # structurally impossible.
        #
        # This is narrower than it looks. coord02's step receipt carries
        # `outcome="unknown"` and claims no resolution, and the launcher
        # receipt that settled the operation has already run, so the
        # settled short-circuit below would have admitted it untouched -
        # the count guard was the only thing refusing it. No `resolves`
        # field is needed for N-30, and none is added: a declared
        # resolution target is the right design if several `unknown`s ever
        # need to be told apart, and it wants a migration with a unique
        # index so two receipts cannot claim one unknown. Until something
        # needs it, the count stays as the sound rule for resolving.
        additional_observation = (
            outcome not in _DECIDED_OUTCOMES
            and _terminal_disposition(op) is None
        )
        if prior and not (resolves_unknown or additional_observation):
            _mark_receipt_conflict(cur, op["id"], p["receipt_identity"], digest,
                                   content, outcome, provenance, actual_cost)
            return (ResultCode.APPLIED, "conflicting receipt preserved for reconciliation",
                    {"operation_id": op["id"], "conflict": True, "settled": bool(op["settled"])},
                    [("operation.receipt_conflict", {"operation_id": op["id"],
                                                     "receipt_identity": p["receipt_identity"]})], [])
        # Without this the insert below would fall through to the state
        # rewrite and DEMOTE a decided operation to `unresolved`, because
        # an unknown sets `state = "unresolved"`. That is worse than the
        # hang this change fixes: a receipt that reports nothing would be
        # able to un-decide a settlement.
        if (prior and outcome not in _DECIDED_OUTCOMES
                and any(row["outcome"] in _DECIDED_OUTCOMES for row in prior)):
            cur.execute(
                "INSERT INTO receipts (receipt_identity, operation_id, content_digest,"
                " content, outcome, provenance)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (p["receipt_identity"], op["id"], digest, _j(content), outcome, provenance),
            )
            return (ResultCode.APPLIED,
                    "additional observation recorded, operation already decided",
                    {"operation_id": op["id"], "settled": bool(op["settled"])},
                    [("operation.receipted", {"operation_id": op["id"]})], [])
        cur.execute(
            "INSERT INTO receipts (receipt_identity, operation_id, content_digest,"
            " content, outcome, provenance)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (p["receipt_identity"], op["id"], digest, _j(content), outcome, provenance),
        )
        stored = dict(op["payload"] or {})
        stored["_receipt_provenance"] = provenance
        stored["_receipt_actual_cost"] = actual_cost
        if cost_error is not None and outcome in ("success", "failure") \
                and not bool(op["settled"]):
            cur.execute(
                "UPDATE operations SET dispatch_state = 'unresolved', reconcile_state = 'unresolved',"
                " receipt_provenance = %s, payload = %s, settled = FALSE, updated_at = now()"
                " WHERE id = %s",
                (provenance, _j(stored), op["id"]),
            )
            return (ResultCode.APPLIED,
                    f"receipt preserved, cost infeasible: {cost_error}",
                    {"operation_id": op["id"], "settled": False,
                     "settlement_refused": cost_error, "actual_cost": actual_cost},
                    [("operation.receipted", {"operation_id": op["id"], "outcome": outcome}),
                     ("operation.settlement_infeasible",
                      {"operation_id": op["id"], "reason": cost_error})], [])
        if bool(op["settled"]):
            cur.execute(
                "UPDATE operations SET receipt_provenance = %s, payload = %s, updated_at = now()"
                " WHERE id = %s",
                (provenance, _j(stored), op["id"]),
            )
            return (ResultCode.APPLIED, "receipt recorded, reservation already settled",
                    {"operation_id": op["id"], "settled": True},
                    [("operation.receipted", {"operation_id": op["id"]})], [])
        settled = False
        if op["reservation_id"] is not None and outcome in ("success", "failure"):
            try:
                if cost_error is not None:
                    raise SettlementError(cost_error)
                settled, _, _ = _settle_amount(
                    cur, op["reservation_id"], outcome, actual_cost)
            except SettlementError as exc:
                cur.execute(
                    "UPDATE operations SET dispatch_state = 'unresolved', reconcile_state = 'unresolved',"
                    " receipt_provenance = %s, payload = %s, settled = FALSE, updated_at = now()"
                    " WHERE id = %s",
                    (provenance, _j(stored), op["id"]),
                )
                return (ResultCode.APPLIED,
                        f"receipt preserved, settlement infeasible: {exc}",
                        {"operation_id": op["id"], "settled": False,
                         "settlement_refused": str(exc), "actual_cost": actual_cost},
                        [("operation.receipted", {"operation_id": op["id"], "outcome": outcome}),
                         ("operation.settlement_infeasible",
                          {"operation_id": op["id"], "reason": str(exc)})], [])
        elif op["reservation_id"] is not None:
            _settle_amount(cur, op["reservation_id"], "unknown")
        state = "observed" if outcome in ("success", "failure") else "unresolved"
        reconcile = "none" if outcome in ("success", "failure") else "unresolved"
        cur.execute(
            "UPDATE operations SET dispatch_state = %s, reconcile_state = %s, receipt_provenance = %s,"
            " payload = %s, settled = %s, updated_at = now() WHERE id = %s",
            (state, reconcile, provenance, _j(stored), settled or bool(op["settled"]), op["id"]),
        )
        return (ResultCode.APPLIED, f"receipt admitted, outcome {outcome}",
                {"operation_id": op["id"], "settled": settled or bool(op["settled"])},
                [("operation.receipted", {"operation_id": op["id"], "outcome": outcome})], [])
    return transact(dsn, cmd, _fn)


def request_cancellation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        op = _get_operation(cur, cmd.payload["operation_id"])
        _refuse_terminal_unknown(op, "cancellation")
        cur.execute(
            "UPDATE operations SET cancel_state = 'requested', updated_at = now() WHERE id = %s", (op["id"],))
        return (ResultCode.APPLIED, "cancellation requested", {"operation_id": op["id"]},
                [("operation.cancel_requested", {"operation_id": op["id"]})], [])
    return transact(dsn, cmd, _fn)


def confirm_cancellation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        op = _get_operation(cur, cmd.payload["operation_id"])
        _refuse_terminal_unknown(op, "cancellation")
        cur.execute("SELECT outcome FROM receipts WHERE operation_id = %s", (op["id"],))
        outcomes = [row["outcome"] for row in cur.fetchall()]
        if op["reconcile_state"] == "conflict":
            raise MissingEvidence(
                f"operation {op['id']} has a receipt conflict; cancellation cannot settle it")
        if any(outcome in ("success", "failure") for outcome in outcomes):
            cur.execute(
                "UPDATE operations SET cancel_state = 'confirmed', updated_at = now() WHERE id = %s",
                (op["id"],))
            return (ResultCode.APPLIED, "cancellation confirmed after receipt settlement",
                    {"operation_id": op["id"], "exposure": "settled"}, [], [])
        stored = dict(op.get("payload") or {})
        generation = int(stored.get("_dispatch_generation", 0))
        proof = None
        if "never_sent_proof" in cmd.payload:
            proof = _never_sent_proof(cmd.payload, str(op["id"]), generation,
                                      op.get("launcher_id"))
        if proof is None:
            if op["reservation_id"] is not None:
                cur.execute(
                    "UPDATE reservations SET state = 'uncertain' WHERE id = %s"
                    " AND state = 'reserved'",
                    (op["reservation_id"],),
                )
            cur.execute(
                "UPDATE operations SET cancel_state = 'confirmed', dispatch_state = 'unresolved',"
                " reconcile_state = 'unresolved', updated_at = now() WHERE id = %s",
                (op["id"],),
            )
            return (ResultCode.APPLIED, "cancellation retained unresolved exposure",
                    {"operation_id": op["id"], "exposure": "unresolved"},
                    [("operation.cancel_confirmed", {"operation_id": op["id"],
                                                     "exposure": "unresolved"})], [])
        if op["reservation_id"] is not None:
            cur.execute(
                "UPDATE allocations SET reserved = reserved - (SELECT amount FROM reservations"
                " WHERE id = %s) WHERE id = (SELECT allocation_id FROM reservations WHERE id = %s)",
                (op["reservation_id"], op["reservation_id"]),
            )
            cur.execute("UPDATE reservations SET state = 'released' WHERE id = %s", (op["reservation_id"],))
        cur.execute(
            "UPDATE operations SET cancel_state = 'confirmed', dispatch_state = 'cancelled',"
            " reconcile_state = 'reconciled', updated_at = now() WHERE id = %s",
            (op["id"],),
        )
        return (ResultCode.APPLIED, "cancellation confirmed with never-sent proof",
                {"operation_id": op["id"], "exposure": "released"},
                [("operation.cancel_confirmed", {
                    "operation_id": op["id"], "exposure": "released",
                    "never_sent_proof": proof})], [])
    return transact(dsn, cmd, _fn)


def operation_receipts(dsn: str, operation_id: str) -> list[dict]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_study_operation_binding(cur, operation_id)
            cur.execute("SELECT receipt_identity, outcome, content, provenance FROM receipts"
                        " WHERE operation_id = %s"
                        " ORDER BY created_at, receipt_identity", (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def operation_receipt_conflicts(dsn: str, operation_id: str) -> list[dict]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_study_operation_binding(cur, operation_id)
            cur.execute("SELECT receipt_identity, operation_id, content_digest, content"
                        " FROM receipt_conflicts WHERE operation_id = %s"
                        " ORDER BY id", (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def reset_dispatch(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT * FROM operations WHERE id = %s", (cmd.payload["operation_id"],))
        op = cur.fetchone()
        if op is None:
            raise SettlementError(f"unknown operation {cmd.payload['operation_id']}")
        if op["dispatch_state"] not in ("dispatching", "unresolved"):
            raise SettlementError(f"operation {op['id']} is {op['dispatch_state']}, not dispatching")
        if (op["cancel_state"] or "none") != "none":
            raise SettlementError(f"operation {op['id']} has cancel activity; explicit reconcile only")
        cur.execute("SELECT outcome FROM receipts WHERE operation_id = %s", (op["id"],))
        outcomes = {r["outcome"] for r in cur.fetchall()}
        if outcomes:
            raise SettlementError(f"operation {op['id']} already has receipts")
        stored = dict(op["payload"] or {})
        current_generation = _require_generation(
            stored.get("_dispatch_generation"), "operation dispatch generation")
        expected_generation = cmd.payload.get("expected_generation")
        if expected_generation is None:
            raise MissingEvidence("dispatch reset requires the current generation")
        expected_generation = _require_generation(expected_generation)
        if expected_generation != current_generation:
            raise StaleRevision(
                f"operation {op['id']} is at dispatch generation"
                f" {current_generation}, not {expected_generation}")
        proof = _never_sent_proof(cmd.payload, str(op["id"]), current_generation,
                                  op.get("launcher_id"))
        generation = current_generation + 1
        stored["_dispatch_generation"] = generation
        stored["_never_sent_proof"] = proof
        stored["_admitted_launcher"] = ""
        cur.execute("UPDATE operations SET dispatch_state = 'prepared', launcher_id = '',"
                    " payload = %s, updated_at = now() WHERE id = %s", (_j(stored), op["id"],))
        return (ResultCode.APPLIED, f"operation {op['id']} returned to prepared",
                {"operation_id": op["id"], "dispatch_generation": generation},
                [("dispatch.reset", {
                    "operation_id": op["id"], "dispatch_generation": generation,
                    "never_sent_proof": proof})], [])
    return transact(dsn, cmd, _fn)


def reconcile_operation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        op = _get_operation(cur, p["operation_id"])
        if op["dispatch_state"] in ("prepared", "cancelled"):
            raise SettlementError(
                f"operation {op['id']} is {op['dispatch_state']}, nothing dispatched to reconcile")
        resolution = p.get("resolution", "reconciled")
        if resolution not in ("reconciled", "unresolved", _TERMINAL_UNKNOWN):
            raise SettlementError(f"unknown resolution {resolution}")
        stored = dict(op.get("payload") or {})
        terminal = _terminal_disposition(op)
        if terminal is not None:
            if resolution == _TERMINAL_UNKNOWN:
                if op["reconcile_state"] == "conflict":
                    raise MissingEvidence(
                        f"operation {op['id']} has a receipt conflict; retain conflict state")
                return (ResultCode.ALREADY_APPLIED,
                        f"operation {op['id']} already {resolution}",
                        {"operation_id": op["id"], "resolution": resolution,
                         "terminal_disposition": terminal}, [], [])
            raise MissingEvidence(
                f"operation {op['id']} is {_TERMINAL_UNKNOWN}; resolution is final")
        if op["reconcile_state"] == "conflict":
            raise MissingEvidence(
                f"operation {op['id']} has a receipt conflict; retain conflict state")
        cur.execute(
            "SELECT receipt_identity, outcome, content FROM receipts WHERE operation_id = %s"
            " ORDER BY created_at, receipt_identity FOR UPDATE", (op["id"],))
        receipt_rows = [dict(row) for row in cur.fetchall()]
        receipts = [row["outcome"] for row in receipt_rows]
        decided = [outcome for outcome in receipts if outcome in ("success", "failure")]
        if resolution == _TERMINAL_UNKNOWN and (
                len(receipt_rows) != 1 or receipts[0] != "unknown"):
            raise MissingEvidence(
                f"operation {op['id']} needs one unknown receipt for terminal uncertainty")
        if resolution == _TERMINAL_UNKNOWN and not receipts:
            raise MissingEvidence(
                f"operation {op['id']} needs an unknown receipt for terminal uncertainty")
        if resolution == "unresolved" and decided:
            raise MissingEvidence(
                f"operation {op['id']} has a decided receipt; unresolved state would hide it")
        if receipts and not decided:
            if resolution == "reconciled":
                raise MissingEvidence(
                    f"operation {op['id']} has no decided receipt")
            if resolution == _TERMINAL_UNKNOWN:
                content = receipt_rows[0].get("content")
                if not isinstance(content, dict) or content.get("response_received") is not False:
                    raise MissingEvidence(
                        f"operation {op['id']} terminal unknown requires response_received=false")
                if op["dispatch_state"] != "unresolved" \
                        or op["reconcile_state"] != "unresolved" or bool(op["settled"]):
                    raise MissingEvidence(
                        f"operation {op['id']} is not unsettled unresolved exposure")
                reservation_id = op.get("reservation_id")
                if not reservation_id:
                    raise MissingEvidence(
                        f"operation {op['id']} terminal unknown has no reservation")
                cur.execute(
                    "SELECT id, allocation_id, amount, state FROM reservations"
                    " WHERE id = %s FOR UPDATE", (reservation_id,))
                reservation = cur.fetchone()
                if reservation is None or reservation["state"] != "uncertain":
                    state = "missing" if reservation is None else reservation["state"]
                    raise MissingEvidence(
                        f"reservation {reservation_id} is {state}, not uncertain")
                amount = int(reservation["amount"])
                cur.execute(
                    "SELECT reserved FROM allocations WHERE id = %s FOR UPDATE",
                    (reservation["allocation_id"],))
                allocation = cur.fetchone()
                if allocation is None or int(allocation["reserved"]) < amount:
                    raise MissingEvidence(
                        f"allocation {reservation['allocation_id']} does not retain reservation {amount}")
                disposition = {
                    "kind": _TERMINAL_UNKNOWN,
                    "receipt_identity": receipt_rows[0]["receipt_identity"],
                    "response_class": str(content.get("response_class") or "unknown"),
                    "response_received": False,
                    "reservation_amount": amount,
                }
                stored["_terminal_disposition"] = disposition
                cur.execute(
                    "UPDATE operations SET payload = %s, updated_at = now() WHERE id = %s",
                    (_j(stored), op["id"]))
                return (ResultCode.APPLIED,
                        f"operation {op['id']} recorded {resolution}",
                        {"operation_id": op["id"], "resolution": resolution,
                         "terminal_disposition": disposition},
                        [("operation.unresolved_terminal", {
                            "operation_id": op["id"],
                            "terminal_disposition": disposition})], [])
        elif not receipts:
            if op["dispatch_state"] not in ("dispatching", "sent", "unresolved"):
                raise MissingEvidence(
                    f"operation {op['id']} is {op['dispatch_state']} without a receipt")
            if resolution == "reconciled":
                if op["dispatch_state"] not in ("dispatching", "unresolved"):
                    raise MissingEvidence(
                        f"operation {op['id']} is {op['dispatch_state']}, not a never-sent state")
                if (op.get("cancel_state") or "none") != "none":
                    raise MissingEvidence(
                        f"operation {op['id']} has cancellation activity; explicit reconcile only")
                try:
                    generation = _require_generation(
                        stored.get("_dispatch_generation"),
                        "operation dispatch generation")
                except SettlementError as exc:
                    raise MissingEvidence(str(exc)) from exc
                proof = _never_sent_proof(p, str(op["id"]), generation,
                                          op.get("launcher_id"))
                reservation_id = op.get("reservation_id")
                if reservation_id is not None:
                    cur.execute(
                        "SELECT id, allocation_id, amount, state FROM reservations"
                        " WHERE id = %s FOR UPDATE", (reservation_id,))
                    reservation = cur.fetchone()
                    if reservation is not None and reservation["state"] in ("reserved", "uncertain"):
                        cur.execute(
                            "UPDATE allocations SET reserved = reserved - %s"
                            " WHERE id = %s",
                            (int(reservation["amount"]), reservation["allocation_id"]))
                        cur.execute(
                            "UPDATE reservations SET state = 'released' WHERE id = %s",
                            (reservation_id,))
                stored["_never_sent_proof"] = proof
                cur.execute(
                    "UPDATE operations SET dispatch_state = 'reconciled',"
                    " reconcile_state = 'reconciled', payload = %s, updated_at = now()"
                    " WHERE id = %s", (_j(stored), op["id"]))
                return (ResultCode.APPLIED, f"operation {op['id']} reconciled with never-sent proof",
                        {"operation_id": op["id"], "resolution": resolution,
                         "never_sent_proof": proof},
                        [("operation.reconciled", {
                            "operation_id": op["id"], "resolution": resolution,
                            "never_sent_proof": proof})], [])
        state = "reconciled" if resolution == "reconciled" else "unresolved"
        cur.execute(
            "UPDATE operations SET dispatch_state = %s, reconcile_state = %s, updated_at = now() WHERE id = %s",
            (state, resolution, op["id"]),
        )
        return (ResultCode.APPLIED, f"operation {op['id']} {resolution}",
                {"operation_id": op["id"], "resolution": resolution},
                [("operation.reconciled", {"operation_id": op["id"], "resolution": resolution})], [])
    return transact(dsn, cmd, _fn)


def scan_outbox(dsn: str, limit: int = 100) -> list[dict]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT workflow_identity, intent_kind, payload, delivered, created_epoch"
                " FROM outbox WHERE delivered = FALSE ORDER BY created_epoch, workflow_identity LIMIT %s",
                (limit,),
            )
            conn.commit()
            return [dict(r) for r in cur.fetchall()]


def claim_outbox(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT workflow_identity, intent_kind, payload, delivered FROM outbox WHERE workflow_identity = %s",
                    (cmd.payload["workflow_identity"],))
        row = cur.fetchone()
        if row is None:
            raise SettlementError(f"unknown outbox intent {cmd.payload['workflow_identity']}")
        return (ResultCode.APPLIED if not row["delivered"] else ResultCode.ALREADY_APPLIED,
                "intent claimed" if not row["delivered"] else "already delivered",
                {"workflow_identity": row["workflow_identity"], "intent_kind": row["intent_kind"],
                 "payload": dict(row["payload"] or {}), "delivered": bool(row["delivered"])}, [], [])
    return transact(dsn, cmd, _fn)


def record_delivery(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT delivered FROM outbox WHERE workflow_identity = %s",
                    (cmd.payload["workflow_identity"],))
        row = cur.fetchone()
        if row is None:
            raise SettlementError(f"unknown outbox intent {cmd.payload['workflow_identity']}")
        if row["delivered"]:
            return (ResultCode.ALREADY_APPLIED, "already delivered",
                    {"workflow_identity": cmd.payload["workflow_identity"]}, [], [])
        cur.execute(
            "UPDATE outbox SET delivered = TRUE, delivered_at = now() WHERE workflow_identity = %s",
            (cmd.payload["workflow_identity"],))
        return (ResultCode.APPLIED, "delivery recorded",
                {"workflow_identity": cmd.payload["workflow_identity"]},
                [("outbox.delivered", {"workflow_identity": cmd.payload["workflow_identity"]})], [])
    return transact(dsn, cmd, _fn)


def read_events(dsn: str, cursor_epoch: int = 0, cursor_ordinal: int = -1, limit: int = 100) -> dict:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT epoch, ordinal, kind, payload FROM domain_events"
                " WHERE (epoch > %s OR (epoch = %s AND ordinal > %s))"
                " ORDER BY epoch, ordinal LIMIT %s",
                (cursor_epoch, cursor_epoch, cursor_ordinal, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    if rows:
        cursor_epoch, cursor_ordinal = int(rows[-1]["epoch"]), int(rows[-1]["ordinal"])
    return {"events": rows, "cursor_epoch": cursor_epoch, "cursor_ordinal": cursor_ordinal}


def restart_reconciliation(dsn: str) -> dict:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, attempt_id, dispatch_state, launcher_id, execution_version, reconcile_state,"
                " cancel_state, settled, payload FROM operations"
                " WHERE dispatch_state IN ('dispatching', 'sent', 'unresolved')"
                " OR (cancel_state = 'requested')"
                " OR reconcile_state = 'conflict' ORDER BY id",
            )
            operations = [dict(row) for row in cur.fetchall()
                          if _terminal_disposition(dict(row)) is None
                          or row["reconcile_state"] == "conflict"]
            cur.execute(
                "SELECT id, investigation_id, investigation_revision, ownership_generation, lifecycle"
                " FROM attempts WHERE lifecycle NOT IN ('completed', 'failed', 'cancelled') ORDER BY id",
            )
            attempts = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT o.id, o.execution_version, o.payload FROM operations o"
                " WHERE o.execution_version <> '' AND o.dispatch_state IN"
                " ('dispatching', 'sent', 'unresolved') ORDER BY o.id",
            )
            versions = [dict(row) for row in cur.fetchall()
                        if _terminal_disposition(dict(row)) is None]
            conn.commit()
    return {"unfinished_operations": operations, "live_attempts": attempts, "execution_versions": versions}



def _bump_inflight_dispatch(cur) -> list[dict]:
    cur.execute("SELECT id, payload FROM operations"
                " WHERE dispatch_state IN ('dispatching', 'sent', 'unresolved') ORDER BY id")
    fenced = []
    for op in cur.fetchall():
        if _terminal_disposition(dict(op)) is not None:
            continue
        stored = dict(op["payload"] or {})
        generation = int(stored.get("_dispatch_generation", 0)) + 1
        stored["_dispatch_generation"] = generation
        cur.execute("UPDATE operations SET payload = %s, updated_at = now() WHERE id = %s",
                    (_j(stored), op["id"]))
        fenced.append({"id": op["id"], "dispatch_generation": generation})
    return fenced


def _live_continuations(cur) -> list[dict]:
    cur.execute("SELECT id, continuation_ref, ownership_generation, lifecycle FROM attempts"
                " WHERE lifecycle NOT IN ('completed', 'failed', 'cancelled') ORDER BY id")
    snapshot = []
    for attempt in cur.fetchall():
        ref = attempt["continuation_ref"] or ""
        snapshot.append({"id": attempt["id"], "lifecycle": attempt["lifecycle"],
                         "ownership_generation": int(attempt["ownership_generation"]),
                         "continuation_digest": hashlib.sha256(ref.encode()).hexdigest()})
    return snapshot


def checkpoint_barrier(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        pre_paused = bool(control.get("dispatch_paused", False))
        pre_reason = str(control.get("paused_reason") or "")
        cur.execute("UPDATE control SET admission_epoch = admission_epoch + 1 WHERE id = 1"
                    " RETURNING admission_epoch")
        epoch = int(cur.fetchone()["admission_epoch"])
        if pre_paused:
            reason = pre_reason
        else:
            cur.execute("UPDATE control SET dispatch_paused = TRUE,"
                        " paused_reason = 'checkpoint' WHERE id = 1")
            reason = "checkpoint"
        cur.execute("SELECT COUNT(*) AS n FROM command_journal")
        journal = int(cur.fetchone()["n"]) + 1
        cur.execute("SELECT workflow_identity FROM outbox WHERE delivered = FALSE"
                    " ORDER BY workflow_identity")
        pending = [r["workflow_identity"] for r in cur.fetchall()]
        fenced = _bump_inflight_dispatch(cur)
        continuations = _live_continuations(cur)
        data = {"barrier_epoch": epoch, "journal_count": journal,
                "event_epoch": int(control["event_epoch"]) + 1,
                "outbox_pending": pending, "dispatch_paused": True,
                "paused_reason": reason, "pre_paused": pre_paused,
                "pause_owner": reason, "fenced_operations": fenced,
                "continuations": continuations}
        return (ResultCode.APPLIED, f"checkpoint barrier at admission epoch {epoch}", data,
                [("recovery.barrier", data)], [])
    return transact(dsn, cmd, _fn)


def resume_dispatch(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        only = cmd.payload.get("only_reason")
        reason = str(control.get("paused_reason") or "")
        if only is not None and reason != str(only):
            return (ResultCode.ALREADY_APPLIED,
                    f"dispatch pause owned by {reason or 'none'};"
                    f" {cmd.payload.get('reason', 'operator')} is not resuming it",
                    {"resumed": False, "paused_reason": reason,
                     "reason": cmd.payload.get("reason", "")}, [], [])
        cur.execute("UPDATE control SET dispatch_paused = FALSE, paused_reason = '' WHERE id = 1")
        return (ResultCode.APPLIED,
                f"dispatch resumed ({cmd.payload.get('reason', 'operator')})",
                {"resumed": True, "reason": cmd.payload.get("reason", "")},
                [("recovery.resumed", {"reason": cmd.payload.get("reason", "")})], [])
    return transact(dsn, cmd, _fn)


def checkpoint_verify(dsn: str, barrier: dict) -> list[str]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT admission_epoch, event_epoch, dispatch_paused, paused_reason"
                        " FROM control WHERE id = 1")
            control = cur.fetchone()
            cur.execute("SELECT COUNT(*) AS n FROM command_journal")
            journal = int(cur.fetchone()["n"])
            cur.execute("SELECT workflow_identity FROM outbox WHERE delivered = FALSE"
                        " ORDER BY workflow_identity")
            pending = [r["workflow_identity"] for r in cur.fetchall()]
            continuations = _live_continuations(cur)
            conn.commit()
    mismatches = []
    if int(control["admission_epoch"]) != int(barrier["barrier_epoch"]):
        mismatches.append(
            f"admission moved during checkpoint: barrier={barrier['barrier_epoch']}"
            f" now={control['admission_epoch']}")
    if int(control["event_epoch"]) != int(barrier["event_epoch"]):
        mismatches.append(
            f"events moved during checkpoint: barrier={barrier['event_epoch']}"
            f" now={control['event_epoch']}")
    if journal != int(barrier["journal_count"]):
        mismatches.append(
            f"journal moved during checkpoint: barrier={barrier['journal_count']} now={journal}")
    if pending != list(barrier["outbox_pending"]):
        mismatches.append(
            f"outbox moved during checkpoint: barrier={barrier['outbox_pending']} now={pending}")
    if bool(control.get("dispatch_paused", True)) != bool(barrier.get("dispatch_paused", True)):
        mismatches.append(
            f"dispatch pause flipped during checkpoint: barrier={barrier.get('dispatch_paused')}"
            f" now={control.get('dispatch_paused')}")
    if str(control.get("paused_reason") or "") != str(barrier.get("paused_reason") or ""):
        mismatches.append(
            f"pause owner moved during checkpoint: barrier={barrier.get('paused_reason')}"
            f" now={control.get('paused_reason')}")
    if continuations != list(barrier.get("continuations", [])):
        mismatches.append(
            f"workflow continuations moved during checkpoint: barrier={barrier.get('continuations')}"
            f" now={continuations}")
    return mismatches


def restore_fence(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT id, ownership_generation FROM attempts"
                    " WHERE lifecycle NOT IN ('completed', 'failed', 'cancelled') ORDER BY id")
        bumped = []
        for attempt in cur.fetchall():
            generation = int(attempt["ownership_generation"]) + 1
            cur.execute("UPDATE attempts SET ownership_generation = %s, updated_at = now()"
                        " WHERE id = %s", (generation, attempt["id"]))
            bumped.append({"id": attempt["id"], "ownership_generation": generation})
        fenced = _bump_inflight_dispatch(cur)
        cur.execute("UPDATE control SET dispatch_paused = TRUE,"
                    " paused_reason = 'restore' WHERE id = 1")
        data = {"attempts": bumped, "operations": fenced,
                "reason": cmd.payload.get("reason", ""), "dispatch_paused": True}
        return (ResultCode.APPLIED,
                f"fenced {len(bumped)} attempts and {len(fenced)} operations;"
                " dispatch paused until resume_dispatch", data,
                [("recovery.fenced", data)], [])
    return transact(dsn, cmd, _fn)


def register_evidence_change(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("UPDATE control SET evidence_epoch = evidence_epoch + 1 WHERE id = 1 RETURNING evidence_epoch")
        epoch = cur.fetchone()["evidence_epoch"]
        return (ResultCode.APPLIED, f"evidence epoch now {epoch}", {"evidence_epoch": epoch},
                [("evidence.invalidated", {"evidence_epoch": epoch})], [])
    return transact(dsn, cmd, _fn)
