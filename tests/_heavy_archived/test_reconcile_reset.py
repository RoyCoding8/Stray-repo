import shutil
import uuid

from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


def _cmd(payload):
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _seed(dsn, tag="rr"):
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 10_000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"investigation_id": f"{tag}-i", "attempt_id": f"{tag}-att",
                                  "allocation_id": f"{tag}-a"}))
    broker.ensure_operation(
        dsn, operation_id=f"{tag}-op", effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"], "timeout_ms": 10_000,
                 "max_output_bytes": 1024},
        allocation_id=f"{tag}-a", attempt_id=f"{tag}-att")
    return f"{tag}-op"


def _advanced(dsn, op, launcher_id=None):
    from settlement.launcher_local import LocalLauncher

    advanced = store.advance_dispatch(
        dsn, _cmd({"operation_id": op, "launcher_id": launcher_id or LocalLauncher.launcher_id,
                   "execution_version": "exec-default"}))
    assert advanced.code == ResultCode.APPLIED
    assert broker.read_operation(dsn, op)["dispatch_state"] == "dispatching"


def test_advanced_but_unsent_resets_and_redispatches_once(migrated_db, tmp_path):
    dsn = migrated_db
    op = _seed(dsn)
    _advanced(dsn, op)
    launcher = LocalLauncher(tmp_path / "runs")
    launchers = {"local-process": launcher, "local": launcher}
    refused = broker.redispatch_after_reset(dsn, op, launchers, expected_generation=99)
    assert refused.sent_this_call is False
    assert refused.next_decision == "reset-refused-stale_revision"
    assert broker.read_operation(dsn, op)["dispatch_state"] == "dispatching"
    assert list((tmp_path / "runs").glob("*.spawns")) == []
    generation = int(broker.read_operation(dsn, op)["payload"]["_dispatch_generation"])
    status = broker.redispatch_after_reset(dsn, op, launchers,
                                           expected_generation=generation)
    assert status.sent_this_call is True and status.dispatch_state == "observed"
    spawns = list((tmp_path / "runs").glob("*.spawns"))
    assert len(spawns) == 1 and spawns[0].read_text().strip() == "1"


def test_post_claim_crash_parks_instead_of_resetting(migrated_db, tmp_path):
    dsn = migrated_db
    op = _seed(dsn, "rc")
    _advanced(dsn, op)
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    (run_dir / "rc-op_exec-default.pid").write_text("999999999")
    launcher = LocalLauncher(run_dir)
    decision = broker.reconcile(dsn, op, {"local-process": launcher, "local": launcher})
    assert decision.decision == "unresolved-liability"
    assert broker.read_operation(dsn, op)["dispatch_state"] == "unresolved"


def test_recorded_receipt_never_resets(migrated_db, tmp_path):
    dsn = migrated_db
    op = _seed(dsn, "rx")
    _advanced(dsn, op)
    broker.admit_launcher_receipt(dsn, op, broker.ReceiptProposal(
        receipt_identity="re:rx", content={"ok": True}, outcome="success",
        provenance="test"))
    launcher = LocalLauncher(tmp_path / "runs")
    decision = broker.reconcile(dsn, op, {"local-process": launcher, "local": launcher})
    assert decision.decision == "already-terminal"
    assert broker.read_operation(dsn, op)["dispatch_state"] == "observed"


def test_cancel_requested_never_resets(migrated_db, tmp_path):
    dsn = migrated_db
    op = _seed(dsn, "cx")
    _advanced(dsn, op)
    assert store.request_cancellation(dsn, _cmd({"operation_id": op})).code \
        == ResultCode.APPLIED
    launcher = LocalLauncher(tmp_path / "runs")
    decision = broker.reconcile(dsn, op, {"local-process": launcher, "local": launcher})
    assert decision.decision == "unresolved-liability"
    assert "requested" in broker.read_operation(dsn, op)["cancel_state"]


def test_wiped_run_state_parks_instead_of_resetting(migrated_db, tmp_path):
    dsn = migrated_db
    op = _seed(dsn, "wx")
    _advanced(dsn, op)
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    launcher = LocalLauncher(run_dir)
    shutil.rmtree(run_dir)
    decision = broker.reconcile(dsn, op, {"local-process": launcher, "local": launcher})
    assert decision.decision == "unresolved-liability"


def test_reset_refuses_prepared_and_unknown(migrated_db):
    dsn = migrated_db
    op = _seed(dsn, "rz")
    assert store.reset_dispatch(dsn, _cmd({"operation_id": op})).code \
        == ResultCode.INVALID_INPUT
    assert store.reset_dispatch(dsn, _cmd({"operation_id": "ghost"})).code \
        == ResultCode.INVALID_INPUT
