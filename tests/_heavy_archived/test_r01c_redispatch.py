from __future__ import annotations

import threading
import uuid

from settlement import broker, store
from settlement.broker import BrokerOp
from settlement.common import Command
from settlement.launcher_local import LocalLauncher


def _cmd(payload):
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _seed(dsn, tag):
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 10_000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"investigation_id": f"{tag}-i",
                                  "attempt_id": f"{tag}-att"}))
    broker.ensure_operation(
        dsn, operation_id=f"{tag}-op", effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024},
        allocation_id=f"{tag}-a", attempt_id=f"{tag}-att")
    return f"{tag}-op"


def _op(operation_id, generation):
    return BrokerOp(operation_id=operation_id, effect="sandbox-exec",
                    payload={"profile": "local-process", "argv": ["/bin/true"],
                             "timeout_ms": 10_000, "max_output_bytes": 1024},
                    execution_version="exec-default", dispatch_generation=generation)


def test_generation_record_written_and_voids_never_sent_proof(tmp_path):
    launcher = LocalLauncher(tmp_path / "runs")
    assert launcher.prove_never_sent("gen-op") is True
    out = launcher.dispatch(_op("gen-op", 7))
    assert out.sent is True and out.receipt is not None
    assert (tmp_path / "runs" / "gen-op_exec-default.gen").read_text().strip() == "7"
    assert launcher.prove_never_sent("gen-op") is False
    assert launcher.prove_never_sent("gen-op", 7) is False
    assert launcher.prove_never_sent("other-op") is True


def test_paused_before_claim_fenced_by_reset(migrated_db, tmp_path, monkeypatch):
    dsn = migrated_db
    op = _seed(dsn, "r01ca")
    launcher = LocalLauncher(tmp_path / "runs")
    launchers = {"local-process": launcher, "local": launcher}
    real_claim, entered, release, calls = (
        LocalLauncher._claim, threading.Event(), threading.Event(), [])

    def gated(self, path):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=30)
        return real_claim(self, path)

    monkeypatch.setattr(LocalLauncher, "_claim", gated)
    holder = {}
    worker = threading.Thread(target=lambda: holder.setdefault(
        "status", broker.dispatch_operation(dsn, op, launchers=launchers)))
    worker.start()
    assert entered.wait(timeout=30)
    # The worker is parked inside `_claim`, so the launcher has written
    # nothing: no pid, spawns, generation or result file. That is the one
    # state a never-sent proof honestly describes, and it is the state
    # `redispatch_after_reset` exists for, so this test takes the real path
    # rather than a bare store reset with no proof behind it.
    assert launcher.prove_never_sent(op, 1) is True, (
        "precondition: the reset below needs a launchable launcher, and a "
        "launcher that already sent cannot honestly certify a reset")
    status = broker.redispatch_after_reset(dsn, op, launchers, expected_generation=1)
    assert status.sent_this_call is True
    assert broker.read_operation(dsn, op)["dispatch_state"] == "observed"
    release.set()
    worker.join(timeout=60)
    assert not worker.is_alive()
    assert holder["status"].sent_this_call is False
    assert (tmp_path / "runs" / "r01ca-op_exec-default.spawns").read_text().strip() == "1"
    assert (tmp_path / "runs" / "r01ca-op_exec-default.gen").read_text().strip() == "3"


def test_paused_after_claim_never_spawns(tmp_path, monkeypatch):
    launcher = LocalLauncher(tmp_path / "runs")
    real_record, entered, release, calls = (
        LocalLauncher._recorded_generation, threading.Event(), threading.Event(), [])

    def gated(self, path):
        if not calls and path.exists():
            calls.append(1)
            entered.set()
            assert release.wait(timeout=30)
        return real_record(self, path)

    monkeypatch.setattr(LocalLauncher, "_recorded_generation", gated)
    holder = {}
    worker = threading.Thread(target=lambda: holder.setdefault(
        "old", launcher.dispatch(_op("race-op", 1))))
    worker.start()
    assert entered.wait(timeout=30)
    newer = launcher.dispatch(_op("race-op", 2))
    assert newer.sent is False and newer.refused_reason == "superseded-claim"
    release.set()
    worker.join(timeout=60)
    assert not worker.is_alive()
    old = holder["old"]
    assert old.sent is False and old.refused_reason == "superseded-generation"
    assert list((tmp_path / "runs").glob("race-op_*.spawns")) == []
    assert list((tmp_path / "runs").glob("race-op_*.result.json")) == []
    assert (tmp_path / "runs" / "race-op_exec-default.gen").read_text().strip() == "2"
    assert launcher.prove_never_sent("race-op", 2) is False
