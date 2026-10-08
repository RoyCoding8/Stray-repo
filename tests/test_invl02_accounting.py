from __future__ import annotations

import pytest

from settlement.common import CommandResult, ResultCode, SettlementError, payload_digest


def test_terminal_unknown_cannot_be_planted_in_operation_intent(monkeypatch):
    from settlement import store
    from settlement.common import Command

    class Cursor:
        def execute(self, sql, params=()):
            raise AssertionError(sql)

        def fetchone(self):
            return None

    cursor = Cursor()

    def transact(dsn, command, handler, *args):
        code, detail, data, events, outbox = handler(
            cursor, {"authority_version": 1}, *args)
        return CommandResult(
            code=code, request_id=command.request_id,
            detail=detail, data=data)

    monkeypatch.setattr(store, "transact", transact)
    with pytest.raises(store.ConflictPayload, match="_terminal_disposition"):
        store.prepare_operation("unused", Command(
            request_id="forged-terminal",
            payload={"operation_id": "op", "operation": {
                "_terminal_disposition": {"kind": "unresolved-terminal"},
            }}))


def test_terminal_unknown_preserves_exposure_and_is_idempotent(monkeypatch):
    from settlement import store
    from settlement.common import Command, ResultCode

    operation = {
        "id": "op-unknown", "reservation_id": "res-unknown",
        "dispatch_state": "unresolved", "reconcile_state": "unresolved",
        "cancel_state": "none", "settled": False,
        "payload": {"effect": "model-inference", "_dispatch_generation": 1},
    }
    reservation = {
        "id": "res-unknown", "allocation_id": "alloc-unknown",
        "amount": 2294, "state": "uncertain",
    }
    allocation = {"id": "alloc-unknown", "reserved": 2294}
    receipt = {
        "receipt_identity": "lost-response", "outcome": "unknown",
        "content": {"response_class": "lost-response", "response_received": False},
    }

    class Cursor:
        def __init__(self):
            self.one = None
            self.many = []
            self.updates = 0
            self.reads = 0

        def execute(self, sql, params=()):
            sql = " ".join(sql.split())
            if "FROM operations" in sql:
                self.one = dict(operation)
                self.many = []
            elif "FROM receipts" in sql:
                self.reads += 1
                self.one, self.many = None, [dict(receipt)]
            elif "FROM reservations" in sql:
                self.one, self.many = dict(reservation), []
            elif "FROM allocations" in sql:
                self.one, self.many = dict(allocation), []
            elif sql.startswith("UPDATE operations"):
                self.updates += 1
                if "SET payload" in sql:
                    operation["payload"] = next(
                        getattr(value, "obj", value) for value in params
                        if hasattr(value, "obj"))
                if "reconcile_state = 'conflict'" in sql:
                    operation["reconcile_state"] = "conflict"
                self.one = None
            elif sql.startswith("INSERT INTO receipt_conflicts"):
                self.one = None
            else:
                raise AssertionError(sql)

        def fetchone(self):
            return self.one

        def fetchall(self):
            return list(self.many)

    cursor = Cursor()

    def transact(dsn, command, handler, *args):
        code, detail, data, events, outbox = handler(
            cursor, {"authority_version": 1}, *args)
        return CommandResult(
            code=code, request_id=command.request_id,
            detail=detail, data=data)

    monkeypatch.setattr(store, "transact", transact)
    payload = {
        "operation_id": "op-unknown",
        "resolution": "unresolved-terminal",
    }
    first = store.reconcile_operation(
        "unused", Command(request_id="close-unknown", payload=payload))
    second = store.reconcile_operation(
        "unused", Command(request_id="close-unknown-replay", payload=payload))

    assert first.code == ResultCode.APPLIED
    assert second.code == ResultCode.ALREADY_APPLIED
    assert operation["dispatch_state"] == "unresolved"
    assert operation["reconcile_state"] == "unresolved"
    assert operation["settled"] is False
    assert reservation["state"] == "uncertain"
    assert allocation["reserved"] == 2294
    assert receipt["outcome"] == "unknown"
    assert operation["payload"]["_terminal_disposition"] == {
        "kind": "unresolved-terminal",
        "receipt_identity": "lost-response",
        "response_class": "lost-response",
        "response_received": False,
        "reservation_amount": 2294,
    }
    assert cursor.updates == 1
    assert cursor.reads == 1

    def admit_late_receipt(dsn, command, handler, *args):
        try:
            code, detail, data, events, outbox = handler(
                cursor, {"authority_version": 1}, *args)
        except store.MissingEvidence as exc:
            code, detail, data, events, outbox = exc.code, str(exc), {}, [], []
        return CommandResult(
            code=code, request_id=command.request_id,
            detail=detail, data=data)

    monkeypatch.setattr(store, "transact", admit_late_receipt)
    late = store.admit_receipt("unused", Command(
        request_id="late-decided", payload={
            "operation_id": "op-unknown",
            "receipt_identity": "late-success",
            "content": {"operation_id": "op-unknown", "text": "late"},
            "outcome": "success",
            "provenance": "gateway",
        }))

    assert late.code == ResultCode.APPLIED
    assert late.data["conflict"] is True
    assert operation["reconcile_state"] == "conflict"
    assert operation["settled"] is False
    assert reservation["state"] == "uncertain"
    assert allocation["reserved"] == 2294


def test_terminal_unknown_refuses_ordinary_reconciliation(monkeypatch):
    from settlement import store
    from settlement.common import Command, ResultCode

    operation = {
        "id": "op-unknown", "dispatch_state": "unresolved",
        "reconcile_state": "unresolved", "settled": False, "payload": {},
    }
    receipt = {"outcome": "unknown"}

    class Cursor:
        def __init__(self):
            self.one = None
            self.many = []

        def execute(self, sql, params=()):
            if "FROM operations" in sql:
                self.one = dict(operation)
            elif "FROM receipts" in sql:
                self.one, self.many = None, [receipt]
            else:
                raise AssertionError(sql)

        def fetchone(self):
            return self.one

        def fetchall(self):
            return list(self.many)

    cursor = Cursor()

    def transact(dsn, command, handler, *args):
        try:
            code, detail, data, events, outbox = handler(
                cursor, {"authority_version": 1}, *args)
        except store.MissingEvidence as exc:
            code, detail, data, events, outbox = exc.code, str(exc), {}, [], []
        return CommandResult(
            code=code, request_id=command.request_id,
            detail=detail, data=data)

    monkeypatch.setattr(store, "transact", transact)
    first = store.reconcile_operation("unused", Command(
        request_id="ordinary-reconcile", payload={
            "operation_id": "op-unknown",
            "resolution": "reconciled",
        }))
    operation["payload"]["_terminal_disposition"] = {
        "kind": "unresolved-terminal",
        "reservation_amount": 2294,
    }
    final = store.reconcile_operation("unused", Command(
        request_id="ordinary-reconcile-final", payload={
            "operation_id": "op-unknown",
            "resolution": "reconciled",
        }))

    assert first.code == ResultCode.MISSING_EVIDENCE
    assert "no decided receipt" in first.detail
    assert final.code == ResultCode.MISSING_EVIDENCE
    assert "resolution is final" in final.detail
    assert operation["settled"] is False
