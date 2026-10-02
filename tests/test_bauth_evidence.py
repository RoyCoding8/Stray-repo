import os
import uuid
from pathlib import Path

from experiments.coord02 import schemas_evidence as SE
from experiments.coord02 import experience as E
from experiments.coord02.controller import seed_episode
from settlement import broker, db
from settlement.common import ResultCode

DSN = os.environ.get("EC02_BAUTH_DSN",
                     "dbname=ec02test_bauth host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"


def _settle_model_op(dsn: str, operation_id: str, allocation_id: str,
                     usage: dict) -> None:
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "b-auth-probe", "messages": [{"role": "user",
                                                        "content": "probe"}],
                 "max_output_tokens": 16, "deadline_ms": 10_000},
        allocation_id=allocation_id)
    assert ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    admitted = broker.admit_launcher_receipt(
        dsn, operation_id, broker.ReceiptProposal(
            receipt_identity="bauth:%s" % operation_id,
            content={"usage": dict(usage)}, outcome="success",
            provenance="b-auth"))
    assert admitted.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)


def test_store_derived_costs_sum_nonuniform_receipts():
    assert "live" not in DSN and "ec02test_bauth" in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="B-AUTH slice 1 store-derived costs")
    E.prepare_disposable_db(DSN, MIGRATIONS)
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
