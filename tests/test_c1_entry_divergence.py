from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from settlement import artifacts
from settlement.common import SettlementError

ENTRY_A = b"ENTRY = 'A'\n"
ENTRY_B = b"ENTRY = 'B'\n"


def test_safe_write_rejects_an_existing_symlink(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    target = tmp_path / "outside.py"
    target.write_bytes(ENTRY_A)
    link = staging / "entry.py"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"host cannot create a file symlink: {exc}")

    with pytest.raises(SettlementError, match="rejected path"):
        artifacts._safe_write(staging, "entry.py", ENTRY_B)
    assert target.read_bytes() == ENTRY_A


def test_safe_write_creates_a_regular_file(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    written = artifacts._safe_write(staging, "regular.py", ENTRY_B)
    assert written.read_bytes() == ENTRY_B
    assert artifacts._safe_write(staging, "regular.py", ENTRY_B) == written
    with pytest.raises(SettlementError, match="existing staged bytes differ"):
        artifacts._safe_write(staging, "regular.py", ENTRY_A)
    assert written.read_bytes() == ENTRY_B


def test_stage_package_updates_receipt_metadata_without_rewriting_members(tmp_path):
    raw = b"immutable package member"
    manifest = {
        "files": [{"path": "member.txt", "kind": "file",
                   "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)}]
    }
    staging_root = tmp_path / "staging"
    first = artifacts.stage_package(
        None, staging_root, manifest=manifest, files={"member.txt": raw},
        format="format-a", version="1", dependencies=["first"])

    second = artifacts.stage_package(
        None, staging_root, manifest=manifest, files={"member.txt": raw},
        format="format-b", version="2", dependencies=["second"])

    assert second["digest"] == first["digest"]
    assert (Path(first["staging_dir"]) / "member.txt").read_bytes() == raw
    stored_receipt = json.loads(
        (Path(first["staging_dir"]) / "_receipt.json").read_text())
    assert stored_receipt["format"] == "format-b"
    assert stored_receipt["version"] == "2"
    assert stored_receipt["dependencies"] == ["second"]


def test_stage_package_replaces_receipt_symlink_without_writing_through(tmp_path):
    raw = b"immutable package member"
    manifest = {
        "files": [{"path": "member.txt", "kind": "file",
                   "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)}]
    }
    first = artifacts.stage_package(
        None, tmp_path / "staging", manifest=manifest,
        files={"member.txt": raw}, format="format-a")
    stage_dir = Path(first["staging_dir"])
    receipt_path = stage_dir / "_receipt.json"
    external = tmp_path / "outside.json"
    external.write_bytes(b"keep this target unchanged")
    receipt_path.unlink()
    try:
        receipt_path.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"host cannot create a file symlink: {exc}")

    artifacts.stage_package(
        None, tmp_path / "staging", manifest=manifest,
        files={"member.txt": raw}, format="format-b")

    assert external.read_bytes() == b"keep this target unchanged"
    assert not receipt_path.is_symlink()
    assert json.loads(receipt_path.read_text())["format"] == "format-b"
    assert (stage_dir / "member.txt").read_bytes() == raw


@pytest.mark.parametrize("kind", ["file", "dir"])
@pytest.mark.parametrize("path", ["_receipt.json", "_RECEIPT.JSON"])
def test_stage_package_reserves_generated_receipt_path(tmp_path, kind, path):
    raw = b"package data"
    entry = {"path": path, "kind": kind}
    files = {}
    if kind == "file":
        entry.update({"digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)})
        files[path] = raw
    manifest = {"files": [entry]}
    with pytest.raises(SettlementError, match="reserved staging path"):
        artifacts.stage_package(
            None, tmp_path / "staging", manifest=manifest, files=files)

