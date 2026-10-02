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
import threading
import time
from typing import Any, Callable

from psycopg import errors as _pgerrors
from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import db
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
_TERMINAL_ATTEMPT = {"completed", "failed", "cancelled"}
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


def _require_generation(value: Any, label: str = "dispatch generation") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SettlementError(f"{label} must be a positive integer")
    return int(value)


def _never_sent_proof(payload: dict[str, Any], subject: str,
                      generation: int | None = None) -> dict[str, str | int]:
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
    if not valid:
        raise MissingEvidence(
            "never-sent proof requires claim, subject, dispatch generation, and provenance")
    canonical = {
        "claim": "never-sent",
        "subject": subject,
        "provenance": proof["provenance"].strip(),
    }
    if supplied_generation is not None:
        canonical["dispatch_generation"] = supplied_generation
    elif generation is not None:
        canonical["dispatch_generation"] = generation
    return canonical


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
        _take_reservation(cur, p["allocation_id"], p["reservation_id"], int(p["amount"]), p.get("operation_id", ""))
        return (ResultCode.APPLIED, f"reserved {p['amount']}",
                {"reservation_id": p["reservation_id"], "amount": int(p["amount"])},
                [("resources.reserved", {"reservation_id": p["reservation_id"]})], [])
    return transact(dsn, cmd, _fn)


def settle_reservation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
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
                    "SELECT payload FROM operations WHERE id = %s", (operation_id,))
                operation = cur.fetchone()
                if operation is None:
                    raise MissingEvidence(
                        f"reservation {res['id']} has no operation for never-sent proof")
                try:
                    generation = _require_generation(
                        dict(operation.get("payload") or {}).get("_dispatch_generation"),
                        "operation dispatch generation")
                except SettlementError as exc:
                    raise MissingEvidence(str(exc)) from exc
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
        "WITH RECURSIVE allocation_lineage (id) AS ("
        " SELECT id FROM allocations WHERE id = %s"
        " UNION SELECT a.id FROM allocations a"
        " JOIN allocation_lineage line ON a.parent_id = line.id)"
        " SELECT study_authority.study_root FROM study_authority"
        " JOIN allocation_lineage ON allocation_lineage.id = study_authority.allocation_id"
        " LIMIT 1", (allocation_id,))
    row = cur.fetchone()
    if row is None:
        return ""
    value = row.get("study_root") if hasattr(row, "get") else None
    return str(value) if value else ""


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


def _prepare_operation(cur, authority_version: int, *, operation_id: str,
                       attempt_id=None, allocation_id=None, reservation_id=None,
                       exposure: int = 0, operation=None,
                       execution_version: str = "") -> dict:
    body = operation or {}
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


def _study_operation_counts(cur, allocation_id: str) -> dict[str, int]:
    cur.execute(
        "WITH RECURSIVE study_allocs (id) AS ("
        " SELECT id FROM allocations WHERE id = %s"
        " UNION SELECT a.id FROM allocations a"
        " JOIN study_allocs s ON a.parent_id = s.id)"
        " SELECT id FROM study_allocs", (allocation_id,))
    allocation_ids = [row["id"] for row in cur.fetchall()]
    if not allocation_ids:
        return {"operations": 0, "model_calls": 0, "construction_calls": 0,
                "sandbox_calls": 0, "execution_units": 0}
    cur.execute(
        "SELECT o.id, o.allocation_id, o.payload, COALESCE(r.amount, 0) AS exposure"
        " FROM operations o LEFT JOIN reservations r ON r.id = o.reservation_id"
        " WHERE o.allocation_id = ANY(%s) ORDER BY o.id", (allocation_ids,))
    rows = [dict(row) for row in cur.fetchall()]
    counts = {"operations": len(rows), "model_calls": 0,
              "construction_calls": 0, "sandbox_calls": 0,
              "execution_units": 0}
    for row in rows:
        effect = (row.get("payload") or {}).get("effect")
        if effect == "model-inference":
            counts["model_calls"] += 1
            if "-construct-" in str(row.get("id") or ""):
                counts["construction_calls"] += 1
        elif effect == "sandbox-exec":
            counts["sandbox_calls"] += 1
            counts["execution_units"] += int(row.get("exposure") or 0)
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
        body = dict(p["body"])
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
                exposure=exposure, execution_version=str(p.get("execution_version", "")),
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
        counts = _study_operation_counts(cur, parent_id)
        ceilings = dict(study.get("ceilings") or {})
        for name, raw_limit in ceilings.items():
            limit = _ceiling_value(raw_limit)
            counter = CEILING_COUNTERS.get(str(name))
            if limit is None or counter is None:
                raise SettlementError(f"unsupported study ceiling {name}")
            if counter in counts:
                used = counts[counter]
            else:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM operations WHERE allocation_id LIKE %s",
                    (f"{parent_id}/{counter}/%",))
                used = int(cur.fetchone()["n"])
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
             _j(stored_body), str(p.get("execution_version", ""))),
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
    if outcome == "failure":
        provenance = payload.get("provenance")
        if not isinstance(provenance, str) or not provenance.strip():
            raise SettlementError("failure receipt needs provenance")
        if not any(value not in (None, "") for value in (
                content.get("response_operation_id"),
                content.get("response_class"),
                content.get("response_status"),
                content.get("response_digest"),
                content.get("error"),
                content.get("text"),
                content.get("response"))):
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
        )
        if prior and not resolves_unknown:
            _mark_receipt_conflict(cur, op["id"], p["receipt_identity"], digest,
                                   content, outcome, provenance, actual_cost)
            return (ResultCode.APPLIED, "conflicting receipt preserved for reconciliation",
                    {"operation_id": op["id"], "conflict": True, "settled": bool(op["settled"])},
                    [("operation.receipt_conflict", {"operation_id": op["id"],
                                                     "receipt_identity": p["receipt_identity"]})], [])
        cur.execute(
            "INSERT INTO receipts (receipt_identity, operation_id, content_digest, content, outcome)"
            " VALUES (%s, %s, %s, %s, %s)",
            (p["receipt_identity"], op["id"], digest, _j(content), outcome),
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
        cur.execute(
            "UPDATE operations SET cancel_state = 'requested', updated_at = now() WHERE id = %s", (op["id"],))
        return (ResultCode.APPLIED, "cancellation requested", {"operation_id": op["id"]},
                [("operation.cancel_requested", {"operation_id": op["id"]})], [])
    return transact(dsn, cmd, _fn)


def confirm_cancellation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        op = _get_operation(cur, cmd.payload["operation_id"])
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
            proof = _never_sent_proof(cmd.payload, str(op["id"]), generation)
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
            cur.execute("SELECT receipt_identity, outcome, content FROM receipts WHERE operation_id = %s"
                        " ORDER BY receipt_identity", (operation_id,))
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
        proof = _never_sent_proof(cmd.payload, str(op["id"]), current_generation)
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
        if resolution not in ("reconciled", "unresolved"):
            raise SettlementError(f"unknown resolution {resolution}")
        if op["reconcile_state"] == "conflict":
            raise MissingEvidence(
                f"operation {op['id']} has a receipt conflict; retain conflict state")
        cur.execute(
            "SELECT outcome FROM receipts WHERE operation_id = %s"
            " ORDER BY created_at, receipt_identity FOR UPDATE", (op["id"],))
        receipts = [row["outcome"] for row in cur.fetchall()]
        decided = [outcome for outcome in receipts if outcome in ("success", "failure")]
        if resolution == "unresolved" and decided:
            raise MissingEvidence(
                f"operation {op['id']} has a decided receipt; unresolved state would hide it")
        if receipts and not decided:
            if resolution == "reconciled":
                raise MissingEvidence(
                    f"operation {op['id']} has no decided receipt")
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
                stored = dict(op.get("payload") or {})
                try:
                    generation = _require_generation(
                        stored.get("_dispatch_generation"),
                        "operation dispatch generation")
                except SettlementError as exc:
                    raise MissingEvidence(str(exc)) from exc
                proof = _never_sent_proof(p, str(op["id"]), generation)
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
                " cancel_state, settled FROM operations"
                " WHERE dispatch_state IN ('dispatching', 'sent', 'unresolved')"
                " OR (cancel_state = 'requested')"
                " OR reconcile_state = 'conflict' ORDER BY id",
            )
            operations = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT id, investigation_id, investigation_revision, ownership_generation, lifecycle"
                " FROM attempts WHERE lifecycle NOT IN ('completed', 'failed', 'cancelled') ORDER BY id",
            )
            attempts = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT o.id, o.execution_version FROM operations o"
                " WHERE o.execution_version <> '' AND o.dispatch_state IN"
                " ('dispatching', 'sent', 'unresolved') ORDER BY o.id",
            )
            versions = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return {"unfinished_operations": operations, "live_attempts": attempts, "execution_versions": versions}



def _bump_inflight_dispatch(cur) -> list[dict]:
    cur.execute("SELECT id, payload FROM operations"
                " WHERE dispatch_state IN ('dispatching', 'sent', 'unresolved') ORDER BY id")
    fenced = []
    for op in cur.fetchall():
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
