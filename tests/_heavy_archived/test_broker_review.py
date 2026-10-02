import os
import threading
import uuid

from settlement import broker, run, store
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


def _cmd(payload):
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _comp(children):
    return run.Composition(
        revision=1, root={"kind": "sequence", "node_id": "root", "steps": children},
        allocation_id="a1", authority_version=1)


def test_revise_rejects_duplicate_node_ids():
    base = _comp([{"kind": "invoke", "node_id": "n1", "effect": "observation-adapter",
                   "payload": {"adapter": "clock"}}])
    try:
        run.revise(base, {"kind": "sequence", "node_id": "root",
                          "steps": [{"kind": "invoke", "node_id": "n1",
                                     "effect": "observation-adapter",
                                     "payload": {"adapter": "clock"}},
                                    {"kind": "invoke", "node_id": "n1",
                                     "effect": "observation-adapter",
                                     "payload": {"adapter": "clock"}}]})
    except run.InvalidComposition:
        return
    raise AssertionError("duplicate node ids admitted")


def test_revise_rejects_dangling_join_ref():
    base = _comp([{"kind": "invoke", "node_id": "n1", "effect": "observation-adapter",
                   "payload": {"adapter": "clock"}}])
    try:
        run.revise(base, {"kind": "sequence", "node_id": "root",
                          "steps": [{"kind": "join", "node_id": "j",
                                     "needs": {"o1": "ghost"}}]})
    except run.InvalidComposition:
        return
    raise AssertionError("dangling join ref admitted")


def test_concurrent_dispatch_spawns_exactly_once(migrated_db, tmp_path):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 10000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"investigation_id": "i1", "attempt_id": "att1"}))
    prepared = broker.ensure_operation(
        dsn, operation_id="op_race", effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"], "timeout_ms": 10_000,
                 "max_output_bytes": 1024},
        allocation_id="a1", attempt_id="att1")
    assert prepared.code == ResultCode.APPLIED
    launcher = LocalLauncher(tmp_path / "runs", grace_ms=500)
    outcomes = []
    barrier = threading.Barrier(8)

    def _go():
        barrier.wait()
        outcomes.append(broker.dispatch_operation(
            dsn, "op_race", launchers={"local-process": launcher}).next_decision)

    threads = [threading.Thread(target=_go) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    spawns = (tmp_path / "runs" / "op_race_exec-default.spawns").read_text().strip()
    assert spawns == "1", f"spawned {spawns} times under 8-way race"
    assert broker.read_operation(dsn, "op_race")["dispatch_state"] == "observed"


def test_stop_kills_process_group(tmp_path):
    import time as _time

    launcher = LocalLauncher(tmp_path / "runs", grace_ms=500)
    op = broker.BrokerOp(operation_id="op_stop", effect="sandbox-exec",
                         payload={"profile": "local-process",
                                  "argv": ["/bin/sleep", "30"],
                                  "timeout_ms": 60_000, "max_output_bytes": 1024},
                         execution_version="exec-v1")
    outcomes = []
    worker = threading.Thread(target=lambda: outcomes.append(launcher.dispatch(op)))
    worker.start()
    deadline = _time.monotonic() + 10
    while not launcher.is_live("op_stop") and _time.monotonic() < deadline:
        _time.sleep(0.05)
    assert launcher.is_live("op_stop") is True
    assert launcher.stop("op_stop") is True
    worker.join(timeout=70)
    assert not worker.is_alive()
    assert launcher.is_live("op_stop") is False
    assert outcomes and outcomes[0].sent is True


def test_stop_unknown_operation_is_false(tmp_path):
    assert LocalLauncher(tmp_path / "runs").stop("never-ran") is False
