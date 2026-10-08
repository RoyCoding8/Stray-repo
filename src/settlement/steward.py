"""S1 operator stewardship (IF-1 + T2-R04): versioned resource decisions over the store.

Leases live in ``worker_leases`` (migration 0004). Expiry and revocation bump
the attempt's ownership_generation inside the same transition, so a stale
worker's dispatch and fulfillment are refused while its observation submission
stays open. Attempt deadlines are stored by T2; expiry policy lives here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


from . import store
from .common import (
    SUPERVISION_SCOPE,
    Command,
    CommandResult,
    ResultCode,
    SettlementError,
    Unauthorized,
)

_LIVE = ("running", "suspended")

_LEASE_DEFAULT_TTL_MS = 600_000


def _lease_terms(payload: dict) -> tuple[int, datetime]:
    ttl = int(payload.get("ttl_ms", _LEASE_DEFAULT_TTL_MS))
    if ttl <= 0:
        raise SettlementError("ttl_ms must be a positive integer")
    return ttl, datetime.now(timezone.utc) + timedelta(milliseconds=ttl)


def admit_commitment(dsn: str, cmd: Command) -> CommandResult:
    return store.admit_commitment(dsn, cmd)


def amend_commitment(dsn: str, cmd: Command) -> CommandResult:
    return store.amend_commitment(dsn, cmd)


def withdraw_commitment(dsn: str, cmd: Command) -> CommandResult:
    return store.withdraw_commitment(dsn, cmd)


def subdivide_allocation(dsn: str, cmd: Command) -> CommandResult:
    return store.subdivide_allocation(dsn, cmd)


def reserve(dsn: str, cmd: Command) -> CommandResult:
    return store.reserve(dsn, cmd)


def settle_reservation(dsn: str, cmd: Command) -> CommandResult:
    return store.settle_reservation(dsn, cmd)


def release_reservation(dsn: str, cmd: Command) -> CommandResult:
    return store.release_reservation(dsn, cmd)


def amend_allocation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        cur.execute("SELECT * FROM allocations WHERE id = %s", (p["allocation_id"],))
        alloc = cur.fetchone()
        if alloc is None:
            raise SettlementError(f"unknown allocation {p['allocation_id']}")
        target = int(p["authorized"])
        if target < 0:
            raise SettlementError("authorized must be a non-negative integer")
        if int(alloc["consumed"]) + int(alloc["reserved"]) > target:
            raise SettlementError(
                f"allocation {alloc['id']} has consumed {alloc['consumed']}"
                f" + reserved {alloc['reserved']} above {target}")
        cur.execute("SELECT COALESCE(SUM(authorized), 0) AS total FROM allocations WHERE parent_id = %s",
                    (alloc["id"],))
        if int(cur.fetchone()["total"]) > target:
            raise SettlementError(
                f"allocation {alloc['id']} has children above {target}")
        if alloc["parent_id"] is not None and target > int(alloc["authorized"]):
            cur.execute("SELECT * FROM allocations WHERE id = %s", (alloc["parent_id"],))
            parent = cur.fetchone()
            cur.execute("SELECT COALESCE(SUM(authorized), 0) AS total FROM allocations WHERE parent_id = %s",
                        (parent["id"],))
            siblings = int(cur.fetchone()["total"]) - int(alloc["authorized"]) + target
            free = (int(parent["authorized"]) - int(parent["consumed"])
                    - int(parent["reserved"]) - siblings)
            if free < 0:
                from .common import InsufficientResources
                raise InsufficientResources(
                    f"parent {parent['id']} cannot cover growth to {target}")
        cur.execute("UPDATE allocations SET authorized = %s WHERE id = %s", (target, alloc["id"]))
        return (ResultCode.APPLIED, f"allocation {alloc['id']} now {target}",
                {"allocation_id": alloc["id"], "authorized": target},
                [("allocation.amended", {"allocation_id": alloc["id"], "authorized": target})], [])
    return store.transact(dsn, cmd, _fn)


def _scope_of(dsn: str, allocation_id: str) -> str:
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT owner_scope FROM allocations WHERE id = %s", (allocation_id,))
            row = cur.fetchone()
            conn.commit()
            if row is None:
                raise SettlementError(f"unknown allocation {allocation_id}")
            return str(row["owner_scope"])


def admit_task(dsn: str, cmd: Command) -> CommandResult:
    alloc_id = cmd.payload.get("allocation_id")
    if alloc_id is not None and cmd.payload.get("kind", "task") != "recovery":
        if _scope_of(dsn, alloc_id) == SUPERVISION_SCOPE:
            return CommandResult(code=ResultCode.INSUFFICIENT_RESOURCES, request_id=cmd.request_id,
                                 detail=f"allocation {alloc_id} is protected supervision capacity",
                                 data={"allocation_id": alloc_id})
    return store.acquire_work(dsn, cmd)


def _lease_attempt(cur, attempt_id: str) -> dict:
    cur.execute("SELECT * FROM attempts WHERE id = %s", (attempt_id,))
    attempt = cur.fetchone()
    if attempt is None:
        raise SettlementError(f"unknown attempt {attempt_id}")
    return attempt


def issue_lease(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        attempt = _lease_attempt(cur, p["attempt_id"])
        if attempt["lifecycle"] not in _LIVE:
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}")
        cur.execute("SELECT state FROM worker_leases WHERE attempt_id = %s", (attempt["id"],))
        seen = cur.fetchone()
        if seen is not None and seen["state"] == "active":
            raise SettlementError(f"attempt {attempt['id']} already holds an active lease")
        _, expires = _lease_terms(p)
        cur.execute(
            "INSERT INTO worker_leases (attempt_id, holder, ownership_generation, state, expires_at)"
            " VALUES (%s, %s, %s, 'active', %s)"
            " ON CONFLICT (attempt_id) DO UPDATE SET holder = EXCLUDED.holder,"
            " ownership_generation = EXCLUDED.ownership_generation, state = 'active',"
            " issued_at = now(), expires_at = EXCLUDED.expires_at, updated_at = now()",
            (attempt["id"], p.get("holder", ""), int(attempt["ownership_generation"]), expires),
        )
        return (ResultCode.APPLIED, f"lease issued for attempt {attempt['id']}",
                {"attempt_id": attempt["id"], "ownership_generation": int(attempt["ownership_generation"]),
                 "expires_at": expires.isoformat()},
                [("lease.issued", {"attempt_id": attempt["id"]})], [])
    return store.transact(dsn, cmd, _fn)


def _retire_lease(cur, attempt_id: str, state: str) -> tuple:
    attempt = _lease_attempt(cur, attempt_id)
    cur.execute("SELECT * FROM worker_leases WHERE attempt_id = %s", (attempt_id,))
    lease = cur.fetchone()
    if lease is None:
        raise SettlementError(f"attempt {attempt_id} holds no lease")
    if lease["state"] != "active":
        return (ResultCode.ALREADY_APPLIED, f"lease already {lease['state']}",
                {"attempt_id": attempt_id, "ownership_generation": int(attempt["ownership_generation"])}, [], [])
    cur.execute("UPDATE attempts SET ownership_generation = ownership_generation + 1,"
                " updated_at = now() WHERE id = %s RETURNING ownership_generation", (attempt_id,))
    generation = int(cur.fetchone()["ownership_generation"])
    cur.execute("UPDATE worker_leases SET state = %s, updated_at = now() WHERE attempt_id = %s",
                (state, attempt_id))
    return (ResultCode.APPLIED, f"lease {state}; attempt {attempt_id} now generation {generation}",
            {"attempt_id": attempt_id, "ownership_generation": generation},
            [(f"lease.{state}", {"attempt_id": attempt_id, "ownership_generation": generation})], [])


def expire_lease(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        return _retire_lease(cur, cmd.payload["attempt_id"], "expired")
    return store.transact(dsn, cmd, _fn)


def revoke_lease(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        return _retire_lease(cur, cmd.payload["attempt_id"], "revoked")
    return store.transact(dsn, cmd, _fn)


def reacquire_lease(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        attempt = _lease_attempt(cur, p["attempt_id"])
        if attempt["lifecycle"] not in _LIVE:
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}")
        cur.execute("SELECT state FROM worker_leases WHERE attempt_id = %s", (attempt["id"],))
        lease = cur.fetchone()
        if lease is None or lease["state"] == "active":
            raise SettlementError(f"attempt {attempt['id']} has no retired lease to reacquire")
        _, expires = _lease_terms(p)
        cur.execute("UPDATE worker_leases SET holder = %s, ownership_generation = %s, state = 'active',"
                    " issued_at = now(), expires_at = %s, updated_at = now() WHERE attempt_id = %s",
                    (p.get("holder", ""), int(attempt["ownership_generation"]), expires, attempt["id"]))
        return (ResultCode.APPLIED, f"lease reacquired for attempt {attempt['id']}",
                {"attempt_id": attempt["id"], "ownership_generation": int(attempt["ownership_generation"]),
                 "expires_at": expires.isoformat()},
                [("lease.reacquired", {"attempt_id": attempt["id"]})], [])
    return store.transact(dsn, cmd, _fn)


def read_lease(dsn: str, attempt_id: str) -> dict | None:
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM worker_leases WHERE attempt_id = %s", (attempt_id,))
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row is not None else None


def due_attempts(dsn: str, now: datetime | None = None) -> list[dict]:
    moment = now or datetime.now(timezone.utc)
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, investigation_id, ownership_generation, lifecycle, deadline"
                        " FROM attempts WHERE lifecycle IN ('running', 'suspended')"
                        " AND deadline IS NOT NULL AND deadline <= %s ORDER BY deadline, id", (moment,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def expire_attempt(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        attempt = _lease_attempt(cur, cmd.payload["attempt_id"])
        if attempt["lifecycle"] not in _LIVE:
            raise SettlementError(f"attempt {attempt['id']} is {attempt['lifecycle']}")
        cur.execute("UPDATE attempts SET lifecycle = 'cancelled', updated_at = now() WHERE id = %s",
                    (attempt["id"],))
        if attempt["allocation_id"] is not None:
            cur.execute("UPDATE allocations SET occupancy = GREATEST(occupancy - 1, 0) WHERE id = %s",
                        (attempt["allocation_id"],))
        return (ResultCode.APPLIED, f"attempt {attempt['id']} expired past its deadline",
                {"attempt_id": attempt["id"], "lifecycle": "cancelled"},
                [("work.expired", {"attempt_id": attempt["id"]})], [])
    return store.transact(dsn, cmd, _fn)


def fulfill_investigation(dsn: str, cmd: Command) -> CommandResult:
    return store.fulfill_investigation(dsn, cmd)


def fulfill_investigation_override(dsn: str, cmd: Command) -> CommandResult:
    return store.fulfill_investigation_override(dsn, cmd)


def dispatch_guarded(dsn: str, cmd: Command) -> CommandResult:
    return store.advance_dispatch(dsn, cmd)


def check_authority(dsn: str, authority_version: int | None) -> None:
    if authority_version is None:
        return
    control = store.get_control(dsn)
    if int(authority_version) != int(control["authority_version"]):
        raise Unauthorized(f"authority v{authority_version} is stale; current v{control['authority_version']}")


def read_budgets(dsn: str) -> list[dict[str, Any]]:
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, parent_id, domain, authorized, consumed, reserved,"
                        " occupancy, max_occupancy, owner_scope FROM allocations ORDER BY id")
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows
