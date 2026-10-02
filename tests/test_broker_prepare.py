from __future__ import annotations

import uuid

from settlement import broker, store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _setup(dsn, authorized=1000):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": authorized}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _model_payload():
    return {"model": "m1", "messages": [{"role": "user", "content": "hi"}],
            "max_output_tokens": 16, "deadline_ms": 10_000}


def test_unknown_effect_rejected_before_any_reservation(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    result = broker.ensure_operation(dsn, operation_id="opx", effect="telepathy",
                                     payload={}, allocation_id="a1", attempt_id="att1")
    assert result.code == ResultCode.INVALID_INPUT
    assert broker.read_operation(dsn, "opx") is None
    assert store.allocation_status(dsn, "a1")["reserved"] == 0


def test_model_prepare_reserves_estimated_budget(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    result = broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                                     payload=_model_payload(), allocation_id="a1",
                                     attempt_id="att1", execution_version="exec-v1")
    assert result.code == ResultCode.APPLIED
    assert result.data["exposure"] == 17
    assert result.data["budget_kind"] == "estimated-budget"
    assert store.allocation_status(dsn, "a1")["reserved"] == 17
    row = broker.read_operation(dsn, "op1")
    assert row["dispatch_state"] == "prepared"
    assert row["payload"]["effect"] == "model-inference"


def test_model_exposure_scales_with_retries(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    result = broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                                     payload=_model_payload(), allocation_id="a1",
                                     attempt_id="att1", retries=2)
    assert result.data["exposure"] == 51


def test_sandbox_prepare_reserves_hard_ceiling(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    payload = {"profile": "local-process", "argv": ["/bin/true"], "timeout_ms": 8_000,
               "max_output_bytes": 1024}
    result = broker.ensure_operation(dsn, operation_id="op1", effect="sandbox-exec",
                                     payload=payload, allocation_id="a1", attempt_id="att1",
                                     retries=1)
    assert result.code == ResultCode.APPLIED
    assert result.data["exposure"] == 28
    assert result.data["budget_kind"] == "hard-ceiling"


def test_reensure_same_intent_is_idempotent(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    first = broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                                    payload=_model_payload(), allocation_id="a1", attempt_id="att1")
    second = broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                                     payload=_model_payload(), allocation_id="a1", attempt_id="att1")
    assert first.code == ResultCode.APPLIED
    assert second.code == ResultCode.ALREADY_APPLIED
    assert store.allocation_status(dsn, "a1")["reserved"] == 17


def test_reensure_clashing_intent_is_refused(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                            payload=_model_payload(), allocation_id="a1", attempt_id="att1")
    other = dict(_model_payload(), max_output_tokens=32)
    clash = broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                                    payload=other, allocation_id="a1", attempt_id="att1")
    assert clash.code == ResultCode.INVALID_INPUT


def test_insufficient_allocation_refuses_prepare(migrated_db):
    dsn = migrated_db
    _setup(dsn, authorized=5)
    result = broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                                     payload=_model_payload(), allocation_id="a1", attempt_id="att1")
    assert result.code == ResultCode.INSUFFICIENT_RESOURCES
    assert broker.read_operation(dsn, "op1") is None
