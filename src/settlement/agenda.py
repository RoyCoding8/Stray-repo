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


def seed_order(pending: list[dict[str, Any]], cursor: int = 0,
               rank=None) -> dict[str, Any]:
    for item in pending:
        if item.get("seed_class") not in SEED_CLASSES:
            raise SettlementError(f"proposal {item.get('id')} names unknown seed class")
    lanes: dict[str, list[dict[str, Any]]] = {c: [] for c in SEED_CLASSES}
    for item in pending:
        lanes[item["seed_class"]].append(item)
    key = rank or (lambda item: str(item.get("id")))
    for lane in lanes.values():
        lane.sort(key=key)
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


OVERVIEW_ATTEMPT_LIMIT = 50
OVERVIEW_OPERATION_LIMIT = 200


def derive_next_decision(lifecycle: str, ops: list[dict[str, Any]]) -> str:
    if lifecycle != "running":
        return f"attempt-{lifecycle}"
    for op in ops:
        if op["reconcile_state"] in ("conflict", "unresolved"):
            return f"reconcile-{op['id']}"
        if op["dispatch_state"] in ("dispatching", "sent", "unresolved"):
            return f"await-receipt-{op['id']}"
        if op["dispatch_state"] == "prepared":
            return f"dispatch-{op['id']}"
    return "idle" if not ops else "advance-continuation"


def next_decisions_for(dsn: str, attempt_ids: list[str]) -> dict[str, str]:
    ids = list(attempt_ids)
    if not ids:
        return {}
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT a.id, a.lifecycle, o.id AS op_id, o.dispatch_state,"
                        " o.reconcile_state FROM attempts a LEFT JOIN operations o"
                        " ON o.attempt_id = a.id WHERE a.id = ANY(%s) ORDER BY a.id, o.id",
                        (ids,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = grouped.setdefault(row["id"], {"lifecycle": row["lifecycle"], "ops": []})
        if row["op_id"] is not None:
            group["ops"].append({"id": row["op_id"],
                                 "dispatch_state": row["dispatch_state"],
                                 "reconcile_state": row["reconcile_state"]})
    out = {aid: "unknown-attempt" for aid in ids}
    for aid, group in grouped.items():
        out[aid] = derive_next_decision(group["lifecycle"], group["ops"])
    return out


def next_decision_for(dsn: str, attempt_id: str) -> str:
    return next_decisions_for(dsn, [attempt_id]).get(attempt_id, "unknown-attempt")


def agenda_snapshot(dsn: str, now: datetime | None = None,
                    attempt_limit: int = OVERVIEW_ATTEMPT_LIMIT) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM investigations WHERE disposition IN"
                        " ('accepted', 'amended')")
            obligations = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM attempts")
            attempt_total = int(cur.fetchone()["n"])
            cur.execute("SELECT id, investigation_id, lifecycle FROM attempts"
                        " ORDER BY (lifecycle IN ('running', 'suspended')) DESC, id LIMIT %s",
                        (attempt_limit,))
            attempts = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, attempt_id, dispatch_state, reconcile_state FROM operations"
                        " WHERE dispatch_state IN ('dispatching', 'sent', 'unresolved')"
                        " OR reconcile_state IN ('conflict', 'unresolved') ORDER BY id LIMIT %s",
                        (OVERVIEW_OPERATION_LIMIT,))
            unresolved = [dict(r) for r in cur.fetchall()]
            try:
                extra = _agenda_options_from_cursor(cur)
            except _pgerrors.UndefinedTable:
                conn.rollback()
                extra = {"options": [], "cursor": None, "trajectories": [], "liability": 0,
                         "remaining": 0, "decisions": 0, "events": [],
                         "outcomes": [], "costs": []}
            else:
                conn.commit()
    snap: dict[str, Any] = {"obligations": obligations, "attempts": attempts,
            "attempt_total": attempt_total, "attempt_limit": attempt_limit,
            "unresolved_operations": unresolved, "capacity": capacity_view(dsn),
            "due": steward.due_attempts(dsn, moment)}
    snap.update(extra)
    return snap


AG01_OP_VERSION = "AG01-OP-1"
AG01_DECISION_COST = 1


def _agenda_option(cur, option_id: str) -> dict | None:
    cur.execute("SELECT * FROM agenda_options WHERE option_id = %s", (option_id,))
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _agenda_require_root(cur, root: str) -> None:
    cur.execute("SELECT 1 FROM allocations WHERE id = %s", (root,))
    if cur.fetchone() is None:
        raise SettlementError(f"unknown allocation root {root};"
                              " proposals cannot authorize spending")


def _agenda_root_free(cur, root: str) -> int:
    cur.execute("SELECT authorized, consumed, reserved FROM allocations WHERE id = %s", (root,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown allocation {root}")
    return int(row["authorized"]) - int(row["consumed"]) - int(row["reserved"])


def _agenda_cursor(cur, trajectory: str) -> dict:
    cur.execute("SELECT * FROM agenda_cursors WHERE trajectory = %s", (trajectory,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO agenda_cursors (trajectory) VALUES (%s)"
            " ON CONFLICT (trajectory) DO NOTHING RETURNING *",
            (trajectory,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute("SELECT * FROM agenda_cursors WHERE trajectory = %s", (trajectory,))
            row = cur.fetchone()
    return dict(row)


def _agenda_merge_deps(cur, trajectory: str, dep_versions: dict) -> dict:
    cursor = _agenda_cursor(cur, trajectory)
    merged = dict(cursor.get("dep_versions") or {})
    for key, value in (dep_versions or {}).items():
        merged[str(key)] = max(int(merged.get(str(key), 0)), int(value))
    cur.execute("UPDATE agenda_cursors SET dep_versions = %s WHERE trajectory = %s",
                (store._j(merged), trajectory))
    return merged


def _agenda_charge_decision(cur, root: str, trajectory: str) -> tuple[int, str]:
    _agenda_cursor(cur, trajectory)
    if _agenda_root_free(cur, root) < AG01_DECISION_COST:
        from .common import InsufficientResources
        raise InsufficientResources(
            f"allocation {root} cannot fund another decision; exploration is unfunded")
    cur.execute(
        "UPDATE agenda_cursors SET tick = tick + 1, epoch = tick + 1, rotation = rotation + 1"
        " WHERE trajectory = %s RETURNING tick",
        (trajectory,),
    )
    tick = int(cur.fetchone()["tick"])
    dec_op = f"ag01:{trajectory}:dec:{tick}"
    store._take_reservation(cur, root, dec_op + ":r", AG01_DECISION_COST, dec_op)
    store._settle_amount(cur, dec_op + ":r", "success")
    return tick, dec_op


def _agenda_effect_identity(root: str, option_id: str, evidence: dict,
                            probe: str, decision: str, slot: str | None) -> str:
    from .common import payload_digest
    return payload_digest({"root": root, "option": option_id,
                           "evidence": sorted((str(k), int(v)) for k, v in (evidence or {}).items()),
                           "probe": probe, "decision": decision, "slot": slot})


def _agenda_option_spend(cur, option_id: str) -> int:
    cur.execute("SELECT COALESCE(SUM(r.amount), 0) AS spend FROM agenda_attempt_links l"
                " JOIN reservations r ON r.id = l.reservation_id WHERE l.option_id = %s",
                (option_id,))
    return int(cur.fetchone()["spend"])


def _agenda_option_cap(cur, option_id: str) -> int | None:
    cur.execute("SELECT body FROM agenda_option_revisions WHERE option_id = %s"
                " ORDER BY revision DESC LIMIT 1", (option_id,))
    row = cur.fetchone()
    if row is None:
        return None
    cap = (dict(row["body"]) if not isinstance(row["body"], dict) else row["body"]).get("cap")
    return int(cap) if isinstance(cap, int) else None


def _agenda_check_option_cap(cur, option_id: str, cost: int) -> None:
    cap = _agenda_option_cap(cur, option_id)
    if cap is not None and _agenda_option_spend(cur, option_id) + cost > cap:
        from .common import InsufficientResources
        raise InsufficientResources(f"option {option_id} caps probe exposure at {cap};"
                                    " discretionary execution stops at the cap")


def _agenda_attempt_id(cur, option_id: str, probe: str, slot: str | None) -> str:
    base = f"att-{option_id}-{probe}" + (f"-{slot}" if slot else "")
    cur.execute("SELECT COUNT(*) AS n FROM agenda_attempt_links"
                " WHERE option_id = %s AND probe = %s", (option_id, probe))
    taken = int(cur.fetchone()["n"])
    return base if taken == 0 else f"{base}-{taken}"


def _agenda_concurrent_link(option_id: str) -> SettlementError:
    from .common import StaleRevision
    return StaleRevision(f"concurrent probe-slot write for {option_id};"
                         " the control lock serializes writers, so re-read and retry")


def propose_option(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        from .common import payload_digest
        p = cmd.payload
        option_id = p["option_key"]
        revision = int(p["revision"])
        root = p["allocation_root"]
        body = dict(p.get("body") or {})
        scope = str(p.get("scope", ""))
        question = str(p.get("question", ""))
        have = _agenda_option(cur, option_id)
        if have is None:
            if revision != 1:
                from .common import StaleRevision
                raise StaleRevision(f"first revision of {option_id} must be r1, not r{revision}")
            _agenda_require_root(cur, root)
            digest = payload_digest({"key": option_id, "scope": scope, "question": question,
                                     "revision": revision, "body": body})
            cur.execute(
                "INSERT INTO agenda_options (option_id, scope, question, allocation_root,"
                " revision, disposition, disposition_version)"
                " VALUES (%s, %s, %s, %s, %s, 'open', 1)",
                (option_id, scope, question, root, revision),
            )
            cur.execute(
                "INSERT INTO agenda_option_revisions (option_id, revision, request_id, body, digest)"
                " VALUES (%s, %s, %s, %s, %s)",
                (option_id, revision, cmd.request_id, store._j(body), digest),
            )
            cur.execute(
                "INSERT INTO agenda_disposition_events (option_id, version, kind, reason)"
                " VALUES (%s, 1, 'proposed', %s)",
                (option_id, f"recorded revision r{revision} under {cmd.request_id}"),
            )
            return (ResultCode.APPLIED, f"recorded revision r{revision} under {cmd.request_id}",
                    {"option_id": option_id, "revision": revision,
                     "disposition": "open", "disposition_version": 1, "digest": digest},
                    [("agenda.option_proposed", {"option_id": option_id, "revision": revision})], [])
        if cmd.expected_revision is not None and int(cmd.expected_revision) != int(have["revision"]):
            from .common import StaleRevision
            raise StaleRevision(f"stale expected revision: {option_id} is at"
                                f" r{have['revision']}, expected r{cmd.expected_revision}")
        if revision != int(have["revision"]) + 1:
            from .common import StaleRevision
            raise StaleRevision(f"stale revision: {option_id} is at"
                                f" r{have['revision']}, proposed r{revision}")
        if have["disposition"] != "open":
            raise SettlementError(f"option {option_id} is {have['disposition']}, not open;"
                                  " revisions require an open option")
        if have["allocation_root"] != root:
            raise SettlementError(f"option {option_id} is rooted at {have['allocation_root']},"
                                  f" not {root}; lineage never re-roots")
        digest = payload_digest({"key": option_id, "scope": scope, "question": question,
                                 "revision": revision, "body": body})
        try:
            cur.execute(
                "INSERT INTO agenda_option_revisions (option_id, revision, request_id, body, digest)"
                " VALUES (%s, %s, %s, %s, %s)",
                (option_id, revision, cmd.request_id, store._j(body), digest),
            )
        except _pgerrors.UniqueViolation:
            from .common import StaleRevision
            raise StaleRevision(f"concurrent revision write for {option_id} r{revision}; re-read")
        cur.execute("UPDATE agenda_options SET revision = %s, updated_at = now() WHERE option_id = %s",
                    (revision, option_id))
        return (ResultCode.APPLIED, f"recorded revision r{revision} under {cmd.request_id}",
                {"option_id": option_id, "revision": revision,
                 "disposition": have["disposition"],
                 "disposition_version": int(have["disposition_version"]), "digest": digest},
                [("agenda.option_proposed", {"option_id": option_id, "revision": revision})], [])
    return store.transact(dsn, cmd, _fn)


def select_and_admit(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        from . import broker as _broker
        p = cmd.payload
        trajectory = p["trajectory"]
        option_id = p["option_id"]
        probe = p["probe"]
        intended = p["intended_decision"]
        slot = p.get("replication_slot")
        policy = str(p["policy_version"])
        digest = str(p["input_digest"])
        expected_revision = p.get("expected_option_revision")
        dep_versions = {str(k): int(v) for k, v in (p.get("dep_versions") or {}).items()}
        cost = int(p["cost"])
        if cost <= 0:
            raise SettlementError("admission needs a finite positive probe cost")
        if not policy or not digest:
            raise SettlementError("admission binds the selecting policy and input digest")
        opt = _agenda_option(cur, option_id)
        if opt is None:
            raise SettlementError(f"unknown option {option_id}")
        if opt["disposition"] != "open":
            raise SettlementError(f"option {option_id} is {opt['disposition']}, not open;"
                                  " admission requires an open option")
        if expected_revision is not None and int(expected_revision) != int(opt["revision"]):
            from .common import StaleRevision
            raise StaleRevision(f"stale selection: {option_id} is at r{opt['revision']},"
                                f" selected r{expected_revision}; re-select before admission")
        root = opt["allocation_root"]
        if _agenda_root_free(cur, root) < AG01_DECISION_COST + cost:
            from .common import InsufficientResources
            raise InsufficientResources(
                f"allocation {root} cannot cover decision plus {cost} exposure;"
                " discretionary execution stops at the cap")
        _agenda_check_option_cap(cur, option_id, cost)
        tick, dec_op = _agenda_charge_decision(cur, root, trajectory)
        identity = _agenda_effect_identity(root, option_id, dep_versions, probe, intended, slot)
        cur.execute("SELECT attempt_id FROM agenda_attempt_links WHERE effect_identity = %s",
                    (identity,))
        dup = cur.fetchone()
        if dup is not None:
            return (ResultCode.ALREADY_APPLIED,
                    f"duplicate intended effect: probe {probe} for {option_id}"
                    f" already bound to {dup['attempt_id']}; no second effect,"
                    " the new decision is charged",
                    {"option_id": option_id, "attempt_id": dup["attempt_id"],
                     "effect_identity": identity, "dec_op": dec_op,
                     "tick": tick},
                    [], [])
        attempt_id = _agenda_attempt_id(cur, option_id, probe, slot)
        acquired = store._acquire_work(cur, investigation_id=_agenda_inv(trajectory),
                                       attempt_id=attempt_id, allocation_id=root,
                                       composition=probe, model=policy, owner=trajectory)
        sample = _agenda_sample_index(cur, trajectory, probe)
        probe_op = f"ag01:{trajectory}:probe:{tick}"
        probe_res = probe_op + ":r"
        store._take_reservation(cur, root, probe_res, cost, probe_op)
        _agenda_merge_deps(cur, trajectory, dep_versions)
        op_input = {"probe": probe, "sample": sample, "attempt_id": attempt_id,
                    "observed": list(p.get("observed_plan") or []),
                    "product": list(p.get("product_plan") or []),
                    "dud": bool(p.get("dud_plan", False)),
                    "dep_versions": dict(dep_versions),
                    "receipt_base": f"{trajectory}:rc:{attempt_id}",
                    "epoch": int(p.get("due_epoch", tick))}
        prepared = store._prepare_operation(
            cur, int(control["authority_version"]), operation_id=probe_op,
            attempt_id=attempt_id, allocation_id=root, operation={
                "effect": _broker.OBSERVATION_ADAPTER,
                "payload": {"adapter": _broker.AG01_PROBE_ADAPTER, "input": op_input},
                "retries": 0, "budget_kind": "recorded-exposure"},
            execution_version=AG01_OP_VERSION)
        if not prepared["prepared"]:
            raise SettlementError(f"operation {probe_op} already prepared with other intent")
        try:
            cur.execute(
                "INSERT INTO agenda_attempt_links (attempt_id, trajectory, option_id,"
                " option_revision, probe, intended_decision, replication_slot, effect_identity,"
                " operation_id, reservation_id, state)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'admitted')",
                (attempt_id, trajectory, option_id, int(opt["revision"]), probe, intended, slot,
                 identity, probe_op, probe_res),
            )
        except _pgerrors.UniqueViolation:
            raise _agenda_concurrent_link(option_id)
        selection = {"option_id": option_id, "kind": "initial", "probe": probe, "cost": cost,
                     "attempt_id": attempt_id, "option_revision": int(opt["revision"]),
                     "policy_version": policy, "input_digest": digest,
                     "ownership_generation": acquired["ownership_generation"]}
        cur.execute(
            "INSERT INTO agenda_decisions (trajectory, tick, policy_version, selection, reasons)"
            " VALUES (%s, %s, %s, %s, %s)",
            (trajectory, tick, policy, store._j(selection),
             store._j([f"selected:{option_id}"])),
        )
        return (ResultCode.APPLIED,
                f"funded {attempt_id}: revision r{opt['revision']} rechecked,"
                f" exposure {cost} reserved as {probe_op}; decision charged as {dec_op}",
                {"option_id": option_id, "attempt_id": attempt_id,
                 "effect_identity": identity, "dec_op": dec_op,
                 "probe_op": probe_op, "tick": tick, "sample": sample,
                 "operation_id": probe_op},
                [("agenda.admitted", {"option_id": option_id, "attempt_id": attempt_id,
                                      "tick": tick})], [])
    return store.transact(dsn, cmd, _fn)


def _agenda_resolve_receipt(cur, link: dict, receipt: str) -> tuple[dict, dict]:
    cur.execute("SELECT * FROM receipts WHERE receipt_identity = %s", (receipt,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown receipt {receipt};"
                              " outcomes link validated durable evidence only")
    row = dict(row)
    if row["operation_id"] != link["operation_id"]:
        raise SettlementError(f"wrong operation: receipt {receipt} belongs to"
                              f" {row['operation_id']}, not {link['operation_id']};"
                              " outcomes cite their own execution only")
    cur.execute("SELECT 1 FROM receipt_conflicts WHERE receipt_identity = %s", (receipt,))
    if cur.fetchone() is not None:
        raise SettlementError(f"conflicting receipt {receipt} is preserved"
                              " for reconciliation; it justifies no outcome")
    content = dict(row.get("content") or {})
    if content.get("source_attempt") != link["attempt_id"]:
        raise SettlementError(f"wrong attempt: receipt {receipt} reports"
                              f" {content.get('source_attempt')}, not {link['attempt_id']}")
    return row, content


def _agenda_check_plan(cur, link: dict, content: dict) -> None:
    cur.execute("SELECT payload FROM operations WHERE id = %s", (link["operation_id"],))
    row = cur.fetchone()
    plan = (((dict(row.get("payload") or {}).get("payload", {}))
             if row is not None else {}).get("input", {}))
    kind = content.get("kind")
    if kind == "observation":
        for entry in plan.get("observed", []):
            if (entry.get("prop") == content.get("prop")
                    and entry.get("scope") == content.get("scope")
                    and entry.get("dep") == content.get("dep")):
                return
        raise SettlementError("receipt content matches no planned measurement;"
                              " fabricated observations justify no outcome")
    if kind == "product-claims":
        if set((content.get("claims") or {})) != set(plan.get("product", [])):
            raise SettlementError("product claims match no planned claim set;"
                                  " fabricated claims justify no outcome")
        return
    if kind == "dud" and plan.get("dud") is True:
        return
    raise SettlementError(f"receipt kind {kind!r} matches no planned measurement;"
                          " fabricated observations justify no outcome")


def record_outcome(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        option_id = p["option_id"]
        attempt_id = p["attempt_id"]
        receipt = str(p.get("receipt_identity") or "")
        scored = bool(p.get("scored", True))
        if not receipt:
            raise SettlementError("an outcome links a receipt identity")
        cur.execute("SELECT * FROM agenda_attempt_links WHERE attempt_id = %s", (attempt_id,))
        link = cur.fetchone()
        if link is None or link["option_id"] != option_id:
            raise SettlementError(f"wrong attempt: {attempt_id} is not bound to {option_id};"
                                  " outcomes cite actual bound attempts only")
        link = dict(link)
        _, content = _agenda_resolve_receipt(cur, link, receipt)
        value = content.get("value", "unknown")
        if value not in ("true", "false", "unknown"):
            raise SettlementError("observation value must be true, false or unknown;"
                                  " uncertainty is preserved, never rounded up")
        _agenda_check_plan(cur, link, content)
        cursor = _agenda_cursor(cur, link["trajectory"])
        deps = dict(cursor.get("dep_versions") or {})
        want = int(content.get("epoch", -1))
        if want > int(cursor["epoch"]):
            raise SettlementError(f"future-epoch support refused: cited {want},"
                                  f" current {cursor['epoch']}")
        if content.get("kind") == "observation":
            dep, ver = str(content.get("dep", "")), int(content.get("dep_version", -1))
            now = int(deps.get(dep, ver))
            if ver != now:
                raise SettlementError(f"invalidated support refused: {dep} cited at v{ver},"
                                      f" current v{now}; a changed dependency voids the result")
        cur.execute("SELECT observation FROM agenda_outcomes WHERE receipt_identity = %s",
                    (receipt,))
        have = cur.fetchone()
        stored = {"kind": content.get("kind", "observation"),
                  "prop": content.get("prop"), "scope": content.get("scope"),
                  "dep": content.get("dep"), "dep_version": content.get("dep_version"),
                  "value": value, "source_attempt": attempt_id, "receipt": receipt,
                  "epoch": want, "simulated": content.get("simulated", False)}
        if content.get("kind") == "product-claims":
            stored["claims"] = dict(content.get("claims") or {})
        if have is not None:
            if dict(have["observation"]) == stored:
                return (ResultCode.ALREADY_APPLIED,
                        f"receipt {receipt} already recorded; no duplicate effect",
                        {"option_id": option_id, "attempt_id": attempt_id,
                         "receipt": receipt, "observation": stored},
                        [], [])
            raise SettlementError(f"receipt {receipt} already recorded with other content;"
                                  " reattribution justifies no outcome")
        cur.execute(
            "INSERT INTO agenda_outcomes (receipt_identity, option_id, attempt_id, observation,"
            " epoch, scored) VALUES (%s, %s, %s, %s, %s, %s)",
            (receipt, option_id, attempt_id, store._j(stored), want, scored),
        )
        settled = None
        measured = value != "unknown" or content.get("kind") == "product-claims"
        if measured and link["state"] == "admitted":
            done, _, _ = store._settle_amount(cur, link["reservation_id"], "success")
            if done:
                cur.execute("UPDATE agenda_attempt_links SET state = 'settled' WHERE attempt_id = %s",
                            (attempt_id,))
                settled = link["operation_id"]
        if settled:
            tail = f" probe exposure settled as {settled}"
        elif value == "unknown" and content.get("kind") != "product-claims":
            tail = (" unresolved result remains unknown: probe exposure retained"
                    " as outstanding liability")
        else:
            tail = " probe exposure was already settled"
        return (ResultCode.APPLIED, f"linked {receipt} to {attempt_id} at epoch {want};" + tail,
                {"option_id": option_id, "attempt_id": attempt_id, "receipt": receipt,
                 "settled_probe": settled, "observation": stored},
                [("agenda.outcome_recorded", {"option_id": option_id, "attempt_id": attempt_id,
                                              "receipt": receipt})], [])
    return store.transact(dsn, cmd, _fn)


def _agenda_inv(trajectory: str) -> str:
    return f"ag01-inv-{trajectory}"


def _agenda_sample_index(cur, trajectory: str, probe: str) -> int:
    cur.execute("SELECT COUNT(*) AS n FROM agenda_attempt_links"
                " WHERE trajectory = %s AND probe = %s", (trajectory, probe))
    return int(cur.fetchone()["n"])


def _agenda_refuse(cur, trajectory, tick, dec_op, option_id, kind, reason,
                   policy: str) -> tuple:
    selection = {"option_id": option_id, "kind": kind, "decision": "refused",
                 "policy_version": policy}
    cur.execute(
        "INSERT INTO agenda_decisions (trajectory, tick, policy_version, selection, reasons)"
        " VALUES (%s, %s, %s, %s, %s)",
        (trajectory, tick, policy, store._j(selection), store._j([reason])),
    )
    return (ResultCode.INVALID_INPUT, f"justified refusal: {reason}; decision charged as {dec_op}",
            {"option_id": option_id, "decision": "refused", "reason": reason, "dec_op": dec_op},
            [("agenda.continuation_refused", {"option_id": option_id, "tick": tick})], [])


def _agenda_parse_slot(slot: str, next_probe: str) -> tuple[int, int]:
    try:
        kind, base, tail = str(slot).split(":", 2)
        taken, total = tail.split("-of-")
        k, n = int(taken), int(total)
    except (ValueError, AttributeError):
        raise SettlementError(f"malformed replication slot {slot!r};"
                              " slots read repl:<probe>:<k>-of-<N>")
    if kind != "repl" or base != next_probe:
        raise SettlementError(f"slot {slot!r} does not name probe {next_probe}")
    if n <= 0 or k < 0:
        raise SettlementError(f"slot {slot!r} carries no finite remaining obligation")
    return k, n


def _agenda_slot_denied(cur, trajectory: str, next_probe: str,
                        slot: str) -> str | None:
    k, n = _agenda_parse_slot(slot, next_probe)
    cur.execute("SELECT DISTINCT replication_slot FROM agenda_attempt_links"
                " WHERE trajectory = %s AND probe = %s AND replication_slot IS NOT NULL",
                (trajectory, next_probe))
    for row in cur.fetchall():
        try:
            _, other_n = _agenda_parse_slot(row["replication_slot"], next_probe)
        except SettlementError:
            continue
        if other_n != n:
            return (f"protocol drift: slot {slot!r} declares {n} samples but"
                    f" {row['replication_slot']!r} already froze the protocol;"
                    " replication follows the predeclared finite plan")
    taken = _agenda_sample_index(cur, trajectory, next_probe)
    if k != taken:
        return (f"slot {slot!r} claims sample {k} but {taken} samples are taken;"
                " slots advance in order, never skipped or repeated")
    if k >= n:
        return (f"slot {slot!r} exceeds the frozen plan of {n} samples;"
                " the stopping condition is already reached")
    return None


def submit_continuation(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        from . import broker as _broker
        from .agenda_policy import POLICY_Q_VERSION, qualify_continuation
        p = cmd.payload
        option_id = p["option_id"]
        parent_attempt = p["parent_attempt"]
        cites = list(p.get("observation_refs") or [])
        next_probe = p["next_probe"]
        intended = p["intended_decision"]
        residual = p["residual_question"]
        res_q = residual if isinstance(residual, dict) else {"prop": residual}
        policy = str(p["policy_version"])
        digest = str(p["input_digest"])
        expected_revision = p.get("expected_option_revision")
        slot = p.get("replication_slot")
        cost = int(p["cost"])
        if cost <= 0:
            raise SettlementError("a continuation needs a finite positive probe cost")
        if not next_probe or not residual:
            raise SettlementError("a continuation names its next probe and residual question")
        if not policy or not digest or not intended:
            raise SettlementError("a continuation binds its policy, input digest and intent")
        opt = _agenda_option(cur, option_id)
        if opt is None:
            raise SettlementError(f"unknown option {option_id}")
        if opt["disposition"] != "open":
            raise SettlementError(f"option {option_id} is {opt['disposition']}, not open;"
                                  " continuations require an open option")
        if expected_revision is not None and int(expected_revision) != int(opt["revision"]):
            from .common import StaleRevision
            raise StaleRevision(f"stale selection: {option_id} is at r{opt['revision']},"
                                f" selected r{expected_revision}; re-select before admission")
        root = opt["allocation_root"]
        cur.execute("SELECT * FROM agenda_attempt_links WHERE attempt_id = %s", (parent_attempt,))
        parent = cur.fetchone()
        if parent is None or parent["option_id"] != option_id:
            raise SettlementError(f"wrong parent: {parent_attempt} is not bound to {option_id};"
                                  " continuations link a real parent attempt")
        trajectory = parent["trajectory"]
        if _agenda_root_free(cur, root) < AG01_DECISION_COST:
            from .common import InsufficientResources
            raise InsufficientResources(
                f"allocation {root} cannot fund another decision; exploration is unfunded")
        tick, dec_op = _agenda_charge_decision(cur, root, trajectory)
        cursor = _agenda_cursor(cur, trajectory)
        deps = dict(cursor.get("dep_versions") or {})
        cur.execute("SELECT * FROM agenda_outcomes WHERE option_id = %s AND receipt_identity = ANY(%s)"
                    " ORDER BY receipt_identity", (option_id, sorted(set(cites))))
        rows = [dict(r) for r in cur.fetchall()]
        if len(rows) != len(set(cites)):
            found = {r["receipt_identity"] for r in rows}
            raise SettlementError(f"missing support: only {sorted(found)} found;"
                                  " continuations cite durable receipts only")
        cited = [(dict(r)["observation"], dict(r)["receipt_identity"]) for r in rows]
        for obs, receipt in cited:
            dep, ver = str(obs.get("dep", "")), int(obs.get("dep_version", -1))
            now = int(deps.get(dep, ver))
            if ver < now:
                return _agenda_refuse(cur, trajectory, tick, dec_op, option_id, "continuation",
                                      f"stale evidence: {dep} cited at v{ver}, current v{now};"
                                      " a changed dependency invalidates the old result,"
                                      " it does not qualify the new probe by itself", policy)
            if ver > now:
                return _agenda_refuse(cur, trajectory, tick, dec_op, option_id, "continuation",
                                      f"cited {dep} v{ver} is newer than current v{now};"
                                      " support from the future justifies no probe", policy)
        for obs, receipt in cited:
            if obs.get("value") == "unknown":
                return _agenda_refuse(cur, trajectory, tick, dec_op, option_id, "continuation",
                                      f"unresolved result remains unknown ({receipt});"
                                      " an unknown observation justifies no probe", policy)
        usable = [obs for obs, _ in cited
                  if obs.get("scope") == opt["scope"] and obs.get("value") in ("true", "false")]
        if not usable:
            return _agenda_refuse(cur, trajectory, tick, dec_op, option_id, "continuation",
                                  f"cited observations say nothing usable about scope {opt['scope']};"
                                  " paraphrase and novelty are not qualification", policy)
        cur.execute("SELECT receipt_identity FROM agenda_outcomes WHERE option_id = %s"
                    " AND grounded", (option_id,))
        grounded = {r["receipt_identity"] for r in cur.fetchall()}
        if cites and all(rc in grounded for _, rc in cited):
            return _agenda_refuse(cur, trajectory, tick, dec_op, option_id, "continuation",
                                  f"distinction already settled by {sorted(grounded)};"
                                  " re-citing grounded support justifies no probe", policy)
        if slot is not None:
            denied = _agenda_slot_denied(cur, trajectory, next_probe, slot)
            if denied is not None:
                return _agenda_refuse(cur, trajectory, tick, dec_op, option_id, "continuation",
                                      denied, policy)
        if policy == POLICY_Q_VERSION:
            decl = dict(p.get("next_probe_decl") or {})
            outs = decl.get("outcomes")
            if not isinstance(decl.get("question"), dict) or not isinstance(outs, list):
                raise SettlementError("a Q-armed continuation declares its next probe"
                                      " question and outcomes in the limited language")
            rep = p.get("replication")
            if slot is not None:
                if not isinstance(rep, dict):
                    raise SettlementError("a slotted continuation carries its replication record")
                taken = _agenda_sample_index(cur, trajectory, next_probe)
                if int(rep.get("completed", -1)) != taken:
                    raise SettlementError("replication progress is read from durable outcomes,"
                                          " never asserted by the caller")
            record = {"parent_attempt": parent_attempt,
                      "cited": [{"prop": o.get("prop"), "scope": o.get("scope"),
                                 "dep": o.get("dep"), "dep_version": o.get("dep_version")}
                                for o in usable],
                      "residual_question": res_q,
                      "next_probe": {"id": next_probe, "question": decl["question"],
                                     "outcomes": outs},
                      "scope": opt["scope"], "replication": rep,
                      "stop_condition": p.get("stop_condition"),
                      "decision_before": str(p.get("decision_before", "")),
                      "decision_after": str(p.get("decision_after", ""))}
            verdict = qualify_continuation(record, usable, {"dep_versions": deps})
            if not verdict["qualified"]:
                return _agenda_refuse(cur, trajectory, tick, dec_op, option_id, "continuation",
                                      "unqualified continuation: "
                                      + "; ".join(verdict["reasons"]), policy)
            route = "qualified " + str(verdict["route"]) + ": " + "; ".join(verdict["reasons"])
        else:
            route = ("mechanically valid continuation: open option, bound parent, durable"
                     " current in-scope support, no duplicate effect")
        attempt_id = _agenda_attempt_id(cur, option_id, next_probe, slot)
        identity = _agenda_effect_identity(root, option_id, deps, next_probe, intended, slot)
        cur.execute("SELECT attempt_id FROM agenda_attempt_links WHERE effect_identity = %s",
                    (identity,))
        clash = cur.fetchone()
        if clash is not None:
            return (ResultCode.ALREADY_APPLIED,
                    f"duplicate intended effect: continuation probe {next_probe}"
                    f" already bound to {clash['attempt_id']}; no second effect,"
                    " the new decision is charged",
                    {"option_id": option_id, "attempt_id": clash["attempt_id"],
                     "dec_op": dec_op, "tick": tick}, [], [])
        _agenda_check_option_cap(cur, option_id, cost)
        if _agenda_root_free(cur, root) < cost:
            from .common import InsufficientResources
            raise InsufficientResources(f"allocation {root} cannot cover {cost} exposure;"
                                        " discretionary execution stops at the cap")
        acquired = store._acquire_work(cur, investigation_id=_agenda_inv(trajectory),
                                       attempt_id=attempt_id, allocation_id=root,
                                       composition=next_probe, model=policy, owner=trajectory)
        sample = _agenda_sample_index(cur, trajectory, next_probe)
        probe_op = f"ag01:{trajectory}:probe:{tick}c"
        probe_res = probe_op + ":r"
        store._take_reservation(cur, root, probe_res, cost, probe_op)
        op_input = {"probe": next_probe, "sample": sample, "attempt_id": attempt_id,
                    "observed": list(p.get("observed_plan") or []),
                    "product": list(p.get("product_plan") or []),
                    "dud": bool(p.get("dud_plan", False)),
                    "dep_versions": dict(deps),
                    "receipt_base": f"{trajectory}:rc:{attempt_id}",
                    "epoch": int(p.get("due_epoch", tick))}
        prepared = store._prepare_operation(
            cur, int(control["authority_version"]), operation_id=probe_op,
            attempt_id=attempt_id, allocation_id=root, operation={
                "effect": _broker.OBSERVATION_ADAPTER,
                "payload": {"adapter": _broker.AG01_PROBE_ADAPTER, "input": op_input},
                "retries": 0, "budget_kind": "recorded-exposure"},
            execution_version=AG01_OP_VERSION)
        if not prepared["prepared"]:
            raise SettlementError(f"operation {probe_op} already prepared with other intent")
        try:
            cur.execute(
                "INSERT INTO agenda_attempt_links (attempt_id, trajectory, option_id,"
                " option_revision, probe, intended_decision, replication_slot, effect_identity,"
                " operation_id, reservation_id, state)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'admitted')",
                (attempt_id, trajectory, option_id, int(opt["revision"]), next_probe,
                 intended, slot, identity, probe_op, probe_res),
            )
        except _pgerrors.UniqueViolation:
            raise _agenda_concurrent_link(option_id)
        cur.execute("UPDATE agenda_outcomes SET grounded = TRUE WHERE receipt_identity = ANY(%s)",
                    (sorted({rc for _, rc in cited}),))
        selection = {"option_id": option_id, "kind": "continuation", "probe": next_probe,
                     "cost": cost, "attempt_id": attempt_id, "decision": "useful-continuation",
                     "route": route, "option_revision": int(opt["revision"]),
                     "policy_version": policy, "input_digest": digest,
                     "ownership_generation": acquired["ownership_generation"]}
        cur.execute(
            "INSERT INTO agenda_decisions (trajectory, tick, policy_version, selection, reasons)"
            " VALUES (%s, %s, %s, %s, %s)",
            (trajectory, tick, policy, store._j(selection), store._j([route])),
        )
        return (ResultCode.APPLIED,
                f"useful continuation: {route}: {attempt_id} addresses {residual};"
                f" exposure {cost} reserved as {probe_op}; decision charged as {dec_op}",
                {"option_id": option_id, "decision": "useful-continuation", "route": route,
                 "attempt_id": attempt_id, "dec_op": dec_op, "probe_op": probe_op,
                 "sample": sample, "operation_id": probe_op},
                [("agenda.continued", {"option_id": option_id, "attempt_id": attempt_id,
                                       "tick": tick})], [])
    return store.transact(dsn, cmd, _fn)


def _agenda_normalize_wake(cond: dict, deps: dict) -> dict:
    out = dict(cond or {})
    kind = out.get("type")
    if kind == "evidence-change":
        if not out.get("dep"):
            raise SettlementError("an evidence-change wake condition names its dependency")
        if not isinstance(out.get("known_version"), int):
            observed = out.get("observed_version")
            out["known_version"] = int(observed) if isinstance(observed, int) \
                else int(deps.get(str(out["dep"]), 0))
    elif kind == "prerequisite-version":
        if not out.get("name") and out.get("ref"):
            out["name"] = out["ref"]
        if not out.get("name") or not isinstance(out.get("min_version"), int):
            version = out.get("version")
            out["min_version"] = int(version) if isinstance(version, int) else 0
        if not out.get("name"):
            raise SettlementError("a prerequisite-version wake condition names its prerequisite")
    elif kind == "authorized-scan-due":
        if not out.get("scan_id") and out.get("scan"):
            out["scan_id"] = out["scan"]
        if not out.get("scan_id") and out.get("ref"):
            out["scan_id"] = out["ref"]
        if not out.get("scan_id"):
            raise SettlementError("an authorized-scan-due wake condition names its scan")
        if not isinstance(out.get("due_epoch"), int):
            out["due_epoch"] = 0
    else:
        raise SettlementError(f"unknown wake condition type {kind!r}; typed predicates only")
    return out


def _agenda_rest(dsn: str, cmd: Command, kind: str) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        option_id = p["option_id"]
        expected = p.get("expected_disposition_version")
        reason = str(p.get("reason", ""))
        if not reason:
            raise SettlementError(f"{kind} records its reason")
        opt = _agenda_option(cur, option_id)
        if opt is None:
            raise SettlementError(f"unknown option {option_id}")
        if expected is not None and int(expected) != int(opt["disposition_version"]):
            from .common import StaleRevision
            raise StaleRevision(f"stale disposition version: {option_id} is at"
                                f" v{opt['disposition_version']}, expected v{expected}")
        version = int(opt["disposition_version"]) + 1
        wake = None
        answer = None
        if kind == "dormant":
            deps: dict = {}
            cur.execute("SELECT trajectory FROM agenda_attempt_links WHERE option_id = %s LIMIT 1",
                        (option_id,))
            seen = cur.fetchone()
            if seen is not None:
                deps = dict(_agenda_cursor(cur, seen["trajectory"]).get("dep_versions") or {})
            wake = _agenda_normalize_wake(dict(p.get("wake_condition") or {}), deps)
        if kind == "answered":
            answer = str(p.get("answer", ""))
            if not answer:
                raise SettlementError("an answer records its content")
        cur.execute("UPDATE agenda_options SET disposition = %s, disposition_version = %s,"
                    " wake_condition = %s, answer = %s, updated_at = now() WHERE option_id = %s",
                    (kind, version, store._j(wake) if wake else None, answer, option_id))
        decided = p.get("decided_by")
        cur.execute(
            "INSERT INTO agenda_disposition_events (option_id, version, kind, reason, decided_by)"
            " VALUES (%s, %s, %s, %s, %s)",
            (option_id, version, kind, reason,
             store._j(dict(decided)) if isinstance(decided, dict) else None),
        )
        tail = "" if wake is None else f" wake when {wake.get('type')}:{wake.get('dep', '')}"
        return (ResultCode.APPLIED, f"{option_id} is now {kind} at v{version}: {reason}.{tail}",
                {"option_id": option_id, "disposition": kind,
                 "disposition_version": version, "wake_condition": wake},
                [(f"agenda.{kind}", {"option_id": option_id, "version": version})], [])
    return store.transact(dsn, cmd, _fn)


def set_dormant(dsn: str, cmd: Command) -> CommandResult:
    return _agenda_rest(dsn, cmd, "dormant")


def answer_option(dsn: str, cmd: Command) -> CommandResult:
    return _agenda_rest(dsn, cmd, "answered")


def retire_option(dsn: str, cmd: Command) -> CommandResult:
    return _agenda_rest(dsn, cmd, "retired")


def note_dep_version(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        trajectory, dep, version = p["trajectory"], str(p["dep"]), int(p["version"])
        cursor = _agenda_cursor(cur, trajectory)
        have = dict(cursor.get("dep_versions") or {})
        if int(have.get(dep, 0)) >= version:
            return (ResultCode.ALREADY_APPLIED,
                    f"dep {dep} already at v{have.get(dep)}; no regression",
                    {"trajectory": trajectory, "dep": dep,
                     "version": int(have.get(dep, 0))},
                    [], [])
        _agenda_merge_deps(cur, trajectory, {dep: version})
        return (ResultCode.APPLIED, f"dep {dep} advanced to v{version} for {trajectory}",
                {"trajectory": trajectory, "dep": dep, "version": version},
                [("agenda.dep_bumped", {"trajectory": trajectory, "dep": dep,
                                        "version": version})], [])
    return store.transact(dsn, cmd, _fn)


def process_wake(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        from .agenda_policy import match_wake
        p = cmd.payload
        option_id = p["option_id"]
        event = dict(p.get("event") or {})
        identity = str(event.get("identity", ""))
        if not identity:
            raise SettlementError("a wake event carries an identity")
        cur.execute("SELECT matched FROM agenda_wake_log WHERE option_id = %s AND event_identity = %s",
                    (option_id, identity))
        if cur.fetchone() is not None:
            return (ResultCode.ALREADY_APPLIED,
                    f"duplicate delivery of {identity} ignored; wake log dedups (option, event)",
                    {"option_id": option_id, "woke": False}, [], [])
        opt = _agenda_option(cur, option_id)
        if opt is None:
            raise SettlementError(f"unknown option {option_id}")
        cur.execute("INSERT INTO agenda_wake_log (option_id, event_identity, matched)"
                    " VALUES (%s, %s, FALSE)", (option_id, identity))
        if opt["disposition"] == "retired":
            raise SettlementError(f"retired work is never revived: {identity}"
                                  f" cannot reopen {option_id}")
        if opt["disposition"] != "dormant":
            return (ResultCode.APPLIED,
                    f"nothing to wake: {option_id} is {opt['disposition']}; {identity} recorded",
                    {"option_id": option_id, "woke": False},
                    [("agenda.wake_ignored", {"option_id": option_id})], [])
        if event.get("kind") not in ("evidence-changed", "prerequisite-available",
                                           "scan-authorized"):
            cond = dict(opt["wake_condition"] or {})
            return (ResultCode.APPLIED,
                    f"ignored: event {identity} carries no typed evidence;"
                    f" condition needs {cond.get('type')}; dormancy untouched",
                    {"option_id": option_id, "woke": False},
                    [("agenda.wake_ignored", {"option_id": option_id})], [])
        verdict = match_wake(dict(opt["wake_condition"] or {}), event)
        if not verdict.get("matched"):
            why = "; ".join(verdict.get("reasons", ["no-match"]))
            return (ResultCode.APPLIED, f"ignored: {why}",
                    {"option_id": option_id, "woke": False},
                    [("agenda.wake_ignored", {"option_id": option_id})], [])
        match = "; ".join(verdict.get("reasons", ["matched"]))
        version = int(opt["disposition_version"]) + 1
        cur.execute("UPDATE agenda_options SET disposition = 'open', disposition_version = %s,"
                    " updated_at = now() WHERE option_id = %s", (version, option_id))
        cur.execute(
            "INSERT INTO agenda_disposition_events (option_id, version, kind, reason)"
            " VALUES (%s, %s, 'woken', %s)",
            (option_id, version, match),
        )
        cur.execute("UPDATE agenda_wake_log SET matched = TRUE WHERE option_id = %s"
                    " AND event_identity = %s", (option_id, identity))
        if event.get("kind") == "evidence-changed" and event.get("dep"):
            cur.execute("SELECT trajectory FROM agenda_attempt_links WHERE option_id = %s LIMIT 1",
                        (option_id,))
            seen = cur.fetchone()
            if seen is not None and isinstance(event.get("version"), int):
                _agenda_merge_deps(cur, seen["trajectory"], {str(event["dep"]): int(event["version"])})
        return (ResultCode.APPLIED, f"{option_id} reopened at v{version}: {match}",
                {"option_id": option_id, "woke": True, "disposition_version": version},
                [("agenda.woken", {"option_id": option_id, "version": version})], [])
    return store.transact(dsn, cmd, _fn)


def note_idle(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        trajectory = p["trajectory"]
        policy = str(p["policy_version"])
        if not policy:
            raise SettlementError("idling binds the deciding policy")
        reason = str(p.get("reason", "no affordable probe; idling preserves the budget"))
        cur.execute("SELECT o.allocation_root AS root FROM agenda_attempt_links l"
                    " JOIN agenda_options o ON o.option_id = l.option_id"
                    " WHERE l.trajectory = %s LIMIT 1", (trajectory,))
        found = cur.fetchone()
        if found is None:
            cur.execute("SELECT id AS root FROM allocations WHERE domain = 'agenda01'"
                        " ORDER BY id LIMIT 1")
            found = cur.fetchone()
        if found is None:
            raise SettlementError("no agenda allocation exists; nothing can idle")
        root = found["root"]
        tick, dec_op = _agenda_charge_decision(cur, root, trajectory)
        selection = {"decision": "idle"}
        cur.execute(
            "INSERT INTO agenda_decisions (trajectory, tick, policy_version, selection, reasons)"
            " VALUES (%s, %s, %s, %s, %s)",
            (trajectory, tick, policy, store._j(selection), store._j([reason])),
        )
        return (ResultCode.APPLIED, f"idle at tick {tick}: {reason}; decision charged as {dec_op}",
                {"trajectory": trajectory, "tick": tick, "dec_op": dec_op},
                [("agenda.idle", {"trajectory": trajectory, "tick": tick})], [])
    return store.transact(dsn, cmd, _fn)


def explain_eligibility(dsn: str, option_id: str) -> dict[str, Any]:
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM agenda_options WHERE option_id = %s", (option_id,))
            row = cur.fetchone()
            if row is None:
                raise SettlementError(f"unknown option {option_id}")
            opt = dict(row)
            cur.execute("SELECT attempt_id, probe, intended_decision, state, operation_id"
                        " FROM agenda_attempt_links WHERE option_id = %s ORDER BY attempt_id",
                        (option_id,))
            attempts = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT receipt_identity, epoch, grounded FROM agenda_outcomes"
                        " WHERE option_id = %s ORDER BY receipt_identity", (option_id,))
            outcomes = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT kind, reason, version FROM agenda_disposition_events"
                        " WHERE option_id = %s ORDER BY version, id", (option_id,))
            events = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT authorized, consumed, reserved FROM allocations WHERE id = %s",
                        (opt["allocation_root"],))
            alloc = cur.fetchone()
            conn.commit()
    reasons = [f"open at r{opt['revision']}" if opt["disposition"] == "open"
               else f"blocked: {opt['disposition']}"]
    if opt["disposition"] == "dormant":
        cond = dict(opt["wake_condition"] or {})
        reasons.append(f"dormant: {events[-1]['reason'] if events else 'no recorded reason'};"
                       f" wake when {cond.get('type')}:{cond.get('dep', '')}")
    if opt["disposition"] == "retired":
        reasons.append("retired work is never revived")
    if opt["disposition"] == "answered":
        reasons.append("already answered; no open question")
    held = [a for a in attempts if a["state"] == "admitted"]
    if held:
        reasons.append(f"pending effects keep liability:"
                       f" {','.join(a['operation_id'] for a in held)}")
    costs: dict[str, int] = {"authorized": 0, "consumed": 0, "reserved": 0}
    if alloc is not None:
        costs = {k: int(alloc[k]) for k in costs}
    return {"option_id": option_id, "eligible": opt["disposition"] == "open",
            "disposition": opt["disposition"], "revision": int(opt["revision"]),
            "disposition_version": int(opt["disposition_version"]),
            "wake_condition": dict(opt["wake_condition"] or {}),
            "reasons": reasons, "attempts": attempts, "outcomes": outcomes,
            "events": events, "costs": costs}


def _agenda_options_from_cursor(cur) -> dict[str, Any]:
    cur.execute("SELECT option_id, scope, revision, disposition, disposition_version,"
                " wake_condition, allocation_root FROM agenda_options ORDER BY option_id")
    options = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM agenda_cursors ORDER BY trajectory")
    cursors = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COALESCE(SUM(authorized), 0) AS a, COALESCE(SUM(consumed), 0) AS c,"
                " COALESCE(SUM(reserved), 0) AS r FROM allocations WHERE domain = 'agenda01'")
    totals = cur.fetchone()
    cur.execute("SELECT COUNT(*) AS n FROM agenda_decisions")
    decisions = int(cur.fetchone()["n"])
    cur.execute("SELECT option_id, attempt_id, probe, intended_decision, state,"
                " operation_id FROM agenda_attempt_links ORDER BY attempt_id")
    attempts = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT option_id, version, kind, reason FROM agenda_disposition_events"
                " ORDER BY id DESC LIMIT 100")
    events = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT option_id, receipt_identity, epoch, grounded FROM agenda_outcomes"
                " ORDER BY receipt_identity")
    outcomes = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT r.id AS op_identity, r.amount, r.state FROM reservations r"
                " JOIN allocations a ON a.id = r.allocation_id"
                " WHERE a.domain = 'agenda01' ORDER BY r.id")
    costs = [dict(r) for r in cur.fetchall()]
    cursor = None
    if len(cursors) == 1:
        cursor = cursors[0]
    elif cursors:
        cursor = max(cursors, key=lambda c: (int(c["tick"]), str(c["trajectory"])))
    return {"options": options, "cursor": cursor, "trajectories": cursors,
            "liability": int(totals["r"]),
            "remaining": int(totals["a"]) - int(totals["c"]) - int(totals["r"]),
            "decisions": decisions, "agenda_attempts": attempts, "events": events,
            "outcomes": outcomes, "costs": costs}


def agenda_options_view(dsn: str) -> dict[str, Any]:
    with store.db.connect(dsn) as conn:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            out = _agenda_options_from_cursor(cur)
            conn.commit()
    return out
