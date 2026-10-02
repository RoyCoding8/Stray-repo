from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from checkpoint import run_checkpoint
from restore import run_restore

from settlement import broker, run, store
from settlement.common import Command, ResultCode
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher


def _dsn() -> str:
    return os.environ["SETTLEMENT_TEST_DSN"]


def _swap(dsn: str, name: str) -> str:
    parts = urllib.parse.urlsplit(dsn)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, ""))


def _fresh_db(stem: str) -> str:
    from psycopg import errors as _pgerrors

    from settlement import db as _db

    target = _swap(_dsn(), f"{stem}_{uuid.uuid4().hex[:8]}")
    parts = urllib.parse.urlsplit(target)
    admin = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, ""))
    with _db.connect(admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f'CREATE DATABASE "{parts.path.lstrip("/")}"')
            except _pgerrors.DuplicateDatabase:
                pass
    return target


def _fresh_domain() -> str:
    return _fresh_db("r03flow_dom")


def _fresh_workflow_shape() -> str:
    from settlement import db as _db

    target = _fresh_db("r03flow_wf")
    with _db.connect(target, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE SCHEMA "dbos"')
            cur.execute('CREATE TABLE "dbos".workflow_status (workflow_uuid TEXT PRIMARY KEY,'
                        " status TEXT, inputs TEXT)")
            cur.execute('CREATE TABLE "dbos".operation_outputs (workflow_uuid TEXT,'
                        " function_id INTEGER, output TEXT, error TEXT, child_workflow_id TEXT)")
    return target


def _cmd(payload: dict, tag: str) -> Command:
    return Command(request_id=f"r03_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _composition(node_id="n", retry_max=0, argv=("/bin/true",), allocation="r03-a"):
    return {"version": "run/v1", "revision": 1, "allocation_id": allocation,
            "authority_version": 1,
            "root": {"kind": "invoke", "node_id": node_id, "effect": "sandbox-exec",
                     "retry_max": retry_max,
                     "payload": {"profile": "local-process", "argv": list(argv),
                                 "timeout_ms": 30_000, "max_output_bytes": 1024}}}


def _seed(dsn, tag, composition=None) -> dict:
    assert store.seed_grant(
        dsn, _cmd({"version": 1, "charter_text": "r03",
                   "authority_grant": {}, "envelopes": {}}, f"{tag}g")).code == ResultCode.APPLIED
    assert store.seed_allocation(
        dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                   "authorized": 5000}, f"{tag}a")).code == ResultCode.APPLIED
    assert store.admit_commitment(
        dsn, _cmd({"investigation_id": f"{tag}-i", "objective": "r03"}, f"{tag}i")
    ).code == ResultCode.APPLIED
    payload = {"attempt_id": f"{tag}-att", "investigation_id": f"{tag}-i"}
    if composition is not None:
        payload["composition"] = json.dumps(composition)
    acquired = store.acquire_work(dsn, _cmd(payload, f"{tag}q"))
    assert acquired.code == ResultCode.APPLIED
    return {"allocation": f"{tag}-a", "attempt": f"{tag}-att",
            "generation": acquired.data["ownership_generation"]}


def _launchers(run_dir: Path) -> dict:
    launcher = LocalLauncher(run_dir)
    return {"local-process": launcher, launcher.launcher_id: launcher}


def test_checkpoint_refuses_continuation_commit_mid_backup(migrated_db, tmp_path):
    dsn = migrated_db
    env = _seed(dsn, "r03c")
    comp = run.Composition.model_validate(_composition(allocation=env["allocation"]))
    cont = run.register_ops(comp, run.fresh_continuation(comp, env["attempt"]),
                            {"n": "r03c-att:n"})
    run.record_continuation(dsn, env["attempt"], cont, "r03c:setup", None)
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")

    def _interleave(barrier):
        run.record_continuation(dsn, env["attempt"], cont, "r03c:mid-backup", None)

    with pytest.raises(SystemExit, match="continuations moved"):
        run_checkpoint(dsn, art, tmp_path / "backup", _between=_interleave)


def test_checkpoint_preserves_restore_pause(migrated_db, tmp_path):
    dsn = migrated_db
    _seed(dsn, "r03p")
    fenced = store.restore_fence(
        dsn, _cmd({"reason": "restore", "source_commit": "c", "source_database": "src"},
                  "r03pf"))
    assert fenced.code == ResultCode.APPLIED
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    out = tmp_path / "backup"
    run_checkpoint(dsn, art, out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["barrier"]["pre_paused"] is True
    assert manifest["barrier"]["pause_owner"] == "restore"
    control = store.get_control(dsn)
    assert bool(control["dispatch_paused"]) is True
    assert control["paused_reason"] == "restore"


def test_checkpoint_verify_detects_pause_flip(migrated_db):
    dsn = migrated_db
    _seed(dsn, "r03v")
    barrier = store.checkpoint_barrier(dsn, _cmd({}, "r03vb")).data
    assert store.resume_dispatch(
        dsn, _cmd({"reason": "operator"}, "r03vr")).code == ResultCode.APPLIED
    mismatches = store.checkpoint_verify(dsn, barrier)
    assert any("pause flipped" in item for item in mismatches)
    assert any("pause owner moved" in item for item in mismatches)


def test_restore_rebinds_dbos_workflow_inputs(migrated_db, tmp_path):
    dsn = migrated_db
    _seed(dsn, "r03b")
    wfdb = _fresh_workflow_shape()
    from settlement import db as _db

    with _db.connect(wfdb, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO "dbos".workflow_status (workflow_uuid, status, inputs)'
                        " VALUES (%s, %s, %s)",
                        ("wf-r03b", "PENDING", json.dumps({"args": [dsn, "r03b-att", 1]})))
            cur.execute('INSERT INTO "dbos".operation_outputs (workflow_uuid, function_id,'
                        " output, error, child_workflow_id) VALUES (%s, %s, %s, %s, %s)",
                        ("wf-r03b", 1, "step-one", "", ""))
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    out = tmp_path / "backup"
    run_checkpoint(dsn, art, out, workflow_dsn=wfdb)
    assert json.loads((out / "manifest.json").read_text())["workflow"]["kind"] == "dbos-system"
    domain_target, wf_target = _fresh_domain(), _fresh_db("r03flow_wft")
    restored = tmp_path / "restored"
    report = run_restore(out, domain_target, restored, workflow_target_dsn=wf_target)
    assert report["ok"], report["mismatches"]
    assert report["workflow"]["rebound_inputs"] == 1
    with _db.connect(wf_target) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT inputs FROM "dbos".workflow_status WHERE workflow_uuid = %s',
                        ("wf-r03b",))
            inputs = cur.fetchone()[0]
            conn.commit()
    assert domain_target in inputs and dsn not in inputs


def test_restore_refuses_mixed_recovery_set(migrated_db, tmp_path):
    dsn = migrated_db
    _seed(dsn, "r03m")
    wfdb = _fresh_workflow_shape()
    from settlement import db as _db

    with _db.connect(wfdb, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO "dbos".workflow_status (workflow_uuid, status, inputs)'
                        " VALUES (%s, %s, %s)", ("wf-r03m", "PENDING", "[]"))
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    out_a = tmp_path / "backup_a"
    run_checkpoint(dsn, art, out_a, workflow_dsn=wfdb)
    with _db.connect(wfdb, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO "dbos".operation_outputs (workflow_uuid, function_id,'
                        " output, error, child_workflow_id) VALUES (%s, %s, %s, %s, %s)",
                        ("wf-r03m", 2, "late-step", "", ""))
    out_b = tmp_path / "backup_b"
    run_checkpoint(dsn, art, out_b, workflow_dsn=wfdb)
    mixed = tmp_path / "mixed"
    shutil.copytree(out_a, mixed)
    dump_name = f"{urllib.parse.urlsplit(wfdb).path.lstrip('/')}.workflow.dump"
    shutil.copyfile(out_b / dump_name, mixed / dump_name)
    report = run_restore(mixed, _fresh_domain(), tmp_path / "restored",
                         workflow_target_dsn=_fresh_db("r03flow_wft"))
    assert report["ok"] is False
    assert any("steps differ" in item for item in report["mismatches"])


def test_repair_scan_wakes_waiting_workflow_after_restart(migrated_db, tmp_path):
    dsn = migrated_db
    comp = _composition(allocation="r03w-a")
    env = _seed(dsn, "r03w", composition=comp)
    op = f"{env['attempt']}:n"
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    launchers = _launchers(run_dir)
    assert broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 1024},
        allocation_id=env["allocation"], attempt_id=env["attempt"],
        execution_version="run/v1").code == ResultCode.APPLIED
    validated = run.Composition.model_validate(comp)
    cont = run.register_ops(validated, run.fresh_continuation(validated, env["attempt"]),
                            {"n": op})
    run.record_continuation(dsn, env["attempt"], cont, "r03w:setup", None)
    status = broker.dispatch_operation(dsn, op, launchers=launchers,
                                       ownership_generation=env["generation"],
                                       _crash_after_send=True)
    assert status.dispatch_state == "dispatching"
    assert store.operation_receipts(dsn, op) == []
    broker.ATTEMPT_WORKFLOW_RESOURCES.pop(env["attempt"], None)

    def _scan():
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "scripts" / "scheduler.py"),
             "--dsn", dsn, "--run-dir", str(run_dir)],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")})
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    first = _scan()
    assert f"wake:{env['attempt']}" in first["repaired"]
    snap = broker.wf_snapshot(dsn, env["attempt"])
    assert snap["continuation"]["completed"] == {"n": f"op:{op}"}
    assert store.scan_outbox(dsn) == []
    receipts = [r["receipt_identity"] for r in store.operation_receipts(dsn, op)]
    assert len(receipts) == 1
    before = snap["continuation"]
    second = _scan()
    assert broker.wf_snapshot(dsn, env["attempt"])["continuation"] == before
    assert [r["receipt_identity"] for r in store.operation_receipts(dsn, op)] == receipts
    assert second["next_decision"] in ("idle", "work-done", "repair-done")


def test_positive_retry_budget_runs_bounded_fresh_operations(migrated_db, tmp_path, monkeypatch):
    dsn = migrated_db
    comp = _composition(retry_max=1, argv=("/bin/false",), allocation="r03t-a")
    env = _seed(dsn, "r03t", composition=comp)
    broker.ATTEMPT_WORKFLOW_RESOURCES[env["attempt"]] = {
        "launchers": _launchers(tmp_path / "runs"), "gateway": FakeGatewayAdapter()}
    monkeypatch.setattr(broker, "DBOS", SimpleNamespace(
        run_step=lambda _ctx, fn, *args: fn(*args)))
    result = inspect.unwrap(broker.attempt_workflow)(
        dsn, env["attempt"], env["generation"], comp, 10)
    assert result["outcome"] == "completed", result
    assert result["rounds"] == 5
    base, retry = f"{env['attempt']}:n", f"{env['attempt']}:n:retry1"
    assert broker.read_operation(dsn, base)["dispatch_state"] == "observed"
    assert broker.read_operation(dsn, retry)["dispatch_state"] == "observed"
    assert broker.read_operation(dsn, f"{env['attempt']}:n:retry2") is None
    assert len(list((tmp_path / "runs").glob("*.spawns"))) == 2
    snap = broker.wf_snapshot(dsn, env["attempt"])["continuation"]
    assert snap["completed"] == {"n": f"op:{retry}:failed"}
    assert snap["observations"]["n:tries"] == [base, retry]


def test_uncertain_operation_never_gains_retry_identity(migrated_db, tmp_path, monkeypatch):
    dsn = migrated_db
    comp = _composition(retry_max=2, argv=("/bin/true",), allocation="r03u-a")
    env = _seed(dsn, "r03u", composition=comp)

    class _Silent:
        launcher_id = "silent-1"

        def prior_send(self, operation_id):
            return False

        def live_ids(self):
            return []

        def is_live(self, operation_id):
            return False

        def read_result(self, operation_id):
            return None

        def dispatch(self, op):
            return broker.LaunchOutcome(sent=True)

    silent = _Silent()
    broker.ATTEMPT_WORKFLOW_RESOURCES[env["attempt"]] = {
        "launchers": {"local-process": silent, silent.launcher_id: silent},
        "gateway": FakeGatewayAdapter()}
    monkeypatch.setattr(broker, "DBOS", SimpleNamespace(
        run_step=lambda _ctx, fn, *args: fn(*args)))
    result = inspect.unwrap(broker.attempt_workflow)(
        dsn, env["attempt"], env["generation"], comp, 6)
    assert result["outcome"] == "waiting", result
    base = f"{env['attempt']}:n"
    assert broker.read_operation(dsn, base)["dispatch_state"] == "dispatching"
    assert broker.read_operation(dsn, f"{base}:retry1") is None
    assert store.operation_receipts(dsn, base) == []
    snap = broker.wf_snapshot(dsn, env["attempt"])["continuation"]
    assert snap["completed"] == {}
    assert "n:tries" not in snap["observations"]
