from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


from settlement.checkpoint import run_checkpoint
from settlement.restore import run_restore

from conftest_isolation import dbname_of, dsn_with_dbname
from settlement import broker, run, store
from settlement.common import Command, ResultCode
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher


def _dsn() -> str:
    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    return dsn


def _swap(dsn: str, name: str) -> str:
    return dsn_with_dbname(dsn, name)


# Every database this module creates, in the order it created them. A name
# lands here as it is made and leaves when it is dropped, so what is in this
# list is what the running session is still holding.
_FRESH_DATABASES: list[str] = []
# The same names, kept after they are dropped. The gate at the end of the
# module asks the server about these, which is a different question from
# asking this list, and so is not a restatement of it.
_EVERY_CREATED: list[str] = []


def _remember(name: str) -> None:
    _FRESH_DATABASES.append(name)
    _EVERY_CREATED.append(name)


def _drop(name: str) -> None:
    """Drop one database this module made, by name.

    ``IF EXISTS`` because a test may already have dropped it, and ``FORCE``
    because a test that was interrupted mid-connection would otherwise leave a
    backend attached and the drop would fail. The name is unique to one test
    run, so the only connections ``FORCE`` can terminate are this module's.
    """
    from settlement import db as _db

    admin = dsn_with_dbname(_dsn(), "postgres")
    with _db.connect(admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)'
                        % name.replace('"', '""'))


def _fresh_db(stem: str) -> str:
    from psycopg import errors as _pgerrors

    from settlement import db as _db

    target = _swap(_dsn(), f"{stem}_{uuid.uuid4().hex[:8]}")
    admin = dsn_with_dbname(target, "postgres")
    with _db.connect(admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f'CREATE DATABASE "{dbname_of(target)}"')
            except _pgerrors.DuplicateDatabase:
                pass
            except _pgerrors.InsufficientPrivilege as exc:
                pytest.fail(
                    "missing database prerequisite: role cannot CREATE DATABASE"
                    f" ({type(exc).__name__}: {exc})")
    _remember(dbname_of(target))
    return target


@pytest.fixture(autouse=True)
def _drop_what_this_test_created():
    """Drop each test's databases when that test ends.

    ``_fresh_db`` made a database and returned its DSN, and nothing dropped it
    afterwards, so a run of this file left its stores on the server. Six per
    run, from the four tests that call it. By 2026-09-29 that had accumulated
    into 345, 320 of them created that day.

    The ``s09iso`` sweep could not have recovered them as a backstop: it
    selects by ``DERIVED_NAME_RE``, which requires an ``s09iso_`` prefix these
    names do not carry. A name this module mints has to be a name this module
    drops.
    """
    mark = len(_FRESH_DATABASES)
    try:
        yield
    finally:
        created = _FRESH_DATABASES[mark:]
        del _FRESH_DATABASES[mark:]
        for name in created:
            _drop(name)


@pytest.fixture(scope="module", autouse=True)
def _no_database_outlives_this_module():
    """Fail the module if any database it created is still on the server.

    This is a gate, not a report: it is the assertion that the teardown above
    ran and worked, so removing that teardown turns this red.
    """
    yield
    from settlement import db as _db

    admin = dsn_with_dbname(_dsn(), "postgres")
    survivors = []
    with _db.connect(admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            for name in _EVERY_CREATED:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
                if cur.fetchone():
                    survivors.append(name)
    assert not survivors, ("this module left databases on the server: %s"
                           % (", ".join(survivors),))


def test_r03_database_prerequisite_explicit():
    from settlement import db as _db

    dsn = _dsn()
    check = _swap(dsn, f"r03flow_prereq_{uuid.uuid4().hex[:8]}")
    admin = dsn_with_dbname(check, "postgres")
    shown = dsn.rsplit("@", 1)[-1] if "@" in dsn else dsn
    try:
        with _db.connect(admin, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{dbname_of(check)}"')
        with _db.connect(admin, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE "{dbname_of(check)}"')
    except Exception as exc:
        pytest.fail(
            "missing database prerequisite: CREATE/DROP DATABASE failed"
            f" via SETTLEMENT_TEST_DSN={shown}"
            f" ({type(exc).__name__}: {exc})")


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
    dump_name = f"{dbname_of(wfdb)}.workflow.dump"
    shutil.copyfile(out_b / dump_name, mixed / dump_name)
    report = run_restore(mixed, _fresh_domain(), tmp_path / "restored",
                         workflow_target_dsn=_fresh_db("r03flow_wft"))
    assert report["ok"] is False
    assert any("steps differ" in item for item in report["mismatches"])


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
