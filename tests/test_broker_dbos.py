from __future__ import annotations

import urllib.parse
import uuid

import pytest
from psycopg import errors as _pgerrors

from settlement import broker, run, store
from settlement.common import Command, ResultCode
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher

SYSTEM_DB_SUFFIX = "_dbos"


def _base_name(dsn: str) -> str:
    return urllib.parse.urlparse(dsn).path.lstrip("/") or "settlement"


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _swap_db(dsn: str, name: str) -> str:
    base = urllib.parse.urlparse(dsn).path.lstrip("/") or "settlement"
    head, sep, tail = dsn.partition(base)
    assert sep, f"unexpected test DSN shape {dsn!r}"
    return head + name + tail


def _system_dsn(dsn: str) -> str:
    return _swap_db(dsn, _base_name(dsn) + SYSTEM_DB_SUFFIX)


@pytest.fixture(scope="module")
def dbos_home():
    import os

    from settlement import db as _db

    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    sys_dsn = _system_dsn(dsn)
    with _db.connect(_swap_db(dsn, "postgres"), autocommit=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f'CREATE DATABASE "{_base_name(dsn) + SYSTEM_DB_SUFFIX}"')
            except _pgerrors.DuplicateDatabase:
                pass
    broker.init_dbos(sys_dsn)
    yield sys_dsn
    broker.shutdown_dbos()


def _setup(dsn):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 1000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _composition():
    def _invoke(node_id):
        return {"kind": "invoke", "node_id": node_id, "effect": "sandbox-exec",
                "payload": {"profile": "local-process", "argv": ["/bin/true"],
                            "timeout_ms": 5_000, "max_output_bytes": 1024}}

    return {"version": "run/v1", "revision": 1, "allocation_id": "a1", "authority_version": 1,
            "root": {"kind": "sequence", "node_id": "sq1",
                     "steps": [_invoke("n1"), _invoke("n2")] }}


def test_attempt_workflow_runs_two_ops_to_completion(migrated_db, dbos_home, tmp_path):
    from dbos import DBOS, SetWorkflowID

    dsn = migrated_db
    gen = _setup(dsn)
    launcher = LocalLauncher(run_dir=tmp_path / "runs")
    broker.ATTEMPT_WORKFLOW_RESOURCES["att1"] = {
        "launchers": {"local-process": launcher}, "gateway": FakeGatewayAdapter()}
    comp = _composition()
    with SetWorkflowID(f"wf-att1-test1-{uuid.uuid4().hex[:8]}"):
        handle = DBOS.start_workflow(broker.attempt_workflow, dsn, "att1", gen, comp, 10)
        result = handle.get_result()
    assert result["outcome"] == "completed" and result["rounds"] == 3
    assert broker.read_operation(dsn, "att1:n1")["dispatch_state"] == "observed"
    assert broker.read_operation(dsn, "att1:n2")["dispatch_state"] == "observed"
    assert store.scan_outbox(dsn) == []
    spawns = sorted((tmp_path / "runs").glob("*.spawns"))
    assert len(spawns) == 2
    assert all(p.read_text().strip() == "1" for p in spawns)


def test_duplicate_workflow_id_never_resends(migrated_db, dbos_home, tmp_path):
    from dbos import DBOS, SetWorkflowID

    dsn = migrated_db
    gen = _setup(dsn)
    launcher = LocalLauncher(run_dir=tmp_path / "runs")
    broker.ATTEMPT_WORKFLOW_RESOURCES["att1"] = {
        "launchers": {"local-process": launcher}, "gateway": FakeGatewayAdapter()}
    comp = _composition()
    wid = f"wf-att1-test2-{uuid.uuid4().hex[:8]}"
    with SetWorkflowID(wid):
        first = DBOS.start_workflow(broker.attempt_workflow, dsn, "att1", gen, comp, 10)
        assert first.get_result()["outcome"] == "completed"
    with SetWorkflowID(wid):
        second = DBOS.start_workflow(broker.attempt_workflow, dsn, "att1", gen, comp, 10)
        assert second.get_result()["outcome"] == "completed"
    spawns = sorted((tmp_path / "runs").glob("*.spawns"))
    assert len(spawns) == 2
    assert all(p.read_text().strip() == "1" for p in spawns)


def test_record_step_replay_is_idempotent(migrated_db):
    dsn = migrated_db
    _setup(dsn)
    comp = run.Composition.model_validate(_composition())
    cont = run.fresh_continuation(comp, "att1")
    summary = {"node_id": "n1", "operation_id": "att1:n1", "dispatch_state": "observed",
               "next_decision": "terminal"}
    comp_dict = _composition()
    first = broker.wf_record(dsn, "att1", comp_dict, cont.model_dump(), summary,
                             "dbos:probe:record")
    assert first["completed"] == {"n1": "op:att1:n1"}
    assert broker.wf_record(dsn, "att1", comp_dict, cont.model_dump(), summary,
                            "dbos:probe:record") == first
    from settlement import db as _db
    from psycopg.rows import dict_row

    with _db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT continuation_ref FROM attempts WHERE id = 'att1'")
            stored = cur.fetchone()["continuation_ref"]
            conn.commit()
    assert "op:att1:n1" in stored
    assert store.read_events(dsn)["events"]
