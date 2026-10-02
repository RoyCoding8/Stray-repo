from __future__ import annotations

import copy
import inspect
import json

import pytest

from experiments.ad01 import frontier
from experiments.ad01 import live_construct as live
from experiments.ad01 import offline_recompute as m4
from scripts import invl02_live as driver
from settlement.gateway import GatewayError, GatewayErrorKind, ModelResponse, Usage
from test_m4_offline_recompute import _digest, demo_bundle
from test_r123_gates import (
    _fake_e12_bundle,
    _write_authoritative_ledger as _write_unbound_authoritative_ledger,
)


def _output_task_ids_by_split() -> dict:
    """The output study's task ids, read from the generator.

    These were literal `rule-qual-0011` / `rule-audit-0023` strings. The
    worlds made their ids opaque so a public id no longer names its own
    seed, and a test that restates the old format asserts against an id the
    study can no longer produce - it fails for a reason that has nothing to
    do with what it is checking.
    """
    from experiments.ad01 import boolean_rule

    return {split: boolean_rule.make_task(split, seed)["task_id"]
            for split, seed in live.OUTPUT_TASKS.items()}


def _output_task_ids() -> set:
    return set(_output_task_ids_by_split().values())


def _verify_output(result, tmp_path):
    private = json.loads(
        (tmp_path / "scorer-private.json").read_text())
    return m4.verify_bundle(result, private)


def _write_authoritative_ledger(out):
    _write_unbound_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    ledger.update({
        "study": e12["study"],
        "study_root": e12["study_root"],
        "freeze_digest": e12["freeze_digest"],
    })
    path.write_text(json.dumps(ledger) + "\n")


def _attach_durable_receipts(result):
    by_operation = {
        receipt["operation_id"]: receipt
        for receipt in result["candidate_view"]["durable_receipts"]}
    for dispatch in result["candidate_view"]["dispatches"]:
        receipt = by_operation.get(dispatch["operation_id"])
        if receipt is not None:
            dispatch["durable_receipt"] = copy.deepcopy(receipt)


def _durable_receipt(entry):
    usage = copy.deepcopy(entry["usage"])
    usage.update(charge_units=None, charge_scale="unknown", billed=False)
    return {
        "operation_id": entry["operation_id"],
        "receipt_identity": entry["receipt_identity"],
        "outcome": "success",
        "source_digest": entry["source_digest"],
        "artifact_digest": entry["artifact_digest"],
        "input_digest": entry["input_digest"],
        "result_digest": entry["result_digest"],
        "dispatch_evidence_digest": (
            entry.get("dispatch_evidence_digest") or entry["evidence_digest"]),
        "dispatch_state": "observed",
        "reconcile_state": "none",
        "settled": True,
        "usage": usage,
        "measurement_status": "unknown",
    }


def test_m4_rejects_coordinated_observation_and_claim_tamper():
    bundle = demo_bundle()
    record = next(row for row in bundle["use_records"]
                  if row["record_id"] == "a-P2-u-sw-0")
    receipt = bundle["child_receipts"][record["operation_ids"][0]]
    record["observed"] = "other"
    record["claimed_verdict"] = "failed"
    bundle["claimed"]["winner"] = "P0"
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "scored-observation-mismatch a-P2-u-sw-0" in result["problems"]
    assert receipt["details"]["raw_payload"]["result"]["observed"] == "reduce-3"


def test_m4_rejects_p0_derived_expected_label_tamper():
    bundle = demo_bundle()
    task = bundle["freeze"]["tasks"]["u-sw-0"]
    task.update({"split": "qual", "seed": 11, "expected": "other"})
    bundle["freeze"]["freeze_digest"] = m4.freeze_digest(bundle["freeze"])
    for record in bundle["use_records"]:
        if record["task_id"] == "u-sw-0":
            record["claimed_verdict"] = (
                "preserved" if record["observed"] == task["expected"]
                else "failed")
    bundle["claimed"]["winner"] = "P1"
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(problem.startswith("frozen-task-label-mismatch u-sw-0")
               for problem in result["problems"])


def test_m4_rejects_aggregate_only_p1_history():
    bundle = demo_bundle()
    empty_digest = m4.source_digest(m4.canonical([]))
    bundle["freeze"]["arm_contracts"] = {
        "P0": {"kind": "fixed-incumbent", "source": "p0",
               "source_digest": m4.source_digest("p0")},
        "P1": {"history_digest": empty_digest, "history_tokens": 0},
        "P2": {"history_digest": empty_digest, "history_tokens": 0},
    }
    bundle["freeze"]["freeze_digest"] = m4.freeze_digest(bundle["freeze"])
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "history-contract-missing P1" in result["problems"]


def test_e3_durable_child_operation_must_be_settled():
    receipt = {
        "operation_id": "e3-op",
        "receipt_identity": "durable:e3-op",
        "outcome": "success",
        "source_digest": "a" * 64,
        "artifact_digest": "b" * 64,
        "input_digest": "c" * 64,
        "result_digest": driver._digest({}),
        "package_digest": "d" * 64,
        "parent_digest": "e" * 64,
        "round": 1,
        "dispatch_evidence_digest": "f" * 64,
        "details": {"raw_payload": {"result": {}}},
    }

    class Authority:
        def read(self, operation_id):
            return {
                "operation": {
                    "id": operation_id, "dispatch_state": "observed",
                    "reconcile_state": "none", "settled": False,
                },
                "receipts": [{
                    "receipt_identity": receipt["receipt_identity"],
                    "operation_id": operation_id,
                    "outcome": "success",
                    "content": {key: receipt[key] for key in (
                        "source_digest", "artifact_digest", "input_digest",
                        "result_digest", "package_digest", "parent_digest",
                        "round", "dispatch_evidence_digest")},
                }],
                "receipt_conflicts": [],
            }

    matched, reason = driver._durable_e3_receipt(Authority(), receipt)

    assert matched is False
    assert "unsettled" in reason


def test_e3_requires_durable_usable_result_equal_to_local_child_result():
    local_result = {"status": "usable", "value": 3}
    receipt = {
        "operation_id": "e3-op",
        "receipt_identity": "durable:e3-op",
        "outcome": "success",
        "source_digest": "a" * 64,
        "artifact_digest": "b" * 64,
        "input_digest": "c" * 64,
        "result_digest": driver._digest(local_result),
        "package_digest": "d" * 64,
        "parent_digest": "e" * 64,
        "round": 1,
        "dispatch_evidence_digest": "f" * 64,
        "details": {"raw_payload": {"result": local_result}},
    }

    class Authority:
        def __init__(self, durable_result):
            self.durable_result = durable_result

        def read(self, operation_id):
            content = {key: receipt[key] for key in (
                "source_digest", "artifact_digest", "input_digest",
                "result_digest", "package_digest", "parent_digest",
                "round", "dispatch_evidence_digest")}
            if self.durable_result is not None:
                content["result"] = self.durable_result
            return {
                "operation": {
                    "id": operation_id, "dispatch_state": "observed",
                    "reconcile_state": "none", "settled": True,
                },
                "receipts": [{
                    "receipt_identity": receipt["receipt_identity"],
                    "operation_id": operation_id,
                    "outcome": "success",
                    "content": content,
                }],
                "receipt_conflicts": [],
            }

    matched, reason = driver._durable_e3_receipt(Authority(None), receipt)
    assert matched is False
    assert "usable result" in reason

    matched, reason = driver._durable_e3_receipt(
        Authority({"status": "usable", "value": 4}), receipt)
    assert matched is False
    assert "does not match" in reason

    matched, reason = driver._durable_e3_receipt(
        Authority(local_result), receipt)
    assert matched is True
    assert "match" in reason


def test_e0_and_e12_freeze_exact_route(tmp_path):
    assert driver.freeze_e0(tmp_path / "e0")["route"] == live.OUTPUT_ROUTE
    assert driver.freeze_e12(tmp_path / "e12")["route"] == live.OUTPUT_ROUTE


def test_e0_and_e12_freezes_pin_execution_source_identity(tmp_path):
    for name, freeze in (
            ("e0", driver.freeze_e0(tmp_path / "e0")),
            ("e12", driver.freeze_e12(tmp_path / "e12"))):
        assert set(freeze["code_digests"]) == set(driver.LIVE_CODE_PATHS)
        assert set(freeze["source_digests"]) == set(driver.LIVE_SOURCE_PATHS)
        assert freeze["source_identity"] == driver._live_source_identity(freeze)
        assert freeze["run_id"]
        assert freeze["protocol"].endswith("-v1")


@pytest.mark.parametrize("study", ["e0", "e12"])
def test_live_freeze_rejects_execution_source_drift_before_authority(
        tmp_path, monkeypatch, study):
    freeze = (driver.freeze_e0(tmp_path) if study == "e0"
              else driver.freeze_e12(tmp_path))
    freeze["source_digests"]["experiments/ad01/boolean_rule.py"] = "0" * 64
    freeze["source_identity"] = driver._live_source_identity(freeze)
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    (tmp_path / "freeze.json").write_text(json.dumps(freeze))
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model", lambda: freeze["route"]["requested_model"])
    authority_calls = []
    monkeypatch.setattr(
        driver, "_authorize",
        lambda *args, **kwargs: authority_calls.append(True))

    runner = driver.run_e0 if study == "e0" else driver.run_e12
    with pytest.raises(ValueError, match="source.*digest"):
        runner("unavailable", tmp_path)
    assert authority_calls == []


def test_same_route_stale_preflight_refuses_before_e0_authority(
        tmp_path, monkeypatch):
    freeze = driver.freeze_e0(tmp_path)
    (tmp_path / "preflight.json").write_text(json.dumps({
        "route": freeze["route"],
        "route_digest": driver._digest(freeze["route"]),
    }))
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model", lambda: freeze["route"]["requested_model"])
    authority_calls = []
    monkeypatch.setattr(
        driver, "_authorize",
        lambda *args, **kwargs: authority_calls.append(True))

    result = driver.run_e0("unavailable", tmp_path)

    assert result["status"] == "unavailable"
    assert "preflight" in result["reason"]
    assert authority_calls == []


def test_route_preflight_binds_frozen_run_and_source_identity(tmp_path):
    freeze = driver.freeze_e0(tmp_path)

    class Gateway:
        def preflight_route(self, route):
            return dict(route)

    result = driver.preflight_route(tmp_path, gateway=Gateway())
    record = json.loads((tmp_path / "preflight.json").read_text())

    assert result["route"] == freeze["route"]
    assert record["study_root"] == freeze["study_root"]
    assert record["protocol"] == freeze["protocol"]
    assert record["freeze_digest"] == freeze["freeze_digest"]
    assert record["source_identity"] == freeze["source_identity"]
    assert record["run_id"] == freeze["run_id"]


def test_e12_refuses_history_drift_before_authority(tmp_path, monkeypatch):
    freeze = driver.freeze_e12(tmp_path)
    (tmp_path / "preflight.json").write_text(json.dumps(
        driver._preflight_record(freeze, freeze["route"])))
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model", lambda: freeze["route"]["requested_model"])
    monkeypatch.setattr(
        driver, "_live_route", lambda: dict(freeze["route"]))
    monkeypatch.setattr(
        driver, "_permitted_dev_history", lambda *args: [{"task_id": "drift"}])
    authority_calls = []
    monkeypatch.setattr(
        driver, "_authorize", lambda *args, **kwargs: authority_calls.append(True))

    result = driver.run_e12("unavailable", tmp_path)

    assert result["status"] == "unavailable"
    assert authority_calls == []
    assert "history" in result["reason"]


def test_route_metadata_must_match_before_e0_retention(tmp_path):
    freeze = driver.freeze_e0(tmp_path / "e0")
    route = freeze["route"]

    class Gateway:
        def infer(self, request):
            return ModelResponse(request.operation_id, "{}", {}, Usage(), "stop")

    guard = live.LiveGuard(
        Gateway(), pinned_model=route["requested_model"], ceiling=2,
        expected_route=route)
    record = driver._run_frontier_investigation(
        tmp_path / "frontier.json", freeze, "live", guard=guard,
        model=route["requested_model"])
    assert record["acquisition"]["status"] == "unavailable"


def test_m4_export_uses_m4_freeze_identity_and_preserves_e12_digest(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    source = json.loads((out / "e12-run.json").read_text())

    bundle = driver.export_m4_bundle(out)

    assert bundle["freeze_digest"] == bundle["freeze"]["freeze_digest"]
    assert bundle["source_e12_freeze_digest"] == source["freeze_digest"]
    verified = m4.verify_bundle(bundle)
    assert verified["status"] == "pass", verified["problems"]


def test_m4_software_quality_is_derived_from_frozen_task(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    bundle["software"]["use_records"][0]["expected"] = "wrong"
    bundle["software"]["outcomes"][0]["expected"] = "wrong"

    verified = m4.verify_bundle(bundle)

    assert verified["status"] == "fail"
    assert any(problem.startswith("software-frozen-quality-mismatch")
               for problem in verified["problems"])


def test_m4_export_includes_and_verifies_software_use_outcomes(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    freeze = json.loads((out / "freeze.json").read_text())

    bundle = driver.export_m4_bundle(out)
    result = driver.verify_m4_bundle(out)

    assert [row["task_id"] for row in bundle["software"]["use_records"]] == [
        task_id for task_id in freeze["software_tasks"]
        for _ in ("P0", "P1", "P2")]
    assert bundle["software"]["outcomes"] == [
        {"arm": arm, "task_id": task_id, "expected": "preserved",
         "observed": "preserved", "queries": 2}
        for task_id in freeze["software_tasks"]
        for arm in ("P0", "P1", "P2")]
    assert result["status"] == "pass", result["problems"]
    assert result["recomputed"]["software_use_records"] == 6

    bundle["software"]["outcomes"][0]["observed"] = "forged"
    (out / "m4-bundle.json").write_text(json.dumps(bundle) + "\n")
    rejected = driver.verify_m4_bundle(out)
    assert rejected["status"] == "fail"
    assert "software-outcome-mismatch" in rejected["problems"]


def test_m4_export_uses_frozen_metric_rule(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12_path = out / "e12-run.json"
    e12 = json.loads(e12_path.read_text())
    e12["metric_rule"] = {"kind": "mean-quality", "margin": 0.75,
                          "tie": "incumbent"}
    freeze = json.loads((out / "freeze.json").read_text())
    freeze["metric_rule"] = e12["metric_rule"]
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    e12["freeze_digest"] = freeze["freeze_digest"]
    e12["source_identity"] = freeze["source_identity"]
    e12_path.write_text(json.dumps(e12) + "\n")
    (out / "freeze.json").write_text(json.dumps(freeze) + "\n")
    ledger_path = out / "authoritative-operations.json"
    ledger = json.loads(ledger_path.read_text())
    ledger.update({key: e12[key] for key in (
        "protocol", "run_id", "source_identity", "study", "study_root",
        "freeze_digest", "route_digest")})
    ledger_path.write_text(json.dumps(ledger) + "\n")

    bundle = driver.export_m4_bundle(out)

    assert bundle["freeze"]["metric_rule"]["margin"] == 0.75
    assert m4.verify_bundle(bundle)["recomputed"]["comparison"]["winner"] == "P0"


def test_m4_candidate_export_requires_successful_usable_durable_result(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12_path = out / "e12-run.json"
    e12 = json.loads(e12_path.read_text())
    receipt = e12["durable_receipts"][0]
    receipt.update({"outcome": "success", "usable_result": False})
    e12_path.write_text(json.dumps(e12) + "\n")

    with pytest.raises(ValueError, match="successful.*usable"):
        driver.export_m4_bundle(out)


def test_m4_export_requires_explicit_ledger_identity(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    for key in ("study", "study_root", "freeze_digest"):
        ledger.pop(key)
    path.write_text(json.dumps(ledger))

    with pytest.raises(ValueError, match="ledger identity"):
        driver.export_m4_bundle(out)


def test_m4_software_requires_every_frozen_arm_task_membership(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    freeze = json.loads((out / "freeze.json").read_text())
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    op_id = next(
        op_id for op_id, receipt in ledger["child_receipts"].items()
        if receipt.get("arm") == "P2"
        and receipt.get("task_id") in set(freeze["software_tasks"]))
    ledger["operations"].pop(op_id)
    ledger["child_receipts"].pop(op_id)
    path.write_text(json.dumps(ledger))

    with pytest.raises(ValueError, match="software arm/task membership is incomplete"):
        driver.export_m4_bundle(out)


def test_m4_export_rejects_retired_or_relabelled_authoritative_ledger(
        tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    ledger["study"] = "invl02-live-retired"
    ledger["study_root"] = "invl02-live-retired"
    ledger["freeze_digest"] = "0" * 64
    path.write_text(json.dumps(ledger))

    with pytest.raises(ValueError, match="ledger.*identity"):
        driver.export_m4_bundle(out)


def test_m4_export_rejects_local_receipt_identity(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    op_id, row = next(iter(ledger["operations"].items()))
    receipt = row["receipts"][0]
    receipt["receipt_identity"] = "local:%s" % op_id
    receipt["evidence_digest"] = frontier._evidence_identity_digest(receipt)
    ledger["child_receipts"][op_id] = receipt
    path.write_text(json.dumps(ledger))

    with pytest.raises(ValueError, match="local receipt identity"):
        driver.export_m4_bundle(out)


def test_m4_query_accounting_stays_unknown_for_unobserved_child_count(
        tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    for op_id, receipt in ledger["child_receipts"].items():
        result = receipt["details"]["raw_payload"]["result"]
        result["queries"] = None
        receipt["result_digest"] = m4.source_digest(m4.canonical(result))
        receipt["raw_payload_digest"] = m4.source_digest(m4.canonical(
            receipt["details"]["raw_payload"]))
        receipt["evidence_digest"] = frontier._evidence_identity_digest(receipt)
        ledger["operations"][op_id]["receipts"][0] = receipt
    path.write_text(json.dumps(ledger))

    bundle = driver.export_m4_bundle(out)

    assert bundle["accounting"]["tool_queries"]["measured"] == "unknown"
    assert bundle["accounting"]["tool_queries"]["measurement_status"] == (
        "unknown")


def test_m4_export_labels_every_accounting_measurement(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    assert set(bundle["accounting"]) == {
        "model_dispatches", "input_tokens", "output_tokens", "tool_queries",
        "child_compute_ms", "billed_units", "unresolved_exposure",
        "human_interventions"}
    for entry in bundle["accounting"].values():
        assert entry["measurement_status"] in {"measured", "unknown", "unresolved"}
        assert entry["source"]
    assert bundle["accounting"]["human_interventions"] == {
        "measured": "unknown", "measurement_status": "unknown",
        "source": "human-intervention-ledger:absent"}


def test_m4_refuses_missing_explicit_arm(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    del e12["arms"]["P0"]
    (out / "e12-run.json").write_text(json.dumps(e12))
    with pytest.raises(ValueError, match="missing-arm P0"):
        driver.export_m4_bundle(out)


def test_m4_refuses_coherent_candidate_swap():
    bundle = demo_bundle()
    candidates = []
    for record in bundle["use_records"]:
        if record["arm"] not in ("P1", "P2"):
            continue
        predictor = {"observed": record["observed"]}
        candidate = {
            "arm": record["arm"], "task_id": record["task_id"],
            "raw_response": record["observed"],
            "raw_response_digest": m4.source_digest(record["observed"]),
            "predictor": predictor,
            "predictor_digest": m4.source_digest(m4.canonical(predictor)),
            "input_digest": record["input_digest"],
            "prompt_digest": _digest("prompt:%s" % record["record_id"]),
        }
        candidates.append(candidate)
    bundle["candidates"] = candidates
    p1 = next(row for row in candidates
              if row["arm"] == "P1" and row["task_id"] == "u-sw-0")
    p2 = next(row for row in candidates
              if row["arm"] == "P2" and row["task_id"] == "u-sw-0")
    p1["predictor"], p2["predictor"] = p2["predictor"], p1["predictor"]
    p1["predictor_digest"], p2["predictor_digest"] = (
        p2["predictor_digest"], p1["predictor_digest"])
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(problem.startswith("candidate-task-binding-mismatch")
               for problem in result["problems"])


def test_e12_boolean_digest_identity_is_single_text_digest_path():
    legal = json.dumps({"specs": [
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
    ]})

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id, legal,
                {"model": live.OUTPUT_ROUTE["resolved_model"],
                 "endpoint": live.OUTPUT_ROUTE["endpoint"],
                 "provider": live.OUTPUT_ROUTE["provider"],
                 "tier": live.OUTPUT_ROUTE["tier"]},
                Usage(), "stop")

    guard = live.LiveGuard(
        Gateway(), pinned_model=live.OUTPUT_ROUTE["requested_model"],
        ceiling=2, expected_route=live.OUTPUT_ROUTE)
    result = driver.boolean_live_round(
        guard=guard, model=live.OUTPUT_ROUTE["requested_model"],
        arm="P1", split="qual", seed=11, history=[], repairs=1)
    artifact = result["candidate_artifact"]
    dispatch = result["dispatch_ledger"][-1]
    assert artifact["input_digest"] == dispatch["input_digest"]
    assert artifact["prompt_digest"] == dispatch["prompt_digest"]
    assert artifact["raw_response_digest"] == dispatch["response_digest"]
    assert artifact["raw_response_digest"] == live.source_digest(
        artifact["raw_response"])


def test_boolean_round_counts_automatic_retries_as_physical_dispatches():
    legal = json.dumps({"specs": [
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
    ]})

    class Gateway:
        def __init__(self):
            self.calls = 0

        def infer(self, request):
            self.calls += 1
            if self.calls == 1:
                return GatewayError(
                    GatewayErrorKind.TRANSPORT, "retry", True,
                    request.operation_id, Usage())
            return ModelResponse(
                request.operation_id, legal,
                {"model": live.OUTPUT_ROUTE["resolved_model"],
                 "endpoint": live.OUTPUT_ROUTE["endpoint"],
                 "provider": live.OUTPUT_ROUTE["provider"],
                 "tier": live.OUTPUT_ROUTE["tier"]},
                Usage(), "stop")

    gateway = Gateway()
    guard = live.LiveGuard(
        gateway, pinned_model=live.OUTPUT_ROUTE["requested_model"],
        ceiling=4, automatic_retries=1,
        expected_route=live.OUTPUT_ROUTE)
    result = driver.boolean_live_round(
        guard=guard, model=live.OUTPUT_ROUTE["requested_model"],
        arm="P1", split="qual", seed=11, history=[], repairs=1)
    assert result["physical_dispatch_count"] == 2
    assert result["automatic_retry_count"] == 1
    assert result["model_calls"] == 2
    assert len(result["dispatch_ledger"]) == 2


def test_run_e12_marks_m4_export_unavailable_without_authoritative_ledger(
        tmp_path, monkeypatch):
    out = tmp_path / "e12"
    driver.freeze_e12(out)
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(driver, "_authorize", lambda *args, **kwargs: None)
    monkeypatch.setattr(driver, "_live_model",
                        lambda: live.OUTPUT_ROUTE["requested_model"])

    class Guard:
        dispatch_count = 0

        def guard_status(self):
            return {"dispatch_count": 0}

        def finalized_dispatches(self):
            return []

    monkeypatch.setattr(driver, "_guard", lambda *args, **kwargs: Guard())

    store_path = tmp_path / "frontier-store.json"
    store_path.write_text("{}\n")

    def frontier(*args, **kwargs):
        return {"effects_settled": 0, "acquisition": {
            "status": "unavailable", "reason": "test"},
            "store_path": str(store_path)}

    monkeypatch.setattr(driver, "_run_frontier_investigation", frontier)

    def boolean(*, arm, split, seed, **kwargs):
        task_id = "rule-%s-%04d" % (split, seed)
        predictor = {"specs": []}
        raw_response = json.dumps(predictor, sort_keys=True)
        artifact = {
            "arm": arm, "task_id": task_id, "raw_response": raw_response,
            "raw_response_digest": m4.source_digest(raw_response),
            "predictor": predictor,
            "predictor_digest": m4.source_digest(m4.canonical(predictor)),
            "input_digest": m4.source_digest("input:" + task_id),
            "prompt_digest": m4.source_digest("prompt:" + task_id),
        }
        return {"task_id": task_id, "split": split, "seed": seed,
                "queries": 8, "model_calls": 0, "failed_attempts": 0,
                "history_entries": 0 if arm == "P1" else 2,
                "history_digest": m4.source_digest(m4.canonical(
                    [] if arm == "P1" else live.output_permitted_history())),
                "predictor_digest": artifact["predictor_digest"],
                "predictor_specs": [], "predictor_tables": [],
                "target_tables": [], "candidate_artifact": artifact,
                "dispatch_ledger": []}

    monkeypatch.setattr(driver, "boolean_live_round", boolean)
    result = driver.run_e12("unused", out)
    assert result["m4_export"]["status"] == "unavailable"
    assert not (out / "authoritative-operations.json").exists()
    with pytest.raises(ValueError, match="authoritative operation ledger"):
        driver.export_m4_bundle(out)


def test_e0_is_unavailable_before_dispatch_without_durable_authority(
        tmp_path, monkeypatch):
    freeze = driver.freeze_e0(tmp_path)
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model", lambda: freeze["route"]["requested_model"])
    monkeypatch.setattr(driver, "_live_route", lambda: dict(freeze["route"]))
    monkeypatch.setattr(driver, "_authorize", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        driver, "_guard",
        lambda *args, **kwargs: pytest.fail("guard was constructed"))
    result = driver.run_e0("unavailable", tmp_path)
    assert result["status"] == "unavailable"
    assert result["live"]["model_calls"] == 0


def test_e12_is_unavailable_before_dispatch_without_durable_authority(
        tmp_path, monkeypatch):
    freeze = driver.freeze_e12(tmp_path)
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model", lambda: freeze["route"]["requested_model"])
    monkeypatch.setattr(driver, "_live_route", lambda: dict(freeze["route"]))
    monkeypatch.setattr(driver, "_authorize", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        driver, "_guard",
        lambda *args, **kwargs: pytest.fail("guard was constructed"))
    result = driver.run_e12("unavailable", tmp_path)
    assert result["status"] == "unavailable"
    assert result["model_total"] == 0
    assert all(arm["status"] == "unavailable"
               for arm in result["arms"].values())


def test_output_freeze_declares_p0_and_seals_task_identities(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    assert freeze["arms"] == ["P0", "P1", "P2"]
    assert freeze["p0_incumbent"]["kind"] == "fixed-incumbent"
    assert set(freeze["p0_incumbent"]["task_seals"]) == _output_task_ids()


@pytest.mark.parametrize("round_value", [None, 0, 2, "1", True])
def test_output_run_refuses_missing_or_mismatched_output_round(
        tmp_path, round_value):
    from test_output_evidence import _OutputGateway, _responses

    freeze = driver.freeze_output(tmp_path)
    if round_value is None:
        freeze.pop("round")
    else:
        freeze["round"] = round_value
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    (tmp_path / "freeze.json").write_text(json.dumps(freeze))
    gateway = _OutputGateway(_responses(), freeze["route"])

    with pytest.raises(ValueError, match="output round identity"):
        driver.run_output(
            tmp_path, gateway=gateway,
            model=freeze["route"]["requested_model"])
    assert gateway.requests == []


def test_output_run_records_p0_control_without_model_dispatch(tmp_path):
    from test_output_evidence import _OutputGateway, _responses

    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    controls = result["candidate_view"]["incumbent_control"]
    assert [row["arm"] for row in controls] == ["P0", "P0"]
    assert {row["task_id"] for row in controls} == _output_task_ids()
    assert all(row["model_calls"] == 0 for row in controls)
    assert {row["arm"] for row in result["candidate_view"]["dispatches"]} == {
        "P1", "P2"}
    accepted = [row for row in result["candidate_view"]["dispatches"]
                if row["parse_outcome"] == "accepted"]
    assert all(len(row["source_digest"]) == 64 for row in accepted)
    assert all(len(row["artifact_digest"]) == 64 for row in accepted)
    private = json.loads((tmp_path / "scorer-private.json").read_text())
    assert {row["arm"] for row in private["scores"]} == {"P0", "P1", "P2"}


@pytest.mark.parametrize("missing", ["code_digests", "source_digests", "path"])
def test_output_run_refuses_missing_frozen_identity_before_dispatch(
        tmp_path, missing):
    from test_output_evidence import _OutputGateway, _responses

    freeze = driver.freeze_output(tmp_path)
    if missing == "code_digests":
        freeze.pop("code_digests")
    elif missing == "source_digests":
        freeze.pop("source_digests")
    else:
        freeze["code_digests"].pop("src/settlement/gateway_http.py")
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    (tmp_path / "freeze.json").write_text(json.dumps(freeze))
    gateway = _OutputGateway(_responses(), freeze["route"])
    with pytest.raises(ValueError, match="digest paths"):
        driver.run_output(
            tmp_path, gateway=gateway,
            model=freeze["route"]["requested_model"])
    assert gateway.requests == []


def test_output_live_path_requires_broker_and_does_not_fallback(tmp_path,
                                                                  monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(driver, "_live_model",
                        lambda: freeze["route"]["requested_model"])

    class Gateway:
        def __init__(self):
            self.calls = 0

        def infer(self, request):
            self.calls += 1
            raise AssertionError("gateway was called without durable broker")

    gateway = Gateway()
    monkeypatch.setattr(driver, "_live_gateway", lambda route: gateway)
    monkeypatch.setattr(
        driver, "_authorize",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("durable broker unavailable")))
    source = inspect.getsource(driver.run_output_live)
    durable_source = inspect.getsource(driver._DurableBrokerOutput)
    assert "broker" in source.lower()
    assert "broker.ensure_operation" in durable_source
    assert "store.operation_receipts" in durable_source
    assert "return run_output(" not in source
    assert "gateway.infer" not in source
    result = driver.run_output_live("unavailable", tmp_path)
    assert result["status"] == "unavailable"
    assert gateway.calls == 0


def test_output_live_refuses_missing_preflight_before_authority(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(driver, "_live_model",
                        lambda: freeze["route"]["requested_model"])
    authority_calls = []
    monkeypatch.setattr(
        driver, "_authorize", lambda *args, **kwargs: authority_calls.append(True))

    result = driver.run_output_live("unavailable", tmp_path)

    assert result["status"] == "unavailable"
    assert authority_calls == []
    assert "preflight" in result["reason"]


def test_output_run_rejects_changed_p0_task_seal(tmp_path):
    from test_output_evidence import _OutputGateway, _responses

    freeze = driver.freeze_output(tmp_path)
    qual_id = _output_task_ids_by_split()["qual"]
    freeze["p0_incumbent"]["task_seals"][qual_id]["seed"] = 12
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    (tmp_path / "freeze.json").write_text(json.dumps(freeze))
    with pytest.raises(ValueError, match="P0 task seal"):
        driver.run_output(
            tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
            model=freeze["route"]["requested_model"])


def test_verify_output_rejects_missing_or_substituted_p0(tmp_path):
    from test_output_evidence import _OutputGateway, _responses

    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    missing = copy.deepcopy(result)
    missing["candidate_view"]["incumbent_control"] = []
    assert _verify_output(missing, tmp_path)["status"] == "fail"
    substituted = copy.deepcopy(result)
    control = substituted["candidate_view"]["incumbent_control"][0]
    control["arm"] = "P1"
    assert _verify_output(substituted, tmp_path)["status"] == "fail"


def test_verify_output_requires_durable_receipt_for_failed_dispatch(tmp_path):
    from test_output_evidence import _OutputGateway, _responses

    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    failed = next(entry for entry in result["candidate_view"]["dispatches"]
                  if entry["parse_outcome"] == "parse-failed")
    result["candidate_view"]["durable_receipts"] = [
        _durable_receipt(entry)
        for entry in result["candidate_view"]["dispatches"]
        if entry is not failed]
    denied = _verify_output(result, tmp_path)
    assert denied["status"] == "fail"
    assert "missing-durable-receipt %s" % failed[
        "operation_id"] in denied["problems"]

    receipt = _durable_receipt(failed)
    result["candidate_view"]["durable_receipts"].append(receipt)
    _attach_durable_receipts(result)
    assert _verify_output(result, tmp_path)["status"] == "pass"
    receipt["input_digest"] = "f" * 64
    verified = _verify_output(result, tmp_path)
    assert verified["status"] == "fail"
    assert "durable-receipt-lineage-mismatch %s" % failed[
        "operation_id"] in verified["problems"]


def test_verify_output_keeps_route_refused_dispatch_attributable(tmp_path):
    from test_output_evidence import (
        _legal_text, _OutputGateway, _responses, _route_response,
    )

    freeze = driver.freeze_output(tmp_path)
    responses = _responses()
    responses[0] = _route_response(
        _legal_text("qual", 11), model="openrouter/other:free")
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(responses, freeze["route"]),
        model=freeze["route"]["requested_model"])
    refused = result["candidate_view"]["dispatches"][0]
    assert refused["parse_outcome"] == "route-refused"

    denied = _verify_output(result, tmp_path)
    assert denied["status"] == "fail"
    assert denied["recomputed"]["accepted_candidates"] == 0
    assert "missing-durable-receipt %s" % refused[
        "operation_id"] in denied["problems"]

    result["candidate_view"]["durable_receipts"] = [
        _durable_receipt(refused)]
    _attach_durable_receipts(result)
    verified = _verify_output(result, tmp_path)
    assert verified["status"] == "fail"
    assert verified["recomputed"]["accepted_candidates"] == 0
    assert "missing-durable-receipt %s" % refused[
        "operation_id"] not in verified["problems"]


def test_verify_output_rejects_repair_after_accepted_response(tmp_path):
    from test_output_evidence import _legal_text, _OutputGateway, _responses

    freeze = driver.freeze_output(tmp_path)
    gateway = _OutputGateway(_responses(), freeze["route"])
    result = driver.run_output(
        tmp_path, gateway=gateway, model=freeze["route"]["requested_model"])
    first = next(entry for entry in result["candidate_view"]["dispatches"]
                 if entry["parse_outcome"] == "accepted"
                 and entry["attempt"] == 1)
    # The task id is an HMAC over its split and seed, so it does not carry
    # the seed. Only the producer's mapping turns it back into a split.
    split, seed = next((split, seed) for split, seed in live.OUTPUT_TASKS.items()
                       if m4._task_id_for(split, seed) == first["task_id"])
    _task, session = driver._output_public_task(split, seed)
    history = [] if first["arm"] == "P1" else live.output_permitted_history()
    prompt = live.render_output_prompt(session.model_input(), history, 2)
    operation_id = live.output_operation_id(
        first["arm"], split, seed, 2, round_run_id=freeze["run_id"])
    details = copy.deepcopy(first["details"])
    details["raw_payload"] = {"raw_prompt": prompt, "raw_response": "not json"}
    repair = frontier.make_evidence_record(
        "gateway-dispatch", operation_id, "unknown", attempt=2,
        arm=first["arm"], task_id=first["task_id"],
        input_digest=m4.source_digest(prompt), result_digest=None,
        details=details)
    for key in (
            "requested_model", "returned_model", "endpoint", "provider",
            "tier", "requested_output_cap", "response_digest",
            "prompt_digest", "raw_prompt", "raw_response", "stop_reason",
            "usage", "billed", "charge_units", "route_error"):
        if key in first:
            repair[key] = copy.deepcopy(first[key])
    repair.update({
        "attempt": 2, "parse_outcome": "parse-failed",
        "raw_prompt": prompt, "prompt_digest": m4.source_digest(prompt),
        "raw_response": "not json", "response_digest": m4.source_digest(
            "not json"), "accepted_candidate_digest": None,
    })
    result["candidate_view"]["dispatches"].append(repair)
    result["candidate_view"]["dispatches"].sort(
        key=lambda row: (row["arm"], row["task_id"], row["attempt"]))
    verified = _verify_output(result, tmp_path)
    assert verified["status"] == "fail"
    assert "repair-after-accepted %s-%s" % (
        first["arm"], split) in verified["problems"]


def test_p2_frontier_construction_prompt_contains_permitted_history(tmp_path):
    from experiments.ad01 import live_construct as live

    class Guard:
        pinned_model = "test-model"

        def __init__(self):
            self.prompts = []

        def infer(self, request, *, evidence=None):
            self.prompts.append(request.messages[0]["content"])
            raise RuntimeError("stop after prompt capture")

        def finalized_dispatches(self):
            return []

    freeze = driver.freeze_e12(tmp_path)
    permitted = driver._permitted_dev_history([3, 7])
    guard = Guard()
    driver._run_frontier_investigation(
        tmp_path / "frontier-P2.json", freeze, "P2", guard=guard,
        model="test-model", history=permitted)

    assert len(guard.prompts) == 1
    assert driver._canonical(permitted) in guard.prompts[0]
    assert "Permitted development history" in guard.prompts[0]


def test_preflight_refusal_writes_standalone_evidence(tmp_path):
    from settlement.gateway import GatewayError, GatewayErrorKind

    class Gateway:
        def preflight_route(self, route):
            return GatewayError(
                GatewayErrorKind.TRANSPORT, "route absent", False,
                "preflight-test", None)

    freeze = driver.freeze_e0(tmp_path)
    with pytest.raises(ValueError, match="preflight refused"):
        driver.preflight_route(tmp_path, gateway=Gateway())
    refusal = json.loads((tmp_path / "preflight-refusal.json").read_text())
    assert refusal["route"] == live.OUTPUT_ROUTE
    assert refusal["freeze_digest"] == freeze["freeze_digest"]
    assert refusal["run_id"] == freeze["run_id"]
    assert refusal["reason"] == "route absent"
    assert not (tmp_path / "preflight.json").exists()


def test_probe_cli_is_nonzero_for_refusal(monkeypatch, capsys):
    monkeypatch.setattr(driver, "probe", lambda *args, **kwargs: {
        "probe": "refused", "reason": "no grant"})
    assert driver.main(["probe", "--out", "unused"]) == 1
    assert "probe refused" in capsys.readouterr().out


def test_m4_cannot_coordinate_candidate_with_forged_task_input(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    candidate = next(row for row in bundle["candidates"]
                      if row["arm"] == "P1")
    candidate["input_digest"] = "f" * 64
    bundle["freeze"]["arm_contracts"]["P1"]["input_bindings"][
        candidate["task_id"]] = candidate["input_digest"]
    bundle["freeze"]["freeze_digest"] = m4.freeze_digest(bundle["freeze"])

    verified = m4.verify_bundle(bundle)

    assert verified["status"] == "fail"
    assert any(problem.startswith("candidate-input-not-frozen")
               for problem in verified["problems"])


def test_m4_cannot_coordinate_candidate_with_unbound_raw_response(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    candidate = next(row for row in bundle["candidates"]
                      if row["arm"] == "P1")
    candidate["raw_response"] = "forged-response"
    candidate["raw_response_digest"] = m4.source_digest(
        candidate["raw_response"])

    verified = m4.verify_bundle(bundle)

    assert verified["status"] == "fail"
    assert any(problem.startswith("candidate-raw-response-recompute-failed")
               for problem in verified["problems"])


def test_m4_rejects_dispatch_operation_outside_authoritative_ledger(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    bundle["dispatch_ledger"][0]["operation_id"] = "forged-operation"

    verified = m4.verify_bundle(bundle)

    assert verified["status"] == "fail"
    assert "dispatch-operation-unknown forged-operation" in verified[
        "problems"]


def test_m4_export_requires_complete_authoritative_ledger_identity(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    ledger.pop("protocol")
    path.write_text(json.dumps(ledger) + "\n")

    with pytest.raises(ValueError, match="ledger identity"):
        driver.export_m4_bundle(out)


def test_m4_export_rejects_task_membership_outside_frozen_protocol(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    path = out / "e12-run.json"
    e12 = json.loads(path.read_text())
    e12["held"].append({"split": "qual", "seed": 11})
    path.write_text(json.dumps(e12) + "\n")

    with pytest.raises(ValueError, match="held.*protocol"):
        driver.export_m4_bundle(out)
