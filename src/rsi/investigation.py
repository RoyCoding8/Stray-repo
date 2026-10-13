"""Durable continuation state for persistent RSI investigations.

This module owns the continuation revision and decision/observation links.
The kernel's investigation row remains the only objective authority; dispatch
identity and settlement remain owned by the broker and operations table.
"""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg.types.json import Json

from settlement import db, store
from settlement.common import (
    Command,
    CommandResult,
    ResultCode,
    SettlementError,
    StaleRevision,
)

_OUTCOMES = {"ready", "completed", "unresolved"}
_DEFINITE_PREP_REFUSALS = {
    ResultCode.INVALID_INPUT.value,
    ResultCode.INSUFFICIENT_RESOURCES.value,
    ResultCode.UNAUTHORIZED.value,
    ResultCode.INCOMPATIBLE_VERSION.value,
    ResultCode.MISSING_EVIDENCE.value,
}


def _state(cur, investigation_id: str, *, lock: bool = False) -> dict:
    cur.execute(
        "SELECT s.*, r.objective, i.revision AS current_objective_revision,"
        " i.disposition AS objective_disposition"
        " FROM rsi_investigations s"
        " JOIN investigations i ON i.id = s.investigation_id"
        " JOIN investigation_revisions r ON r.investigation_id = s.investigation_id"
        " AND r.revision = s.objective_revision"
        " WHERE s.investigation_id = %s" + (" FOR UPDATE OF s" if lock else ""),
        (investigation_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise SettlementError(f"unknown investigation {investigation_id}")
    return row


def _expect(cmd: Command, state: dict) -> None:
    expected = cmd.expected_revision
    if isinstance(expected, bool) or not isinstance(expected, int):
        raise SettlementError("expected_revision is required for investigation mutations")
    if expected != int(state["revision"]):
        raise StaleRevision(f"expected revision {expected}, current {state['revision']}")


def _public(row: dict) -> dict:
    pending = None
    if row["pending_decision_id"] is not None:
        pending = dict(row["pending_decision"] or {})
    return {
        "investigation_id": row["investigation_id"],
        "objective": row["objective"],
        "objective_revision": int(row["objective_revision"]),
        "revision": int(row["revision"]),
        "status": row["status"],
        "domain": row["domain"],
        "config": dict(row["config"] or {}),
        "policy": dict(row["policy"] or {}),
        "open_questions": list(row["open_questions"] or []),
        "artifact_refs": dict(row["artifact_refs"] or {}),
        "pending_decision": pending,
        "last_observation": (dict(row["last_observation"])
                             if row["last_observation"] is not None else None),
    }


def _load_public(cur, investigation_id: str, *, lock: bool = False) -> dict:
    row = _state(cur, investigation_id, lock=lock)
    if row["pending_decision_id"] is not None:
        cur.execute("SELECT id, data FROM rsi_decisions WHERE id = %s",
                    (row["pending_decision_id"],))
        decision = cur.fetchone()
        data = dict(decision["data"] or {}) if decision else {}
        row["pending_decision"] = {
            "id": row["pending_decision_id"],
            "attempt_id": row["pending_attempt_id"],
            "operation_id": data.get("operation_id"),
            "action": data.get("action"),
            "visible_input": data.get("visible_input"),
        }
    return _public(row)


def _record_refusal(cur, state: dict, *, operation_id: str, reason: str) -> tuple:
    """Close a worker attempt only from a durable, definitive prepare refusal."""
    cur.execute("SELECT 1 FROM operations WHERE attempt_id = %s LIMIT 1",
                (state["pending_attempt_id"],))
    if cur.fetchone() is not None:
        return (ResultCode.OUTCOME_UNKNOWN,
                "attempt has an operation row; refusal cannot establish no effect",
                {"status": "pending", "operation_id": operation_id}, [], [])
    observation = {"episode": operation_id, "status": "refused", "passed": None,
                   "verdict": None, "solution": None, "reason": reason}
    cur.execute("INSERT INTO attempt_observations (attempt_id, decision_id, content)"
                " VALUES (%s, %s, %s)",
                (state["pending_attempt_id"], state["pending_decision_id"], Json(observation)))
    cur.execute("SELECT * FROM attempts WHERE id = %s FOR UPDATE",
                (state["pending_attempt_id"],))
    attempt = cur.fetchone()
    store._end_attempt(cur, attempt, "failed")
    revision = int(state["revision"]) + 1
    cur.execute("UPDATE rsi_investigations SET revision = %s, status = 'unresolved',"
                " pending_decision_id = NULL, pending_attempt_id = NULL,"
                " last_observation = %s, updated_at = now() WHERE investigation_id = %s",
                (revision, Json(observation), state["investigation_id"]))
    data = {"investigation_id": state["investigation_id"], "revision": revision,
            "status": "unresolved", "operation_id": operation_id}
    return (ResultCode.APPLIED, "durable pre-dispatch refusal recorded as unresolved", data,
            [("rsi.investigation.unresolved", {**data, "reason": reason})], [])


def create(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        inv_id = p.get("investigation_id")
        objective = p.get("objective")
        domain = p.get("domain")
        allocation_id = p.get("allocation_id")
        if not isinstance(inv_id, str) or not inv_id.strip():
            raise SettlementError("investigation_id must be a non-empty string")
        if not isinstance(objective, str) or not objective.strip():
            raise SettlementError("objective must be a non-empty string")
        if not isinstance(domain, str) or not domain.strip():
            raise SettlementError("domain must be a non-empty string")
        if not isinstance(allocation_id, str) or not allocation_id.strip():
            raise SettlementError("allocation_id must be a non-empty string")
        inv_id = inv_id.strip()
        objective = objective.strip()
        domain = domain.strip()
        allocation_id = allocation_id.strip()
        config_value = p.get("config")
        policy_value = p.get("policy")
        questions_value = p.get("open_questions")
        refs_value = p.get("artifact_refs")
        if not isinstance(config_value, dict) or not isinstance(policy_value, dict):
            raise SettlementError("config and policy must be objects")
        if not isinstance(refs_value, dict):
            raise SettlementError("artifact_refs must be an object")
        if not isinstance(questions_value, list) or not questions_value:
            raise SettlementError("open_questions must be a non-empty list")
        config = dict(config_value)
        policy = dict(policy_value)
        questions = list(questions_value)
        refs = dict(refs_value)
        if any(not isinstance(q, str) or not q.strip() for q in questions):
            raise SettlementError("open_questions must contain non-empty strings")
        if domain == "task":
            if not isinstance(config.get("max_steps"), int) or isinstance(config.get("max_steps"), bool) or config["max_steps"] < 1:
                raise SettlementError("task config max_steps must be a positive integer")
            if config.get("token_allocation") != allocation_id:
                raise SettlementError("allocation_id must be the configured token allocation")
            for key in ("token_allocation", "cpu_allocation"):
                aid = config.get(key)
                if not isinstance(aid, str) or not aid:
                    raise SettlementError(f"task config {key} is required")
                cur.execute("SELECT 1 FROM allocations WHERE id = %s", (aid,))
                if cur.fetchone() is None:
                    raise SettlementError(f"unknown {key} {aid}")
        cur.execute("SELECT 1 FROM investigations WHERE id = %s", (inv_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"investigation {inv_id} already exists")
        cur.execute(
            "INSERT INTO investigations (id, revision, objective, scope, obligations, sponsor, origin, disposition)"
            " VALUES (%s, 1, %s, %s, %s, %s, %s, 'accepted')",
            (inv_id, objective, Json({}), Json({}), "rsi", "persistent-investigation"),
        )
        cur.execute(
            "INSERT INTO investigation_revisions (investigation_id, revision, objective, obligations)"
            " VALUES (%s, 1, %s, %s)", (inv_id, objective, Json({})),
        )
        cur.execute(
            "INSERT INTO rsi_investigations (investigation_id, objective_revision, domain, config, policy,"
            " allocation_id, open_questions, artifact_refs) VALUES (%s, 1, %s, %s, %s, %s, %s, %s)",
            (inv_id, domain, Json(config), Json(policy), allocation_id,
             Json(questions), Json(refs)),
        )
        data = {"investigation_id": inv_id, "objective_revision": 1, "revision": 0}
        return (ResultCode.APPLIED, f"investigation {inv_id} created", data,
                [("commitment.admitted", {"investigation_id": inv_id, "revision": 1}),
                 ("rsi.investigation.created", data)], [])
    return store.transact(dsn, cmd, _fn)


def read(dsn: str, investigation_id: str) -> dict | None:
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        try:
            return _load_public(cur, investigation_id)
        except SettlementError:
            return None


def decide(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        state = _state(cur, str(p["investigation_id"]), lock=True)
        _expect(cmd, state)
        if state["status"] != "ready":
            raise SettlementError(f"investigation is {state['status']}; only ready state accepts a decision")
        if state["objective_disposition"] in ("withdrawn", "fulfilled"):
            raise SettlementError(f"kernel objective is {state['objective_disposition']}")
        if int(state["current_objective_revision"]) != int(state["objective_revision"]):
            raise StaleRevision("kernel objective changed; investigation must be explicitly rebound")
        decision_id = str(p["decision_id"])
        action = p.get("action")
        visible = p.get("visible_input")
        if not isinstance(visible, dict):
            raise SettlementError("visible_input must be an object")
        if (not isinstance(action, dict) or action.get("kind") != "worker"
                or set(action) - {"kind", "explanation", "intended_observation"}
                or not isinstance(action.get("explanation"), str)
                or not isinstance(action.get("intended_observation"), str)):
            cur.execute("INSERT INTO rsi_decisions (id, kind, actor, subject, data)"
                        " VALUES (%s, 'unresolved', 'fixed', %s, %s)",
                        (decision_id, state["investigation_id"],
                         Json({"reason": "unsupported action", "action": action,
                                "visible_input": visible})))
            revision = int(state["revision"]) + 1
            obs = {"kind": "unresolved", "reason": "unsupported action", "action": action}
            cur.execute("UPDATE rsi_investigations SET revision = %s, status = 'unresolved',"
                        " last_observation = %s, updated_at = now() WHERE investigation_id = %s",
                        (revision, Json(obs), state["investigation_id"]))
            return (ResultCode.APPLIED, "unsupported action recorded as unresolved",
                    {"revision": revision, "status": "unresolved"},
                    [("rsi.investigation.unresolved", {"investigation_id": state["investigation_id"],
                                                        "reason": "unsupported action"})], [])

        config = dict(state["config"] or {})
        cur.execute("SELECT count(*) AS n FROM rsi_decisions WHERE subject = %s AND kind = 'worker'",
                    (state["investigation_id"],))
        steps = int(cur.fetchone()["n"])
        if steps >= int(config["max_steps"]):
            cur.execute("INSERT INTO rsi_decisions (id, kind, actor, subject, data)"
                        " VALUES (%s, 'unresolved', 'fixed', %s, %s)",
                        (decision_id, state["investigation_id"],
                         Json({"reason": "max_steps exhausted", "visible_input": visible})))
            revision = int(state["revision"]) + 1
            obs = {"kind": "unresolved", "reason": "max_steps exhausted"}
            cur.execute("UPDATE rsi_investigations SET revision = %s, status = 'unresolved',"
                        " last_observation = %s, updated_at = now() WHERE investigation_id = %s",
                        (revision, Json(obs), state["investigation_id"]))
            return (ResultCode.APPLIED, "max_steps exhaustion recorded as unresolved",
                    {"revision": revision, "status": "unresolved"},
                    [("rsi.investigation.unresolved", {"investigation_id": state["investigation_id"],
                                                        "reason": "max_steps exhausted"})], [])
        if not all(k in visible for k in ("objective", "objective_revision", "state_revision",
                                          "open_questions", "artifact_refs", "previous_observation")):
            raise SettlementError("visible_input must include objective and the full continuation")
        if (visible["objective_revision"] != int(state["objective_revision"])
                or visible["state_revision"] != int(state["revision"])):
            raise StaleRevision("visible_input revision identity does not match current state")
        expected_visible = {
            "objective": state["objective"],
            "objective_revision": int(state["objective_revision"]),
            "state_revision": int(state["revision"]),
            "open_questions": list(state["open_questions"] or []),
            "artifact_refs": dict(state["artifact_refs"] or {}),
            "previous_observation": (dict(state["last_observation"])
                                     if state["last_observation"] is not None else None),
        }
        if any(visible[k] != v for k, v in expected_visible.items()):
            raise StaleRevision("visible_input does not match the current continuation")
        operation_id = str(p["operation_id"])
        if not operation_id:
            raise SettlementError("operation_id is required")
        cur.execute("SELECT 1 FROM operations WHERE id = %s UNION ALL"
                    " SELECT 1 FROM rsi_decisions WHERE data->>'operation_id' = %s LIMIT 1",
                    (operation_id, operation_id))
        if cur.fetchone() is not None:
            raise SettlementError(f"operation identity {operation_id} is already reserved")
        cur.execute("INSERT INTO rsi_decisions (id, kind, actor, subject, data)"
                    " VALUES (%s, 'worker', 'fixed', %s, %s)",
                    (decision_id, state["investigation_id"], Json({
                        "action": action, "visible_input": visible,
                        "operation_id": operation_id,
                        "attempt_id": str(p["attempt_id"]),
                    })))
        acquired = store._acquire_work(
            cur, investigation_id=state["investigation_id"],
            attempt_id=str(p["attempt_id"]), allocation_id=None,
            composition=str(config.get("genome", "")),
            model="", env="", owner=decision_id, kind="task",
        )
        revision = int(state["revision"]) + 1
        cur.execute("UPDATE rsi_investigations SET revision = %s, status = 'pending',"
                    " pending_decision_id = %s, pending_attempt_id = %s, updated_at = now()"
                    " WHERE investigation_id = %s",
                    (revision, decision_id, acquired["attempt_id"], state["investigation_id"]))
        data = {"investigation_id": state["investigation_id"], "revision": revision,
                "decision_id": decision_id, "attempt_id": acquired["attempt_id"],
                "operation_id": operation_id}
        return (ResultCode.APPLIED, "decision and attempt reserved before dispatch", data,
                [("rsi.investigation.decision", data),
                 ("work.acquired", {"attempt_id": acquired["attempt_id"],
                                     "ownership_generation": acquired["ownership_generation"]})], [])
    return store.transact(dsn, cmd, _fn)


def observe(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        p = cmd.payload
        state = _state(cur, str(p["investigation_id"]), lock=True)
        _expect(cmd, state)
        if state["status"] not in ("pending", "suspended") or state["pending_decision_id"] is None:
            raise SettlementError("investigation has no pending decision to observe")
        if state["objective_disposition"] in ("withdrawn", "fulfilled"):
            raise SettlementError(f"kernel objective is {state['objective_disposition']}")
        if int(state["current_objective_revision"]) != int(state["objective_revision"]):
            raise StaleRevision("kernel objective changed during the pending effect")
        if p.get("decision_id") != state["pending_decision_id"]:
            raise StaleRevision("observation decision does not match pending decision")
        cur.execute("SELECT id, data FROM rsi_decisions WHERE id = %s",
                    (state["pending_decision_id"],))
        decision = cur.fetchone()
        decision_data = dict(decision["data"] or {})
        operation_id = decision_data.get("operation_id")
        if p.get("operation_id") != operation_id:
            raise StaleRevision("observation operation does not match pending operation")
        supplied = dict(p.get("observation", {}))
        episode_id = supplied.get("episode")
        if episode_id != operation_id:
            raise SettlementError("worker episode must use the reserved operation identity")
        # A pending or uncertain effect is not an observation. Preserve the exact
        # reservation so recovery can inspect or settle this same operation.
        cur.execute("SELECT id, attempt_id, settled, dispatch_state, reconcile_state"
                    " FROM operations WHERE id = %s", (operation_id,))
        op = cur.fetchone()
        if op is None:
            prep_id = f"broker-prep-{operation_id}"
            cur.execute("SELECT result_code, result_detail FROM command_journal WHERE request_id = %s",
                        (prep_id,))
            refusal = cur.fetchone()
            if (refusal is not None and refusal["result_code"] in _DEFINITE_PREP_REFUSALS
                    and p.get("outcome") == "unresolved"
                    and supplied.get("status") == "refused"
                    and supplied.get("passed") is None
                    and supplied.get("verdict") is None
                    and supplied.get("solution") is None):
                return _record_refusal(cur, state, operation_id=operation_id,
                                       reason=str(refusal["result_detail"]))
            return (ResultCode.OUTCOME_UNKNOWN,
                    "operation is absent without a definitive prepare refusal; pending identity retained",
                    {"status": "pending", "operation_id": operation_id}, [], [])
        if (op["attempt_id"] != state["pending_attempt_id"]
                or not bool(op["settled"]) or op["dispatch_state"] not in ("observed", "reconciled")
                or op["reconcile_state"] in ("conflict", "unresolved")):
            return (ResultCode.OUTCOME_UNKNOWN, "worker operation is not settled; pending identity retained",
                    {"status": "pending", "operation_id": operation_id}, [], [])
        config = dict(state["config"] or {})
        cur.execute("SELECT operation_id, genome, task, status, trajectory"
                    " FROM rsi_episodes WHERE operation_id = %s",
                    (operation_id,))
        episode = cur.fetchone()
        if (episode is None or episode["genome"] != config.get("genome")
                or episode["task"] != config.get("task")):
            return (ResultCode.OUTCOME_UNKNOWN, "settled operation has no episode record; pending identity retained",
                    {"status": "pending", "operation_id": operation_id}, [], [])
        cur.execute("SELECT id, dispatch_state, reconcile_state, settled FROM operations"
                    " WHERE attempt_id = %s ORDER BY id", (state["pending_attempt_id"],))
        effects = cur.fetchall()
        if any(not bool(effect["settled"])
               or effect["dispatch_state"] not in ("observed", "reconciled")
               or effect["reconcile_state"] in ("conflict", "unresolved")
               for effect in effects):
            return (ResultCode.OUTCOME_UNKNOWN,
                    "an associated effect is unsettled or conflicted; pending identity retained",
                    {"status": "pending", "operation_id": operation_id}, [], [])
        cur.execute("SELECT v.episode, v.operation_id, v.solution, v.status, v.passed, v.detail,"
                    " o.settled AS verifier_settled FROM rsi_verdicts v"
                    " JOIN operations o ON o.id = v.operation_id"
                    " JOIN rsi_episodes e ON e.operation_id = v.episode"
                    " JOIN rsi_tasks t ON t.digest = e.task AND t.evaluator_version = v.evaluator_version"
                    " WHERE v.episode = %s ORDER BY v.created_at DESC LIMIT 1", (operation_id,))
        verdict = cur.fetchone()
        outcome = p.get("outcome")
        if outcome not in _OUTCOMES:
            raise SettlementError("outcome must be ready, completed, or unresolved")
        if verdict is None or not bool(verdict["verifier_settled"]):
            # A real, settled non-completed episode is an inspectable terminal
            # failure, but cannot establish task success or a checked continuation.
            if (outcome != "unresolved" or episode["status"] == "completed"
                    or supplied.get("status") != episode["status"]
                    or supplied.get("passed") is not None
                    or supplied.get("verdict") is not None
                    or supplied.get("solution") is not None):
                return (ResultCode.OUTCOME_UNKNOWN,
                        "checked verdict is unavailable; pending identity retained",
                        {"status": "pending", "operation_id": operation_id}, [], [])
        else:
            if (supplied.get("solution") != verdict["solution"]
                    or supplied.get("verdict") != verdict["operation_id"]
                    or supplied.get("status") != verdict["status"]
                    or supplied.get("passed") is not verdict["passed"]):
                raise SettlementError("observation does not match the stored checked verdict")
            if outcome == "completed" and (state["domain"] != "task" or verdict["status"] != "passed"
                                            or verdict["passed"] is not True):
                raise SettlementError("completion requires a stored passing task verdict")
            if outcome == "ready" and (state["domain"] != "task" or verdict["status"] != "failed"
                                        or verdict["passed"] is not False):
                raise SettlementError("ready continuation requires a stored failed task verdict")
            if state["domain"] != "task" and outcome == "completed":
                raise SettlementError("this domain has no registered completion checker")
            cur.execute("SELECT attempt_id, settled, dispatch_state, reconcile_state FROM operations"
                        " WHERE id = %s", (verdict["operation_id"],))
            verifier_op = cur.fetchone()
            if (verifier_op is None or verifier_op["attempt_id"] != state["pending_attempt_id"]
                    or not bool(verifier_op["settled"])
                    or verifier_op["dispatch_state"] not in ("observed", "reconciled")
                    or verifier_op["reconcile_state"] in ("conflict", "unresolved")):
                return (ResultCode.OUTCOME_UNKNOWN,
                        "verifier operation is unsettled or conflicted; pending identity retained",
                        {"status": "pending", "operation_id": operation_id}, [], [])
        expected_refs = {"trajectory": episode["trajectory"]}
        if supplied.get("solution") is not None:
            expected_refs["solution"] = supplied["solution"]
        if dict(p.get("artifact_refs", {})) != expected_refs:
            raise SettlementError("artifact_refs must identify the stored episode trajectory and solution")
        questions = list(p.get("open_questions", []))
        refs = dict(p.get("artifact_refs", {}))
        observation = {k: supplied.get(k) for k in
                       ("episode", "status", "passed", "verdict", "solution", "reason")}
        attempt_id = state["pending_attempt_id"]
        cur.execute("INSERT INTO attempt_observations (attempt_id, decision_id, content)"
                    " VALUES (%s, %s, %s)",
                    (attempt_id, state["pending_decision_id"], Json(observation)))
        cur.execute("SELECT * FROM attempts WHERE id = %s FOR UPDATE", (attempt_id,))
        attempt = cur.fetchone()
        store._end_attempt(cur, attempt, "completed" if outcome in ("completed", "ready") else "failed")
        if outcome == "completed":
            status = "completed"
        elif outcome == "unresolved":
            status = "unresolved"
        else:
            status = "suspended" if state["status"] == "suspended" else "ready"
        revision = int(state["revision"]) + 1
        cur.execute("UPDATE rsi_investigations SET revision = %s, status = %s,"
                    " pending_decision_id = NULL, pending_attempt_id = NULL,"
                    " open_questions = %s, artifact_refs = %s, last_observation = %s, updated_at = now()"
                    " WHERE investigation_id = %s",
                    (revision, status, Json(questions), Json(refs), Json(observation),
                     state["investigation_id"]))
        data = {"investigation_id": state["investigation_id"], "revision": revision,
                "status": status, "observation": observation}
        return (ResultCode.APPLIED, "checked observation recorded", data,
                [("rsi.investigation.observed", {"investigation_id": state["investigation_id"],
                                                  "decision_id": state["pending_decision_id"],
                                                  "status": status})], [])
    return store.transact(dsn, cmd, _fn)


def suspend(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        state = _state(cur, str(cmd.payload["investigation_id"]), lock=True)
        _expect(cmd, state)
        if state["status"] not in ("ready", "pending"):
            raise SettlementError(f"investigation is {state['status']} and cannot be suspended")
        revision = int(state["revision"]) + 1
        cur.execute("UPDATE rsi_investigations SET revision = %s, status = 'suspended', updated_at = now()"
                    " WHERE investigation_id = %s", (revision, state["investigation_id"]))
        data = {"investigation_id": state["investigation_id"], "revision": revision,
                "status": "suspended"}
        return (ResultCode.APPLIED, "investigation suspended; admitted effects retained", data,
                [("rsi.investigation.suspended", data)], [])
    return store.transact(dsn, cmd, _fn)


def resume(dsn: str, cmd: Command) -> CommandResult:
    def _fn(cur, control):
        state = _state(cur, str(cmd.payload["investigation_id"]), lock=True)
        _expect(cmd, state)
        if state["status"] != "suspended":
            raise SettlementError(f"investigation is {state['status']}; only suspended state resumes")
        status = "pending" if state["pending_decision_id"] is not None else "ready"
        revision = int(state["revision"]) + 1
        cur.execute("UPDATE rsi_investigations SET revision = %s, status = %s, updated_at = now()"
                    " WHERE investigation_id = %s", (revision, status, state["investigation_id"]))
        data = {"investigation_id": state["investigation_id"], "revision": revision,
                "status": status, "pending_decision_id": state["pending_decision_id"]}
        return (ResultCode.APPLIED, "investigation resumed", data,
                [("rsi.investigation.resumed", data)], [])
    return store.transact(dsn, cmd, _fn)


def export(dsn: str, investigation_id: str) -> dict | None:
    state = read(dsn, investigation_id)
    if state is None:
        return None
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT d.id, d.kind, d.actor, d.data, d.created_at FROM rsi_decisions d"
                    " WHERE d.subject = %s ORDER BY d.created_at, d.id", (investigation_id,))
        decisions = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT o.id, o.decision_id, o.content, o.created_at FROM attempt_observations o"
                    " JOIN attempts a ON a.id = o.attempt_id WHERE a.investigation_id = %s"
                    " ORDER BY o.id", (investigation_id,))
        observations = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT o.id, o.dispatch_state, o.reconcile_state, o.settled,"
                    " o.receipt_provenance FROM operations o JOIN attempts a ON a.id = o.attempt_id"
                    " WHERE a.investigation_id = %s ORDER BY o.created_at, o.id",
                    (investigation_id,))
        effects = [dict(row) for row in cur.fetchall()]
        for effect in effects:
            cur.execute("SELECT receipt_identity, content_digest, outcome, created_at FROM receipts"
                        " WHERE operation_id = %s ORDER BY created_at, receipt_identity",
                        (effect["id"],))
            effect["receipts"] = [dict(row) for row in cur.fetchall()]
        if state["pending_decision"] is not None and not any(
                effect["id"] == state["pending_decision"]["operation_id"] for effect in effects):
            effects.append({"id": state["pending_decision"]["operation_id"],
                            "dispatch_state": "not_admitted", "reconcile_state": "none",
                            "settled": False, "receipt_provenance": "", "receipts": []})
    return {"state": state, "decisions": decisions, "observations": observations,
            "unresolved_effects": [effect for effect in effects
                                   if (effect["reconcile_state"] in ("unresolved", "conflict")
                                       or not effect["settled"]
                                       or effect["dispatch_state"] not in
                                       ("observed", "reconciled", "cancelled"))]}
