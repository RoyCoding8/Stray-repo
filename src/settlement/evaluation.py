"""S3 evaluation (IF-6, LEARN-2): versioned evaluator packages, hidden answers
outside candidate access, authenticated evaluator receipts.

Candidates submit content; only the evaluator writes receipts, and only
through an actual broker invocation bound as ``invocation_ref``. Evaluator
version pins are enforced: a swapped always-pass evaluator cannot release
old results.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import broker, db, evidence, store, trials
from .common import (
    Command,
    CommandResult,
    ResultCode,
    SettlementError,
    Unauthorized,
    payload_digest,
)

ANSWER_PREFIX = "s3-answer:"


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def register_evaluator(dsn: str, cmd: Command, evaluator_id: str, version: str,
                       access_policy: dict | None = None,
                       code_digest: str = "") -> CommandResult:
    if not evaluator_id or not version:
        raise SettlementError("evaluator needs an id and version")

    def _fn(cur, control):
        cur.execute("INSERT INTO evaluator_packages (id, version, access_policy, code_digest)"
                    " VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                    (evaluator_id, version, _j(access_policy or {}), code_digest))
        if code_digest:
            cur.execute("UPDATE evaluator_packages SET code_digest = %s"
                        " WHERE id = %s AND code_digest = ''",
                        (code_digest, evaluator_id))
        return (ResultCode.APPLIED, f"evaluator {evaluator_id} v{version} registered",
                {"evaluator_id": evaluator_id, "version": version},
                [("evaluation.evaluator_registered", {"evaluator_id": evaluator_id})], [])
    return store.transact(dsn, cmd, _fn)


def propose_hidden_answer(dsn: str, cmd: Command, task_id: str,
                          answer: dict) -> CommandResult:
    claim_id = f"{ANSWER_PREFIX}{task_id}"
    sub = Command(request_id=f"{cmd.request_id}:answer:{task_id}",
                  payload={"claim_id": claim_id})
    return evidence.propose_claim(dsn, sub, claim_id, {"task_id": task_id, **answer},
                                  scope={"task_id": task_id}, access_label="hidden")


def hidden_answer(dsn: str, task_id: str, scope: str) -> dict:
    if scope not in ("evaluator", "operator"):
        raise Unauthorized(f"hidden answers are never served to {scope!r} scope")
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT proposition FROM claims WHERE id = %s",
                        (f"{ANSWER_PREFIX}{task_id}",))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"no hidden answer for {task_id}")
    return dict(row["proposition"])


def candidate_view(dsn: str) -> list[dict]:
    return evidence.scoped_claims(dsn, "candidate")


def submit_candidate(dsn: str, cmd: Command, assignment_id: str,
                     content: dict) -> CommandResult:
    digest = payload_digest(content or {})
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT candidate_digest FROM trial_assignments WHERE id = %s",
                        (assignment_id,))
            bound = cur.fetchone()
            conn.commit()
    if bound is None:
        raise SettlementError(f"unknown assignment {assignment_id}")
    if bound["candidate_digest"] and digest != bound["candidate_digest"]:
        raise SettlementError(
            f"candidate bytes do not match the bound digest for assignment"
            f" {assignment_id}: post-binding replacement refused")

    def _fn(cur, control):
        cur.execute("SELECT candidate_digest FROM trial_assignments WHERE id = %s",
                    (assignment_id,))
        bound = cur.fetchone()
        if bound is None:
            raise SettlementError(f"unknown assignment {assignment_id}")
        if bound["candidate_digest"] and digest != bound["candidate_digest"]:
            raise SettlementError(
                f"candidate bytes do not match the bound digest for assignment"
                f" {assignment_id}: post-binding replacement refused")
        cur.execute("INSERT INTO candidate_submissions (assignment_id, content)"
                    " VALUES (%s, %s)", (assignment_id, _j(content)))
        return (ResultCode.APPLIED, f"candidate submission recorded for {assignment_id}",
                {"assignment_id": assignment_id, "content_digest": digest},
                [("evaluation.candidate_submitted", {"assignment_id": assignment_id})], [])
    return store.transact(dsn, cmd, _fn)


def _tallies(contents: list) -> list[dict]:
    found = []
    for content in contents:
        worker = (dict(content or {}).get("data") or {}).get("worker") or {}
        detail = worker.get("data") if isinstance(worker, dict) else None
        if not isinstance(detail, dict):
            continue
        counts = detail
        if all(type(counts.get(key)) is int for key in ("passed", "failed", "total")):
            found.append({"passed": counts["passed"], "failed": counts["failed"],
                          "total": counts["total"],
                          "failures": counts.get("failures") or []})
    return found


def _tally_clean(tally: dict) -> bool:
    return tally["failed"] == 0 and tally["total"] > 0 \
        and tally["passed"] == tally["total"] and not tally["failures"]


def _check_claimed_outcome(invocation_ref: str, op_success: bool,
                           tallies: list[dict], outcome: str) -> None:
    if outcome == "success":
        if not op_success:
            raise SettlementError(
                f"invocation {invocation_ref} never succeeded:"
                " failed operation labeled success refused")
        dirty = [t for t in tallies if not _tally_clean(t)]
        if dirty:
            failed = sum(max(t["failed"], len(t["failures"])) for t in dirty)
            total = sum(t["total"] for t in dirty)
            raise SettlementError(
                f"invocation {invocation_ref} grader reported {failed} failed"
                f" cases out of {total}: operation success is not evaluation"
                " success; success refused")
        return
    if any(_tally_clean(t) for t in tallies):
        clean = next(t for t in tallies if _tally_clean(t))
        raise SettlementError(
            f"invocation {invocation_ref} grader passed {clean['passed']}/"
            f"{clean['total']}: {outcome!r} diverges from the authenticated"
            " grader result; failure labels for a passing run refused")
    if op_success and not tallies:
        raise SettlementError(
            f"invocation {invocation_ref} succeeded with no recorded test"
            f" outcome: {outcome!r} diverges from the authenticated result;"
            " only success may be claimed")


def _bound_proof(assignment) -> dict:
    instance = ((assignment or {}).get("instance") or {})
    if not isinstance(instance, dict):
        return {}
    proof = instance.get("evaluation_binding") or {}
    return dict(proof) if isinstance(proof, dict) else {}


def _bind_state(assignment, digests, clash, has_receipt, op, pin, package) -> dict:
    body = dict((op or {}).get("payload") or {})
    return {"assignment": assignment, "digests": list(digests), "clash": clash,
            "has_receipt": bool(has_receipt), "op": op,
            "op_state": (op or {}).get("dispatch_state", ""),
            "op_effect": body.get("effect", ""), "pin": pin or "",
            "package": package, "binding": _bound_proof(assignment)}


def _proven_executable(state: dict, executable_digest: str) -> str:
    return executable_digest or (state.get("binding") or {}).get("executable_digest", "")


def _check_executable_proof(state: dict, executable_digest: str, *,
                            assignment_id: str, evaluator_id: str,
                            evaluator_version: str) -> str:
    pinned = (state["package"] or {}).get("code_digest", "") \
        if state["package"] else ""
    proven = _proven_executable(state, executable_digest)
    if pinned and proven != pinned:
        raise SettlementError(
            f"evaluation binding for assignment {assignment_id} proves no"
            f" executable matching evaluator {evaluator_id} v{evaluator_version}:"
            " unrelated observed operation refused")
    return proven


def _verify_bind(state: dict, *, assignment_id: str, candidate_digest: str,
                 evaluator_id: str, evaluator_version: str,
                 invocation_ref: str, executable_digest: str = "",
                 input_digest: str = "") -> bool:
    assignment = state["assignment"]
    if assignment is None:
        raise SettlementError(f"unknown assignment {assignment_id}")
    if assignment["evaluation_op"]:
        if (assignment["candidate_digest"], assignment["evaluator_id"],
                assignment["evaluator_version"], assignment["evaluation_op"]) == \
                (candidate_digest, evaluator_id, evaluator_version, invocation_ref):
            return True
        raise SettlementError(
            f"assignment {assignment_id} already has an immutable evaluation"
            " binding: rebinding refused")
    if state["has_receipt"]:
        raise SettlementError(
            f"assignment {assignment_id} already has an evaluator receipt:"
            " post-hoc binding refused")
    if state["pin"] != evaluator_version:
        raise SettlementError(
            f"version pin mismatch: protocol {assignment['protocol_id']} pins"
            f" evaluator {state['pin']!r}, binding uses {evaluator_version!r}")
    if state["package"] is None:
        raise SettlementError(f"unknown evaluator {evaluator_id}")
    if state["package"]["version"] != evaluator_version:
        raise SettlementError(
            f"evaluator {evaluator_id} is {state['package']['version']!r},"
            f" binding claims {evaluator_version!r}")
    _check_executable_proof(state, executable_digest, assignment_id=assignment_id,
                            evaluator_id=evaluator_id,
                            evaluator_version=evaluator_version)
    if state["op"] is None:
        raise SettlementError(
            f"evaluation binding references no actual invocation {invocation_ref}")
    if state["op_state"] != "prepared":
        raise SettlementError(
            f"invocation {invocation_ref} is already {state['op_state']}:"
            " evaluation binding must precede launch")
    if state["op_effect"] != broker.SANDBOX_EXEC:
        raise SettlementError(
            f"invocation {invocation_ref} is not a grader execution"
            f" ({state['op_effect'] or 'unknown effect'}):"
            " evaluation binding refused")
    if not state["digests"]:
        raise SettlementError(
            f"assignment {assignment_id} has no candidate submission to bind")
    if candidate_digest not in state["digests"]:
        raise SettlementError(
            f"bound candidate digest matches no submission for assignment"
            f" {assignment_id}: mismatched candidate bytes refused")
    if state["clash"]:
        raise SettlementError(
            f"invocation {invocation_ref} already backs {state['clash']}:"
            " unrelated observed operation refused")
    return False


def _receipt_state(assignment, digests, clash, duplicate, op, broker_rows,
                   pin, package) -> dict:
    tallies = _tallies([r["content"] for r in broker_rows])
    return {"assignment": assignment, "digests": list(digests), "clash": clash,
            "duplicate": bool(duplicate), "op": op,
            "op_state": (op or {}).get("dispatch_state", ""),
            "op_success": any(r["outcome"] == "success" for r in broker_rows),
            "tallies": tallies, "pin": pin or "", "package": package,
            "binding": _bound_proof(assignment)}


def _verify_receipt(state: dict, *, assignment_id: str, evaluator_id: str,
                    evaluator_version: str, invocation_ref: str,
                    result: dict) -> None:
    assignment = state["assignment"]
    if assignment is None:
        raise SettlementError(f"unknown assignment {assignment_id}")
    bound_op = assignment["evaluation_op"] or ""
    if not bound_op:
        raise SettlementError(
            f"assignment {assignment_id} has no immutable evaluation binding:"
            " bind candidate, evaluator and invocation before launch;"
            " unrelated observed operation refused")
    if invocation_ref != bound_op:
        raise SettlementError(
            f"invocation {invocation_ref} is not the bound evaluation invocation"
            f" {bound_op} for assignment {assignment_id}:"
            " unrelated observed operation refused")
    if (evaluator_id, evaluator_version) != (assignment["evaluator_id"],
                                             assignment["evaluator_version"]):
        raise SettlementError(
            f"evaluator {evaluator_id} v{evaluator_version} does not match the"
            f" bound evaluator {assignment['evaluator_id']}"
            f" v{assignment['evaluator_version']} for assignment {assignment_id}:"
            " evaluator replacement refused")
    if state["pin"] != evaluator_version:
        raise SettlementError(
            f"version pin mismatch: protocol {assignment['protocol_id']} pins"
            f" evaluator {state['pin']!r}, receipt uses {evaluator_version!r}")
    if state["package"] is None:
        raise SettlementError(f"unknown evaluator {evaluator_id}")
    if state["package"]["version"] != evaluator_version:
        raise SettlementError(
            f"evaluator {evaluator_id} is {state['package']['version']!r},"
            f" receipt claims {evaluator_version!r}")
    if not state["digests"]:
        raise SettlementError(
            f"assignment {assignment_id} has no candidate submission to evaluate")
    if state["digests"][-1] != assignment["candidate_digest"]:
        raise SettlementError(
            f"candidate submission for assignment {assignment_id} does not match"
            " its bound digest: mismatched candidate bytes refused")
    detail = result.get("detail", {})
    if not isinstance(detail, dict) or detail.get("task_id") != assignment["task_id"]:
        raise SettlementError(
            f"receipt result for assignment {assignment_id} names task"
            f" {detail.get('task_id') if isinstance(detail, dict) else None!r},"
            f" bound task is {assignment['task_id']!r}:"
            " task identity mismatch refused")
    if state["op"] is None:
        raise SettlementError(
            f"receipt references no actual invocation {invocation_ref}")
    if state["op_state"] not in ("observed", "reconciled"):
        raise SettlementError(
            f"invocation {invocation_ref} has no observed receipt")
    _check_executable_proof(state, "", assignment_id=assignment_id,
                            evaluator_id=evaluator_id,
                            evaluator_version=evaluator_version)
    if (state.get("binding") or {}).get("executable_digest") \
            and result.get("outcome") == "success" and not state["tallies"]:
        raise SettlementError(
            f"invocation {invocation_ref} succeeded with no recorded test"
            " outcome: bare process success cannot certify an evaluation"
            " outcome; only an authenticated grader result may")
    _check_claimed_outcome(invocation_ref, state["op_success"], state["tallies"],
                           result.get("outcome", ""))
    if state["clash"]:
        raise SettlementError(
            f"invocation {invocation_ref} already backs {state['clash']}:"
            " unrelated observed operation refused")
    if state["duplicate"]:
        raise SettlementError(
            f"assignment {assignment_id} already has an evaluator receipt")


def _bind_state_dsn(dsn: str, assignment_id: str, evaluator_id: str,
                    invocation_ref: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM trial_assignments WHERE id = %s",
                        (assignment_id,))
            row = cur.fetchone()
            assignment = dict(row) if row else None
            digests: list[str] = []
            clash = None
            has_receipt = False
            pin = ""
            if assignment is not None:
                cur.execute("SELECT content FROM candidate_submissions"
                            " WHERE assignment_id = %s ORDER BY id",
                            (assignment_id,))
                digests = [payload_digest(dict(r["content"] or {}))
                           for r in cur.fetchall()]
                cur.execute("SELECT id FROM trial_assignments"
                            " WHERE protocol_id = %s AND evaluation_op = %s"
                            " AND id <> %s",
                            (assignment["protocol_id"], invocation_ref,
                             assignment_id))
                hit = cur.fetchone()
                clash = hit["id"] if hit else None
                if clash is None:
                    cur.execute("SELECT r.assignment_id FROM evaluator_receipts r"
                                " JOIN trial_assignments a ON a.id = r.assignment_id"
                                " WHERE r.invocation_ref = %s AND a.protocol_id = %s",
                                (invocation_ref, assignment["protocol_id"]))
                    hit = cur.fetchone()
                    clash = hit["assignment_id"] if hit else None
                cur.execute("SELECT 1 FROM evaluator_receipts WHERE assignment_id = %s",
                            (assignment_id,))
                has_receipt = cur.fetchone() is not None
                cur.execute("SELECT evaluator_version FROM trial_protocols WHERE id = %s",
                            (assignment["protocol_id"],))
                prow = cur.fetchone()
                pin = (prow["evaluator_version"] or "") if prow else ""
            conn.commit()
    op = broker.read_operation(dsn, invocation_ref)
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM evaluator_packages WHERE id = %s",
                        (evaluator_id,))
            prow = cur.fetchone()
            package = dict(prow) if prow else None
            conn.commit()
    protocol = trials._protocol(dsn, assignment["protocol_id"]) \
        if assignment is not None else None
    if protocol is not None:
        pin = protocol["evaluator_version"] or ""
    return _bind_state(assignment, digests, clash, has_receipt, op, pin, package)


def _bind_state_cur(cur, assignment_id: str, evaluator_id: str,
                    invocation_ref: str) -> dict:
    cur.execute("SELECT * FROM trial_assignments WHERE id = %s", (assignment_id,))
    row = cur.fetchone()
    assignment = dict(row) if row else None
    digests: list[str] = []
    clash = None
    has_receipt = False
    pin = ""
    package = None
    if assignment is not None:
        cur.execute("SELECT content FROM candidate_submissions"
                    " WHERE assignment_id = %s ORDER BY id", (assignment_id,))
        digests = [payload_digest(dict(r["content"] or {})) for r in cur.fetchall()]
        cur.execute("SELECT id FROM trial_assignments"
                    " WHERE protocol_id = %s AND evaluation_op = %s AND id <> %s",
                    (assignment["protocol_id"], invocation_ref, assignment_id))
        hit = cur.fetchone()
        clash = hit["id"] if hit else None
        if clash is None:
            cur.execute("SELECT r.assignment_id FROM evaluator_receipts r"
                        " JOIN trial_assignments a ON a.id = r.assignment_id"
                        " WHERE r.invocation_ref = %s AND a.protocol_id = %s",
                        (invocation_ref, assignment["protocol_id"]))
            hit = cur.fetchone()
            clash = hit["assignment_id"] if hit else None
        cur.execute("SELECT 1 FROM evaluator_receipts WHERE assignment_id = %s",
                    (assignment_id,))
        has_receipt = cur.fetchone() is not None
        cur.execute("SELECT evaluator_version FROM trial_protocols WHERE id = %s",
                    (assignment["protocol_id"],))
        prow = cur.fetchone()
        pin = (prow["evaluator_version"] or "") if prow else ""
        cur.execute("SELECT * FROM evaluator_packages WHERE id = %s",
                    (evaluator_id,))
        prow = cur.fetchone()
        package = dict(prow) if prow else None
    cur.execute("SELECT * FROM operations WHERE id = %s", (invocation_ref,))
    orow = cur.fetchone()
    op = None
    if orow is not None:
        op = {"dispatch_state": orow["dispatch_state"],
              "payload": dict(orow["payload"] or {})}
    return _bind_state(assignment, digests, clash, has_receipt, op, pin, package)


def _receipt_state_dsn(dsn: str, assignment_id: str, evaluator_id: str,
                       invocation_ref: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM trial_assignments WHERE id = %s",
                        (assignment_id,))
            row = cur.fetchone()
            assignment = dict(row) if row else None
            digests: list[str] = []
            clash = None
            duplicate = False
            pin = ""
            package = None
            if assignment is not None:
                cur.execute("SELECT content FROM candidate_submissions"
                            " WHERE assignment_id = %s ORDER BY id",
                            (assignment_id,))
                digests = [payload_digest(dict(r["content"] or {}))
                           for r in cur.fetchall()]
                cur.execute("SELECT r.assignment_id FROM evaluator_receipts r"
                            " JOIN trial_assignments a ON a.id = r.assignment_id"
                            " WHERE r.invocation_ref = %s AND a.protocol_id = %s"
                            " AND r.assignment_id <> %s",
                            (invocation_ref, assignment["protocol_id"],
                             assignment_id))
                hit = cur.fetchone()
                clash = hit["assignment_id"] if hit else None
                cur.execute("SELECT 1 FROM evaluator_receipts WHERE assignment_id = %s",
                            (assignment_id,))
                duplicate = cur.fetchone() is not None
                cur.execute("SELECT evaluator_version FROM trial_protocols WHERE id = %s",
                            (assignment["protocol_id"],))
                prow = cur.fetchone()
                pin = (prow["evaluator_version"] or "") if prow else ""
                cur.execute("SELECT * FROM evaluator_packages WHERE id = %s",
                            (evaluator_id,))
                prow = cur.fetchone()
                package = dict(prow) if prow else None
            cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s"
                        " ORDER BY created_at", (invocation_ref,))
            broker_rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    op = broker.read_operation(dsn, invocation_ref)
    protocol = trials._protocol(dsn, assignment["protocol_id"]) \
        if assignment is not None else None
    if protocol is not None:
        pin = protocol["evaluator_version"] or ""
    return _receipt_state(assignment, digests, clash, duplicate, op, broker_rows,
                          pin, package)


def _receipt_state_cur(cur, assignment_id: str, evaluator_id: str,
                       invocation_ref: str) -> dict:
    cur.execute("SELECT * FROM trial_assignments WHERE id = %s", (assignment_id,))
    row = cur.fetchone()
    assignment = dict(row) if row else None
    digests: list[str] = []
    clash = None
    duplicate = False
    pin = ""
    package = None
    if assignment is not None:
        cur.execute("SELECT content FROM candidate_submissions"
                    " WHERE assignment_id = %s ORDER BY id", (assignment_id,))
        digests = [payload_digest(dict(r["content"] or {})) for r in cur.fetchall()]
        cur.execute("SELECT r.assignment_id FROM evaluator_receipts r"
                    " JOIN trial_assignments a ON a.id = r.assignment_id"
                    " WHERE r.invocation_ref = %s AND a.protocol_id = %s"
                    " AND r.assignment_id <> %s",
                    (invocation_ref, assignment["protocol_id"], assignment_id))
        hit = cur.fetchone()
        clash = hit["assignment_id"] if hit else None
        cur.execute("SELECT 1 FROM evaluator_receipts WHERE assignment_id = %s",
                    (assignment_id,))
        duplicate = cur.fetchone() is not None
        cur.execute("SELECT evaluator_version FROM trial_protocols WHERE id = %s",
                    (assignment["protocol_id"],))
        prow = cur.fetchone()
        pin = (prow["evaluator_version"] or "") if prow else ""
        cur.execute("SELECT * FROM evaluator_packages WHERE id = %s",
                    (evaluator_id,))
        prow = cur.fetchone()
        package = dict(prow) if prow else None
    cur.execute("SELECT dispatch_state, payload FROM operations WHERE id = %s",
                (invocation_ref,))
    orow = cur.fetchone()
    op = None
    if orow is not None:
        op = {"dispatch_state": orow["dispatch_state"],
              "payload": dict(orow["payload"] or {})}
    cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s"
                " ORDER BY created_at", (invocation_ref,))
    broker_rows = [dict(r) for r in cur.fetchall()]
    return _receipt_state(assignment, digests, clash, duplicate, op, broker_rows,
                          pin, package)


def _receipt_binding(dsn: str, *, assignment_id: str, evaluator_id: str,
                     evaluator_version: str, invocation_ref: str,
                     result: dict) -> None:
    _verify_receipt(_receipt_state_dsn(dsn, assignment_id, evaluator_id,
                                       invocation_ref),
                    assignment_id=assignment_id, evaluator_id=evaluator_id,
                    evaluator_version=evaluator_version,
                    invocation_ref=invocation_ref, result=result)


def _binding_inside(cur, *, assignment_id: str, evaluator_id: str,
                    evaluator_version: str, invocation_ref: str,
                    result: dict) -> None:
    _verify_receipt(_receipt_state_cur(cur, assignment_id, evaluator_id,
                                       invocation_ref),
                    assignment_id=assignment_id, evaluator_id=evaluator_id,
                    evaluator_version=evaluator_version,
                    invocation_ref=invocation_ref, result=result)


def bind_evaluation(dsn: str, cmd: Command, assignment_id: str, *,
                    candidate_digest: str, evaluator_id: str,
                    evaluator_version: str, invocation_ref: str,
                    executable_digest: str = "",
                    input_digest: str = "") -> CommandResult:
    if not candidate_digest or not evaluator_id or not evaluator_version \
            or not invocation_ref:
        raise SettlementError(
            "evaluation binding needs candidate digest, evaluator id/version"
            " and invocation ref")
    state = _bind_state_dsn(dsn, assignment_id, evaluator_id, invocation_ref)
    identical = _verify_bind(
        state, assignment_id=assignment_id, candidate_digest=candidate_digest,
        evaluator_id=evaluator_id, evaluator_version=evaluator_version,
        invocation_ref=invocation_ref, executable_digest=executable_digest,
        input_digest=input_digest)
    if identical:
        return CommandResult(code=ResultCode.ALREADY_APPLIED,
                             request_id=cmd.request_id,
                             detail=f"evaluation binding already established"
                             f" for {assignment_id}",
                             data={"assignment_id": assignment_id,
                                   "invocation_ref": invocation_ref})

    def _fn(cur, control):
        same = _verify_bind(
            _bind_state_cur(cur, assignment_id, evaluator_id, invocation_ref),
            assignment_id=assignment_id, candidate_digest=candidate_digest,
            evaluator_id=evaluator_id, evaluator_version=evaluator_version,
            invocation_ref=invocation_ref, executable_digest=executable_digest,
            input_digest=input_digest)
        if same:
            return (ResultCode.ALREADY_APPLIED,
                    f"evaluation binding already established for {assignment_id}",
                    {"assignment_id": assignment_id,
                     "invocation_ref": invocation_ref}, [], [])
        cur.execute("UPDATE trial_assignments SET candidate_digest = %s,"
                    " evaluator_id = %s, evaluator_version = %s, evaluation_op = %s"
                    " WHERE id = %s",
                    (candidate_digest, evaluator_id, evaluator_version,
                     invocation_ref, assignment_id))
        if executable_digest or input_digest:
            cur.execute("UPDATE trial_assignments SET instance ="
                        " COALESCE(instance, '{}'::jsonb) || %s::jsonb"
                        " WHERE id = %s",
                        (_j({"evaluation_binding":
                             {"executable_digest": executable_digest,
                              "input_digest": input_digest}}),
                         assignment_id))
        return (ResultCode.APPLIED, f"evaluation binding recorded for {assignment_id}",
                {"assignment_id": assignment_id, "invocation_ref": invocation_ref},
                [("evaluation.binding_recorded", {"assignment_id": assignment_id})],
                [])
    return store.transact(dsn, cmd, _fn)


def submit_evaluator_receipt(dsn: str, cmd: Command, *, receipt_id: str,
                             assignment_id: str, evaluator_id: str,
                             evaluator_version: str, invocation_ref: str,
                             result: dict) -> CommandResult:
    outcome = result.get("outcome")
    if outcome not in trials.OUTCOMES:
        raise SettlementError(f"receipt needs an outcome in {trials.OUTCOMES}")
    _receipt_binding(dsn, assignment_id=assignment_id, evaluator_id=evaluator_id,
                     evaluator_version=evaluator_version,
                     invocation_ref=invocation_ref, result=result)

    def _fn(cur, control):
        _binding_inside(cur, assignment_id=assignment_id, evaluator_id=evaluator_id,
                        evaluator_version=evaluator_version,
                        invocation_ref=invocation_ref, result=result)
        cur.execute("INSERT INTO evaluator_receipts (id, assignment_id, evaluator_id,"
                    " evaluator_version, invocation_ref, result)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (receipt_id, assignment_id, evaluator_id, evaluator_version,
                     invocation_ref, _j(result)))
        cur.execute("INSERT INTO trial_results (assignment_id, outcome, invocation_ref,"
                    " conditions, cost, detail) VALUES (%s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (assignment_id) DO NOTHING",
                    (assignment_id, outcome, invocation_ref,
                     _j(result.get("conditions", {})), _j(result.get("cost", {})),
                     _j(result.get("detail", {}))))
        return (ResultCode.APPLIED, f"evaluator receipt {receipt_id} admitted",
                {"receipt_id": receipt_id, "assignment_id": assignment_id,
                 "outcome": outcome},
                [("evaluation.receipt_admitted", {"receipt_id": receipt_id})], [])
    return store.transact(dsn, cmd, _fn)
