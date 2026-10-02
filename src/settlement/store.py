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

import time
from typing import Any, Callable

from psycopg import errors as _pgerrors
from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import db
from .common import (
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

_OUTCOMES = {"success", "failure", "unknown"}
_TERMINAL_ATTEMPT = {"completed", "failed", "cancelled"}


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
    deadline = time.monotonic() + max(int(cmd.deadline_ms), 1) / 1000.0
    while True:
        try:
            with db.connect(dsn) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
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
                        with conn.cursor(row_factory=dict_row) as cur2:
                            cur2.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
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


def _get_alloc(cur, allocation_id: str) -> dict:
    cur.execute("SELECT * FROM allocations WHERE id = %s", (allocation_id,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown allocation {allocation_id}")
    return row


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
        try:
            consumed = int(actual)
        except (TypeError, ValueError):
            raise SettlementError(f"actual cost {actual!r} is not an integer")
        if consumed < 0 or consumed > amount:
            raise SettlementError(f"actual cost {actual} outside reserved {amount}")
    cur.execute(
        "UPDATE allocations SET reserved = reserved - %s, consumed = consumed + %s WHERE id = %s",
        (amount, consumed, res["allocation_id"]),
    )
    cur.execute("UPDATE reservations SET state = 'settled' WHERE id = %s", (reservation_id,))
    return True, "settled", consumed


def get_control(dsn: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("INSERT INTO control (id) VALUES (1) ON CONFLICT DO NOTHING")
            cur.execute("SELECT * FROM control WHERE id = 1")
            conn.commit()
            return dict(cur.fetchone())


def allocation_status(dsn: str, allocation_id: str) -> dict:
    with db.connect(dsn) as conn:
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
        version = int(p["version"])
        if version <= 0:
            raise SettlementError("grant version must be positive")
        cur.execute(
            "INSERT INTO grants (version, charter_text, authority_grant, envelopes)"
            " VALUES (%s, %s, %s, %s) ON CONFLICT (version) DO UPDATE SET charter_text = EXCLUDED.charter_text,"
            " authority_grant = EXCLUDED.authority_grant, envelopes = EXCLUDED.envelopes",
            (version, p["charter_text"], _j(p.get("authority_grant", {})), _j(p.get("envelopes", {}))),
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
        parent = _get_alloc(cur, p["parent_id"])
        amount = int(p["authorized"])
        if amount <= 0:
            raise SettlementError("child authorized must be a positive integer")
        free = _alloc_available(parent, _child_authorized(cur, p["parent_id"]))
        if free < amount:
            raise InsufficientResources(f"parent {parent['id']} has {free} free, child needs {amount}")
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
        cur.execute(
            "UPDATE allocations SET reserved = reserved - %s WHERE id = %s",
            (int(res["amount"]), res["allocation_id"]),
        )
        cur.execute("UPDATE reservations SET state = 'released' WHERE id = %s", (res["id"],))
        return (ResultCode.APPLIED, "released", {"reservation_id": res["id"]},
                [("resources.released", {"reservation_id": res["id"]})], [])
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


def acquire_work(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        cur.execute("SELECT * FROM investigations WHERE id = %s", (p["investigation_id"],))
        inv = cur.fetchone()
        if inv is None:
            raise SettlementError(f"unknown investigation {p['investigation_id']}")
        if inv["disposition"] in ("withdrawn", "fulfilled"):
            raise SettlementError(f"investigation {inv['id']} is {inv['disposition']}")
        alloc_id = p.get("allocation_id")
        if alloc_id is not None:
            alloc = _get_alloc(cur, alloc_id)
            if int(alloc["occupancy"]) >= int(alloc["max_occupancy"]):
                raise InsufficientResources(f"allocation {alloc_id} occupancy exhausted")
            cur.execute("UPDATE allocations SET occupancy = occupancy + 1 WHERE id = %s", (alloc_id,))
        cur.execute("SELECT COALESCE(MAX(ownership_generation), 0) AS g FROM attempts WHERE investigation_id = %s",
                    (inv["id"],))
        generation = int(cur.fetchone()["g"]) + 1
        cur.execute(
            "INSERT INTO attempts (id, investigation_id, investigation_revision, allocation_id,"
            " ownership_generation, composition, model, env, lifecycle, deadline, owner)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'running', %s, %s)",
            (p["attempt_id"], inv["id"], int(inv["revision"]), alloc_id, generation,
             p.get("composition", ""), p.get("model", ""), p.get("env", ""),
             p.get("deadline"), p.get("owner", "")),
        )
        return (ResultCode.APPLIED, f"attempt {p['attempt_id']} acquired at generation {generation}",
                {"attempt_id": p["attempt_id"], "ownership_generation": generation,
                 "investigation_revision": int(inv["revision"])},
                [("work.acquired", {"attempt_id": p["attempt_id"], "ownership_generation": generation})],
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


def fulfill_investigation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        cur.execute("SELECT * FROM investigations WHERE id = %s", (p["investigation_id"],))
        inv = cur.fetchone()
        if inv is None:
            raise SettlementError(f"unknown investigation {p['investigation_id']}")
        if cmd.expected_revision is not None and int(cmd.expected_revision) != int(inv["revision"]):
            raise StaleRevision(f"expected revision {cmd.expected_revision}, current {inv['revision']}")
        if inv["disposition"] == "withdrawn":
            raise SettlementError(f"investigation {inv['id']} is withdrawn")
        if inv["disposition"] == "fulfilled" and inv["fulfilled_revision"] == inv["revision"]:
            raise SettlementError(f"investigation {inv['id']} revision {inv['revision']} already fulfilled")
        if "authority_version" in p and int(p["authority_version"]) != int(control["authority_version"]):
            raise Unauthorized("stale completion authority")
        attempt = None
        if p.get("attempt_id") is not None:
            attempt = _get_attempt(cur, p["attempt_id"])
            _check_owner(cur, attempt, p.get("ownership_generation"))
            if attempt["lifecycle"] != "completed":
                raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}, not completed")
            if int(attempt["investigation_revision"]) != int(inv["revision"]):
                raise StaleRevision(f"attempt revision {attempt['investigation_revision']} != {inv['revision']}")
        cur.execute(
            "UPDATE investigations SET disposition = 'fulfilled', fulfilled_revision = %s,"
            " updated_at = now() WHERE id = %s",
            (int(inv["revision"]), inv["id"]),
        )
        return (ResultCode.APPLIED, f"investigation {inv['id']} r{inv['revision']} fulfilled",
                {"investigation_id": inv["id"], "revision": int(inv["revision"])},
                [("commitment.fulfilled", {"investigation_id": inv["id"], "revision": int(inv["revision"])})], [])
    return transact(dsn, cmd, _fn)


def _get_operation(cur, operation_id: str) -> dict:
    cur.execute("SELECT * FROM operations WHERE id = %s", (operation_id,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown operation {operation_id}")
    return row


def prepare_operation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        op_id = p["operation_id"]
        body = p.get("operation", {})
        digest = payload_digest(body)
        cur.execute("SELECT payload_digest FROM operations WHERE id = %s", (op_id,))
        existing = cur.fetchone()
        if existing is not None:
            if existing["payload_digest"] != digest:
                raise ConflictPayload(f"operation {op_id} intent is immutable")
            return (ResultCode.ALREADY_APPLIED, "operation already prepared",
                    {"operation_id": op_id}, [], [])
        attempt_id = p.get("attempt_id")
        if attempt_id is not None and _get_attempt(cur, attempt_id) is None:
            raise SettlementError(f"unknown attempt {attempt_id}")
        exposure = int(p.get("exposure", 0))
        reservation_id = p.get("reservation_id")
        if exposure > 0:
            if not reservation_id or not p.get("allocation_id"):
                raise SettlementError("exposure needs reservation_id and allocation_id")
            _take_reservation(cur, p["allocation_id"], reservation_id, exposure, op_id)
        cur.execute(
            "INSERT INTO operations (id, attempt_id, allocation_id, reservation_id, payload_digest,"
            " payload, dispatch_state, execution_version)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'prepared', %s)",
            (op_id, attempt_id, p.get("allocation_id"), reservation_id, digest, _j(body),
             p.get("execution_version", "")),
        )
        return (ResultCode.APPLIED, f"operation {op_id} prepared",
                {"operation_id": op_id, "reservation_id": reservation_id},
                [("operation.prepared", {"operation_id": op_id})], [])
    return transact(dsn, cmd, _fn)


def advance_dispatch(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        op = _get_operation(cur, p["operation_id"])
        if op["dispatch_state"] != "prepared":
            if op["launcher_id"] == p.get("launcher_id", op["launcher_id"]) and op["dispatch_state"] == "dispatching":
                return (ResultCode.ALREADY_APPLIED, "already dispatching",
                        {"operation_id": op["id"]}, [], [])
            raise SettlementError(f"operation {op['id']} is {op['dispatch_state']}, not prepared")
        if "grant_version" in p and int(p["grant_version"]) != int(control["authority_version"]):
            raise Unauthorized("stale dispatch grant")
        if op["attempt_id"] is not None:
            attempt = _get_attempt(cur, op["attempt_id"])
            _check_owner(cur, attempt, p.get("ownership_generation"))
            if attempt["lifecycle"] not in ("running", "suspended"):
                raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}")
        cur.execute(
            "UPDATE operations SET dispatch_state = 'dispatching', launcher_id = %s,"
            " provider_id = %s, updated_at = now() WHERE id = %s",
            (p.get("launcher_id", ""), p.get("provider_id", ""), op["id"]),
        )
        intent = {"operation_id": op["id"], "payload": op["payload"], "launcher_id": p.get("launcher_id", "")}
        return (ResultCode.APPLIED, f"operation {op['id']} dispatching",
                {"operation_id": op["id"]},
                [("operation.dispatching", {"operation_id": op["id"]})],
                [("dispatch", intent, f"dispatch:{op['id']}")])
    return transact(dsn, cmd, _fn)


def admit_receipt(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        op = _get_operation(cur, p["operation_id"])
        content = p.get("content", {})
        digest = payload_digest(content)
        outcome = p.get("outcome", "unknown")
        if outcome not in _OUTCOMES:
            raise SettlementError(f"unknown outcome {outcome}")
        cur.execute("SELECT * FROM receipts WHERE receipt_identity = %s", (p["receipt_identity"],))
        seen = cur.fetchone()
        if seen is not None:
            if seen["content_digest"] == digest:
                return (ResultCode.ALREADY_APPLIED, "duplicate receipt",
                        {"operation_id": op["id"], "settled": bool(op["settled"])}, [], [])
            cur.execute(
                "INSERT INTO receipt_conflicts (receipt_identity, operation_id, content_digest, content)"
                " VALUES (%s, %s, %s, %s)",
                (p["receipt_identity"], op["id"], digest, _j(content)),
            )
            cur.execute(
                "UPDATE operations SET reconcile_state = 'conflict', receipt_provenance = %s,"
                " updated_at = now() WHERE id = %s",
                (p.get("provenance", ""), op["id"]),
            )
            return (ResultCode.APPLIED, "conflicting receipt preserved for reconciliation",
                    {"operation_id": op["id"], "conflict": True, "settled": bool(op["settled"])},
                    [("operation.receipt_conflict", {"operation_id": op["id"]})], [])
        cur.execute(
            "INSERT INTO receipts (receipt_identity, operation_id, content_digest, content, outcome)"
            " VALUES (%s, %s, %s, %s, %s)",
            (p["receipt_identity"], op["id"], digest, _j(content), outcome),
        )
        if bool(op["settled"]):
            return (ResultCode.APPLIED, "receipt recorded, reservation already settled",
                    {"operation_id": op["id"], "settled": True},
                    [("operation.receipted", {"operation_id": op["id"]})], [])
        settled = False
        if op["reservation_id"] is not None and outcome in ("success", "failure"):
            settled, _, _ = _settle_amount(cur, op["reservation_id"], outcome, p.get("actual_cost"))
        elif op["reservation_id"] is not None:
            _settle_amount(cur, op["reservation_id"], "unknown")
        state = "observed" if outcome in ("success", "failure") else "unresolved"
        reconcile = "none" if outcome in ("success", "failure") else "unresolved"
        cur.execute(
            "UPDATE operations SET dispatch_state = %s, reconcile_state = %s, receipt_provenance = %s,"
            " settled = %s, updated_at = now() WHERE id = %s",
            (state, reconcile, p.get("provenance", ""), settled or bool(op["settled"]), op["id"]),
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
        cur.execute(
            "UPDATE operations SET cancel_state = 'confirmed', updated_at = now() WHERE id = %s", (op["id"],))
        return (ResultCode.APPLIED, "cancellation confirmed", {"operation_id": op["id"]},
                [("operation.cancel_confirmed", {"operation_id": op["id"]})], [])
    return transact(dsn, cmd, _fn)


def reconcile_operation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        op = _get_operation(cur, p["operation_id"])
        resolution = p.get("resolution", "reconciled")
        if resolution not in ("reconciled", "unresolved"):
            raise SettlementError(f"unknown resolution {resolution}")
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
    with db.connect(dsn) as conn:
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
    with db.connect(dsn) as conn:
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
    with db.connect(dsn) as conn:
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



def register_evidence_change(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        cur.execute("UPDATE control SET evidence_epoch = evidence_epoch + 1 WHERE id = 1 RETURNING evidence_epoch")
        epoch = cur.fetchone()["evidence_epoch"]
        return (ResultCode.APPLIED, f"evidence epoch now {epoch}", {"evidence_epoch": epoch},
                [("evidence.invalidated", {"evidence_epoch": epoch})], [])
    return transact(dsn, cmd, _fn)
