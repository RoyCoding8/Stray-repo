from __future__ import annotations

import pytest

from settlement import broker, store
from settlement.common import (
    Command,
    CommandResult,
    ConflictPayload,
    MissingEvidence,
    ResultCode,
    SettlementError,
    Unauthorized,
)


class QueryCursor:
    def __init__(self, resolver):
        self.resolver = resolver
        self.sql = ""
        self.params = ()
        self.current = None
        self.rows = []
        self.rowcount = 1
        self.executed = []

    def execute(self, sql, params=()):
        self.sql = " ".join(sql.split())
        self.params = params
        self.executed.append((self.sql, params))
        self.current, self.rows = self.resolver(self.sql, params)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _run_handler(monkeypatch, cursor, control=None):
    def transact(dsn, command, handler, *args):
        code, detail, data, events, outbox = handler(
            cursor, control or {"authority_version": 1}, *args)
        return CommandResult(
            code=code, request_id=command.request_id, detail=detail, data=data)

    monkeypatch.setattr(store, "transact", transact)
    return transact


def _cmd(tag, payload):
    return Command(request_id=tag, payload=payload)


def _proof(subject, generation=None):
    proof = {
        "claim": "never-sent",
        "subject": subject,
        "provenance": "launcher:test:stable-run-directory",
    }
    if generation is not None:
        proof["dispatch_generation"] = generation
    return proof


def _allocation_resolver(allocations, child=None, children=0):
    def resolve(sql, params):
        if "FROM allocations" in sql and "COALESCE(SUM" in sql:
            return {"total": children}, []
        if "FROM allocations" in sql:
            allocation_id = params[0]
            if allocation_id == child:
                return None, []
            return allocations.get(allocation_id), []
        return None, []
    return resolve


def test_seed_allocation_refuses_to_overcommit_parent(monkeypatch):
    cursor = QueryCursor(_allocation_resolver(
        {"parent": {"id": "parent", "authorized": 50, "consumed": 10,
                    "reserved": 5}}, child="child"))
    _run_handler(monkeypatch, cursor)

    with pytest.raises(store.InsufficientResources):
        store.seed_allocation("fake", _cmd("seed-child", {
            "allocation_id": "child",
            "parent_id": "parent",
            "domain": "cpu",
            "authorized": 36,
        }))

    assert not any(sql.startswith("INSERT INTO allocations") for sql, _ in cursor.executed)


def test_prepare_operation_refuses_allocation_outside_attempt_envelope(monkeypatch):
    allocations = {
        "attempt-root": {"id": "attempt-root", "parent_id": None},
        "other-root": {"id": "other-root", "parent_id": None},
    }

    def resolve(sql, params):
        if "FROM operations" in sql:
            return None, []
        if "FROM attempts" in sql:
            return {"id": "att", "allocation_id": "attempt-root"}, []
        if "WITH RECURSIVE allocation_lineage" in sql:
            candidate, ancestor = params
            return ({"ok": True} if candidate == ancestor else None), []
        if "FROM allocations" in sql:
            return allocations.get(params[0]), []
        return None, []

    cursor = QueryCursor(resolve)
    _run_handler(monkeypatch, cursor)

    with pytest.raises(ConflictPayload):
        store._prepare_operation(
            cursor, 1, operation_id="op", attempt_id="att",
            allocation_id="other-root", operation={"kind": "probe"})

    assert not any(sql.startswith("INSERT INTO operations") for sql, _ in cursor.executed)


@pytest.mark.parametrize("changed", [
    {"attempt_id": "other-attempt"},
    {"allocation_id": "other-allocation"},
    {"reservation_id": "other-reservation"},
    {"execution_version": "exec-v2"},
    {"authority_version": 2},
    {"exposure": 11},
])
def test_prepare_operation_replay_compares_every_immutable_field(monkeypatch, changed):
    body = {"kind": "probe"}
    stored_payload = {**body, "_authority_version": 1}
    existing = {
        "id": "op",
        "payload_digest": store.payload_digest(body),
        "payload": stored_payload,
        "attempt_id": "att",
        "allocation_id": "alloc",
        "reservation_id": "res",
        "execution_version": "exec-v1",
        "reservation_amount": 10,
    }
    cursor = QueryCursor(lambda sql, params: (
        (existing, []) if "FROM operations" in sql else (None, [])))
    _run_handler(monkeypatch, cursor)
    fields = {
        "operation_id": "op",
        "attempt_id": "att",
        "allocation_id": "alloc",
        "reservation_id": "res",
        "execution_version": "exec-v1",
        "exposure": 10,
        "operation": body,
        "authority_version": 1,
    }
    fields.update(changed)

    with pytest.raises(ConflictPayload):
        store._prepare_operation(
            cursor, fields.pop("authority_version"),
            operation_id=fields["operation_id"], attempt_id=fields["attempt_id"],
            allocation_id=fields["allocation_id"], reservation_id=fields["reservation_id"],
            exposure=fields["exposure"], operation=fields["operation"],
            execution_version=fields["execution_version"])


def test_seed_grant_refuses_mutation_of_an_existing_version(monkeypatch):
    existing = {
        "version": 1,
        "charter_text": "original",
        "authority_grant": {"scope": ["cpu"]},
        "envelopes": {"model": "test"},
    }
    cursor = QueryCursor(lambda sql, params: (existing, []) if "FROM grants" in sql else (None, []))
    _run_handler(monkeypatch, cursor)

    with pytest.raises(ConflictPayload):
        store.seed_grant("fake", _cmd("grant-mutation", {
            "version": 1,
            "charter_text": "changed",
            "authority_grant": {"scope": ["network"]},
            "envelopes": {"model": "other"},
        }))

    assert not any("INSERT INTO grants" in sql for sql, _ in cursor.executed)


@pytest.mark.parametrize("actual", [1.5, True, "1"])
def test_settlement_rejects_non_integer_actual_cost(actual):
    cursor = QueryCursor(lambda sql, params: ({
        "id": "res",
        "allocation_id": "alloc",
        "amount": 10,
        "state": "reserved",
    }, []) if "FROM reservations" in sql else (None, []))

    with pytest.raises(SettlementError, match="actual cost"):
        store._settle_amount(cursor, "res", "success", actual)

    assert not any(sql.startswith("UPDATE allocations") for sql, _ in cursor.executed)


@pytest.mark.parametrize("charge", [1.5, True, "1"])
def test_billed_receipt_rejects_non_integer_charge(charge):
    with pytest.raises(SettlementError, match="billed charge_units"):
        store.receipt_actual_cost({"content": {
            "usage": {"billed": True, "charge_units": charge}}})


def test_receipt_validation_rejects_invalid_outcome_and_pre_dispatch_receipt():
    dispatched = {
        "id": "op",
        "dispatch_state": "dispatching",
        "payload": {"effect": "probe"},
        "settled": False,
    }
    invalid = {
        "receipt_identity": "receipt",
        "content": {"value": 1},
        "outcome": "cancelled",
    }
    with pytest.raises(SettlementError, match="unknown receipt outcome"):
        store._validate_receipt(dispatched, invalid)

    prepared = {**dispatched, "dispatch_state": "prepared"}
    with pytest.raises(SettlementError, match="was not dispatched"):
        store._validate_receipt(prepared, {
            "receipt_identity": "receipt",
            "content": {"value": 1},
            "outcome": "success",
        })


@pytest.mark.parametrize("identities,resolution,accepted", [
    (["unknown"], None, True),
    (["u1", "u2"], ["u1", "u2"], True),
    (["u1", "u2"], None, False),
    (["u1", "u2"], ["u1"], False),
    (["u1", "u2"], ["u1", "foreign"], False),
    (["u1", "u2"], ["u1", "u1", "u2"], False),
])
def test_unknown_receipt_can_be_resolved_by_a_later_decided_receipt(
        monkeypatch, identities, resolution, accepted):
    op = {
        "id": "op",
        "attempt_id": None,
        "allocation_id": "alloc",
        "reservation_id": "res",
        "payload": {"effect": "probe"},
        "dispatch_state": "unresolved",
        "reconcile_state": "unresolved",
        "settled": False,
    }
    prior = [{"receipt_identity": identity, "outcome": "unknown"}
             for identity in identities]
    reservation = {"id": "res", "allocation_id": "alloc", "amount": 10, "state": "uncertain"}

    def resolve(sql, params):
        if "FROM operations" in sql:
            return op, []
        if "FROM receipts WHERE receipt_identity" in sql:
            return None, []
        if "FROM receipts WHERE operation_id" in sql:
            return prior[0], prior
        if "FROM reservations" in sql:
            return reservation, []
        return None, []

    cursor = QueryCursor(resolve)
    _run_handler(monkeypatch, cursor)
    result = store.admit_receipt("fake", _cmd("receipt-resolution", {
        "operation_id": "op",
        "receipt_identity": "decided",
        "content": {"value": 2, **({"resolves_unknowns": resolution}
                                    if resolution is not None else {})},
        "outcome": "success",
        "provenance": "provider",
    }))

    conflict = any("INSERT INTO receipt_conflicts" in sql
                   for sql, _ in cursor.executed)
    if accepted:
        assert result.data == {"operation_id": "op", "settled": True}
        assert not conflict
    else:
        assert result.data == {"operation_id": "op", "settled": False,
                               "conflict": True}
        assert conflict


def test_conflicted_operation_does_not_accept_a_later_receipt(monkeypatch):
    op = {
        "id": "op",
        "attempt_id": None,
        "allocation_id": "alloc",
        "reservation_id": "res",
        "payload": {"effect": "probe"},
        "dispatch_state": "observed",
        "reconcile_state": "conflict",
        "settled": True,
    }
    cursor = QueryCursor(lambda sql, params: (
        (op, []) if "FROM operations" in sql else (None, [])))
    _run_handler(monkeypatch, cursor)
    result = store.admit_receipt("fake", _cmd("receipt-after-conflict", {
        "operation_id": "op",
        "receipt_identity": "later",
        "content": {"value": 3, "response_class": "provider-failure"},
        "outcome": "failure",
        "provenance": "provider",
    }))

    assert result.data["conflict"] is True
    assert not any("INSERT INTO receipts" in sql for sql, _ in cursor.executed)


def test_never_sent_proof_rejects_boolean_generation():
    with pytest.raises(MissingEvidence, match="dispatch generation"):
        store._never_sent_proof(
            {"never_sent_proof": _proof("op", True)}, "op", 1)


def test_never_sent_proof_requires_provenance(monkeypatch):
    reservation = {"id": "res", "allocation_id": "alloc", "amount": 10, "state": "uncertain"}
    cursor = QueryCursor(lambda sql, params: (
        (reservation, []) if "FROM reservations" in sql else (None, [])))
    _run_handler(monkeypatch, cursor)

    with pytest.raises(MissingEvidence, match="provenance"):
        store.release_reservation("fake", _cmd("bare-proof", {
            "reservation_id": "res",
            "never_sent_proof": True,
        }))


def test_structured_never_sent_proof_releases_uncertain_reservation(monkeypatch):
    reservation = {"id": "res", "allocation_id": "alloc", "amount": 10, "state": "uncertain"}
    cursor = QueryCursor(lambda sql, params: (
        (reservation, []) if "FROM reservations" in sql else (None, [])))
    _run_handler(monkeypatch, cursor)

    result = store.release_reservation("fake", _cmd("attributed-proof", {
        "reservation_id": "res",
        "never_sent_proof": _proof("res"),
    }))

    assert result.code == ResultCode.APPLIED
    assert any("UPDATE reservations SET state = 'released'" in sql
               for sql, _ in cursor.executed)


def test_operation_reservation_requires_generation_bound_never_sent_proof(monkeypatch):
    reservation = {
        "id": "res", "allocation_id": "alloc", "operation_id": "op",
        "amount": 10, "state": "uncertain",
    }
    operation = {"id": "op", "payload": {"_dispatch_generation": 1}}

    def resolve(sql, params):
        if "FROM reservations" in sql:
            return reservation, []
        if "FROM operations" in sql:
            return operation, []
        return None, []

    cursor = QueryCursor(resolve)
    _run_handler(monkeypatch, cursor)

    with pytest.raises(MissingEvidence, match="dispatch generation"):
        store.release_reservation("fake", _cmd("unbound-operation-proof", {
            "reservation_id": "res",
            "never_sent_proof": _proof("res"),
        }))


def test_reset_dispatch_refuses_without_proof(monkeypatch):
    op = {
        "id": "op",
        "dispatch_state": "dispatching",
        "cancel_state": "none",
        "reconcile_state": "none",
        "payload": {"_dispatch_generation": 1},
    }

    def resolve(sql, params):
        if "FROM operations" in sql:
            return op, []
        if "FROM receipts" in sql:
            return None, []
        return None, []

    cursor = QueryCursor(resolve)
    _run_handler(monkeypatch, cursor)

    with pytest.raises(MissingEvidence, match="provenance"):
        store.reset_dispatch("fake", _cmd("reset-without-proof", {
            "operation_id": "op",
            "expected_generation": 1,
        }))

    assert not any(sql.startswith("UPDATE operations") for sql, _ in cursor.executed)


def test_reset_dispatch_persists_generation_bound_never_sent_proof(monkeypatch):
    op = {
        "id": "op",
        "dispatch_state": "dispatching",
        "cancel_state": "none",
        "reconcile_state": "none",
        "payload": {"_dispatch_generation": 1},
    }

    def resolve(sql, params):
        if "FROM operations" in sql:
            return op, []
        if "FROM receipts" in sql:
            return None, []
        return None, []

    cursor = QueryCursor(resolve)
    _run_handler(monkeypatch, cursor)
    result = store.reset_dispatch("fake", _cmd("attributed-reset", {
        "operation_id": "op",
        "expected_generation": 1,
        "never_sent_proof": _proof("op", 1),
    }))

    assert result.data["dispatch_generation"] == 2
    update = next(params for sql, params in cursor.executed
                  if sql.startswith("UPDATE operations"))
    stored = getattr(update[0], "obj", update[0])
    assert stored["_never_sent_proof"] == _proof("op", 1)


def test_grant_version_rejects_coercion_at_the_store_boundary():
    for value in (True, 1.0, "1"):
        with pytest.raises(Unauthorized):
            store._check_grant(
                {"authority_version": 1},
                {"grant_version": value},
                {"_authority_version": 1},
            )


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_seed_grant_rejects_coerced_versions(monkeypatch, version):
    _run_handler(monkeypatch, QueryCursor(lambda sql, params: (None, [])))

    with pytest.raises(SettlementError, match="positive integer"):
        store.seed_grant("fake", _cmd("grant-type", {
            "version": version,
            "charter_text": "typed",
        }))


def test_receipt_cost_rejects_usage_mismatch_and_keeps_noncanonical_scale_unknown():
    with pytest.raises(SettlementError, match="actual cost"):
        store.receipt_actual_cost({
            "actual_cost": 3,
            "content": {"usage": {"billed": True, "input_tokens": 1,
                                   "output_tokens": 1, "charge_units": 4,
                                   "charge_scale": 1000}},
        })
    assert store.receipt_actual_cost({
        "content": {"usage": {"billed": True, "charge_units": 4,
                               "charge_scale": 7}},
    }) is None


def test_failure_receipt_requires_provenance_and_response_evidence():
    operation = {
        "id": "op",
        "dispatch_state": "dispatching",
        "payload": {"effect": "model-inference"},
    }
    with pytest.raises(SettlementError, match="provenance"):
        store._validate_receipt(operation, {
            "receipt_identity": "failure",
            "outcome": "failure",
            "content": {"operation_id": "op", "error": "provider failed"},
        })
    with pytest.raises(SettlementError, match="response evidence"):
        store._validate_receipt(operation, {
            "receipt_identity": "failure",
            "outcome": "failure",
            "provenance": "gateway",
            "content": {"operation_id": "op", "value": "not a response"},
        })


def _sandbox_failure_receipt(content):
    """The shape a LocalLauncher writes when the program it ran failed.

    N-43. Built from `launcher_local.py:322-323` (`_base`) and `:326-348`
    (`_interpret`) rather than from memory, so a change to the launcher that
    renames one of these keys has to be made here on purpose.
    """
    return {
        "receipt_identity": "local:op.result",
        "outcome": "failure",
        "provenance": "local-process",
        "content": content,
    }


def _sandbox_op():
    return {
        "id": "op",
        "dispatch_state": "dispatching",
        "payload": {"effect": "sandbox-exec"},
    }


def test_a_sandbox_failure_is_admitted_with_the_launchers_own_evidence():
    """N-43. The check op has to be able to record that the program failed.

    Every one of the 539 launcher result files on disk carries `outcome:
    failure` and none of them carries a gateway key, so before this the
    receipt that reports a failed check could not be admitted at all, and
    the operation was left `dispatching` with no receipt.
    """
    store._validate_receipt(_sandbox_op(), _sandbox_failure_receipt({
        "containment": False, "profile": "local", "argv": ["python", "app.py"],
        "data": {"worker": {"status": "error"}, "timed_out": False, "wall_ms": 12},
        "truncated": False, "parse": "typed-json", "_verdict": "failure",
    }))


def test_a_sandbox_spawn_error_is_still_evidence():
    """The one launcher failure branch that carries neither returncode nor parse.

    `launcher_local.py:256-258` calls `_base` directly, so the content has
    `data.spawn_error` and no `parse` key at all. Without this case the
    repair would cover a failed program but not a program that could not
    be started, which is the failure a sandbox reports when it is broken.
    """
    store._validate_receipt(_sandbox_op(), _sandbox_failure_receipt({
        "containment": False, "profile": "local", "argv": ["python", "app.py"],
        "data": {"spawn_error": "No such file or directory"},
    }))


def test_a_sandbox_failure_still_needs_provenance():
    """The widened evidence set does not widen anything else.

    Provenance is what says who is reporting the failure, and it is checked
    immediately above the evidence test, so the widening must not have
    reached around it.
    """
    with pytest.raises(SettlementError, match="provenance"):
        store._validate_receipt(_sandbox_op(), {
            "receipt_identity": "local:op.result",
            "outcome": "failure",
            "content": {"data": {"spawn_error": "nope"}, "parse": "rejected"},
        })


def test_a_sandbox_failure_with_no_evidence_at_all_is_still_refused():
    """The invariant survives the widening.

    A failure still cannot be recorded on a claim alone. This is the
    distinction that makes N-43 a repair rather than a removal: the rule
    said "a failure must be evidenced" and it still does, in vocabulary
    the launcher can actually produce.
    """
    with pytest.raises(SettlementError, match="response evidence"):
        store._validate_receipt(_sandbox_op(), {
            "receipt_identity": "local:op.result",
            "outcome": "failure",
            "provenance": "local-process",
            "content": {"value": "not a response"},
        })


def test_receiptless_reconciliation_requires_never_sent_proof(monkeypatch):
    operation = {
        "id": "op",
        "dispatch_state": "dispatching",
        "reconcile_state": "none",
        "cancel_state": "none",
        "payload": {"_dispatch_generation": 1},
    }

    def resolve(sql, params):
        if "FROM operations" in sql:
            return operation, []
        if "FROM receipts" in sql:
            return None, []
        return None, []

    cursor = QueryCursor(resolve)
    _run_handler(monkeypatch, cursor)

    with pytest.raises(MissingEvidence, match="never-sent proof"):
        store.reconcile_operation("fake", _cmd("receiptless-reconcile", {
            "operation_id": "op",
            "resolution": "reconciled",
        }))

    result = store.reconcile_operation("fake", _cmd("receiptless-proof", {
        "operation_id": "op",
        "resolution": "reconciled",
        "never_sent_proof": _proof("op", 1),
    }))
    assert result.data["never_sent_proof"] == _proof("op", 1)
