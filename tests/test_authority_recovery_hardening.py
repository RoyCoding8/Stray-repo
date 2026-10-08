from __future__ import annotations

import pytest

from settlement import broker, run, store
from settlement.common import Command, ConflictPayload, ResultCode
from settlement.gateway import ModelResponse, Usage


def _cmd(payload: dict, tag: str) -> Command:
    return Command(request_id=f"hardening-{tag}-{id(payload)}", payload=payload)


def _seed_operation(dsn: str, tag: str, operation_id: str) -> None:
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": f"{tag}-allocation", "domain": "cpu", "authorized": 100},
        f"{tag}-allocation"))
    store.seed_grant(dsn, _cmd(
        {"version": 1, "charter_text": tag, "authority_grant": {}, "envelopes": {}},
        f"{tag}-grant"))
    store.admit_commitment(dsn, _cmd(
        {"investigation_id": f"{tag}-investigation", "objective": tag},
        f"{tag}-commitment"))
    store.acquire_work(dsn, _cmd(
        {"attempt_id": f"{tag}-attempt", "investigation_id": f"{tag}-investigation"},
        f"{tag}-attempt"))
    store.prepare_operation(dsn, _cmd(
        {"operation_id": operation_id, "attempt_id": f"{tag}-attempt",
         "allocation_id": f"{tag}-allocation", "reservation_id": f"res-{operation_id}",
         "exposure": 20, "operation": {"kind": "probe"}}, f"{tag}-prepare"))
    store.advance_dispatch(dsn, _cmd(
        {"operation_id": operation_id, "launcher_id": "test-launcher"},
        f"{tag}-advance"))


def _receipt(operation_id: str, identity: str, *, provenance: str,
             actual_cost: int | None = None, outcome: str = "success") -> Command:
    payload = {
        "operation_id": operation_id,
        "receipt_identity": identity,
        "content": {"value": identity},
        "outcome": outcome,
        "provenance": provenance,
    }
    if actual_cost is not None:
        payload["actual_cost"] = actual_cost
    return _cmd(payload, f"{operation_id}-{identity}-{provenance}-{actual_cost}")


def test_second_receipt_identity_conflicts_even_when_content_matches(migrated_db):
    dsn = migrated_db
    _seed_operation(dsn, "receipt-two", "receipt-two-operation")
    first = store.admit_receipt(dsn, _receipt(
        "receipt-two-operation", "receipt-a", provenance="provider"))
    second = store.admit_receipt(dsn, _receipt(
        "receipt-two-operation", "receipt-b", provenance="provider"))

    assert first.code == ResultCode.APPLIED
    assert second.data["conflict"] is True
    assert [r["receipt_identity"] for r in store.operation_receipts(
        dsn, "receipt-two-operation")] == ["receipt-a"]


def test_cross_operation_receipt_collision_conflicts_both_operations(migrated_db):
    dsn = migrated_db
    _seed_operation(dsn, "receipt-cross-a", "receipt-cross-a-operation")
    _seed_operation(dsn, "receipt-cross-b", "receipt-cross-b-operation")
    assert store.admit_receipt(dsn, _receipt(
        "receipt-cross-a-operation", "shared-receipt", provenance="provider-a")
    ).code == ResultCode.APPLIED
    collision = store.admit_receipt(dsn, _receipt(
        "receipt-cross-b-operation", "shared-receipt", provenance="provider-b"))

    assert collision.data["conflict"] is True
    assert broker.read_operation(dsn, "receipt-cross-a-operation")[
        "reconcile_state"] == "conflict"
    assert broker.read_operation(dsn, "receipt-cross-b-operation")[
        "reconcile_state"] == "conflict"


def test_duplicate_receipt_compares_provenance_and_actual_cost(migrated_db):
    dsn = migrated_db
    _seed_operation(dsn, "receipt-metadata", "receipt-metadata-operation")
    first = store.admit_receipt(dsn, _receipt(
        "receipt-metadata-operation", "metadata-receipt",
        provenance="provider-a", actual_cost=4))
    same = store.admit_receipt(dsn, _receipt(
        "receipt-metadata-operation", "metadata-receipt",
        provenance="provider-a", actual_cost=4))
    changed_cost = store.admit_receipt(dsn, _receipt(
        "receipt-metadata-operation", "metadata-receipt",
        provenance="provider-a", actual_cost=5))
    changed_provenance = store.admit_receipt(dsn, _receipt(
        "receipt-metadata-operation", "metadata-receipt",
        provenance="provider-b", actual_cost=4))

    assert first.code == ResultCode.APPLIED
    assert same.code == ResultCode.ALREADY_APPLIED
    assert changed_cost.data["conflict"] is True
    assert changed_provenance.data["conflict"] is True


def test_receipt_cost_mismatch_preserves_receipt_and_liability(migrated_db):
    dsn = migrated_db
    _seed_operation(dsn, "cost-mismatch", "cost-mismatch-operation")
    result = store.admit_receipt(dsn, _cmd({
        "operation_id": "cost-mismatch-operation",
        "receipt_identity": "cost-mismatch-receipt",
        "content": {"operation_id": "cost-mismatch-operation",
                    "error": "provider failure",
                    "usage": {"input_tokens": 1, "output_tokens": 1,
                              "charge_units": 4, "charge_scale": 1000,
                              "billed": True}},
        "outcome": "failure",
        "provenance": "gateway",
        "actual_cost": 3,
    }, "cost-mismatch"))

    operation = broker.read_operation(dsn, "cost-mismatch-operation")
    assert result.code == ResultCode.APPLIED
    assert result.data["settled"] is False
    assert operation["dispatch_state"] == "unresolved"
    assert operation["reconcile_state"] == "unresolved"
    assert store.allocation_status(dsn, "cost-mismatch-allocation")["reserved"] == 20


def test_uncertain_reservation_requires_never_sent_proof(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": "uncertain-allocation", "domain": "cpu", "authorized": 20},
        "uncertain-allocation"))
    store.reserve(dsn, _cmd(
        {"allocation_id": "uncertain-allocation", "reservation_id": "uncertain-reservation",
         "amount": 10}, "uncertain-reserve"))
    store.settle_reservation(dsn, _cmd(
        {"reservation_id": "uncertain-reservation", "outcome": "unknown"},
        "uncertain-settle"))

    refused = store.release_reservation(dsn, _cmd(
        {"reservation_id": "uncertain-reservation"}, "uncertain-release-refused"))
    released = store.release_reservation(dsn, _cmd(
        {"reservation_id": "uncertain-reservation", "never_sent_proof": {
            "claim": "never-sent", "subject": "uncertain-reservation",
            "provenance": "launcher:test:stable-run-directory"}},
        "uncertain-release-proof"))

    assert refused.code == ResultCode.MISSING_EVIDENCE
    assert released.code == ResultCode.APPLIED
    assert store.allocation_status(dsn, "uncertain-allocation")["reserved"] == 0


def test_model_response_with_wrong_operation_identity_is_not_a_success(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": "model-identity", "domain": "cpu", "authorized": 100},
        "model-identity-allocation"))
    store.seed_grant(dsn, _cmd(
        {"version": 1, "charter_text": "model identity"}, "model-identity-grant"))
    prepared = broker.ensure_operation(
        dsn, operation_id="model-identity-operation", effect=broker.MODEL_INFERENCE,
        payload={"model": "test", "messages": [{"role": "user", "content": "x"}],
                 "max_output_tokens": 8, "deadline_ms": 1_000},
        allocation_id="model-identity")
    assert prepared.code == ResultCode.APPLIED

    class WrongGateway:
        def infer(self, request):
            return ModelResponse("different-operation", "answer", {}, Usage(), "stop")

    status = broker.dispatch_operation(dsn, "model-identity-operation", gateway=WrongGateway())

    assert status.sent_this_call is True
    receipts = store.operation_receipts(dsn, "model-identity-operation")
    assert len(receipts) == 1
    assert receipts[0]["outcome"] == "unknown"
    assert status.next_decision == "needs-reconciliation"
