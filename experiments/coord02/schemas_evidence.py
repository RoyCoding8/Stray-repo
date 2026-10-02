"""Shared EC02 trial/record schema, cost-union reconciliation, freeze assembly.

Owned by lane E. Both L-construction output and E-evidence consume the
trial record defined here. Identity vocabulary (panels, arms, repeats)
and freeze/checker mechanics are reused from lane W; nothing here
duplicates them. Unknown measurement stays unknown, never zero.
"""

from __future__ import annotations

from typing import Any

from settlement.representation import canonical_bytes, sha_hex

from . import freeze as freeze_mod

TRIAL_VERSION = "coord02-trial/1"

ARMS = freeze_mod.ARMS
PANELS = freeze_mod.PANELS
REPEATS = tuple(freeze_mod.REPEATS)

OUTCOMES = ("success", "failure", "refusal", "timeout", "incomplete")

OP_KINDS = ("build", "validation", "episode", "failed", "cancelled")

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


def build_trial_record(*, freeze_id: str, panel: str, task_id: str,
                       repeat: int, arm: str, source_sha: str,
                       config_digest: str, package_digest: str,
                       outcome: str, solved: bool,
                       protected: dict, failures: list,
                       costs: dict, receipts: list,
                       operations: list | None = None,
                       liabilities: list | None = None,
                       internal_accounting: dict | None = None,
                       external_billing: dict | None = None) -> dict:
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
    return {"version": TRIAL_VERSION, "freeze_id": freeze_id,
            "panel": panel, "task_id": task_id, "repeat": repeat,
            "arm": arm, "source_sha": source_sha,
            "config_digest": config_digest,
            "package_digest": package_digest, "outcome": outcome,
            "solved": solved,
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
        external_billing=record.get("external_billing", {}))


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
    return build_trial_record(
        freeze_id=w_record.get("freeze_id", ""),
        panel=w_record.get("panel", ""),
        task_id=w_record.get("task_id", ""),
        repeat=w_record.get("repeat", 0), arm=w_record.get("arm", ""),
        source_sha=source_sha, config_digest=config_digest,
        package_digest=w_record.get("procedure_digest") or "none",
        outcome="success" if solved else "failure", solved=solved,
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
