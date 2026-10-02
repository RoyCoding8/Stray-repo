"""REC-3/REC-4: restore a checkpoint into a fenced environment.

Restores the pg_dump backup into a FRESH target database plus an artifact
directory, then verifies the manifest (migrations, control epochs, row
counts, artifact re-hash of every digest). Any mismatch is reported as
failure (nonzero exit); this script never reports partial success.

Refuses to touch a database whose name matches the checkpoint source, or
an artifact directory that resolves to the source artifact root. The
target database must be fresh (no rows in any domain table). A checkpoint
that coordinates a workflow store needs --workflow-target-dsn, and the
workflow target must be fresh of DBOS system schemata; the workflow dump
is restored there, never dropped. External writes stay disabled: this
script performs no dispatch and replays no journal entry as an external
command; operations that postdate the backup are listed for REC-4
reconciliation instead of being repeated. After the manifest verifies, the
script establishes the execution fence (REC-3): new ownership generations
for every live attempt, a dispatch-generation bump for every in-flight
operation, and a persisted dispatch pause, so an old dispatcher holding
pre-restore authority cannot send and no new effects dispatch until
reconciliation explicitly calls resume_dispatch. A different database name
alone is not that fence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from checkpoint import dbname_of

DOMAIN_TABLE_GUARD = "settlement tables present"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _target_rows(dsn: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            tables = [r["tablename"] for r in cur.fetchall()]
            counts = {}
            for table in tables:
                cur.execute(f' SELECT COUNT(*) AS n FROM "{table}"')
                counts[table] = int(cur.fetchone()["n"])
            conn.commit()
    return counts


def _check_fresh(target_dsn: str) -> list[str]:
    try:
        counts = _target_rows(target_dsn)
    except Exception:
        return []
    return [t for t, n in counts.items() if t != "schema_migrations" and n > 0]


def _restore_dump(dump_path: Path, target_dsn: str) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PGPASSWORD"}
    if "password" in target_dsn.lower():
        raise SystemExit("refusing restore: target DSN must use peer auth, no passwords")
    proc = subprocess.run(
        ["pg_restore", "--clean", "--if-exists", "--dbname", target_dsn, str(dump_path)],
        capture_output=True, text=True, env=env, timeout=300)
    if proc.returncode != 0:
        raise SystemExit(f"pg_restore failed: {proc.stderr.strip()}")


def _extract_tar(tar_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            target = (dest / member.name).resolve()
            if target != (dest.resolve() / member.name):
                raise SystemExit(f"refusing restore: tar member escapes: {member.name}")
        tar.extractall(dest, filter="data")


def _check_workflow_fresh(target_dsn: str) -> list[str]:
    import psycopg

    with psycopg.connect(target_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT table_schema FROM information_schema.tables"
                        " WHERE table_name = 'workflow_status'"
                        " AND table_schema NOT IN ('pg_catalog', 'information_schema')"
                        " ORDER BY table_schema")
            schemata = [r[0] for r in cur.fetchall()]
            conn.commit()
    return schemata


def _verify_restored_workflow(mismatches: list[str], manifest: dict,
                             workflow_target_dsn: str, target_dsn: str) -> tuple[list[str], int]:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    import checkpoint as _checkpoint

    from settlement import store as _store

    barrier = (manifest.get("workflow") or {}).get("barrier") or {}
    kind = (manifest.get("workflow") or {}).get("kind", "unknown")
    rebound = 0
    if kind == "dbos-system":
        schema = _checkpoint._dbos_sys_schema(workflow_target_dsn)
        if not schema:
            return mismatches + ["restored workflow target has no workflow_status"], rebound
        now = _checkpoint._dbos_progress(workflow_target_dsn, schema)
        if now["pending_workflows"] != list(barrier.get("pending_workflows", [])):
            mismatches.append("restored workflow pending differs from manifest barrier")
        if [list(row) for row in now["workflow_statuses"]] != \
                [list(row) for row in barrier.get("workflow_statuses", [])]:
            mismatches.append("restored workflow statuses differ from manifest barrier")
        if now["step_count"] != barrier.get("step_count") or \
                now["step_digest"] != barrier.get("step_digest"):
            mismatches.append("restored workflow steps differ from manifest barrier")
        pairs = [((manifest.get("source") or {}).get("domain_dsn", ""), target_dsn)]
        source_wf = (manifest.get("source") or {}).get("workflow_dsn", "")
        if source_wf:
            pairs.append((source_wf, workflow_target_dsn))
        rebound = _rebind_workflow_inputs(workflow_target_dsn, schema, pairs)
        if _residual_source_inputs(workflow_target_dsn, schema, pairs):
            mismatches.append("restored workflow inputs still reference the source DSN")
    elif kind == "settlement-shaped" and "continuations" in barrier:
        for item in _store.checkpoint_verify(workflow_target_dsn, barrier):
            mismatches.append(f"restored workflow target: {item}")
    return mismatches, rebound


def _rebind_workflow_inputs(target_dsn: str, schema: str,
                            pairs: list[tuple[str, str]]) -> int:
    import psycopg

    swaps = [(old, new) for old, new in pairs if old and old != new]
    if not swaps:
        return 0
    rebound = 0
    with psycopg.connect(target_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT workflow_uuid, inputs FROM "{schema}".workflow_status')
            rows = list(cur.fetchall())
            for workflow_uuid, inputs in rows:
                updated = inputs or ""
                for old, new in swaps:
                    if old in updated:
                        updated = updated.replace(old, new)
                if updated != (inputs or ""):
                    cur.execute(f'UPDATE "{schema}".workflow_status SET inputs = %s'
                                " WHERE workflow_uuid = %s", (updated, workflow_uuid))
                    rebound += 1
            conn.commit()
    return rebound


def _residual_source_inputs(target_dsn: str, schema: str,
                            pairs: list[tuple[str, str]]) -> bool:
    import psycopg

    with psycopg.connect(target_dsn) as conn:
        with conn.cursor() as cur:
            for old, new in pairs:
                if not old or old == new:
                    continue
                cur.execute(f'SELECT COUNT(*) FROM "{schema}".workflow_status'
                            " WHERE inputs LIKE %s", (f"%{old}%",))
                if int(cur.fetchone()[0]) > 0:
                    conn.commit()
                    return True
            conn.commit()
    return False


def run_restore(backup_dir: str | Path, target_dsn: str,
                artifacts_dir: str | Path,
                workflow_target_dsn: str | None = None) -> dict:
    backup_dir = Path(backup_dir)
    artifacts_dir = Path(artifacts_dir)
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    source_db = manifest["source"]["database"]
    target_db = dbname_of(target_dsn)
    if target_db == source_db:
        raise SystemExit(
            f"refusing restore: target database {target_db!r} matches checkpoint source")
    if artifacts_dir.resolve() == Path(manifest["source"]["artifacts_root"]).resolve():
        raise SystemExit("refusing restore: artifact dir matches checkpoint source root")
    coordinated = bool((manifest.get("workflow") or {}).get("coordinated"))
    if coordinated and not workflow_target_dsn:
        raise SystemExit("refusing restore: checkpoint coordinates a workflow store but no"
                         " workflow target was given; pass --workflow-target-dsn")
    if workflow_target_dsn:
        if dbname_of(workflow_target_dsn) == (manifest.get("workflow") or {}).get("database"):
            raise SystemExit("refusing restore: workflow target matches checkpoint source")
        present = _check_workflow_fresh(workflow_target_dsn)
        if present:
            raise SystemExit(
                "refusing restore: workflow target not fresh:"
                f" workflow_status present in {present}")
    dirty = _check_fresh(target_dsn)
    if dirty:
        raise SystemExit(f"refusing restore: target not fresh: {DOMAIN_TABLE_GUARD} {dirty}")
    _restore_dump(backup_dir / f"{source_db}.dump", target_dsn)
    _extract_tar(backup_dir / "artifacts.tar", artifacts_dir)
    workflow: dict = {"coordinated": False}
    rebound_inputs = 0
    mismatches: list[str] = []
    if workflow_target_dsn:
        source_wf = f"{(manifest.get('workflow') or {}).get('database') or 'workflow'}.workflow.dump"
        if not (backup_dir / source_wf).is_file():
            raise SystemExit(f"refusing restore: coordinated workflow dump missing: {source_wf}")
        _restore_dump(backup_dir / source_wf, workflow_target_dsn)
        workflow = {"coordinated": True,
                    "target": dbname_of(workflow_target_dsn),
                    "kind": (manifest.get("workflow") or {}).get("kind", "unknown")}
        mismatches, rebound_inputs = _verify_restored_workflow(
            mismatches, manifest, workflow_target_dsn, target_dsn)
    counts = _target_rows(target_dsn)
    if sorted(counts) != sorted(manifest["row_counts"]):
        mismatches.append(
            f"tables differ: restored={sorted(counts)} manifest={sorted(manifest['row_counts'])}")
    for table, expected in manifest["row_counts"].items():
        if counts.get(table) != expected:
            mismatches.append(f"row count {table}: restored={counts.get(table)} manifest={expected}")
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(target_dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT name FROM schema_migrations ORDER BY name")
            restored_migrations = [r["name"] for r in cur.fetchall()]
            cur.execute("SELECT * FROM control WHERE id = 1")
            control = dict(cur.fetchone())
            cur.execute("SELECT id, dispatch_state FROM operations WHERE dispatch_state NOT IN"
                        " ('observed', 'reconciled', 'cancelled') ORDER BY id")
            unfinished = [dict(r) for r in cur.fetchall()]
            conn.commit()
    if restored_migrations != manifest["migrations"]:
        mismatches.append(
            f"migrations differ: restored={restored_migrations} manifest={manifest['migrations']}")
    for key, expected in manifest["control"].items():
        if control.get(key) != expected:
            mismatches.append(
                f"control {key}: restored={control.get(key)} manifest={expected}")
    for entry in manifest["artifacts"]:
        path = artifacts_dir / entry["path"]
        if not path.is_file():
            mismatches.append(f"artifact missing: {entry['path']}")
        elif path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
            mismatches.append(f"artifact digest mismatch: {entry['path']}")
    with tempfile.TemporaryDirectory(prefix="restore-diff-") as tmp:
        with tarfile.open(backup_dir / "artifacts.tar", "r") as tar:
            tar.extractall(tmp, filter="data")
        hashed = sorted(str(p.relative_to(tmp)) for p in Path(tmp).rglob("*") if p.is_file())
        expected = sorted(e["path"] for e in manifest["artifacts"])
        if hashed != expected:
            mismatches.append("artifact tar contents differ from manifest")
    from settlement import store as _store
    if "continuations" in manifest.get("barrier", {}):
        for item in _store.checkpoint_verify(target_dsn, manifest["barrier"]):
            mismatches.append(f"restored domain: {item}")
    workflow["rebound_inputs"] = rebound_inputs
    ok = not mismatches
    fence: dict = {}
    if ok:
        from settlement.common import Command as _Command
        fenced = _store.restore_fence(
            target_dsn, _Command(
                request_id=f"restore-fence-{source_db}-{manifest['source']['commit']}",
                payload={"reason": "restore", "source_commit": manifest["source"]["commit"],
                         "source_database": source_db}))
        if fenced.code.value != "applied":
            mismatches.append(f"fence not established: {fenced.detail}")
            ok = False
        else:
            fence = fenced.data
    return {"ok": ok, "mismatches": mismatches,
            "unfinished_operations": unfinished, "fence": fence,
            "workflow": workflow,
            "note": ("dispatch stays paused until resume_dispatch after explicit reconciliation;"
                     " reconcile unfinished operations against launchers/providers (REC-4),"
                     " never replay them as new commands") if unfinished else
            "dispatch stays paused until resume_dispatch after explicit reconciliation"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--target-dsn", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--workflow-target-dsn", default=None)
    args = parser.parse_args(argv)
    report = run_restore(args.backup_dir, args.target_dsn, args.artifacts_dir,
                         args.workflow_target_dsn)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
