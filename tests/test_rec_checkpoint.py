from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from checkpoint import dbname_of, run_checkpoint

from settlement import artifacts, db, evidence, store
from settlement.common import Command

REPO = Path(__file__).parent.parent


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"rec_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def seed_state(dsn, tag, artifacts_root: Path, staging_root: Path) -> dict:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "rec",
                                "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 5000}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "rec"}, f"{tag}i"))
    store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                  "investigation_id": f"{tag}-i"}, f"{tag}q"))
    store.reserve(dsn, _cmd({"allocation_id": f"{tag}-a",
                             "reservation_id": f"{tag}-r", "amount": 100}, f"{tag}res"))
    raw = f"checkpoint bytes {tag}".encode()
    manifest = {"files": [{"path": "doc.txt", "kind": "file",
                           "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)}],
                "entry": "doc.txt"}
    receipt = artifacts.stage_package(dsn, staging_root, manifest=manifest,
                                      files={"doc.txt": raw}, access_label="public")
    published = artifacts.publish_package(dsn, _cmd({}, f"{tag}p"), artifacts_root, receipt)
    evidence.register_observation(dsn, _cmd({}, f"{tag}o"), f"{tag}-att",
                                  {"checkpoint": tag}, "rec-src")
    return {"allocation_id": f"{tag}-a", "digest": published.data["digest"]}


def _head() -> str:
    out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_checkpoint_writes_consistent_recovery_set(migrated_db, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    art.mkdir()
    staging.mkdir()
    seed_state(dsn, "ck1", art, staging)
    out = tmp_path / "backup"
    result = run_checkpoint(dsn, art, out)
    assert Path(result["dump"]).stat().st_size > 0
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["source"]["database"] == dbname_of(dsn)
    assert manifest["source"]["commit"] == _head()
    assert manifest["migrations"] == ["0001_schema.sql", "0002_s2_evidence.sql",
                                      "0003_s3_learning.sql", "0004_leases.sql",
                                      "0005_eval_binding.sql",
                                      "0006_recovery_fence.sql",
                                      "0007_dev_episodes.sql",
                                      "0008_context_packets.sql",
                                      "0009_packet_input_binding.sql",
                                      "0010_agenda01.sql",
                                      "0011_agenda01_correction.sql",
                                      "0012_agenda01_resume.sql",
                                      "0013_agenda01_epoch.sql",
                                      "0014_team_runtime.sql"]
    assert set(manifest["control"]) == {"admission_epoch", "authority_version",
                                        "evidence_epoch", "release_epoch", "event_epoch"}
    assert manifest["control"]["authority_version"] == 1
    assert manifest["row_counts"]["grants"] >= 1
    assert manifest["row_counts"]["allocations"] >= 1
    assert manifest["row_counts"]["observations"] >= 1
    assert manifest["row_counts"]["artifact_versions"] >= 1
    assert len(manifest["artifacts"]) == 1
    entry = manifest["artifacts"][0]
    on_disk = next(p for p in art.rglob("*") if p.is_file())
    assert entry["size"] == on_disk.stat().st_size > 0
    assert entry["sha256"] == hashlib.sha256(on_disk.read_bytes()).hexdigest()
    with tarfile.open(result["tar"], "r") as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
    assert names == [entry["path"]]
    for name, digest in result["digests"].items():
        assert digest == hashlib.sha256((out / name).read_bytes()).hexdigest()


def test_checkpoint_refuses_and_releases_on_concurrent_write(
        migrated_db, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    art.mkdir()
    staging.mkdir()
    seed_state(dsn, "ckm", art, staging)
    out = tmp_path / "backup"

    def _move(barrier):
        store.seed_allocation(
            dsn, _cmd({"allocation_id": "late", "domain": "cpu",
                       "authorized": 5}, "late"))

    with pytest.raises(SystemExit, match="barrier violated"):
        run_checkpoint(dsn, art, out, _between=_move)
    assert store.get_control(dsn)["dispatch_paused"] is False


def test_checkpoint_cli_prints_digests(migrated_db, tmp_path):
    dsn = migrated_db
    art = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    art.mkdir()
    staging.mkdir()
    (art / "seed.txt").write_text("seed")
    seed_state(dsn, "ck2", art, staging)
    out = tmp_path / "backup"
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "checkpoint.py"), "--dsn", dsn,
         "--artifacts-root", str(art), "--out-dir", str(out)],
        capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr
    printed = json.loads(proc.stdout)
    assert set(printed["digests"]) == {f"{dbname_of(dsn)}.dump", "manifest.json",
                                       "artifacts.tar"}


def test_checkpoint_refuses_password_dsn(tmp_path):
    with pytest.raises(SystemExit, match="peer auth"):
        run_checkpoint("postgresql://u:secret@/db?host=/var/run/postgresql",
                       tmp_path, tmp_path / "out")
    assert dbname_of("postgresql://ubuntu@/settlement_t0validate?host=/var/run/postgresql") \
        == "settlement_t0validate"
    assert dbname_of("dbname=settlement_x host=/var/run/postgresql") == "settlement_x"
