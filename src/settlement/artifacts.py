"""S2 artifact staging, publication, protection and retention (ART-1..ART-4).

Staging lives outside the authoritative namespace; only ``publish_package``
commits availability, and only after bytes are fsync-durable at their final
content-addressed path. Protection references are counted under the store
control lock; retirement marks first and removes never.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
from pathlib import Path, PureWindowsPath
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import db, exec_profile, store
from .common import Command, CommandResult, ResultCode, SettlementError, fsync_dir, open_nofollow

STAGE_MAX_BYTES = 64 * 1024 * 1024
STAGE_MAX_FILES = 1024
_TMP_GRACE_S = 3600

_VISIBLE = {
    "public": ("public",),
    "candidate": ("public", "candidate"),
    "evaluator": ("public", "candidate", "hidden", "evaluator"),
    "operator": ("public", "candidate", "hidden", "evaluator"),
}
_HOLDERS = ("evidence", "release", "attempt", "checkpoint", "continuation")


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _check_relpath(rel: str) -> None:
    if (not isinstance(rel, str) or not rel or "\\" in rel
            or PureWindowsPath(rel).drive or rel.startswith("~")):
        raise SettlementError(f"rejected path {rel!r}: must be relative")
    parts = rel.split("/")
    if ("" in parts) or ("." in parts) or (".." in parts):
        raise SettlementError(f"rejected path {rel!r}: traversal or empty segment")


def _check_manifest(manifest: dict) -> list[dict]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise SettlementError("manifest must be a dict with a 'files' list")
    entries = manifest["files"]
    if len(entries) > STAGE_MAX_FILES:
        raise SettlementError(f"too many staged files: {len(entries)}")
    total = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise SettlementError("manifest entries must be dicts")
        _check_relpath(entry.get("path", ""))
        kind = entry.get("kind", "file")
        if kind in ("symlink", "hardlink", "link"):
            raise SettlementError(f"rejected link entry {entry.get('path')!r}")
        if kind not in ("file", "dir", "archive"):
            raise SettlementError(f"unexpected entry type {kind!r}")
        if kind != "dir" and (not entry.get("digest") or entry.get("size") is None):
            raise SettlementError(f"entry {entry.get('path')!r} needs digest and size")
        try:
            total += int(entry.get("size") or 0)
        except (TypeError, ValueError):
            raise SettlementError(f"entry {entry.get('path')!r} has a non-integer size")
    if total > STAGE_MAX_BYTES:
        raise SettlementError(f"staged package {total} bytes exceeds {STAGE_MAX_BYTES}")
    return entries


def _scope_used(dsn: str, scope: str) -> int:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COALESCE(SUM(size), 0) AS used FROM artifact_versions"
                        " WHERE scope = %s AND retention_state != 'purged'",
                        (scope,))
            conn.commit()
            return int(cur.fetchone()["used"])


def _check_budget(dsn: str | None, scope: str, size: int) -> None:
    if dsn is None or not scope:
        return
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT quota_bytes FROM retention_budgets WHERE scope = %s", (scope,))
            row = cur.fetchone()
            conn.commit()
    if row is not None and _scope_used(dsn, scope) + size > int(row["quota_bytes"]):
        raise SettlementError(f"scope {scope!r} over quota: staged {size} exceeds budget")


def _contained(root: Path, rel: str) -> Path:
    base = Path(os.path.realpath(root))
    target = base / rel
    parent = Path(os.path.realpath(target.parent))
    if parent != base and base not in parent.parents:
        raise SettlementError(f"rejected path {rel!r}: escapes the staging root")
    return target


def _safe_write(root: Path, rel: str, raw: bytes) -> Path:
    target = _contained(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    binary = getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     binary | nofollow, 0o644)
    except FileExistsError:
        try:
            if not stat.S_ISREG(target.lstat().st_mode):
                raise SettlementError(
                    f"rejected path {rel!r}: existing staging path is not a regular file")
            fd = os.open(target, os.O_RDONLY | binary | nofollow)
            with os.fdopen(fd, "rb") as handle:
                existing = handle.read()
        except OSError as exc:
            raise SettlementError(f"rejected path {rel!r}: {exc.strerror or exc}")
        if existing != raw:
            raise SettlementError(
                f"rejected path {rel!r}: existing staged bytes differ")
        return target
    except OSError as exc:
        raise SettlementError(f"rejected path {rel!r}: {exc.strerror or exc}")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return target


def _strip_dot_prefix(name: str) -> str:
    return name[2:] if name.startswith("./") else name


def _unpacked_size(dest: Path) -> int:
    return sum(p.stat().st_size for p in dest.rglob("*") if p.is_file() and not p.is_symlink())


def _reject_untrusted_extraction(dest: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(dest, followlinks=False):
        for name in dirnames + filenames:
            found = Path(dirpath) / name
            if found.is_symlink() or not (found.is_file() or found.is_dir()):
                raise SettlementError(
                    f"rejected archive member {found.relative_to(dest)}: links and"
                    " special files are never materialized")


def _unpack_archive_isolated(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    listed = exec_profile.run_local_process(
        ["tar", "-tzf", str(archive)], timeout_ms=30_000, max_output_bytes=1_048_576)
    if listed.returncode != 0:
        raise SettlementError(f"archive list failed: {listed.stderr[:200]}")
    for line in listed.stdout.splitlines():
        _check_relpath(_strip_dot_prefix(line.strip()) or ".")
    # Refuse links and special members before anything is materialized; the
    # verbose listing's first column is the member type on GNU tar and bsdtar.
    verbose = exec_profile.run_local_process(
        ["tar", "-tvzf", str(archive)], timeout_ms=30_000, max_output_bytes=4_194_304)
    if verbose.returncode != 0:
        raise SettlementError(f"archive list failed: {verbose.stderr[:200]}")
    for line in verbose.stdout.splitlines():
        if line and line[0] not in "-d":
            raise SettlementError(
                f"rejected archive member {line.split()[-1]!r}: links and"
                " special files are never materialized")
    result = exec_profile.run_local_process(
        ["tar", "-xzf", str(archive), "-C", str(dest),
         "--no-same-owner", "--no-same-permissions"], timeout_ms=60_000,
        max_output_bytes=1_048_576)
    if result.returncode != 0:
        raise SettlementError(f"archive unpack failed: {result.stderr[:200]}")
    _reject_untrusted_extraction(dest)
    if _unpacked_size(dest) > STAGE_MAX_BYTES:
        raise SettlementError("unpacked archive exceeds staging byte bound")


def package_bytes(manifest: dict, files: dict[str, bytes], scope: str) -> bytes:
    """Canonical package encoding, shared by identity and publication."""
    return json.dumps({"manifest": manifest, "scope": scope,
                       "files": {rel: raw.hex() for rel, raw in files.items()}},
                      sort_keys=True, separators=(",", ":")).encode()


def stage_package(dsn: str | None, staging_root: str | Path, *, manifest: dict,
                  files: dict[str, bytes], scope: str = "", access_label: str = "public",
                  format: str = "", version: str = "",
                  dependencies: list[str] | None = None) -> dict:
    entries = _check_manifest(manifest)
    if access_label not in _VISIBLE["evaluator"]:
        raise SettlementError(f"unknown access label {access_label!r}")
    by_path = {entry["path"]: entry for entry in entries}
    if {p for p, e in by_path.items() if e.get("kind", "file") != "dir"} != set(files):
        raise SettlementError("staged files do not match manifest paths")
    if any(entry["path"].casefold() == "_receipt.json" for entry in entries):
        raise SettlementError("rejected path '_receipt.json': reserved staging path")
    size = 0
    for rel, raw in files.items():
        entry = by_path[rel]
        if entry.get("kind", "file") == "dir":
            raise SettlementError(f"dir entry {rel!r} takes no bytes")
        if _digest_bytes(raw) != entry["digest"] or len(raw) != int(entry["size"]):
            raise SettlementError(f"content mismatch for {rel!r}")
        size += len(raw)
    _check_budget(dsn, scope, size)
    payload = package_bytes(manifest, files, scope)
    package_digest = _digest_bytes(payload)
    stage_dir = Path(staging_root) / package_digest
    stage_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        if entry.get("kind") == "dir":
            _contained(stage_dir, entry["path"]).mkdir(parents=True, exist_ok=True)
    for rel, raw in files.items():
        _safe_write(stage_dir, rel, raw)
        if by_path[rel].get("kind") == "archive" and by_path[rel].get("unpack"):
            _unpack_archive_isolated(stage_dir / rel, stage_dir / (rel + ".unpacked"))
    receipt = {"digest": package_digest, "size": size, "manifest": manifest,
               "scope": scope, "access_label": access_label, "format": format,
               "version": version, "dependencies": list(dependencies or [])}
    receipt_path = stage_dir / "_receipt.json"
    fd, temp_path = tempfile.mkstemp(prefix=".receipt-", dir=stage_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(receipt).encode())
        os.replace(temp_path, receipt_path)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
    return dict(receipt, staging_dir=str(stage_dir))


def _final_path(artifacts_root: Path, digest: str) -> Path:
    return artifacts_root / digest


def _write_final_bytes(artifacts_root: Path, receipt: dict, stage_dir: Path) -> Path:
    artifacts_root.mkdir(parents=True, exist_ok=True)
    final = _final_path(artifacts_root, receipt["digest"])
    if final.is_symlink() or (final.exists() and not final.is_file()):
        raise SettlementError(f"final path {receipt['digest']!r} is not a regular file")
    if final.is_file():
        with open(final, "rb") as handle:
            if _digest_bytes(handle.read()) != receipt["digest"]:
                raise SettlementError("existing bytes do not match digest")
        return final
    stage_files = {}
    for entry in receipt["manifest"]["files"]:
        if entry.get("kind", "file") == "dir":
            continue
        with open(stage_dir / entry["path"], "rb") as handle:
            stage_files[entry["path"]] = handle.read().hex()
    payload = package_bytes(receipt["manifest"],
                            {rel: bytes.fromhex(raw) for rel, raw in stage_files.items()},
                            receipt["scope"])
    if _digest_bytes(payload) != receipt["digest"]:
        raise SettlementError("staging bytes do not match receipt digest")
    tmp = final.parent / (receipt["digest"] + ".tmp")
    fd = open_nofollow(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.rename(tmp, final)
    fsync_dir(final.parent)
    return final


def _manifest_size(manifest: dict) -> int:
    return sum(int(entry.get("size") or 0) for entry in manifest.get("files", [])
               if entry.get("kind", "file") != "dir")


def publish_package(dsn: str, cmd: Command, artifacts_root: str | Path, receipt: dict) -> CommandResult:
    roots = Path(artifacts_root)
    stage_dir = Path(receipt.get("staging_dir", ""))
    if not stage_dir.is_dir():
        raise SettlementError("staging receipt has no staging dir")
    for entry in receipt.get("manifest", {}).get("files", []):
        _check_relpath(entry.get("path", ""))
    if int(receipt.get("size", -1)) != _manifest_size(receipt.get("manifest", {})):
        raise SettlementError("staging receipt size does not match its manifest")
    _write_final_bytes(roots, receipt, stage_dir)

    def _fn(cur, control):
        cur.execute("SELECT digest, availability FROM artifact_versions WHERE digest = %s",
                    (receipt["digest"],))
        found = cur.fetchone()
        if found is not None:
            return (ResultCode.ALREADY_APPLIED, "artifact already published",
                    {"digest": receipt["digest"], "availability": found["availability"]}, [], [])
        cur.execute(
            "INSERT INTO artifact_versions (digest, size, manifest, format, version, dependencies,"
            " availability, access_label, scope, path) VALUES (%s, %s, %s, %s, %s, %s,"
            " 'available', %s, %s, %s)",
            (receipt["digest"], int(receipt["size"]), _j(receipt["manifest"]),
             receipt.get("format", ""), receipt.get("version", ""),
             _j(receipt.get("dependencies", [])), receipt.get("access_label", "public"),
             receipt.get("scope", ""), receipt["digest"]),
        )
        return (ResultCode.APPLIED, f"artifact {receipt['digest'][:12]} published",
                {"digest": receipt["digest"], "availability": "available"},
                [("artifact.published", {"digest": receipt["digest"]})], [])
    return store.transact(dsn, cmd, _fn)


def reconcile_staging(dsn: str, staging_root: str | Path, artifacts_root: str | Path) -> dict:
    roots, staged = Path(artifacts_root), Path(staging_root)
    registered, reclaimed = [], []
    orphans = [p for p in roots.iterdir()] if roots.is_dir() else []
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            known = set()
            if orphans:
                cur.execute("SELECT digest FROM artifact_versions WHERE digest = ANY(%s)",
                            ([p.name for p in orphans],))
                known = {row["digest"] for row in cur.fetchall()}
            conn.commit()
    receipts: dict[str, dict] = {}
    if staged.is_dir():
        for receipt_path in staged.glob("*/_receipt.json"):
            try:
                doc = json.loads(receipt_path.read_text())
                receipts[doc["digest"]] = doc
            except (ValueError, KeyError, OSError):
                continue
    with db.connect(dsn) as conn:
        for orphan in orphans:
            if orphan.name in known or not orphan.is_file():
                continue
            if orphan.suffix == ".tmp":
                if time.time() - orphan.stat().st_mtime < _TMP_GRACE_S:
                    continue
                orphan.unlink()
                reclaimed.append(orphan.name)
                continue
            with open(orphan, "rb") as handle:
                digest = _digest_bytes(handle.read())
            if orphan.name != digest or digest not in receipts:
                orphan.unlink()
                reclaimed.append(orphan.name)
                continue
            manifest = receipts[digest].get("manifest")
            if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
                continue
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO artifact_versions (digest, size, manifest, availability, path)"
                    " VALUES (%s, %s, %s, 'available', %s) ON CONFLICT (digest) DO NOTHING",
                    (digest, _manifest_size(manifest), Json(manifest), digest),
                )
            registered.append(digest)
        conn.commit()
    return {"registered": registered, "reclaimed": reclaimed}


def _add_reference(cur, digest: str, holder_kind: str, holder_id: str) -> None:
    cur.execute("SELECT digest FROM artifact_versions WHERE digest = %s", (digest,))
    if cur.fetchone() is None:
        raise SettlementError(f"unknown artifact {digest[:12]}")
    cur.execute(
        "INSERT INTO artifact_refs (digest, holder_kind, holder_id) VALUES (%s, %s, %s)"
        " ON CONFLICT (digest, holder_kind, holder_id) DO NOTHING",
        (digest, holder_kind, holder_id),
    )
    if cur.rowcount:
        cur.execute("UPDATE artifact_versions SET protection_count = protection_count + 1"
                    " WHERE digest = %s", (digest,))


def add_reference(dsn: str, cmd: Command, digest: str, holder_kind: str, holder_id: str) -> CommandResult:
    if holder_kind not in _HOLDERS:
        raise SettlementError(f"unknown holder kind {holder_kind!r}")

    def _fn(cur, control):
        _add_reference(cur, digest, holder_kind, holder_id)
        cur.execute("SELECT protection_count FROM artifact_versions WHERE digest = %s", (digest,))
        count = int(cur.fetchone()["protection_count"])
        return (ResultCode.APPLIED, "reference added",
                {"digest": digest, "protection_count": count},
                [("artifact.referenced", {"digest": digest, "holder_kind": holder_kind})], [])
    return store.transact(dsn, cmd, _fn)


def remove_reference(dsn: str, cmd: Command, digest: str, holder_kind: str, holder_id: str) -> CommandResult:
    def _fn(cur, control):
        cur.execute("DELETE FROM artifact_refs WHERE digest = %s AND holder_kind = %s AND holder_id = %s",
                    (digest, holder_kind, holder_id))
        if cur.rowcount:
            cur.execute("UPDATE artifact_versions SET protection_count = GREATEST(protection_count - 1, 0)"
                        " WHERE digest = %s", (digest,))
        cur.execute("SELECT protection_count FROM artifact_versions WHERE digest = %s", (digest,))
        row = cur.fetchone()
        return (ResultCode.APPLIED, "reference removed",
                {"digest": digest, "protection_count": int(row["protection_count"]) if row else 0},
                [("artifact.unreferenced", {"digest": digest})], [])
    return store.transact(dsn, cmd, _fn)


def retire_artifact(dsn: str, cmd: Command, digest: str) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT digest FROM artifact_versions WHERE digest = %s", (digest,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown artifact {digest[:12]}")
        cur.execute("UPDATE artifact_versions SET availability = 'retired', retention_state = 'retired'"
                    " WHERE digest = %s", (digest,))
        return (ResultCode.APPLIED, "artifact retired", {"digest": digest, "availability": "retired"},
                [("artifact.retired", {"digest": digest})], [])
    return store.transact(dsn, cmd, _fn)


def collect_garbage(dsn: str, artifacts_root: str | Path) -> dict:
    roots = Path(artifacts_root)
    removed, kept = [], []
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT digest, protection_count, availability FROM artifact_versions"
                        " WHERE availability = 'retired'")
            candidates = [dict(r) for r in cur.fetchall()]
            conn.commit()
    for row in candidates:
        with db.connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT protection_count, availability FROM artifact_versions"
                            " WHERE digest = %s", (row["digest"],))
                fresh = cur.fetchone()
                conn.commit()
        if (fresh is None or int(fresh["protection_count"]) > 0
                or fresh["availability"] != "retired"):
            kept.append(row["digest"])
            continue
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE artifact_versions SET retention_state = 'purged', path = ''"
                            " WHERE digest = %s AND protection_count = 0"
                            " AND availability = 'retired'", (row["digest"],))
                purged = cur.rowcount
                conn.commit()
        if purged:
            target = roots / row["digest"]
            if target.is_file() and not target.is_symlink():
                target.unlink()
            removed.append(row["digest"])
        else:
            kept.append(row["digest"])
    return {"removed": removed, "kept": kept}


def verify_bytes(dsn: str, artifacts_root: str | Path, digest: str) -> dict:
    ok = bytes_match(artifacts_root, digest)
    if ok:
        return {"digest": digest, "ok": True}
    target = Path(artifacts_root) / digest
    reason = "missing bytes" if not target.exists() else "digest mismatch"
    if not _known_digest(dsn, digest):
        return {"digest": digest, "ok": False, "reason": "unknown digest"}

    def _fn(cur, control):
        cur.execute("UPDATE artifact_versions SET availability = 'invalid' WHERE digest = %s",
                    (digest,))
        cur.execute("UPDATE control SET evidence_epoch = evidence_epoch + 1 WHERE id = 1"
                    " RETURNING evidence_epoch")
        epoch = int(cur.fetchone()["evidence_epoch"])
        return (ResultCode.APPLIED, f"artifact {digest[:12]} marked invalid",
                {"digest": digest, "evidence_epoch": epoch},
                [("artifact.invalid", {"digest": digest})], [])
    from .common import new_id
    store.transact(dsn, Command(request_id=new_id("req"), payload={}), _fn)
    return {"digest": digest, "ok": False, "reason": reason}


def _known_digest(dsn: str, digest: str) -> bool:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM artifact_versions WHERE digest = %s", (digest,))
            found = cur.fetchone() is not None
            conn.commit()
            return found


def bytes_match(artifacts_root: str | Path, digest: str) -> bool:
    target = Path(artifacts_root) / digest
    try:
        if target.is_symlink() or not target.is_file():
            return False
        fd = open_nofollow(target, os.O_RDONLY)
        with os.fdopen(fd, "rb") as handle:
            return _digest_bytes(handle.read()) == digest
    except OSError:
        return False


def artifact_available(dsn: str, artifacts_root: str | Path, digest: str) -> bool:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT availability FROM artifact_versions WHERE digest = %s", (digest,))
            row = cur.fetchone()
            conn.commit()
    if row is None or row["availability"] != "available":
        return False
    return bytes_match(artifacts_root, digest)


def scoped_artifacts(dsn: str, caller_scope: str) -> list[dict]:
    labels = _VISIBLE.get(caller_scope, ("public",))
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT digest, size, format, version, availability, access_label, scope"
                        " FROM artifact_versions WHERE access_label = ANY(%s) ORDER BY digest",
                        (list(labels),))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows


def set_retention_budget(dsn: str, cmd: Command, scope: str, quota_bytes: int,
                         kind: str = "working_set") -> CommandResult:
    if kind not in ("working_set", "archive"):
        raise SettlementError(f"unknown budget kind {kind!r}")

    def _fn(cur, control):
        cur.execute("INSERT INTO retention_budgets (scope, kind, quota_bytes) VALUES (%s, %s, %s)"
                    " ON CONFLICT (scope) DO UPDATE SET kind = EXCLUDED.kind,"
                    " quota_bytes = EXCLUDED.quota_bytes",
                    (scope, kind, int(quota_bytes)))
        return (ResultCode.APPLIED, f"budget for {scope!r} set to {quota_bytes}",
                {"scope": scope, "quota_bytes": int(quota_bytes)},
                [("retention.budgeted", {"scope": scope})], [])
    return store.transact(dsn, cmd, _fn)


def propose_retention_change(dsn: str, cmd: Command, scope: str, quota_bytes: int) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT COALESCE(SUM(size), 0) AS protected FROM artifact_versions"
                    " WHERE scope = %s AND protection_count > 0", (scope,))
        protected = int(cur.fetchone()["protected"])
        if int(quota_bytes) < protected:
            raise SettlementError(
                f"proposed quota {quota_bytes} bypasses {protected} protected bytes in {scope!r}")
        cur.execute("INSERT INTO retention_budgets (scope, quota_bytes) VALUES (%s, %s)"
                    " ON CONFLICT (scope) DO UPDATE SET quota_bytes = EXCLUDED.quota_bytes",
                    (scope, int(quota_bytes)))
        return (ResultCode.APPLIED, f"retention for {scope!r} now {quota_bytes}",
                {"scope": scope, "quota_bytes": int(quota_bytes)},
                [("retention.changed", {"scope": scope})], [])
    return store.transact(dsn, cmd, _fn)


def scope_usage(dsn: str, scope: str) -> dict:
    used = _scope_used(dsn, scope)
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT quota_bytes, kind FROM retention_budgets WHERE scope = %s", (scope,))
            row = cur.fetchone()
            conn.commit()
    quota = int(row["quota_bytes"]) if row else None
    return {"scope": scope, "used": used, "quota_bytes": quota,
            "kind": row["kind"] if row else None}
