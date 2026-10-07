from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest


from settlement.checkpoint import run_checkpoint
from settlement.restore import run_restore

from settlement import broker, db, store
from settlement.launcher_local import LocalLauncher
from test_rec_checkpoint import seed_state

@pytest.fixture()
def fence():
    from isolation_db import (
        create_disposable_db, drop_disposable_db)
    database = create_disposable_db(
        "ci-restore-fence", migrations_dir=Path(__file__).parents[2] / "migrations")
    try:
        with db.connect(database.dsn) as conn:
            conn.execute("TRUNCATE control, store_identity CASCADE")
        yield database.dsn
    finally:
        drop_disposable_db(database)


def _take_checkpoint(dsn, art: Path, tag: str, out: Path) -> Path:
    run_checkpoint(dsn, art, out)
    return out


def test_restore_roundtrip_verifies_manifest(migrated_db, fence, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    art.mkdir()
    staging.mkdir()
    seed_state(dsn, "rs1", art, staging)
    backup = tmp_path / "backup"
    _take_checkpoint(dsn, art, "rs1", backup)
    restored_art = tmp_path / "restored-art"
    report = run_restore(backup, fence, restored_art)
    assert report["ok"] is True and report["mismatches"] == []
    manifest = json.loads((backup / "manifest.json").read_text())
    assert report["fence"], "R01-006: restore must establish the execution fence"
    with db.connect(fence) as conn:
        with conn.cursor() as cur:
            counts = {}
            for table in manifest["row_counts"]:
                cur.execute(f' SELECT COUNT(*) FROM "{table}"')
                counts[table] = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM command_journal WHERE request_id LIKE 'restore-fence-%'")
                fence_records = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM domain_events WHERE kind = 'recovery.fenced'")
                fence_events = cur.fetchone()[0]
            conn.commit()
    assert fence_records == 1 and fence_events == 1
    expected = dict(manifest["row_counts"])
    expected["command_journal"] += 1
    expected["domain_events"] += 1
    assert counts == expected
    for entry in manifest["artifacts"]:
        assert (restored_art / entry["path"]).read_bytes() == (art / entry["path"]).read_bytes()


def test_restore_refuses_source_and_non_fresh_target(migrated_db, fence, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    art.mkdir()
    staging.mkdir()
    seed_state(dsn, "rs2", art, staging)
    backup = tmp_path / "backup"
    _take_checkpoint(dsn, art, "rs2", backup)
    with pytest.raises(SystemExit, match="matches checkpoint source"):
        run_restore(backup, dsn, tmp_path / "nope")
    report = run_restore(backup, fence, tmp_path / "restored-art")
    assert report["ok"] is True
    with pytest.raises(SystemExit, match="not fresh"):
        run_restore(backup, fence, tmp_path / "restored-art-2")


def test_restore_tamper_reports_failure_never_partial(migrated_db, fence, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    art.mkdir()
    staging.mkdir()
    seed_state(dsn, "rs3", art, staging)
    backup = tmp_path / "backup"
    _take_checkpoint(dsn, art, "rs3", backup)
    tampered = tmp_path / "tampered"
    shutil.copytree(backup, tampered)
    manifest_path = tampered / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    report = run_restore(tampered, fence, tmp_path / "restored-art")
    assert report["ok"] is False
    assert any("digest mismatch" in m for m in report["mismatches"])


def test_restored_db_predating_effect_reconciles(migrated_db, fence, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    runs = tmp_path / "runs"
    art.mkdir()
    staging.mkdir()
    runs.mkdir()
    env = seed_state(dsn, "rs4", art, staging)
    backup = tmp_path / "backup"
    _take_checkpoint(dsn, art, "rs4", backup)
    manifest = json.loads((backup / "manifest.json").read_text())
    launcher = LocalLauncher(runs)
    broker.ensure_operation(dsn, operation_id="rs4-op", effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process", "argv": ["/bin/true"],
                                     "timeout_ms": 30_000, "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"], attempt_id="rs4-att")
    status = broker.dispatch_operation(dsn, "rs4-op",
                                       launchers={"local-process": launcher})
    assert status.dispatch_state == "observed"
    report = run_restore(backup, fence, tmp_path / "restored-art")
    assert report["ok"] is True
    assert broker.read_operation(fence, "rs4-op") is None
    with db.connect(fence) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts")
            fence_receipts = cur.fetchone()[0]
            conn.commit()
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts")
            primary_receipts = cur.fetchone()[0]
            conn.commit()
    assert fence_receipts == manifest["row_counts"]["receipts"] == 0
    assert primary_receipts == 1
    primary = broker.read_operation(dsn, "rs4-op")
    assert primary["dispatch_state"] == "observed" and primary["settled"] is True
    decision = broker.reconcile(dsn, "rs4-op", {"local-process": launcher})
    assert decision.decision == "already-terminal"
