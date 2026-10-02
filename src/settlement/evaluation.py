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
from .common import Command, CommandResult, ResultCode, SettlementError, Unauthorized

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
        return (ResultCode.APPLIED, f"evaluator {evaluator_id} v{version} registered",
                {"evaluator_id": evaluator_id, "version": version},
                [("evaluation.evaluator_registered", {"evaluator_id": evaluator_id})], [])
    return store.transact(dsn, cmd, _fn)


def _package(dsn: str, evaluator_id: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM evaluator_packages WHERE id = %s", (evaluator_id,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"unknown evaluator {evaluator_id}")
    return dict(row)


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
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM trial_assignments WHERE id = %s", (assignment_id,))
            if cur.fetchone() is None:
                raise SettlementError(f"unknown assignment {assignment_id}")
            conn.commit()

    def _fn(cur, control):
        cur.execute("INSERT INTO candidate_submissions (assignment_id, content)"
                    " VALUES (%s, %s)", (assignment_id, _j(content)))
        return (ResultCode.APPLIED, f"candidate submission recorded for {assignment_id}",
                {"assignment_id": assignment_id},
                [("evaluation.candidate_submitted", {"assignment_id": assignment_id})], [])
    return store.transact(dsn, cmd, _fn)


def _invocation_observed(dsn: str, invocation_ref: str) -> None:
    row = broker.read_operation(dsn, invocation_ref)
    if row is None:
        raise SettlementError(f"receipt references no actual invocation {invocation_ref}")
    if row["dispatch_state"] not in ("observed", "reconciled"):
        raise SettlementError(
            f"invocation {invocation_ref} has no observed receipt")


def submit_evaluator_receipt(dsn: str, cmd: Command, *, receipt_id: str,
                             assignment_id: str, evaluator_id: str,
                             evaluator_version: str, invocation_ref: str,
                             result: dict) -> CommandResult:
    package = _package(dsn, evaluator_id)
    if package["version"] != evaluator_version:
        raise SettlementError(
            f"evaluator {evaluator_id} is {package['version']!r},"
            f" receipt claims {evaluator_version!r}")
    outcome = result.get("outcome")
    if outcome not in trials.OUTCOMES:
        raise SettlementError(f"receipt needs an outcome in {trials.OUTCOMES}")
    _invocation_observed(dsn, invocation_ref)
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT protocol_id FROM trial_assignments WHERE id = %s",
                        (assignment_id,))
            assignment = cur.fetchone()
            conn.commit()
    if assignment is None:
        raise SettlementError(f"unknown assignment {assignment_id}")
    protocol = trials._protocol(dsn, assignment["protocol_id"])
    if (protocol["evaluator_version"] or "") != evaluator_version:
        raise SettlementError(
            f"version pin mismatch: protocol {protocol['id']} pins evaluator"
            f" {protocol['evaluator_version']!r}, receipt uses {evaluator_version!r}")

    def _fn(cur, control):
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
