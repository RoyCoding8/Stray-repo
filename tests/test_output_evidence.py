from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import cli as ad01_cli
from experiments.ad01 import live_construct as live
from experiments.ad01 import offline_recompute
from experiments.ad01 import rule_learner
from scripts import invl02_live as driver
from settlement.gateway import ModelResponse, Usage


class _OutputGateway:
    def __init__(self, responses, route):
        self.responses = list(responses)
        self.route = route
        self.requests = []

    def infer(self, request):
        from settlement.gateway import GatewayError

        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, GatewayError):
            return response
        return ModelResponse(
            request.operation_id,
            response["text"],
            {
                "adapter": "http",
                "contract": "settlement-gateway/http-responses-v1",
                "endpoint": self.route["endpoint"],
                "model": response.get("model", self.route["resolved_model"]),
                "provider": response.get("provider", self.route["provider"]),
                "tier": response.get("tier", self.route["tier"]),
            },
            Usage(input_tokens=3, output_tokens=5, charge_units=0, billed=False),
            response.get("stop_reason", "stop"),
        )

    def check_discovery(self):
        return "reachable"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True


def _legal_text(split, seed):
    task = rules.make_task(split, seed)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        learner.observe(pick, session.query(pick))
    return json.dumps({"specs": [dict(s) for s in learner.predict(
        dict(session.queried))["specs"]]})


def _responses():
    return [{"text": "not json"}, {"text": _legal_text("audit", 23)},
            {"text": _legal_text("qual", 11)},
            {"text": _legal_text("audit", 23)},
            {"text": _legal_text("qual", 11)},
            {"text": _legal_text("audit", 23)},
            {"text": _legal_text("qual", 11)},
            {"text": _legal_text("audit", 23)}]


def _rebuild_dispatch_evidence(dispatch, **updates):
    from experiments.ad01 import frontier

    dispatch.update(updates)
    rebuilt = frontier.make_evidence_record(
        dispatch["kind"], dispatch["operation_id"], dispatch["outcome"],
        attempt=dispatch["attempt"],
        receipt_identity=dispatch["receipt_identity"],
        arm=dispatch["arm"], task_id=dispatch["task_id"],
        source_digest=dispatch["source_digest"],
        artifact_digest=dispatch["artifact_digest"],
        input_digest=dispatch["input_digest"],
        result_digest=dispatch["result_digest"],
        package_digest=dispatch.get("package_digest"),
        parent_digest=dispatch.get("parent_digest"),
        round_no=dispatch.get("round"),
        dispatch_evidence_digest=dispatch.get("dispatch_evidence_digest"),
        details=dispatch["details"])
    for key in ("version", "kind", "operation_id", "attempt", "outcome",
                "arm", "task_id", "source_digest", "artifact_digest",
                "input_digest", "result_digest", "package_digest",
                "parent_digest", "round", "dispatch_evidence_digest",
                "raw_payload_digest", "receipt_identity", "evidence_digest",
                "details"):
        if key in rebuilt:
            dispatch[key] = rebuilt[key]
    return dispatch


def _durable_receipts(result, *, status="measured", usage_overrides=None):
    receipts = []
    for dispatch in result["candidate_view"]["dispatches"]:
        usage = copy.deepcopy(dispatch["usage"])
        if usage_overrides:
            usage.update(usage_overrides)
        receipts.append({
            "operation_id": dispatch["operation_id"],
            "receipt_identity": dispatch["receipt_identity"],
            "outcome": "success" if dispatch["parse_outcome"] == "accepted"
                       else "failure",
            "source_digest": dispatch["source_digest"],
            "artifact_digest": dispatch["artifact_digest"],
            "input_digest": dispatch["input_digest"],
            "result_digest": dispatch["result_digest"],
            "dispatch_evidence_digest": (
                dispatch.get("dispatch_evidence_digest")
                or dispatch["evidence_digest"]),
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "settled": True,
            "usage": usage,
            "measurement_status": status,
        })
    result["candidate_view"]["durable_receipts"] = receipts
    for dispatch in result["candidate_view"]["dispatches"]:
        dispatch["durable_receipt"] = copy.deepcopy(next(
            receipt for receipt in receipts
            if receipt["operation_id"] == dispatch["operation_id"]))
    return result


def _verify(result, private_dir=None):
    private = None
    if private_dir is not None:
        private = json.loads(
            (Path(private_dir) / "scorer-private.json").read_text())
    return offline_recompute.verify_bundle(result, private)


def test_output_freeze_binds_one_protocol_and_limits(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    assert freeze["protocol"] == "invl02-output-shape-550b-r1-v1"
    assert freeze["study_root"] == "invl02-output-shape-550b-r1"
    assert freeze["route"] == live.OUTPUT_ROUTE
    assert freeze["limits"] == {
        "max_response_characters": 512,
        "max_output_tokens": 2048,
        "max_dispatches": 8,
        "initial_dispatches": 4,
        "repairs_per_task": 1,
        "automatic_retries": 0,
    }
    assert freeze["tasks"] == {"qual": 11, "audit": 23}
    assert freeze["history"]["P1"]["entries"] == []
    assert freeze["history"]["P2"]["digest"]
    assert freeze["prompt"]["template_digest"] == live.response_digest(
        live.OUTPUT_PROMPT_TEMPLATE)
    assert freeze["code_digests"]["scripts/invl02_live.py"]
    assert freeze["source_digests"]["experiments/ad01/live_construct.py"]
    assert freeze["freeze_digest"] == driver._digest(
        {k: v for k, v in freeze.items() if k != "freeze_digest"})


def test_output_run_uses_2048_and_new_id_for_one_repair(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    gateway = _OutputGateway(_responses(), freeze["route"])
    result = driver.run_output(tmp_path, gateway=gateway,
                               model=freeze["route"]["requested_model"])
    assert result["status"] in {"available", "incomplete"}
    assert [request.max_output_tokens for request in gateway.requests] == [
        2048
    ] * len(gateway.requests)
    operation_ids = [request.operation_id for request in gateway.requests]
    assert len(operation_ids) == len(set(operation_ids))
    dispatches = result["candidate_view"]["dispatches"]
    assert len(dispatches) == len(operation_ids)
    assert {d["attempt"] for d in dispatches} <= {1, 2}
    assert all(d["requested_output_cap"] == 2048 for d in dispatches)


def test_output_run_has_no_hidden_empty_retry(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    responses = [{"text": ""}, {"text": _legal_text("audit", 23)}]
    responses.extend(_responses()[1:])
    gateway = _OutputGateway(responses, freeze["route"])
    result = driver.run_output(tmp_path, gateway=gateway,
                               model=freeze["route"]["requested_model"])
    first = result["candidate_view"]["dispatches"][0]
    second = result["candidate_view"]["dispatches"][1]
    assert first["parse_outcome"] == "empty"
    assert second["parse_outcome"] == "accepted"
    assert first["operation_id"] != second["operation_id"]
    assert first["attempt"] == 1
    assert second["attempt"] == 2


def test_output_run_real_gateway_route_mismatch_is_terminal(tmp_path):
    import httpx
    from settlement.gateway_http import HttpGatewayAdapter

    freeze = driver.freeze_output(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        body = {
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": _legal_text("qual", 11)}]}],
            "model": "other/resolved:free",
            "provider": freeze["route"]["provider"],
            "tier": freeze["route"]["tier"],
            "input_tokens": 3,
            "output_tokens": 5,
        }
        raw = json.dumps(body).encode("utf-8")
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = HttpGatewayAdapter(
        endpoint=freeze["route"]["endpoint"], api_key="test-key",
        client=client, api="responses", expected_route=freeze["route"])
    result = driver.run_output(
        tmp_path, gateway=gateway,
        model=freeze["route"]["requested_model"])
    assert result["status"] == "incomplete"
    assert len(requests) == 1
    assert [entry["attempt"] for entry in
            result["candidate_view"]["dispatches"]] == [1]
    assert result["candidate_view"]["dispatches"][0]["parse_outcome"] == (
        "route-refused")


def test_output_run_refuses_route_mismatch_without_repair(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    responses = _responses()
    responses[0] = {"text": _legal_text("qual", 11),
                    "model": "openrouter/other:free"}
    gateway = _OutputGateway(responses, freeze["route"])
    result = driver.run_output(tmp_path, gateway=gateway,
                               model=freeze["route"]["requested_model"])
    assert result["status"] == "incomplete"
    assert any(d["parse_outcome"] == "route-refused"
               for d in result["candidate_view"]["dispatches"])
    first_task = result["candidate_view"]["dispatches"][0]
    assert len(result["candidate_view"]["dispatches"]) == 1
    assert first_task["parse_outcome"] == "route-refused"
    assert not any(d["task_id"] == first_task["task_id"]
                   and d["attempt"] == 2
                   for d in result["candidate_view"]["dispatches"])


def test_output_evidence_retains_raw_bytes_without_private_targets(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    gateway = _OutputGateway(_responses(), freeze["route"])
    result = driver.run_output(tmp_path, gateway=gateway,
                               model=freeze["route"]["requested_model"])
    encoded = json.dumps(result, sort_keys=True)
    assert "raw_prompt" in encoded
    assert "raw_response" in encoded
    assert "target_tables" not in encoded
    assert "private_answer" not in encoded
    assert "SETTLEMENT_GATEWAY_KEY" not in encoded
    assert "api_key" not in encoded
    candidate_view = result["candidate_view"]
    assert "scorer_private" not in candidate_view
    assert all("score" not in d for d in candidate_view["dispatches"])
    private = json.loads((tmp_path / "scorer-private.json").read_text())
    assert private["scores"]


def test_candidate_artifact_excludes_scorer_private_state(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    gateway = _OutputGateway(_responses(), freeze["route"])
    driver.run_output(tmp_path, gateway=gateway,
                      model=freeze["route"]["requested_model"])
    artifact = json.loads((tmp_path / "output-run.json").read_text())
    private = json.loads((tmp_path / "scorer-private.json").read_text())
    forbidden = {"score", "scores", "score_overall", "target_tables",
                 "private_answer", "winner", "selection"}

    def scan(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key not in forbidden
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(artifact)
    assert private["scores"]
    assert "scorer_private" not in artifact


def test_output_offline_recompute_uses_raw_response_and_fails_closed(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    gateway = _OutputGateway(_responses(), freeze["route"])
    result = driver.run_output(tmp_path, gateway=gateway,
                               model=freeze["route"]["requested_model"])
    verified = _verify(result, tmp_path)
    assert verified["status"] == "fail"
    assert any(problem.startswith("missing-durable-receipt")
               for problem in verified["problems"])
    tampered = copy.deepcopy(result)
    dispatch = tampered["candidate_view"]["dispatches"][0]
    dispatch["raw_response"] += " "
    failed = _verify(tampered, tmp_path)
    assert failed["status"] == "fail"
    assert "response-digest-mismatch" in failed["problems"]


def test_incomplete_output_recompute_is_nonzero(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    responses = [{"text": "not json"} for _ in range(8)]
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(responses, freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})

    verified = _verify(result, tmp_path)

    assert result["status"] == "incomplete"
    assert verified["status"] == "incomplete"
    assert verified["problems"] == ["study-incomplete"]


def test_verify_output_malformed_shape_fails_without_raising():
    verified = offline_recompute.verify_bundle({"candidate_view": []})

    assert verified["status"] == "fail"
    assert "bundle-shape-invalid candidate_view" in verified["problems"]


def test_recompute_cli_preserves_incomplete_output_status(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    responses = [{"text": "not json"} for _ in range(8)]
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(responses, freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    (tmp_path / "output-run.json").write_text(json.dumps(result) + "\n")

    verified = driver.recompute(tmp_path)

    assert verified["status"] == "incomplete"
    assert (tmp_path / "output-recompute.json").is_file()


def test_verify_output_recomputes_candidate_and_evidence_lineage(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    accepted = next(entry for entry in result["candidate_view"]["dispatches"]
                    if entry["parse_outcome"] == "accepted")
    durable = next(receipt for receipt in
                   result["candidate_view"]["durable_receipts"]
                   if receipt["operation_id"] == accepted["operation_id"])
    for row in (accepted, accepted["durable_receipt"], durable):
        row["source_digest"] = "f" * 64
    _rebuild_dispatch_evidence(accepted)

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert "candidate-lineage-mismatch %s" % accepted["operation_id"] in (
        verified["problems"])


def test_verify_output_binds_candidate_input_to_raw_prompt(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    accepted = next(entry for entry in result["candidate_view"]["dispatches"]
                    if entry["parse_outcome"] == "accepted")
    durable = next(receipt for receipt in
                   result["candidate_view"]["durable_receipts"]
                   if receipt["operation_id"] == accepted["operation_id"])
    for row in (accepted, accepted["durable_receipt"], durable):
        row["input_digest"] = "e" * 64
    _rebuild_dispatch_evidence(accepted)

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert "candidate-input-mismatch %s" % accepted["operation_id"] in (
        verified["problems"])


def test_verify_output_requires_authoritative_physical_operation(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    physical = next(entry for entry in result["candidate_view"]["dispatches"]
                    if not entry.get("replay", False))
    physical["new_dispatch"] = False

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert "physical-operation-not-authoritative %s" % physical[
        "operation_id"] in verified["problems"]


def test_verify_output_requires_one_nested_durable_receipt(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    physical = next(entry for entry in result["candidate_view"]["dispatches"]
                    if not entry.get("replay", False))
    nested = physical["durable_receipt"]
    physical["durable_receipt"] = [nested, copy.deepcopy(nested)]

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert "durable-nested-receipt-count-invalid %s" % physical[
        "operation_id"] in verified["problems"]


def test_verify_output_refuses_replay_without_physical_operation(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    physical = next(entry for entry in result["candidate_view"]["dispatches"]
                    if not entry.get("replay", False))
    replay = copy.deepcopy(physical)
    replay["replay"] = True
    replay["new_dispatch"] = False
    result["candidate_view"]["dispatches"].append(replay)
    result["candidate_view"]["dispatch_count"] += 1
    result["candidate_view"]["replay_count"] = 1
    result["candidate_view"]["physical_dispatch_count"] = len(
        result["candidate_view"]["dispatches"]) - 1
    replay["operation_id"] = "invl02-output-P1-qual-0011-a2"
    result["candidate_view"]["durable_receipts"].append(copy.deepcopy(
        result["candidate_view"]["durable_receipts"][0]))

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert any(problem.startswith("replay-physical-operation-missing")
               for problem in verified["problems"])


def test_verify_output_accepts_one_replay_with_one_authoritative_receipt(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    physical = next(entry for entry in result["candidate_view"]["dispatches"]
                    if not entry.get("replay", False)
                    and entry["parse_outcome"] == "accepted")
    replay = copy.deepcopy(physical)
    replay["replay"] = True
    replay["new_dispatch"] = False
    result["candidate_view"]["dispatches"].append(replay)
    result["candidate_view"]["dispatch_count"] += 1
    result["candidate_view"]["replay_count"] += 1

    verified = _verify(result, tmp_path)

    assert verified["status"] == "pass", verified["problems"]
    assert verified["recomputed"]["dispatches"] == len(
        result["candidate_view"]["dispatches"])
    assert verified["recomputed"]["accepted_candidates"] == 4


def test_verify_output_requires_settled_true_on_every_durable_receipt(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result)
    result["candidate_view"]["durable_receipts"][0].pop("settled")

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert "durable-receipt-settled-missing" in verified["problems"]


def test_verify_output_requires_matching_nested_durable_receipts(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result)
    first = result["candidate_view"]["dispatches"][0]
    first.pop("durable_receipt")

    missing = _verify(result, tmp_path)

    assert missing["status"] == "fail"
    assert "durable-nested-receipt-missing %s" % first[
        "operation_id"] in missing["problems"]

    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result)
    first = result["candidate_view"]["dispatches"][0]
    first["durable_receipt"]["usage"]["input_tokens"] = -1

    mismatched = _verify(result, tmp_path)

    assert mismatched["status"] == "fail"
    assert "durable-nested-receipt-mismatch %s" % first[
        "operation_id"] in mismatched["problems"]


def test_verify_output_rejects_malformed_unknown_usage(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, status="unknown", usage_overrides={
        "input_tokens": -1, "charge_units": "bad", "charge_scale": "bad",
        "billed": "no"})

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert "durable-receipt-usage-state-invalid" in verified["problems"]


def test_verify_output_rejects_unclosed_durable_usage_state(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result)
    result["candidate_view"]["durable_receipts"][0].pop(
        "measurement_status")
    result["candidate_view"]["durable_receipts"][0]["usage"] = {}

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert "durable-receipt-measurement-status-missing" in verified["problems"]
    assert "durable-receipt-usage-state-invalid" in verified["problems"]


@pytest.mark.parametrize("usage, expected", [
    ({"charge_scale": 0}, "unknown"),
    ({"charge_units": 0, "billed": True}, "unknown"),
    ({"charge_units": 1, "billed": False}, "unknown"),
])
def test_verify_output_usage_contradictions_are_not_measured_zero(
        usage, expected):
    receipt = {
        "operation_id": "op", "receipt_identity": "receipt",
        "outcome": "success", "settled": True, "usage": {
            "input_tokens": 3, "output_tokens": 5, "charge_units": 0,
            "charge_scale": 7, "billed": False,
        },
    }
    receipt["usage"].update(usage)
    assert offline_recompute.receipt_measurement_status(receipt) == expected


def test_verify_output_malformed_nested_shape_returns_failure():
    verified = offline_recompute.verify_bundle({
        "protocol": {"prompt": {"rendered_digests": []}},
        "candidate_view": {"dispatches": [], "durable_receipts": [],
                           "incumbent_control": []},
    })

    assert verified["status"] == "fail"
    assert "bundle-shape-invalid protocol.prompt.rendered_digests" in verified[
        "problems"]


def test_verify_output_recomputes_measurement_status_and_identity_ownership(
        tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})

    assert _verify(result, tmp_path)["status"] == "pass"

    missing = copy.deepcopy(result)
    missing["candidate_view"]["durable_receipts"][0].pop(
        "measurement_status")
    assert _verify(missing, tmp_path)["status"] == "fail"

    wrong = copy.deepcopy(result)
    wrong["candidate_view"]["durable_receipts"][0][
        "measurement_status"] = "unknown"
    assert _verify(wrong, tmp_path)["status"] == "fail"

    duplicate = copy.deepcopy(result)
    duplicate["candidate_view"]["durable_receipts"][1][
        "receipt_identity"] = duplicate["candidate_view"][
            "durable_receipts"][0]["receipt_identity"]
    assert _verify(duplicate, tmp_path)["status"] == "fail"


def test_verify_output_requires_conflict_usage_and_unresolved_exposure(
        tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    receipt = result["candidate_view"]["durable_receipts"][0]
    receipt["conflict_count"] = 1
    receipt["outcome"] = "conflict"
    receipt["measurement_status"] = "unresolved"
    receipt["unresolved_exposure"] = 11
    receipt["receipt_conflicts"] = [{
        "receipt_identity": receipt["receipt_identity"],
        "outcome": "failure",
        "usage": {},
        "unresolved_exposure": 11,
    }]

    verified = _verify(result, tmp_path)

    assert verified["status"] == "fail"
    assert any(problem.startswith(
        "durable-receipt-conflict-usage-invalid")
        for problem in verified["problems"])

    receipt["receipt_conflicts"][0]["usage"] = {
        "input_tokens": 3, "output_tokens": 5, "charge_units": 1,
        "charge_scale": 7, "billed": True,
    }
    receipt["receipt_conflicts"][0]["unresolved_exposure"] = 12
    assert _verify(result, tmp_path)["status"] == "fail"


    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    accepted = next(entry for entry in result["candidate_view"]["dispatches"]
                    if entry["parse_outcome"] == "accepted")
    result["candidate_view"]["durable_receipts"] = [{
        "operation_id": accepted["operation_id"],
        "receipt_identity": accepted["receipt_identity"],
        "outcome": "success",
        "source_digest": accepted["source_digest"],
        "artifact_digest": accepted["artifact_digest"],
        "input_digest": accepted["input_digest"],
        "result_digest": accepted["result_digest"],
        "dispatch_evidence_digest": accepted["evidence_digest"],
        "dispatch_state": "observed",
        "reconcile_state": "none",
    }]
    assert _verify(result, tmp_path)["status"] == "fail"
    result["candidate_view"]["durable_receipts"][0]["result_digest"] = "f" * 64
    verified = _verify(result, tmp_path)
    assert any(problem.startswith("durable-receipt-lineage-mismatch")
               for problem in verified["problems"])


def test_output_durable_conflict_refuses_success_text_and_keeps_usage(monkeypatch):
    from settlement import broker, store
    from settlement.common import ResultCode
    from settlement.gateway import ModelRequest

    operation_id = "invl02-output-P1-qual-0011-a1"
    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.APPLIED,
            data={"reservation_id": "res-1", "exposure": 11}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: SimpleNamespace(
            dispatch_state="observed", reconcile_state="none",
            next_decision="terminal"))
    monkeypatch.setattr(
        broker, "read_operation",
        lambda *args, **kwargs: {
            "reservation_id": "res-1", "dispatch_state": "observed",
            "reconcile_state": "none"})
    monkeypatch.setattr(
        store, "operation_receipts",
        lambda *args, **kwargs: [
            {"receipt_identity": "gw:success", "outcome": "success",
             "content": {"text": "must not escape", "usage": {
                 "input_tokens": 3, "output_tokens": 5, "charge_units": 1,
                 "charge_scale": 7, "billed": True}}},
            {"receipt_identity": "gw:failure", "outcome": "failure",
             "content": {"error": "conflicting failure", "usage": {
                 "input_tokens": 3, "output_tokens": 0, "charge_units": 1,
                 "charge_scale": 7, "billed": True}}},
        ])
    monkeypatch.setattr(
        store, "operation_receipt_conflicts",
        lambda *args, **kwargs: [{
            "receipt_identity": "gw:success",
            "content": {
                "outcome": "failure",
                "receipt_content": {"usage": {
                    "input_tokens": 3, "output_tokens": 0,
                    "charge_units": 1, "charge_scale": 7, "billed": True}},
            },
        }])

    durable = driver._DurableBrokerOutput(
        "unused", _OutputGateway([], live.OUTPUT_ROUTE),
        allocation_id="allocation-1", expected_route=live.OUTPUT_ROUTE)
    with pytest.raises(RuntimeError, match="receipt conflict"):
        durable.infer(ModelRequest(
            model=live.OUTPUT_ROUTE["requested_model"],
            messages=({"role": "user", "content": "input"},),
            max_output_tokens=2048, deadline_ms=1000,
            operation_id=operation_id))
    assert durable.durable_receipts[0]["outcome"] == "conflict"
    assert durable.durable_receipts[0]["usage"]["charge_scale"] == 7
    assert durable.durable_receipts[0]["exposure"] == 11
    assert durable.durable_receipts[0]["conflict_count"] == 1
    assert durable.durable_receipts[0]["unresolved_exposure"] == 11
    assert durable.durable_receipts[0]["receipt_conflicts"] == [{
        "receipt_identity": "gw:success",
        "outcome": "failure",
        "usage": {
            "input_tokens": 3, "output_tokens": 0, "charge_units": 1,
            "charge_scale": 7, "billed": True,
        },
        "unresolved_exposure": 11,
    }]


def test_output_partial_dispatch_evidence_is_preserved(monkeypatch):
    from settlement import broker
    from settlement.common import ResultCode
    from settlement.gateway import ModelRequest

    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.APPLIED,
            data={"reservation_id": "res-1", "exposure": 11}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("transport stopped")))
    durable = driver._DurableBrokerOutput(
        "unused", _OutputGateway([], live.OUTPUT_ROUTE),
        allocation_id="allocation-1", expected_route=live.OUTPUT_ROUTE)
    with pytest.raises(RuntimeError, match="transport stopped"):
        durable.infer(ModelRequest(
            model=live.OUTPUT_ROUTE["requested_model"],
            messages=({"role": "user", "content": "input"},),
            max_output_tokens=2048, deadline_ms=1000,
            operation_id="invl02-output-P1-qual-0011-a1"))
    assert len(durable.partial_dispatches) == 1
    assert durable.partial_dispatches[0]["raw_prompt"] == "input"
    assert durable.partial_dispatches[0]["parse_outcome"] == "transport-error"


def test_output_ambiguous_success_receipts_preserve_every_row(monkeypatch):
    from settlement import broker, store
    from settlement.common import ResultCode
    from settlement.gateway import ModelRequest

    operation_id = "invl02-output-P1-qual-0011-a1"
    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.APPLIED,
            data={"reservation_id": "res-1", "exposure": 11}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: SimpleNamespace(
            dispatch_state="observed", reconcile_state="none",
            settled=True, next_decision="terminal"))
    monkeypatch.setattr(
        broker, "read_operation",
        lambda *args, **kwargs: {
            "reservation_id": "res-1", "dispatch_state": "observed",
            "reconcile_state": "none", "settled": True})
    monkeypatch.setattr(
        store, "operation_receipts",
        lambda *args, **kwargs: [
            {"receipt_identity": "gw:success-1", "outcome": "success",
             "content": {"text": "first", "usage": {
                 "input_tokens": 3, "output_tokens": 5, "charge_units": 1,
                 "charge_scale": 7, "billed": True}}},
            {"receipt_identity": "gw:success-2", "outcome": "success",
             "content": {"text": "second", "usage": {
                 "input_tokens": 3, "output_tokens": 5, "charge_units": 1,
                 "charge_scale": 7, "billed": True}}},
        ])
    monkeypatch.setattr(
        store, "operation_receipt_conflicts", lambda *args, **kwargs: [])

    durable = driver._DurableBrokerOutput(
        "unused", _OutputGateway([], live.OUTPUT_ROUTE),
        allocation_id="allocation-1", expected_route=live.OUTPUT_ROUTE)
    with pytest.raises(RuntimeError, match="ambiguous"):
        durable.infer(ModelRequest(
            model=live.OUTPUT_ROUTE["requested_model"],
            messages=({"role": "user", "content": "input"},),
            max_output_tokens=2048, deadline_ms=1000,
            operation_id=operation_id))
    assert [row["receipt_identity"] for row in durable.durable_receipts] == [
        "gw:success-1", "gw:success-2"]
    assert all(row["unresolved_exposure"] == 11
               for row in durable.durable_receipts)


def test_output_success_requires_settled_operation(monkeypatch):
    from settlement import broker, store
    from settlement.common import ResultCode
    from settlement.gateway import ModelRequest

    operation_id = "invl02-output-P1-qual-0011-a1"
    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.APPLIED,
            data={"reservation_id": "res-1", "exposure": 11}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: SimpleNamespace(
            dispatch_state="observed", reconcile_state="none",
            settled=False, next_decision="terminal"))
    monkeypatch.setattr(
        broker, "read_operation",
        lambda *args, **kwargs: {
            "reservation_id": "res-1", "dispatch_state": "observed",
            "reconcile_state": "none", "settled": False})
    monkeypatch.setattr(
        store, "operation_receipts",
        lambda *args, **kwargs: [{
            "receipt_identity": "gw:success", "outcome": "success",
            "content": {"text": "must not escape", "usage": {
                "input_tokens": 3, "output_tokens": 5, "charge_units": 1,
                "charge_scale": 7, "billed": True}}}])
    monkeypatch.setattr(
        store, "operation_receipt_conflicts", lambda *args, **kwargs: [])

    durable = driver._DurableBrokerOutput(
        "unused", _OutputGateway([], live.OUTPUT_ROUTE),
        allocation_id="allocation-1", expected_route=live.OUTPUT_ROUTE)
    with pytest.raises(RuntimeError, match="unsettled"):
        durable.infer(ModelRequest(
            model=live.OUTPUT_ROUTE["requested_model"],
            messages=({"role": "user", "content": "input"},),
            max_output_tokens=2048, deadline_ms=1000,
            operation_id=operation_id))
    assert durable.durable_receipts[0]["outcome"] == "unresolved"
    assert durable.durable_receipts[0]["unsettled"] is True
    assert durable.durable_receipts[0]["unresolved_exposure"] == 11


def test_output_unresolved_reconciliation_records_exposure(monkeypatch):
    from settlement import broker, store
    from settlement.common import ResultCode
    from settlement.gateway import ModelRequest

    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.APPLIED,
            data={"reservation_id": "res-2", "exposure": 13}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: SimpleNamespace(
            dispatch_state="unresolved", reconcile_state="unresolved",
            next_decision="needs-reconciliation"))
    monkeypatch.setattr(
        broker, "read_operation",
        lambda *args, **kwargs: {
            "reservation_id": "res-2", "dispatch_state": "unresolved",
            "reconcile_state": "unresolved"})
    monkeypatch.setattr(
        store, "operation_receipts", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        store, "operation_receipt_conflicts", lambda *args, **kwargs: [])

    durable = driver._DurableBrokerOutput(
        "unused", _OutputGateway([], live.OUTPUT_ROUTE),
        allocation_id="allocation-1", expected_route=live.OUTPUT_ROUTE)
    with pytest.raises(RuntimeError, match="unresolved"):
        durable.infer(ModelRequest(
            model=live.OUTPUT_ROUTE["requested_model"],
            messages=({"role": "user", "content": "input"},),
            max_output_tokens=2048, deadline_ms=1000,
            operation_id="invl02-output-P1-qual-0011-a1"))
    assert durable.durable_receipts == [{
        "operation_id": "invl02-output-P1-qual-0011-a1",
        "reservation_id": "res-2", "receipt_identity": None,
        "receipt_outcome": None, "outcome": "unresolved", "usage": {},
        "exposure": 13, "unresolved_exposure": 13,
        "dispatch_state": "unresolved", "reconcile_state": "unresolved",
        "settled": False, "unsettled": True, "conflict": False,
        "conflict_count": 0, "receipt_conflicts": [],
        "measurement_status": "unresolved",
    }]


@pytest.mark.parametrize("charge_scale", [7, None])
def test_output_receipt_preserves_known_and_unknown_charge_scale(
        monkeypatch, charge_scale):
    from settlement import broker, store
    from settlement.common import ResultCode
    from settlement.gateway import ModelRequest, ModelResponse

    operation_id = "invl02-output-P1-qual-0011-a1"
    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.APPLIED, data={"reservation_id": "res-1"}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: SimpleNamespace(
            dispatch_state="observed", reconcile_state="none", settled=True,
            next_decision="terminal"))
    monkeypatch.setattr(
        broker, "read_operation",
        lambda *args, **kwargs: {
            "reservation_id": "res-1", "dispatch_state": "observed",
            "reconcile_state": "none", "settled": True})
    monkeypatch.setattr(
        store, "operation_receipts",
        lambda *args, **kwargs: [{
            "receipt_identity": "gw:success", "outcome": "success",
            "content": {"text": "{}", "usage": {
                "input_tokens": 3, "output_tokens": 5, "charge_units": 1,
                "charge_scale": charge_scale, "billed": True}}}])
    monkeypatch.setattr(
        store, "operation_receipt_conflicts", lambda *args, **kwargs: [])

    durable = driver._DurableBrokerOutput(
        "unused", _OutputGateway([], live.OUTPUT_ROUTE),
        allocation_id="allocation-1", expected_route=live.OUTPUT_ROUTE)
    response = durable.infer(ModelRequest(
        model=live.OUTPUT_ROUTE["requested_model"],
        messages=({"role": "user", "content": "input"},),
        max_output_tokens=2048, deadline_ms=1000,
        operation_id=operation_id))
    assert isinstance(response, ModelResponse)
    assert response.text == "{}"
    assert response.usage.charge_scale == charge_scale
    assert durable.durable_receipts[0]["usage"]["charge_scale"] == charge_scale


def test_output_failed_dispatch_keeps_initial_evidence_and_durable_receipt():
    dispatch = {
        "operation_id": "invl02-output-P1-qual-0011-a1",
        "evidence_digest": "f" * 64,
        "dispatch_evidence_digest": "e" * 64,
        "parse_outcome": "parse-failed",
    }
    durable = {
        "operation_id": dispatch["operation_id"],
        "receipt_identity": "durable:invl02-output-P1-qual-0011-a1",
        "outcome": "failure",
        "usage": {"input_tokens": 4, "output_tokens": 0,
                  "charge_units": 0, "charge_scale": 1000, "billed": False},
        "dispatch_state": "observed", "reconcile_state": "none",
    }
    dispatches, receipts = driver._bind_output_dispatches(
        [dispatch], [durable])
    assert dispatches[0]["initial_evidence_digest"] == "e" * 64
    assert dispatches[0]["durable_receipt_identity"] == durable[
        "receipt_identity"]
    assert dispatches[0]["durable_receipt"]["outcome"] == "failure"
    assert receipts[0]["measurement_status"] == "measured"


def test_broker_model_receipt_preserves_charge_scale(monkeypatch):
    from settlement import broker
    from settlement.common import ResultCode
    from settlement.gateway import ModelResponse, Usage

    captured = {}

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id, "{}", {}, Usage(
                    input_tokens=2, output_tokens=1, charge_units=3,
                    charge_scale=7, billed=True), "stop")

    monkeypatch.setattr(
        broker, "_advance",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.APPLIED, data={"dispatch_generation": 1}))
    monkeypatch.setattr(broker, "_revalidate", lambda *args, **kwargs: None)
    monkeypatch.setattr(broker, "_decided_receipt", lambda *args, **kwargs: False)

    def finish(*args, **kwargs):
        captured.update(args[2].receipt.content)
        return SimpleNamespace()

    monkeypatch.setattr(broker, "_finish_send", finish)
    op = broker.BrokerOp(
        operation_id="broker-charge-scale", effect=broker.MODEL_INFERENCE,
        payload={"model": "test", "messages": ({"role": "user", "content": "x"},),
                 "max_output_tokens": 10, "deadline_ms": 1000})
    broker._send_model("unused", {}, op, {}, Gateway(), None, None, False)
    assert captured["usage"]["charge_units"] == 3
    assert captured["usage"]["charge_scale"] == 7


def test_settled_broker_replay_is_not_counted_as_new_dispatch(monkeypatch):
    from settlement import broker, store
    from settlement.common import ResultCode
    from settlement.gateway import ModelRequest

    operation_id = "invl02-output-P1-qual-0011-a1"
    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.ALREADY_APPLIED, data={"reservation_id": "res-1"}))
    monkeypatch.setattr(
        broker, "read_operation",
        lambda *args, **kwargs: {
            "reservation_id": "res-1", "dispatch_state": "observed",
            "reconcile_state": "none", "settled": True})
    monkeypatch.setattr(
        store, "operation_receipts",
        lambda *args, **kwargs: [{
            "receipt_identity": "gw:settled", "outcome": "success",
            "content": {"text": "{}", "usage": {
                "input_tokens": 3, "output_tokens": 5, "charge_units": 0,
                "charge_scale": 7, "billed": False}}}])
    monkeypatch.setattr(store, "operation_receipt_conflicts",
                        lambda *args, **kwargs: [])
    durable = driver._DurableBrokerOutput(
        "unused", _OutputGateway([], live.OUTPUT_ROUTE),
        allocation_id="allocation-1", expected_route=live.OUTPUT_ROUTE)
    guard = driver._OutputGuard(
        durable, pinned_model=live.OUTPUT_ROUTE["requested_model"], ceiling=1)
    response = guard.infer(ModelRequest(
        model=live.OUTPUT_ROUTE["requested_model"],
        messages=({"role": "user", "content": "input"},),
        max_output_tokens=2048, deadline_ms=1000,
        operation_id=operation_id), evidence={
            "arm": "P1", "task": "rule-qual-0011", "attempt": 1,
            "raw_prompt": "input"})
    assert response.text == "{}"
    assert guard.guard_status()["dispatch_count"] == 0
    assert guard.guard_status()["replay_count"] == 1
    assert durable.last_replay is True
    assert len(durable.durable_receipts) == 1
    guard.finalize_evidence(operation_id, parse_outcome="accepted",
                            accepted_candidate_digest="a" * 64)
    assert guard.finalized_dispatches()[0]["replay"] is True


def test_output_route_uses_authorized_exact_ids():
    assert live.OUTPUT_ROUTE["requested_model"] == (
        "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free")
    assert live.OUTPUT_ROUTE["resolved_model"] == (
        "nvidia/nemotron-3-ultra-550b-a55b:free")


def test_model_list_preflight_accepts_observed_openrouter_catalog_shape():
    from settlement import gateway_http

    body = {"data": [
        {"id": "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
         "owned_by": "Openrouter"},
        {"id": "nvidia/nemotron-3-ultra-550b-a55b:free",
         "owned_by": "Openrouter"},
    ]}
    result = gateway_http.validate_model_route(body, live.OUTPUT_ROUTE)
    assert result == live.OUTPUT_ROUTE
    assert "data" not in result


@pytest.mark.parametrize("entry_overrides", [
    {"pricing": {"prompt": "0.000001", "completion": "0"}},
    {"tier": "paid"},
    {"pricing": None},
])
def test_model_list_preflight_refuses_untrustworthy_free_signal(entry_overrides):
    from settlement import gateway_http

    entry = {
        "id": live.OUTPUT_ROUTE["resolved_model"],
        "owned_by": "Openrouter",
    }
    entry.update(entry_overrides)
    body = {"data": [
        {"id": live.OUTPUT_ROUTE["requested_model"],
         "owned_by": "Openrouter"},
        entry,
    ]}
    with pytest.raises(ValueError, match="free|pricing|tier"):
        gateway_http.validate_model_route(body, live.OUTPUT_ROUTE)


@pytest.mark.parametrize("pricing", [
    {},
    {"prompt": "0"},
    {"completion": "0"},
])
def test_model_list_preflight_refuses_incomplete_pricing(pricing):
    from settlement import gateway_http

    body = {"data": [
        {"id": live.OUTPUT_ROUTE["requested_model"],
         "owned_by": "Openrouter"},
        {"id": live.OUTPUT_ROUTE["resolved_model"],
         "owned_by": "Openrouter", "pricing": pricing},
    ]}
    with pytest.raises(ValueError, match="pricing"):
        gateway_http.validate_model_route(body, live.OUTPUT_ROUTE)


def test_model_list_preflight_does_not_use_free_suffix_with_explicit_tier():
    from settlement import gateway_http

    body = {"data": [
        {"id": live.OUTPUT_ROUTE["requested_model"],
         "owned_by": "Openrouter"},
        {"id": live.OUTPUT_ROUTE["resolved_model"],
         "owned_by": "Openrouter", "tier": "free"},
    ]}
    with pytest.raises(ValueError, match="free|tier"):
        gateway_http.validate_model_route(body, live.OUTPUT_ROUTE)


def test_model_list_preflight_accepts_explicit_zero_pricing_without_free_suffix():
    from settlement import gateway_http

    expected = {
        **live.OUTPUT_ROUTE,
        "requested_model": live.OUTPUT_ROUTE["requested_model"].removesuffix(
            ":free"),
        "resolved_model": live.OUTPUT_ROUTE["resolved_model"].removesuffix(
            ":free"),
    }
    body = {"data": [
        {"id": expected["requested_model"],
         "pricing": {"prompt": "0", "completion": "0"}},
        {"id": expected["resolved_model"],
         "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    assert gateway_http.validate_model_route(body, expected) == expected


def test_model_list_preflight_refuses_missing_free_marker():
    from settlement import gateway_http

    expected = {
        **live.OUTPUT_ROUTE,
        "requested_model": live.OUTPUT_ROUTE["requested_model"].removesuffix(
            ":free"),
        "resolved_model": live.OUTPUT_ROUTE["resolved_model"].removesuffix(
            ":free"),
    }
    body = {"data": [
        {"id": expected["requested_model"], "owned_by": "Openrouter"},
        {"id": expected["resolved_model"], "owned_by": "Openrouter"},
    ]}
    with pytest.raises(ValueError, match="free signal"):
        gateway_http.validate_model_route(body, expected)


def test_model_list_preflight_refuses_provider_namespace_mismatch():
    from settlement import gateway_http

    resolved = "openai/" + live.OUTPUT_ROUTE["resolved_model"].split("/", 1)[1]
    expected = {**live.OUTPUT_ROUTE, "resolved_model": resolved}
    body = {"data": [
        {"id": expected["requested_model"], "owned_by": "Openrouter"},
        {"id": resolved, "provider": "nvidia", "owned_by": "Openrouter"},
    ]}
    with pytest.raises(ValueError, match="namespace"):
        gateway_http.validate_model_route(body, expected)


def test_model_list_preflight_refuses_missing_exact_ids():
    from settlement import gateway_http

    body = {"data": [
        {"id": live.OUTPUT_ROUTE["requested_model"],
         "owned_by": "Openrouter"},
    ]}
    with pytest.raises(ValueError, match="exact"):
        gateway_http.validate_model_route(body, live.OUTPUT_ROUTE)


def test_preflight_performs_authenticated_get_only(tmp_path):
    import httpx
    from settlement.gateway_http import HttpGatewayAdapter

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [
            {"id": live.OUTPUT_ROUTE["requested_model"],
             "owned_by": "Openrouter"},
            {"id": live.OUTPUT_ROUTE["resolved_model"],
             "owned_by": "Openrouter"},
        ]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = HttpGatewayAdapter(
        endpoint=live.OUTPUT_ROUTE["endpoint"], api_key="test-key",
        client=client, expected_route=live.OUTPUT_ROUTE)
    result = adapter.preflight_route(live.OUTPUT_ROUTE)
    assert result == live.OUTPUT_ROUTE
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/v1/models"
    assert calls[0].headers["authorization"] == "Bearer test-key"


def test_output_rejects_duplicate_initial_physical_dispatch(tmp_path):
    from experiments.ad01 import frontier

    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    first = result["candidate_view"]["dispatches"][0]
    duplicate = frontier.make_evidence_record(
        "gateway-dispatch", first["operation_id"], first["outcome"],
        attempt=1, arm=first["arm"], task_id=first["task_id"],
        input_digest=first["input_digest"],
        result_digest=first["result_digest"],
        dispatch_evidence_digest=first["dispatch_evidence_digest"],
        details=first["details"])
    for key, value in first.items():
        if key not in {"version", "kind", "evidence_digest", "receipt_identity",
                       "outcome", "operation_id", "attempt", "arm", "task_id",
                       "input_digest", "result_digest", "details",
                       "dispatch_evidence_digest"}:
            duplicate[key] = copy.deepcopy(value)
    result["candidate_view"]["dispatches"].append(duplicate)
    result["candidate_view"]["dispatch_count"] += 1
    result["candidate_view"]["automatic_retry_count"] = 1
    verified = _verify(result, tmp_path)
    assert verified["status"] == "fail"
    assert any(problem.startswith("duplicate-initial-dispatch")
               for problem in verified["problems"])


def test_output_rejects_repair_after_route_refusal(tmp_path):
    from experiments.ad01 import frontier

    freeze = driver.freeze_output(tmp_path)
    responses = _responses()
    responses[0] = {"text": _legal_text("qual", 11),
                    "model": "other/resolved:free"}
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(responses, freeze["route"]),
        model=freeze["route"]["requested_model"])
    first = result["candidate_view"]["dispatches"][0]
    assert first["parse_outcome"] == "route-refused"
    split = "qual" if first["task_id"].endswith("0011") else "audit"
    seed = 11 if split == "qual" else 23
    _task, session = driver._output_public_task(split, seed)
    history = [] if first["arm"] == "P1" else live.output_permitted_history()
    prompt = live.render_output_prompt(session.model_input(), history, 2)
    operation_id = live.output_operation_id(
        first["arm"], split, seed, 2)
    details = copy.deepcopy(first["details"])
    details["raw_payload"] = {"raw_prompt": prompt, "raw_response": "not json"}
    repair = frontier.make_evidence_record(
        "gateway-dispatch", operation_id, "unknown", attempt=2,
        arm=first["arm"], task_id=first["task_id"],
        input_digest=offline_recompute.source_digest(prompt), result_digest=None,
        details=details)
    for key in (
            "requested_model", "returned_model", "endpoint", "provider",
            "tier", "requested_output_cap", "response_digest", "prompt_digest",
            "raw_prompt", "raw_response", "stop_reason", "usage", "billed",
            "charge_units", "route_error"):
        if key in first:
            repair[key] = copy.deepcopy(first[key])
    repair.update({
        "attempt": 2, "parse_outcome": "parse-failed",
        "raw_prompt": prompt,
        "prompt_digest": offline_recompute.source_digest(prompt),
        "raw_response": "not json",
        "response_digest": offline_recompute.source_digest(
            "not json"), "accepted_candidate_digest": None,
    })
    result["candidate_view"]["dispatches"].append(repair)
    result["candidate_view"]["dispatch_count"] += 1
    verified = _verify(result, tmp_path)
    assert verified["status"] == "fail"
    assert any(problem.startswith("repair-after-route-refused")
               for problem in verified["problems"])


def test_output_run_refuses_retired_550b_study_root(tmp_path):
    out = tmp_path / "invl02-output-shape-final"
    out.mkdir()
    freeze = driver.freeze_output(out)
    freeze["study_root"] = "invl02-output-shape-final"
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    (out / "freeze.json").write_text(json.dumps(freeze))
    with pytest.raises(ValueError, match="retired output evidence"):
        driver.run_output(out, gateway=_OutputGateway(_responses(), freeze["route"]),
                          model=freeze["route"]["requested_model"])


def test_output_run_refuses_non_protocol_freeze(tmp_path):
    driver.freeze_e12(tmp_path)
    gateway = _OutputGateway(_responses(), live.OUTPUT_ROUTE)
    with pytest.raises(ValueError, match="output-shape protocol"):
        driver.run_output(tmp_path, gateway=gateway,
                          model=live.OUTPUT_ROUTE["requested_model"])


def test_output_live_requires_preflight_before_inference(tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(driver, "_live_model",
                        lambda: freeze["route"]["requested_model"])
    monkeypatch.setattr(driver, "_authorize",
                        lambda *args, **kwargs: {"allocation_id": "allocation-1"})

    class Gateway:
        calls = 0

        def preflight_route(self, route):
            self.calls += 1
            return route

        def infer(self, request):
            raise AssertionError("inference started without a preflight record")

    gateway = Gateway()
    monkeypatch.setattr(driver, "_live_gateway", lambda route: gateway)
    result = driver.run_output_live("unused", tmp_path)
    assert result["status"] == "unavailable"
    assert "preflight" in result["reason"]
    assert gateway.calls == 0


def test_output_live_rejects_changed_fresh_preflight_before_inference(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    (tmp_path / "preflight.json").write_text(json.dumps({
        "route": freeze["route"], "route_digest": driver._digest(freeze["route"])}))
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(driver, "_live_model",
                        lambda: freeze["route"]["requested_model"])
    monkeypatch.setattr(driver, "_authorize",
                        lambda *args, **kwargs: {"allocation_id": "allocation-1"})

    class Gateway:
        calls = 0

        def preflight_route(self, route):
            self.calls += 1
            return {**route, "endpoint": "http://changed.invalid/v1"}

        def infer(self, request):
            raise AssertionError("inference started after a changed route")

    gateway = Gateway()
    monkeypatch.setattr(driver, "_live_gateway", lambda route: gateway)
    monkeypatch.setattr("settlement.broker.scan_prepared",
                        lambda *args, **kwargs: None)
    result = driver.run_output_live("unused", tmp_path)
    assert result["status"] == "unavailable"
    assert "preflight" in result["reason"]
    assert gateway.calls == 1


def test_run_cli_returns_nonzero_for_unavailable_or_incomplete_statuses(
        monkeypatch, capsys):
    monkeypatch.setattr(driver, "run_e0", lambda *args: {
        "status": "unavailable", "live": {"model_calls": 0},
        "guard": {"dispatch_count": 0}})
    monkeypatch.setattr(driver, "run_e12", lambda *args: {
        "status": "incomplete", "model_total": 0})
    monkeypatch.setattr(driver, "run_e3", lambda *args: {
        "status": "unavailable"})
    monkeypatch.setattr(driver, "export_m4_bundle", lambda *args: {
        "status": "incomplete", "freeze": {"tasks": {}}, "use_records": []})

    assert driver.main([
        "run-e0", "--dsn", "unused", "--out", "unused"]) == 1
    assert driver.main([
        "run-e12", "--dsn", "unused", "--out", "unused"]) == 1
    assert driver.main([
        "run-e3", "--dsn", "unused", "--out", "unused", "--e12",
        "unused"]) == 1
    assert driver.main([
        "export-m4", "--bundle", "unused"]) == 1
    assert "e0 live=0" in capsys.readouterr().out


def test_run_cli_returns_zero_for_available_or_eligible_statuses(
        monkeypatch, capsys):
    monkeypatch.setattr(driver, "run_e0", lambda *args: {
        "status": "available", "live": {"model_calls": 0},
        "guard": {"dispatch_count": 0}})
    monkeypatch.setattr(driver, "run_e12", lambda *args: {
        "status": "available", "model_total": 0})
    monkeypatch.setattr(driver, "run_e3", lambda *args: {
        "status": "eligibility-screen", "execution": "unavailable"})
    monkeypatch.setattr(driver, "export_m4_bundle", lambda *args: {
        "status": "available", "freeze": {"tasks": {}}, "use_records": []})

    assert driver.main([
        "run-e0", "--dsn", "unused", "--out", "unused"]) == 0
    assert driver.main([
        "run-e12", "--dsn", "unused", "--out", "unused"]) == 0
    assert driver.main([
        "run-e3", "--dsn", "unused", "--out", "unused", "--e12",
        "unused"]) == 0
    assert driver.main([
        "export-m4", "--bundle", "unused"]) == 0
    assert "e3 eligibility-screen" in capsys.readouterr().out


@pytest.mark.parametrize("status", ["unavailable", "incomplete"])
def test_output_cli_returns_nonzero_for_noncomplete_run(tmp_path, monkeypatch,
                                                        status, capsys):
    monkeypatch.setattr(
        driver, "run_output_live",
        lambda dsn, out: {"status": status})
    result = driver.main([
        "run-output", "--dsn", "unused", "--out", str(tmp_path)])
    assert result == 1
    assert "output status=%s" % status in capsys.readouterr().out


def test_output_cli_returns_zero_for_complete_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        driver, "run_output_live",
        lambda dsn, out: {"status": "available"})
    result = driver.main([
        "run-output", "--dsn", "unused", "--out", str(tmp_path)])
    assert result == 0
    assert "output status=available" in capsys.readouterr().out


def test_ad01_cli_refuses_live_and_recorded_modes_together():
    with pytest.raises(SystemExit) as raised:
        ad01_cli.main([
            "run", "--dsn", "unused", "--world", "0", "--arm", "I",
            "--model", "live/model", "--recordings", "recordings.json"])
    assert raised.value.code == 2


def test_ad01_gateway_refuses_live_and_recorded_modes_together():
    with pytest.raises(ValueError, match="mutually exclusive"):
        ad01_cli._gateway("live/model", "recordings.json")


def test_ad01_cli_labels_the_doubled_harness_truthfully():
    args = SimpleNamespace(
        model="", recordings="", dsn="", world=0, arm="I", tasks="",
        max_boundaries=1, agenda_authorized=None, policy_release=None)

    configured = ad01_cli._campaign_kwargs(args, 0, "I", "ad01-w0-I-0")

    assert configured["model"] == "fake-harness"
    assert configured["execution_mode"] == "doubled"


def test_scorer_private_is_a_bound_canonical_envelope(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    assert private["schema"] == "invl02-output-scorer-private-v1"
    assert private["protocol"] == freeze["protocol"]
    assert private["study_root"] == freeze["study_root"]
    assert private["run_id"] == freeze["run_id"]
    assert private["freeze_digest"] == freeze["freeze_digest"]
    assert private["envelope_digest"] == offline_recompute.source_digest(
        offline_recompute.canonical({
            key: value for key, value in private.items()
            if key != "envelope_digest"}))
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})

    verified = offline_recompute.verify_bundle(result, private)
    assert verified["status"] == "pass", verified["problems"]


def test_canonical_output_verifier_requires_private_scorer_envelope(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})

    verified = offline_recompute.verify_bundle(result)

    assert verified["status"] == "fail"
    assert "scorer-private-missing" in verified["problems"]


def test_private_scorer_envelope_rejects_relabelled_study(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    private = json.loads((tmp_path / "scorer-private.json").read_text())
    private["study_root"] = "another-study"
    private["envelope_digest"] = offline_recompute.source_digest(
        offline_recompute.canonical({
            key: value for key, value in private.items()
            if key != "envelope_digest"}))

    verified = offline_recompute.verify_bundle(result, private)

    assert verified["status"] == "fail"
    assert "scorer-private-study-root-mismatch" in verified["problems"]


def test_recompute_returns_structured_failure_for_unreadable_declared_artifact(
        tmp_path):
    driver.freeze_output(tmp_path)
    (tmp_path / "output-run.json").write_text("{\n")

    verified = driver.recompute(tmp_path)

    assert verified["status"] == "fail"
    assert verified["problems"] == ["declared-artifact-unavailable"]


def test_recompute_rejects_mixed_output_and_m4_artifacts(tmp_path):
    from test_m4_offline_recompute import demo_bundle

    out = tmp_path / "mixed"
    freeze = driver.freeze_output(out)
    result = driver.run_output(
        out, gateway=_OutputGateway(_responses(), freeze["route"]),
        model=freeze["route"]["requested_model"])
    _durable_receipts(result, usage_overrides={
        "charge_scale": 1000, "charge_units": 0})
    (out / "output-run.json").write_text(json.dumps(result) + "\n")
    m4 = demo_bundle()
    (out / "m4-bundle.json").write_text(json.dumps(m4) + "\n")

    verified = driver.recompute(out)

    assert verified["status"] == "fail"
    assert "mixed-study-artifacts" in verified["problems"]


def test_recompute_selects_m4_by_declared_root_not_misnamed_file(tmp_path):
    from test_m4_offline_recompute import demo_bundle

    out = tmp_path / "m4"
    out.mkdir()
    m4 = demo_bundle()
    (out / "freeze.json").write_text(json.dumps(m4["freeze"]) + "\n")
    (out / "m4-bundle.json").write_text(json.dumps(m4) + "\n")
    (out / "output-run.json").write_text(json.dumps(m4) + "\n")

    verified = driver.recompute(out)

    assert verified["status"] == "pass", verified["problems"]
    assert verified["study_status"] is None
