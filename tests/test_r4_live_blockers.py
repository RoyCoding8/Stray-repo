from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from experiments.ad01 import live_construct as live
from experiments.ad01 import offline_recompute
from scripts import invl02_live as driver
from settlement.common import ResultCode
from settlement.gateway import GatewayError, ModelRequest
from test_output_evidence import (
    _legal_text,
    _OutputGateway,
    _responses,
    _route_response,
)


_USAGE = {
    "input_tokens": 3,
    "output_tokens": 5,
    "charge_units": 0,
    "charge_scale": 7,
    "provider_enforced_ceiling": True,
    "billed": False,
}


def _operation_id(freeze, *, arm="P1", split="audit", seed=23, attempt=1):
    return live.output_operation_id(
        arm, split, seed, attempt, round_run_id=freeze["run_id"])


def _raw_receipt(operation_id, text, route, identity):
    return {
        "operation_id": operation_id,
        "receipt_identity": identity,
        "outcome": "success",
        "content": {
            "text": text,
            "model_meta": {
                "endpoint": route["endpoint"],
                "model": route["resolved_model"],
                "provider": route["provider"],
                "tier": route["tier"],
            },
            "stop_reason": "stop",
            "usage": copy.deepcopy(_USAGE),
        },
    }


def _model_receipt(operation_id, response, identity):
    return {
        "operation_id": operation_id,
        "receipt_identity": identity,
        "outcome": "failure" if isinstance(response, GatewayError) else "success",
        "content": {} if isinstance(response, GatewayError) else {
            "text": response.text,
            "model_meta": copy.deepcopy(response.model_meta),
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "charge_units": response.usage.charge_units,
                "charge_scale": response.usage.charge_scale,
                "provider_enforced_ceiling": (
                    response.usage.provider_enforced_ceiling),
                "billed": response.usage.billed,
            },
        },
    }


def _operation(operation_id):
    return {
        "reservation_id": f"reservation:{operation_id}",
        "exposure": 1,
        "dispatch_state": "observed",
        "reconcile_state": "none",
        "settled": True,
    }


def _install_dynamic_broker(monkeypatch, gateway, *, replay_operations=None,
                            replay_receipts=None, unsettled_operations=None):
    from settlement import broker, store

    replay_operations = dict(replay_operations or {})
    replay_receipts = dict(replay_receipts or {})
    unsettled_operations = dict(unsettled_operations or {})
    receipts = dict(replay_receipts)
    settled = set(replay_operations)
    sent = []

    def ensure_operation(_dsn, *, operation_id, **_kwargs):
        if (operation_id in replay_operations
                or operation_id in unsettled_operations):
            return SimpleNamespace(
                code=ResultCode.ALREADY_APPLIED,
                data={"reservation_id": f"reservation:{operation_id}"})
        return SimpleNamespace(
            code=ResultCode.APPLIED,
            data={"reservation_id": f"reservation:{operation_id}"})

    def dispatch_operation(_dsn, operation_id, *, gateway, **_kwargs):
        sent.append(operation_id)
        request = ModelRequest(
            model=live.OUTPUT_ROUTE["requested_model"],
            messages=({"role": "user", "content": "unused"},),
            max_output_tokens=2048,
            deadline_ms=300_000,
            operation_id=operation_id,
        )
        response = gateway.infer(request)
        receipts[operation_id] = _model_receipt(
            operation_id, response, f"gw:{operation_id}")
        settled.add(operation_id)
        return SimpleNamespace(
            dispatch_state="observed",
            reconcile_state="none",
            settled=True,
            next_decision="terminal")

    def read_operation(_dsn, operation_id):
        operation = _operation(operation_id)
        operation["settled"] = operation_id in settled
        return operation

    monkeypatch.setattr(broker, "ensure_operation", ensure_operation)
    monkeypatch.setattr(broker, "dispatch_operation", dispatch_operation)
    monkeypatch.setattr(broker, "read_operation", read_operation)
    monkeypatch.setattr(
        store, "operation_receipts",
        lambda _dsn, operation_id: ([copy.deepcopy(receipts[operation_id])]
                                    if operation_id in receipts else []))
    monkeypatch.setattr(
        store, "operation_receipt_conflicts", lambda *_args, **_kwargs: [])
    return sent


def _write_prior(out, freeze, dispatches, receipts):
    prior = {
        "schema": offline_recompute.OUTPUT_SCHEMA,
        "protocol": freeze,
        "protocol_id": freeze["protocol"],
        "study": freeze["study"],
        "study_root": freeze["study_root"],
        "run_id": freeze["run_id"],
        "source_identity": freeze["source_identity"],
        "freeze_digest": freeze["freeze_digest"],
        "status": "incomplete",
        "candidate_view": {
            "protocol": freeze["protocol"],
            "route": dict(freeze["route"]),
            "incumbent_control": [],
            "dispatch_count": len(dispatches),
            "physical_dispatch_count": len(dispatches),
            "replay_count": 0,
            "automatic_retry_count": 0,
            "dispatches": copy.deepcopy(dispatches),
            "durable_receipts": copy.deepcopy(receipts),
        },
    }
    driver._write_output_bundle(out, prior)


def _non_observed_dispatch(freeze):
    operation_id = _operation_id(freeze)

    def timeout(_request):
        raise TimeoutError("response lost after provider send")

    gateway = _OutputGateway([], freeze["route"])
    gateway.infer = timeout
    guard = driver._OutputGuard(
        gateway,
        pinned_model=freeze["route"]["requested_model"],
        ceiling=freeze["limits"]["max_dispatches"],
        automatic_retries=freeze["limits"]["automatic_retries"],
        expected_route=freeze["route"],
    )
    task, session = driver._output_public_task("audit", 23)
    prompt = live.render_output_prompt(session.model_input(), [], 1)
    with pytest.raises(TimeoutError):
        guard.infer(
            ModelRequest(
                model=freeze["route"]["requested_model"],
                messages=({"role": "user", "content": prompt},),
                max_output_tokens=2048,
                deadline_ms=300_000,
                operation_id=operation_id,
            ),
            evidence={
                "arm": "P1",
                "task": task["task_id"],
                "attempt": 1,
                "raw_prompt": prompt,
                "round": freeze["round"],
            },
        )
    return guard.finalized_dispatches()[0]


def _allow_synthetic_output_operations(monkeypatch):
    def operation_id(arm, split, seed, attempt, *, round_run_id):
        return "%s-%s-%04d-a%d-%s" % (
            run_id_prefix, arm, int(seed), int(attempt), round_run_id)

    run_id_prefix = "frozen"
    monkeypatch.setattr(live, "output_operation_id", operation_id)


def test_output_operation_ids_follow_frozen_repair_count(
        tmp_path, monkeypatch):
    _allow_synthetic_output_operations(monkeypatch)
    freeze = driver.freeze_output(tmp_path)
    freeze["limits"]["repairs_per_task"] = 2

    operation_ids = driver._output_operation_ids(freeze)

    assert len(operation_ids) == 12
    assert any(operation_id.endswith("-a3-%s" % freeze["run_id"])
               for operation_id in operation_ids)


def test_output_operation_ids_follow_frozen_non_p0_arms(
        tmp_path, monkeypatch):
    _allow_synthetic_output_operations(monkeypatch)
    freeze = driver.freeze_output(tmp_path)
    freeze["order"] = ["P0", "P1", "P2", "P3"]

    operation_ids = driver._output_operation_ids(freeze)

    assert len(operation_ids) == 12
    assert any("-P3-" in operation_id for operation_id in operation_ids)


def test_output_operation_ids_must_equal_frozen_dispatch_ceiling(
        tmp_path, monkeypatch):
    _allow_synthetic_output_operations(monkeypatch)
    freeze = driver.freeze_output(tmp_path)
    freeze["limits"]["repairs_per_task"] = 2

    with pytest.raises(ValueError, match="operation id space"):
        driver._output_already_spent(freeze, dsn="unused")


def test_resume_counts_durable_store_when_evidence_claims_zero_dispatches(
        tmp_path, migrated_db, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    _write_prior(tmp_path, freeze, [], [])
    from settlement import broker, store
    from settlement.common import Command

    assert store.seed_allocation(
        migrated_db,
        Command(request_id="r4-test-allocation", payload={
            "allocation_id": "r4-test-allocation",
            "domain": "study",
            "authorized": 10000,
        })).code == ResultCode.APPLIED
    prepared = broker.ensure_operation(
        migrated_db,
        operation_id=operation_id,
        effect=broker.MODEL_INFERENCE,
        payload={
            "model": freeze["route"]["requested_model"],
            "messages": [{"role": "user", "content": "lost response"}],
            "max_output_tokens": 2048,
            "deadline_ms": 300_000,
        },
        allocation_id="r4-test-allocation",
    )

    assert prepared.code == ResultCode.APPLIED, prepared.detail
    gateway = _OutputGateway([], freeze["route"])
    attempted = []

    def infer(request):
        attempted.append(request.operation_id)
        raise TimeoutError("response lost after provider send")

    gateway.infer = infer
    dispatched = broker.dispatch_operation(
        migrated_db, operation_id, gateway=gateway)
    assert dispatched.dispatch_state == "unresolved"
    assert attempted == [operation_id]
    budgets = []

    def capture_budget(_delegate, *, ceiling, already_spent, **_kwargs):
        budgets.append((ceiling, already_spent))
        raise RuntimeError("stop after reading durable budget")

    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model", lambda: freeze["route"]["requested_model"])
    monkeypatch.setattr(driver, "_require_output_preflight", lambda *_args: None)
    monkeypatch.setattr(driver, "preflight_route", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(driver, "_live_gateway", lambda _route: gateway)
    monkeypatch.setattr(driver, "_authorize", lambda *_args, **_kwargs: {
        "allocation_id": "r4-test-allocation"})
    monkeypatch.setattr(broker, "scan_prepared", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(driver, "_OutputGuard", capture_budget)

    driver.run_output_live(migrated_db, tmp_path)

    assert budgets == [(8, 1)]
    assert budgets[0][0] - budgets[0][1] == 7
    assert attempted == [operation_id]


def test_live_timeout_bundle_reports_every_physical_dispatch(tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    attempted = []
    gateway = _OutputGateway(
        [_route_response(_legal_text("qual", 11), freeze["route"])],
        freeze["route"])
    original_infer = gateway.infer
    lost_operation = _operation_id(freeze)

    def infer(request):
        attempted.append(request.operation_id)
        if request.operation_id == lost_operation:
            raise TimeoutError("response lost after provider send")
        return original_infer(request)

    gateway.infer = infer
    from settlement import broker

    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda _dsn, *, operation_id, **_kwargs: SimpleNamespace(
            code=ResultCode.APPLIED,
            data={"reservation_id": f"reservation:{operation_id}"}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda _dsn, operation_id, *, gateway: _dispatch_response(
            gateway, operation_id))
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model", lambda: freeze["route"]["requested_model"])
    monkeypatch.setattr(driver, "_authorize", lambda *_args, **_kwargs: {
        "allocation_id": "allocation-1"})
    monkeypatch.setattr(driver, "_live_gateway", lambda _route: gateway)
    monkeypatch.setattr(driver, "_require_output_preflight", lambda *_args: None)
    monkeypatch.setattr(driver, "preflight_route", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(broker, "scan_prepared", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(driver, "_output_already_spent", lambda *args, **kwargs: 0)

    result = driver.run_output_live("unused", tmp_path)

    view = result["candidate_view"]
    assert len(attempted) == 1
    assert {entry["operation_id"] for entry in view["dispatches"]} == set(attempted)
    # The send never reached the store, so the bundle cannot claim a count
    # that reconciles against it. The dispatch itself is still reported.
    assert view["dispatch_evidence"] == {
        "state": "incomplete",
        "store_operation_count": 0,
        "file_dispatch_count": 1,
        "file_physical_dispatch_count": 1,
    }
    assert view["dispatch_count"] == "unknown"
    assert view["physical_dispatch_count"] == "unknown"


def _dispatch_response(gateway, operation_id):
    request = ModelRequest(
        model=gateway.route["requested_model"],
        messages=({"role": "user", "content": "unused"},),
        max_output_tokens=2048,
        deadline_ms=300_000,
        operation_id=operation_id,
    )
    gateway.infer(request)
    return SimpleNamespace(
        dispatch_state="observed",
        reconcile_state="none",
        settled=True,
        next_decision="terminal")


def test_resume_accounts_prior_non_observed_dispatch_exactly_once(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    lost_operation = _operation_id(freeze)
    prior = _non_observed_dispatch(freeze)
    assert prior["operation_id"] == lost_operation
    _write_prior(tmp_path, freeze, [prior], [])

    replay = _raw_receipt(
        lost_operation, _legal_text("audit", 23), freeze["route"],
        "gw:recovered-lost-audit")
    gateway = _OutputGateway([
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response(_legal_text("audit", 23), freeze["route"]),
    ], freeze["route"])
    sent = _install_dynamic_broker(
        monkeypatch,
        gateway,
        replay_operations={lost_operation: True},
        replay_receipts={lost_operation: replay},
    )
    durable = driver._DurableBrokerOutput(
        "unused", gateway, allocation_id="allocation-1",
        expected_route=freeze["route"])

    resumed = driver.run_output(
        tmp_path, gateway=durable,
        model=freeze["route"]["requested_model"])

    view = resumed["candidate_view"]
    assert lost_operation not in sent
    assert len(sent) == 3
    assert view["dispatch_count"] == 5
    assert view["physical_dispatch_count"] == 4
    assert view["replay_count"] == 1
    assert sum(entry["operation_id"] == lost_operation
               for entry in view["dispatches"]) == 2
    assert sum(entry["operation_id"] == lost_operation and not entry.get("replay")
               for entry in view["dispatches"]) == 1
    assert sum(entry["operation_id"] == lost_operation and entry.get("replay")
               for entry in view["dispatches"]) == 1


def test_resume_uses_recovered_receipt_without_foreign_prior_receipt(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    lost_operation = _operation_id(freeze)
    source_responses = [
        _route_response(_legal_text("audit", 23), freeze["route"]),
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response(_legal_text("audit", 23), freeze["route"]),
        _route_response(_legal_text("qual", 11), freeze["route"]),
    ]
    source_result = driver.run_output(
        tmp_path,
        gateway=_OutputGateway(source_responses, freeze["route"]),
        model=freeze["route"]["requested_model"])
    lost = next(
        entry for entry in source_result["candidate_view"]["dispatches"]
        if entry["operation_id"] == lost_operation)
    old_receipt = {
        "operation_id": lost_operation,
        "receipt_identity": "gw:lost-local",
        "outcome": "success",
        "settled": True,
        "source_digest": lost["source_digest"],
        "artifact_digest": lost["artifact_digest"],
        "input_digest": lost["input_digest"],
        "result_digest": lost["result_digest"],
        "dispatch_evidence_digest": lost["dispatch_evidence_digest"],
        "dispatch_state": "observed",
        "reconcile_state": "none",
        "usage": copy.deepcopy(_USAGE),
        "measurement_status": "measured",
    }
    _write_prior(tmp_path, freeze, [lost], [old_receipt])

    recovered = _raw_receipt(
        lost_operation, _legal_text("audit", 23), freeze["route"],
        "gw:recovered-authority")
    gateway = _OutputGateway([
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response(_legal_text("audit", 23), freeze["route"]),
    ], freeze["route"])
    _install_dynamic_broker(
        monkeypatch,
        gateway,
        replay_operations={lost_operation: True},
        replay_receipts={lost_operation: recovered},
    )
    durable = driver._DurableBrokerOutput(
        "unused", gateway, allocation_id="allocation-1",
        expected_route=freeze["route"])

    resumed = driver.run_output(
        tmp_path, gateway=durable,
        model=freeze["route"]["requested_model"])
    written = json.loads((tmp_path / "output-run.json").read_text())
    receipts = [
        receipt for receipt in written["candidate_view"]["durable_receipts"]
        if receipt["operation_id"] == lost_operation]
    assert len(receipts) == 1
    assert receipts[0]["receipt_identity"] == "gw:recovered-authority"
    assert [entry["raw_response"] for entry in written["candidate_view"][
        "dispatches"] if entry["operation_id"] == lost_operation] == [None, _legal_text(
            "audit", 23)]


def test_unsettled_lost_dispatch_repair_respects_eight_dispatch_ceiling(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    lost_operation = _operation_id(freeze)
    prior = _non_observed_dispatch(freeze)
    _write_prior(tmp_path, freeze, [prior], [])

    responses = [
        _route_response("not json", freeze["route"]),
        _route_response(_legal_text("audit", 23), freeze["route"]),
        _route_response("not json", freeze["route"]),
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response("not json", freeze["route"]),
        _route_response(_legal_text("audit", 23), freeze["route"]),
        _route_response("not json", freeze["route"]),
        _route_response(_legal_text("qual", 11), freeze["route"]),
    ]
    gateway = _OutputGateway(responses, freeze["route"])
    sent = _install_dynamic_broker(
        monkeypatch, gateway, unsettled_operations={lost_operation: True})
    durable = driver._DurableBrokerOutput(
        "unused", gateway, allocation_id="allocation-1",
        expected_route=freeze["route"])

    resumed = driver.run_output(
        tmp_path, gateway=durable,
        model=freeze["route"]["requested_model"])

    view = resumed["candidate_view"]
    assert 1 + len(sent) <= freeze["limits"]["max_dispatches"]
    assert view["physical_dispatch_count"] == 1 + len(sent)
    assert sent.count(lost_operation) <= 1


def test_mixed_observed_and_non_observed_bundle_satisfies_receipt_bijection(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    lost_operation = _operation_id(freeze)
    prior = _non_observed_dispatch(freeze)
    _write_prior(tmp_path, freeze, [prior], [])

    replay = _raw_receipt(
        lost_operation, _legal_text("audit", 23), freeze["route"],
        "gw:recovered-lost-audit")
    gateway = _OutputGateway([
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response(_legal_text("qual", 11), freeze["route"]),
        _route_response(_legal_text("audit", 23), freeze["route"]),
    ], freeze["route"])
    _install_dynamic_broker(
        monkeypatch,
        gateway,
        replay_operations={lost_operation: True},
        replay_receipts={lost_operation: replay},
    )
    durable = driver._DurableBrokerOutput(
        "unused", gateway, allocation_id="allocation-1",
        expected_route=freeze["route"])
    resumed = driver.run_output(
        tmp_path, gateway=durable,
        model=freeze["route"]["requested_model"])
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    verified = offline_recompute.verify_bundle(resumed, private)

    assert "dispatch-operation-receipt-bijection" not in verified["problems"]


def test_unresolved_lost_dispatch_is_not_silently_dropped_from_candidate_view(
        tmp_path):
    freeze = driver.freeze_output(tmp_path)
    lost_operation = _operation_id(freeze)
    prior = _non_observed_dispatch(freeze)
    current = copy.deepcopy(prior)
    current["raw_response"] = _legal_text("audit", 23)
    current["response_digest"] = offline_recompute.source_digest(
        current["raw_response"])
    current["parse_outcome"] = "accepted"

    dispatches, _receipts = driver._merge_output_evidence(
        tmp_path, freeze, [current], [])

    lost = [entry for entry in dispatches
            if entry["operation_id"] == lost_operation]
    assert len(lost) == 2
    assert any(entry["raw_response"] is None for entry in lost)
    assert any(entry["raw_response"] == _legal_text("audit", 23)
               for entry in lost)
