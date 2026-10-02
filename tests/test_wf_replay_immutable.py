from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

import pytest

from settlement import broker, db, run as runmod, store
from settlement.common import Command, ResultCode


_BASE_PAYLOAD = {
    "model": "m1",
    "messages": [{"role": "user", "content": "hello"}],
    "max_output_tokens": 8,
}
_OPERATION_ID = "op-replay"
_ALLOCATION_ID = "alloc-original"
_EXECUTION_VERSION = "exec-v1"


def _command(payload: dict[str, Any]) -> Command:
    return Command(request_id=f"test-{uuid.uuid4().hex}", payload=payload)


def _changed_request(changed_field: str) -> dict[str, Any]:
    op_args = {
        "operation_id": _OPERATION_ID,
        "effect": broker.MODEL_INFERENCE,
        "payload": deepcopy(_BASE_PAYLOAD),
        "allocation_id": _ALLOCATION_ID,
        "execution_version": _EXECUTION_VERSION,
    }
    if changed_field == "effect":
        op_args["effect"] = broker.SANDBOX_EXEC
        op_args["payload"] = {
            "profile": "local-process",
            "argv": ["/bin/true"],
            "timeout_ms": 5_000,
            "max_output_bytes": 1_024,
        }
    elif changed_field == "payload":
        op_args["payload"]["messages"][0]["content"] = "changed"
    elif changed_field == "allocation_id":
        op_args["allocation_id"] = "alloc-changed"
    elif changed_field == "execution_version":
        op_args["execution_version"] = "exec-v2"
    else:
        raise AssertionError(f"unknown changed field {changed_field}")
    return op_args


def _prepare_terminal_operation(dsn: str, prior: dict[str, Any]) -> None:
    assert store.seed_allocation(dsn, _command({
        "allocation_id": _ALLOCATION_ID,
        "domain": "model",
        "authorized": 100,
    })).code == ResultCode.APPLIED
    clean = broker.validate_effect(broker.MODEL_INFERENCE, _BASE_PAYLOAD)
    exposure, budget_kind = broker.exposure_schedule(
        broker.MODEL_INFERENCE, clean, 0)
    body = {
        "effect": broker.MODEL_INFERENCE,
        "payload": clean,
        "retries": 0,
        "budget_kind": budget_kind,
    }
    assert store.prepare_operation(dsn, _command({
        "operation_id": _OPERATION_ID,
        "allocation_id": _ALLOCATION_ID,
        "reservation_id": f"res-{_OPERATION_ID}",
        "exposure": exposure,
        "operation": body,
        "execution_version": _EXECUTION_VERSION,
    })).code == ResultCode.APPLIED
    assert store.advance_dispatch(dsn, _command({
        "operation_id": _OPERATION_ID,
        "launcher_id": "launcher-test",
    })).code == ResultCode.APPLIED

    first_outcome = "success" if prior["outcome"] == "conflict" else prior["outcome"]
    content = {
        "success": {
            "text": "ok",
            "operation_id": _OPERATION_ID,
            "response_operation_id": _OPERATION_ID,
        },
        "failure": {
            "error": "failed",
            "operation_id": _OPERATION_ID,
            "response_operation_id": _OPERATION_ID,
        },
    }[first_outcome]
    receipt = {
        "operation_id": _OPERATION_ID,
        "receipt_identity": f"receipt-{_OPERATION_ID}",
        "content": content,
        "outcome": first_outcome,
        "provenance": "test",
    }
    assert store.admit_receipt(dsn, _command(receipt)).code == ResultCode.APPLIED
    if prior["outcome"] == "conflict":
        conflict = store.admit_receipt(dsn, _command({
            **receipt,
            "content": {**content, "text": "changed"},
        }))
        assert conflict.code == ResultCode.APPLIED
        assert conflict.data["conflict"] is True


@pytest.mark.parametrize("changed_field", [
    "effect",
    "payload",
    "allocation_id",
    "execution_version",
])
@pytest.mark.parametrize("prior", [
    pytest.param(
        {"found": True, "outcome": "failure", "dispatch_state": "observed"},
        id="already-failed",
    ),
    pytest.param(
        {"found": True, "outcome": "success", "dispatch_state": "observed"},
        id="already-replayed",
    ),
    pytest.param(
        {"found": True, "outcome": "conflict", "dispatch_state": "observed"},
        id="needs-reconciliation",
    ),
])
def test_terminal_replay_refuses_changed_immutable_request(
    migrated_db: str,
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
    prior: dict[str, Any],
) -> None:
    _prepare_terminal_operation(migrated_db, prior)
    monkeypatch.setitem(
        broker.ATTEMPT_WORKFLOW_RESOURCES,
        "att-replay",
        {"launchers": {}, "gateway": None},
    )
    monkeypatch.setattr(
        broker,
        "dispatch_operation",
        lambda *_args, **_kwargs: pytest.fail("a changed terminal replay must not dispatch"),
    )

    summary = broker.wf_ensure_dispatch(
        migrated_db,
        _changed_request(changed_field),
        1,
        1,
        "node",
        "att-replay",
    )

    assert summary == {
        "node_id": "node",
        "operation_id": _OPERATION_ID,
        "dispatch_state": prior["dispatch_state"],
        "next_decision": "ensure-refused-invalid_input",
        "ensure_refused": (
            f"operation {_OPERATION_ID} replay changed immutable authority metadata"
        ),
        "failed_try": False,
    }
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM operations WHERE id = %s", (_OPERATION_ID,))
            operations = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM reservations WHERE id = %s",
                        (f"res-{_OPERATION_ID}",))
            reservations = cur.fetchone()[0]
        conn.commit()
    assert (operations, reservations) == (1, 1)
    persisted = runmod.operation_outcome(migrated_db, _OPERATION_ID)
    assert (persisted["found"], persisted["outcome"],
            persisted["dispatch_state"]) == (
                prior["found"], prior["outcome"], prior["dispatch_state"])
