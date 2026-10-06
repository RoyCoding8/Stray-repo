"""INV-F2 gate: post-effect cost reads observe receipt content.

Real Postgres (`inv_f2_loop`, never live) in every test. Doubles sit at
the provider seam only: a recording gateway answers model calls.
Every assertion names a literal durable outcome: billed charge units
surface as measured cost, unknown receipts stay listed with zero
measured, and journaled observations carry the settled receipt content.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conftest_isolation import admin_dsn  # noqa: E402

DSN = os.environ.get("INV_F2_DSN", "dbname=inv_f2_loop")
MIGRATIONS = ROOT / "migrations"


def _fresh_db():
    # Routeless the authority refuses and the test skips (conftest_isolation)
    # instead of connecting on a guessed socket.
    admin_dsn()
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


def _study(authorized=100_000):
    from settlement import store
    from settlement.loop import ResourceEnvelope
    store.admit_commitment(DSN, _cmd({"investigation_id": "i1", "objective": "o"}))
    return ResourceEnvelope.bind(DSN, "st1", authorized)


class RecordingGateway:
    def __init__(self, texts, billed=True):
        from settlement.gateway import Usage
        self._texts = list(texts)
        self._usage = Usage(input_tokens=11, output_tokens=7,
                            charge_units=3, billed=billed)
        self.calls: list = []

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            self._texts[min(len(self.calls) - 1, len(self._texts) - 1)],
            {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


class LostGateway:
    def infer(self, request):
        return None

    def cancel(self, operation_id):
        return False


def _model_inputs():
    return {"model": "scripted", "prompt": "hi", "max_output_tokens": 8}


def test_measured_costs_read_billed_receipt_content():
    _fresh_db()
    from settlement import broker
    from settlement.loop import Grant, admit_effect, read_measured_costs

    _study()
    granted = admit_effect(
        DSN, allocation_id="st1", operation_id="model-1",
        effect=broker.MODEL_INFERENCE,
        payload={"model": "scripted",
                 "messages": [{"role": "user", "content": "hi"}],
                 "max_output_tokens": 8, "deadline_ms": 10_000},
        attempt_id=None, kind="diagnose")
    assert isinstance(granted, Grant)
    status = broker.dispatch_operation(DSN, "model-1",
                                       gateway=RecordingGateway(["hi"]))
    assert status.dispatch_state == "observed"
    costs = read_measured_costs(DSN, "model-1")
    assert costs["measured"] == 3
    assert costs["unknown"] == []


def test_unknown_receipt_stays_listed_with_zero_measured():
    _fresh_db()
    from settlement import broker, store
    from settlement.loop import Grant, admit_effect, read_measured_costs

    _study()
    granted = admit_effect(
        DSN, allocation_id="st1", operation_id="model-u",
        effect=broker.MODEL_INFERENCE,
        payload={"model": "scripted",
                 "messages": [{"role": "user", "content": "hi"}],
                 "max_output_tokens": 8, "deadline_ms": 10_000},
        attempt_id=None, kind="diagnose")
    assert isinstance(granted, Grant)
    broker.dispatch_operation(DSN, "model-u", gateway=LostGateway())
    costs = read_measured_costs(DSN, "model-u")
    assert costs["measured"] == 0
    assert costs["provider_charge_units"] is None
    receipt = store.operation_receipts(DSN, "model-u")[-1]
    assert receipt["outcome"] == "unknown"
    assert costs["unknown"] == [receipt["receipt_identity"]]
    assert receipt["receipt_identity"] == "gw:model-u:%s" % receipt["content"][
        "response_class"]
    assert receipt["content"]["response_received"] is False


def _packet():
    from experiments.ad01.packet import decision_packet
    return decision_packet(
        charter={"objective": "x", "freeze_id": "ad01"},
        visible=["t1"],
        experience={"observations": [{"observation_id": "obs-0", "task_id": "t1",
                                      "capability_id": "seed", "verdict": "unmeasured",
                                      "detail": "d"}]},
        retained=[], remaining={"queries": 6, "model_calls": 60},
        curriculum="t1", boundary={"world": 0, "arm": "I", "seq": 0})


def test_run_boundary_observation_carries_receipt_content():
    _fresh_db()
    from settlement.loop import run_boundary

    _study()

    def _propose(materialized, state):
        return {"target": "t1", "instrument": "note",
                "inputs": {"payload": {}, "idempotency_key": "k1"},
                "dependencies": [], "requested": {}, "hypothesis": None}

    transition, state = run_boundary(
        DSN, study_root="st1", allocation_id="st1",
        packet=_packet(), propose=_propose)
    assert transition.admission == "admitted"
    assert state.observations[-1]["content"] == {
        "command": "note", "payload": {}, "idempotency_key": "k1"}
