from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from settlement import artifacts, capabilities
from settlement.common import SettlementError

ENTRY_A = b"ENTRY = 'A'\n"
ENTRY_B = b"ENTRY = 'B'\n"


def _manifest_entry(manifest: dict) -> str:
    return capabilities.resolve_entry_path(manifest)


def _package(entries: list[tuple[str, bytes]], named: str | None) -> tuple[dict, dict]:
    files = {path: body for path, body in entries}
    manifest = {
        "files": [{"path": path, "digest": hashlib.sha256(body).hexdigest(),
                   "size": len(body), "kind": "file"}
                  for path, body in entries],
    }
    if named is not None:
        manifest["entry"] = named
    package = {"manifest": manifest, "scope": "", "files":
               {path: body.hex() for path, body in files.items()}}
    return package, manifest


def test_resolver_honours_named_entry_over_first_python():
    _package_body, manifest = _package(
        [("A.py", ENTRY_A), ("B.py", ENTRY_B)], named="B.py")

    assert _manifest_entry(manifest) == "B.py"


def test_resolver_falls_back_to_first_python_only_when_unnamed():
    _package_body, manifest = _package(
        [("A.py", ENTRY_A), ("B.py", ENTRY_B)], named=None)

    assert _manifest_entry(manifest) == "A.py"


def test_resolver_refuses_entry_absent_from_files():
    _package_body, manifest = _package([("A.py", ENTRY_A)], named="missing.py")

    with pytest.raises(SettlementError, match="not in the manifest files"):
        _manifest_entry(manifest)


def test_resolver_refuses_manifest_with_no_executable_entry():
    _package_body, manifest = _package([("README.txt", b"no code here")], named=None)

    with pytest.raises(SettlementError, match="no executable entry"):
        _manifest_entry(manifest)


def test_extract_and_invoke_resolve_the_same_entry(tmp_path):
    published, manifest = _package(
        [("A.py", ENTRY_A), ("B.py", ENTRY_B)], named="B.py")
    staged = artifacts.stage_package(
        None, tmp_path / "staging", manifest=manifest,
        files={"A.py": ENTRY_A, "B.py": ENTRY_B})
    (tmp_path / "store").mkdir()
    (tmp_path / "store" / staged["digest"]).write_bytes(
        json.dumps(published, sort_keys=True, separators=(",", ":")).encode())

    path, body, _args = capabilities._extract_entry(
        tmp_path / "store", staged["digest"])

    assert path == "B.py"
    assert body == ENTRY_B


def test_entry_bytes_selected_are_the_named_file_not_the_first_python():
    _package_body, manifest = _package(
        [("A.py", ENTRY_A), ("B.py", ENTRY_B)], named="B.py")
    files = {"A.py": ENTRY_A, "B.py": ENTRY_B}

    selected = files[_manifest_entry(manifest)]

    assert selected == ENTRY_B
    assert selected != ENTRY_A


def test_invoke_method_stages_the_named_entry_not_the_first_python(tmp_path):
    from settlement import experiment

    published, manifest = _package(
        [("A.py", ENTRY_A), ("B.py", ENTRY_B)], named="B.py")
    staged = artifacts.stage_package(
        None, tmp_path / "staging", manifest=manifest,
        files={"A.py": ENTRY_A, "B.py": ENTRY_B})
    root = tmp_path / "store"
    root.mkdir()
    (root / staged["digest"]).write_bytes(
        json.dumps(published, sort_keys=True, separators=(",", ":")).encode())

    class _Launcher:
        def __init__(self):
            self.staged: dict[str, bytes] = {}

        def stage_input(self, _op, _ver, name, body):
            self.staged[name] = body

        def staged_python(self):
            return "python"

        def exec_dirs(self, _op, _ver):
            return ("in", "out")

        def read_output(self, *_a):
            return b"fixed"

    launcher = _Launcher()
    monkeypatch_target = experiment
    original_sandbox = monkeypatch_target._run_sandbox
    original_broker = experiment.broker.read_operation
    monkeypatch_target._run_sandbox = lambda *_a, **_k: (
        "op", {"content": {"data": {"worker": {"status": "ok"}}}})
    experiment.broker.read_operation = lambda *_a, **_k: {"dispatch_state": "observed"}
    try:
        _fixed, executed_source = monkeypatch_target._invoke_method(
            "unused", launcher, root,
            {"artifact_digest": staged["digest"]}, "b'pass'", "t", "a", "e")
    finally:
        monkeypatch_target._run_sandbox = original_sandbox
        experiment.broker.read_operation = original_broker

    assert launcher.staged["method.py"] == ENTRY_B
    assert executed_source == ENTRY_B.decode()
    assert executed_source != ENTRY_A.decode()


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

