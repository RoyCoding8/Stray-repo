"""M4 offline recomputation (E1/E2 prospective comparison).

Deterministic only: no gateway, no database, no network. Quality is
derived from frozen tasks plus observable behavior, never from runtime
verdict labels. Resource records name a source and a closed measurement
status. Only measured records carry numeric values; unknown billing stays
unknown, never zero.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from experiments.ad01 import frontier
from experiments.ad01 import offline_recompute as M4

P0_SRC = ("def STEP(view, state):\n"
          "    return {'action': {'kind': 'diagnose', 'target': 't',"
          " 'inputs': {}, 'evidence_refs': [], 'requested_resources': {}},"
          " 'state': {}}\n")
P1_SRC = ("def STEP(view, state):\n"
          "    return {'action': {'kind': 'construct_method', 'target': 't',"
          " 'inputs': {'max_queries': 2}, 'evidence_refs': [],"
          " 'requested_resources': {'queries': 2}}, 'state': {}}\n")
P2_SRC = ("def STEP(view, state):\n"
          "    return {'action': {'kind': 'use_method', 'target': 't',"
          " 'inputs': {'method': 'm'}, 'evidence_refs': [],"
          " 'requested_resources': {}}, 'state': {}}\n")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _action(kind: str) -> dict:
    return {"kind": kind, "target": "t", "inputs": {},
            "evidence_refs": [], "requested_resources": {}}


def _receipt(op_id: str, *, arm: str, task_id: str,
             source_digest: str, artifact_digest: str | None = None,
             result: dict | None = None, receipt_identity: str | None = None) -> dict:
    result = dict(result or {"status": "recorded"})
    artifact_digest = artifact_digest or source_digest
    return frontier.make_evidence_record(
        "m4-observation", op_id, "success",
        receipt_identity=receipt_identity,
        arm=arm, task_id=task_id,
        source_digest=source_digest, artifact_digest=artifact_digest,
        input_digest=_digest("input:%s" % op_id),
        result_digest=_digest(json.dumps(result, sort_keys=True,
                                         separators=(",", ":"))),
        details={"raw_payload": {"result": result}})


def _op(op_id: str, *, arm: str = "P0", task_id: str | None = None,
        source_digest: str = "0" * 64,
        result: dict | None = None) -> dict:
    receipt = _receipt(op_id, arm=arm, task_id=task_id or op_id,
                       source_digest=source_digest, result=result)
    return {"operation_id": op_id, "receipts": [receipt],
            "invocation": {"operation_id": op_id, "launcher": "test-double",
                           "attempt": 1}}


def _tasks() -> dict:
    return {
        "d-sw-0": {"expected": "reduce-4"},
        "d-gr-0": {"expected": "reduce-6"},
        "u-sw-0": {"expected": "reduce-3"},
        "u-gr-0": {"expected": "reduce-5"},
        "x-sw-0": {"expected": "reduce-2"},
    }


def _freeze() -> dict:
    sources = {"P0": P0_SRC, "P1": P1_SRC, "P2": P2_SRC}
    identities = {}
    repertoires = {}
    for arm, source in sources.items():
        digest = _digest(source)
        identities[arm] = {
            "status": "available",
            "source": source,
            "source_digest": digest,
            "artifact": {"kind": "learning-policy",
                         "abi": "ad01-policy-step-v1",
                         "source_digest": digest},
            "history_tokens": 40 if arm == "P0" else 120,
            "failed_attempts": 0,
        }
        repertoires[arm] = {
            "members": [{"method_source": source,
                         "source_digest": digest}],
            "member_digests": [digest],
        }
    freeze = {
        "study_id": "invl02-m4-demo",
        "study_root": "invl02_m4",
        "arms": ["P0", "P1", "P2"],
        "order": ["P1", "P2"],
        "development": [{"episode_id": "d-sw-0", "task_id": "d-sw-0"},
                        {"episode_id": "d-gr-0", "task_id": "d-gr-0"}],
        "assessment": [{"episode_id": "a-0",
                        "use_tasks": ["u-sw-0", "u-gr-0"]}],
        "audit": [{"episode_id": "t-0", "use_tasks": ["x-sw-0"]}],
        "construction_allowance": M4.reserve_allowance(
            ["P1", "P2"], init=1, repair=1),
        "caps": {"per_episode": {"policy_steps": 6, "model_calls": 4},
                 "diagnostic_queries_per_episode": 8,
                 "study_model_calls": 20,
                 "history_token_ceiling": 10000},
        "metric_rule": {"kind": "mean-quality", "margin": 0.0,
                        "tie": "incumbent"},
        "resource_rule": {"kind": "ceiling",
                          "note": "quality under common ceilings"},
        "config": {"model": "test-double",
                   "instruments": ["diagnostic", "construct", "use"],
                   "abi": "ad01-policy-step-v1",
                   "artifact_kind": "learning-policy"},
        "policy_identities": identities,
        "method_repertoires": repertoires,
        "tasks": _tasks(),
    }
    freeze["freeze_digest"] = M4.freeze_digest(freeze)
    return freeze


def _episode(episode_id: str, arm: str, digest: str, op_id: str) -> dict:
    return {"episode_id": episode_id, "arm": arm,
            "policy_digest": digest,
            "policy_actions": [_action("diagnose")],
            "policy_steps": 1, "model_calls": 1, "witness_queries": 2,
            "history_tokens": 30, "failed_attempts": 0,
            "operations": [op_id]}


def demo_bundle() -> dict:
    freeze = _freeze()
    digests = {arm: _digest(source)
               for arm, source in (("P0", P0_SRC), ("P1", P1_SRC),
                                   ("P2", P2_SRC))}
    ops = {}
    for op_id in ("op-d-sw-0", "op-d-gr-0", "op-a-0", "op-t-0"):
        ops[op_id] = _op(op_id, arm="P0", task_id=op_id.removeprefix("op-"),
                         source_digest=digests["P0"])
    for arm, suffixes in (("P1", ("init",)), ("P2", ("init", "repair"))):
        for suffix in suffixes:
            op_id = "op-construct-%s-%s" % (arm, suffix)
            ops[op_id] = _op(op_id, arm=arm, task_id="construct-%s" % arm,
                             source_digest=digests[arm])
    observed = {
        ("P0", "u-sw-0"): "reduce-3", ("P0", "u-gr-0"): "other",
        ("P1", "u-sw-0"): "other", ("P1", "u-gr-0"): "other",
        ("P2", "u-sw-0"): "reduce-3", ("P2", "u-gr-0"): "reduce-5",
        ("P0", "x-sw-0"): "reduce-2", ("P1", "x-sw-0"): "other",
        ("P2", "x-sw-0"): "reduce-2",
    }
    records = []
    for (arm, task), output in sorted(observed.items()):
        rid = "a-%s-%s" % (arm, task) if task.startswith("u") else \
            "t-%s-%s" % (arm, task)
        op_id = "op-use-%s" % rid
        ops[op_id] = _op(
            op_id, arm=arm, task_id=task, source_digest=digests[arm],
            result={"observed": output, "queries": 1})
        expected = freeze["tasks"][task]["expected"]
        records.append({
            "record_id": rid, "arm": arm, "task_id": task,
            "executed": "candidate",
            "policy_digest": digests[arm],
            "executed_source_digest": digests[arm],
            "policy_artifact_kind": "learning-policy",
            "observed": output,
            "claimed_verdict": "preserved" if output == expected
                               else "failed",
            "costs": {"witness_queries": 1},
            "input_digest": ops[op_id]["receipts"][0]["input_digest"],
            "result_digest": ops[op_id]["receipts"][0]["result_digest"],
            "receipt_identity": ops[op_id]["receipts"][0][
                "receipt_identity"],
            "operation_ids": [op_id],
        })
    witness_use = len(records)
    child_receipts = {
        op_id: dict(row["receipts"][0])
        for op_id, row in ops.items()
    }
    for record in records:
        receipt = child_receipts[record["operation_ids"][0]]
        record["child_result"] = receipt["details"]["raw_payload"]["result"]
    candidates = []
    for record in records:
        if record["arm"] not in ("P1", "P2"):
            continue
        predictor = {"observed": record["observed"]}
        predictor_digest = hashlib.sha256(json.dumps(
            predictor, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        candidate = {
            "arm": record["arm"], "task_id": record["task_id"],
            "raw_response": record["observed"],
            "raw_response_digest": hashlib.sha256(
                record["observed"].encode()).hexdigest(),
            "predictor": predictor, "predictor_digest": predictor_digest,
            "operation_id": "op-candidate-%s" % record["record_id"],
            "operation_ids": ["op-candidate-%s" % record["record_id"]],
            "input_digest": record["input_digest"],
            "prompt_digest": _digest("prompt:%s" % record["record_id"]),
        }
        candidates.append(candidate)
        record["candidate_digest"] = predictor_digest
        record["executed_source_digest"] = predictor_digest
        op_id = record["operation_ids"][0]
        result = {"observed": record["observed"], "queries": 1}
        receipt = _receipt(op_id, arm=record["arm"],
                           task_id=record["task_id"],
                           source_digest=predictor_digest, result=result)
        ops[op_id] = _op(op_id, arm=record["arm"],
                         task_id=record["task_id"],
                         source_digest=predictor_digest, result=result)
        child_receipts[op_id] = receipt
        record["child_result"] = result
        record["result_digest"] = receipt["result_digest"]
        record["receipt_identity"] = receipt["receipt_identity"]
        candidate_op = candidate["operation_id"]
        candidate_result = {"raw_response": candidate["raw_response"]}
        ops[candidate_op] = _op(
            candidate_op, arm=record["arm"], task_id=record["task_id"],
            source_digest=predictor_digest, result=candidate_result)
        child_receipts[candidate_op] = ops[candidate_op]["receipts"][0]
    candidate_digests = {"P1": {}, "P2": {}}
    input_bindings = {"P1": {}, "P2": {}}
    prompt_bindings = {"P1": {}, "P2": {}}
    for candidate in candidates:
        arm = candidate["arm"]
        candidate_digests[arm][candidate["task_id"]] = candidate[
            "predictor_digest"]
        input_bindings[arm][candidate["task_id"]] = candidate["input_digest"]
        prompt_bindings[arm][candidate["task_id"]] = candidate["prompt_digest"]
    for arm in ("P1", "P2"):
        freeze["policy_identities"][arm]["candidate_digests"] = \
            candidate_digests[arm]
        freeze["method_repertoires"][arm] = {
            "members": [{"method_source": json.dumps(
                candidate["predictor"], sort_keys=True,
                separators=(",", ":")),
                "source_digest": candidate["predictor_digest"]}
                for candidate in candidates if candidate["arm"] == arm],
            "member_digests": sorted(set(candidate_digests[arm].values()))}
    history_reference = {"P1": [], "P2": [{"task_id": "permitted"}]}
    freeze["history_reference"] = history_reference
    freeze["arm_contracts"] = {
        "P0": {"kind": "fixed-incumbent", "source": P0_SRC,
               "source_digest": _digest(P0_SRC)},
        "P1": {"history": [], "history_digest": _digest("[]"),
               "input_bindings": input_bindings["P1"],
               "prompt_bindings": prompt_bindings["P1"]},
        "P2": {"history": history_reference["P2"],
               "history_digest": _digest(json.dumps(
                   history_reference["P2"], sort_keys=True,
                   separators=(",", ":"))),
               "input_bindings": input_bindings["P2"],
               "prompt_bindings": prompt_bindings["P2"]},
    }
    freeze["dispatch_ledger"] = [
        {"dispatch_id": "dispatch-%d" % index, "operation_id": op_id,
         "arm": arm, "task_id": task, "attempt": 1}
        for index, (op_id, arm, task) in enumerate([
            ("op-d-sw-0", "P0", "d-sw-0"),
            ("op-d-gr-0", "P0", "d-gr-0"),
            ("op-a-0", "P0", "a-0"),
            ("op-t-0", "P0", "t-0"),
            ("op-construct-P1-init", "P1", "construct-P1"),
            ("op-construct-P2-init", "P2", "construct-P2"),
            ("op-construct-P2-repair", "P2", "construct-P2")], start=1)]
    freeze["dispatch_ledger"].extend([
        {"dispatch_id": "dispatch-candidate-%s-%s" % (
            candidate["arm"], candidate["task_id"]),
         "operation_id": candidate["operation_id"],
         "arm": candidate["arm"], "task_id": candidate["task_id"],
         "attempt": 1}
        for candidate in candidates])
    for entry in freeze["dispatch_ledger"]:
        entry["evidence_digest"] = child_receipts[entry["operation_id"]][
            "evidence_digest"]
    freeze["freeze_digest"] = M4.freeze_digest(freeze)
    bundle = {
        "freeze": freeze,
        "development": [_episode("d-sw-0", "P0", digests["P0"],
                                 "op-d-sw-0"),
                        _episode("d-gr-0", "P0", digests["P0"],
                                 "op-d-gr-0")],
        "construction": {
            "P1": {"status": "available", "policy_source": P1_SRC,
                   "source_digest": digests["P1"], "calls": 1,
                   "history_tokens": 120, "failed_attempts": 0,
                   "operations": ["op-construct-P1-init"]},
            "P2": {"status": "available", "policy_source": P2_SRC,
                   "source_digest": digests["P2"], "calls": 2,
                   "history_tokens": 200, "failed_attempts": 1,
                   "operations": ["op-construct-P2-init",
                                  "op-construct-P2-repair"]},
        },
        "assessment": [_episode("a-0", "P0", digests["P0"], "op-a-0")],
        "audit": [_episode("t-0", "P0", digests["P0"], "op-t-0")],
        "use_records": records,
        "operations": ops,
        "dispatch_ledger": freeze["dispatch_ledger"],
        "candidates": candidates,
        "child_receipts": child_receipts,
        "accounting": {
            "model_dispatches": {
                "measured": 13, "measurement_status": "measured",
                "source": "runtime-attestation:test-builder"},
            "input_tokens": {"measured": "unknown",
                             "measurement_status": "unknown",
                             "source": "unmeasured-offline"},
            "output_tokens": {"measured": "unknown",
                              "measurement_status": "unknown",
                              "source": "unmeasured-offline"},
            "tool_queries": {
                "measured": 8 + witness_use,
                "measurement_status": "measured",
                "source": "runtime-attestation:test-builder"},
            "child_compute_ms": {"measured": "unknown",
                                 "measurement_status": "unknown",
                                 "source": "unmeasured-offline"},
            "billed_units": {"measured": "unknown",
                             "measurement_status": "unresolved",
                             "source": "billing:unresolved-provider"},
            "unresolved_exposure": {
                "measured": 0, "measurement_status": "measured",
                "source": "runtime-attestation:test-builder"},
            "human_interventions": {
                "measured": 0, "measurement_status": "measured",
                "source": "runtime-attestation:test-builder"},
        },
        "claimed": {"winner": "P2",
                    "note": "assessment means P2 1.0 over P0 0.5, P1 0.0"},
    }
    return bundle


def test_offline_recompute_passes_without_gateway_or_db(monkeypatch):
    for name in list(__import__("os").environ):
        if name.startswith(("SETTLEMENT_", "GATEWAY_", "VERCEL_",
                            "AI_GATEWAY_")):
            monkeypatch.delenv(name, raising=False)
    bundle = demo_bundle()
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]
    recomputed = result["recomputed"]
    assert recomputed["model_calls"] == 13
    assert recomputed["history_tokens"] == 30 * 4 + 120 + 200
    assert recomputed["failed_attempts"] == 1
    assert recomputed["quality_by_arm"] == {"P0": 0.5, "P1": 0.0,
                                            "P2": 1.0}
    assert recomputed["comparison"]["winner"] == "P2"
    assert recomputed["comparison"]["status"] == "complete"
    source = Path(M4.__file__).read_text()
    imports = [line for line in source.splitlines()
               if line.startswith(("import ", "from "))]
    assert not any("gateway" in line or "psycopg" in line
                   or "settlement" in line or "urllib" in line
                   or "httpx" in line or "os" in line
                   for line in imports)
    assert "os.environ" not in source
    assert "SETTLEMENT_" not in source


def test_unsettled_authoritative_operation_cannot_be_accounted_as_resolved():
    bundle = demo_bundle()
    bundle["operations"]["op-d-sw-0"]["settled"] = False
    bundle["accounting"]["unresolved_exposure"] = {
        "measured": 0, "measurement_status": "measured",
        "source": "runtime-attestation:test-builder",
    }

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert any("unresolved_exposure" in problem
               for problem in result["problems"])


def test_tamper_identity_fails():
    bundle = demo_bundle()
    bundle["freeze"]["policy_identities"]["P1"]["source"] = P2_SRC
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(
        bundle["freeze"])
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("identity-digest-mismatch P1")
               for p in result["problems"])


def test_tamper_content_fails():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P2-u-sw-0")
    record["observed"] = "forged-output"
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("quality-mismatch a-P2-u-sw-0")
               for p in result["problems"])


def test_tamper_membership_fails():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P1-u-sw-0")
    record["task_id"] = "elsewhere-task"
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("membership-unknown-task a-P1-u-sw-0")
               for p in result["problems"])


def test_tamper_costs_fails():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P2-u-gr-0")
    record["costs"]["witness_queries"] = 99
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("accounting-tool_queries-mismatch")
               for p in result["problems"])


def test_tamper_results_fails():
    bundle = demo_bundle()
    bundle["claimed"]["winner"] = "P1"
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "comparison-verdict-mismatch" in result["problems"]


def test_swapped_candidate_is_refused():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P1-u-sw-0")
    record["executed_source_digest"] = _digest(P2_SRC)
    record["policy_digest"] = _digest(P2_SRC)
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("executed-source-not-frozen a-P1-u-sw-0")
               for p in result["problems"])


def test_wrong_arm_source_or_task_receipt_is_refused():
    bundle = demo_bundle()
    op_id = "op-use-a-P2-u-sw-0"
    receipt = _receipt(
        op_id, arm="P1", task_id="u-gr-0", source_digest=_digest(P1_SRC),
        result={"observed": "reduce-3", "queries": 1})
    bundle["child_receipts"][op_id] = receipt
    bundle["operations"][op_id]["receipts"] = [receipt]
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "receipt-lineage-mismatch %s" % op_id in result["problems"]


def test_duplicate_receipt_identity_across_operations_is_refused():
    bundle = demo_bundle()
    first_op = "op-use-a-P0-u-sw-0"
    second_op = "op-use-a-P1-u-sw-0"
    first_receipt = bundle["operations"][first_op]["receipts"][0]
    second = bundle["operations"][second_op]["receipts"][0]
    duplicate = _receipt(
        second_op, arm=second["arm"], task_id=second["task_id"],
        source_digest=second["source_digest"],
        artifact_digest=second["artifact_digest"],
        result=second["details"]["raw_payload"]["result"],
        receipt_identity=first_receipt["receipt_identity"])
    bundle["operations"][second_op]["receipts"] = [duplicate]
    bundle["child_receipts"][second_op] = duplicate
    record = next(row for row in bundle["use_records"]
                  if row["operation_ids"] == [second_op])
    record["receipt_identity"] = duplicate["receipt_identity"]
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "duplicate-receipt-identity %s" % first_receipt[
        "receipt_identity"] in result["problems"]


def test_child_receipt_with_reused_identity_and_wrong_lineage_is_refused():
    bundle = demo_bundle()
    op_id = "op-use-a-P2-u-sw-0"
    authoritative = bundle["operations"][op_id]["receipts"][0]
    result = {"observed": "reduce-3", "queries": 1}
    substituted = frontier.make_evidence_record(
        "m4-observation", op_id, "success",
        receipt_identity=authoritative["receipt_identity"],
        arm="P1", task_id="u-gr-0",
        source_digest=_digest(P1_SRC), artifact_digest=_digest(P2_SRC),
        input_digest=_digest("wrong-input"),
        result_digest=_digest(json.dumps(result, sort_keys=True,
                                         separators=(",", ":"))),
        details={"raw_payload": {"result": result}})
    frontier.validate_evidence_record(substituted)
    bundle["child_receipts"][op_id] = substituted

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "missing-child-receipt %s" % op_id in result["problems"]


def test_disconnected_artifact_is_refused():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P2-u-sw-0")
    record["executed_source_digest"] = "f" * 64
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("executed-source-not-frozen a-P2-u-sw-0")
               for p in result["problems"])


def test_forged_witness_without_execution_is_refused():
    bundle = demo_bundle()
    record = next(r for r in bundle["use_records"]
                  if r["record_id"] == "a-P1-u-gr-0")
    record["observed"] = "reduce-5"
    record["claimed_verdict"] = "preserved"
    record["operation_ids"] = ["op-missing-forgery"]
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "missing-operation op-missing-forgery" in result["problems"]


def test_quota_reservation_reversed_order_same_allowance():
    forward = M4.reserve_allowance(["P1", "P2"], init=1, repair=1)
    reversed_ = M4.reserve_allowance(["P2", "P1"], init=1, repair=1)
    assert forward == reversed_
    assert forward["P1"] == forward["P2"] == {"init": 1, "repair": 1}
    bundle = demo_bundle()
    bundle["construction"]["P2"]["calls"] = 3
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "construction-ceiling-exceeded P2" in result["problems"]


def test_unavailable_arm_never_substituted():
    bundle = demo_bundle()
    freeze = bundle["freeze"]
    freeze["policy_identities"]["P1"] = {"status": "unavailable",
                                        "reason": "no settled response",
                                        "history_tokens": 60,
                                        "failed_attempts": 1}
    freeze["method_repertoires"]["P1"] = {"members": [],
                                          "member_digests": []}
    freeze["freeze_digest"] = M4.freeze_digest(freeze)
    bundle["construction"]["P1"] = {
        "status": "unavailable", "reason": "no settled response",
        "calls": 1, "history_tokens": 60, "failed_attempts": 1,
        "operations": ["op-construct-P1-init"]}
    for record in bundle["use_records"]:
        if record["arm"] != "P1":
            continue
        record.update({"executed": "incumbent", "claimed_verdict": "failed"})
        record.pop("policy_digest", None)
        record.pop("executed_source_digest", None)
    bundle["claimed"] = {"winner": "none",
                         "note": "P1 unavailable so no verdict"}
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]
    assert result["recomputed"]["comparison"]["status"] == "incomplete"
    assert result["recomputed"]["comparison"]["missing_arms"] == ["P1"]
    assert result["recomputed"]["comparison"]["winner"] is None
    assert result["recomputed"]["quality_by_arm"]["P1"] is None
    cheating = copy.deepcopy(bundle)
    record = next(r for r in cheating["use_records"]
                  if r["record_id"] == "a-P1-u-sw-0")
    record.update({"executed": "candidate",
                   "executed_source_digest": _digest(P2_SRC),
                   "policy_digest": _digest(P2_SRC),
                   "policy_artifact_kind": "learning-policy"})
    refused = M4.verify_bundle(cheating)
    assert refused["status"] == "fail"
    assert any(p.startswith("substituted-baseline a-P1-u-sw-0")
               for p in refused["problems"])


def test_m4_conflict_receipt_counts_unresolved_exposure():
    bundle = demo_bundle()
    bundle["operations"]["op-d-sw-0"]["receipt_conflicts"] = [{
        "receipt_identity": "conflict:op-d-sw-0",
        "outcome": "failure",
        "usage": {
            "input_tokens": 3, "output_tokens": 0, "charge_units": 1,
            "charge_scale": 7, "billed": True,
        },
        "unresolved_exposure": 11,
    }]
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "accounting-unresolved_exposure-mismatch reported=0 recomputed=1" in (
        result["problems"])

    bundle["accounting"]["unresolved_exposure"] = {
        "measured": 1,
        "measurement_status": "unresolved",
        "source": "durable-receipt-conflict",
    }
    assert M4.verify_bundle(bundle)["status"] == "pass"


    bundle = demo_bundle()
    assert bundle["accounting"]["billed_units"] == {
        "measured": "unknown",
        "measurement_status": "unresolved",
        "source": "billing:unresolved-provider",
    }
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]


def test_measured_zero_billing_requires_status_and_source():
    bundle = demo_bundle()
    bundle["accounting"]["billed_units"] = {
        "measured": 0,
        "measurement_status": "measured",
        "source": "provider-receipt:test",
    }
    assert M4.verify_bundle(bundle)["status"] == "pass"

    missing_status = copy.deepcopy(bundle)
    missing_status["accounting"]["billed_units"].pop("measurement_status")
    denied = M4.verify_bundle(missing_status)
    assert denied["status"] == "fail"
    assert "accounting-measurement-status-missing billed_units" in denied[
        "problems"]
    assert "billed-unknown-scored-as-zero" in denied["problems"]

    invalid_status = copy.deepcopy(bundle)
    invalid_status["accounting"]["billed_units"][
        "measurement_status"] = "attested"
    denied = M4.verify_bundle(invalid_status)
    assert denied["status"] == "fail"
    assert any(problem.startswith(
        "accounting-measurement-status-invalid billed_units")
               for problem in denied["problems"])

    missing_source = copy.deepcopy(bundle)
    missing_source["accounting"]["billed_units"]["source"] = ""
    denied = M4.verify_bundle(missing_source)
    assert denied["status"] == "fail"
    assert "accounting-source-missing billed_units" in denied["problems"]
    assert "billed-unknown-scored-as-zero" in denied["problems"]


@pytest.mark.parametrize("status", ["unknown", "unresolved"])
def test_unmeasured_zero_billing_is_never_scored_as_zero(status):
    bundle = demo_bundle()
    bundle["accounting"]["billed_units"] = {
        "measured": 0,
        "measurement_status": status,
        "source": "provider-attestation",
    }
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "accounting-unmeasured-value-invalid billed_units" in result[
        "problems"]
    assert "billed-unknown-scored-as-zero" in result["problems"]


def test_nonzero_measured_billing_is_preserved():
    bundle = demo_bundle()
    bundle["accounting"]["billed_units"] = {
        "measured": 17,
        "measurement_status": "measured",
        "source": "provider-receipt:test",
    }
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]


def test_bundle_round_trips_through_json_file(tmp_path):
    bundle = demo_bundle()
    path = tmp_path / "m4-bundle.json"
    path.write_text(json.dumps(bundle, sort_keys=True) + "\n")
    assert M4.verify_bundle_file(str(path))["status"] == "pass"


def test_multiple_terminal_receipts_for_one_operation_are_refused():
    bundle = demo_bundle()
    op_id = "op-use-a-P0-u-sw-0"
    first = bundle["operations"][op_id]["receipts"][0]
    second = _receipt(
        op_id, arm=first["arm"], task_id=first["task_id"],
        source_digest=first["source_digest"],
        artifact_digest=first["artifact_digest"],
        result=first["details"]["raw_payload"]["result"],
        receipt_identity="gw:second-terminal")
    bundle["operations"][op_id]["receipts"].append(second)
    result = M4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "multiple-terminal-receipts %s" % op_id in result["problems"]


def test_operation_receipt_lineage_is_one_to_one():
    bundle = demo_bundle()
    extra = "op-unclaimed"
    extra_row = _op(extra, arm="P1", task_id="unclaimed",
                    source_digest="0" * 64)
    bundle["operations"][extra] = extra_row
    bundle["child_receipts"][extra] = extra_row["receipts"][0]

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "dispatch-operation-set-mismatch" in result["problems"]
    assert "dispatch-operation-receipt-bijection" in result["problems"]


def test_claimed_operation_cannot_be_reused():
    bundle = demo_bundle()
    bundle["assessment"][0]["operations"].append("op-use-a-P0-u-sw-0")

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "dispatch-operation-reused op-use-a-P0-u-sw-0" in result["problems"]


def test_malformed_accounting_shape_fails_without_raising():
    bundle = demo_bundle()
    bundle["accounting"]["tool_queries"] = []

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "bundle-shape-invalid accounting.tool_queries" in result["problems"]


def test_unknown_history_tokens_are_reported_as_unknown():
    bundle = demo_bundle()
    bundle["freeze"]["policy_identities"]["P1"]["history_tokens"] = "unknown"
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])
    result = M4.verify_bundle(bundle)
    assert result["status"] == "pass", result["problems"]
    assert result["recomputed"]["history_tokens"] == "unknown"


def test_m4_refuses_p2_history_substitution_and_stale_digest():
    bundle = demo_bundle()
    empty = []
    bundle["freeze"]["history_reference"]["P2"] = empty
    contract = bundle["freeze"]["arm_contracts"]["P2"]
    contract["history"] = empty
    contract["history_digest"] = _digest("stale-history")
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "p2-history-not-permitted" in result["problems"]
    assert "p2-history-digest-mismatch" in result["problems"]


def test_m4_malformed_dispatch_rows_return_structured_failure():
    bundle = demo_bundle()
    bundle["dispatch_ledger"] = [None]

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "malformed-dispatch-ledger-entry" in result["problems"]


def test_m4_malformed_use_rows_return_structured_failure():
    bundle = demo_bundle()
    bundle["use_records"] = [None]

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "malformed-use-record" in result["problems"]


def test_m4_allows_retry_dispatches_with_one_terminal_receipt():
    bundle = demo_bundle()
    original = next(
        entry for entry in bundle["dispatch_ledger"]
        if entry["operation_id"].startswith("op-candidate-"))
    retry = copy.deepcopy(original)
    retry["dispatch_id"] = "dispatch-retry-before-terminal"
    retry["evidence_digest"] = "f" * 64
    bundle["dispatch_ledger"].append(retry)
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])
    bundle["accounting"]["model_dispatches"]["measured"] = 14

    result = M4.verify_bundle(bundle)

    assert result["status"] == "pass", result["problems"]
    assert result["recomputed"]["model_calls"] == 14


def test_m4_tie_rule_is_derived_from_frozen_metric():
    bundle = demo_bundle()
    bundle["freeze"]["metric_rule"] = {
        "kind": "mean-quality", "margin": 2.0, "tie": "none"}
    bundle["freeze"]["freeze_digest"] = M4.freeze_digest(bundle["freeze"])
    bundle["claimed"]["winner"] = "none"

    result = M4.verify_bundle(bundle)

    assert result["status"] == "pass", result["problems"]
    assert result["recomputed"]["comparison"]["winner"] is None


def test_m4_malformed_complete_schema_returns_specific_structured_failure():
    bundle = demo_bundle()
    bundle["protocol"] = []
    bundle["authority"] = []
    bundle["software"] = []

    result = M4.verify_bundle(bundle)

    assert result["status"] == "fail"
    assert "bundle-shape-invalid protocol" in result["problems"]
    assert "bundle-shape-invalid authority" in result["problems"]
    assert "bundle-shape-invalid software" in result["problems"]
