from __future__ import annotations

import pytest

from settlement import experiment, loop, trials
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


def test_episode_union_keeps_unknown_billing_and_token_counts(monkeypatch):
    operations = {
        "op-measured": {
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "reservation_id": "res-measured",
            "payload": {"effect": "model-inference"},
        },
        "op-unknown": {
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "reservation_id": "res-unknown",
            "payload": {"effect": "model-inference"},
        },
        "op-unbilled": {
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "reservation_id": "res-unbilled",
            "payload": {"effect": "model-inference"},
        },
        "op-sandbox": {
            "dispatch_state": "observed",
            "reconcile_state": "none",
            "reservation_id": "res-sandbox",
            "payload": {"effect": "sandbox-exec"},
        },
    }
    reservations = {
        "res-measured": {"amount": 20, "state": "settled"},
        "res-unknown": {"amount": 30, "state": "settled"},
        "res-unbilled": {"amount": 12, "state": "settled"},
        "res-sandbox": {"amount": 4, "state": "settled"},
    }
    receipts = {
        "op-measured": [{
            "outcome": "success",
            "content": {"usage": {
                "input_tokens": 5,
                "output_tokens": 3,
                "charge_units": 7,
                "billed": True,
            }},
        }],
        "op-unknown": [{
            "outcome": "success",
            "content": {"usage": {
                "input_tokens": 11,
                "output_tokens": None,
                "charge_units": None,
                "billed": None,
            }},
        }],
        "op-unbilled": [{
            "outcome": "success",
            "content": {"usage": {
                "input_tokens": 1,
                "output_tokens": 1,
                "charge_units": 0,
                "billed": False,
            }},
        }],
        "op-sandbox": [{
            "outcome": "success",
            "content": {},
        }],
    }
    monkeypatch.setattr(
        experiment.db, "connect",
        lambda dsn: _Connection(_Cursor(operations, reservations, receipts)),
    )

    union = experiment.episode_cost_union("unused", {
        "model": ["op-measured", "op-unknown", "op-unbilled"],
        "sandbox": ["op-sandbox", "op-measured"],
    })

    assert union["totals"]["settled"] == 53
    assert union["totals"]["tokens"] == {"input": 17, "output": None}
    assert union["phases"]["model"]["tokens"] == {
        "input": 17,
        "output": None,
    }
    assert union["provider_billing"] == {
        "unit": "charge_units",
        "status": "unknown",
        "total_units": None,
        "measured_units": 7,
        "unknown_operations": ["op-unknown"],
        "unbilled_operations": ["op-unbilled"],
    }


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
