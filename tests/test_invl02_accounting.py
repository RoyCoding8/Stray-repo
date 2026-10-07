from __future__ import annotations

import pytest

from settlement import loop, trials
from settlement.common import CommandResult, ResultCode, SettlementError, payload_digest


def test_public_cost_read_preserves_unknown_billing_and_tokens(monkeypatch):
    receipt = {
        "receipt_identity": "receipt-unknown",
        "outcome": "success",
        "content": {"usage": {
            "input_tokens": 5,
            "output_tokens": None,
            "charge_units": None,
            "billed": None,
        }},
    }
    monkeypatch.setattr(
        loop, "_operation_row",
        lambda dsn, operation_id: {
            "dispatch_state": "observed",
            "payload": {"effect": "model-inference"},
        },
    )
    monkeypatch.setattr(
        loop.store, "operation_receipts",
        lambda dsn, operation_id: [receipt],
    )

    costs = loop.read_measured_costs("unused", "operation-unknown")

    assert costs["measured"] == 0
    assert costs["billed"] is None
    assert costs["provider_charge_units"] is None
    assert costs["unknown"] == ["receipt-unknown"]
    assert costs["tokens"] == {"input": 5, "output": None}


def test_public_cost_read_does_not_call_sandbox_usage_provider_billing(monkeypatch):
    receipt = {
        "receipt_identity": "receipt-sandbox",
        "outcome": "success",
        "content": {},
    }
    monkeypatch.setattr(
        loop, "_operation_row",
        lambda dsn, operation_id: {
            "dispatch_state": "observed",
            "payload": {"effect": "sandbox-exec"},
        },
    )
    monkeypatch.setattr(
        loop.store, "operation_receipts",
        lambda dsn, operation_id: [receipt],
    )

    costs = loop.read_measured_costs("unused", "operation-sandbox")

    assert costs["measured"] == 0
    assert costs["billed"] is False
    assert costs["provider_charge_units"] is None
    assert costs["unknown"] == []
    assert costs["tokens"] == {"input": 0, "output": 0}


def test_public_cost_read_counts_one_operation_charge(monkeypatch):
    receipts = [
        {
            "receipt_identity": "receipt-old",
            "outcome": "success",
            "content": {"usage": {
                "input_tokens": 2,
                "output_tokens": 3,
                "charge_units": 5,
                "billed": True,
            }},
        },
        {
            "receipt_identity": "receipt-terminal",
            "outcome": "success",
            "content": {"usage": {
                "input_tokens": 7,
                "output_tokens": 11,
                "charge_units": 9,
                "billed": True,
            }},
        },
    ]
    monkeypatch.setattr(
        loop, "_operation_row",
        lambda dsn, operation_id: {
            "dispatch_state": "observed",
            "payload": {"effect": "model-inference"},
        },
    )
    monkeypatch.setattr(
        loop.store, "operation_receipts",
        lambda dsn, operation_id: receipts,
    )

    costs = loop.read_measured_costs("unused", "operation-receipts")

    assert costs["measured"] == 9
    assert costs["provider_charge_units"] == 9
    assert costs["tokens"] == {"input": 7, "output": 11}
    assert costs["unknown"] == []


def test_public_cost_read_keeps_usage_from_unknown_outcome(monkeypatch):
    receipt = {
        "receipt_identity": "receipt-unknown-outcome",
        "outcome": "unknown",
        "content": {"usage": {
            "input_tokens": 5,
            "output_tokens": 7,
            "charge_units": 11,
            "billed": True,
        }},
    }
    monkeypatch.setattr(
        loop, "_operation_row",
        lambda dsn, operation_id: {
            "dispatch_state": "unresolved",
            "payload": {"effect": "model-inference"},
        },
    )
    monkeypatch.setattr(
        loop.store, "operation_receipts",
        lambda dsn, operation_id: [receipt],
    )

    costs = loop.read_measured_costs("unused", "operation-unknown-outcome")

    assert costs["measured"] == 11
    assert costs["billed"] is True
    assert costs["provider_charge_units"] == 11
    assert costs["tokens"] == {"input": 5, "output": 7}
    assert costs["unknown"] == ["receipt-unknown-outcome"]


class _Cursor:
    def __init__(self, operations: dict[str, dict], reservations: dict[str, dict],
                 receipts: dict[str, list[dict]]) -> None:
        self.operations = operations
        self.reservations = reservations
        self.receipts = receipts
        self.one: dict | None = None
        self.many: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: tuple = ()) -> None:
        operation_id = str(params[0])
        if "FROM operations" in sql:
            self.one = self.operations.get(operation_id)
            self.many = []
        elif "FROM reservations" in sql:
            self.one = self.reservations.get(operation_id)
            self.many = []
        elif "FROM receipts" in sql:
            self.one = None
            self.many = list(self.receipts.get(operation_id, []))
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.one

    def fetchall(self):
        return list(self.many)


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self, **kwargs):
        return self.cursor_value

    def commit(self) -> None:
        return None


class _LedgerCursor:
    def __init__(self, harness: "_LedgerHarness") -> None:
        self.harness = harness
        self.one: dict | None = None

    def execute(self, sql: str, params: tuple) -> None:
        if "FROM operations" in sql:
            operation_id = str(params[0])
            self.one = ({"id": operation_id}
                        if operation_id in self.harness.operation_ids else None)
        elif "INSERT INTO expenditure_ledger" in sql:
            self.harness.rows.append(tuple(params))
            self.one = None
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.one


class _LedgerHarness:
    def __init__(self, operation_ids: set[str] | None = None) -> None:
        self.operation_ids = ({"operation-1"} if operation_ids is None
                              else operation_ids)
        self.rows: list[tuple] = []
        self.requests: list[str] = []
        self.results: dict[str, CommandResult] = {}

    def transact(self, dsn, command, handler, *args):
        self.requests.append(command.request_id)
        prior = self.results.get(command.request_id)
        if prior is not None:
            return CommandResult(
                code=ResultCode.ALREADY_APPLIED,
                request_id=command.request_id,
                detail=prior.detail,
                data=prior.data,
            )
        code, detail, data, events, outbox = handler(
            _LedgerCursor(self), {}, *args
        )
        result = CommandResult(
            code=code,
            request_id=command.request_id,
            detail=detail,
            data=data,
        )
        self.results[command.request_id] = result
        return result


@pytest.mark.parametrize("category", ["construction", "use", "failed_trials"])
def test_operation_expenditure_replay_is_idempotent(monkeypatch, category):
    harness = _LedgerHarness()
    monkeypatch.setattr(trials, "_protocol", lambda dsn, protocol_id: {
        "id": protocol_id,
        "budgets": {},
    })
    monkeypatch.setattr(trials.store, "transact", harness.transact)

    first = trials.record_expenditure(
        "unused", "protocol", category, 17, "replayed operation",
        operation_id="operation-1",
    )
    second = trials.record_expenditure(
        "unused", "protocol", category, 17, "replayed operation",
        operation_id="operation-1",
    )

    assert first == second
    assert first["operation_id"] == "operation-1"
    assert harness.rows == [(
        "protocol", category, 17,
        "replayed operation [operation:operation-1]",
    )]
    assert harness.requests[0] == harness.requests[1]
    assert payload_digest(first) == payload_digest(second)


def test_operation_expenditure_requires_a_durable_operation(monkeypatch):
    harness = _LedgerHarness(set())
    monkeypatch.setattr(trials, "_protocol", lambda dsn, protocol_id: {
        "id": protocol_id,
        "budgets": {},
    })
    monkeypatch.setattr(trials.store, "transact", harness.transact)

    with pytest.raises(SettlementError, match="durable operation_id"):
        trials.record_expenditure(
            "unused", "protocol", "construction", 17,
            "missing operation",
        )
    with pytest.raises(SettlementError, match="unknown operation"):
        trials.record_expenditure(
            "unused", "protocol", "construction", 17,
            "missing operation", operation_id="missing-operation",
        )




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
