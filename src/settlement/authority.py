"""One explicitly authorized study root over the durable store.

A study names its root once through :func:`authorize_study`. Every later
bind, calibration, development, repair and use resolves against that row:
child allocations subdivide from remaining parent authority, reopening the
same database reconnects without seeding, and any other database refuses
with missing authority instead of minting a fresh allocation. Rejected
proposal corrections and diagnostic/validation phase completions persist
here so resume restores budgets and observations without redoing work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Json

from . import broker, db, store
from .common import Command, ConflictPayload, ResultCode, SettlementError

KINDS = ("calibration", "development", "repair", "use")

PHASES = ("diagnostic", "validation")


def _j(value: Any) -> Json:
    return Json(dict(value) if isinstance(value, dict) else value)


class MissingAuthority(SettlementError):
    code = ResultCode.UNAUTHORIZED


@dataclass(frozen=True)
class StudyHandle:
    study_root: str
    allocation_id: str
    authorized: int
    ceilings: dict[str, Any] = field(default_factory=dict)
    correction_budget: int = 2
    store_fingerprint: str = ""


def _handle(row: dict) -> StudyHandle:
    return StudyHandle(
        study_root=row["study_root"], allocation_id=row["allocation_id"],
        authorized=int(row["authorized"]),
        ceilings=dict(row.get("ceilings") or {}),
        correction_budget=int(row.get("correction_budget", 2)),
        store_fingerprint=str(row.get("store_fingerprint") or ""))


def store_fingerprint(dsn: str) -> str:
    from psycopg.rows import dict_row

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT fingerprint FROM store_identity WHERE id = 1")
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError("store carries no identity row")
    return str(row["fingerprint"])


def authorize_study(dsn: str, study_root: str, *, authorized: int,
                    allocation_id: str | None = None,
                    ceilings: dict[str, Any] | None = None,
                    correction_budget: int = 2) -> StudyHandle:
    if not isinstance(study_root, str) or not study_root.strip():
        raise SettlementError("authorization names a study root")
    if isinstance(authorized, bool) or not isinstance(authorized, int) \
            or authorized <= 0:
        raise SettlementError("authorization carries finite positive authority")
    if not isinstance(correction_budget, int) or correction_budget < 0:
        raise SettlementError("correction budget is a non-negative integer")
    allocation_id = allocation_id or study_root
    payload = {"study_root": study_root, "allocation_id": allocation_id,
               "authorized": authorized, "ceilings": dict(ceilings or {}),
               "correction_budget": correction_budget}

    def _fn(cur, control):
        cur.execute("INSERT INTO store_identity (id) VALUES (1)"
                    " ON CONFLICT (id) DO NOTHING")
        cur.execute("SELECT fingerprint FROM store_identity WHERE id = 1")
        fingerprint = cur.fetchone()["fingerprint"]
        cur.execute("SELECT * FROM study_authority WHERE study_root = %s",
                    (study_root,))
        existing = cur.fetchone()
        if existing is not None:
            if existing["allocation_id"] != allocation_id \
                    or int(existing["authorized"]) != authorized:
                raise ConflictPayload(
                    f"study {study_root} already holds"
                    f" {existing['authorized']} on {existing['allocation_id']};"
                    " refusing to reseed")
            return (ResultCode.APPLIED, f"study {study_root} already bound",
                    {**payload, "store_fingerprint": str(fingerprint)}, [], [])
        cur.execute("SELECT authorized FROM allocations WHERE id = %s",
                    (allocation_id,))
        allocation = cur.fetchone()
        if allocation is None:
            cur.execute(
                "INSERT INTO allocations (id, parent_id, domain, epoch,"
                " authorized, amount_scale, max_occupancy, owner_scope)"
                " VALUES (%s, NULL, 'study', 0, %s, 1, 8, '')",
                (allocation_id, authorized))
        elif int(allocation["authorized"]) != authorized:
            raise SettlementError(
                f"allocation {allocation_id} already holds"
                f" {allocation['authorized']}, not {authorized}")
        cur.execute(
            "INSERT INTO study_authority (study_root, allocation_id,"
            " authorized, ceilings, correction_budget, store_fingerprint)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (study_root, allocation_id, authorized,
             _j(payload["ceilings"]), correction_budget, fingerprint))
        return (ResultCode.APPLIED, f"study {study_root} authorized",
                {**payload, "store_fingerprint": str(fingerprint)},
                [("study.authorized", {"study_root": study_root})], [])

    result = store.transact(
        dsn, Command(request_id=f"authorize-{study_root}", payload=payload),
        _fn)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"authorization refused: {result.detail}")
    data = dict(result.data)
    data["store_fingerprint"] = data.get(
        "store_fingerprint") or store_fingerprint(dsn)
    return StudyHandle(
        study_root=study_root, allocation_id=data["allocation_id"],
        authorized=int(data["authorized"]),
        ceilings=dict(data.get("ceilings") or {}),
        correction_budget=int(data.get("correction_budget", 2)),
        store_fingerprint=str(data["store_fingerprint"]))


def bind_study(dsn: str, study_root: str) -> StudyHandle:
    from psycopg.rows import dict_row

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM study_authority WHERE study_root = %s",
                        (study_root,))
            row = cur.fetchone()
            try:
                cur.execute(
                    "SELECT fingerprint FROM store_identity WHERE id = 1")
                identity = cur.fetchone()
            except Exception:
                identity = None
            conn.commit()
    if row is None:
        raise MissingAuthority(
            f"no authority for study {study_root!r} in this store;"
            " refusing to seed")
    if identity is not None and str(identity["fingerprint"]) != str(
            row["store_fingerprint"]):
        raise MissingAuthority(
            f"study {study_root!r} is bound to another store;"
            " refusing to seed")
    return _handle(dict(row))


def study_remaining(dsn: str, study_root: str) -> int:
    handle = bind_study(dsn, study_root)
    return store.allocation_free(dsn, handle.allocation_id)


def admit_study_call(dsn: str, study_root: str, *, kind: str,
                     operation_id: str, effect: str, payload: dict[str, Any],
                     attempt_id: str | None = None,
                     execution_version: str = "",
                     retries: int = 0):
    from . import loop as _loop

    if kind not in KINDS:
        return _loop.Refusal(reason="unknown-kind",
                             detail=f"kind {kind!r} is not one of"
                             f" {list(KINDS)}")
    try:
        handle = bind_study(dsn, study_root)
    except MissingAuthority as exc:
        return _loop.Refusal(reason="missing-authority", detail=str(exc))
    try:
        clean = broker.validate_effect(effect, payload)
    except broker.InvalidEffect as exc:
        return _loop.Refusal(reason="malformed-action", detail=str(exc))
    exposure, budget_kind = broker.exposure_schedule(effect, clean, retries)
    replayed = _existing_grant(
        dsn, operation_id, effect, clean, retries, budget_kind, kind)
    if replayed is not None:
        return replayed
    child_id = f"{handle.allocation_id}/{kind}/{operation_id}"
    provisioned = _provision_child(dsn, handle, child_id, exposure)
    if isinstance(provisioned, _loop.Refusal):
        return provisioned
    return _loop.admit_effect(
        dsn, allocation_id=child_id, operation_id=operation_id,
        effect=effect, payload=clean, attempt_id=attempt_id,
        execution_version=execution_version, retries=retries, kind=kind)


def _existing_grant(dsn: str, operation_id: str, effect: str,
                    clean: dict[str, Any], retries: int,
                    budget_kind: str, kind: str):
    from . import loop as _loop
    from .common import payload_digest

    existing = broker.read_operation(dsn, operation_id)
    if existing is None:
        return None
    body = {"effect": effect, "payload": clean,
            "retries": max(int(retries), 0), "budget_kind": budget_kind}
    if existing.get("payload_digest") != payload_digest(body):
        return _loop.Refusal(
            reason="admission-refused",
            detail=f"operation {operation_id} intent is immutable")
    exposure, _ = broker.exposure_schedule(effect, clean, retries)
    allocation_id = existing.get("allocation_id") or ""
    return _loop.Grant(
        allowance=_loop.Allowance(allowance_id=f"{allocation_id}:{operation_id}",
                                  kind=kind or effect, amount=exposure),
        operation_id=operation_id, exposure=exposure,
        budget_kind=budget_kind, already=True)


def _provision_child(dsn: str, handle: StudyHandle, child_id: str,
                     exposure: int):
    from . import loop as _loop
    from psycopg.rows import dict_row

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT authorized FROM allocations WHERE id = %s",
                        (child_id,))
            found = cur.fetchone()
            conn.commit()
    if found is not None:
        if int(found["authorized"]) != int(exposure):
            raise SettlementError(
                f"child {child_id} already holds {found['authorized']},"
                f" not {exposure}")
        return {"child_id": child_id, "reused": True}
    result = store.subdivide_allocation(
        dsn, Command(request_id=f"auth-child-{child_id}",
                     payload={"parent_id": handle.allocation_id,
                              "child_id": child_id,
                              "authorized": exposure, "domain": "study"}))
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return {"child_id": child_id, "reused": False}
    if result.code == ResultCode.INSUFFICIENT_RESOURCES:
        return _loop.Refusal(reason="insufficient-authority",
                             detail=result.detail)
    return _loop.Refusal(reason="admission-refused", detail=result.detail)


def _study_alloc_ids(dsn: str, allocation_id: str) -> list[str]:
    from psycopg.rows import dict_row

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "WITH RECURSIVE study_allocs (id) AS ("
                " SELECT id FROM allocations WHERE id = %s"
                " UNION SELECT a.id FROM allocations a"
                " JOIN study_allocs s ON a.parent_id = s.id)"
                " SELECT id FROM study_allocs", (allocation_id,))
            rows = [r["id"] for r in cur.fetchall()]
            conn.commit()
    return rows


def verify_ledger(dsn: str, study_root: str) -> dict[str, Any]:
    from psycopg.rows import dict_row

    handle = bind_study(dsn, study_root)
    alloc_ids = _study_alloc_ids(dsn, handle.allocation_id) or ["~none"]
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT r.receipt_identity, r.outcome,"
                " COALESCE((r.content->'usage'->>'charge_units')::int, 0)"
                " AS charge,"
                " CASE WHEN r.content->'usage'->>'billed' = 'true'"
                " THEN TRUE ELSE FALSE END AS billed,"
                " COALESCE(res.amount, 0) AS reserved_amount,"
                " COALESCE(res.state, '') AS reservation_state"
                " FROM receipts r JOIN operations o ON o.id = r.operation_id"
                " LEFT JOIN reservations res ON res.id = o.reservation_id"
                " WHERE o.allocation_id = ANY(%s)"
                " ORDER BY r.receipt_identity", (alloc_ids,))
            receipts = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT COALESCE(SUM(consumed), 0) AS consumed,"
                " COALESCE(SUM(reserved), 0) AS reserved"
                " FROM allocations WHERE id = ANY(%s)", (alloc_ids,))
            totals = dict(cur.fetchone())
            cur.execute(
                "SELECT o.id, COALESCE(res.amount, 0) AS reserved_amount"
                " FROM operations o LEFT JOIN receipts r"
                " ON r.operation_id = o.id"
                " LEFT JOIN reservations res ON res.id = o.reservation_id"
                " WHERE o.allocation_id = ANY(%s) AND r.operation_id IS NULL"
                " AND COALESCE(res.state, '') IN ('reserved', 'uncertain')",
                (alloc_ids,))
            unreceipted = [dict(r) for r in cur.fetchall()]
            conn.commit()
    measured = sum(r["charge"] for r in receipts
                   if r["outcome"] in ("success", "failure") and r["billed"])
    unknown = sorted(r["receipt_identity"] for r in receipts
                     if r["outcome"] == "unknown")
    settled_unbilled = sum(
        r["reserved_amount"] for r in receipts
        if r["outcome"] in ("success", "failure") and not r["billed"]
        and r["reservation_state"] == "settled")
    expected_consumed = measured + settled_unbilled
    pending = sum(r["reserved_amount"] for r in receipts
                  if r["reservation_state"] in ("reserved", "uncertain"))
    pending += sum(int(r["reserved_amount"]) for r in unreceipted)
    consumed, reserved = int(totals["consumed"]), int(totals["reserved"])
    return {"study_root": study_root, "measured": measured,
            "expected_consumed": expected_consumed, "consumed": consumed,
            "pending": pending, "reserved": reserved,
            "unknown": unknown,
            "unreceipted": sorted(r["id"] for r in unreceipted),
            "match": consumed == expected_consumed
            and reserved == pending}


def note_phase(dsn: str, study_root: str, decision_id: str, phase: str,
               operation_id: str, ref_digest: str = "",
               detail: dict[str, Any] | None = None) -> dict[str, Any]:
    if phase not in PHASES:
        raise SettlementError(f"unknown phase {phase!r}")
    if not decision_id:
        raise SettlementError("phase completion names its decision")
    if phase == "validation" and not ref_digest:
        raise SettlementError("validation names its candidate digest")
    handle = bind_study(dsn, study_root)
    alloc_ids = _study_alloc_ids(dsn, handle.allocation_id)
    payload = {"study_root": study_root, "decision_id": decision_id,
               "phase": phase, "operation_id": operation_id,
               "ref_digest": ref_digest, "detail": dict(detail or {})}

    def _fn(cur, control):
        cur.execute("SELECT allocation_id FROM operations WHERE id = %s",
                    (operation_id,))
        operation = cur.fetchone()
        if operation is None:
            raise SettlementError(f"unknown operation {operation_id}")
        if operation["allocation_id"] not in alloc_ids:
            raise SettlementError(
                f"operation {operation_id} is not {study_root} work")
        cur.execute("SELECT 1 FROM receipts WHERE operation_id = %s"
                    " AND outcome IN ('success', 'failure')", (operation_id,))
        if cur.fetchone() is None:
            raise SettlementError(
                f"phase {phase} needs a decided receipt for {operation_id}")
        cur.execute(
            "INSERT INTO study_phases (study_root, decision_id, phase,"
            " operation_id, ref_digest, detail)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (study_root, decision_id, phase) DO NOTHING",
            (study_root, decision_id, phase, operation_id, ref_digest,
             _j(payload["detail"])))
        return (ResultCode.APPLIED if cur.rowcount else ResultCode.ALREADY_APPLIED,
                f"phase {phase} recorded for {decision_id}", payload, [], [])

    result = store.transact(
        dsn, Command(
            request_id=f"phase-{study_root}-{decision_id}-{phase}",
            payload=payload), _fn)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"phase not recorded: {result.detail}")
    return dict(result.data)


def phase_status(dsn: str, study_root: str,
                 decision_id: str) -> dict[str, Any]:
    from psycopg.rows import dict_row

    bind_study(dsn, study_root)
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT phase, operation_id, ref_digest, created_at"
                        " FROM study_phases"
                        " WHERE study_root = %s AND decision_id = %s",
                        (study_root, decision_id))
            rows = {r["phase"]: dict(r) for r in cur.fetchall()}
            conn.commit()
    return {"study_root": study_root, "decision_id": decision_id,
            "diagnostic": rows.get("diagnostic"),
            "validation": rows.get("validation")}


def correction_state(dsn: str, study_root: str,
                     decision_key: str) -> dict[str, Any]:
    from psycopg.rows import dict_row

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT used, failure FROM study_corrections"
                            " WHERE study_root = %s AND decision_key = %s",
                            (study_root, decision_key))
                row = cur.fetchone()
            except Exception:
                conn.rollback()
                row = None
            conn.commit()
    if row is None:
        return {"study_root": study_root, "decision_key": decision_key,
                "used": 0, "failure": {}}
    return {"study_root": study_root, "decision_key": decision_key,
            "used": int(row["used"]), "failure": dict(row["failure"] or {})}


def corrections_total(dsn: str, study_root: str) -> int:
    from psycopg.rows import dict_row

    try:
        with db.read_connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT COALESCE(SUM(used), 0) AS used"
                            " FROM study_corrections WHERE study_root = %s",
                            (study_root,))
                total = int(cur.fetchone()["used"])
                conn.commit()
    except Exception:
        return 0
    return total


def take_correction(dsn: str, study_root: str, decision_key: str,
                    failure: dict[str, Any], attempt: int,
                    budget: int) -> dict[str, Any]:
    from psycopg.rows import dict_row

    try:
        handle = bind_study(dsn, study_root)
        effective = min(int(budget), int(handle.correction_budget))
    except MissingAuthority:
        raise
    if not isinstance(attempt, int) or attempt <= 0:
        raise SettlementError("correction attempts count from one")
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT used FROM study_corrections"
                        " WHERE study_root = %s AND decision_key = %s"
                        " FOR UPDATE", (study_root, decision_key))
            row = cur.fetchone()
            used = int(row["used"]) if row is not None else 0
            if used >= attempt:
                conn.commit()
                return {"allowed": used < effective, "used": used,
                        "budget": effective, "replayed": True}
            if used >= effective:
                cur.execute(
                    "INSERT INTO study_corrections (study_root, decision_key,"
                    " used, failure) VALUES (%s, %s, %s, %s)"
                    " ON CONFLICT (study_root, decision_key) DO UPDATE"
                    " SET failure = EXCLUDED.failure,"
                    " updated_at = now()",
                    (study_root, decision_key, used,
                     _j(dict(failure or {}))))
                conn.commit()
                return {"allowed": False, "used": used,
                        "budget": effective, "replayed": False}
            cur.execute(
                "INSERT INTO study_corrections (study_root, decision_key,"
                " used, failure) VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (study_root, decision_key) DO UPDATE"
                " SET used = study_corrections.used + 1,"
                " failure = EXCLUDED.failure, updated_at = now()",
                (study_root, decision_key, used + 1,
                 _j(dict(failure or {}))))
            conn.commit()
            return {"allowed": used + 1 <= effective, "used": used + 1,
                    "budget": effective, "replayed": False}
