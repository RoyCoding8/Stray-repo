from __future__ import annotations

import hashlib
import io
import json
import tarfile
import uuid

import pytest

from settlement import artifacts, capabilities, db, evaluation, store, trials
from settlement.common import Command, ResultCode, SettlementError


def _cmd(payload=None, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload or {}, **kw)


GROUPS = [{"name": "development", "kind": "development"},
          {"name": "panel", "kind": "visible-regression"},
          {"name": "prot", "kind": "protected-eval"}]


def _freeze(dsn, pid, **kw):
    return trials.freeze_protocol(dsn, _cmd(), protocol_id=pid, candidate_version="cv",
                                  reference_version="rv", evaluator_version="ev1",
                                  task_groups=GROUPS, **kw)


def test_assign_retry_returns_prior_blind_key(migrated_db):
    dsn = migrated_db
    _freeze(dsn, "invc-retry")
    first = trials.assign(dsn, _cmd(), "invc-retry", "t1", "panel", "candidate", {})
    assert first.code == ResultCode.APPLIED
    second = trials.assign(dsn, _cmd(), "invc-retry", "t1", "panel", "candidate", {})
    assert second.code == ResultCode.ALREADY_APPLIED
    assert second.data["blind_key"] == first.data["blind_key"]
    assert second.data["assignment_id"] == first.data["assignment_id"]


def test_assign_refuses_unfrozen_protocol(migrated_db):
    dsn = migrated_db
    _freeze(dsn, "invc-draft", _frozen=False)
    with pytest.raises(SettlementError, match="not frozen"):
        trials.assign(dsn, _cmd(), "invc-draft", "t1", "panel", "candidate", {})


def test_register_evaluator_refuses_version_change(migrated_db):
    dsn = migrated_db
    first = evaluation.register_evaluator(dsn, _cmd(), "invc-eval", "v1")
    assert first.code == ResultCode.APPLIED
    again = evaluation.register_evaluator(dsn, _cmd(), "invc-eval", "v1")
    assert again.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    refused = evaluation.register_evaluator(dsn, _cmd(), "invc-eval", "v2")
    assert refused.code == ResultCode.INVALID_INPUT
    assert "already" in refused.detail


def _pkg(body: bytes = b"hello", name: str = "a.txt"):
    digest = hashlib.sha256(body).hexdigest()
    manifest = {"files": [{"path": name, "digest": digest, "size": len(body),
                           "kind": "file"}]}
    return manifest, {name: body}


def _stage_publish(dsn, tmp_roots, manifest=None, files=None, **kw):
    manifest, files = (manifest, files) if manifest else _pkg()
    receipt = artifacts.stage_package(dsn, tmp_roots["staging"], manifest=manifest,
                                      files=files, **kw)
    result = artifacts.publish_package(dsn, _cmd(), tmp_roots["artifacts"], receipt)
    assert result.code == ResultCode.APPLIED
    return receipt


def test_purged_bytes_free_quota(migrated_db, tmp_roots):
    dsn = migrated_db
    manifest, files = _pkg(b"x" * 8)
    receipt = _stage_publish(dsn, tmp_roots, manifest, files, scope="invc-q")
    artifacts.set_retention_budget(dsn, _cmd(), "invc-q", 8)
    assert artifacts.scope_usage(dsn, "invc-q")["used"] == 8
    artifacts.retire_artifact(dsn, _cmd(), receipt["digest"])
    out = artifacts.collect_garbage(dsn, tmp_roots["artifacts"])
    assert receipt["digest"] in out["removed"]
    assert artifacts.scope_usage(dsn, "invc-q")["used"] == 0


def test_publish_refuses_tampered_receipt_size(migrated_db, tmp_roots):
    dsn = migrated_db
    manifest, files = _pkg(b"01234567")
    receipt = artifacts.stage_package(None, tmp_roots["staging"], manifest=manifest,
                                      files=files, scope="invc-t")
    receipt["size"] = 0
    with pytest.raises(SettlementError, match="size"):
        artifacts.publish_package(dsn, _cmd(), tmp_roots["artifacts"], receipt)


def test_reconcile_registers_manifest_and_logical_size(migrated_db, tmp_roots):
    dsn = migrated_db
    manifest, files = _pkg(b"orphan-bytes")
    receipt = artifacts.stage_package(None, tmp_roots["staging"], manifest=manifest,
                                      files=files)
    payload = json.dumps({"manifest": manifest, "scope": "",
                          "files": {k: v.hex() for k, v in files.items()}},
                         sort_keys=True, separators=(",", ":")).encode()
    (tmp_roots["artifacts"] / receipt["digest"]).write_bytes(payload)
    out = artifacts.reconcile_staging(dsn, tmp_roots["staging"], tmp_roots["artifacts"])
    assert receipt["digest"] in out["registered"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT manifest, size FROM artifact_versions WHERE digest = %s",
                        (receipt["digest"],))
            stored_manifest, stored_size = cur.fetchone()
            conn.commit()
    assert stored_manifest == manifest
    assert stored_size == len(b"orphan-bytes")


def test_stage_refuses_archive_symlink(migrated_db, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    arc_path = tmp_path / "evil.tar.gz"
    with tarfile.open(arc_path, "w:gz") as tf:
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tf.addfile(link)
        info = tarfile.TarInfo("ok.txt")
        info.size = 2
        tf.addfile(info, io.BytesIO(b"hi"))
    arc_bytes = arc_path.read_bytes()
    manifest = {"files": [{"path": "evil.tar.gz", "kind": "archive",
                           "digest": hashlib.sha256(arc_bytes).hexdigest(),
                           "size": len(arc_bytes), "unpack": True}]}
    with pytest.raises(SettlementError, match="links and special files"):
        artifacts.stage_package(None, staging, manifest=manifest,
                                files={"evil.tar.gz": arc_bytes})


def test_extract_entry_malformed_package_is_settlement_error(tmp_path):
    inner = {"manifest": {"files": [{"path": "data.txt", "kind": "file"}]},
             "files": {"data.txt": b"hi".hex()}}
    payload = json.dumps(inner, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / digest).write_bytes(payload)
    with pytest.raises(SettlementError):
        capabilities._extract_entry(str(tmp_path), digest)
