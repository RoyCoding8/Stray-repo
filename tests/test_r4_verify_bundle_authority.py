from __future__ import annotations

import json

from experiments.ad01 import offline_recompute as m4
from scripts import invl02_live as driver
from test_m4_offline_recompute import _lost_response_bundle


def _unavailable_with_preflight(tmp_path, refusal_run_id=None):
    freeze = driver.freeze_output(tmp_path)
    driver._output_unavailable(
        tmp_path, freeze, "durable broker unavailable before inference")
    preflight = driver._preflight_record(freeze, freeze["route"])
    (tmp_path / "preflight.json").write_text(json.dumps(preflight))
    refusal = {**preflight, "reason": "output preflight record is missing",
               "dispatch_count": 0}
    if refusal_run_id is not None:
        refusal["run_id"] = refusal_run_id
    (tmp_path / "preflight-refusal.json").write_text(json.dumps(refusal))
    return tmp_path / "output-run.json"


def test_output_verification_declares_bundle_only_dispatch_authority(tmp_path):
    bundle = _lost_response_bundle(tmp_path)
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    verified = m4.verify_bundle(bundle, private)

    assert verified["verification_scope"] == {
        "dispatch_authority": "bundle-only",
        "external_operation_store_checked": False,
        "sibling_evidence_checked": False,
    }


def test_output_incomplete_run_cannot_claim_established_utility(tmp_path):
    bundle = _lost_response_bundle(tmp_path)
    bundle["claims"] = {
        "task_utility": "established",
        "transfer": "established",
        "recursive_improvement": "established",
    }
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    verified = m4.verify_bundle(bundle, private)

    assert verified["status"] == "fail"
    assert "research-claims-invalid" in verified["problems"]


def test_output_honest_lost_response_has_no_receipt_contract_problem(tmp_path):
    bundle = _lost_response_bundle(tmp_path)
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    verified = m4.verify_bundle(bundle, private)

    operation_id = verified["recomputed"][
        "lost-response-disposition"][0]["operation_id"]
    assert [problem for problem in verified["problems"]
            if operation_id in problem and "receipt" in problem] == []


def test_output_failed_outcome_cannot_claim_lost_response(tmp_path):
    bundle = _lost_response_bundle(tmp_path)
    receipt = bundle["candidate_view"]["durable_receipts"][0]
    receipt["outcome"] = "failure"
    dispatch = bundle["candidate_view"]["dispatches"][0]
    dispatch["durable_receipt"] = dict(receipt)
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    verified = m4.verify_bundle(bundle, private)

    operation_id = receipt["operation_id"]
    assert [problem for problem in verified["problems"]
            if operation_id in problem and "receipt" in problem]


def test_output_file_rejects_valid_preflight_with_refusal_sibling(tmp_path):
    path = _unavailable_with_preflight(tmp_path)

    verified = m4.verify_bundle_file(str(path))

    assert verified["status"] == "fail"
    assert "preflight-refusal-contradicts-valid-preflight" in verified["problems"]


def test_output_file_ignores_refusal_from_another_run(tmp_path):
    path = _unavailable_with_preflight(tmp_path, refusal_run_id="another-run")

    verified = m4.verify_bundle_file(str(path))

    assert "preflight-refusal-contradicts-valid-preflight" not in (
        verified["problems"])
