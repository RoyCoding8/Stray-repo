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
from .common import Command, ConflictPayload, MissingEvidence, ResultCode, SettlementError

KINDS = ("calibration", "development", "repair", "use")

PHASES = ("diagnostic", "validation")

STRANDED_DISPATCH_STATES = ("dispatching", "sent", "unresolved")


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
    if isinstance(correction_budget, bool) or not isinstance(correction_budget, int) \
            or correction_budget < 0:
        raise SettlementError("correction budget is a non-negative integer")
    allocation_id = allocation_id or study_root
    if ceilings is not None and not isinstance(ceilings, dict):
        raise SettlementError("study ceilings must be an object")
    for name, value in dict(ceilings or {}).items():
        if not isinstance(name, str) or not name.strip():
            raise SettlementError("study ceilings name a resource")
        if not store.is_ceiling_name(name):
            raise SettlementError(f"unsupported study ceiling {name}")
        if isinstance(value, dict):
            value = value.get("max", value.get("limit"))
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SettlementError(f"study ceiling {name} must be a non-negative integer")
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
            immutable = (
                existing["allocation_id"] == allocation_id
                and int(existing["authorized"]) == authorized
                and dict(existing.get("ceilings") or {}) == dict(ceilings or {})
                and int(existing.get("correction_budget", 2)) == correction_budget
            )
            if not immutable:
                raise ConflictPayload(
                    f"study {study_root} is already bound with different authority fields")
            if str(existing.get("store_fingerprint") or "") != str(fingerprint):
                raise MissingAuthority(
                    f"study {study_root} is bound to another store; refusing to seed")
            return (ResultCode.APPLIED, f"study {study_root} already bound",
                    {"study_root": study_root, "allocation_id": existing["allocation_id"],
                     "authorized": int(existing["authorized"]),
                     "ceilings": dict(existing.get("ceilings") or {}),
                     "correction_budget": int(existing.get("correction_budget", 2)),
                     "store_fingerprint": str(fingerprint)}, [], [])
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
    if result.code == ResultCode.UNAUTHORIZED:
        raise MissingAuthority(result.detail)
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
                cur.execute("SELECT fingerprint FROM store_identity WHERE id = 1")
                identity = cur.fetchone()
            except Exception as exc:
                conn.rollback()
                raise MissingAuthority(
                    f"store identity for study {study_root!r} is unreadable;"
                    " refusing to bind") from exc
            conn.commit()
    if row is None:
        raise MissingAuthority(
            f"no authority for study {study_root!r} in this store;"
            " refusing to seed")
    if identity is None or str(identity["fingerprint"]) != str(row["store_fingerprint"]):
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
                     retries: int = 0,
                     resource: str | None = None):
    from . import loop as _loop

    if kind not in KINDS:
        return _loop.Refusal(reason="unknown-kind",
                             detail=f"kind {kind!r} is not one of"
                             f" {list(KINDS)}")
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        return _loop.Refusal(reason="invalid-retry",
                             detail="retries must be a non-negative integer")
    try:
        handle = bind_study(dsn, study_root)
    except MissingAuthority as exc:
        return _loop.Refusal(reason="missing-authority", detail=str(exc))
    try:
        clean = broker.validate_effect(effect, payload)
    except broker.InvalidEffect as exc:
        return _loop.Refusal(reason="malformed-action", detail=str(exc))
    exposure, budget_kind = broker.exposure_schedule(effect, clean, retries)
    child_id = f"{handle.allocation_id}/{kind}/{operation_id}"
    body = {
        "effect": effect,
        "payload": clean,
        "retries": retries,
        "budget_kind": budget_kind,
        "study_root": study_root,
        "kind": kind,
        "allocation_id": child_id,
    }
    # The resource this call draws on, for the ceilings that bound a resource
    # rather than an effect. `kind` above names the study phase, which is a
    # different axis, so the two cannot share a key.
    if resource is not None:
        body["resource"] = str(resource)
    try:
        result = store.admit_study_operation(
            dsn, Command(
                request_id=f"admit-study-{study_root}-{operation_id}",
                payload={
                    "study_root": study_root,
                    "kind": kind,
                    "operation_id": operation_id,
                    "allocation_id": child_id,
                    "reservation_id": f"res-{operation_id}",
                    "exposure": exposure,
                    "budget_kind": budget_kind,
                    "body": body,
                    "attempt_id": attempt_id,
                    "execution_version": execution_version,
                },
            ))
    except ConflictPayload as exc:
        return _loop.Refusal(reason="admission-refused", detail=str(exc))
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return _loop.Grant(
            allowance=_loop.Allowance(
                allowance_id=f"{child_id}:{operation_id}", kind=kind,
                amount=exposure),
            operation_id=operation_id, exposure=exposure,
            budget_kind=budget_kind,
            already=result.code == ResultCode.ALREADY_APPLIED)
    if result.code == ResultCode.INSUFFICIENT_RESOURCES:
        return _loop.Refusal(reason="insufficient-authority", detail=result.detail)
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


def _summarize_receipts(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        grouped.setdefault(str(receipt["operation_id"]), []).append(receipt)
    measured = 0
    expected_consumed = 0
    pending = 0
    unknown: list[str] = []
    unknown_usage: list[str] = []
    for operation_receipts in grouped.values():
        terminal = operation_receipts[-1]
        state = str(terminal.get("reconcile_state") or "none")
        reserved_amount = int(terminal.get("reserved_amount") or 0)
        reservation_state = str(terminal.get("reservation_state") or "")
        if state in ("conflict", "unresolved"):
            if reservation_state in ("reserved", "uncertain"):
                pending += reserved_amount
            unknown.extend(
                str(receipt["receipt_identity"]) for receipt in operation_receipts
                if receipt["outcome"] == "unknown")
            continue
        decided = [receipt for receipt in operation_receipts
                   if receipt["outcome"] in ("success", "failure")]
        if not decided:
            unknown.extend(
                str(receipt["receipt_identity"]) for receipt in operation_receipts
                if receipt["outcome"] == "unknown")
            if reservation_state in ("reserved", "uncertain"):
                pending += reserved_amount
            continue
        receipt = decided[-1]
        content = dict(receipt.get("content") or {})
        usage = content.get("usage")
        usage = dict(usage) if isinstance(usage, dict) else {}
        cost = store.receipt_actual_cost({"content": content})
        if cost is None:
            if usage.get("billed") is not False:
                unknown_usage.append(str(receipt["receipt_identity"]))
            if reservation_state == "settled":
                expected_consumed += reserved_amount
        else:
            measured += cost
            expected_consumed += cost
    return {
        "measured": measured,
        "expected_consumed": expected_consumed,
        "pending": pending,
        "unknown": sorted(unknown),
        "unknown_usage": sorted(unknown_usage),
    }


def _stranded_exposure(unreceipted: list[dict[str, Any]]) -> dict[str, int]:
    """Receiptless exposure held by an operation nothing will ever finish.

    An operation that is still ``prepared`` holds exposure a dispatch will
    consume, so its units are pending in the ordinary sense. One that has
    been dispatched and produced no receipt has left the queue: the launcher
    that was given the work either never spawned it or can no longer report
    on it, and no receipt will arrive to settle the reservation. Those units
    are lost, not pending, and counting them as pending is what let a study
    holding them report an all-clear — the amount appeared on both sides of
    the ledger's own arithmetic, so the arithmetic agreed with itself about
    an exposure nothing would ever release.
    """
    stranded: dict[str, int] = {}
    for row in unreceipted:
        if str(row.get("dispatch_state") or "") not in STRANDED_DISPATCH_STATES:
            continue
        amount = int(row["reserved_amount"])
        if amount > 0:
            stranded[str(row["id"])] = amount
    return stranded


def verify_ledger(dsn: str, study_root: str) -> dict[str, Any]:
    from psycopg.rows import dict_row

    handle = bind_study(dsn, study_root)
    alloc_ids = _study_alloc_ids(dsn, handle.allocation_id) or ["~none"]
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT r.receipt_identity, r.operation_id, r.outcome, r.content,"
                " o.reconcile_state, COALESCE(res.amount, 0) AS reserved_amount,"
                " COALESCE(res.state, '') AS reservation_state"
                " FROM receipts r JOIN operations o ON o.id = r.operation_id"
                " LEFT JOIN reservations res ON res.id = o.reservation_id"
                " WHERE o.allocation_id = ANY(%s)"
                " ORDER BY r.operation_id, r.created_at, r.receipt_identity", (alloc_ids,))
            receipts = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT DISTINCT o.id FROM operations o"
                " JOIN receipt_conflicts c ON c.operation_id = o.id"
                " WHERE o.allocation_id = ANY(%s) ORDER BY o.id", (alloc_ids,))
            conflicts = [row["id"] for row in cur.fetchall()]
            cur.execute(
                "SELECT COALESCE(SUM(consumed), 0) AS consumed,"
                " COALESCE(SUM(reserved), 0) AS reserved"
                " FROM allocations WHERE id = ANY(%s)", (alloc_ids,))
            totals = dict(cur.fetchone())
            cur.execute(
                "SELECT o.id, COALESCE(res.amount, 0) AS reserved_amount,"
                " o.dispatch_state"
                " FROM operations o LEFT JOIN receipts r"
                " ON r.operation_id = o.id"
                " LEFT JOIN reservations res ON res.id = o.reservation_id"
                " WHERE o.allocation_id = ANY(%s) AND r.operation_id IS NULL"
                " AND COALESCE(res.state, '') IN ('reserved', 'uncertain')",
                (alloc_ids,))
            unreceipted = [dict(r) for r in cur.fetchall()]
            conn.commit()
    summary = _summarize_receipts(receipts)
    pending = summary["pending"] + sum(
        int(row["reserved_amount"]) for row in unreceipted)
    stranded = _stranded_exposure(unreceipted)
    consumed, reserved = int(totals["consumed"]), int(totals["reserved"])
    return {
        "study_root": study_root,
        "measured": summary["measured"],
        "expected_consumed": summary["expected_consumed"],
        "consumed": consumed,
        "pending": pending,
        "reserved": reserved,
        "unknown": summary["unknown"],
        "unknown_usage": summary["unknown_usage"],
        "conflicts": conflicts,
        "unreceipted": sorted(row["id"] for row in unreceipted),
        "stranded": stranded,
        "match": not conflicts and consumed == summary["expected_consumed"]
        and reserved == pending and not stranded,
    }


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
        cur.execute("SELECT allocation_id, reconcile_state FROM operations WHERE id = %s",
                    (operation_id,))
        operation = cur.fetchone()
        if operation is None:
            raise SettlementError(f"unknown operation {operation_id}")
        if operation["allocation_id"] not in alloc_ids:
            raise SettlementError(
                f"operation {operation_id} is not {study_root} work")
        if operation.get("reconcile_state") in ("conflict", "unresolved"):
            raise MissingEvidence(
                f"operation {operation_id} is {operation['reconcile_state']}")
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

    bind_study(dsn, study_root)
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

    bind_study(dsn, study_root)
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COALESCE(SUM(used), 0) AS used"
                        " FROM study_corrections WHERE study_root = %s",
                        (study_root,))
            total = int(cur.fetchone()["used"])
            conn.commit()
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
