from __future__ import annotations

import hashlib
import threading
import uuid

import pytest

from settlement import artifacts, store
from settlement.common import Command, ResultCode, SettlementError


def _cmd(payload=None, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload or {}, **kw)


def _pkg(body: bytes = b"hello", name: str = "a.txt"):
    digest = hashlib.sha256(body).hexdigest()
    manifest = {"files": [{"path": name, "digest": digest, "size": len(body), "kind": "file"}]}
    return manifest, {name: body}


def _stage_publish(dsn, tmp_roots, manifest=None, files=None, **kw):
    manifest, files = (manifest, files) if manifest else _pkg()
    receipt = artifacts.stage_package(dsn, tmp_roots["staging"], manifest=manifest,
                                      files=files, **kw)
    result = artifacts.publish_package(dsn, _cmd(), tmp_roots["artifacts"], receipt)
    assert result.code == ResultCode.APPLIED
    return receipt


def test_traversal_and_link_attacks_rejected(migrated_db, tmp_roots):
    evil = ["../escape.txt", "/abs.txt", "a/../../b.txt", "sub/./x.txt"]
    for path in evil:
        manifest = {"files": [{"path": path, "digest": "0" * 64, "size": 1, "kind": "file"}]}
        with pytest.raises(SettlementError):
            artifacts.stage_package(None, tmp_roots["staging"], manifest=manifest,
                                    files={path: b"x"})
    for kind in ("symlink", "hardlink", "link", "fifo", "device"):
        manifest = {"files": [{"path": "x", "digest": "0" * 64, "size": 1, "kind": kind}]}
        with pytest.raises(SettlementError):
            artifacts.stage_package(None, tmp_roots["staging"], manifest=manifest,
                                    files={"x": b"x"})
    manifest, files = _pkg(b"real")
    manifest["files"][0]["digest"] = "0" * 64
    with pytest.raises(SettlementError):
        artifacts.stage_package(None, tmp_roots["staging"], manifest=manifest, files=files)


def test_budget_refuses_over_quota_staging(migrated_db, tmp_roots):
    dsn = migrated_db
    artifacts.set_retention_budget(dsn, _cmd(), "ws1", 10, "working_set")
    manifest, files = _pkg(b"x" * 11)
    with pytest.raises(SettlementError):
        artifacts.stage_package(dsn, tmp_roots["staging"], manifest=manifest, files=files,
                                scope="ws1")
    manifest, files = _pkg(b"x" * 10)
    receipt = artifacts.stage_package(dsn, tmp_roots["staging"], manifest=manifest,
                                      files=files, scope="ws1")
    assert receipt["digest"]


def test_publish_makes_available_and_digest_alone_does_not(migrated_db, tmp_roots):
    dsn = migrated_db
    receipt = _stage_publish(dsn, tmp_roots)
    assert artifacts.artifact_available(dsn, tmp_roots["artifacts"], receipt["digest"])
    ghost = "0" * 64
    assert not artifacts.artifact_available(dsn, tmp_roots["artifacts"], ghost)
    (tmp_roots["artifacts"] / receipt["digest"]).unlink()
    assert not artifacts.artifact_available(dsn, tmp_roots["artifacts"], receipt["digest"])


def test_publication_crash_orphan_is_registered_or_reclaimed(migrated_db, tmp_roots):
    dsn = migrated_db
    manifest, files = _pkg(b"orphan-bytes")
    receipt = artifacts.stage_package(None, tmp_roots["staging"], manifest=manifest, files=files)
    import json
    payload = json.dumps({"manifest": manifest, "scope": "",
                          "files": {k: v.hex() for k, v in files.items()}},
                         sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(payload).hexdigest() == receipt["digest"]
    (tmp_roots["artifacts"] / receipt["digest"]).write_bytes(payload)
    (tmp_roots["artifacts"] / "junk").write_bytes(b"junk")
    out = artifacts.reconcile_staging(dsn, tmp_roots["staging"], tmp_roots["artifacts"])
    assert receipt["digest"] in out["registered"]
    assert "junk" in out["reclaimed"]
    assert artifacts.artifact_available(dsn, tmp_roots["artifacts"], receipt["digest"])


def test_retirement_race_keeps_referenced_bytes(migrated_db, tmp_roots):
    dsn = migrated_db
    receipt = _stage_publish(dsn, tmp_roots)
    digest = receipt["digest"]
    errors: list = []

    def add_ref(n):
        try:
            artifacts.add_reference(dsn, _cmd(), digest, "evidence", f"holder-{n}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=add_ref, args=(n,)) for n in range(8)]
    retire = threading.Thread(
        target=lambda: artifacts.retire_artifact(dsn, _cmd(), digest))
    for thread in threads + [retire]:
        thread.start()
    for thread in threads + [retire]:
        thread.join()
    assert not errors
    out = artifacts.collect_garbage(dsn, tmp_roots["artifacts"])
    assert digest in out["kept"]
    assert artifacts.artifact_available(dsn, tmp_roots["artifacts"], digest) is False
    assert (tmp_roots["artifacts"] / digest).is_file()
    for n in range(8):
        artifacts.remove_reference(dsn, _cmd(), digest, "evidence", f"holder-{n}")
    out = artifacts.collect_garbage(dsn, tmp_roots["artifacts"])
    assert digest in out["removed"]
    assert not (tmp_roots["artifacts"] / digest).exists()


def test_missing_and_corrupted_protected_bytes_detected(migrated_db, tmp_roots):
    dsn = migrated_db
    receipt = _stage_publish(dsn, tmp_roots)
    digest = receipt["digest"]
    artifacts.add_reference(dsn, _cmd(), digest, "evidence", "claim-c1")
    (tmp_roots["artifacts"] / digest).write_bytes(b"corrupted!!")
    assert artifacts.artifact_available(dsn, tmp_roots["artifacts"], digest) is False
    check = artifacts.verify_bytes(dsn, tmp_roots["artifacts"], digest)
    assert check == {"digest": digest, "ok": False, "reason": "digest mismatch"}
    assert store.get_control(dsn)["evidence_epoch"] >= 1
    gone = _stage_publish(dsn, tmp_roots, *_pkg(b"gone"))
    artifacts.add_reference(dsn, _cmd(), gone["digest"], "release", "rel-1")
    (tmp_roots["artifacts"] / gone["digest"]).unlink()
    check = artifacts.verify_bytes(dsn, tmp_roots["artifacts"], gone["digest"])
    assert check["ok"] is False and check["reason"] == "missing bytes"


def test_hidden_labels_scoped_in_sql(migrated_db, tmp_roots):
    dsn = migrated_db
    pub = _stage_publish(dsn, tmp_roots, *_pkg(b"pub", "p.txt"))
    hid_manifest, hid_files = _pkg(b"secret", "s.txt")
    hid = artifacts.stage_package(None, tmp_roots["staging"], manifest=hid_manifest,
                                  files=hid_files, access_label="hidden")
    assert artifacts.publish_package(dsn, _cmd(), tmp_roots["artifacts"], hid).code == ResultCode.APPLIED
    candidate = {row["digest"] for row in artifacts.scoped_artifacts(dsn, "candidate")}
    evaluator = {row["digest"] for row in artifacts.scoped_artifacts(dsn, "evaluator")}
    assert pub["digest"] in candidate and hid["digest"] not in candidate
    assert hid["digest"] in evaluator


def test_retention_proposal_cannot_bypass_preservation(migrated_db, tmp_roots):
    dsn = migrated_db
    artifacts.set_retention_budget(dsn, _cmd(), "ws2", 10_000, "working_set")
    receipt = _stage_publish(dsn, tmp_roots, *_pkg(b"protected-data", "ev.bin"), scope="ws2")
    artifacts.add_reference(dsn, _cmd(), receipt["digest"], "evidence", "claim-x")
    refused = artifacts.propose_retention_change(dsn, _cmd(), "ws2", 1)
    assert refused.code == ResultCode.INVALID_INPUT
    assert artifacts.scope_usage(dsn, "ws2")["used"] >= len(b"protected-data")
    ok = artifacts.propose_retention_change(dsn, _cmd(), "ws2", 10_000)
    assert ok.code == ResultCode.APPLIED


def test_untrusted_archive_unpacks_only_via_isolated_process(migrated_db, tmp_roots):
    import io
    import tarfile
    dsn = migrated_db
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("inner.txt")
        data = b"inside"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    raw = buf.getvalue()
    manifest = {"files": [{"path": "pack.tar.gz", "digest": hashlib.sha256(raw).hexdigest(),
                           "size": len(raw), "kind": "archive", "unpack": True}]}
    receipt = artifacts.stage_package(None, tmp_roots["staging"], manifest=manifest,
                                      files={"pack.tar.gz": raw})
    assert (tmp_roots["staging"] / receipt["digest"] / "pack.tar.gz.unpacked" / "inner.txt").is_file()
    assert artifacts.publish_package(dsn, _cmd(), tmp_roots["artifacts"], receipt).code == ResultCode.APPLIED
