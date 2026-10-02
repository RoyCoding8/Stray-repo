from __future__ import annotations

import inspect
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import sys

sys.path.insert(0, "experiments")

from doubles import ScriptedDouble
from settlement import broker, evidence, store
from settlement.common import Command, MissingEvidence, ResultCode
from settlement.gateway import GatewayError, ModelRequest
from settlement.run import Composition, InvalidComposition, validate_composition
from test_r02_authority import _base_name, _conn_params, _make_database, _sibling_dsn


def _cmd(payload: dict, tag: str) -> Command:
    return Command(request_id=f"close1_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _seed(dsn: str, tag: str) -> None:
    assert store.seed_grant(
        dsn, _cmd({"version": 1, "charter_text": tag}, f"{tag}g")).code == ResultCode.APPLIED
    assert store.seed_allocation(
        dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                   "authorized": 5000}, f"{tag}a")).code == ResultCode.APPLIED
    assert store.admit_commitment(
        dsn, _cmd({"investigation_id": f"{tag}-i", "objective": tag}, f"{tag}i")).code \
        == ResultCode.APPLIED
    acquired = store.acquire_work(
        dsn, _cmd({"attempt_id": f"{tag}-att", "investigation_id": f"{tag}-i"}, f"{tag}q"))
    assert acquired.code == ResultCode.APPLIED


def test_seed_allocation_refuses_nonpositive_inputs(migrated_db):
    dsn = migrated_db
    _seed(dsn, "close1a")
    for tag, payload in (
            ("neg", {"allocation_id": "close1a-neg", "domain": "cpu", "authorized": -5}),
            ("zero", {"allocation_id": "close1a-zero", "domain": "cpu", "authorized": 0}),
            ("occ", {"allocation_id": "close1a-occ", "domain": "cpu",
                      "authorized": 10, "max_occupancy": -1}),
            ("scale", {"allocation_id": "close1a-scale", "domain": "cpu",
                       "authorized": 10, "amount_scale": 0})):
        result = store.seed_allocation(dsn, _cmd(payload, tag))
        assert result.code == ResultCode.INVALID_INPUT, (tag, result)
    assert store.seed_allocation(
        dsn, _cmd({"allocation_id": "close1a-ok", "domain": "cpu",
                   "authorized": 10}, "ok")).code == ResultCode.APPLIED


def _settled_op(dsn: str, tag: str) -> str:
    _seed(dsn, tag)
    op = f"{tag}-op"
    prepared = store.prepare_operation(dsn, _cmd(
        {"operation_id": op, "attempt_id": f"{tag}-att", "allocation_id": f"{tag}-a",
         "reservation_id": f"{tag}-res", "exposure": 40,
         "operation": {"kind": "close1-probe"}}, f"{tag}p"))
    assert prepared.code == ResultCode.APPLIED, prepared.detail
    first = store.admit_receipt(dsn, _cmd(
        {"operation_id": op, "receipt_identity": f"{tag}-rc1",
         "content": {"out": 1}, "outcome": "success"}, f"{tag}r1"))
    assert first.code == ResultCode.APPLIED
    assert store.allocation_status(dsn, f"{tag}-a")["consumed"] == 40
    return op


def test_contradictory_late_receipt_flagged_for_reconciliation(migrated_db):
    dsn = migrated_db
    op = _settled_op(dsn, "close1b")
    late = store.admit_receipt(dsn, _cmd(
        {"operation_id": op, "receipt_identity": "close1b-rc2",
         "content": {"out": 2}, "outcome": "failure"}, "close1br2"))
    assert late.code == ResultCode.APPLIED
    assert late.data.get("conflict") is True
    assert late.data.get("settled") is True
    assert store.allocation_status(dsn, "close1b-a")["consumed"] == 40
    assert {r["outcome"] for r in store.operation_receipts(dsn, op)} == {"success", "failure"}
    state = store.restart_reconciliation(dsn)
    pending = {o["id"]: o for o in state["unfinished_operations"]}
    assert pending[op]["reconcile_state"] == "conflict"


def test_matching_late_receipt_not_flagged(migrated_db):
    dsn = migrated_db
    op = _settled_op(dsn, "close1c")
    late = store.admit_receipt(dsn, _cmd(
        {"operation_id": op, "receipt_identity": "close1c-rc2",
         "content": {"out": 1}, "outcome": "success"}, "close1cr2"))
    assert late.code == ResultCode.APPLIED
    assert late.data.get("conflict") is None
    assert "already settled" in late.detail


def _nested(depth: int) -> dict:
    node: dict = {"kind": "invoke", "node_id": "leaf", "effect": "sandbox-exec",
                  "payload": {"profile": "local-process", "argv": ["/bin/true"],
                              "timeout_ms": 1000, "max_output_bytes": 64}}
    for level in range(depth - 1):
        node = {"kind": "sequence", "node_id": f"s{level}", "steps": [node]}
    return {"version": "run/v1", "revision": 1, "root": node,
            "allocation_id": "a", "authority_version": 1}


def test_validate_composition_enforces_max_depth():
    with pytest.raises(InvalidComposition):
        validate_composition(Composition.model_validate(_nested(5)))
    assert validate_composition(Composition.model_validate(_nested(4))).max_depth == 4
    wide = _nested(5)
    wide["max_depth"] = 5
    assert validate_composition(Composition.model_validate(wide)).max_depth == 5


def test_attempt_workflow_refuses_deep_composition(migrated_db, monkeypatch):
    monkeypatch.setattr(broker, "DBOS", SimpleNamespace(
        run_step=lambda _ctx, fn, *args: fn(*args),
        workflow=lambda: (lambda fn: fn)))
    body = inspect.unwrap(broker.attempt_workflow)
    with pytest.raises(InvalidComposition):
        body(migrated_db, "close1d-att", 1, _nested(6), 3)


def test_broker_admission_refuses_unadmitted_cwd_key(migrated_db):
    refused = broker.ensure_operation(
        migrated_db, operation_id="close1g-op", effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 1000, "max_output_bytes": 64, "cwd": "/tmp"},
        allocation_id="close1g-a", attempt_id="close1g-att")
    assert refused.code == ResultCode.INVALID_INPUT
    assert broker.read_operation(migrated_db, "close1g-op") is None


def _supported_claim(dsn: str, tag: str) -> str:
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "o"}, f"{tag}i"))
    store.acquire_work(dsn, _cmd({"investigation_id": f"{tag}-i",
                                  "attempt_id": f"{tag}-att"}, f"{tag}q"))
    obs = evidence.register_observation(
        dsn, _cmd({}, f"{tag}o"), f"{tag}-att", {"n": 1}, source_identity="src")
    claim = f"{tag}-claim"
    evidence.propose_claim(dsn, _cmd({}, f"{tag}c"), claim, {"p": 1}, [])
    evidence.admit_warrant(dsn, _cmd({}, f"{tag}w"), f"w_{claim}", claim,
                           "test-proc", "v1", [[(obs.data["receipt_id"], "observation")]])
    return claim


def test_check_use_refuses_future_epoch(migrated_db):
    dsn = migrated_db
    claim = _supported_claim(dsn, "close1e")
    current = int(store.get_control(dsn)["evidence_epoch"])
    assert evidence.check_use(dsn, claim, current)["supported"] is True
    with pytest.raises(MissingEvidence):
        evidence.check_use(dsn, claim, current + 1)


def test_scripted_double_unknown_task_is_protocol_error():
    double = ScriptedDouble(competence={}, fixes={}, broken={})
    request = ModelRequest(operation_id="close1f", model="double",
                           messages=({"role": "user",
                                      "content": json.dumps({"arm": "A",
                                                             "task_id": "nope"})},),
                           max_output_tokens=10, deadline_ms=1000)
    result = double.infer(request)
    assert isinstance(result, GatewayError)
    assert "nope" in result.message


def test_sibling_dsn_handles_keyword_and_url_forms(monkeypatch):
    monkeypatch.setenv("SETTLEMENT_TEST_DSN", "host=/var/run/postgresql dbname=base1")
    assert _conn_params("host=/var/run/postgresql dbname=base1")["dbname"] == "base1"
    assert _base_name() == "base1"
    sibling = _sibling_dsn("base1_wfshape")
    assert "dbname=base1_wfshape" in sibling and "://" not in sibling
    monkeypatch.setenv("SETTLEMENT_TEST_DSN",
                       "postgresql://ubuntu@/base2?host=/var/run/postgresql")
    assert _base_name() == "base2"
    sibling = _sibling_dsn("base2_wfshape")
    assert sibling == "postgresql://ubuntu@/base2_wfshape?host=/var/run/postgresql"
    monkeypatch.setenv("SETTLEMENT_TEST_DSN",
                       "postgresql:///base3?host=/var/run/postgresql")
    assert _sibling_dsn("base3_x") == "postgresql:///base3_x?host=/var/run/postgresql"


def test_make_database_roundtrip_keyword_dsn(migrated_db):
    from settlement import db as _db

    target = _sibling_dsn(f"{_base_name()}_close1sib")
    _make_database(target)
    _db.apply_migrations(target, Path(__file__).parent.parent / "migrations")
    assert store.get_control(target)["authority_version"] >= 0
    params = _conn_params(target)
    admin = " ".join(f"{k}={v}" for k, v in {**params, "dbname": "postgres"}.items()
                     if v != "")
    with _db.connect(admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE "{params["dbname"]}"')


def test_read_paths_use_bounded_timeouts(migrated_db):
    from settlement import db as _db

    assert _db.READ_CONNECT_TIMEOUT_S == 10
    assert _db.READ_STATEMENT_TIMEOUT == "60s"
    with _db.read_connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert cur.fetchone()[0] in ("60s", "1min")
        conn.commit()
    assert store.get_control(migrated_db)["authority_version"] >= 0
