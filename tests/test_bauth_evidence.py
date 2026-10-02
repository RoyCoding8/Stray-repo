import os
import uuid
from pathlib import Path

from experiments.coord02 import schemas_evidence as SE
from experiments.coord02 import experience as E
from experiments.coord02.controller import seed_episode
from settlement import broker, db, store
from settlement.common import Command, ResultCode

DSN = os.environ.get("EC02_BAUTH_DSN",
                     "dbname=ec02test_bauth host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"
PURPOSE = "B-AUTH slice 1 store-derived costs"


def _settle_model_op(dsn: str, operation_id: str, allocation_id: str,
                     usage: dict) -> None:
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "b-auth-probe", "messages": [{"role": "user",
                                                        "content": "probe"}],
                 "max_output_tokens": 16, "deadline_ms": 10_000},
        allocation_id=allocation_id)
    assert ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    advanced = store.advance_dispatch(
        DSN, Command(request_id="bauth-adv-%s" % operation_id,
                     payload={"operation_id": operation_id,
                              "launcher_id": "gateway",
                              "provider_id": "b-auth-probe"}))
    assert advanced.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    # A `model-inference` success receipt has to name the response it is a
    # receipt for and carry the text that came back. `broker._send_model`
    # builds the production shape at broker.py:723-731 and it has both
    # fields; this helper used to send `content={"usage": ...}` alone, which
    # the store refuses, so this test asserted on costs it could never reach.
    # What it costs is named here so the accounting under test stays the
    # accounting under test.
    admitted = broker.admit_launcher_receipt(
        dsn, operation_id, broker.ReceiptProposal(
            receipt_identity="bauth:%s" % operation_id,
            content={"operation_id": operation_id,
                     "text": "b-auth probe response",
                     "usage": dict(usage)},
            outcome="success",
            provenance="b-auth"))
    assert admitted.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)


def _designation_rows(dsn: str) -> list:
    from psycopg.rows import dict_row
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT to_regclass(%s) AS reg", (E.DESIGNATION_TABLE,))
            if cur.fetchone()["reg"] is None:
                conn.commit()
                return []
            cur.execute(f"SELECT kind, purpose FROM "
                        f"{E.DESIGNATION_TABLE} ORDER BY created_at")
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def test_store_derived_costs_sum_nonuniform_receipts():
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    # designate_db only ever appends, so an inherited designation is the one
    # way this store can belong to another battery. Check it before the write
    # below, or the check just reads back the row the test itself made.
    inherited = _designation_rows(DSN)
    assert not inherited or inherited[-1]["purpose"] == PURPOSE, inherited
    E.designate_db(DSN, kind="disposable", purpose=PURPOSE)
    E.prepare_disposable_db(DSN, MIGRATIONS)
    assert _designation_rows(DSN)[-1] == {"kind": "disposable",
                                           "purpose": PURPOSE}
    seed = seed_episode(DSN, "bauth-s1-%s" % uuid.uuid4().hex[:8], {"m": "1"})
    allocation = seed["allocation_id"]
    op_ids = []
    for usage in ({"input_tokens": 7, "output_tokens": 11, "model_calls": 1},
                  {"input_tokens": 13, "output_tokens": 29,
                   "model_calls": 1}):
        op_id = "bauth-s1-%s" % uuid.uuid4().hex[:8]
        _settle_model_op(DSN, op_id, allocation, usage)
        op_ids.append(op_id)
    assert SE.costs_for_operations(DSN, op_ids) == {"in": 20, "out": 40,
                                                   "calls": 2}
    assert SE.costs_for_operations(
        DSN, [op_ids[0], op_ids[0], op_ids[1]]) == {"in": 20, "out": 40,
                                                   "calls": 2}
