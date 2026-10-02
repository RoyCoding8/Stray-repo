from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import pytest
from psycopg import errors as _pgerrors

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from checkpoint import run_checkpoint
from restore import run_restore

from settlement import broker, db, run, store
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_local import LocalLauncher

REPO = Path(__file__).parent.parent


def _base(dsn: str) -> str:
    name = urllib.parse.urlparse(dsn).path.lstrip("/") or "settlement"
    assert name, f"unexpected test DSN shape {dsn!r}"
    return name


def _cmd(payload: dict, tag: str = "", **kw) -> Command:
    return Command(request_id=f"r01_{tag}_{uuid.uuid4().hex[:10]}", payload=payload, **kw)


def _swap(dsn: str, name: str) -> str:
    base = _base(dsn)
    head, sep, tail = dsn.partition(base)
    assert sep, f"unexpected test DSN shape {dsn!r}"
    return head + name + tail


def _fresh_db(dsn: str, name: str) -> str:
    with db.connect(_swap(dsn, "postgres"), autocommit=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f'CREATE DATABASE "{name}"')
            except _pgerrors.DuplicateDatabase:
                pass
    target = _swap(dsn, name)
    db.apply_migrations(target, REPO / "migrations")
    with db.connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                        " AND tablename != 'schema_migrations'")
            for (table,) in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()
    return target


@pytest.fixture()
def restore_dsn(dsn):
    return _fresh_db(dsn, f"{_base(dsn)}_restore")


@pytest.fixture()
def workflow_dsn(dsn):
    return _fresh_db(dsn, f"{_base(dsn)}_wf")


def _composition(alloc: str, node: str = "n1", argv=("bin-true",)) -> dict:
    argv = ["/bin/true"] if argv == ("bin-true",) else list(argv)
    return {"version": "run/v1", "revision": 1, "allocation_id": alloc,
            "authority_version": 1,
            "root": {"kind": "sequence", "node_id": "sq1",
                     "steps": [{"kind": "invoke", "node_id": node, "effect": "sandbox-exec",
                                "payload": {"profile": "local-process", "argv": argv,
                                            "timeout_ms": 30_000, "max_output_bytes": 1024}}]}}


def _seed(dsn, tag, comp=None) -> dict:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "r01",
                                "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 5000}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "r01"}, f"{tag}i"))
    payload = {"attempt_id": f"{tag}-att", "investigation_id": f"{tag}-i"}
    if comp is not None:
        payload["composition"] = json.dumps(comp)
    acquired = store.acquire_work(dsn, _cmd(payload, f"{tag}q"))
    return {"allocation": f"{tag}-a", "attempt": f"{tag}-att",
            "generation": acquired.data["ownership_generation"]}


def _sandbox_op(dsn, tag, env, node="n1", argv=("/bin/true",), version="run/v1") -> str:
    op = f"{tag}-att:{node}"
    result = broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": list(argv),
                 "timeout_ms": 30_000, "max_output_bytes": 1024},
        allocation_id=env["allocation"], attempt_id=env["attempt"],
        execution_version=version)
    assert result.code == ResultCode.APPLIED, result.detail
    return op


def _journal_count(dsn) -> int:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM command_journal")
            n = int(cur.fetchone()[0])
            conn.commit()
    return n


def test_checkpoint_manifest_carries_barrier(migrated_db, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    _seed(dsn, "r06a")
    out = tmp_path / "backup"
    run_checkpoint(dsn, art, out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert set(manifest["barrier"]) >= {"barrier_epoch", "journal_count", "outbox_pending"}
    assert manifest["journal_count"] == _journal_count(dsn) - 1
    assert manifest["barrier"]["barrier_epoch"] == manifest["control"]["admission_epoch"] >= 1
    assert manifest["outbox_pending"] == []
    assert manifest["workflow"]["coordinated"] is False


def test_checkpoint_detects_concurrent_write(migrated_db, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    _seed(dsn, "r06b")
    out = tmp_path / "backup"

    def _race(_barrier):
        store.seed_grant(dsn, _cmd({"version": 2, "charter_text": "race",
                                    "authority_grant": {}, "envelopes": {}}, "race"))

    with pytest.raises(SystemExit, match="barrier"):
        run_checkpoint(dsn, art, out, _between=_race)
    assert not (out / "manifest.json").exists()


def test_checkpoint_coordinates_workflow_store(migrated_db, workflow_dsn, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    _seed(dsn, "r06c")
    out = tmp_path / "backup"
    result = run_checkpoint(dsn, art, out, workflow_dsn=workflow_dsn)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["workflow"]["coordinated"] is True
    assert Path(result["workflow_dump"]).stat().st_size > 0
    assert manifest["workflow"]["barrier"]["barrier_epoch"] >= 1


def test_restore_fences_old_dispatcher(migrated_db, restore_dsn, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    runs = tmp_path / "runs"
    art.mkdir()
    runs.mkdir()
    (art / "seed.txt").write_text("seed")
    env = _seed(dsn, "r06d")
    att, gen = env["attempt"], env["generation"]
    op_idle = _sandbox_op(dsn, "r06d", env, node="idle")
    op_live = _sandbox_op(dsn, "r06d", env, node="live")
    launcher = LocalLauncher(runs)
    crashed = broker.dispatch_operation(dsn, op_live, launchers={"local-process": launcher},
                                        ownership_generation=gen, _crash_after_send=True)
    assert crashed.dispatch_state == "dispatching" and crashed.sent_this_call
    live_gen = int(broker.read_operation(dsn, op_live)["payload"]["_dispatch_generation"])
    out = tmp_path / "backup"
    run_checkpoint(dsn, art, out)
    report = run_restore(out, restore_dsn, tmp_path / "restored-art")
    assert report["ok"] is True, report["mismatches"]
    assert report["fence"]["attempts"] == [{"id": att, "ownership_generation": gen + 1}]
    assert report["fence"]["dispatch_paused"] is True
    held = store.advance_dispatch(
        restore_dsn, _cmd({"operation_id": op_idle, "launcher_id": "gateway",
                           "ownership_generation": gen + 1}, "held"))
    assert held.code == ResultCode.INVALID_INPUT and "paused" in held.detail
    resumed = store.resume_dispatch(restore_dsn, _cmd({"reason": "test-reconciled"}, "resume"))
    assert resumed.code == ResultCode.APPLIED
    stale = store.advance_dispatch(
        restore_dsn, _cmd({"operation_id": op_idle, "launcher_id": "gateway",
                           "ownership_generation": gen}, "stale"))
    assert stale.code == ResultCode.STALE_REVISION
    refused = broker.dispatch_operation(
        restore_dsn, op_idle, launchers={"local-process": launcher}, ownership_generation=gen)
    assert refused.sent_this_call is False and "stale" in refused.next_decision
    assert len(list(runs.glob("*.spawns"))) == 1
    fenced = broker._finish_send(
        restore_dsn, op_live, broker.LaunchOutcome(
            sent=True, receipt=broker.ReceiptProposal(
                receipt_identity=f"stale:{op_live}", content={"text": "old dispatcher"},
                outcome="success", provenance="old")),
        live_gen)
    assert fenced.sent_this_call is True
    late = broker.read_operation(restore_dsn, op_live)
    assert late["dispatch_state"] == "observed"
    receipts = {r["receipt_identity"] for r in store.operation_receipts(restore_dsn, op_live)}
    assert f"stale:{op_live}" in receipts
    assert f"fenced:{op_live}:g{live_gen}" in receipts
    reset = store.reset_dispatch(
        restore_dsn, _cmd({"operation_id": op_live, "expected_generation": live_gen + 2},
                          "resetlate"))
    assert reset.code != ResultCode.APPLIED
    fresh = broker.ensure_operation(
        restore_dsn, operation_id="r06d-fresh", effect=broker.OBSERVATION_ADAPTER,
        payload={"adapter": "clock", "input": {}}, allocation_id=env["allocation"],
        attempt_id=att)
    assert fresh.code == ResultCode.APPLIED, fresh.detail
    done = broker.dispatch_operation(restore_dsn, "r06d-fresh", launchers={},
                                     ownership_generation=gen + 1)
    assert done.dispatch_state == "observed" and done.sent_this_call


def test_post_backup_external_action_reconciled(migrated_db, restore_dsn, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    runs = tmp_path / "runs"
    art.mkdir()
    runs.mkdir()
    (art / "seed.txt").write_text("seed")
    env = _seed(dsn, "r06e")
    op = _sandbox_op(dsn, "r06e", env, node="n1")
    launcher = LocalLauncher(runs)
    crashed = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                        ownership_generation=env["generation"],
                                        _crash_after_send=True)
    assert crashed.dispatch_state == "dispatching"
    out = tmp_path / "backup"
    run_checkpoint(dsn, art, out)
    broker.admit_launcher_receipt(dsn, op, broker.ReceiptProposal(
        receipt_identity=f"late:{op}", content={"text": "post-backup effect"},
        outcome="success", provenance="local-post-backup"))
    assert broker.read_operation(dsn, op)["dispatch_state"] == "observed"
    report = run_restore(out, restore_dsn, tmp_path / "restored-art")
    assert report["ok"] is True, report["mismatches"]
    assert broker.read_operation(restore_dsn, op)["dispatch_state"] == "dispatching"
    assert any(u["id"] == op for u in report["unfinished_operations"])


_CHILD = """
import json, sys
sys.path.insert(0, "SRC")
p = json.loads(sys.argv[1])
from settlement import broker
from settlement.launcher_local import LocalLauncher
assert p["attempt"] not in broker.ATTEMPT_WORKFLOW_RESOURCES
broker.restore_workflow_resources(
    p["dsn"], p["attempt"], {"local-process": LocalLauncher(p["runs"])},
    admitted_execution_versions=("run/v1",))
launchers = broker.ATTEMPT_WORKFLOW_RESOURCES[p["attempt"]]["launchers"]
decision = broker.reconcile(p["dsn"], p["op"], launchers)
out = broker.wf_consume(p["dsn"], p["attempt"], p["comp"], p["cont"], p["node"],
                        p["op"], "freshproc:consume")
print(json.dumps({"reconciled": decision.decision, "applied": out["applied"],
                  "outcome": out["outcome"]["outcome"],
                  "continuation": out["continuation"]}))
""".replace("SRC", str(REPO / "src"))


def test_fresh_process_consumes_delayed_result(migrated_db, tmp_path):
    dsn = migrated_db
    runs = tmp_path / "runs"
    runs.mkdir()
    comp = _composition("r13a-a")
    env = _seed(dsn, "r13a", comp)
    att = env["attempt"]
    broker.ATTEMPT_WORKFLOW_RESOURCES.pop(att, None)
    op = _sandbox_op(dsn, "r13a", env)
    launcher = LocalLauncher(runs)
    crashed = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                        ownership_generation=env["generation"],
                                        _crash_after_send=True)
    assert crashed.dispatch_state == "dispatching"
    cont = run.fresh_continuation(run.Composition.model_validate(comp), att)
    cont = run.register_ops(run.Composition.model_validate(comp), cont, {"n1": op})
    payload = {"dsn": dsn, "attempt": att, "op": op, "node": "n1",
               "runs": str(runs), "comp": comp, "cont": cont.model_dump(mode="json")}
    try:
        proc = subprocess.run([sys.executable, "-c", _CHILD, json.dumps(payload)],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["reconciled"] == "receipt-admitted"
        assert result["applied"] is True and result["outcome"] == "success"
        assert result["continuation"]["completed"] == {"n1": f"op:{op}"}
        assert att not in broker.ATTEMPT_WORKFLOW_RESOURCES
        assert broker.read_operation(dsn, op)["dispatch_state"] == "observed"
        assert len(list(runs.glob("*.spawns"))) == 1
    finally:
        broker.ATTEMPT_WORKFLOW_RESOURCES.pop(att, None)


def test_failed_invocation_never_completes(migrated_db, tmp_path):
    dsn = migrated_db
    runs = tmp_path / "runs"
    runs.mkdir()
    comp = _composition("r13b-a", argv=("/bin/false",))
    env = _seed(dsn, "r13b", comp)
    op = _sandbox_op(dsn, "r13b", env, argv=("/bin/false",))
    status = broker.dispatch_operation(dsn, op, launchers={"local-process": LocalLauncher(runs)},
                                       ownership_generation=env["generation"])
    assert status.dispatch_state == "observed" and status.sent_this_call
    assert run.operation_outcome(dsn, op)["outcome"] == "failure"
    cont = run.fresh_continuation(run.Composition.model_validate(comp), env["attempt"])
    done = broker.wf_record(dsn, env["attempt"], comp, cont.model_dump(mode="json"),
                            {"node_id": "n1", "operation_id": op,
                             "dispatch_state": "observed", "next_decision": "terminal"},
                            "dbos:probe:failed")
    assert "n1" not in done["completed"]
    assert done["observations"] == {"n1:outcome": "failure"}


def test_receipt_consumed_exactly_once(migrated_db, tmp_path):
    dsn = migrated_db
    runs = tmp_path / "runs"
    runs.mkdir()
    comp = _composition("r13c-a")
    env = _seed(dsn, "r13c", comp)
    op = _sandbox_op(dsn, "r13c", env)
    status = broker.dispatch_operation(dsn, op, launchers={"local-process": LocalLauncher(runs)},
                                       ownership_generation=env["generation"])
    assert status.dispatch_state == "observed"
    validated = run.Composition.model_validate(comp)
    cont = run.fresh_continuation(validated, env["attempt"]).model_dump(mode="json")
    first = broker.wf_consume(dsn, env["attempt"], comp, cont, "n1", op, "probe:consume")
    assert first["applied"] is True
    assert first["continuation"]["completed"] == {"n1": f"op:{op}"}
    second = broker.wf_consume(dsn, env["attempt"], comp, first["continuation"], "n1", op,
                               "probe:consume")
    assert second["applied"] is False
    assert second["continuation"] == first["continuation"]


def test_workflow_resources_need_durable_restore(migrated_db):
    dsn = migrated_db
    comp = _composition("r13d-a")
    env = _seed(dsn, "r13d", comp)
    _sandbox_op(dsn, "r13d", env, version="run/v9")
    with pytest.raises(SettlementError, match="unadmitted"):
        broker.restore_workflow_resources(dsn, env["attempt"], {}, admitted_execution_versions=("run/v1",))
    with pytest.raises(SettlementError, match="restore_workflow_resources"):
        broker.wf_ensure_dispatch(dsn, {"operation_id": "r13d-att:n1", "effect": "sandbox-exec",
                                        "payload": {"profile": "local-process",
                                                    "argv": ["/bin/true"],
                                                    "timeout_ms": 30_000,
                                                    "max_output_bytes": 1024},
                                        "allocation_id": env["allocation"],
                                        "attempt_id": env["attempt"]},
                                  0, env["generation"], "n1", "r13d-att")


def test_control_row_lock_wait_bounded_by_deadline(migrated_db):
    dsn = migrated_db
    store.get_control(dsn)
    ready, release = threading.Event(), threading.Event()

    def _holder():
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM control WHERE id = 1 FOR UPDATE")
                ready.set()
                release.wait(10)
            conn.commit()

    worker = threading.Thread(target=_holder, daemon=True)
    worker.start()
    assert ready.wait(10)
    try:
        start = time.monotonic()
        result = store.seed_grant(
            dsn, _cmd({"version": 7, "charter_text": "lock",
                       "authority_grant": {}, "envelopes": {}}, "lock",
                      deadline_ms=800))
        elapsed = time.monotonic() - start
    finally:
        release.set()
        worker.join(10)
    assert result.code == ResultCode.UNAVAILABLE_DEPENDENCY, result.detail
    assert "deadline" in result.detail
    assert elapsed < 5
    assert store.seed_grant(
        dsn, _cmd({"version": 7, "charter_text": "lock",
                   "authority_grant": {}, "envelopes": {}}, "lock2")).code == ResultCode.APPLIED
