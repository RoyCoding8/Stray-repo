from __future__ import annotations

import hashlib
import os
import sys
import uuid

import pytest

from settlement import artifacts, broker, run, store
from settlement.common import Command, ResultCode, SettlementError, Unauthorized, payload_digest
from settlement.launcher_local import LocalLauncher
from settlement.launcher_runsc import RunscLauncher
from settlement.run import Composition, SuspendNode


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"advi_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn, tag, authorized=100_000):
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "advi",
                                "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "advi"}, f"{tag}i"))
    return f"{tag}-a", f"{tag}-i"


def _op(dsn, tag, alloc, payload, attempt=None):
    return broker.ensure_operation(dsn, operation_id=f"{tag}-op", effect=broker.SANDBOX_EXEC,
                                   payload=payload, allocation_id=alloc, attempt_id=attempt)


def test_unknown_effect_rejected(migrated_db):
    dsn = migrated_db
    alloc, _ = _env(dsn, "u1")
    res = broker.ensure_operation(dsn, operation_id="u1-op", effect="teleport",
                                  payload={"destination": "mars"}, allocation_id=alloc)
    assert res.code == ResultCode.INVALID_INPUT
    assert broker.read_operation(dsn, "u1-op") is None


def test_unsupported_runtime_never_falls_back(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, inv = _env(dsn, "u2")
    store.acquire_work(dsn, _cmd({"attempt_id": "u2-att",
                                  "investigation_id": inv}, "u2q"))
    _op(dsn, "u2", alloc,
        {"profile": "gvisor", "argv": [sys.executable, "-c", "pass"], "timeout_ms": 5000,
         "max_output_bytes": 1024}, attempt="u2-att")
    launcher = RunscLauncher(image_digest="sha256:" + "0" * 64)
    status = broker.dispatch_operation(dsn, "u2-op", launchers={"gvisor": launcher})
    assert status.next_decision == "incompatible-profile"
    assert status.sent_this_call is False
    assert broker.read_operation(dsn, "u2-op")["dispatch_state"] == "dispatching"
    assert not list((tmp_path).glob("u2-op_*"))


def test_worker_credential_reachability(migrated_db, tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", "super-secret-key")
    monkeypatch.setenv("SETTLEMENT_DSN", "postgresql://ubuntu@/prod?host=x")
    monkeypatch.setenv("SETTLEMENT_GATEWAY_URL", "https://gateway.example")
    dsn = migrated_db
    alloc, _ = _env(dsn, "u3")
    probe = ("import os,json; print(json.dumps({'status': 'ok', 'data': {"
             "'keys': sorted(os.environ)}}))")
    _op(dsn, "u3", alloc,
        {"profile": "local-process", "argv": [sys.executable, "-c", probe],
         "timeout_ms": 30_000, "max_output_bytes": 65_536})
    launcher = LocalLauncher(tmp_path / "runs")
    status = broker.dispatch_operation(dsn, "u3-op",
                                       launchers={"local-process": launcher})
    assert status.dispatch_state == "observed"
    row = broker.read_operation(dsn, "u3-op")
    assert row is not None
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s", ("u3-op",))
            content = cur.fetchone()[0]
            conn.commit()
    keys = content["data"]["worker"]["data"]["keys"]
    assert keys == ["LANG", "PATH", "PYTHONPATH", "SETTLEMENT_OPERATION"]
    assert "super-secret-key" not in str(content)


def test_over_quota_output_capped(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, _ = _env(dsn, "u4")
    flood = ("import sys; sys.stdout.write('x' * 200000)")
    _op(dsn, "u4", alloc,
        {"profile": "local-process", "argv": [sys.executable, "-c", flood],
         "timeout_ms": 30_000, "max_output_bytes": 1024})
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, "u4-op", launchers={"local-process": launcher})
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s", ("u4-op",))
            content = cur.fetchone()[0]
            conn.commit()
    assert content["truncated"] is True
    assert len(content["data"]["stdout"]) <= 1024


def test_artifact_publish_retire_reference_race(migrated_db, tmp_path):
    dsn = migrated_db
    _env(dsn, "u8")
    roots = {"artifacts": tmp_path / "artifacts", "staging": tmp_path / "staging"}
    roots["artifacts"].mkdir()
    roots["staging"].mkdir()
    raw = b"load-bearing bytes"
    manifest = {"files": [{"path": "m.py", "kind": "file",
                           "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)}],
                "entry": "m.py"}
    receipt = artifacts.stage_package(dsn, roots["staging"], manifest=manifest,
                                      files={"m.py": raw}, access_label="public")
    published = artifacts.publish_package(dsn, _cmd({}, "u8p"), roots["artifacts"], receipt)
    digest = published.data["digest"]
    artifacts.add_reference(dsn, _cmd({}, "u8ref"), digest, "attempt", "u8-att")
    artifacts.retire_artifact(dsn, _cmd({}, "u8ret"), digest)
    collected = artifacts.collect_garbage(dsn, roots["artifacts"])
    assert digest in collected["kept"]
    assert artifacts.artifact_available(dsn, roots["artifacts"], digest) is False
    assert (roots["artifacts"] / digest).is_file()
    artifacts.remove_reference(dsn, _cmd({}, "u8unref"), digest, "attempt", "u8-att")
    collected = artifacts.collect_garbage(dsn, roots["artifacts"])
    assert digest in collected["removed"]
    assert artifacts.artifact_available(dsn, roots["artifacts"], digest) is False
