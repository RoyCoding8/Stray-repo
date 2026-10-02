"""S3 trials (LEARN-2/3/4/5/6): frozen protocols, blinded assignments,
invocation-bound results, expenditure ledger, finite-panel verdicts.

Any inferential claim path refuses: no validated LEARN-6 procedure exists,
so the gate is recorded as unverified and the claim is never made.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import broker, db, store
from .common import Command, CommandResult, ResultCode, SettlementError

OUTCOMES = ("success", "failure", "timeout", "invalid", "unavailable", "infra")
CATEGORIES = ("construction", "retrieval", "evaluation", "coordination",
              "selection", "failed_trials", "use")
GROUP_KINDS = ("development", "visible-regression", "protected-eval")


class UnverifiedProcedure(SettlementError):
    code = ResultCode.MISSING_EVIDENCE


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def freeze_protocol(dsn: str, cmd: Command, *, protocol_id: str,
                    candidate_version: str = "", reference_version: str = "",
                    evaluator_version: str = "", task_groups: list | None = None,
                    budgets: dict | None = None, metrics: list | None = None,
                    stopping: dict | None = None, exclusions: list | None = None,
                    uncertainty: dict | None = None,
                    supported_scope: dict | None = None,
                    _frozen: bool = True) -> CommandResult:
    groups = list(task_groups or [])
    kinds = {g.get("kind") for g in groups if isinstance(g, dict)}
    if not groups or kinds - set(GROUP_KINDS) or "protected-eval" not in kinds:
        raise SettlementError(
            "protocol needs separated dev/visible-regression/protected-eval groups")

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM trial_protocols WHERE id = %s", (protocol_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"protocol {protocol_id} already exists")
        cur.execute(
            "INSERT INTO trial_protocols (id, candidate_version, reference_version,"
            " evaluator_version, task_groups, budgets, metrics, stopping, exclusions,"
            " uncertainty, supported_scope, frozen)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (protocol_id, candidate_version, reference_version, evaluator_version,
             _j(groups), _j(budgets or {}), _j(metrics or []), _j(stopping or {}),
             _j(exclusions or []), _j(uncertainty or {}),
             _j(supported_scope or {}), _frozen))
        return (ResultCode.APPLIED, f"protocol {protocol_id} frozen",
                {"protocol_id": protocol_id},
                [("trial.protocol_frozen", {"protocol_id": protocol_id})], [])
    return store.transact(dsn, cmd, _fn)


def amend_protocol(dsn: str, cmd: Command, *, protocol_id: str,
                   supersedes: str, **fields: Any) -> CommandResult:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM trial_protocols WHERE id = %s", (supersedes,))
            old = cur.fetchone()
            conn.commit()
    if old is None:
        raise SettlementError(f"unknown protocol {supersedes}")
    base = {key: old[key] for key in
            ("candidate_version", "reference_version", "evaluator_version")}
    base.update({k: v for k, v in fields.items() if k in base})
    groups = fields.get("task_groups", list(old["task_groups"] or []))
    supported_scope = fields.get("supported_scope",
                                 dict(old.get("supported_scope") or {}))
    budgets = fields.get("budgets", dict(old["budgets"] or {}))
    metrics = fields.get("metrics", list(old["metrics"] or []))
    stopping = fields.get("stopping", dict(old["stopping"] or {}))
    exclusions = fields.get("exclusions", list(old["exclusions"] or []))
    uncertainty = fields.get("uncertainty", dict(old["uncertainty"] or {}))
    result = freeze_protocol(
        dsn, cmd, protocol_id=protocol_id, task_groups=groups, budgets=budgets,
        metrics=metrics, stopping=stopping, exclusions=exclusions,
        uncertainty=uncertainty, supported_scope=supported_scope,
        _frozen=False, **base)
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE trial_protocols SET supersedes = %s, frozen = TRUE"
                        " WHERE id = %s", (supersedes, protocol_id))
    return result


def _protocol(dsn: str, protocol_id: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM trial_protocols WHERE id = %s", (protocol_id,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"unknown protocol {protocol_id}")
    return dict(row)


def _group_names(protocol: dict) -> set[str]:
    return {g.get("name", "") for g in (protocol["task_groups"] or []) if isinstance(g, dict)}


def assign(dsn: str, cmd: Command, protocol_id: str, task_id: str, task_group: str,
           arm: str, instance: dict | None = None) -> CommandResult:
    from .common import new_id  # noqa: PLC0415

    if arm not in ("candidate", "reference"):
        raise SettlementError(f"unknown arm {arm!r}")
    protocol = _protocol(dsn, protocol_id)
    if not protocol.get("frozen"):
        raise SettlementError(f"protocol {protocol_id} is not frozen: assignments refused")
    if task_group not in _group_names(protocol):
        raise SettlementError(f"task group {task_group!r} not in protocol {protocol_id}")
    blind_key = new_id("blind")
    assignment_id = f"{protocol_id}:{arm}:{task_id}"

    def _fn(cur, control):
        cur.execute("SELECT blind_key FROM trial_assignments WHERE id = %s",
                    (assignment_id,))
        prior = cur.fetchone()
        if prior is not None:
            return (ResultCode.ALREADY_APPLIED,
                    f"assignment {assignment_id} already exists",
                    {"assignment_id": assignment_id,
                     "blind_key": prior["blind_key"]}, [], [])
        cur.execute("INSERT INTO trial_assignments (id, protocol_id, task_id, task_group,"
                    " arm, blind_key, instance) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (assignment_id, protocol_id, task_id, task_group, arm,
                     blind_key, _j(instance or {})))
        return (ResultCode.APPLIED, f"assigned {task_id} to {arm}",
                {"assignment_id": assignment_id, "blind_key": blind_key},
                [("trial.assigned", {"assignment_id": assignment_id})], [])
    return store.transact(dsn, cmd, _fn)


def blinded_assignment(dsn: str, blind_key: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT task_id, task_group, instance FROM trial_assignments"
                        " WHERE blind_key = %s", (blind_key,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"unknown blind key {blind_key}")
    return {"task_id": row["task_id"], "task_group": row["task_group"],
            "instance": dict(row["instance"] or {})}


def resolve_blind(dsn: str, blind_key: str) -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, arm, protocol_id FROM trial_assignments"
                        " WHERE blind_key = %s", (blind_key,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"unknown blind key {blind_key}")
    return dict(row)


def record_result(dsn: str, cmd: Command, *, assignment_id: str, outcome: str,
                  invocation_ref: str = "", conditions: dict | None = None,
                  cost: dict | None = None, detail: dict | None = None) -> CommandResult:
    if outcome not in OUTCOMES:
        raise SettlementError(f"unknown outcome {outcome!r}")
    if invocation_ref and broker.read_operation(dsn, invocation_ref) is None:
        raise SettlementError(f"result references no actual invocation {invocation_ref}")
    stamped = dict(detail or {})
    stamped.setdefault("origin", "direct-caller-outcome")

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM trial_assignments WHERE id = %s", (assignment_id,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown assignment {assignment_id}")
        cur.execute("INSERT INTO trial_results (assignment_id, outcome, invocation_ref,"
                    " conditions, cost, detail) VALUES (%s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (assignment_id) DO NOTHING",
                    (assignment_id, outcome, invocation_ref, _j(conditions or {}),
                     _j(cost or {}), _j(stamped)))
        if cur.rowcount == 0:
            cur.execute("SELECT outcome FROM trial_results WHERE assignment_id = %s",
                        (assignment_id,))
            prior = cur.fetchone()["outcome"]
            return (ResultCode.ALREADY_APPLIED, f"result already recorded: {prior}",
                    {"assignment_id": assignment_id, "outcome": prior}, [], [])
        return (ResultCode.APPLIED, f"outcome {outcome} recorded for {assignment_id}",
                {"assignment_id": assignment_id, "outcome": outcome},
                [("trial.result_recorded", {"assignment_id": assignment_id})], [])
    return store.transact(dsn, cmd, _fn)


def record_expenditure(dsn: str, protocol_id: str, category: str,
                       amount: int, note: str = "") -> dict:
    if category not in CATEGORIES:
        raise SettlementError(f"unknown expenditure category {category!r}")
    if int(amount) < 0:
        raise SettlementError("expenditure must be a non-negative integer")
    _protocol(dsn, protocol_id)
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO expenditure_ledger (protocol_id, category, amount, note)"
                        " VALUES (%s, %s, %s, %s)", (protocol_id, category, int(amount), note))
    return {"protocol_id": protocol_id, "category": category, "amount": int(amount)}


def development_expenditure(dsn: str, protocol_id: str) -> dict:
    protocol = _protocol(dsn, protocol_id)
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT category, COALESCE(SUM(amount), 0) AS total"
                        " FROM expenditure_ledger WHERE protocol_id = %s GROUP BY category",
                        (protocol_id,))
            by_category = {r["category"]: int(r["total"]) for r in cur.fetchall()}
            conn.commit()
    by_category = {cat: by_category.get(cat, 0) for cat in CATEGORIES}
    development = sum(v for k, v in by_category.items() if k != "use")
    return {"protocol_id": protocol_id, "by_category": by_category,
            "development_total": development, "use_total": by_category["use"],
            "grand_total": development + by_category["use"],
            "amortization_horizon": dict(protocol["budgets"] or {}).get(
                "amortization_horizon")}


def protocol_results(dsn: str, protocol_id: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT a.id, a.task_id, a.task_group, a.arm,"
                        " r.outcome, r.invocation_ref, r.conditions, r.cost, r.detail"
                        " FROM trial_assignments a LEFT JOIN trial_results r"
                        " ON r.assignment_id = a.id WHERE a.protocol_id = %s ORDER BY a.id",
                        (protocol_id,))
            rows = [{**dict(r), "conditions": dict(r["conditions"] or {}),
                     "cost": dict(r["cost"] or {}),
                     "detail": dict(r["detail"] or {})} for r in cur.fetchall()]
            conn.commit()
    return rows


def verdict(dsn: str, protocol_id: str) -> dict:
    rows = protocol_results(dsn, protocol_id)
    missing = [r["id"] for r in rows if r["outcome"] is None]
    if missing:
        raise SettlementError(f"protocol {protocol_id} has {len(missing)}"
                              f" assigned cases without outcomes")
    groups: dict[str, dict[str, int]] = {}
    for row in rows:
        cell = groups.setdefault(row["task_group"], {"candidate": 0, "reference": 0})
        if row["outcome"] == "success":
            cell[row["arm"]] += 1
    cand = sum(cell["candidate"] for cell in groups.values())
    ref = sum(cell["reference"] for cell in groups.values())
    regressed = sorted(name for name, cell in groups.items()
                       if cell["candidate"] < cell["reference"])
    label = ("observed-gain" if cand > ref and not regressed else
             "regression" if ref > cand else "inconclusive")
    return {"protocol_id": protocol_id, "label": label,
            "candidate_successes": cand, "reference_successes": ref,
            "groups": groups, "regressed_groups": regressed}


def register_opportunity(dsn: str, cmd: Command, *, opportunity_id: str,
                         question: str = "", hypothesis: str = "", basis: str = "",
                         desired_observation: str = "",
                         cap: dict | None = None) -> CommandResult:
    if not opportunity_id or not question:
        raise SettlementError("an opportunity needs an id and a question")

    def _fn(cur, control):
        cur.execute("INSERT INTO development_opportunities (id, question, hypothesis,"
                    " basis, desired_observation, cap)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (opportunity_id, question, hypothesis, basis,
                     desired_observation, _j(cap or {})))
        return (ResultCode.APPLIED, f"opportunity {opportunity_id} registered",
                {"opportunity_id": opportunity_id},
                [("development.opportunity_registered",
                  {"opportunity_id": opportunity_id})], [])
    return store.transact(dsn, cmd, _fn)


def allocate_opportunity(dsn: str, cmd: Command, opportunity_id: str,
                         investigation_id: str, objective: str = "",
                         scope: dict | None = None,
                         obligations: dict | None = None) -> CommandResult:
    from .store import admit_commitment  # noqa: PLC0415

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT status FROM development_opportunities WHERE id = %s",
                        (opportunity_id,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        raise SettlementError(f"unknown opportunity {opportunity_id}")
    if row["status"] != "proposed":
        raise SettlementError(f"opportunity {opportunity_id} is {row['status']}")
    sub = Command(request_id=f"{cmd.request_id}:investigation",
                  payload={"investigation_id": investigation_id,
                           "objective": objective or opportunity_id,
                           "scope": scope or {}, "obligations": obligations or {}})
    admitted = admit_commitment(dsn, sub)
    if admitted.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"distinguishing investigation refused: {admitted.detail}")

    def _fn(cur, control):
        cur.execute("UPDATE development_opportunities SET status = 'allocated',"
                    " investigation_id = %s WHERE id = %s",
                    (investigation_id, opportunity_id))
        return (ResultCode.APPLIED,
                f"opportunity {opportunity_id} allocated to {investigation_id}",
                {"opportunity_id": opportunity_id,
                 "investigation_id": investigation_id},
                [("development.opportunity_allocated",
                  {"opportunity_id": opportunity_id})], [])
    return store.transact(dsn, cmd, _fn)


def inferential_claim(dsn: str, protocol_id: str, procedure: str) -> dict:
    _protocol(dsn, protocol_id)
    reason = ("no validated LEARN-6 procedure exists: estimand, grouping, stopping rule,"
              " error budget and calibration against simulated nulls are all unvalidated")
    with db.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO inferential_gates (protocol_id, requested_procedure,"
                        " status, reason) VALUES (%s, %s, 'unverified', %s)"
                        " ON CONFLICT (protocol_id) DO UPDATE SET requested_procedure ="
                        " EXCLUDED.requested_procedure, status = 'unverified',"
                        " reason = EXCLUDED.reason",
                        (protocol_id, procedure, reason))
    raise UnverifiedProcedure(f"inferential claim refused for {protocol_id}: {reason}")
