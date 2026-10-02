from __future__ import annotations

import uuid

from settlement import store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, tag: str) -> Command:
    return Command(request_id=f"inva_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _seed(dsn: str, tag: str) -> int:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": tag}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 5000}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": tag}, f"{tag}i"))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                             "investigation_id": f"{tag}-i"}, f"{tag}q"))
    return int(acquired.data["ownership_generation"])


def _prepare(dsn: str, tag: str, op: str, allocation: str, attempt: str) -> None:
    result = store.prepare_operation(dsn, _cmd({"operation_id": op, "attempt_id": attempt,
                                                "allocation_id": allocation,
                                                "operation": {"kind": "probe"}}, f"{tag}-{op}"))
    assert result.code == ResultCode.APPLIED, result.detail


def test_receipt_identity_bound_to_operation(migrated_db):
    dsn = migrated_db
    _seed(dsn, "inva-r")
    _prepare(dsn, "inva-r", "inva-r-op1", "inva-r-a", "inva-r-att")
    _prepare(dsn, "inva-r", "inva-r-op2", "inva-r-a", "inva-r-att")
    store.advance_dispatch(dsn, _cmd({"operation_id": "inva-r-op1",
                                      "launcher_id": "L"}, "inva-r-ad"))
    first = store.admit_receipt(dsn, _cmd({"operation_id": "inva-r-op1",
                                           "receipt_identity": "inva-r-shared",
                                           "content": {"out": 1}, "outcome": "success"},
                                          "inva-r-rc1"))
    assert first.code == ResultCode.APPLIED
    replay = store.admit_receipt(dsn, _cmd({"operation_id": "inva-r-op2",
                                            "receipt_identity": "inva-r-shared",
                                            "content": {"out": 1}, "outcome": "success"},
                                           "inva-r-rc2"))
    assert replay.code == ResultCode.APPLIED
    assert replay.data.get("conflict") is True
    assert replay.data["operation_id"] == "inva-r-op2"
    assert store.operation_receipts(dsn, "inva-r-op2") == []
    state = store.restart_reconciliation(dsn)
    pending = {o["id"]: o for o in state["unfinished_operations"]}
    assert pending["inva-r-op2"]["reconcile_state"] == "conflict"


def test_receipt_duplicate_same_operation_still_acknowledged(migrated_db):
    dsn = migrated_db
    _seed(dsn, "inva-d")
    _prepare(dsn, "inva-d", "inva-d-op", "inva-d-a", "inva-d-att")
    store.advance_dispatch(dsn, _cmd({"operation_id": "inva-d-op",
                                      "launcher_id": "L"}, "inva-d-ad"))
    content = {"out": 1}
    first = store.admit_receipt(dsn, _cmd({"operation_id": "inva-d-op",
                                           "receipt_identity": "inva-d-rc",
                                           "content": dict(content), "outcome": "success"},
                                          "inva-d-rc1"))
    assert first.code == ResultCode.APPLIED
    dup = store.admit_receipt(dsn, _cmd({"operation_id": "inva-d-op",
                                         "receipt_identity": "inva-d-rc",
                                         "content": dict(content), "outcome": "success"},
                                        "inva-d-rc2"))
    assert dup.code == ResultCode.ALREADY_APPLIED


def test_reconcile_prepared_operation_refused(migrated_db):
    dsn = migrated_db
    _seed(dsn, "inva-p")
    _prepare(dsn, "inva-p", "inva-p-op", "inva-p-a", "inva-p-att")
    refused = store.reconcile_operation(dsn, _cmd({"operation_id": "inva-p-op",
                                                   "resolution": "reconciled"}, "inva-p-rc"))
    assert refused.code == ResultCode.INVALID_INPUT
    advanced = store.advance_dispatch(dsn, _cmd({"operation_id": "inva-p-op",
                                                 "launcher_id": "L"}, "inva-p-ad"))
    assert advanced.code == ResultCode.APPLIED


def test_reconcile_dispatched_operation_still_applies(migrated_db):
    dsn = migrated_db
    gen = _seed(dsn, "inva-s")
    _prepare(dsn, "inva-s", "inva-s-op", "inva-s-a", "inva-s-att")
    store.advance_dispatch(dsn, _cmd({"operation_id": "inva-s-op", "launcher_id": "L",
                                      "ownership_generation": gen}, "inva-s-ad"))
    resolved = store.reconcile_operation(dsn, _cmd({"operation_id": "inva-s-op",
                                                    "resolution": "unresolved"}, "inva-s-rc"))
    assert resolved.code == ResultCode.APPLIED
