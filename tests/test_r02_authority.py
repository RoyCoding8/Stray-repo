from __future__ import annotations

import inspect
import json
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from checkpoint import run_checkpoint
from restore import run_restore

from settlement import broker, capabilities, run, store
from settlement.common import Command, CommandResult, ResultCode
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher


def _cmd(payload: dict, tag: str = "", **kw) -> Command:
    return Command(request_id=f"r02_{tag}_{uuid.uuid4().hex[:10]}", payload=payload, **kw)


def _seed(dsn, tag, obligations=None) -> dict:
    assert store.seed_grant(
        dsn, _cmd({"version": 1, "charter_text": "r02",
                   "authority_grant": {}, "envelopes": {}}, f"{tag}g")).code == ResultCode.APPLIED
    assert store.seed_allocation(
        dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                   "authorized": 5000}, f"{tag}a")).code == ResultCode.APPLIED
    assert store.admit_commitment(
        dsn, _cmd({"investigation_id": f"{tag}-i", "objective": "r02",
                   "obligations": obligations or {}}, f"{tag}i")).code == ResultCode.APPLIED
    acquired = store.acquire_work(
        dsn, _cmd({"attempt_id": f"{tag}-att", "investigation_id": f"{tag}-i"}, f"{tag}q"))
    assert acquired.code == ResultCode.APPLIED
    return {"allocation": f"{tag}-a", "attempt": f"{tag}-att",
            "generation": acquired.data["ownership_generation"]}


def _sandbox(dsn, op, env, argv=("/bin/true",)) -> None:
    result = broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": list(argv),
                 "timeout_ms": 30_000, "max_output_bytes": 1024},
        allocation_id=env["allocation"], attempt_id=env["attempt"],
        execution_version="run/v1")
    assert result.code == ResultCode.APPLIED, result.detail


def _fulfill_payload(dsn, inv, attempt, gen, obligations):
    control = store.get_control(dsn)
    return {"investigation_id": inv, "attempt_id": attempt,
            "ownership_generation": gen, "revision": 1,
            "authority_version": int(control["authority_version"]),
            "evidence_epoch": int(control["evidence_epoch"]),
            "obligations": obligations}


def test_stale_generation_sender_never_sends(monkeypatch):
    admissions = iter([(ResultCode.APPLIED, 1), (ResultCode.ALREADY_APPLIED, 3)])
    sent = []

    def advance(*args):
        code, generation = next(admissions)
        return CommandResult(code=code, request_id="probe", data={
            "dispatch_generation": generation, "admitted": code == ResultCode.APPLIED})

    class Gateway(FakeGatewayAdapter):
        def infer(self, request):
            sent.append(request.operation_id)
            return super().infer(request)

    row = {"dispatch_state": "dispatching", "reconcile_state": "none",
           "cancel_state": "none", "settled": False}
    monkeypatch.setattr(broker, "_advance", advance)
    monkeypatch.setattr(broker, "read_operation", lambda *args: dict(row))
    op = broker.BrokerOp(operation_id="op", effect=broker.MODEL_INFERENCE,
                         payload={"model": "fake", "messages": [],
                                  "max_output_tokens": 5, "deadline_ms": 1000})
    status = broker._send_model("unused", {}, op, {}, Gateway(), 1, 1, False)
    assert sent == []
    assert status.next_decision == "stale-dispatch-generation"
    assert status.sent_this_call is False


def test_stale_owner_refused_end_to_end(migrated_db, tmp_path):
    dsn = migrated_db
    env = _seed(dsn, "r02a")
    _sandbox(dsn, "r02a-att:n", env)
    launcher = LocalLauncher(tmp_path / "runs")
    first = store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02a-att:n", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "a1"))
    assert first.code == ResultCode.APPLIED
    fenced = store.restore_fence(dsn, _cmd({"reason": "test"}, "fence"))
    assert fenced.code == ResultCode.APPLIED
    retry = broker.dispatch_operation(
        dsn, "r02a-att:n", launchers={"local-process": launcher},
        ownership_generation=env["generation"])
    assert retry.sent_this_call is False
    assert list((tmp_path / "runs").glob("*.spawns")) == []
    assert store.resume_dispatch(dsn, _cmd({"reason": "test"}, "rel")).code == ResultCode.APPLIED
    stale = store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02a-att:n", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "a2"))
    assert stale.code == ResultCode.STALE_REVISION
    readmit = broker.redispatch_after_reset(
        dsn, "r02a-att:n", launchers={"local-process": launcher},
        expected_generation=env["generation"] + 1)
    assert readmit.dispatch_state == "observed" and readmit.sent_this_call
    assert len(list((tmp_path / "runs").glob("*.spawns"))) == 1


def test_withdrawn_investigation_refuses_dispatch_both_paths(migrated_db):
    dsn = migrated_db
    env = _seed(dsn, "r02b")
    _sandbox(dsn, "r02b-att:n1", env)
    _sandbox(dsn, "r02b-att:n2", env)
    assert store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02b-att:n2", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "w0")).code == ResultCode.APPLIED
    assert store.withdraw_commitment(
        dsn, _cmd({"investigation_id": "r02b-i"}, "wd")).code == ResultCode.APPLIED
    fresh = store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02b-att:n1", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "w1"))
    assert fresh.code == ResultCode.INVALID_INPUT and "withdrawn" in fresh.detail
    reentry = store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02b-att:n2", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "w2"))
    assert reentry.code == ResultCode.INVALID_INPUT and "withdrawn" in reentry.detail


def test_amended_investigation_fences_old_revision_ops(migrated_db):
    dsn = migrated_db
    env = _seed(dsn, "r02c")
    _sandbox(dsn, "r02c-att:n", env)
    assert store.amend_commitment(
        dsn, _cmd({"investigation_id": "r02c-i", "obligations": {}}, "am"),
        ).code == ResultCode.APPLIED
    result = store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02c-att:n", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "am2"))
    assert result.code == ResultCode.STALE_REVISION


def test_fulfillment_rejects_unwitnessed_obligations(migrated_db):
    dsn = migrated_db
    env = _seed(dsn, "r02d", {"claim-required": "a claim with no admitted derivation"})
    assert store.complete_attempt(
        dsn, _cmd({"attempt_id": env["attempt"],
                   "ownership_generation": env["generation"]}, "done")).code == ResultCode.APPLIED
    result = store.fulfill_investigation(
        dsn, _cmd(_fulfill_payload(dsn, "r02d-i", env["attempt"], env["generation"],
                                  {"claim-required": "a claim with no admitted derivation"}),
                  "ful"))
    assert result.code == ResultCode.MISSING_EVIDENCE
    assert "witness" in result.detail


def test_fulfillment_accepts_witnessed_success(migrated_db, tmp_path):
    dsn = migrated_db
    obligations = {"w": {"success": "r02e-att:n"}}
    env = _seed(dsn, "r02e", obligations)
    _sandbox(dsn, "r02e-att:n", env)
    launcher = LocalLauncher(tmp_path / "runs")
    done = broker.dispatch_operation(
        dsn, "r02e-att:n", launchers={"local-process": launcher},
        ownership_generation=env["generation"])
    assert done.dispatch_state == "observed" and done.sent_this_call
    assert store.complete_attempt(
        dsn, _cmd({"attempt_id": env["attempt"],
                   "ownership_generation": env["generation"]}, "done")).code == ResultCode.APPLIED
    result = store.fulfill_investigation(
        dsn, _cmd(_fulfill_payload(dsn, "r02e-i", env["attempt"], env["generation"],
                                  obligations), "ful"))
    assert result.code == ResultCode.APPLIED, result.detail


def test_fulfillment_rejects_future_epoch(migrated_db):
    dsn = migrated_db
    env = _seed(dsn, "r02f")
    assert store.complete_attempt(
        dsn, _cmd({"attempt_id": env["attempt"],
                   "ownership_generation": env["generation"]}, "done")).code == ResultCode.APPLIED
    payload = _fulfill_payload(dsn, "r02f-i", env["attempt"], env["generation"], {})
    payload["evidence_epoch"] = int(payload["evidence_epoch"]) + 1
    result = store.fulfill_investigation(dsn, _cmd(payload, "ful"))
    assert result.code == ResultCode.MISSING_EVIDENCE


def test_fulfillment_rejects_quarantined_attempt(migrated_db):
    dsn = migrated_db
    env = _seed(dsn, "r02g")
    with store.db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id) VALUES (%s)"
                        " ON CONFLICT (id) DO NOTHING", ("r02g-cap",))
            conn.commit()
    capabilities.pin_capability(dsn, env["attempt"], "r02g-cap")
    assert capabilities.quarantine(
        dsn, _cmd({"version_id": "r02g-cap"}, "q"), "r02g-cap", "r02 probe").code \
        == ResultCode.APPLIED
    assert store.complete_attempt(
        dsn, _cmd({"attempt_id": env["attempt"],
                   "ownership_generation": env["generation"]}, "done")).code == ResultCode.APPLIED
    result = store.fulfill_investigation(
        dsn, _cmd(_fulfill_payload(dsn, "r02g-i", env["attempt"], env["generation"], {}),
                  "ful"))
    assert result.code == ResultCode.UNAUTHORIZED


def test_barrier_pauses_and_resume_reopens(migrated_db):
    dsn = migrated_db
    env = _seed(dsn, "r02h")
    _sandbox(dsn, "r02h-att:n", env)
    barrier = store.checkpoint_barrier(dsn, _cmd({}, "bar"))
    assert barrier.code == ResultCode.APPLIED
    assert barrier.data["dispatch_paused"] is True
    held = store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02h-att:n", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "held"))
    assert held.code == ResultCode.INVALID_INPUT and "paused" in held.detail
    assert store.resume_dispatch(dsn, _cmd({"reason": "test"}, "rel")).code == ResultCode.APPLIED
    assert store.advance_dispatch(
        dsn, _cmd({"operation_id": "r02h-att:n", "launcher_id": "local-process",
                   "ownership_generation": env["generation"]}, "go")).code == ResultCode.APPLIED


def _conn_params(dsn: str) -> dict:
    import urllib.parse

    if "://" in dsn:
        parts = urllib.parse.urlsplit(dsn)
        params = dict(urllib.parse.parse_qsl(parts.query))
        if parts.hostname:
            params.setdefault("host", parts.hostname)
        if parts.port:
            params.setdefault("port", str(parts.port))
        if parts.username:
            params.setdefault("user", parts.username)
        if parts.password:
            params.setdefault("password", parts.password)
        params["dbname"] = parts.path.lstrip("/") or params.get("dbname", "")
        return params
    params = {}
    for token in dsn.split():
        if "=" in token:
            key, value = token.split("=", 1)
            params[key] = value
    return params


def _sibling_dsn(name: str) -> str:
    import os
    import urllib.parse

    dsn = os.environ["SETTLEMENT_TEST_DSN"]
    if "://" in dsn:
        parts = urllib.parse.urlsplit(dsn)
        if parts.netloc:
            return urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, f"/{name}", parts.query, ""))
        base = f"{parts.scheme}:///{name}"
        return f"{base}?{parts.query}" if parts.query else base
    params = _conn_params(dsn)
    params["dbname"] = name
    return " ".join(f"{key}={value}" for key, value in params.items() if value != "")


def _make_database(target: str) -> None:
    from settlement import db as _db
    from psycopg import errors as _pgerrors

    params = _conn_params(target)
    name = params.pop("dbname", "")
    admin = " ".join(f"{key}={value}" for key, value in
                     {**params, "dbname": "postgres"}.items() if value != "")
    with _db.connect(admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f'CREATE DATABASE "{name}"')
            except _pgerrors.DuplicateDatabase:
                pass


def _base_name() -> str:
    import os

    return _conn_params(os.environ["SETTLEMENT_TEST_DSN"]).get("dbname", "")


@pytest.fixture(scope="module")
def companion_dsn():
    from pathlib import Path as _Path

    from settlement import db as _db

    target = _sibling_dsn(f"{_base_name()}_wfshape")
    _make_database(target)
    _db.apply_migrations(target, _Path(__file__).parent.parent / "migrations")
    return target


@pytest.fixture(scope="module")
def dbos_sys_dsn():
    import os

    if "://" not in os.environ["SETTLEMENT_TEST_DSN"]:
        pytest.skip("DBOS system-store tests need URL-form SETTLEMENT_TEST_DSN"
                    " (DBOS database_url is SQLAlchemy-parsed)")
    target = _sibling_dsn(f"{_base_name()}_dbos")
    _make_database(target)
    broker.init_dbos(target)
    yield target
    broker.shutdown_dbos()


def test_checkpoint_refuses_post_write_mutation(migrated_db, tmp_path, monkeypatch):
    dsn = migrated_db
    _seed(dsn, "r02i")
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    real_verify = store.checkpoint_verify
    calls = []

    def counting(dsn_arg, barrier):
        calls.append(1)
        if len(calls) >= 2:
            return ["journal moved during checkpoint: test-injected"]
        return real_verify(dsn_arg, barrier)

    monkeypatch.setattr(store, "checkpoint_verify", counting)
    with pytest.raises(SystemExit, match="state moved while writing"):
        run_checkpoint(dsn, art, tmp_path / "backup")
    assert len(calls) == 2


def test_restore_coordinated_needs_workflow_target(migrated_db, tmp_path, companion_dsn):
    dsn = migrated_db
    _seed(dsn, "r02j")
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    out = tmp_path / "backup"
    run_checkpoint(dsn, art, out, workflow_dsn=companion_dsn)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["workflow"]["kind"] == "settlement-shaped"
    with pytest.raises(SystemExit, match="workflow target"):
        run_restore(out, companion_dsn, tmp_path / "restored")


def test_checkpoint_detects_dbos_system_store(migrated_db, tmp_path, dbos_sys_dsn):
    dsn = migrated_db
    _seed(dsn, "r02k")
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "seed.txt").write_text("seed")
    out = tmp_path / "backup"
    result = run_checkpoint(dsn, art, out, workflow_dsn=dbos_sys_dsn)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["workflow"]["coordinated"] is True
    assert manifest["workflow"]["kind"] == "dbos-system"
    assert Path(result["workflow_dump"]).stat().st_size > 0


def test_clean_process_resume_consumes_delayed_success_once(
        migrated_db, tmp_path, dbos_sys_dsn):
    from dbos import DBOS, SetWorkflowID

    dsn = migrated_db
    env = _seed(dsn, "r02m")
    comp = {"version": "run/v1", "revision": 1, "allocation_id": env["allocation"],
            "authority_version": 1,
            "root": {"kind": "invoke", "node_id": "n", "effect": "sandbox-exec",
                     "payload": {"profile": "local-process", "argv": ["/bin/true"],
                                 "timeout_ms": 30_000, "max_output_bytes": 1024}}}
    _sandbox(dsn, "r02m-att:n", env)
    cont = run.register_ops(run.Composition.model_validate(comp),
                            run.fresh_continuation(
                                run.Composition.model_validate(comp), env["attempt"]),
                            {"n": "r02m-att:n"})
    run.record_continuation(dsn, env["attempt"], cont, "r02m:setup", None)
    assert broker.admit_launcher_receipt(
        dsn, "r02m-att:n", broker.ReceiptProposal(
            receipt_identity="delayed:r02m-att:n", content={"ok": True},
            outcome="success", provenance="local")).code == ResultCode.APPLIED
    broker.ATTEMPT_WORKFLOW_RESOURCES.pop(env["attempt"], None)
    launcher = LocalLauncher(tmp_path / "runs")
    report = broker.heartbeat(dsn, {"local-process": launcher,
                                    launcher.launcher_id: launcher})
    assert env["attempt"] in broker.ATTEMPT_WORKFLOW_RESOURCES
    assert report.next_decision in ("idle", "work-done", "repair-done")
    with SetWorkflowID(f"wf-r02m-{uuid.uuid4().hex[:8]}"):
        handle = DBOS.start_workflow(broker.attempt_workflow, dsn, env["attempt"],
                                     env["generation"], comp, 10)
        result = handle.get_result()
    assert result["outcome"] == "completed", result
    receipts = store.operation_receipts(dsn, "r02m-att:n")
    assert [r["receipt_identity"] for r in receipts] == ["delayed:r02m-att:n"]
    stored = broker.wf_snapshot(dsn, env["attempt"])["continuation"]
    assert stored["completed"] == {"n": "op:r02m-att:n"}


def test_failed_invocation_terminates_at_retry_budget(migrated_db, tmp_path, monkeypatch):
    dsn = migrated_db
    env = _seed(dsn, "r02n")
    comp = {"version": "run/v1", "revision": 1, "allocation_id": env["allocation"],
            "authority_version": 1,
            "root": {"kind": "invoke", "node_id": "n", "effect": "sandbox-exec",
                     "retry_max": 0,
                     "payload": {"profile": "local-process", "argv": ["/bin/false"],
                                 "timeout_ms": 30_000, "max_output_bytes": 1024}}}
    launcher = LocalLauncher(tmp_path / "runs")
    broker.ATTEMPT_WORKFLOW_RESOURCES[env["attempt"]] = {
        "launchers": {"local-process": launcher}, "gateway": FakeGatewayAdapter()}
    monkeypatch.setattr(broker, "DBOS", SimpleNamespace(
        run_step=lambda _ctx, fn, *args: fn(*args),
        workflow=lambda: (lambda fn: fn)))
    body = inspect.unwrap(broker.attempt_workflow)
    result = body(dsn, env["attempt"], env["generation"], comp, 10)
    assert result["outcome"] == "completed", result
    snap = broker.wf_snapshot(dsn, env["attempt"])["continuation"]
    assert snap["observations"].get("n:outcome") == "failure"
    assert snap["completed"]["n"] == "op:r02n-att:n:failed"
    assert len(list((tmp_path / "runs").glob("*.spawns"))) == 1


def test_unbilled_usage_settles_full_reservation(migrated_db):
    dsn = migrated_db
    env = _seed(dsn, "r02o")
    op = "r02o-model"
    prepared = broker.ensure_operation(
        dsn, operation_id=op, effect=broker.MODEL_INFERENCE,
        payload={"model": "fake", "messages": [{"role": "user", "content": "hi"}],
                 "max_output_tokens": 50, "deadline_ms": 10000},
        allocation_id=env["allocation"], attempt_id=env["attempt"])
    assert prepared.code == ResultCode.APPLIED
    exposure = int(prepared.data["exposure"])
    status = broker.dispatch_operation(dsn, op, gateway=FakeGatewayAdapter(),
                                       ownership_generation=env["generation"])
    assert status.dispatch_state == "observed" and status.sent_this_call
    receipt = store.operation_receipts(dsn, op)
    assert receipt and store.allocation_status(
        dsn, env["allocation"])["consumed"] == exposure


def test_transact_bounded_under_contention(migrated_db):
    import psycopg

    dsn = migrated_db
    _seed(dsn, "r02p")
    holder = psycopg.connect(dsn, autocommit=True)
    holder.execute("BEGIN")
    holder.execute("SELECT * FROM control WHERE id = 1 FOR UPDATE")
    started = time.monotonic()
    try:
        result = store.seed_allocation(
            dsn, Command(request_id=f"r02_bound_{uuid.uuid4().hex[:8]}",
                         deadline_ms=200,
                         payload={"allocation_id": "r02p-b", "domain": "cpu",
                                  "authorized": 10}))
    finally:
        holder.close()
    elapsed = time.monotonic() - started
    assert result.code == ResultCode.UNAVAILABLE_DEPENDENCY
    assert elapsed < 5.0


def test_uncertain_resolution_never_returns_to_prepared(migrated_db, tmp_path):
    dsn = migrated_db
    env = _seed(dsn, "r02q")
    _sandbox(dsn, "r02q-att:n", env)
    launcher = LocalLauncher(tmp_path / "runs")
    crashed = broker.dispatch_operation(
        dsn, "r02q-att:n", launchers={"local-process": launcher},
        ownership_generation=env["generation"], _crash_after_send=True)
    assert crashed.dispatch_state == "dispatching"
    repaired = store.reconcile_operation(
        dsn, _cmd({"operation_id": "r02q-att:n", "resolution": "unresolved"}, "rec"))
    assert repaired.code == ResultCode.APPLIED
    again = broker.dispatch_operation(
        dsn, "r02q-att:n", launchers={"local-process": launcher},
        ownership_generation=env["generation"])
    assert again.sent_this_call is False
    assert broker.read_operation(dsn, "r02q-att:n")["dispatch_state"] == "unresolved"
