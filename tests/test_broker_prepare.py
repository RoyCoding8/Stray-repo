from __future__ import annotations

import uuid

from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.exec_profile import STOP_SETTLE_S


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


def test_model_retry_is_refused_before_any_reservation(migrated_db):
    """Retry scaling is not live, and the refusal is the decided rule.

    `59a10df` (2026-09-24) made `ensure_operation` refuse a non-zero
    `retries` with "use distinct operation identities". Exposure still
    multiplied by `retries + 1` for a while after, which is why this test
    once read `exposure == 51` for `retries=2`: a ceiling no caller can
    reach, asserted as if it could. Every live caller had already moved to
    distinct operation identities, and
    `tests/test_broker_route_recovery.py:513` asserts the refusal itself.

    The refusal is the correct rule, not a gate that was tightened by
    accident. One operation identity must mean one send, because a retry
    under the same identity is exactly what makes "was this charged twice?"
    unanswerable afterwards. So this asserts the refusal, and that it
    refuses *before* reserving: an exposure that gets reserved and then
    refused is a spend with no record of what spent it.
    """
    dsn = migrated_db
    _setup(dsn)
    result = broker.ensure_operation(dsn, operation_id="op1", effect="model-inference",
                                     payload=_model_payload(), allocation_id="a1",
                                     attempt_id="att1", retries=2)
    assert result.code == ResultCode.INVALID_INPUT
    assert result.detail == "retries must be zero; use distinct operation identities"
    assert broker.read_operation(dsn, "op1") is None
    assert store.allocation_status(dsn, "a1")["reserved"] == 0


def test_sandbox_prepare_reserves_hard_ceiling(migrated_db):
    """The hard ceiling is the stop/settle bound, and it is per operation.

    The retry multiplier is gone from the assertion for the same reason as
    in the test above: `ensure_operation` refuses `retries=1` outright, so
    `(bound) * 2` described a reservation the broker will not make. The
    ceiling itself is unchanged and still enforced: timeout, plus the
    declared stop/settle allowance, plus the one unit the read costs.
    """
    dsn = migrated_db
    _setup(dsn)
    payload = {"profile": "local-process", "argv": ["/bin/true"], "timeout_ms": 8_000,
               "max_output_bytes": 1024}
    result = broker.ensure_operation(dsn, operation_id="op1", effect="sandbox-exec",
                                     payload=payload, allocation_id="a1", attempt_id="att1")
    assert result.code == ResultCode.APPLIED
    assert result.data["exposure"] == 8 + STOP_SETTLE_S + 1
    assert result.data["budget_kind"] == "hard-ceiling"
    assert store.allocation_status(dsn, "a1")["reserved"] == 8 + STOP_SETTLE_S + 1


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
