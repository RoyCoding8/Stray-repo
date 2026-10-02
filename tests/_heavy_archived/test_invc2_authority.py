"""INV-C2 M2 gate: one explicitly authorized study root.

Real Postgres (`inv_c2_auth` and `inv_c2_auth2`, never live) in every test.
Doubles sit at the provider seam only: a recording gateway answers model
calls and the local launcher runs sandboxes. Every assertion names a
literal durable outcome: refusals after exhaustion, missing authority on a
fresh database with zero reproduced calls, children funded from remaining
parent authority, and independently summed receipts and liabilities.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "INV_C2_DSN",
    "dbname=inv_c2_auth host=/var/run/postgresql user=ubuntu")
DSN2 = os.environ.get(
    "INV_C2_DSN2",
    "dbname=inv_c2_auth2 host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"


def _fresh_db(dsn: str):
    assert "live" not in dsn
    from settlement import db
    db.apply_migrations(dsn, MIGRATIONS)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                " AND tablename != 'schema_migrations'")
            for (table,) in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()


class RecordingGateway:
    def __init__(self, texts, charge_units=0, billed=False):
        from settlement.gateway import Usage
        self._texts = list(texts)
        self._usage = Usage(input_tokens=11, output_tokens=7,
                            charge_units=charge_units, billed=billed)
        self.calls: list = []

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            self._texts[min(len(self.calls) - 1, len(self._texts) - 1)],
            {"simulated": True}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def _diag_payload():
    return {"model": "scripted",
            "messages": [{"role": "user", "content": "hi"}],
            "max_output_tokens": 8, "deadline_ms": 10_000}


def _sandbox_payload():
    return {"profile": "local-process", "argv": ["/bin/true"],
            "timeout_ms": 10_000, "max_output_bytes": 1024}


def _exposure(effect, payload):
    from settlement import broker
    return broker.exposure_schedule(effect, payload)[0]


def _counts(dsn):
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM operations")
            ops = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM receipts")
            receipts = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM allocations")
            allocs = cur.fetchone()[0]
            conn.commit()
    return ops, receipts, allocs


def test_exhausted_parent_refuses_init_repair_use(tmp_path):
    from settlement import authority, broker
    from settlement.launcher_local import LocalLauncher
    from settlement.loop import Refusal
    _fresh_db(DSN)
    diag_exposure = _exposure(broker.MODEL_INFERENCE, _diag_payload())
    handle = authority.authorize_study(
        DSN, "study-exhaust", authorized=diag_exposure)
    assert handle.authorized == diag_exposure
    gateway = RecordingGateway(["ok"], charge_units=3, billed=True)
    launcher = LocalLauncher(tmp_path / "runs")
    launchers = {"local-process": launcher}
    granted = authority.admit_study_call(
        DSN, "study-exhaust", kind="calibration",
        operation_id="study-exhaust-cal-0",
        effect=broker.MODEL_INFERENCE, payload=_diag_payload())
    assert granted.exposure == diag_exposure
    assert authority.study_remaining(DSN, "study-exhaust") == 0
    assert broker.dispatch_operation(
        DSN, "study-exhaust-cal-0",
        launchers={}, gateway=gateway).dispatch_state == "observed"
    for kind, op_id in (("development", "study-exhaust-dev-0"),
                        ("repair", "study-exhaust-rep-0"),
                        ("use", "study-exhaust-use-0")):
        refused = authority.admit_study_call(
            DSN, "study-exhaust", kind=kind, operation_id=op_id,
            effect=broker.SANDBOX_EXEC, payload=_sandbox_payload())
        assert isinstance(refused, Refusal)
        assert refused.reason == "insufficient-authority"
        assert broker.read_operation(DSN, op_id) is None
    assert _counts(DSN) == (1, 1, 2)


def test_same_study_on_fresh_db_refuses_without_renewal():
    from settlement import authority, broker
    from settlement.loop import Refusal
    _fresh_db(DSN)
    _fresh_db(DSN2)
    handle = authority.authorize_study(
        DSN, "study-shared", authorized=10_000)
    gateway = RecordingGateway(["ok"])
    granted = authority.admit_study_call(
        DSN, "study-shared", kind="calibration",
        operation_id="study-shared-b0-cal",
        effect=broker.MODEL_INFERENCE, payload=_diag_payload())
    assert broker.dispatch_operation(
        DSN, "study-shared-b0-cal",
        launchers={}, gateway=gateway).dispatch_state == "observed"
    assert len(gateway.calls) == 1
    assert _counts(DSN) == (1, 1, 2)
    try:
        authority.bind_study(DSN2, "study-shared")
        bound = True
    except authority.MissingAuthority as exc:
        bound = False
        assert "study-shared" in str(exc)
    assert bound is False
    fresh_gateway = RecordingGateway(["ok"])
    refused = authority.admit_study_call(
        DSN2, "study-shared", kind="development",
        operation_id="study-shared-b0-dev",
        effect=broker.MODEL_INFERENCE, payload=_diag_payload())
    assert isinstance(refused, Refusal)
    assert refused.reason == "missing-authority"
    assert fresh_gateway.calls == []
    assert _counts(DSN2) == (0, 0, 0)
    reopened = authority.bind_study(DSN, "study-shared")
    assert reopened.authorized == handle.authorized == 10_000
    from settlement import store
    assert store.allocation_status(
        DSN, "study-shared")["authorized"] == 10_000
    retagged = authority.admit_study_call(
        DSN, "study-shared", kind="development",
        operation_id="study-shared-b1-dev",
        effect=broker.MODEL_INFERENCE, payload=_diag_payload())
    assert retagged.exposure == granted.exposure
    assert store.allocation_status(
        DSN, "study-shared")["authorized"] == 10_000
    assert authority.study_remaining(
        DSN, "study-shared") == 10_000 - 2 * granted.exposure


def test_children_come_from_remaining_parent():
    from settlement import authority, broker, store
    from settlement.loop import Grant, Refusal
    _fresh_db(DSN)
    authority.authorize_study(DSN, "study-split", authorized=100)
    dev_exposure = _exposure(broker.MODEL_INFERENCE, _diag_payload())
    assert dev_exposure < 100
    granted = authority.admit_study_call(
        DSN, "study-split", kind="development",
        operation_id="study-split-dev-0",
        effect=broker.MODEL_INFERENCE, payload=_diag_payload())
    assert isinstance(granted, Grant)
    child = store.allocation_status(DSN, "study-split/development/study-split-dev-0")
    assert child["parent_id"] == "study-split"
    assert child["authorized"] == dev_exposure
    assert authority.study_remaining(DSN, "study-split") == 100 - dev_exposure
    oversized = {"model": "scripted",
                 "messages": [{"role": "user", "content": "x" * 400}],
                 "max_output_tokens": 8, "deadline_ms": 10_000}
    refused = authority.admit_study_call(
        DSN, "study-split", kind="repair",
        operation_id="study-split-rep-oversized",
        effect=broker.MODEL_INFERENCE, payload=oversized)
    assert isinstance(refused, Refusal)
    assert refused.reason == "insufficient-authority"
    try:
        store.allocation_status(DSN, "study-split/repair/study-split-rep-oversized")
        funded = True
    except Exception:
        funded = False
    assert funded is False
    repeat = authority.admit_study_call(
        DSN, "study-split", kind="development",
        operation_id="study-split-dev-0",
        effect=broker.MODEL_INFERENCE, payload=_diag_payload())
    assert isinstance(repeat, Grant)
    assert repeat.already is True
    assert authority.study_remaining(DSN, "study-split") == 100 - dev_exposure


def test_ledger_independently_sums_receipts_and_liabilities(tmp_path):
    from settlement import authority, broker, db, store
    from settlement.launcher_local import LocalLauncher
    _fresh_db(DSN)
    authority.authorize_study(DSN, "study-ledger", authorized=10_000)
    billed = RecordingGateway(["ok"], charge_units=3, billed=True)

    class LostGateway:
        def infer(self, request):
            return None

        def cancel(self, operation_id):
            return False

    launcher = LocalLauncher(tmp_path / "runs")
    launchers = {"local-process": launcher}
    diag_exposure = _exposure(broker.MODEL_INFERENCE, _diag_payload())
    sandbox_exposure = _exposure(broker.SANDBOX_EXEC, _sandbox_payload())
    assert broker.dispatch_operation(
        DSN, authority.admit_study_call(
            DSN, "study-ledger", kind="calibration",
            operation_id="study-ledger-cal",
            effect=broker.MODEL_INFERENCE,
            payload=_diag_payload()).operation_id,
        launchers={}, gateway=billed).dispatch_state == "observed"
    assert broker.dispatch_operation(
        DSN, authority.admit_study_call(
            DSN, "study-ledger", kind="development",
            operation_id="study-ledger-dev",
            effect=broker.MODEL_INFERENCE,
            payload=_diag_payload()).operation_id,
        launchers={}, gateway=LostGateway()).dispatch_state == "unresolved"
    assert broker.dispatch_operation(
        DSN, authority.admit_study_call(
            DSN, "study-ledger", kind="use",
            operation_id="study-ledger-use",
            effect=broker.SANDBOX_EXEC,
            payload=_sandbox_payload()).operation_id,
        launchers=launchers, gateway=billed).dispatch_state == "observed"
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "WITH RECURSIVE study_allocs AS ("
                " SELECT id FROM allocations WHERE id = 'study-ledger'"
                " UNION SELECT a.id FROM allocations a"
                " JOIN study_allocs s ON a.parent_id = s.id)"
                " SELECT COALESCE(SUM((r.content->'usage'->>'charge_units')::int), 0)"
                " FROM receipts r JOIN operations o ON o.id = r.operation_id"
                " WHERE r.outcome IN ('success', 'failure')"
                " AND r.content->'usage'->>'billed' = 'true'"
                " AND o.allocation_id IN (SELECT id FROM study_allocs)")
            measured = cur.fetchone()[0]
            cur.execute(
                "WITH RECURSIVE study_allocs AS ("
                " SELECT id FROM allocations WHERE id = 'study-ledger'"
                " UNION SELECT a.id FROM allocations a"
                " JOIN study_allocs s ON a.parent_id = s.id)"
                " SELECT receipt_identity FROM receipts r"
                " JOIN operations o ON o.id = r.operation_id"
                " WHERE r.outcome = 'unknown'"
                " AND o.allocation_id IN (SELECT id FROM study_allocs)"
                " ORDER BY receipt_identity")
            unknown = [row[0] for row in cur.fetchall()]
            cur.execute(
                "WITH RECURSIVE study_allocs AS ("
                " SELECT id FROM allocations WHERE id = 'study-ledger'"
                " UNION SELECT a.id FROM allocations a"
                " JOIN study_allocs s ON a.parent_id = s.id)"
                " SELECT COALESCE(SUM(consumed), 0), COALESCE(SUM(reserved), 0)"
                " FROM allocations WHERE id IN (SELECT id FROM study_allocs)")
            consumed, reserved = cur.fetchone()
            conn.commit()
    assert measured == 3
    assert unknown == ["gw:study-ledger-dev:lost-response"]
    assert consumed == 3 + sandbox_exposure
    assert reserved == diag_exposure
    ledger = authority.verify_ledger(DSN, "study-ledger")
    assert ledger["measured"] == measured == 3
    assert ledger["unknown"] == unknown == ["gw:study-ledger-dev:lost-response"]
    assert ledger["consumed"] == consumed == 3 + sandbox_exposure
    assert ledger["reserved"] == reserved == diag_exposure
    assert ledger["match"] is True
    assert store.allocation_status(
        DSN, "study-ledger")["authorized"] == 10_000


def test_ledger_counts_receiptless_killed_operation_as_pending():
    from settlement import authority, broker, db
    _fresh_db(DSN)
    authority.authorize_study(DSN, "study-killed", authorized=10_000)
    grant = authority.admit_study_call(
        DSN, "study-killed", kind="development",
        operation_id="study-killed-dev",
        effect=broker.MODEL_INFERENCE, payload=_diag_payload())
    assert grant.operation_id == "study-killed-dev"
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE operations SET dispatch_state = 'dispatching'"
                        " WHERE id = 'study-killed-dev'")
        conn.commit()
    ledger = authority.verify_ledger(DSN, "study-killed")
    assert ledger["unreceipted"] == ["study-killed-dev"]
    assert ledger["pending"] == grant.exposure
    assert ledger["reserved"] == grant.exposure
    assert ledger["consumed"] == 0
    # The operation is `dispatching` with no receipt, so it has left the queue
    # and no receipt will arrive to settle it. Those units are stranded, not
    # pending, and the ledger must not reconcile them away: before N-202 the
    # match test compared reserved against pending, and this operation
    # contributed to both sides, so the ledger agreed with itself about
    # exposure nothing would ever release.
    assert ledger["stranded"] == {"study-killed-dev": grant.exposure}
    assert ledger["match"] is False
