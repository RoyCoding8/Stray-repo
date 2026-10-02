"""Shared EC02 trial/record schema, cost-union reconciliation, freeze assembly.

Owned by lane E. Both L-construction output and E-evidence consume the
trial record defined here. Identity vocabulary (panels, arms, repeats)
and freeze/checker mechanics are reused from lane W; nothing here
duplicates them. Unknown measurement stays unknown, never zero.
"""

from __future__ import annotations

from typing import Any

from settlement import broker, db
from settlement.representation import canonical_bytes, sha_hex

from . import freeze as freeze_mod

TRIAL_VERSION = "coord02-trial/1"

ARMS = freeze_mod.ARMS
PANELS = freeze_mod.PANELS
REPEATS = tuple(freeze_mod.REPEATS)

OUTCOMES = ("success", "failure", "refusal", "timeout", "incomplete")

EXECUTED_TREATMENTS = ("S", "A", "F", "L", "L-acquired", "S-fallback")

OP_KINDS = ("build", "validation", "episode", "failed", "cancelled",
            "policy_step", "construction", "a_interpretation",
            "child_inference", "check", "probe")

KIND_EFFECTS = {"build": broker.SANDBOX_EXEC,
                "validation": broker.SANDBOX_EXEC,
                "episode": broker.SANDBOX_EXEC,
                "failed": broker.SANDBOX_EXEC,
                "cancelled": broker.SANDBOX_EXEC,
                "policy_step": broker.SANDBOX_EXEC,
                "construction": broker.MODEL_INFERENCE,
                "a_interpretation": broker.MODEL_INFERENCE,
                "child_inference": broker.MODEL_INFERENCE,
                "check": broker.SANDBOX_EXEC,
                "probe": broker.OBSERVATION_ADAPTER}

USAGE_FIELDS = ("input_tokens", "output_tokens", "model_calls")

TOKEN_MAP = {"model_tokens_in": "input_tokens",
             "model_tokens_out": "output_tokens",
             "model_calls": "model_calls"}

SETTLEMENTS = ("observed", "cancelled", "refused", "unresolved")

UNKNOWN = "unknown"

COST_FIELDS = ("model_tokens_in", "model_tokens_out", "model_calls",
               "tool_invocations", "sandbox_ops", "policy_exec_ops",
               "protected_check_ops", "cpu_seconds", "wall_seconds",
               "elapsed_seconds", "abandoned_ops")

NULLABLE_COSTS = ("cpu_seconds", "wall_seconds", "elapsed_seconds")

MANDATORY_RESOURCES = ("model_tokens", "tool_invocations", "sandbox_ops")

RATIO_NUM = 5
RATIO_DEN = 4


class TrialError(ValueError):
    pass


def _req_nonneg(values: dict, key: str) -> Any:
    value = values.get(key, None)
    if value == UNKNOWN and key in TOKEN_MAP:
        return UNKNOWN
    if value is None and key in NULLABLE_COSTS:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrialError("trial cost %r must be a number" % key)
    if value < 0:
        raise TrialError("trial cost %r must be non-negative" % key)
    return value


def _check_billing(billing: Any) -> dict:
    if not isinstance(billing, dict):
        raise TrialError("external_billing must be an object")
    for key in ("model", "infra"):
        value = billing.get(key, UNKNOWN)
        if value == UNKNOWN:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or value < 0:
            raise TrialError("external_billing %r is a number or 'unknown'"
                             % key)
    return {"model": billing.get("model", UNKNOWN),
            "infra": billing.get("infra", UNKNOWN)}


def _check_internal(accounting: Any) -> dict:
    if not isinstance(accounting, dict):
        raise TrialError("internal_accounting must be an object")
    for key, value in accounting.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or value < 0:
            raise TrialError("internal_accounting %r must be non-negative"
                             % key)
    return dict(accounting)


def _check_operations(operations: Any) -> list:
    if not isinstance(operations, list):
        raise TrialError("operations must be a list")
    seen = set()
    cleaned = []
    for entry in operations:
        if not isinstance(entry, dict):
            raise TrialError("operations entries must be objects")
        op_id = entry.get("operation_id")
        kind = entry.get("kind")
        if not isinstance(op_id, str) or not op_id:
            raise TrialError("operations need a non-empty operation_id")
        if kind not in OP_KINDS:
            raise TrialError("operation kind %r is not one of %r"
                             % (kind, OP_KINDS))
        if op_id in seen:
            raise TrialError("duplicate operation_id %r in one record"
                             % op_id)
        seen.add(op_id)
        cleaned.append({"operation_id": op_id, "kind": kind})
    return cleaned


def _check_liabilities(liabilities: Any) -> list:
    if not isinstance(liabilities, list):
        raise TrialError("liabilities must be a list")
    cleaned = []
    for entry in liabilities:
        if not isinstance(entry, dict):
            raise TrialError("liabilities entries must be objects")
        party = entry.get("party")
        reason = entry.get("reason")
        if not isinstance(party, str) or not party:
            raise TrialError("liabilities need a party")
        if not isinstance(reason, str) or not reason:
            raise TrialError("liabilities need a reason")
        item: dict = {"party": party, "reason": reason}
        if "operation" in entry:
            if not isinstance(entry["operation"], str):
                raise TrialError("liability operation must be a string")
            item["operation"] = entry["operation"]
        cleaned.append(item)
    return cleaned


def _check_provenance(executed_treatment: Any,
                       fallback_reason: Any) -> tuple:
    if executed_treatment not in EXECUTED_TREATMENTS:
        raise TrialError("executed treatment %r is not one of %r"
                         % (executed_treatment, EXECUTED_TREATMENTS))
    if fallback_reason is not None and (
            not isinstance(fallback_reason, str) or not fallback_reason):
        raise TrialError("fallback reason is null or a non-empty string")
    if executed_treatment == "S-fallback" and fallback_reason is None:
        raise TrialError("S-fallback execution needs its fallback reason")
    if executed_treatment != "S-fallback" and fallback_reason is not None:
        raise TrialError("only S-fallback execution carries a "
                         "fallback reason")
    return executed_treatment, fallback_reason


def build_trial_record(*, freeze_id: str, panel: str, task_id: str,
                       repeat: int, arm: str, source_sha: str,
                       config_digest: str, package_digest: str,
                       outcome: str, solved: bool,
                       protected: dict, failures: list,
                       costs: dict, receipts: list,
                       operations: list | None = None,
                       liabilities: list | None = None,
                       internal_accounting: dict | None = None,
                       external_billing: dict | None = None,
                       executed_treatment: str | None = None,
                       fallback_reason: str | None = None) -> dict:
    if panel not in PANELS:
        raise TrialError("panel %r is not one of %r" % (panel, PANELS))
    if arm not in ARMS:
        raise TrialError("arm %r is not one of %r" % (arm, ARMS))
    if repeat not in REPEATS:
        raise TrialError("repeat %r is not one of %r" % (repeat, REPEATS))
    if outcome not in OUTCOMES:
        raise TrialError("outcome %r is not one of %r" % (outcome, OUTCOMES))
    if not isinstance(task_id, str) or not task_id:
        raise TrialError("trial record needs a non-empty task_id")
    if not isinstance(freeze_id, str) or not freeze_id:
        raise TrialError("trial record needs a non-empty freeze_id")
    if not isinstance(solved, bool):
        raise TrialError("solved must be a bool")
    if outcome in ("refusal", "timeout", "incomplete") and solved:
        raise TrialError("%s carries zero success by definition" % outcome)
    if outcome == "success" and not solved:
        raise TrialError("success requires solved=true")
    if outcome == "failure" and solved:
        raise TrialError("failure requires solved=false")
    for key in ("source_sha", "config_digest"):
        value = {"source_sha": source_sha,
                 "config_digest": config_digest}[key]
        if not isinstance(value, str) or not value:
            raise TrialError("trial record needs a non-empty %s" % key)
    if not isinstance(package_digest, str) or not package_digest:
        raise TrialError("trial record needs a package_digest ('none' "
                         "when no package is selected)")
    if not isinstance(protected, dict):
        raise TrialError("protected must be an object")
    for key in ("passed", "failed", "total"):
        value = protected.get(key)
        if isinstance(value, bool) or not isinstance(value, int) \
                or value < 0:
            raise TrialError("protected %r must be a non-negative int" % key)
    if protected["passed"] + protected["failed"] != protected["total"]:
        raise TrialError("protected passed+failed must equal total")
    if solved and protected["failed"] != 0:
        raise TrialError("solved requires zero protected failures")
    if not isinstance(failures, list):
        raise TrialError("failures must be a list")
    if not solved and outcome == "failure" and not failures:
        raise TrialError("failure needs at least one quoted failure")
    if not isinstance(costs, dict):
        raise TrialError("costs must be an object")
    clean_costs = {field: _req_nonneg(costs, field)
                   for field in COST_FIELDS}
    if clean_costs["policy_exec_ops"] + clean_costs["protected_check_ops"] \
            > clean_costs["sandbox_ops"]:
        raise TrialError("policy-exec + protected-check ops are a subset "
                         "of sandbox ops")
    if not isinstance(receipts, list) or not receipts \
            or not all(isinstance(r, str) and r for r in receipts):
        raise TrialError("receipts must be a non-empty list of strings")
    if executed_treatment is None:
        executed_treatment = "S-fallback" if arm == "L" and fallback_reason \
            else arm
    treatment, reason = _check_provenance(executed_treatment,
                                          fallback_reason)
    return {"version": TRIAL_VERSION, "freeze_id": freeze_id,
            "panel": panel, "task_id": task_id, "repeat": repeat,
            "arm": arm, "source_sha": source_sha,
            "config_digest": config_digest,
            "package_digest": package_digest, "outcome": outcome,
            "solved": solved,
            "executed_treatment": treatment,
            "fallback_reason": reason,
            "protected": {"passed": protected["passed"],
                          "failed": protected["failed"],
                          "total": protected["total"]},
            "failures": list(failures), "costs": clean_costs,
            "receipts": list(receipts),
            "operations": _check_operations(operations or []),
            "liabilities": _check_liabilities(liabilities or []),
            "internal_accounting": _check_internal(
                internal_accounting or {}),
            "external_billing": _check_billing(external_billing or {})}


def validate_trial_record(record: dict) -> dict:
    if not isinstance(record, dict):
        raise TrialError("trial record must be an object")
    if record.get("version") != TRIAL_VERSION:
        raise TrialError("trial record version must be %r" % TRIAL_VERSION)
    return build_trial_record(
        freeze_id=record.get("freeze_id", ""),
        panel=record.get("panel", ""), task_id=record.get("task_id", ""),
        repeat=record.get("repeat", 0), arm=record.get("arm", ""),
        source_sha=record.get("source_sha", ""),
        config_digest=record.get("config_digest", ""),
        package_digest=record.get("package_digest", ""),
        outcome=record.get("outcome", ""),
        solved=record.get("solved", None),  # type: ignore[arg-type]
        protected=record.get("protected", {}),
        failures=record.get("failures", []),
        costs=record.get("costs", {}),
        receipts=record.get("receipts", []),
        operations=record.get("operations", []),
        liabilities=record.get("liabilities", []),
        internal_accounting=record.get("internal_accounting", {}),
        external_billing=record.get("external_billing", {}),
        executed_treatment=record.get("executed_treatment",
                                      record.get("arm", "")),
        fallback_reason=record.get("fallback_reason", None))


def trial_record_bytes(record: dict) -> bytes:
    return canonical_bytes(validate_trial_record(record))


def to_checker_costs(record: dict) -> dict:
    clean = validate_trial_record(record)
    costs = clean["costs"]
    return {"model_tokens": {"in": costs["model_tokens_in"],
                             "out": costs["model_tokens_out"]},
            "model_calls": costs["model_calls"],
            "tool_invocations": costs["tool_invocations"],
            "sandbox_ops": costs["sandbox_ops"]}


def from_checker_record(w_record: dict, *, source_sha: str,
                        config_digest: str) -> dict:
    costs = w_record.get("costs") or {}
    tokens = costs.get("model_tokens") or {}
    protected = w_record.get("protected") or {}
    solved = w_record.get("outcome") == "success" \
        and protected.get("failed") == 0 \
        and bool(w_record.get("frozen_digest"))
    treatment = w_record.get("executed_treatment")
    if treatment is None:
        treatment = "S-fallback" if w_record.get("fallback_reason") \
            else w_record.get("arm", "")
    return build_trial_record(
        freeze_id=w_record.get("freeze_id", ""),
        panel=w_record.get("panel", ""),
        task_id=w_record.get("task_id", ""),
        repeat=w_record.get("repeat", 0), arm=w_record.get("arm", ""),
        source_sha=source_sha, config_digest=config_digest,
        package_digest=w_record.get("procedure_digest") or "none",
        outcome="success" if solved else "failure", solved=solved,
        executed_treatment=treatment,
        fallback_reason=w_record.get("fallback_reason", None),
        protected={"passed": protected.get("passed", 0),
                   "failed": protected.get("failed", 0),
                   "total": protected.get("total", 0)},
        failures=w_record.get("failures") or [],
        costs={"model_tokens_in": tokens.get("in", 0),
               "model_tokens_out": tokens.get("out", 0),
               "model_calls": costs.get("model_calls", 0),
               "tool_invocations": costs.get("tool_invocations", 0),
               "sandbox_ops": costs.get("sandbox_ops", 0),
               "policy_exec_ops": 0, "protected_check_ops": 0,
               "cpu_seconds": None, "wall_seconds": None,
               "elapsed_seconds": None, "abandoned_ops": 0},
        receipts=w_record.get("receipts") or [],
        external_billing={"model": UNKNOWN, "infra": UNKNOWN})


def _check_usage(usage: Any, operation_id: str) -> dict | None:
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise TrialError("operation %r usage must be an object"
                         % operation_id)
    if set(usage) != set(USAGE_FIELDS):
        raise TrialError("operation %r usage needs exactly %r"
                         % (operation_id, USAGE_FIELDS))
    clean: dict = {}
    for field in USAGE_FIELDS:
        value = usage[field]
        if isinstance(value, bool) or not isinstance(value, int) \
                or value < 0:
            raise TrialError("operation %r usage %r must be a "
                             "non-negative int" % (operation_id, field))
        clean[field] = value
    return clean


def _check_settlement(settlement: Any, refusal: Any,
                      operation_id: str) -> tuple:
    if settlement not in SETTLEMENTS:
        raise TrialError("operation %r settlement %r is not one of %r"
                         % (operation_id, settlement, SETTLEMENTS))
    if settlement == "unresolved":
        if refusal is not None:
            raise TrialError("operation %r unresolved carries no refusal"
                             % operation_id)
        return settlement, None
    if refusal is not None and not isinstance(refusal, dict):
        raise TrialError("operation %r refusal must be an object"
                         % operation_id)
    if settlement in ("cancelled", "refused") and refusal is None:
        raise TrialError("operation %r %s needs its refusal"
                         % (operation_id, settlement))
    return settlement, None if refusal is None else dict(refusal)


def _check_liability_entry(entry: Any, operation_id: str) -> dict:
    if not isinstance(entry, dict):
        raise TrialError("operation %r liability must be an object"
                         % operation_id)
    party = entry.get("party")
    reason = entry.get("reason")
    if not isinstance(party, str) or not party:
        raise TrialError("operation %r liability needs a party"
                         % operation_id)
    if not isinstance(reason, str) or not reason:
        raise TrialError("operation %r liability needs a reason"
                         % operation_id)
    return {"party": party, "reason": reason,
            "operation": entry.get("operation", operation_id)}


def build_operation_record(*, operation_id: str, kind: str,
                           effect: str, receipts: list,
                           usage: dict | None, settlement: str,
                           refusal: dict | None,
                           liability: dict | None,
                           artifacts: list) -> dict:
    if not isinstance(operation_id, str) or not operation_id:
        raise TrialError("operation needs a non-empty operation_id")
    if kind not in OP_KINDS:
        raise TrialError("operation kind %r is not one of %r"
                         % (kind, OP_KINDS))
    if effect != KIND_EFFECTS[kind]:
        raise TrialError("operation %r kind %r admits only effect %r"
                         % (operation_id, kind, KIND_EFFECTS[kind]))
    if not isinstance(receipts, list) \
            or not all(isinstance(r, str) and r for r in receipts):
        raise TrialError("operation %r needs receipt identity strings"
                         % operation_id)
    clean_usage = _check_usage(usage, operation_id)
    clean_settlement, clean_refusal = _check_settlement(
        settlement, refusal, operation_id)
    clean_liability = None if liability is None else _check_liability_entry(
        liability, operation_id)
    if not isinstance(artifacts, list):
        raise TrialError("operation %r artifacts must be a list"
                         % operation_id)
    return {"operation_id": operation_id, "kind": kind, "effect": effect,
            "receipts": list(receipts), "usage": clean_usage,
            "settlement": clean_settlement, "refusal": clean_refusal,
            "liability": clean_liability, "artifacts": list(artifacts)}


STORE_KIND_BY_EFFECT = {
    broker.MODEL_INFERENCE: "child_inference",
    broker.SANDBOX_EXEC: "episode",
    broker.OBSERVATION_ADAPTER: "probe",
}

STORE_SETTLEMENT_BY_STATE = {
    "observed": "observed",
    "reconciled": "observed",
    "cancelled": "cancelled",
    "unresolved": "unresolved",
}


def _full_usage(receipts: list) -> dict | None:
    for receipt in receipts:
        content = dict(receipt.get("content") or {})
        if isinstance(content.get("model_meta"), dict) and content[
                "model_meta"].get("simulated"):
            continue
        seen = content.get("usage") or {}
        if all(isinstance(seen.get(field), int)
               and not isinstance(seen.get(field), bool)
               and seen[field] >= 0 for field in USAGE_FIELDS):
            return {field: seen[field] for field in USAGE_FIELDS}
    return None


def operation_record_from_store_row(row: dict, receipts: list, *,
                                    kind: str | None = None) -> dict:
    operation_id = row.get("id", "")
    effect = (row.get("payload") or {}).get("effect", "")
    resolved_kind = kind or STORE_KIND_BY_EFFECT.get(effect, "")
    state = row.get("dispatch_state", "")
    if (row.get("cancel_state") or "none") not in ("none", ""):
        settlement = "cancelled"
    else:
        settlement = STORE_SETTLEMENT_BY_STATE.get(state, "unresolved")
    usage = _full_usage(receipts)
    refusal = None
    if settlement in ("cancelled", "refused"):
        refusal = {"reason": "cancel-%s" % (row.get("cancel_state")
                                            or "confirmed"),
                   "operation": operation_id}
    liability = None
    if settlement == "unresolved":
        liability = {"party": "campaign",
                     "reason": "unresolved-external-effect",
                     "operation": operation_id}
    identities = [r.get("receipt_identity", "") for r in receipts
                  if r.get("receipt_identity")]
    return build_operation_record(
        operation_id=operation_id, kind=resolved_kind, effect=effect,
        receipts=identities, usage=usage, settlement=settlement,
        refusal=refusal, liability=liability, artifacts=[])


def costs_for_operations(dsn: str, op_ids: list) -> dict:
    from psycopg.rows import dict_row

    if not isinstance(op_ids, list) or not all(
            isinstance(o, str) and o for o in op_ids):
        raise TrialError("costs need an operation_ids list")
    seen: dict = {}
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for operation_id in dict.fromkeys(op_ids):
                cur.execute("SELECT receipt_identity, content"
                            " FROM receipts WHERE operation_id = %s"
                            " ORDER BY receipt_identity",
                            (operation_id,))
                usage = _full_usage([dict(r) for r in cur.fetchall()])
                if usage is None:
                    raise TrialError("operation %r has no measured usage"
                                     % operation_id)
                seen[operation_id] = usage
            conn.commit()
    return {"in": sum(u["input_tokens"] for u in seen.values()),
            "out": sum(u["output_tokens"] for u in seen.values()),
            "calls": sum(u["model_calls"] for u in seen.values())}


def _cell_kind(operation_id: str, effect: str) -> str:
    if effect == broker.MODEL_INFERENCE:
        return "child_inference" if ":work:model" in operation_id \
            else "a_interpretation"
    if effect == broker.OBSERVATION_ADAPTER:
        return "probe"
    if effect == broker.SANDBOX_EXEC:
        if operation_id.endswith(":check"):
            return "check"
        if ":step:" in operation_id:
            return "policy_step"
        return "episode"
    return "episode"


def cell_operation_ids(dsn: str, *, run_id: str, task_id: str,
                       plan_id: str | None = None) -> dict:
    from psycopg.rows import dict_row

    found: dict = {}
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, payload FROM operations WHERE id LIKE %s"
                        " ORDER BY id",
                        ("coord:%s:%s:%%" % (run_id, task_id),))
            for row in cur.fetchall():
                effect = (dict(row.get("payload") or {})).get("effect", "")
                found[row["id"]] = {"kind": _cell_kind(row["id"], effect),
                                    "effect": effect}
            if plan_id:
                cur.execute("SELECT id, payload FROM operations WHERE id"
                            " LIKE %s ORDER BY id", ("%s:%%" % plan_id,))
                for row in cur.fetchall():
                    effect = (dict(row.get("payload") or {})
                              ).get("effect", "")
                    found[row["id"]] = {"kind": _cell_kind(row["id"],
                                                           effect),
                                        "effect": effect}
            conn.commit()
    return found


def reconcile_campaign_union_from_store(dsn: str, cells: list,
                                        *, kinds: dict | None = None) -> dict:
    from psycopg.rows import dict_row

    if not isinstance(cells, list):
        raise TrialError("campaign union needs a list of cells")
    wanted: dict = {}
    for cell in cells:
        if not isinstance(cell, dict):
            raise TrialError("cells must be objects")
        cell_id = cell.get("cell_id")
        ids = cell.get("operation_ids")
        if not isinstance(cell_id, str) or not cell_id:
            raise TrialError("cells need a non-empty cell_id")
        if not isinstance(ids, list) or not all(
                isinstance(o, str) and o for o in ids):
            raise TrialError("cell %r needs an operation_ids list"
                             % cell_id)
        wanted[cell_id] = list(ids)
    hints = dict(kinds or {})
    rows: dict = {}
    receipts_by_op: dict = {}
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for cell_id in wanted:
                for operation_id in wanted[cell_id]:
                    if operation_id in rows:
                        continue
                    cur.execute("SELECT * FROM operations WHERE id = %s",
                                (operation_id,))
                    row = cur.fetchone()
                    if row is None:
                        raise TrialError("operation %r has no durable row"
                                         % operation_id)
                    rows[operation_id] = dict(row)
                    cur.execute("SELECT receipt_identity, outcome, content"
                                " FROM receipts WHERE operation_id = %s"
                                " ORDER BY receipt_identity",
                                (operation_id,))
                    receipts_by_op[operation_id] = [
                        dict(r) for r in cur.fetchall()]
            conn.commit()
    records = {operation_id: operation_record_from_store_row(
        row, receipts_by_op[operation_id], kind=hints.get(operation_id))
        for operation_id, row in rows.items()}
    union_cells = [{"cell_id": cell_id,
                    "operations": [records[o] for o in ids]}
                   for cell_id, ids in wanted.items()]
    union = reconcile_campaign_union(union_cells)
    union["records"] = [records[o] for o in union["operation_ids"]]
    return union


def _operation_costs(record: dict) -> dict:
    usage = record.get("usage") or {}
    costs = {field: 0 for field in COST_FIELDS}
    costs.update({
        "tool_invocations": int(record["effect"] == broker.OBSERVATION_ADAPTER),
        "sandbox_ops": int(record["effect"] == broker.SANDBOX_EXEC),
        "policy_exec_ops": int(record["kind"] == "policy_step"),
        "protected_check_ops": int(record["kind"] == "check"),
        "abandoned_ops": int(record["settlement"] == "cancelled"),
        **dict.fromkeys(NULLABLE_COSTS),
    })
    for trial_field, usage_field in TOKEN_MAP.items():
        costs[trial_field] = usage.get(usage_field, 0)
    return costs


def reconcile_campaign_union(cells: list) -> dict:
    if not isinstance(cells, list):
        raise TrialError("campaign union needs a list of cells")
    attribution: dict = {}
    flat: dict = {}
    order: list = []
    for cell in cells:
        if not isinstance(cell, dict):
            raise TrialError("cells must be objects")
        cell_id = cell.get("cell_id")
        if not isinstance(cell_id, str) or not cell_id:
            raise TrialError("cells need a non-empty cell_id")
        operations = cell.get("operations")
        if not isinstance(operations, list):
            raise TrialError("cell %r needs an operations list" % cell_id)
        for record in operations:
            if not isinstance(record, dict):
                raise TrialError("cell %r operations must be objects"
                                 % cell_id)
            op_id = record.get("operation_id")
            if not isinstance(op_id, str) or not op_id:
                raise TrialError("cell %r operations need a non-empty "
                                 "operation_id" % cell_id)
            if op_id in flat:
                if flat[op_id] != record:
                    raise TrialError("conflicting entries for operation "
                                     "%r" % op_id)
            else:
                flat[op_id] = record
                order.append(op_id)
            attribution.setdefault(op_id, [])
            if cell_id not in attribution[op_id]:
                attribution[op_id].append(cell_id)
    costs_union = reconcile_cost_union(
        [{"operation_id": op_id, "kind": flat[op_id].get("kind"),
          "costs": _operation_costs(flat[op_id])} for op_id in order])
    unknown = any(flat[op_id].get("usage") is None
                  and flat[op_id].get("effect") == broker.MODEL_INFERENCE
                  for op_id in order)
    totals = dict(costs_union["totals"])
    if unknown:
        for field in NULLABLE_COSTS:
            totals[field] = UNKNOWN
        for trial_field in TOKEN_MAP:
            totals[trial_field] = UNKNOWN
    return {"n_operations": costs_union["n_operations"],
            "operation_ids": costs_union["operation_ids"],
            "attribution": attribution,
            "totals": totals, "by_kind": costs_union["by_kind"],
            "records": [flat[op_id] for op_id in order]}


def reconcile_cost_union(operations: list) -> dict:
    if not isinstance(operations, list):
        raise TrialError("reconciliation needs a list of operations")
    by_id: dict = {}
    for entry in operations:
        if not isinstance(entry, dict):
            raise TrialError("operations entries must be objects")
        op_id = entry.get("operation_id")
        kind = entry.get("kind")
        costs = entry.get("costs")
        if not isinstance(op_id, str) or not op_id:
            raise TrialError("operations need a non-empty operation_id")
        if kind not in OP_KINDS:
            raise TrialError("operation kind %r is not one of %r"
                             % (kind, OP_KINDS))
        if not isinstance(costs, dict):
            raise TrialError("operation %r needs a costs object" % op_id)
        for field, value in costs.items():
            if field not in COST_FIELDS:
                raise TrialError("unknown cost field %r" % field)
            if value is None and field in NULLABLE_COSTS:
                continue
            if isinstance(value, bool) \
                    or not isinstance(value, (int, float)) or value < 0:
                raise TrialError("operation cost %r must be non-negative"
                                 % field)
        if op_id in by_id:
            if by_id[op_id]["kind"] != kind \
                    or by_id[op_id]["costs"] != costs:
                raise TrialError("conflicting entries for operation %r"
                                 % op_id)
            continue
        by_id[op_id] = {"kind": kind, "costs": dict(costs)}
    totals: dict = {}
    for field in COST_FIELDS:
        total: Any = 0
        seen = False
        for entry in by_id.values():
            value = entry["costs"].get(field, None)
            if value is None:
                if field in NULLABLE_COSTS:
                    total = UNKNOWN
                continue
            if total == UNKNOWN:
                continue
            total += value
            seen = True
        totals[field] = total if seen or total == UNKNOWN else 0
    by_kind: dict = {}
    for entry in by_id.values():
        by_kind[entry["kind"]] = by_kind.get(entry["kind"], 0) + 1
    return {"totals": totals, "operation_ids": sorted(by_id),
            "by_kind": by_kind, "n_operations": len(by_id)}


def cell_key(freeze_id: str, panel: str, task: str, repeat: int,
               arm: str) -> tuple:
    if panel not in PANELS:
        raise TrialError("panel %r is not one of %r" % (panel, PANELS))
    if arm not in ARMS:
        raise TrialError("arm %r is not one of %r" % (arm, ARMS))
    if repeat not in REPEATS:
        raise TrialError("repeat %r is not one of %r" % (repeat, REPEATS))
    return (freeze_id, panel, task, repeat, arm)


def select_panel_cells(freeze: dict, *, panel: str) -> list:
    if panel not in PANELS:
        raise TrialError("panel %r is not one of %r" % (panel, PANELS))
    schedule = freeze.get("schedule")
    if not isinstance(schedule, list):
        raise TrialError("freeze needs a schedule list")
    freeze_id = freeze.get("freeze_id", "")
    cells = []
    for cell in schedule:
        if cell.get("panel") != panel:
            continue
        cell_key(freeze_id, cell.get("panel"), cell.get("task"),
                 cell.get("repeat"), cell.get("arm"))
        cells.append({"panel": cell.get("panel"), "task": cell.get("task"),
                      "repeat": cell.get("repeat"), "arm": cell.get("arm")})
    return cells


LEGACY_PACKAGE_DIGEST_FIELDS = ("package_digest", "digest")


def _freeze_package_digest(freeze: dict) -> str | None:
    package = freeze.get("package") or {}
    for field in LEGACY_PACKAGE_DIGEST_FIELDS:
        value = package.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _resume_record_settled(record: dict) -> bool:
    outcome = record.get("outcome")
    failures = record.get("failures")
    receipts = record.get("receipts")
    if outcome == "success":
        return True
    return outcome == "failure" and isinstance(failures, list) \
        and len(failures) > 0 and isinstance(receipts, list) \
        and len(receipts) > 0


def resume_plan(*, freeze: dict, schedule_cells: list,
                evidence_by_key: dict, pending_by_key: dict,
                reconciled_operation_ids=None) -> dict:
    if not isinstance(schedule_cells, list):
        raise TrialError("resume needs a schedule cell list")
    if not isinstance(evidence_by_key, dict) \
            or not isinstance(pending_by_key, dict):
        raise TrialError("resume needs evidence and pending maps")
    if reconciled_operation_ids is not None:
        reconciled = frozenset(reconciled_operation_ids)
    else:
        reconciled = None
    package_digest = _freeze_package_digest(freeze)
    none_selection = (freeze.get("package") or {}).get("kind") == "none"
    skip: list = []
    run: list = []
    reconcile: list = []
    for cell in schedule_cells:
        key = cell_key(freeze.get("freeze_id", ""), cell.get("panel"),
                       cell.get("task"), cell.get("repeat"),
                       cell.get("arm"))
        if key in pending_by_key:
            reconcile.append(key)
            continue
        record = evidence_by_key.get(key)
        if _resume_skippable(record, package_digest, reconciled,
                             none_selection=none_selection):
            skip.append(key)
            continue
        run.append(key)
    return {"skip": skip, "run": run, "reconcile": reconcile}


NONE_PACKAGE_MARK = "none"


def _resume_skippable(record: Any, package_digest: str | None,
                      reconciled: frozenset | None,
                      none_selection: bool = False) -> bool:
    if not isinstance(record, dict):
        return False
    if package_digest is None:
        if none_selection:
            if record.get("procedure_digest") != NONE_PACKAGE_MARK:
                return False
        elif record.get("procedure_digest") not in (None, NONE_PACKAGE_MARK):
            return False
    elif record.get("procedure_digest") != package_digest:
        return False
    if not _resume_record_settled(record):
        return False
    if record.get("outcome") == "success" and not none_selection \
            and record.get("frozen_digest") != package_digest:
        return False
    claimed = set()
    for receipt in record.get("receipts") or []:
        if isinstance(receipt, str) and receipt:
            claimed.add(receipt)
    for entry in record.get("operations") or []:
        if isinstance(entry, dict) and entry.get("operation_id"):
            claimed.add(entry["operation_id"])
    if not claimed:
        return False
    if reconciled is None:
        return bool(record.get("outcome"))
    return claimed <= reconciled


def refused_trial_record(*, freeze_id: str, panel: str, task_id: str,
                         repeat: int, arm: str, source_sha: str,
                         config_digest: str, package_digest: str,
                         protected: dict, failures: list, costs: dict,
                         receipts: list, operations: list,
                         liabilities: list | None = None) -> dict:
    if not failures:
        raise TrialError("refusal needs at least one quoted failure")
    record = build_trial_record(
        freeze_id=freeze_id, panel=panel, task_id=task_id, repeat=repeat,
        arm=arm, source_sha=source_sha, config_digest=config_digest,
        package_digest=package_digest, outcome="refusal", solved=False,
        protected=protected, failures=failures, costs=costs,
        receipts=receipts, operations=operations,
        liabilities=liabilities or [])
    return record


def require_settled_failure(operation: dict, costs: dict) -> dict:
    settlement = operation.get("settlement")
    if settlement == "unresolved":
        raise TrialError("unresolved effects are never a settled failure")
    if any(value == UNKNOWN for value in costs.values()):
        raise TrialError("missing mandatory evidence is never a settled "
                         "zero-cost failure")
    return {"settlement": settlement, "costs": dict(costs)}


def derive_correction(record: dict, *, reason: str, fixes: dict) -> dict:
    if not isinstance(record, dict):
        raise TrialError("correction needs a record object")
    if not isinstance(reason, str) or not reason:
        raise TrialError("correction needs a stated reason")
    if not isinstance(fixes, dict) or not fixes:
        raise TrialError("correction needs non-empty fixes")
    validate_trial_record(record)
    corrected = dict(record)
    for field, value in fixes.items():
        corrected[field] = value
    corrected = validate_trial_record(corrected)
    return {"kind": "derived-correction", "reason": reason,
            "raw": record, "record": corrected}


def executed_package(package: dict) -> str:
    if not isinstance(package, dict):
        raise TrialError("package must be an object")
    if package.get("provenance") != "retained-bytes":
        raise TrialError("provenance-only baseline labels never stand in "
                         "for the executed decision package")
    digest = package.get("digest")
    if not isinstance(digest, str) or not digest:
        raise TrialError("executed package needs a non-empty digest")
    return digest


def assemble_freeze_contents(freeze_id: str, *, source_sha: str,
                             package_bytes: bytes,
                             package_kind: str = "learned",
                             input_contract: dict,
                             exposure_manifest: dict,
                             selector: dict, baselines: dict,
                             model: dict | None = None,
                             config: dict | None = None) -> dict:
    if not isinstance(package_bytes, bytes) or not package_bytes:
        raise TrialError("freeze needs non-empty package bytes")
    if package_kind not in ("learned", "none"):
        raise TrialError("package kind is 'learned' or 'none'")
    if not isinstance(baselines, dict) \
            or baselines.get("declared_before_inspection") is not True:
        raise TrialError("baselines must be declared BEFORE inspecting "
                         "the acquired package")
    if not isinstance(input_contract, dict) or not input_contract:
        raise TrialError("freeze needs a non-empty input contract")
    if not isinstance(exposure_manifest, dict):
        raise TrialError("freeze needs an exposure manifest")
    if not isinstance(selector, dict) or not selector:
        raise TrialError("freeze needs a non-empty selector")
    digest = sha_hex(package_bytes)
    if exposure_manifest.get("package_digest") != digest:
        raise TrialError("exposure manifest must reference the bytes "
                         "being frozen")
    freeze = freeze_mod.build_freeze(
        freeze_id, source_sha=source_sha,
        package={"kind": package_kind, "digest": digest},
        baselines={**baselines, "package_digest": digest},
        model=model, config=config)
    freeze["input_contract"] = dict(input_contract)
    freeze["exposure_manifest"] = dict(exposure_manifest)
    freeze["selector"] = dict(selector)
    return freeze


def _vec_side(values: Any, name: str) -> dict:
    if not isinstance(values, dict):
        raise TrialError("%s vector must be an object" % name)
    clean: dict = {}
    solved = values.get("solved")
    if isinstance(solved, bool) or not isinstance(solved, int) \
            or solved < 0:
        raise TrialError("%s solved must be a non-negative int" % name)
    clean["solved"] = solved
    for field in MANDATORY_RESOURCES:
        value = values.get(field, None)
        if value is None:
            clean[field] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)) \
                or value < 0:
            raise TrialError("%s %s must be non-negative" % (name, field))
        else:
            clean[field] = value
    return clean


def _within_ratio(got: Any, base: Any) -> bool:
    if base == 0:
        return got == 0
    return got * RATIO_DEN <= base * RATIO_NUM


def promising_versus(learned: dict, comparator: dict, *,
                     family_losses: dict | None = None,
                     family_cap: int = 0) -> dict:
    side_l = _vec_side(learned, "learned")
    side_c = _vec_side(comparator, "comparator")
    losses = dict(family_losses or {})
    inputs = {"learned": dict(side_l), "comparator": dict(side_c),
              "family_losses": dict(losses), "family_cap": family_cap}
    for fam, lost in losses.items():
        if not isinstance(lost, int) or lost < 0:
            raise TrialError("family loss for %r must be a non-negative "
                             "int" % fam)
        if lost > family_cap:
            return {"verdict": "fail", "reasons": [
                "family %s loses %d solved episodes (cap %d)"
                % (fam, lost, family_cap)], "inputs": inputs}
    if any(side_l[f] is None or side_c[f] is None
           for f in MANDATORY_RESOURCES):
        return {"verdict": "unevaluable",
                "reasons": ["unknown mandatory totals make the comparison "
                            "unevaluable"],
                "inputs": inputs}
    if side_l["solved"] > side_c["solved"]:
        short = [f for f in MANDATORY_RESOURCES
                 if not _within_ratio(side_l[f], side_c[f])]
        if not short:
            return {"verdict": "pass",
                    "reasons": ["strictly more solved within 1.25x on "
                                "every resource"],
                    "inputs": inputs}
        return {"verdict": "fail", "reasons": [
            "resource %s exceeds 1.25x the comparator" % ",".join(short)],
            "inputs": inputs}
    if side_l["solved"] == side_c["solved"]:
        grown = [f for f in MANDATORY_RESOURCES
                 if side_l[f] > side_c[f]]
        if not grown and side_l["model_tokens"] < side_c["model_tokens"]:
            return {"verdict": "pass",
                    "reasons": ["tied solved count with no resource "
                                "increase and strictly fewer model tokens"],
                    "inputs": inputs}
        return {"verdict": "fail", "reasons": [
            "tie needs no increase anywhere and strictly fewer model "
            "tokens"],
            "inputs": inputs}
    return {"verdict": "fail",
            "reasons": ["learned solves fewer (%d vs %d)"
                        % (side_l["solved"], side_c["solved"])],
            "inputs": inputs}


def _cell(matchups: dict, arm: str, panel: str,
          family_cap: int) -> dict:
    try:
        cells = matchups[arm][panel]
    except (KeyError, TypeError):
        raise TrialError("comparator %s needs evaluation + transfer" % arm)
    if not isinstance(cells, (list, tuple)) or len(cells) < 2:
        raise TrialError("comparator %s panel %s needs (learned, "
                         "comparator[, family_losses])" % (arm, panel))
    losses = cells[2] if len(cells) > 2 else None
    return promising_versus(cells[0], cells[1], family_losses=losses,
                            family_cap=family_cap)


def promising_rule(matchups: dict) -> dict:
    if set(matchups) != {"S", "A", "F"}:
        raise TrialError("the rule compares L against S, A and F")
    by_comparator = {}
    for arm in ("S", "A", "F"):
        cell_eval = _cell(matchups, arm, "evaluation", 1)
        cell_transfer = _cell(matchups, arm, "transfer", 0)
        passed = cell_eval["verdict"] == "pass" \
            and cell_transfer["verdict"] == "pass"
        by_comparator[arm] = {"evaluation": cell_eval,
                              "transfer": cell_transfer, "pass": passed}
    raw = {arm: {"evaluation": [matchups[arm]["evaluation"][0],
                                matchups[arm]["evaluation"][1]],
                 "transfer": [matchups[arm]["transfer"][0],
                              matchups[arm]["transfer"][1]]}
           for arm in ("S", "A", "F")}
    return {"promising": all(cell["pass"]
                             for cell in by_comparator.values()),
            "by_comparator": by_comparator, "raw": raw}
