from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live
from experiments.ad01 import offline_recompute
from scripts import invl02_live as driver


def _run_identity(freeze):
    return {
        "protocol": freeze["protocol"],
        "run_id": freeze["run_id"],
        "source_identity": freeze["source_identity"],
        "study": freeze["study"],
        "study_root": freeze["study_root"],
        "freeze_digest": freeze["freeze_digest"],
        "route": dict(freeze["route"]),
        "route_digest": driver._digest(freeze["route"]),
    }


def _synthetic_ledger(e12, operations, child_receipts):
    return {
        **_run_identity(e12),
        "authority": "synthetic-test-fixture",
        "authoritative": False,
        "operations": operations,
        "child_receipts": child_receipts,
    }


def _synthetic_e12(tmp_path):
    out = tmp_path / "e12"
    out.mkdir()
    freeze = driver.freeze_e12(out)
    e12 = {
        **_run_identity(freeze),
        "status": "incomplete",
        "execution_status": "incomplete",
        "metric_rule": dict(freeze["metric_rule"]),
        "dispatch_ledger": [],
        "durable_receipts": [],
        "held": [{"split": "qual", "seed": 11},
                 {"split": "audit", "seed": 23}],
        "arms": {
            "P0": {"status": "available",
                   "booleans": [driver._run_p0_boolean("qual", 11),
                                driver._run_p0_boolean("audit", 23)]},
            "P1": {"status": "unavailable", "reason": "synthetic fixture"},
            "P2": {"status": "unavailable", "reason": "synthetic fixture"},
        },
    }
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    return out


def _complete_receipt(op_id, arm, task_id, source_digest, result):
    return frontier.make_evidence_record(
        "m4-observation", op_id, "success", arm=arm, task_id=task_id,
        receipt_identity="test:%s" % op_id,
        source_digest=source_digest, artifact_digest=source_digest,
        input_digest=driver._digest("input:%s" % op_id),
        result_digest=driver._digest(result),
        details={"raw_payload": {
            "result": result,
            "usage": {"input_tokens": 1, "output_tokens": 1,
                      "charge_units": 0, "charge_scale": 1_000,
                      "billed": False}}})


def _write_synthetic_authority(out, e12):
    freeze = json.loads((out / "freeze.json").read_text())
    p0 = freeze["p0_incumbent"]
    receipts = {}

    def add(op_id, arm, task_id, source_digest, result):
        receipts[op_id] = _complete_receipt(
            op_id, arm, task_id, source_digest, result)

    for index, task_id in enumerate(freeze["software_tasks"]):
        for arm in ("P0", "P1", "P2"):
            op_id = ("op-d-sw-%d" % index if arm == "P0"
                     else "op-use-d-sw-%s-%d" % (arm, index))
            add(op_id, arm, task_id, p0["source_digest"],
                {"observed": "preserved", "queries": 2})
    for held in e12["held"]:
        split = held["split"]
        seed = int(held["seed"])
        task_id = rules.make_task(split, seed)["task_id"]
        prefix = "a" if split == "qual" else "t"
        boolean = next(
            row for row in e12["arms"]["P0"]["booleans"]
            if row["task_id"] == task_id)
        observed = json.dumps(boolean["predictor_tables"],
                              sort_keys=True, separators=(",", ":"))
        op_id = "op-a-0" if prefix == "a" else "op-t-0"
        result = {"observed": observed, "queries": boolean["queries"]}
        add(op_id, "P0", task_id, p0["source_digest"], result)
        add("op-use-%s-P0-%s" % (prefix, task_id), "P0", task_id,
            p0["source_digest"], result)
    for arm in ("P1", "P2"):
        source = live.source_digest(json.dumps(
            {"arm": arm, "predictor": [], "permitted": ""},
            sort_keys=True, separators=(",", ":")))
        add("op-construct-%s-init" % arm, arm, "construct-%s" % arm,
            source, {"status": "synthetic fixture"})
        for held in e12["held"]:
            split = held["split"]
            seed = int(held["seed"])
            task_id = rules.make_task(split, seed)["task_id"]
            prefix = "a" if split == "qual" else "t"
            add("op-use-%s-%s-%s" % (prefix, arm, task_id), arm, task_id,
                source, {"observed": "synthetic fixture", "queries": 0})

    operations = {
        op_id: {"operation_id": op_id, "receipts": [receipt],
                "receipt_conflicts": []}
        for op_id, receipt in receipts.items()
    }
    child_receipts = {op_id: dict(receipt) for op_id, receipt in receipts.items()}
    ledger = _synthetic_ledger(e12, operations, child_receipts)
    (out / "authoritative-operations.json").write_text(
        json.dumps(ledger) + "\n")
    e12["durable_receipts"] = [dict(receipt) for receipt in receipts.values()]
    e12["dispatch_ledger"] = [
        {"operation_id": op_id, "arm": receipt["arm"],
         "task_id": receipt["task_id"], "attempt": 1,
         "dispatch_id": "test-dispatch:%s" % op_id,
         "evidence_digest": receipt.get("dispatch_evidence_digest")
         or receipt["evidence_digest"]}
        for op_id, receipt in receipts.items()
        if (receipt["task_id"] in set(freeze["software_tasks"])
                or receipt["task_id"] in {"construct-P1", "construct-P2"})
    ]
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    return operations, child_receipts


def _bound_acquired_store(path, arm="P1"):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id,
                json.dumps({"entry": channel.IMPROVE_LOW_SOURCE}),
                {}, Usage(), "stop")

    store = frontier.create_store(
        path, namespace=frontier.NAMESPACE,
        mission={"objective": "m", "environments": [{"split": "dev",
                                                     "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    base = channel.make_control("low")
    store.bind_active(base)
    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    operation_id = "op-acquire-%s" % arm
    raw_prompt = "construct"
    response = guard.infer(ModelRequest(
        model="test-model", messages=({"role": "user", "content": raw_prompt},),
        max_output_tokens=8, deadline_ms=1000, operation_id=operation_id),
        evidence={"arm": arm, "task": rules.make_task("dev", 4)["task_id"],
                  "attempt": 1, "raw_prompt": raw_prompt})
    dispatch = guard.provenance(operation_id)
    package = live.parse_and_build_live_package(
        dict(base), response.text, "acquired-%s-r1" % arm,
        dispatch=dispatch)
    store.record_evidence(dispatch)
    dispatch = guard.finalize_evidence(
        operation_id, parse_outcome="accepted",
        accepted_candidate_digest=package["package_digest"],
        parsed_source_digest=package["imp_digest"],
        package_digest=package["package_digest"],
        parent_digest=package["parent_digest"], round_no=1)
    live.retain_acquired(store, package, dispatch)
    bound = live.bind_retained_acquisition(
        str(path), {"status": "retained", "arm": arm,
                    "control_id": package["control_id"],
                    "package_digest": package["package_digest"],
                    "response_digest": package["response_digest"]},
        rules.make_task("dev", 4))
    return frontier.FrontierStore(str(path)), bound


def _write_bound_e3_fixture(tmp_path, arm="P1"):
    out = tmp_path / "e12"
    out.mkdir()
    freeze = driver.freeze_e12(out)
    store_path = tmp_path / "frontier.json"
    store, bound = _bound_acquired_store(store_path, arm)
    summary = {"store_path": str(store_path),
               "store_digest": driver._file_digest(store_path)}
    e12 = {**_run_identity(freeze),
           "status": "incomplete",
           "execution_status": "incomplete",
           "arms": {arm: {"status": "available", "frontier": summary,
                          "revision": bound},
                    "P2": {"status": "unavailable"}}}
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    (out / ("frontier-%s.json" % arm)).write_text(
        json.dumps(summary) + "\n")
    receipt = store.accepted_revisions[-1]["receipt"]
    (out / "e12-receipts.json").write_text(json.dumps({
        **_run_identity(e12),
        "operations": {receipt["operation_id"]: {
            "operation_id": receipt["operation_id"],
            "receipts": [receipt]}},
        "child_receipts": {receipt["operation_id"]: receipt}}) + "\n")
    return out, store, bound


def test_m4_export_refuses_missing_authoritative_ledger(tmp_path):
    out = _synthetic_e12(tmp_path)
    with pytest.raises(ValueError, match="authoritative operation ledger"):
        driver.export_m4_bundle(out)


def test_m4_export_requires_exact_authoritative_receipt_set(tmp_path):
    out = _synthetic_e12(tmp_path)
    freeze = json.loads((out / "freeze.json").read_text())
    (out / "authoritative-operations.json").write_text(json.dumps({
        **_run_identity(freeze),
        "operations": {},
        "child_receipts": {},
    }) + "\n")
    with pytest.raises(ValueError, match="authoritative operation ledger"):
        driver.export_m4_bundle(out)

    e12 = json.loads((out / "e12-run.json").read_text())
    operations, child_receipts = _write_synthetic_authority(out, e12)
    e12 = json.loads((out / "e12-run.json").read_text())
    exact_receipts = list(e12["durable_receipts"])
    e12["durable_receipts"] = exact_receipts[:-1]
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    with pytest.raises(ValueError, match="authoritative/E12 receipt set"):
        driver.export_m4_bundle(out)

    e12["durable_receipts"].append(_complete_receipt(
        "op-extra", "P1", "construct-P1", driver._p0_incumbent()[
            "source_digest"], {"status": "extra synthetic receipt"}))
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    with pytest.raises(ValueError, match="authoritative/E12 receipt set"):
        driver.export_m4_bundle(out)

    first = next(iter(operations))
    e12["durable_receipts"] = exact_receipts
    mismatched = dict(operations[first]["receipts"][0],
                      operation_id="wrong")
    operations[first]["receipts"] = [mismatched]
    child_receipts[first] = mismatched
    ledger = _synthetic_ledger(e12, operations, child_receipts)
    (out / "authoritative-operations.json").write_text(
        json.dumps(ledger) + "\n")
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    with pytest.raises(ValueError, match="receipt"):
        driver.export_m4_bundle(out)


def test_m4_verification_refuses_missing_or_mismatched_receipts(tmp_path):
    out = _synthetic_e12(tmp_path)
    e12 = json.loads((out / "e12-run.json").read_text())
    _write_synthetic_authority(out, e12)
    bundle = driver.export_m4_bundle(out)
    freeze = json.loads((out / "freeze.json").read_text())
    assert bundle["software"]["use_records"] != []
    assert {row["task_id"] for row in bundle["software"]["use_records"]} == set(
        freeze["software_tasks"])
    assert bundle["software"]["outcomes"] == [
        {"arm": row["arm"], "task_id": row["task_id"],
         "expected": row["expected"], "observed": row["observed"],
         "queries": row["queries"]}
        for row in bundle["software"]["use_records"]
    ]
    assert offline_recompute.verify_bundle(bundle)["recomputed"][
        "software_use_records"] == 3 * len(freeze["software_tasks"])

    bundle["operations"]["op-a-0"]["receipts"] = []
    failed = offline_recompute.verify_bundle(bundle)
    assert failed["status"] == "fail"
    assert "missing-receipt for-operation op-a-0" in failed["problems"]
    bundle["operations"]["op-a-0"]["receipts"] = [{
        "operation_id": "wrong", "receipt_identity": "test:wrong",
        "outcome": "success"}]
    failed = offline_recompute.verify_bundle(bundle)
    assert failed["status"] == "fail"
    assert "missing-receipt for-operation op-a-0" in failed["problems"]


def test_canonical_m4_verifier_owns_software_record_schema(tmp_path):
    out = _synthetic_e12(tmp_path)
    e12 = json.loads((out / "e12-run.json").read_text())
    _write_synthetic_authority(out, e12)
    bundle = driver.export_m4_bundle(out)
    bundle["software"]["outcomes"][0]["observed"] = "forged"

    verified = offline_recompute.verify_bundle(bundle)

    assert verified["status"] == "fail"
    assert "software-outcome-mismatch" in verified["problems"]


def test_pending_effect_rejects_unrelated_observation(tmp_path):
    store = frontier.create_store(
        tmp_path / "store.json", namespace=frontier.NAMESPACE,
        mission={"objective": "m", "environments": [{"split": "dev",
                                                     "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    package = channel.make_control("low")
    store.bind_active(package)
    store.propose({"opportunity_id": "opp", "mission_link": "m",
                   "question": "q",
                   "intervention": {"instrument": "boolean-rule-v1",
                                    "target": "rule-dev-0004", "inputs": {}},
                   "resources": {"queries": 1, "steps": 1}})
    effect = store.accept("opp", package["package_digest"])
    unrelated = store.observe({"observation_id": "obs-other",
                               "task": "rule-dev-0005", "verdict": "observed"})
    with pytest.raises(frontier.Refused, match="attribut"):
        store.settle(effect["effect_id"], unrelated)


class _FakeDurableE3Authority:
    def __init__(self, receipt):
        self.receipt = receipt

    def read(self, operation_id):
        if operation_id != self.receipt["operation_id"]:
            return None
        content = {
            key: self.receipt[key]
            for key in (
                "source_digest", "artifact_digest", "input_digest",
                "result_digest", "package_digest", "parent_digest", "round",
                "dispatch_evidence_digest")
        }
        content["result"] = self.receipt["details"]["raw_payload"]["result"]
        return {
            "operation": {
                "id": operation_id, "dispatch_state": "observed",
                "reconcile_state": "none", "settled": True},
            "receipts": [{
                "receipt_identity": self.receipt["receipt_identity"],
                "operation_id": operation_id, "outcome": "success",
                "content": content}],
            "receipt_conflicts": [],
        }


def _replace_local_receipt_with_durable_test_seam(out, store, bound):
    local = store.accepted_revisions[-1]["receipt"]
    details = dict(local["details"])
    raw_payload = dict(details["raw_payload"])
    result = {key: raw_payload[key] for key in ("action", "state")}
    raw_payload["result"] = result
    details["raw_payload"] = raw_payload
    durable = frontier.make_evidence_record(
        local["kind"], local["operation_id"], local["outcome"],
        attempt=local["attempt"],
        receipt_identity="durable:test:%s" % local["operation_id"],
        arm=local["arm"], task_id=local["task_id"],
        source_digest=local["source_digest"],
        artifact_digest=local["artifact_digest"],
        input_digest=local["input_digest"],
        result_digest=driver._digest(result),
        package_digest=local["package_digest"],
        parent_digest=local["parent_digest"], round_no=local["round"],
        dispatch_evidence_digest=local["dispatch_evidence_digest"],
        details=details)
    store.record_revision_receipt(bound["package_digest"], durable)
    summary = json.loads((out / "frontier-P1.json").read_text())
    summary["store_digest"] = driver._file_digest(Path(store.path))
    e12 = json.loads((out / "e12-run.json").read_text())
    e12["arms"]["P1"]["frontier"] = summary
    (out / "frontier-P1.json").write_text(json.dumps(summary) + "\n")
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    (out / "e12-receipts.json").write_text(json.dumps({
        **_run_identity(e12),
        "authority": "local-diagnostic", "authoritative": False,
        "operations": {durable["operation_id"]: {
            "operation_id": durable["operation_id"],
            "receipts": [durable]}},
        "child_receipts": {durable["operation_id"]: durable}}) + "\n")
    return durable


def test_e3_is_an_eligibility_screen_not_an_execution_result(
        tmp_path, monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    out, store, bound = _write_bound_e3_fixture(tmp_path)
    receipt = _replace_local_receipt_with_durable_test_seam(out, store, bound)
    result = driver.run_e3(
        "unused", tmp_path / "e3", out, authority=_FakeDurableE3Authority(receipt))
    assert result["status"] == "eligibility-screen"
    assert result["execution"] == "unavailable"
    assert result["eligible"] is False


def test_e0_requires_bound_preflight_before_authority(tmp_path, monkeypatch):
    freeze = driver.freeze_e0(tmp_path)
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(driver, "_live_model", lambda: freeze["route"][
        "requested_model"])
    monkeypatch.setattr(driver, "_live_route", lambda: dict(freeze["route"]))
    calls = []
    monkeypatch.setattr(driver, "_authorize", lambda *args, **kwargs: calls.append(
        True))
    result = driver.run_e0("unused", tmp_path)
    assert result["status"] == "unavailable"
    assert result["reason"] == "E0 preflight record is missing"
    assert calls == []


def test_e3_local_receipt_cannot_satisfy_missing_durable_authority(
        tmp_path, monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    monkeypatch.setattr(
        driver._DurableE3Authority, "read",
        lambda self, operation_id: (_ for _ in ()).throw(
            RuntimeError("durable authority unavailable")))
    out, _store, _bound = _write_bound_e3_fixture(tmp_path)
    result = driver.run_e3(
        "postgresql:///invl02-e3-authority-that-does-not-exist",
        tmp_path / "e3", out)
    assert result["status"] == "unavailable"
    assert result.get("arms", []) == []


def test_e3_accepts_only_matching_bound_e12_store_and_receipt(
        tmp_path, monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    out, store, bound = _write_bound_e3_fixture(tmp_path)
    receipt = _replace_local_receipt_with_durable_test_seam(out, store, bound)
    authority = _FakeDurableE3Authority(receipt)
    summary = json.loads((out / "frontier-P1.json").read_text())
    result = driver.run_e3(
        "unused", tmp_path / "e3", out, authority=authority)
    assert result["status"] == "eligibility-screen"
    assert result["execution"] == "unavailable"
    assert result.get("eligible") is False
    assert result["arms"][0]["arm"] == "P1"
    assert result["arms"][0]["evidence"]["package_digest"] == bound[
        "package_digest"]
    bad_summary = dict(summary, store_digest="0" * 64)
    e12 = json.loads((out / "e12-run.json").read_text())
    e12["arms"]["P1"]["frontier"] = bad_summary
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    (out / "frontier-P1.json").write_text(json.dumps(bad_summary) + "\n")
    rejected = driver.run_e3(
        "unused", tmp_path / "e3-bad-digest", out, authority=authority)
    assert rejected["status"] == "unavailable"
    assert "store digest" in rejected["arm_revisions"]["P1"]


def test_e3_requires_durable_gateway_dispatch_provenance(
        tmp_path, monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    out, store, _bound = _write_bound_e3_fixture(tmp_path)
    receipt = store.accepted_revisions[-1]["receipt"]
    store._doc["evidence"] = [
        record for record in store._doc["evidence"]
        if record.get("kind") != "gateway-dispatch"]
    store.save()
    assert receipt in store._doc["evidence"]
    assert json.loads((out / "e12-receipts.json").read_text())[
        "child_receipts"][receipt["operation_id"]] == receipt
    summary = json.loads((out / "frontier-P1.json").read_text())
    summary["store_digest"] = driver._file_digest(Path(store.path))
    e12 = json.loads((out / "e12-run.json").read_text())
    e12["arms"]["P1"]["frontier"] = summary
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    (out / "frontier-P1.json").write_text(json.dumps(summary) + "\n")
    result = driver.run_e3("unused", tmp_path / "e3-no-dispatch", out)
    assert result["status"] == "unavailable"
    assert "dispatch provenance" in result["arm_revisions"]["P1"]


def test_e3_rejects_store_not_bound_to_e12_run(tmp_path, monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    out = tmp_path / "e12"
    out.mkdir()
    freeze = driver.freeze_e12(out)
    related_path = tmp_path / "related.json"
    related = frontier.create_store(
        related_path, namespace=frontier.NAMESPACE,
        mission={"objective": "m", "environments": [{"split": "dev",
                                                     "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    related.bind_active(channel.make_control("low"))

    unrelated_path = tmp_path / "unrelated.json"
    unrelated, _bound = _bound_acquired_store(unrelated_path, "P1")
    receipt = unrelated.accepted_revisions[-1]["receipt"]

    related_digest = driver._file_digest(related_path)
    e12 = {**_run_identity(freeze),
           "arms": {"P1": {"status": "available", "frontier": {
               "store_path": str(related_path),
               "store_digest": related_digest}},
               "P2": {"status": "unavailable"}}}
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    summary = {"store_path": str(unrelated_path),
               "store_digest": driver._file_digest(unrelated_path)}
    (out / "frontier-P1.json").write_text(json.dumps(summary) + "\n")
    (out / "e12-receipts.json").write_text(json.dumps({
        **_run_identity(e12),
        "operations": {receipt["operation_id"]: {
            "operation_id": receipt["operation_id"],
            "receipts": [receipt]}},
        "child_receipts": {receipt["operation_id"]: receipt}}) + "\n")
    result = driver.run_e3("unused", tmp_path / "e3", out)
    assert result["status"] == "unavailable"
    assert "E12 arm" in result["arm_revisions"]["P1"]


def test_e3_requires_e12_run(tmp_path, monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    out = tmp_path / "e12"
    out.mkdir()
    driver.freeze_e12(out)
    result = driver.run_e3("unused", tmp_path / "e3", out)
    assert result["status"] == "unavailable"
    assert result["reason"] == "valid E12 run and freeze are required"


def test_e3_rejects_post_hoc_run_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    out = tmp_path / "e12"
    out.mkdir()
    freeze = driver.freeze_e12(out)
    (out / "e12-run.json").write_text(json.dumps({
        **_run_identity(freeze),
        "run_id": "posthoc-run",
        "arms": {"P1": {"status": "unavailable"},
                 "P2": {"status": "unavailable"}},
    }) + "\n")
    result = driver.run_e3("unused", tmp_path / "e3", out)
    assert result == {
        "study": "invl02-live-e3",
        "status": "unavailable",
        "reason": "E12 run does not match its frozen study root",
        "arm_revisions": {},
    }


def test_e3_ignores_forged_bound_summary_without_durable_revision(tmp_path,
                                                                  monkeypatch):
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    out = tmp_path / "e12"
    out.mkdir()
    freeze = driver.freeze_e12(out)
    (out / "e12-run.json").write_text(json.dumps({
        **_run_identity(freeze),
        "arms": {
            "P1": {"status": "available", "revision": {
                "disposition": "bound", "release_id": "forged"}},
            "P2": {"status": "unavailable", "revision": "absent"},
        },
    }) + "\n")
    result = driver.run_e3("unused", tmp_path / "e3", out)
    assert result["status"] == "unavailable"
    assert result["reason"] == "no eligible revised improver"
    assert result["arm_revisions"]["P1"] == \
        "durable frontier record is missing"
