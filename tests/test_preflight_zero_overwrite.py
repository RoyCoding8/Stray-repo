from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts import invl02_live as driver
from settlement import broker, store
from settlement.common import Command, ResultCode
from test_output_evidence import (
    _legal_text,
    _OutputGateway,
    _responses,
    _route_response,
)


def _seed_durable_dispatch(dsn, freeze, operation_id):
    assert store.seed_allocation(
        dsn,
        Command(request_id="preflight-zero-allocation", payload={
            "allocation_id": "preflight-zero-allocation",
            "domain": "study",
            "authorized": 10000,
        })).code == ResultCode.APPLIED
    prepared = broker.ensure_operation(
        dsn,
        operation_id=operation_id,
        effect=broker.MODEL_INFERENCE,
        payload={
            "model": freeze["route"]["requested_model"],
            "messages": [{"role": "user", "content": "lost response"}],
            "max_output_tokens": 2048,
            "deadline_ms": 300_000,
        },
        allocation_id="preflight-zero-allocation",
    )
    assert prepared.code == ResultCode.APPLIED
    gateway = _OutputGateway(
        [_route_response(_legal_text("qual", 11), freeze["route"])],
        freeze["route"])
    dispatched = broker.dispatch_operation(
        dsn, operation_id, gateway=gateway)
    assert dispatched.settled is True
    assert [request.operation_id for request in gateway.requests] == [operation_id]


def _install_live_entry(tmp_path, monkeypatch, freeze):
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(
        driver, "_live_model",
        lambda: freeze["route"]["requested_model"])


def test_preflight_failure_reconciles_store_and_separates_unknown_from_zero(
        tmp_path, migrated_db, monkeypatch):
    spent_out = Path(tmp_path) / "spent"
    freeze = driver.freeze_output(spent_out)
    first = driver.run_output(
        spent_out,
        gateway=_OutputGateway(_responses(freeze["route"]), freeze["route"]),
        model=freeze["route"]["requested_model"])
    assert first["candidate_view"]["physical_dispatch_count"] > 0
    operation_id = first["candidate_view"]["dispatches"][0]["operation_id"]
    _seed_durable_dispatch(migrated_db, freeze, operation_id)

    lost_bundle = copy.deepcopy(first)
    lost_bundle["status"] = "incomplete"
    lost_bundle["candidate_view"].update({
        "dispatch_count": 0,
        "physical_dispatch_count": 0,
        "replay_count": 0,
        "dispatches": [],
        "durable_receipts": [],
    })
    driver._write_output_bundle(spent_out, lost_bundle)
    _install_live_entry(spent_out, monkeypatch, freeze)

    preflight_failure = driver.run_output_live(migrated_db, spent_out)

    spent_view = preflight_failure["candidate_view"]
    assert preflight_failure["status"] == "unavailable"
    assert spent_view["dispatch_count"] == "unknown"
    assert spent_view["physical_dispatch_count"] == "unknown"
    assert preflight_failure["unavailability"]["stage"] == "preflight"
    assert spent_view["dispatch_evidence"]["state"] == "incomplete"
    assert spent_view["dispatch_evidence"]["store_operation_count"] == 1
    assert json.loads((spent_out / "output-run.json").read_text())[
        "candidate_view"]["dispatch_evidence"] == spent_view["dispatch_evidence"]

    clean_out = Path(tmp_path) / "clean"
    clean_freeze = driver.freeze_output(clean_out)
    _install_live_entry(clean_out, monkeypatch, clean_freeze)

    clean_preflight = driver.run_output_live(migrated_db, clean_out)

    clean_view = clean_preflight["candidate_view"]
    assert clean_preflight["status"] == "unavailable"
    assert clean_preflight["unavailability"]["stage"] == "preflight"
    assert clean_view["dispatch_evidence"] == {
        "state": "reconciled",
        "store_operation_count": 0,
        "file_dispatch_count": 0,
        "file_physical_dispatch_count": 0,
    }
    assert clean_view["dispatch_count"] == 0
    assert clean_view["physical_dispatch_count"] == 0


def test_preflight_failure_keeps_dispatch_count_unknown_without_a_store(
        tmp_path, monkeypatch):
    freeze = driver.freeze_output(tmp_path)
    _install_live_entry(tmp_path, monkeypatch, freeze)

    result = driver.run_output_live("postgresql://invalid/unavailable", tmp_path)

    view = result["candidate_view"]
    assert result["status"] == "unavailable"
    assert view["dispatch_count"] == "unknown"
    assert view["physical_dispatch_count"] == "unknown"
    assert result["unavailability"]["stage"] == "preflight"
    assert view["dispatch_evidence"] == {
        "state": "unknown",
        "store_operation_count": "unknown",
        "file_dispatch_count": 0,
        "file_physical_dispatch_count": 0,
    }
