"""REC-1/REC-2: consistent checkpoint of a live settlement database.

Writes into --out-dir: a pg_dump custom-format backup of the domain
database (peer-auth local socket; DSNs carrying a password are refused so
no credential ever appears on a command line), a JSON manifest (source
commit SHA, schema_migrations rows, control epochs, per-table row counts,
artifact digest manifest with sizes), and a tar of the artifact root.
Outputs are fsync'd; digests are printed to stdout as JSON.

The script establishes the domain barrier itself (REC-1): it pauses
dispatch, bumps the admission epoch, fences in-flight senders with a
dispatch-generation bump, snapshots the journal and undelivered outbox,
reads the barrier-point state, dumps, verifies no movement, writes the
manifest and artifacts, verifies again, then releases the pause. Any
movement in either interval refuses to certify. The barrier is dispatch-wide
(`control.dispatch_paused`), not per attempt. An optional --workflow-dsn
extends the barrier, dump and verification to the coordinated workflow
store (a real DBOS system database, or a Settlement-shaped store labeled as
such).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from settlement import store
from settlement.common import Command

REPO_ROOT = Path(__file__).resolve().parent.parent


def dbname_of(dsn: str) -> str:
    if "://" in dsn:
        path = urlparse(dsn).path.strip("/")
        if path:
            return path.split("?")[0]
    for token in dsn.replace(";", " ").split():
        if "=" in token:
            key, value = token.split("=", 1)
            if key.strip().lower() == "dbname":
                return value
    return ""


def _refuse_password(dsn: str) -> None:
    if "PGPASSWORD" in os.environ:
        raise SystemExit("refusing checkpoint: PGPASSWORD is set; use peer auth")
    if "://" in dsn:
        parsed = urlparse(dsn)
        if parsed.password or "password" in dict(parse_qsl(parsed.query)):
            raise SystemExit("refusing checkpoint: DSN must use peer auth, no passwords")
    elif "password" in dsn.lower():
        raise SystemExit("refusing checkpoint: DSN must use peer auth, no passwords")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    with open(path, "rb") as handle:
        os.fsync(handle.fileno())
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _source_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=15)
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _pg_dump(dsn: str, dump_path: Path) -> None:
    _refuse_password(dsn)
    env = {k: v for k, v in os.environ.items() if k != "PGPASSWORD"}
    proc = subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(dump_path), dsn],
        capture_output=True, text=True, env=env, timeout=300)
    if proc.returncode != 0:
        raise SystemExit(f"pg_dump failed: {proc.stderr.strip()}")


def _db_state(dsn: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT name FROM schema_migrations ORDER BY name")
            migrations = [r["name"] for r in cur.fetchall()]
            cur.execute("SELECT * FROM control WHERE id = 1")
            control = dict(cur.fetchone())
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            tables = [r["tablename"] for r in cur.fetchall()]
            counts = {}
            for table in tables:
                cur.execute(f' SELECT COUNT(*) AS n FROM "{table}"')
                counts[table] = int(cur.fetchone()["n"])
            conn.commit()
    return {"migrations": migrations, "control": control, "row_counts": counts}


def _artifact_manifest(root: Path) -> list[dict]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        entries.append({"path": rel, "size": path.stat().st_size,
                        "sha256": _sha256(path)})
    return entries


def _write_tar(root: Path, tar_path: Path) -> None:
    with tarfile.open(tar_path, "w") as tar:
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            info = tar.gettarinfo(str(path), arcname=str(path.relative_to(root)))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with open(path, "rb") as handle:
                tar.addfile(info, handle)


def _barrier(dsn: str) -> dict:
    result = store.checkpoint_barrier(
        dsn, Command(request_id=f"ckpt-barrier-{uuid.uuid4().hex[:12]}", payload={}))
    if result.code.value != "applied":
        raise SystemExit(f"refusing checkpoint: barrier not established: {result.detail}")
    return result.data


def _release(dsn: str, reason: str) -> None:
    result = store.resume_dispatch(
        dsn, Command(request_id=f"ckpt-release-{uuid.uuid4().hex[:12]}",
                     payload={"reason": reason, "only_reason": "checkpoint"}))
    if result.code.value == "already_applied" and not result.data.get("resumed", True):
        return
    if result.code.value != "applied":
        raise SystemExit(f"checkpoint pause not released on {dbname_of(dsn)}: {result.detail}")


def _table_names(dsn: str) -> set[str]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            names = {r[0] for r in cur.fetchall()}
            conn.commit()
            return names


def _dbos_sys_schema(dsn: str) -> str:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT table_schema FROM information_schema.tables"
                        " WHERE table_name = 'workflow_status'"
                        " AND table_schema NOT IN ('pg_catalog', 'information_schema')"
                        " ORDER BY table_schema")
            rows = [r[0] for r in cur.fetchall()]
            conn.commit()
    return rows[0] if rows else ""


def _dbos_progress(dsn: str, schema: str) -> dict:
    import hashlib
    import json

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f'SELECT workflow_uuid, status FROM "{schema}".workflow_status'
                        " ORDER BY workflow_uuid")
            statuses = [(r["workflow_uuid"], r["status"]) for r in cur.fetchall()]
            cur.execute(f'SELECT workflow_uuid, function_id, COALESCE(output, \'\') AS output,'
                        f" COALESCE(error, '') AS error,"
                        f" COALESCE(child_workflow_id, '') AS child"
                        f' FROM "{schema}".operation_outputs'
                        " ORDER BY workflow_uuid, function_id")
            steps = [(r["workflow_uuid"], int(r["function_id"]), r["output"],
                      r["error"], r["child"]) for r in cur.fetchall()]
            conn.commit()
    digest = hashlib.sha256(json.dumps(steps, sort_keys=True).encode()).hexdigest()
    pending = [uuid for uuid, status in statuses if status in ("ENQUEUED", "PENDING")]
    return {"pending_workflows": pending, "workflow_statuses": statuses,
            "step_count": len(steps), "step_digest": digest}


def _workflow_barrier(dsn: str) -> tuple[dict, str]:
    schema = _dbos_sys_schema(dsn)
    if schema:
        barrier = {"kind": "dbos-system"}
        barrier.update(_dbos_progress(dsn, schema))
        return barrier, schema
    if "control" in _table_names(dsn):
        data = _barrier(dsn)
        data["kind"] = "settlement-shaped"
        return data, ""
    raise SystemExit(f"refusing checkpoint: workflow store {dbname_of(dsn)} is neither"
                     " a DBOS system database nor Settlement-shaped")


def _workflow_verify(dsn: str, barrier: dict, schema: str) -> list[str]:
    if barrier.get("kind") == "dbos-system":
        now = _dbos_progress(dsn, schema)
        violations = []
        if now["pending_workflows"] != list(barrier["pending_workflows"]):
            violations.append("workflow store moved during checkpoint:"
                              f" barrier={barrier['pending_workflows']}"
                              f" now={now['pending_workflows']}")
        if [list(row) for row in now["workflow_statuses"]] != \
                [list(row) for row in barrier["workflow_statuses"]]:
            violations.append("workflow statuses moved during checkpoint:"
                              f" barrier={barrier['workflow_statuses']}"
                              f" now={now['workflow_statuses']}")
        if now["step_count"] != barrier["step_count"] or \
                now["step_digest"] != barrier["step_digest"]:
            violations.append("workflow steps moved during checkpoint:"
                              f" barrier={barrier['step_count']}/{barrier['step_digest']}"
                              f" now={now['step_count']}/{now['step_digest']}")
        return violations
    return [f"workflow: {v}" for v in store.checkpoint_verify(dsn, barrier)]


def _write_manifest(manifest_path: Path, name: str, state: dict, barrier: dict,
                    artifacts_root: Path, workflow_dsn: str | None,
                    wf_barrier: dict | None, dsn: str) -> Path:
    with_db = dict(state["control"])
    manifest = {
        "source": {"database": name, "commit": _source_commit(),
                   "checkpoint_at": datetime.now(timezone.utc).isoformat(),
                   "artifacts_root": str(artifacts_root.resolve()),
                   "domain_dsn": dsn, "workflow_dsn": workflow_dsn or ""},
        "migrations": state["migrations"],
        "control": {k: with_db.get(k) for k in
                    ("admission_epoch", "authority_version", "evidence_epoch",
                     "release_epoch", "event_epoch")},
        "row_counts": state["row_counts"],
        "barrier": barrier,
        "journal_count": barrier["journal_count"],
        "outbox_pending": barrier["outbox_pending"],
        "workflow": ({"coordinated": True, "database": dbname_of(workflow_dsn or ""),
                      "kind": (wf_barrier or {}).get("kind", "unknown"),
                      "barrier": wf_barrier}
                     if workflow_dsn else {"coordinated": False,
                                           "note": "no workflow store configured"}),
        "artifacts": _artifact_manifest(artifacts_root),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest_path


def run_checkpoint(dsn: str, artifacts_root: str | Path, out_dir: str | Path,
                   workflow_dsn: str | None = None, _between=None) -> dict:
    _refuse_password(dsn)
    artifacts_root = Path(artifacts_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = dbname_of(dsn) or "settlement"
    dump_path = out_dir / f"{name}.dump"
    manifest_path = out_dir / "manifest.json"
    tar_path = out_dir / "artifacts.tar"
    barrier = _barrier(dsn)
    wf_barrier: dict | None = None
    wf_schema = ""
    wf_dump_path: Path | None = None
    paused = [] if barrier.get("pre_paused") else [dsn]
    try:
        if workflow_dsn:
            _refuse_password(workflow_dsn)
            wf_barrier, wf_schema = _workflow_barrier(workflow_dsn)
            if wf_barrier.get("kind") != "dbos-system" and not wf_barrier.get("pre_paused"):
                paused.append(workflow_dsn)
            wf_dump_path = out_dir / f"{dbname_of(workflow_dsn) or 'workflow'}.workflow.dump"
        state = _db_state(dsn)
        if _between is not None:
            _between(barrier)
        _pg_dump(dsn, dump_path)
        if workflow_dsn and wf_dump_path is not None:
            _pg_dump(workflow_dsn, wf_dump_path)
        violations = store.checkpoint_verify(dsn, barrier)
        if workflow_dsn and wf_barrier is not None:
            violations += _workflow_verify(workflow_dsn, wf_barrier, wf_schema)
        if violations:
            raise SystemExit("refusing checkpoint: barrier violated: " + "; ".join(violations))
        _write_manifest(manifest_path, name, state, barrier, artifacts_root,
                        workflow_dsn, wf_barrier, dsn)
        _write_tar(artifacts_root, tar_path)
        violations = store.checkpoint_verify(dsn, barrier)
        if workflow_dsn and wf_barrier is not None:
            violations += _workflow_verify(workflow_dsn, wf_barrier, wf_schema)
        if violations:
            raise SystemExit("refusing checkpoint: state moved while writing recovery set: "
                             + "; ".join(violations))
    finally:
        for suspended in paused:
            _release(suspended, "checkpoint-complete")
    outputs = [dump_path, manifest_path, tar_path]
    if wf_dump_path is not None:
        outputs.append(wf_dump_path)
    for path in outputs:
        _fsync(path)
    result = {"dump": str(dump_path), "manifest": str(manifest_path),
              "tar": str(tar_path),
              "digests": {p.name: _sha256(out_dir / p.name) for p in outputs}}
    if wf_dump_path is not None:
        result["workflow_dump"] = str(wf_dump_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--workflow-dsn", default=None)
    args = parser.parse_args(argv)
    print(json.dumps(run_checkpoint(args.dsn, args.artifacts_root, args.out_dir,
                                    args.workflow_dsn),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
