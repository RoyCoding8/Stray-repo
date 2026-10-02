from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from experiments.ad01 import live_construct as live
from experiments.ad01 import offline_recompute
from scripts import invl02_live as driver
from settlement.common import ResultCode
from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    ModelRequest,
)


USAGE = {
    "input_tokens": 3,
    "output_tokens": 5,
    "charge_units": 1,
    "charge_scale": 7,
    "provider_enforced_ceiling": True,
    "billed": True,
}


class _CountingGateway:
    def __init__(self):
        self.calls = 0

    def infer(self, request):
        self.calls += 1
        return GatewayError(
            GatewayErrorKind.PROTOCOL,
            "route response refused before send",
            False,
            request.operation_id,
            None,
            route_error=GatewayRouteError.RESPONSE_METADATA,
        )

    def check_discovery(self):
        return "configured"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True


def _operation_id(freeze: dict, *, arm="P1", split="qual", seed=11):
    return live.output_operation_id(
        arm, split, seed, 1, round_run_id=freeze["run_id"])


def _request(operation_id: str) -> ModelRequest:
    return ModelRequest(
        model=driver._live_route()["requested_model"],
        messages=({"role": "user", "content": "input"},),
        max_output_tokens=2048,
        deadline_ms=1000,
        operation_id=operation_id,
    )


def _success_receipt(operation_id: str) -> dict:
    return {
        "operation_id": operation_id,
        "receipt_identity": "gw:resume-success",
        "outcome": "success",
        "content": {
            "text": "durable response",
            "model_meta": {},
            "stop_reason": "stop",
            "usage": copy.deepcopy(USAGE),
        },
    }


def _pre_send_receipt(operation_id: str) -> dict:
    return {
        "operation_id": operation_id,
        "receipt_identity": "gw:resume-pre-send-refusal",
        "outcome": "failure",
        "content": {
            "error": "route response refused before send",
            "error_kind": GatewayErrorKind.PROTOCOL.value,
            "retryable": False,
            "response_class": "pre-send-route-refusal",
            "response_received": False,
            "response_status": None,
            "response_digest": None,
            "route_error": GatewayRouteError.RESPONSE_METADATA.value,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "charge_units": 0,
                "charge_scale": 7,
                "provider_enforced_ceiling": True,
                "billed": False,
            },
        },
    }


def _install_broker_fakes(
        monkeypatch, receipt: dict, *, replay: bool, operation: dict,
        prepared_data: dict | None = None):
    from settlement import broker, store

    prepared_data = copy.deepcopy(prepared_data) if prepared_data is not None else {
        "reservation_id": "reservation-1",
    }
    monkeypatch.setattr(
        broker,
        "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(
            code=ResultCode.ALREADY_APPLIED if replay else ResultCode.APPLIED,
            data=prepared_data,
        ),
    )
    monkeypatch.setattr(
        broker,
        "read_operation",
        lambda *args, **kwargs: copy.deepcopy(operation),
    )

    def dispatch(*args, **kwargs):
        if replay:
            raise AssertionError("replay attempted a physical dispatch")
        kwargs["gateway"].infer(_request(receipt["operation_id"]))
        return SimpleNamespace(
            dispatch_state="observed",
            reconcile_state="none",
            settled=True,
            next_decision="terminal",
        )

    monkeypatch.setattr(broker, "dispatch_operation", dispatch)
    monkeypatch.setattr(
        store,
        "operation_receipts",
        lambda *args, **kwargs: [copy.deepcopy(receipt)],
    )
    monkeypatch.setattr(
        store, "operation_receipt_conflicts", lambda *args, **kwargs: [])


def _durable_record(
        monkeypatch, receipt: dict, *, replay: bool, operation: dict,
        prepared_data: dict | None = None, dsn: str = "unused") -> dict:
    _install_broker_fakes(
        monkeypatch,
        receipt,
        replay=replay,
        operation=operation,
        prepared_data=prepared_data,
    )
    gateway = _CountingGateway()
    broker_output = driver._DurableBrokerOutput(
        dsn,
        gateway,
        allocation_id="allocation-1",
        expected_route=driver._live_route(),
    )
    broker_output.infer(_request(receipt["operation_id"]))
    assert len(broker_output.durable_receipts) == 1
    assert gateway.calls == (0 if replay else 1)
    return broker_output.durable_receipts[0]


def test_replay_keeps_missing_provider_ceiling_unknown(monkeypatch, tmp_path):
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    receipt = _success_receipt(operation_id)
    receipt["content"]["usage"].pop("provider_enforced_ceiling")
    operation = {
        "reservation_id": "reservation-1",
        "dispatch_state": "observed",
        "reconcile_state": "none",
        "settled": True,
    }
    _install_broker_fakes(
        monkeypatch,
        receipt,
        replay=True,
        operation=operation,
        prepared_data={"reservation_id": "reservation-1"},
    )
    gateway = _CountingGateway()
    broker_output = driver._DurableBrokerOutput(
        "unused",
        gateway,
        allocation_id="allocation-1",
        expected_route=driver._live_route(),
    )

    response = broker_output.infer(_request(operation_id))

    assert response.usage.provider_enforced_ceiling is None
    assert gateway.calls == 0


def test_settled_replay_reads_reservation_exposure(monkeypatch, tmp_path):
    from settlement import db
    from psycopg.rows import dict_row

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            assert sql == "SELECT amount, state FROM reservations WHERE id = %s"
            assert params == ("reservation-1",)

        def fetchone(self):
            return {"amount": 2294, "state": "settled"}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self, row_factory=dict_row):
            return Cursor()

        def commit(self):
            pass

    monkeypatch.setattr(db, "read_connect", lambda dsn: Connection())
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    record = _durable_record(
        monkeypatch,
        _success_receipt(operation_id),
        replay=True,
        operation={
            "reservation_id": "reservation-1",
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "settled": True,
        },
        prepared_data={"reservation_id": "reservation-1"},
        dsn="postgresql://ledger",
    )

    assert record["exposure"] == 2294
    assert record["unresolved_exposure"] == 0


def test_pre_send_refusal_has_no_provider_exposure(monkeypatch, tmp_path):
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    operation = {
        "reservation_id": "reservation-1",
        "exposure": 2294,
        "dispatch_state": "observed",
        "reconcile_state": "none",
        "settled": True,
    }
    fresh = _durable_record(
        monkeypatch, _pre_send_receipt(operation_id), replay=False,
        operation=operation)
    replay = _durable_record(
        monkeypatch, _pre_send_receipt(operation_id), replay=True,
        operation=operation)

    assert fresh["exposure"] == 0
    assert fresh["unresolved_exposure"] == 0
    assert replay["exposure"] == 0
    assert replay["unresolved_exposure"] == 0


def test_fresh_dispatch_and_settled_replay_have_identical_full_records(
        monkeypatch, tmp_path):
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    receipt = _success_receipt(operation_id)
    operation = {
        "reservation_id": "reservation-1",
        "exposure": 2294,
        "dispatch_state": "observed",
        "reconcile_state": "none",
        "settled": True,
    }
    fresh = _durable_record(
        monkeypatch, receipt, replay=False, operation=operation)
    replay = _durable_record(
        monkeypatch, receipt, replay=True, operation=operation)

    assert replay == fresh
    assert replay["result"] == {"raw_response": "durable response"}
    assert replay["result_digest"] == hashlib.sha256(
        b"durable response").hexdigest()


def _run_durable_resume(tmp_path, monkeypatch, freeze, operation_id, receipt):
    operation = {
        "reservation_id": "reservation-1",
        "exposure": 2294,
        "dispatch_state": "observed",
        "reconcile_state": "none",
        "settled": True,
    }
    gateway = _CountingGateway()
    _install_broker_fakes(
        monkeypatch, receipt, replay=False, operation=operation)
    delegate = driver._DurableBrokerOutput(
        "unused", gateway, allocation_id="allocation-1",
        expected_route=driver._live_route())
    first = driver.run_output(
        tmp_path, gateway=delegate, model=freeze["route"]["requested_model"])
    assert gateway.calls == 1

    first_replay = None
    for _ in range(2):
        _install_broker_fakes(
            monkeypatch, receipt, replay=True, operation=operation)
        delegate = driver._DurableBrokerOutput(
            "unused", gateway, allocation_id="allocation-1",
            expected_route=driver._live_route())
        if first_replay is None:
            first_replay = driver.run_output(
                tmp_path, gateway=delegate,
                model=freeze["route"]["requested_model"])
        else:
            driver.run_output(
                tmp_path, gateway=delegate,
                model=freeze["route"]["requested_model"])
    return first, first_replay, gateway


def test_resume_replays_durable_operation_without_second_send(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    first, resumed, gateway = _run_durable_resume(
        tmp_path, monkeypatch, freeze, operation_id,
        _pre_send_receipt(operation_id))
    first_written = json.loads((tmp_path / "output-run.json").read_text())
    second = driver.run_output(
        tmp_path, gateway=_CountingGateway(),
        model=freeze["route"]["requested_model"])

    assert gateway.calls == 1
    assert first["candidate_view"]["physical_dispatch_count"] == 1
    assert first["candidate_view"]["replay_count"] == 0
    assert resumed["candidate_view"]["replay_count"] == 1
    assert resumed["candidate_view"]["physical_dispatch_count"] == 1
    assert resumed["candidate_view"]["replay_count"] == 1
    assert resumed["candidate_view"]["automatic_retry_count"] == 0
    assert second["candidate_view"]["durable_receipts"][0]["exposure"] == 0
    assert first_written["candidate_view"]["durable_receipts"][0][
        "exposure"] == 0


def test_resume_bundle_satisfies_receipt_bijection(tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    _run_durable_resume(
        tmp_path, monkeypatch, freeze, operation_id,
        _pre_send_receipt(operation_id))
    bundle = json.loads((tmp_path / "output-run.json").read_text())
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    verified = offline_recompute.verify_bundle(bundle, private)

    assert "replay-physical-operation-missing" not in verified["problems"]


def test_honest_route_refusal_is_not_reported_as_corruption(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_CountingGateway(),
        model=freeze["route"]["requested_model"])
    private = json.loads((tmp_path / "scorer-private.json").read_text())

    verified = offline_recompute.verify_bundle(result, private)
    refused = next(dispatch for dispatch in result["candidate_view"]["dispatches"]
                   if dispatch["parse_outcome"] == "route-refused")

    assert refused["raw_response"] is None
    assert refused["provider"] is None
    assert "route-metadata-mismatch" not in verified["problems"]
    assert "response-digest-mismatch" not in verified["problems"]
    assert "study-incomplete" in verified["problems"]


def test_tampered_observed_response_is_still_reported_as_corruption(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    result = driver.run_output(
        tmp_path, gateway=_CountingGateway(),
        model=freeze["route"]["requested_model"])
    private = json.loads((tmp_path / "scorer-private.json").read_text())
    dispatch = next(dispatch for dispatch in result["candidate_view"]["dispatches"]
                    if dispatch["parse_outcome"] == "route-refused")
    dispatch["parse_outcome"] = "parse-failed"
    dispatch["raw_response"] = "tampered"
    dispatch["response_digest"] = "0" * 64

    verified = offline_recompute.verify_bundle(result, private)

    assert "route-metadata-mismatch" in verified["problems"]
    assert "response-digest-mismatch" in verified["problems"]


def test_prior_evidence_with_foreign_source_identity_is_refused(
        tmp_path):
    freeze = driver.freeze_output(tmp_path)
    first = driver.run_output(
        tmp_path,
        gateway=_CountingGateway(),
        model=freeze["route"]["requested_model"],
    )
    foreign = copy.deepcopy(first)
    foreign["source_identity"] = "foreign-source-identity"
    path = tmp_path / "output-run.json"
    path.write_text(json.dumps(foreign, sort_keys=True, indent=1) + "\n")
    before = path.read_bytes()

    with pytest.raises(ValueError, match="identity mismatch"):
        driver.run_output(
            tmp_path,
            gateway=_CountingGateway(),
            model=freeze["route"]["requested_model"])

    assert path.read_bytes() == before


def test_prior_evidence_with_malformed_identity_is_refused(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    first = driver.run_output(
        tmp_path,
        gateway=_CountingGateway(),
        model=freeze["route"]["requested_model"],
    )
    first["candidate_view"]["dispatches"][0]["operation_id"] = ["bad"]
    (tmp_path / "output-run.json").write_text(
        json.dumps(first, sort_keys=True, indent=1) + "\n")

    with pytest.raises(ValueError, match="malformed dispatch"):
        driver.run_output(
            tmp_path,
            gateway=_CountingGateway(),
            model=freeze["route"]["requested_model"])


def test_unavailable_exposure_is_unknown(monkeypatch, tmp_path):
    freeze = driver.freeze_output(tmp_path)
    operation_id = _operation_id(freeze)
    record = _durable_record(
        monkeypatch,
        _success_receipt(operation_id),
        replay=True,
        operation={
            "reservation_id": "reservation-1",
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "settled": True,
        },
        prepared_data={"reservation_id": "reservation-1"},
    )

    assert record["exposure"] == "unknown"
    assert record["unresolved_exposure"] == "unknown"
