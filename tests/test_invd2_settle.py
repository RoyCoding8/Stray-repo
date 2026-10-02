"""INV-D2 settle: unbilled model calls settle at measured tokens.

Real Postgres (inv_d2_settle, never live) in every test. Doubles sit at
the provider seam only. Every assertion names a literal durable outcome.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "INV_D2_DSN",
    "dbname=inv_d2_settle host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

PROMPT = "x" * 1746
MAX_OUT = 2048
EXPOSURE = 1746 // 4 + 1 + MAX_OUT


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                " AND tablename != 'schema_migrations'")
            for (table,) in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()


def _cmd(payload):
    from settlement.common import Command
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _payload():
    return {"model": "scripted",
            "messages": [{"role": "user", "content": PROMPT}],
            "max_output_tokens": MAX_OUT, "deadline_ms": 300_000}


class UnbilledGateway:
    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage
        return ModelResponse(
            request.operation_id, "hi", {"simulated": True},
            Usage(input_tokens=5, output_tokens=5,
                  charge_units=0, billed=False), "stop")

    def cancel(self, operation_id):
        return False


class BilledGateway:
    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage
        return ModelResponse(
            request.operation_id, "hi", {"simulated": True},
            Usage(input_tokens=5, output_tokens=7,
                  charge_units=42, billed=True), "stop")

    def cancel(self, operation_id):
        return False


class LostGateway:
    def infer(self, request):
        return None

    def cancel(self, operation_id):
        return False


def test_unbilled_model_call_settles_at_measured_tokens():
    from settlement import broker, store
    _fresh_db()
    store.seed_allocation(DSN, _cmd(
        {"allocation_id": "d2-a", "domain": "cpu", "authorized": 100000}))
    prepared = broker.ensure_operation(
        DSN, operation_id="d2-unbilled", effect=broker.MODEL_INFERENCE,
        payload=_payload(), allocation_id="d2-a")
    assert prepared.data["exposure"] == EXPOSURE == 2485
    status = broker.dispatch_operation(
        DSN, "d2-unbilled", launchers={}, gateway=UnbilledGateway())
    assert status.dispatch_state == "observed"
    ledger = store.allocation_status(DSN, "d2-a")
    assert (ledger["consumed"], ledger["reserved"]) == (10, 0)
    receipts = store.operation_receipts(DSN, "d2-unbilled")
    assert len(receipts) == 1
    usage = receipts[0]["content"]["usage"]
    assert usage["input_tokens"] == 5
    assert usage["output_tokens"] == 7 - 2
    assert usage["billed"] is False
    assert usage["charge_units"] == 0


def test_billed_model_call_settles_at_charge():
    from settlement import broker, store
    _fresh_db()
    store.seed_allocation(DSN, _cmd(
        {"allocation_id": "d2-b", "domain": "cpu", "authorized": 100000}))
    prepared = broker.ensure_operation(
        DSN, operation_id="d2-billed", effect=broker.MODEL_INFERENCE,
        payload=_payload(), allocation_id="d2-b")
    assert prepared.data["exposure"] == EXPOSURE == 2485
    status = broker.dispatch_operation(
        DSN, "d2-billed", launchers={}, gateway=BilledGateway())
    assert status.dispatch_state == "observed"
    ledger = store.allocation_status(DSN, "d2-b")
    assert (ledger["consumed"], ledger["reserved"]) == (42, 0)


def test_unknown_outcome_retains_reservation():
    from settlement import broker, store
    _fresh_db()
    store.seed_allocation(DSN, _cmd(
        {"allocation_id": "d2-u", "domain": "cpu", "authorized": 100000}))
    prepared = broker.ensure_operation(
        DSN, operation_id="d2-unknown", effect=broker.MODEL_INFERENCE,
        payload=_payload(), allocation_id="d2-u")
    assert prepared.data["exposure"] == EXPOSURE == 2485
    status = broker.dispatch_operation(
        DSN, "d2-unknown", launchers={}, gateway=LostGateway())
    assert status.dispatch_state == "unresolved"
    ledger = store.allocation_status(DSN, "d2-u")
    assert (ledger["consumed"], ledger["reserved"]) == (0, EXPOSURE)
