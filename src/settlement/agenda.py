"""S1 autonomous-investigation agenda (AGENDA-1..5) over durable records.

No new tables: capacity rides admitted allocations tagged by owner_scope,
ordering is a pure function over eligible proposals, and wakeups are derived
from the domain event log plus attempt deadlines. The repair scan calls
broker.heartbeat with repair_due and never runs model inference.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg import errors as _pgerrors

from . import broker, steward, store
from .common import Command, CommandResult, ResultCode, SettlementError

SEED_CLASSES = ("bottleneck", "transfer", "instrument-gaps", "speculative")
CAPACITY_SCOPES = ("obligations", "development", "supervision")
SINGLE_WORKER_DEFAULT = True
AGENDA_ROOT = "agenda-root"


def ensure_capacity(dsn: str, amounts: dict[str, int] | None = None,
                    root: str = AGENDA_ROOT) -> dict[str, CommandResult]:
    wants = {"obligations": 1000, "development": 1000, "supervision": 500}
    wants.update(amounts or {})
    out: dict[str, CommandResult] = {}
    total = sum(wants.values())
    out["root"] = store.seed_allocation(
        dsn, Command(request_id=f"agenda-root-{root}",
                     payload={"allocation_id": root, "domain": "agenda", "authorized": total}))
    for scope, amount in wants.items():
        child = f"{root}-{scope}"
        try:
            out[scope] = store.subdivide_allocation(
                dsn, Command(request_id=f"agenda-seed-{child}",
                             payload={"parent_id": root, "child_id": child, "authorized": amount,
                                      "domain": "agenda", "owner_scope": scope}))
        except (SettlementError, _pgerrors.UniqueViolation) as exc:
            out[scope] = CommandResult(code=ResultCode.INVALID_INPUT, request_id=f"agenda-seed-{child}",
                                       detail=str(exc), data={})
    return out


def capacity_view(dsn: str) -> dict[str, dict[str, int]]:
    view: dict[str, dict[str, int]] = {}
    for row in steward.read_budgets(dsn):
        scope = row.get("owner_scope") or "untagged"
        if scope not in CAPACITY_SCOPES:
            continue
        view[scope] = {"authorized": int(row["authorized"]), "consumed": int(row["consumed"]),
                       "reserved": int(row["reserved"]),
                       "available": int(row["authorized"]) - int(row["consumed"]) - int(row["reserved"]),
                       "occupancy": int(row["occupancy"]), "max_occupancy": int(row["max_occupancy"])}
    return view


def admit_task(dsn: str, cmd: Command) -> CommandResult:
    return steward.admit_task(dsn, cmd)


def supervision_available(dsn: str, root: str = AGENDA_ROOT) -> int:
    return capacity_view(dsn).get("supervision", {}).get("available", 0)


def seed_order(pending: list[dict[str, Any]], cursor: int = 0) -> dict[str, Any]:
    for item in pending:
        if item.get("seed_class") not in SEED_CLASSES:
            raise SettlementError(f"proposal {item.get('id')} names unknown seed class")
    lanes: dict[str, list[dict[str, Any]]] = {c: [] for c in SEED_CLASSES}
    for item in pending:
        lanes[item["seed_class"]].append(item)
    for lane in lanes.values():
        lane.sort(key=lambda item: str(item.get("id")))
    ordered: list[dict[str, Any]] = []
    start = cursor % len(SEED_CLASSES)
    rotation = SEED_CLASSES[start:] + SEED_CLASSES[:start]
    while any(lanes[c] for c in SEED_CLASSES):
        for cls in rotation:
            if lanes[cls]:
                ordered.append(lanes[cls].pop(0))
    return {"ordered": ordered, "next_cursor": (cursor + 1) % len(SEED_CLASSES)}


def propose_frontier(seed_class: str, question: str, hypothesis: str, basis: str,
                     desired_observation: str, cap: int, next_decision: str) -> dict[str, Any]:
    fields = {"question": question, "hypothesis": hypothesis, "basis": basis,
              "desired_observation": desired_observation, "next_decision": next_decision}
    for name, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise SettlementError(f"frontier proposal needs a non-empty {name}")
    if seed_class not in SEED_CLASSES:
        raise SettlementError(f"unknown seed class {seed_class!r}")
    if not isinstance(cap, int) or cap <= 0:
        raise SettlementError("frontier proposal needs a finite positive resource cap")
    return {"seed_class": seed_class, "cap": cap, **fields}


def renew_proposal(prior: dict[str, Any], changed: str, **updates: Any) -> dict[str, Any]:
    if not isinstance(changed, str) or not changed.strip():
        raise SettlementError("a renewal must name what the preceding attempt changed")
    renewed = dict(prior)
    renewed.update(updates)
    renewed["renewal_changed"] = changed
    return renewed


def collect_wakeups(dsn: str, cursor_epoch: int = 0, cursor_ordinal: int = -1,
                    messages: list[dict[str, Any]] | None = None,
                    now: datetime | None = None) -> dict[str, Any]:
    page = store.read_events(dsn, cursor_epoch, cursor_ordinal, limit=500)
    wakeups = [{"kind": "completed-op" if str(e["kind"]).startswith("work.completed") else "event",
                "ref": f"{e['epoch']}:{e['ordinal']}",
                "detail": f"{e['kind']} {e['payload']}"} for e in page["events"]]
    wakeups.extend({"kind": "deadline", "ref": a["id"],
                    "detail": f"attempt {a['id']} past deadline {a.get('deadline')}"}
                   for a in steward.due_attempts(dsn, now))
    wakeups.extend({"kind": "message", "ref": m.get("id", str(i)), "detail": m.get("text", "")}
                   for i, m in enumerate(messages or []))
    return {"wakeups": wakeups, "cursor_epoch": page["cursor_epoch"],
            "cursor_ordinal": page["cursor_ordinal"]}


def repair_scan(dsn: str, launchers: dict[str, Any]) -> broker.HeartbeatReport:
    return broker.heartbeat(dsn, launchers, gateway=None, repair_due=True)


def propose_team(benefit: str, members: list[str],
                 shared_exposure: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(benefit, str) or not benefit.strip():
        raise SettlementError("a team proposal must state its benefit over a single worker")
    if len({m for m in members if isinstance(m, str) and m}) < 2:
        raise SettlementError("a team needs at least two distinct members")
    return {"benefit": benefit, "members": list(members),
            "shared_exposure": list(shared_exposure or []), "committed": {}}


def commit_member_result(proposal: dict[str, Any], member: str, result_ref: str) -> dict[str, Any]:
    if member not in proposal["members"]:
        raise SettlementError(f"{member} is not on this team")
    if not result_ref:
        raise SettlementError("a member commitment needs a result reference")
    proposal["committed"][member] = result_ref
    return proposal


def reveal_allowed(proposal: dict[str, Any]) -> bool:
    return all(m in proposal["committed"] for m in proposal["members"])


def next_decision_for(dsn: str, attempt_id: str) -> str:
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT lifecycle FROM attempts WHERE id = %s", (attempt_id,))
            row = cur.fetchone()
            cur.execute("SELECT id, dispatch_state, reconcile_state, cancel_state FROM operations"
                        " WHERE attempt_id = %s ORDER BY id", (attempt_id,))
            ops = [dict(r) for r in cur.fetchall()]
            conn.commit()
    if row is None:
        return "unknown-attempt"
    if row["lifecycle"] != "running":
        return f"attempt-{row['lifecycle']}"
    for op in ops:
        if op["reconcile_state"] in ("conflict", "unresolved"):
            return f"reconcile-{op['id']}"
        if op["dispatch_state"] in ("dispatching", "sent", "unresolved"):
            return f"await-receipt-{op['id']}"
        if op["dispatch_state"] == "prepared":
            return f"dispatch-{op['id']}"
    return "idle" if not ops else "advance-continuation"


def agenda_snapshot(dsn: str, now: datetime | None = None) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM investigations WHERE disposition IN"
                        " ('accepted', 'amended')")
            obligations = int(cur.fetchone()["n"])
            cur.execute("SELECT id, investigation_id, lifecycle FROM attempts ORDER BY id")
            attempts = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, attempt_id, dispatch_state, reconcile_state FROM operations"
                        " WHERE dispatch_state IN ('dispatching', 'sent', 'unresolved')"
                        " OR reconcile_state IN ('conflict', 'unresolved') ORDER BY id")
            unresolved = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return {"obligations": obligations, "attempts": attempts, "unresolved_operations": unresolved,
            "capacity": capacity_view(dsn), "due": steward.due_attempts(dsn, moment)}
