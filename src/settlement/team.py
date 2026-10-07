"""Bounded temporary-team runtime (TM-01 through TM-04).

A team plan versions one parent obligation into at most two child attempts
plus one integration check, all compiled into existing run/v1
sequence/parallel/invoke/join nodes and executed through the existing
store/broker/context machinery. No new scheduler, bus, or framework.

Shapes (``team-work/1``): ``single`` (one worker), ``alternatives`` (two
whole-task attempts, select one by executed public checks), ``decompose``
(two workers on disjoint owned paths, conjunctive integration check).

Every JoinNode is paired with a sandbox-exec integration-check invoke whose
broker receipt decides the join. ``JoinNode.needs`` alone is only a barrier.
Child ownership is fenced by attempt generation; a plan allows one revision.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import broker, context, db, run, store
from .common import (
    Command,
    CommandResult,
    InsufficientResources,
    ResultCode,
    SettlementError,
    StaleRevision,
    payload_digest,
)

PROFILE = "team-work/1"
SHAPES = ("single", "alternatives", "decompose")
JOINS = {"single": {"accept"}, "alternatives": {"select-one"},
         "decompose": {"conjunctive"}}
CHILD_LIMIT = 2
MAX_REVISIONS = 1
CLEANUP_RESERVE = 16
CHECK_TIMEOUT_MS = 30_000
CHILD_TIMEOUT_MS = 30_000
CHILD_ARGV = [sys.executable, "-c", "pass"]  # portable no-op child
PACKET_BUDGET = {"input_chars": 20_000, "output_reserve": 2_000}


def _wire(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def content_digest(mapping: dict[str, str]) -> str:
    return hashlib.sha256(_wire(mapping)).hexdigest()


def snapshot_digest(snapshot: dict[str, str]) -> str:
    return content_digest(snapshot)


def output_digest(output: dict[str, str]) -> str:
    return content_digest(output)


def _input_digests(snapshot: dict[str, str], bindings: dict[str, str]) -> dict[str, str]:
    return {name: hashlib.sha256(snapshot[path].encode()).hexdigest()
            for name, path in bindings.items()}


def _relpath_ok(path: Any) -> bool:
    return (isinstance(path, str) and bool(path) and not path.startswith("/")
            and ".." not in path.split("/") and path != ".")


def select_plan(task_info: dict[str, Any]) -> dict[str, Any]:
    defects = int(task_info.get("defect_count", 1))
    stable = bool(task_info.get("interface_stable", False))
    unclear = bool(task_info.get("unclear_diagnosis", False))
    if unclear:
        return {"shape": "alternatives",
                "rationale": "diagnosis unclear: independent attempts then selection"}
    if defects <= 1:
        return {"shape": "single",
                "rationale": "localized defect: one worker owns the whole fix"}
    if stable:
        return {"shape": "decompose",
                "rationale": "disjoint defects under a stable interface: split and join"}
    return {"shape": "alternatives",
            "rationale": "coupled defects without a stable contract: attempt then select"}


def _validate_children(shape: str, snapshot: dict[str, str],
                       children: Any, interface_contract: Any) -> list[dict]:
    if not isinstance(children, list) or not 1 <= len(children) <= CHILD_LIMIT:
        raise SettlementError(f"a team plan needs 1..{CHILD_LIMIT} children")
    want = 1 if shape == "single" else 2
    if len(children) != want:
        raise SettlementError(f"shape {shape} needs exactly {want} children")
    allowed_new = set((interface_contract.get("new_paths") or [])
                      if isinstance(interface_contract, dict) else [])
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    cleaned: list[dict] = []
    for child in children:
        if not isinstance(child, dict):
            raise SettlementError("each child must be an object")
        node = child.get("node_id", "")
        if not isinstance(node, str) or not node or node in seen_ids:
            raise SettlementError(f"child node ids must be unique non-empty: {node!r}")
        seen_ids.add(node)
        if not isinstance(child.get("obligation"), str) or not child["obligation"].strip():
            raise SettlementError(f"child {node} needs a concrete obligation")
        owned = child.get("owned_paths", [])
        if (not isinstance(owned, list) or not owned
                or any(not _relpath_ok(p) for p in owned)):
            raise SettlementError(f"child {node} needs non-empty safe owned_paths")
        for path in owned:
            if path not in snapshot and path not in allowed_new:
                raise SettlementError(f"child {node} owns undeclared path {path!r}")
            if shape == "decompose" and path in seen_paths:
                raise SettlementError(f"owned path {path!r} is not disjoint")
            seen_paths.add(path)
        bindings = child.get("input_bindings", {})
        if not isinstance(bindings, dict) or not bindings:
            raise SettlementError(f"child {node} needs input bindings")
        for name, path in bindings.items():
            if path not in snapshot:
                raise SettlementError(f"child {node} binds missing input {path!r}")
        if not isinstance(child.get("output_contract"), dict) or not child["output_contract"]:
            raise SettlementError(f"child {node} needs an output contract")
        cleaned.append({"node_id": node, "obligation": child["obligation"],
                        "owned_paths": list(owned),
                        "output_contract": dict(child["output_contract"]),
                        "input_bindings": dict(bindings)})
    return cleaned


def _validate_plan(shape: str, snapshot: dict[str, str], children: Any,
                   interface_contract: Any, join_rules: Any,
                   policy_response: Any) -> tuple[list[dict], dict]:
    if shape not in SHAPES:
        raise SettlementError(f"unsupported shape {shape!r}")
    if policy_response is not None:
        if not isinstance(policy_response, dict) or policy_response.get("shape") != shape:
            raise SettlementError("a policy response selects the executed plan:"
                                  " shape does not match the policy selection")
    if not isinstance(interface_contract, dict) or not interface_contract:
        raise SettlementError("a team plan needs a present interface contract")
    if not isinstance(join_rules, dict) or join_rules.get("join") not in JOINS[shape]:
        raise SettlementError(f"shape {shape} admits joins {sorted(JOINS[shape])}")
    owner = join_rules.get("integration_owner", "")
    if not isinstance(owner, str) or not owner:
        raise SettlementError("join rules must name one integration owner")
    cleaned = _validate_children(shape, snapshot, children, interface_contract)
    if owner not in {c["node_id"] for c in cleaned}:
        raise SettlementError("the integration owner must be one child worker")
    checks = join_rules.get("checks", {})
    entry = join_rules.get("check_entry", "")
    if (not isinstance(checks, dict) or not checks
            or not isinstance(entry, str) or checks.get(entry) is None):
        raise SettlementError("join rules must carry the executed public checks")
    for path, body in checks.items():
        if not _relpath_ok(path) or not isinstance(body, str) or not body:
            raise SettlementError(f"join check {path!r} must be a non-empty file")
    return cleaned, {"join": join_rules["join"], "integration_owner": owner,
                     "check_entry": entry, "checks": dict(checks)}


def _child_op_payload() -> dict[str, Any]:
    return {"profile": "local-process", "argv": list(CHILD_ARGV),
            "timeout_ms": CHILD_TIMEOUT_MS, "max_output_bytes": 65_536}


def _check_op_payload(python_exe: str, check_path: str, target: str,
                      extra: list[str] | None = None) -> dict[str, Any]:
    return {"profile": "local-process",
            "argv": [python_exe, check_path, target, *(extra or [])],
            "timeout_ms": CHECK_TIMEOUT_MS, "max_output_bytes": 65_536}


def _planned_exposures(count: int) -> tuple[list[int], int]:
    kid = broker.exposure_schedule(broker.SANDBOX_EXEC, _child_op_payload(), 0)[0]
    probe = dict(_child_op_payload(), timeout_ms=CHECK_TIMEOUT_MS)
    check = broker.exposure_schedule(broker.SANDBOX_EXEC, probe, 0)[0]
    return [kid] * count, check


def compile_composition(shape: str, children: list[dict], join_rules: dict,
                        allocation_id: str = "", authority_version: int = 1,
                        budget: dict | None = None) -> run.Composition:
    works = [run.InvokeNode(node_id=c["node_id"], effect=broker.SANDBOX_EXEC,
                            payload=_child_op_payload()) for c in children]
    check = run.InvokeNode(
        node_id="check", effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process",
                 "argv": [sys.executable, join_rules["check_entry"], "assembly"],
                 "timeout_ms": CHECK_TIMEOUT_MS, "max_output_bytes": 65_536,
                 "team_check": join_rules["join"]})
    join = run.JoinNode(node_id="join", needs={c["node_id"]: c["node_id"]
                                               for c in children} | {"check": "check"})
    if shape == "single":
        root: run.Node = run.SequenceNode(node_id="team", steps=[works[0], check, join])
    else:
        root = run.SequenceNode(
            node_id="team",
            steps=[run.ParallelNode(node_id="workers", branches=works), check, join])
    return run.validate_composition(run.Composition(
        version=run.COMPOSITION_VERSION, revision=1, root=root,
        allocation_id=allocation_id, authority_version=authority_version,
        budget=dict(budget or {})))


def _row(cur, sql: str, args: tuple) -> dict | None:
    cur.execute(sql, args)
    found = cur.fetchone()
    return dict(found) if found is not None else None


def _plan_row_conn(dsn: str, plan_id: str) -> dict:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT * FROM team_plans WHERE plan_id = %s", (plan_id,))
            conn.commit()
    if row is None:
        raise LookupError(f"unknown team plan {plan_id}")
    for key in ("interface_contract", "join_rules", "composition",
                "budget", "policy_response"):
        value = row.get(key) or {}
        row[key] = dict(value) if isinstance(value, dict) else {}
    kids = row.get("children") or []
    row["children"] = [dict(c) for c in kids] if isinstance(kids, list) else []
    return row


def plan_summary(dsn: str, plan_id: str) -> dict:
    plan = _plan_row_conn(dsn, plan_id)
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            snap = _row(cur, "SELECT snapshot FROM team_snapshots WHERE digest = %s",
                        (plan["snapshot_digest"],))
            conn.commit()
    snapshot = dict((snap or {}).get("snapshot") or {})
    children = []
    for child in plan["children"]:
        children.append({**child, "input_digests": _input_digests(
            snapshot, child["input_bindings"])})
    return {"plan_id": plan["plan_id"], "shape": plan["shape"],
            "revision": plan["revision"], "snapshot_digest": plan["snapshot_digest"],
            "interface_contract": plan["interface_contract"], "children": children}


def team_state(dsn: str, investigation_id: str) -> dict:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT plan_id, shape, revision, revision_count,"
                        " frozen_candidate FROM team_plans"
                        " WHERE investigation_id = %s ORDER BY plan_id",
                        (investigation_id,))
            plans = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT plan_id, plan_revision, node_id, input_digests,"
                        " ownership_generation, output_digest, receipt_refs, accepted,"
                        " invalidated FROM team_submissions WHERE plan_id IN"
                        " (SELECT plan_id FROM team_plans WHERE investigation_id = %s)"
                        " ORDER BY plan_id, plan_revision, node_id", (investigation_id,))
            submissions = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT plan_id, plan_revision, candidate_digest, passed,"
                        " failing_input, observed_output, join_receipt, check_operation"
                        " FROM team_joins WHERE plan_id IN"
                        " (SELECT plan_id FROM team_plans WHERE investigation_id = %s)"
                        " ORDER BY plan_id, plan_revision", (investigation_id,))
            joins = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return {"plans": plans, "submissions": submissions, "joins": joins}


def _children_at(plan: dict) -> list[dict]:
    return list(plan.get("children") or [])


def _child_entry(plan: dict, node_id: str) -> dict:
    for child in _children_at(plan):
        if child["node_id"] == node_id:
            return child
    raise LookupError(f"plan {plan['plan_id']} has no child {node_id}")


def child_nodes(dsn: str, plan_id: str, revision: int | None = None) -> list[str]:
    plan = _plan_row_conn(dsn, plan_id)
    if revision is not None and int(revision) != int(plan["revision"]):
        with db.read_connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT node_id FROM team_submissions"
                            " WHERE plan_id = %s AND plan_revision = %s ORDER BY node_id",
                            (plan_id, int(revision)))
                rows = [r["node_id"] for r in cur.fetchall()]
                conn.commit()
        return rows
    return [c["node_id"] for c in _children_at(plan)]


def child_operation(dsn: str, plan_id: str, node_id: str,
                    revision: int | None = None) -> str:
    plan = _plan_row_conn(dsn, plan_id)
    if revision is None or int(revision) == int(plan["revision"]):
        return _child_entry(plan, node_id)["operation_id"]
    return f"{plan_id}:r{int(revision)}:{node_id}:work"


def child_attempt(dsn: str, plan_id: str, node_id: str,
                  revision: int | None = None) -> dict:
    plan = _plan_row_conn(dsn, plan_id)
    attempt_id = ""
    if revision is None or int(revision) == int(plan["revision"]):
        attempt_id = _child_entry(plan, node_id)["attempt_id"]
    else:
        with db.read_connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                row = _row(cur, "SELECT attempt_id FROM team_submissions WHERE plan_id = %s"
                                " AND plan_revision = %s AND node_id = %s",
                           (plan_id, int(revision), node_id))
                conn.commit()
        if row is None:
            raise LookupError(f"no submission for {plan_id} r{revision} {node_id}")
        attempt_id = row["attempt_id"]
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT id, ownership_generation, lifecycle FROM attempts"
                            " WHERE id = %s", (attempt_id,))
            conn.commit()
    if row is None:
        raise LookupError(f"unknown attempt {attempt_id}")
    return {"attempt_id": row["id"],
            "ownership_generation": int(row["ownership_generation"]),
            "lifecycle": row["lifecycle"]}


def expected_inputs(dsn: str, plan_id: str, node_id: str,
                    revision: int | None = None) -> dict[str, str]:
    plan = _plan_row_conn(dsn, plan_id)
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            snap = _row(cur, "SELECT snapshot FROM team_snapshots WHERE digest = %s",
                        (plan["snapshot_digest"],))
            conn.commit()
    snapshot = dict((snap or {}).get("snapshot") or {})
    return _input_digests(snapshot, _child_entry(plan, node_id)["input_bindings"])


def child_packet(dsn: str, plan_id: str, node_id: str) -> dict:
    return context.load_packet(dsn, _child_entry(_plan_row_conn(dsn, plan_id),
                                                 node_id)["packet_id"])


def child_binding(dsn: str, plan_id: str, node_id: str) -> dict:
    packet_id = _child_entry(_plan_row_conn(dsn, plan_id), node_id)["packet_id"]
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT packet_id, operation_id, rendered_digest, input_digest"
                            " FROM packet_invocations WHERE packet_id = %s", (packet_id,))
            conn.commit()
    if row is None:
        raise LookupError(f"packet {packet_id} is not bound")
    return row


def packet_kinds_used(dsn: str, plan_id: str) -> set[str]:
    kinds = set()
    for node in child_nodes(dsn, plan_id):
        kinds.add(child_packet(dsn, plan_id, node)["decision_kind"])
    return kinds


def submission_tuple(dsn: str, plan_id: str, revision: int,
                     node_id: str) -> tuple:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT plan_revision, node_id, input_digests,"
                            " ownership_generation, output_digest, receipt_refs"
                            " FROM team_submissions WHERE plan_id = %s AND plan_revision = %s"
                            " AND node_id = %s AND invalidated = FALSE",
                       (plan_id, int(revision), node_id))
            conn.commit()
    if row is None:
        raise LookupError(f"no live submission for {plan_id} r{revision} {node_id}")
    return (int(row["plan_revision"]), row["node_id"], dict(row["input_digests"] or {}),
            int(row["ownership_generation"]), row["output_digest"],
            list(row["receipt_refs"] or []))


def join_record(dsn: str, plan_id: str, revision: int) -> dict:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT * FROM team_joins WHERE plan_id = %s"
                            " AND plan_revision = %s", (plan_id, int(revision)))
            conn.commit()
    if row is None:
        raise LookupError(f"no join for {plan_id} r{revision}")
    return {k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
            for k, v in dict(row).items()}


def register_snapshot(dsn: str, cmd: Command, snapshot: dict[str, str]) -> CommandResult:
    if not isinstance(snapshot, dict) or not snapshot:
        return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                             detail="a snapshot needs at least one file", data={})
    for path, body in snapshot.items():
        if not _relpath_ok(path) or not isinstance(body, str):
            return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                                 detail=f"snapshot path {path!r} is not a safe file",
                                 data={})
    digest = snapshot_digest(snapshot)

    def _fn(cur, control):
        cur.execute("INSERT INTO team_snapshots (digest, snapshot) VALUES (%s, %s)"
                    " ON CONFLICT (digest) DO NOTHING", (digest, Json(snapshot)))
        return (ResultCode.APPLIED, f"snapshot {digest[:12]} registered",
                {"snapshot_digest": digest, "files": len(snapshot)},
                [("team.snapshot_registered", {"snapshot_digest": digest})], [])
    return store.transact(dsn, cmd, _fn)


def register_output(dsn: str, cmd: Command, output: dict[str, str]) -> CommandResult:
    if not isinstance(output, dict) or not output:
        return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                             detail="an output needs at least one file", data={})
    for path, body in output.items():
        if not _relpath_ok(path) or not isinstance(body, str):
            return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                                 detail=f"output path {path!r} is not a safe file",
                                 data={})
    digest = output_digest(output)

    def _fn(cur, control):
        cur.execute("INSERT INTO team_outputs (digest, output) VALUES (%s, %s)"
                    " ON CONFLICT (digest) DO NOTHING", (digest, Json(output)))
        return (ResultCode.APPLIED, f"output {digest[:12]} registered",
                {"output_digest": digest, "files": len(output)},
                [("team.output_registered", {"output_digest": digest})], [])
    return store.transact(dsn, cmd, _fn)


def _parse_parent(parent_obligation: Any) -> tuple[str, str]:
    inv, sep, name = str(parent_obligation or "").partition(":")
    if not sep or not inv or not name.strip():
        raise SettlementError("parent_obligation must be '<investigation_id>:<obligation>'")
    return inv, name.strip()


def _op_ids(plan_id: str, revision: int, node_id: str) -> dict[str, str]:
    return {"attempt_id": f"{plan_id}-r{revision}-{node_id}",
            "allocation_id": f"{plan_id}:r{revision}:{node_id}",
            "operation_id": f"{plan_id}:r{revision}:{node_id}:work",
            "packet_id": f"pkt_{plan_id}_r{revision}_{node_id}"}


def _insert_attempt(cur, inv_id: str, inv_rev: int, attempt_id: str,
                    allocation_id: str, generation: int, node_id: str) -> None:
    cur.execute("SELECT occupancy, max_occupancy FROM allocations WHERE id = %s",
                (allocation_id,))
    alloc = cur.fetchone()
    if alloc is None:
        raise SettlementError(f"unknown allocation {allocation_id}")
    if int(alloc["occupancy"]) >= int(alloc["max_occupancy"]):
        raise InsufficientResources(f"allocation {allocation_id} occupancy exhausted")
    cur.execute("UPDATE allocations SET occupancy = occupancy + 1 WHERE id = %s",
                (allocation_id,))
    cur.execute(
        "INSERT INTO attempts (id, investigation_id, investigation_revision, allocation_id,"
        " ownership_generation, composition, model, env, lifecycle, owner)"
        " VALUES (%s, %s, %s, %s, %s, %s, '', '', 'running', %s)",
        (attempt_id, inv_id, inv_rev, allocation_id, generation, PROFILE,
         f"team:{node_id}"))


def _insert_operation(cur, authority: int, operation_id: str, attempt_id: str | None,
                      allocation_id: str, exposure: int) -> None:
    body = {"effect": broker.SANDBOX_EXEC, "payload": _child_op_payload(),
            "retries": 0, "budget_kind": "hard-ceiling"}
    digest = payload_digest(body)
    reservation_id = f"res-{operation_id}" if exposure > 0 else None
    if reservation_id is not None:
        store._take_reservation(cur, allocation_id, reservation_id, exposure,
                                operation_id)
    stored = dict(body)
    stored["_authority_version"] = int(authority)
    cur.execute(
        "INSERT INTO operations (id, attempt_id, allocation_id, reservation_id,"
        " payload_digest, payload, dispatch_state, execution_version)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'prepared', %s)",
        (operation_id, attempt_id, allocation_id, reservation_id, digest,
         Json(stored), PROFILE))


def propose_team_plan(dsn: str, cmd: Command, *, parent_obligation: str,
                      snapshot_digest: str, shape: str, children: list[dict],
                      interface_contract: dict, join_rules: dict,
                      allocation_id: str,
                      policy_response: dict | None = None) -> CommandResult:
    inv_id, _ = _parse_parent(parent_obligation)
    canonical = {"parent_obligation": parent_obligation, "snapshot_digest": snapshot_digest,
                 "shape": shape, "children": children,
                 "interface_contract": interface_contract, "join_rules": join_rules,
                 "allocation_id": allocation_id, "policy_response": policy_response or {}}
    inner = Command(request_id=f"{cmd.request_id}:propose", payload=canonical)

    def _fn(cur, control):
        cur.execute("SELECT * FROM investigations WHERE id = %s", (inv_id,))
        inv = cur.fetchone()
        if inv is None:
            raise SettlementError(f"unknown investigation {inv_id}")
        if inv["disposition"] in ("withdrawn", "fulfilled"):
            raise SettlementError(f"investigation {inv_id} is {inv['disposition']}")
        cur.execute("SELECT snapshot FROM team_snapshots WHERE digest = %s",
                    (snapshot_digest,))
        snap = cur.fetchone()
        if snap is None:
            raise SettlementError(f"unknown snapshot {snapshot_digest[:12]}")
        snapshot = dict(snap["snapshot"] or {})
        if content_digest(snapshot) != snapshot_digest:
            raise SettlementError("snapshot bytes do not match their digest")
        cleaned, rules = _validate_plan(shape, snapshot, children, interface_contract,
                                        join_rules, policy_response)
        cur.execute("SELECT * FROM allocations WHERE id = %s", (allocation_id,))
        root = cur.fetchone()
        if root is None:
            raise SettlementError(f"unknown allocation {allocation_id}")
        cur.execute("SELECT COALESCE(SUM(authorized), 0) AS total FROM allocations"
                    " WHERE parent_id = %s", (allocation_id,))
        subdivided = int(cur.fetchone()["total"])
        free = store.free_of(dict(root), subdivided)
        kid_exp, check_exp = _planned_exposures(len(cleaned))
        required = sum(kid_exp) + check_exp + CLEANUP_RESERVE
        if free < required:
            raise InsufficientResources(
                f"root allocation {allocation_id} free {free} does not cover"
                f" children {sum(kid_exp)} + checker {check_exp}"
                f" + cleanup reserve {CLEANUP_RESERVE}")
        plan_id = f"plan_{cmd.request_id}"
        cur.execute("SELECT 1 FROM team_plans WHERE plan_id = %s", (plan_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"team plan {plan_id} already exists")
        cur.execute("SELECT COALESCE(MAX(ownership_generation), 0) AS g FROM attempts"
                    " WHERE investigation_id = %s", (inv_id,))
        base = int(cur.fetchone()["g"])
        authority = int(control["authority_version"])
        budget = {"units": required, "reserve": CLEANUP_RESERVE,
                  "children": kid_exp, "checker": check_exp}
        comp = compile_composition(shape, cleaned, rules,
                                   allocation_id=allocation_id,
                                   authority_version=authority, budget=budget)
        stored_children = []
        for pos, child in enumerate(cleaned):
            ids = _op_ids(plan_id, 1, child["node_id"])
            child_alloc = ids["allocation_id"]
            cur.execute(
                "INSERT INTO allocations (id, parent_id, domain, epoch, authorized,"
                " amount_scale, max_occupancy, owner_scope) VALUES (%s, %s, %s, %s,"
                " %s, 1, 8, %s)",
                (child_alloc, allocation_id, root["domain"], int(root["epoch"]),
                 kid_exp[pos], f"team:{child['node_id']}"))
            _insert_attempt(cur, inv_id, int(inv["revision"]), ids["attempt_id"],
                            child_alloc, base + pos + 1, child["node_id"])
            _insert_operation(cur, authority, ids["operation_id"], ids["attempt_id"],
                              child_alloc, kid_exp[pos])
            stored_children.append({**child, **ids,
                                    "input_digests": _input_digests(
                                        snapshot, child["input_bindings"])})
        checker_alloc = f"{plan_id}:r1:check"
        cur.execute(
            "INSERT INTO allocations (id, parent_id, domain, epoch, authorized,"
            " amount_scale, max_occupancy, owner_scope) VALUES (%s, %s, %s, %s,"
            " %s, 1, 8, %s)",
            (checker_alloc, allocation_id, root["domain"], int(root["epoch"]),
             check_exp, "team:check"))
        cur.execute(
            "INSERT INTO team_plans (plan_id, investigation_id, parent_obligation,"
            " snapshot_digest, shape, children, interface_contract, join_rules,"
            " allocation_id, checker_allocation_id, composition, budget, revision,"
            " revision_count, policy_response)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 0, %s)",
            (plan_id, inv_id, parent_obligation, snapshot_digest, shape,
             Json(stored_children), Json(interface_contract), Json(rules),
             allocation_id, checker_alloc, Json(comp.model_dump()),
             Json(budget), Json(policy_response or {})))
        data = {"plan_id": plan_id, "revision": 1,
                "composition": comp.model_dump(),
                "child_attempts": {c["node_id"]: c["attempt_id"]
                                   for c in stored_children},
                "child_operations": {c["node_id"]: c["operation_id"]
                                     for c in stored_children},
                "packet_ids": {c["node_id"]: c["packet_id"] for c in stored_children}}
        return (ResultCode.APPLIED, f"team plan {plan_id} proposed",
                data, [("team.plan_proposed", {"plan_id": plan_id})], [])
    result = store.transact(dsn, inner, _fn)
    if result.code != ResultCode.APPLIED:
        return result
    wired = _wire_packets(dsn, cmd, result.data["plan_id"], inv_id)
    if wired.code != ResultCode.APPLIED:
        result.data["wiring"] = wired.data
        return CommandResult(code=wired.code, request_id=cmd.request_id,
                             detail=wired.detail, data=result.data)
    result.data["packet_ids"] = wired.data["packet_ids"]
    return result


def _wire_packets(dsn: str, cmd: Command, plan_id: str,
                  inv_id: str) -> CommandResult:
    plan = _plan_row_conn(dsn, plan_id)
    bound: dict[str, str] = {}
    for child in _children_at(plan):
        try:
            context.load_packet(dsn, child["packet_id"])
        except SettlementError:
            made = context.build_packet(
                dsn, Command(request_id=child["packet_id"][4:], payload={}),
                decision={"decision_kind": "team",
                          "purpose": f"team child {child['node_id']} of {plan_id}",
                          "required_inputs": [], "allowed_actions": ["read"],
                          "access": "candidate", "budget": dict(PACKET_BUDGET),
                          "current_versions": {"plan_id": plan_id,
                                               "plan_revision": plan["revision"],
                                               "node_id": child["node_id"]},
                          "investigation_id": inv_id, "episode_id": ""})
            if made.code != ResultCode.APPLIED:
                return CommandResult(code=made.code, request_id=cmd.request_id,
                                     detail=made.detail,
                                     data={"plan_id": plan_id, "packet_ids": bound})
        try:
            child_binding(dsn, plan_id, child["node_id"])
        except LookupError:
            linked = context.bind_packet_invocation(
                dsn, Command(request_id=f"{plan_id}:{child['node_id']}:bind",
                             payload={}),
                child["packet_id"], child["operation_id"])
            if linked.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                return CommandResult(code=linked.code, request_id=cmd.request_id,
                                     detail=linked.detail,
                                     data={"plan_id": plan_id, "packet_ids": bound})
        bound[child["node_id"]] = child["packet_id"]
    return CommandResult(code=ResultCode.APPLIED, request_id=cmd.request_id,
                         detail=f"wired {len(bound)} child packets",
                         data={"plan_id": plan_id, "packet_ids": bound})


def submit_child(dsn: str, cmd: Command, *, plan_revision: int, node_id: str,
                 input_digests: dict[str, str],
                 ownership_generation: int, output_digest: str,
                 receipt_refs: list[str]) -> CommandResult:
    inner = Command(request_id=f"{cmd.request_id}:submit",
                    payload={"plan_revision": plan_revision, "node_id": node_id,
                             "input_digests": input_digests,
                             "ownership_generation": ownership_generation,
                             "output_digest": output_digest,
                             "receipt_refs": receipt_refs})

    def _fn(cur, control):
        cur.execute("SELECT * FROM team_plans WHERE plan_id = %s",
                    (cmd.payload.get("plan_id", ""),))
        plan = cur.fetchone()
        if plan is None:
            raise SettlementError("submit needs the plan id in the command payload")
        children = list(plan["children"] or [])
        child = next((c for c in children if c["node_id"] == node_id), None)
        if child is None:
            raise SettlementError(f"plan {plan['plan_id']} has no child {node_id}")
        if plan["frozen_candidate"]:
            raise SettlementError(f"plan {plan['plan_id']} is frozen")
        if int(plan_revision) != int(plan["revision"]):
            raise StaleRevision(f"submission targets r{plan_revision},"
                                f" plan is r{plan['revision']}")
        cur.execute("SELECT snapshot FROM team_snapshots WHERE digest = %s",
                    (plan["snapshot_digest"],))
        snapshot = dict((cur.fetchone() or {})["snapshot"] or {})
        if _input_digests(snapshot, child["input_bindings"]) != dict(input_digests or {}):
            raise StaleRevision(f"child {node_id} input bindings no longer match")
        cur.execute("SELECT ownership_generation, lifecycle FROM attempts WHERE id = %s",
                    (child["attempt_id"],))
        attempt = cur.fetchone()
        if attempt is None:
            raise SettlementError(f"unknown attempt {child['attempt_id']}")
        if int(ownership_generation) != int(attempt["ownership_generation"]):
            raise StaleRevision(
                f"attempt owned by generation {attempt['ownership_generation']},"
                f" not {ownership_generation}")
        cur.execute("SELECT output FROM team_outputs WHERE digest = %s", (output_digest,))
        found = cur.fetchone()
        if found is None:
            raise SettlementError(f"unknown output {output_digest[:12]}")
        output = dict(found["output"] or {})
        owned = set(child["owned_paths"] or [])
        if set(output) - owned:
            raise SettlementError(f"child {node_id} declares paths outside its ownership")
        if not isinstance(receipt_refs, list) or not receipt_refs:
            raise SettlementError(f"child {node_id} needs attributable receipts")
        cur.execute("SELECT receipt_identity, operation_id, outcome FROM receipts"
                    " WHERE receipt_identity = ANY(%s)", (list(receipt_refs),))
        receipts = {r["receipt_identity"]: r for r in cur.fetchall()}
        for ref in receipt_refs:
            hit = receipts.get(ref)
            if hit is None or hit["operation_id"] != child["operation_id"]:
                raise SettlementError(f"receipt {ref} is not this child's work")
            if hit["outcome"] != "success":
                raise SettlementError(f"receipt {ref} is {hit['outcome']}, not success")
        cur.execute("SELECT input_digests, ownership_generation, output_digest,"
                    " receipt_refs FROM team_submissions WHERE plan_id = %s"
                    " AND plan_revision = %s AND node_id = %s",
                    (plan["plan_id"], int(plan_revision), node_id))
        prior = cur.fetchone()
        if prior is not None:
            same = (dict(prior["input_digests"] or {}) == dict(input_digests or {})
                    and int(prior["ownership_generation"]) == int(ownership_generation)
                    and prior["output_digest"] == output_digest
                    and list(prior["receipt_refs"] or []) == list(receipt_refs))
            if not same:
                raise SettlementError(f"child {node_id} already submitted r{plan_revision}")
            return (ResultCode.ALREADY_APPLIED, f"child {node_id} already accepted",
                    {"accepted_for_join": True, "plan_id": plan["plan_id"],
                     "node_id": node_id, "plan_revision": int(plan_revision)}, [], [])
        cur.execute(
            "INSERT INTO team_submissions (plan_id, plan_revision, node_id, attempt_id,"
            " input_digests, ownership_generation, output_digest, receipt_refs)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (plan["plan_id"], int(plan_revision), node_id, child["attempt_id"],
             Json(dict(input_digests or {})), int(ownership_generation),
             output_digest, Json(list(receipt_refs))))
        if attempt["lifecycle"] == "running":
            cur.execute("UPDATE attempts SET lifecycle = 'completed', updated_at = now()"
                        " WHERE id = %s", (child["attempt_id"],))
            cur.execute("SELECT allocation_id FROM attempts WHERE id = %s",
                        (child["attempt_id"],))
            alloc = cur.fetchone()["allocation_id"]
            if alloc is not None:
                cur.execute("UPDATE allocations SET occupancy = GREATEST(occupancy - 1, 0)"
                            " WHERE id = %s", (alloc,))
        return (ResultCode.APPLIED, f"child {node_id} accepted for join",
                {"accepted_for_join": True, "plan_id": plan["plan_id"],
                 "node_id": node_id, "plan_revision": int(plan_revision)},
                [("team.child_accepted", {"plan_id": plan["plan_id"],
                                          "node_id": node_id})], [])
    return store.transact(dsn, inner, _fn)


def _snapshot_of(dsn: str, digest: str) -> dict[str, str]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT snapshot FROM team_snapshots WHERE digest = %s",
                       (digest,))
            conn.commit()
    if row is None:
        raise LookupError(f"unknown snapshot {digest[:12]}")
    return dict(row["snapshot"] or {})


def _output_of(dsn: str, digest: str) -> dict[str, str]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = _row(cur, "SELECT output FROM team_outputs WHERE digest = %s",
                       (digest,))
            conn.commit()
    if row is None:
        raise LookupError(f"unknown output {digest[:12]}")
    return dict(row["output"] or {})


def _worker_data(content: Any) -> dict:
    if isinstance(content, dict):
        data = content.get("data") or {}
        worker = data.get("worker") or {}
        if isinstance(worker.get("data"), dict):
            return dict(worker["data"])
        return {k: v for k, v in data.items() if k in ("stdout", "stderr", "returncode")}
    return {}


def _check_receipts(dsn: str, operation_id: str) -> list[dict]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT receipt_identity, outcome, content FROM receipts"
                        " WHERE operation_id = %s ORDER BY receipt_identity",
                        (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows


def assemble_and_join(dsn: str, cmd: Command, *, plan_id: str,
                      launchers: dict | None = None,
                      python_exe: str | None = None) -> CommandResult:
    try:
        plan = _plan_row_conn(dsn, plan_id)
    except LookupError as exc:
        return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                             detail=str(exc), data={})
    if plan["frozen_candidate"]:
        return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                             detail=f"plan {plan_id} is frozen", data={})
    revision = int(plan["revision"])
    children = _children_at(plan)
    rules = plan["join_rules"]
    try:
        snapshot = _snapshot_of(dsn, plan["snapshot_digest"])
        outputs = {}
        for child in children:
            _rev, _node, _inp, _gen, digest, _refs = submission_tuple(
                dsn, plan_id, revision, child["node_id"])
            outputs[child["node_id"]] = _output_of(dsn, digest)
    except LookupError as exc:
        return CommandResult(code=ResultCode.MISSING_EVIDENCE,
                             request_id=cmd.request_id,
                             detail=f"join blocked: {exc}", data={"plan_id": plan_id})
    nodes = [c["node_id"] for c in children]
    if plan["shape"] == "alternatives":
        for node in nodes:
            missing = set(snapshot) - set(outputs[node])
            if missing:
                return CommandResult(
                    code=ResultCode.MISSING_EVIDENCE, request_id=cmd.request_id,
                    detail=f"candidate {node} is missing {sorted(missing)}",
                    data={"plan_id": plan_id})
            if set(outputs[node]) - set(snapshot):
                return CommandResult(
                    code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                    detail=f"candidate {node} declares paths outside the snapshot",
                    data={"plan_id": plan_id})
        staged = {node: dict(outputs[node]) for node in nodes}
    else:
        seen: dict[str, str] = {}
        for node in nodes:
            for path in outputs[node]:
                if path in seen:
                    return CommandResult(
                        code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                        detail=f"overlapping patch {path!r} from {seen[path]} and {node}",
                        data={"plan_id": plan_id})
                seen[path] = node
        tree = dict(snapshot)
        for node in nodes:
            tree.update(outputs[node])
        staged = {"assembly": tree}
    launcher = (launchers or {}).get("local-process")
    if launcher is None or not hasattr(launcher, "exec_dirs"):
        return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                             detail="the join check needs an executing launcher:"
                                    " refusing a prose verdict",
                             data={"plan_id": plan_id})
    check_op = f"{plan_id}:r{revision}:check"
    inputs_dir, _outputs_dir = launcher.exec_dirs(check_op, PROFILE)
    from pathlib import Path as _Path

    root = _Path(inputs_dir)
    for relpath, body in (rules.get("checks") or {}).items():
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    if plan["shape"] == "alternatives":
        target_dir = root / "candidates"
        for node in nodes:
            for relpath, body in staged[node].items():
                dest = target_dir / node / relpath
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(body)
        extra = [",".join(nodes)]
    else:
        target_dir = root / "assembly"
        for relpath, body in staged["assembly"].items():
            dest = target_dir / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        extra = []
    check_path = str(root / rules["check_entry"])
    ensured = broker.ensure_operation(
        dsn, operation_id=check_op, effect=broker.SANDBOX_EXEC,
        payload=_check_op_payload(python_exe or sys.executable, check_path,
                                  str(target_dir), extra),
        allocation_id=plan["checker_allocation_id"], attempt_id=None,
        execution_version=PROFILE)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return CommandResult(code=ensured.code, request_id=cmd.request_id,
                             detail=f"check admission refused: {ensured.detail}",
                             data={"plan_id": plan_id})
    broker.dispatch_operation(dsn, check_op, launchers=launchers or {})
    receipts = _check_receipts(dsn, check_op)
    good = [r for r in receipts if r["outcome"] == "success"]
    bad = [r for r in receipts if r["outcome"] == "failure"]
    if not good and not bad:
        return CommandResult(code=ResultCode.OUTCOME_UNKNOWN,
                             request_id=cmd.request_id,
                             detail=f"check {check_op} has no observed receipt",
                             data={"plan_id": plan_id, "check_operation": check_op})
    if good and not bad:
        worker = _worker_data(good[-1]["content"])
        if plan["shape"] == "alternatives":
            selected = worker.get("selected")
            if selected not in outputs:
                passed, worker = False, {"message": "selection is not a candidate",
                                         "selected": selected}
                digest = content_digest({})
            else:
                digest = output_digest(outputs[selected])
                passed = True
        else:
            digest = content_digest(staged["assembly"])
            passed = True
    else:
        worker = _worker_data(bad[-1]["content"])
        if plan["shape"] == "alternatives":
            digest = content_digest({})
        else:
            digest = content_digest(staged["assembly"])
        passed = False
    join_receipt = (good[-1] if good and not bad else bad[-1])["receipt_identity"]
    inner = Command(request_id=f"{cmd.request_id}:join",
                    payload={"plan_id": plan_id, "plan_revision": revision,
                             "candidate_digest": digest, "passed": passed,
                             "join_receipt": join_receipt,
                             "observed_output": worker,
                             "check_operation": check_op})

    def _fn(cur, control):
        failing = {} if passed else {"plan_revision": revision,
                                     "candidate_digest": digest,
                                     "check_entry": rules["check_entry"],
                                     "nodes": nodes}
        observed = {} if passed and not worker else dict(worker)
        cur.execute(
            "INSERT INTO team_joins (plan_id, plan_revision, candidate_digest, passed,"
            " failing_input, observed_output, join_receipt, check_operation)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (plan_id, plan_revision) DO UPDATE SET candidate_digest ="
            " EXCLUDED.candidate_digest, passed = EXCLUDED.passed, failing_input ="
            " EXCLUDED.failing_input, observed_output = EXCLUDED.observed_output,"
            " join_receipt = EXCLUDED.join_receipt, check_operation ="
            " EXCLUDED.check_operation",
            (plan_id, revision, digest, passed, Json(failing), Json(observed),
             join_receipt, check_op))
        code = ResultCode.APPLIED if passed else ResultCode.OBSERVED_FAILURE
        return (code, f"join {'passed' if passed else 'failed'} for {plan_id} r{revision}",
                {"candidate_digest": digest, "join_receipt": join_receipt,
                 "plan_id": plan_id, "plan_revision": revision},
                [("team.joined", {"plan_id": plan_id, "passed": passed})], [])
    return store.transact(dsn, inner, _fn)


def freeze_candidate(dsn: str, cmd: Command, *, plan_id: str,
                     candidate_digest: str) -> CommandResult:
    inner = Command(request_id=f"{cmd.request_id}:freeze",
                    payload={"plan_id": plan_id, "candidate_digest": candidate_digest})

    def _fn(cur, control):
        cur.execute("SELECT revision, frozen_candidate FROM team_plans WHERE plan_id = %s",
                    (plan_id,))
        plan = cur.fetchone()
        if plan is None:
            raise SettlementError(f"unknown team plan {plan_id}")
        if plan["frozen_candidate"]:
            raise SettlementError(f"plan {plan_id} is already frozen")
        cur.execute("SELECT candidate_digest, passed FROM team_joins WHERE plan_id = %s"
                    " AND plan_revision = %s", (plan_id, int(plan["revision"])))
        join = cur.fetchone()
        if join is None or not join["passed"]:
            raise SettlementError(f"plan {plan_id} r{plan['revision']} has no passing join")
        if join["candidate_digest"] != candidate_digest:
            raise SettlementError("only the checked candidate can freeze")
        cur.execute("UPDATE team_plans SET frozen_candidate = %s WHERE plan_id = %s",
                    (candidate_digest, plan_id))
        return (ResultCode.APPLIED, f"plan {plan_id} froze {candidate_digest[:12]}",
                {"plan_id": plan_id, "frozen_candidate": candidate_digest,
                 "revision": int(plan["revision"])},
                [("team.frozen", {"plan_id": plan_id})], [])
    return store.transact(dsn, inner, _fn)


def _complete_carried_attempt(cur, attempt_id: str) -> None:
    cur.execute("UPDATE attempts SET lifecycle = 'completed', updated_at = now()"
                " WHERE id = %s", (attempt_id,))
    cur.execute("SELECT allocation_id FROM attempts WHERE id = %s", (attempt_id,))
    alloc = cur.fetchone()["allocation_id"]
    if alloc is not None:
        cur.execute("UPDATE allocations SET occupancy = GREATEST(occupancy - 1, 0)"
                    " WHERE id = %s", (alloc,))


def _settle_superseded(dsn: str, cmd: Command, entries: list[dict],
                       launchers: dict | None = None) -> list[dict]:
    settled: list[dict] = []
    for entry in entries:
        attempt_id = entry.get("attempt_id", "")
        operation_id = entry.get("operation_id", "")
        if attempt_id:
            with db.read_connect(dsn) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    attempt = _row(cur, "SELECT lifecycle, ownership_generation"
                                        " FROM attempts WHERE id = %s", (attempt_id,))
                    conn.commit()
            if attempt is None:
                settled.append({"attempt_id": attempt_id, "cancel": "unknown-attempt"})
            elif attempt["lifecycle"] not in ("completed", "failed", "cancelled"):
                done = store.complete_attempt(
                    dsn, Command(request_id=f"{cmd.request_id}:end:{attempt_id}",
                                 payload={"attempt_id": attempt_id,
                                          "outcome": "cancelled",
                                          "ownership_generation":
                                          int(attempt["ownership_generation"])}))
                settled.append({"attempt_id": attempt_id,
                                "cancel": done.code.value})
            else:
                settled.append({"attempt_id": attempt_id,
                                "cancel": "already-terminal"})
        if operation_id:
            op = broker.read_operation(dsn, operation_id)
            if op is None:
                settled.append({"operation_id": operation_id,
                                "settle": "unknown-operation"})
                continue
            state = op["dispatch_state"]
            if state == "prepared":
                if op["reservation_id"] is not None:
                    freed = store.release_reservation(
                        dsn, Command(
                            request_id=f"{cmd.request_id}:release:{operation_id}",
                            payload={"reservation_id": op["reservation_id"]}))
                    settled.append({"operation_id": operation_id,
                                    "settle": freed.code.value})
                else:
                    settled.append({"operation_id": operation_id,
                                    "settle": "nothing-reserved"})
            elif state in ("dispatching", "sent", "unresolved"):
                asked = broker.request_cancel(dsn, operation_id,
                                              launchers=launchers or {})
                if asked.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                    shut = broker.confirm_cancel(dsn, operation_id)
                    settled.append({"operation_id": operation_id,
                                    "settle": shut.code.value})
                else:
                    settled.append({"operation_id": operation_id,
                                    "settle": asked.code.value})
            else:
                settled.append({"operation_id": operation_id,
                                "settle": f"left-{state}"})
    return settled


def revise_team_plan(dsn: str, cmd: Command, *, plan_id: str,
                     children: list[dict],
                     interface_contract: dict | None = None,
                     reason: str = "",
                     launchers: dict | None = None,
                     rework: list[str] | None = None) -> CommandResult:
    # rework names nodes whose prior submission must NOT be carried into
    # the new revision: they get fresh attempts and operations so new
    # bytes can be dispatched and submitted. Without it, a node with
    # unchanged inputs is carried (old bytes copied, attempt completed),
    # which makes revise+resubmit with different bytes impossible.
    inner = Command(request_id=f"{cmd.request_id}:revise",
                    payload={"plan_id": plan_id, "children": children,
                             "interface_contract": interface_contract or {},
                             "reason": reason,
                             "rework": list(rework or [])})

    def _fn(cur, control):
        cur.execute("SELECT * FROM team_plans WHERE plan_id = %s", (plan_id,))
        plan = cur.fetchone()
        if plan is None:
            raise SettlementError(f"unknown team plan {plan_id}")
        if plan["frozen_candidate"]:
            raise SettlementError(f"plan {plan_id} is frozen")
        if int(plan["revision_count"]) >= MAX_REVISIONS:
            raise SettlementError(f"plan {plan_id} already used its one revision")
        cur.execute("SELECT snapshot FROM team_snapshots WHERE digest = %s",
                    (plan["snapshot_digest"],))
        snapshot = dict((cur.fetchone() or {})["snapshot"] or {})
        old_iface = dict(plan["interface_contract"] or {})
        new_iface = dict(interface_contract) if interface_contract is not None else old_iface
        cleaned, _rules = _validate_plan(plan["shape"], snapshot, children, new_iface,
                                         dict(plan["join_rules"] or {}), None)
        old_children = list(plan["children"] or [])
        superseded = [{"attempt_id": old["attempt_id"],
                       "operation_id": old["operation_id"]} for old in old_children]
        superseded.append({"attempt_id": "",
                           "operation_id": f"{plan_id}:r{int(plan['revision'])}:check"})
        new_revision = int(plan["revision"]) + 1
        cur.execute("SELECT COALESCE(MAX(ownership_generation), 0) AS g FROM attempts"
                    " WHERE investigation_id = %s", (plan["investigation_id"],))
        base = int(cur.fetchone()["g"])
        authority = int(control["authority_version"])
        cur.execute("SELECT * FROM allocations WHERE id = %s", (plan["allocation_id"],))
        root = cur.fetchone()
        kid_exp, check_exp = _planned_exposures(len(cleaned))
        iface_same = payload_digest(new_iface) == payload_digest(old_iface)
        cur.execute("SELECT plan_revision, node_id, attempt_id, input_digests,"
                    " ownership_generation, output_digest, receipt_refs"
                    " FROM team_submissions WHERE plan_id = %s AND plan_revision = %s"
                    " AND invalidated = FALSE", (plan_id, int(plan["revision"])))
        prior = {(r["node_id"]): r for r in cur.fetchall()}
        carried: set[str] = set()
        rework = set((inner.payload.get("rework")) or [])
        known = {child["node_id"] for child in cleaned}
        if not rework <= known:
            raise SettlementError(
                "rework names unknown nodes %s" % sorted(rework - known))
        for child in cleaned:
            old = prior.get(child["node_id"])
            if old is None:
                continue
            if child["node_id"] in rework:
                continue
            old_contract = next((c["output_contract"] for c in old_children
                                 if c["node_id"] == child["node_id"]), None)
            if (dict(old["input_digests"] or {})
                    == _input_digests(snapshot, child["input_bindings"])
                    and child["output_contract"] == old_contract
                    and iface_same):
                carried.add(child["node_id"])
        cur.execute("SELECT COALESCE(SUM(authorized), 0) AS total FROM allocations"
                    " WHERE parent_id = %s", (plan["allocation_id"],))
        subdivided = int(cur.fetchone()["total"])
        cur.execute("SELECT authorized, consumed, reserved FROM allocations WHERE id = %s",
                    (plan["allocation_id"],))
        root_funds = cur.fetchone()
        free = store.free_of(dict(root_funds), subdivided)
        need = sum(exp for pos, exp in enumerate(kid_exp)
                   if cleaned[pos]["node_id"] not in carried) + check_exp
        if free < need:
            raise InsufficientResources(
                f"root allocation {plan['allocation_id']} free {free} does not cover"
                f" revision work {need}")
        cur.execute("SELECT revision FROM investigations WHERE id = %s",
                    (plan["investigation_id"],))
        inv_revision = int(cur.fetchone()["revision"])
        stored_children = []
        for pos, child in enumerate(cleaned):
            ids = _op_ids(plan_id, new_revision, child["node_id"])
            if child["node_id"] in carried:
                old = next(c for c in old_children if c["node_id"] == child["node_id"])
                _insert_attempt(cur, plan["investigation_id"], inv_revision,
                                ids["attempt_id"], old["allocation_id"], base + pos + 1,
                                child["node_id"])
                _complete_carried_attempt(cur, ids["attempt_id"])
                _insert_operation(cur, authority, ids["operation_id"],
                                  ids["attempt_id"], old["allocation_id"], 0)
                alloc_id = old["allocation_id"]
            else:
                cur.execute(
                    "INSERT INTO allocations (id, parent_id, domain, epoch, authorized,"
                    " amount_scale, max_occupancy, owner_scope) VALUES (%s, %s, %s, %s,"
                    " %s, 1, 8, %s)",
                    (ids["allocation_id"], plan["allocation_id"], root["domain"],
                     int(root["epoch"]), kid_exp[pos], f"team:{child['node_id']}"))
                _insert_attempt(cur, plan["investigation_id"], inv_revision,
                                ids["attempt_id"], ids["allocation_id"], base + pos + 1,
                                child["node_id"])
                _insert_operation(cur, authority, ids["operation_id"],
                                  ids["attempt_id"], ids["allocation_id"], kid_exp[pos])
                alloc_id = ids["allocation_id"]
            stored_children.append({**child, **ids, "allocation_id": alloc_id,
                                    "input_digests": _input_digests(
                                        snapshot, child["input_bindings"])})
        for node, old in prior.items():
            if node in carried:
                cur.execute(
                    "INSERT INTO team_submissions (plan_id, plan_revision, node_id,"
                    " attempt_id, input_digests, ownership_generation, output_digest,"
                    " receipt_refs) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (plan_id, new_revision, node, old["attempt_id"],
                     Json(dict(old["input_digests"] or {})),
                     int(old["ownership_generation"]), old["output_digest"],
                     Json(list(old["receipt_refs"] or []))))
            else:
                cur.execute("UPDATE team_submissions SET invalidated = TRUE"
                            " WHERE plan_id = %s AND plan_revision = %s AND node_id = %s",
                            (plan_id, int(plan["revision"]), node))
        checker_alloc = f"{plan_id}:r{new_revision}:check"
        cur.execute(
            "INSERT INTO allocations (id, parent_id, domain, epoch, authorized,"
            " amount_scale, max_occupancy, owner_scope) VALUES (%s, %s, %s, %s,"
            " %s, 1, 8, %s)",
            (checker_alloc, plan["allocation_id"], root["domain"], int(root["epoch"]),
             check_exp, "team:check"))
        comp = compile_composition(plan["shape"], cleaned, dict(plan["join_rules"] or {}),
                                   allocation_id=plan["allocation_id"],
                                   authority_version=authority,
                                   budget=dict(plan["budget"] or {}))
        dumped = comp.model_dump()
        dumped["revision"] = new_revision
        cur.execute("UPDATE team_plans SET children = %s, interface_contract = %s,"
                    " checker_allocation_id = %s, composition = %s, revision = %s,"
                    " revision_count = revision_count + 1 WHERE plan_id = %s",
                    (Json(stored_children), Json(new_iface), checker_alloc,
                     Json(dumped), new_revision, plan_id))
        return (ResultCode.APPLIED, f"plan {plan_id} revised to r{new_revision}",
                {"plan_id": plan_id, "revision": new_revision,
                 "composition": dumped, "carried": sorted(carried),
                 "child_operations": {c["node_id"]: c["operation_id"]
                                      for c in stored_children},
                 "superseded": superseded},
                [("team.plan_revised", {"plan_id": plan_id,
                                        "revision": new_revision})], [])
    result = store.transact(dsn, inner, _fn)
    if result.code != ResultCode.APPLIED:
        return result
    result.data["superseded"] = _settle_superseded(
        dsn, cmd, result.data.get("superseded") or [], launchers=launchers)
    plan = _plan_row_conn(dsn, plan_id)
    wired = _wire_packets(dsn, cmd, plan_id, plan["investigation_id"])
    if wired.code != ResultCode.APPLIED:
        result.data["wiring"] = wired.data
        return CommandResult(code=wired.code, request_id=cmd.request_id,
                             detail=wired.detail, data=result.data)
    return result


def dispatch_child(dsn: str, *, plan_id: str, node_id: str,
                   launchers: dict | None = None,
                   revision: int | None = None):
    plan = _plan_row_conn(dsn, plan_id)
    rev = int(plan["revision"]) if revision is None else int(revision)
    operation_id = child_operation(dsn, plan_id, node_id,
                                   rev if rev != int(plan["revision"]) else None)
    generation = child_attempt(dsn, plan_id, node_id,
                               rev if rev != int(plan["revision"]) else None)[
        "ownership_generation"]
    return broker.dispatch_operation(dsn, operation_id, launchers=launchers or {},
                                     ownership_generation=generation)


def resume_team(dsn: str, investigation_id: str) -> dict:
    package = context.resume_package(dsn, investigation_id)
    plans = []
    for brief in package["team"]["plans"]:
        full = _plan_row_conn(dsn, brief["plan_id"])
        done, pending = [], []
        for child in _children_at(full):
            try:
                submission_tuple(dsn, full["plan_id"], int(full["revision"]),
                                 child["node_id"])
                done.append(child["node_id"])
            except LookupError:
                pending.append(child["node_id"])
        op_ids = {c["operation_id"] for c in _children_at(full)}
        unfinished = [op for op in package["pending_operations"]
                      if op["id"] in op_ids]
        wired = True
        for child in _children_at(full):
            try:
                child_binding(dsn, full["plan_id"], child["node_id"])
            except LookupError:
                wired = False
        plans.append({"plan_id": full["plan_id"], "revision": int(full["revision"]),
                      "shape": full["shape"], "completed": done, "pending": pending,
                      "frozen": bool(full["frozen_candidate"]),
                      "wiring_complete": wired,
                      "pending_operations": unfinished,
                      "joins": [j for j in package["team"]["joins"]
                                if j["plan_id"] == full["plan_id"]]})
    return {"investigation_id": investigation_id, "plans": plans}
