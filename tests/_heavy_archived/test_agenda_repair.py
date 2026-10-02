import json
import uuid

from settlement import agenda, broker, store
from settlement.common import Command, ResultCode


def _cmd(payload):
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _sandbox(dsn, operation_id):
    broker.ensure_operation(
        dsn, operation_id=operation_id, effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"], "timeout_ms": 10_000,
                 "max_output_bytes": 1024},
        allocation_id="a1", attempt_id="att1")


def test_repair_scan_converges_advanced_unsent(migrated_db, tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parents[2]))
    from scripts.scheduler import redispatch_reset, run_once

    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu",
                                     "authorized": 10_000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"investigation_id": "i1", "attempt_id": "att1",
                                  "allocation_id": "a1"}))
    _sandbox(dsn, "op1")
    _sandbox(dsn, "op2")
    from settlement.launcher_local import LocalLauncher

    for operation_id in ("op1", "op2"):
        advanced = store.advance_dispatch(
            dsn, _cmd({"operation_id": operation_id, "launcher_id": LocalLauncher.launcher_id,
                       "execution_version": "exec-default"}))
        assert advanced.code == ResultCode.APPLIED
    redo = redispatch_reset(dsn, tmp_path / "runs", "op1", expected_generation=1)
    assert redo["sent_this_call"] is True and redo["dispatch_state"] == "observed"
    assert broker.read_operation(dsn, "op1")["dispatch_state"] == "observed"
    assert broker.read_operation(dsn, "op2")["dispatch_state"] == "dispatching"
    summary = run_once(dsn, tmp_path / "runs")
    assert broker.read_operation(dsn, "op2")["dispatch_state"] == "unresolved"
    # op2 converges to unresolved, and the sweep is what drove it there: the
    # row reads unresolved only after run_once, never before. It is absent
    # from `repaired` because that key means "this scan settled something",
    # and an unresolved-liability decision recovered nothing. Listing it
    # would claim a settlement that did not happen. The same exclusion is
    # pinned for the identical state in test_c9_repaired_key_meaning.py.
    assert "op2" not in summary["repaired"]
    assert summary["repaired"] == []
    assert summary["next_decision"] == "idle"
    assert agenda.collect_wakeups(dsn)["wakeups"]
    json.dumps(summary)
    json.dumps(redo)
