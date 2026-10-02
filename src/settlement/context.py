"""S2 context views and durable continuation (RUN-2, RUN-5).

A context view names its decision, source versions, transformations,
governing references and unresolved limitations. A continuation document
carries composition version, position, completed refs, unresolved operation
ids, obligations and the next decision; it is stored as an immutable artifact
and installed via the store so a fresh worker resumes with no shared memory.

Hidden-evaluation boundary: retrieval filters by caller scope in SQL. A table
name is not isolation; the access-label predicate below is the enforcement
point reused by the broker and store, and candidate builders cannot remove it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import artifacts, db, evidence, store
from .common import Command, CommandResult, ResultCode, SettlementError, new_id

_LATEST_VERSION = 1


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def build_context(dsn: str, cmd: Command, decision: dict, source_refs: list[dict],
                  transforms: list[dict] | None = None, governing_refs: list[str] | None = None,
                  limitations: list[str] | None = None, caller_scope: str = "public",
                  mandatory: list[str] | None = None) -> CommandResult:
    mandatory = list(mandatory or [])
    visible_claims = {row["id"] for row in evidence.scoped_claims(dsn, caller_scope)}
    visible_digests = {row["digest"] for row in artifacts.scoped_artifacts(dsn, caller_scope)}
    missing = [key for key in mandatory if key not in decision or decision[key] in (None, "", [])]
    withheld: list[str] = []
    kept: list[dict] = []
    for ref in source_refs:
        target = ref.get("claim_id") or ref.get("digest") or ""
        if ref.get("claim_id") and target not in visible_claims:
            withheld.append(target)
        elif ref.get("digest") and target not in visible_digests:
            withheld.append(target)
        else:
            kept.append(ref)
    staged = bool(missing or withheld)

    def _fn(cur, control):
        view_id = f"ctx_{cmd.request_id}"
        cur.execute("INSERT INTO context_views (id, decision, sources, transforms,"
                    " governing_refs, limitations, staged, version)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (view_id, _j(decision), _j(kept), _j(transforms or []),
                     _j(governing_refs or []),
                     _j(list(limitations or []) + (["missing: " + m for m in missing])
                         + (["withheld: " + w for w in withheld])),
                     staged, _LATEST_VERSION))
        data: dict[str, Any] = {"view_id": view_id, "version": _LATEST_VERSION, "staged": staged,
                                "sources": kept, "missing": missing, "withheld": withheld}
        if missing:
            data["narrowed_decision"] = {k: v for k, v in decision.items() if k not in missing}
        return (ResultCode.APPLIED, "staged context" if staged else "context built", data,
                [("context.built", {"view_id": view_id, "staged": staged})], [])
    return store.transact(dsn, cmd, _fn)


def save_continuation(dsn: str, cmd: Command, artifacts_root: str | Path, investigation_id: str,
                      attempt_id: str, composition_version: str, position: dict,
                      completed_refs: list, unresolved_ops: list[str], obligations: dict,
                      next_decision: dict, ownership_generation: int | None = None) -> CommandResult:
    doc = {"investigation_id": investigation_id, "composition_version": composition_version,
           "position": position, "completed_refs": completed_refs,
           "unresolved_ops": list(unresolved_ops), "obligations": obligations,
           "next_decision": next_decision}
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    roots = Path(artifacts_root)
    roots.mkdir(parents=True, exist_ok=True)
    target = roots / digest
    created = False
    if not target.is_file():
        tmp = roots / (digest + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(tmp, target)
        fd = os.open(roots, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        created = True

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM investigations WHERE id = %s", (investigation_id,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown investigation {investigation_id}")
        cur.execute("INSERT INTO artifact_versions (digest, size, manifest, format, version,"
                    " availability, scope, path) VALUES (%s, %s, %s, 'continuation', %s,"
                    " 'available', %s, %s) ON CONFLICT (digest) DO NOTHING",
                    (digest, len(raw), _j({"continuation": investigation_id}),
                     composition_version, investigation_id, digest))
        cur.execute("INSERT INTO continuation_docs (id, investigation_id, composition_version,"
                    " position, completed_refs, unresolved_ops, obligations, next_decision)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (id) DO UPDATE SET position = EXCLUDED.position,"
                    " completed_refs = EXCLUDED.completed_refs,"
                    " unresolved_ops = EXCLUDED.unresolved_ops, obligations = EXCLUDED.obligations,"
                    " next_decision = EXCLUDED.next_decision",
                    (digest, investigation_id, composition_version, _j(position),
                     _j(completed_refs), _j(list(unresolved_ops)), _j(obligations),
                     _j(next_decision)))
        cur.execute("SELECT id, lifecycle, ownership_generation FROM attempts WHERE id = %s",
                    (attempt_id,))
        attempt = cur.fetchone()
        if attempt is None:
            raise SettlementError(f"unknown attempt {attempt_id}")
        if attempt["lifecycle"] in ("completed", "failed", "cancelled"):
            raise SettlementError(f"attempt {attempt_id} is {attempt['lifecycle']}")
        if ownership_generation is not None and int(ownership_generation) != int(
                attempt["ownership_generation"]):
            raise SettlementError(f"attempt {attempt_id} owned by generation"
                                  f" {attempt['ownership_generation']}")
        cur.execute("UPDATE attempts SET continuation_ref = %s, updated_at = now() WHERE id = %s",
                    (digest, attempt_id))
        return (ResultCode.APPLIED, "continuation stored and installed",
                {"continuation_id": digest, "attempt_id": attempt_id},
                [("work.continued", {"attempt_id": attempt_id}),
                 ("artifact.published", {"digest": digest})], [])
    result = store.transact(dsn, cmd, _fn)
    if created and result.code != ResultCode.APPLIED:
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM artifact_versions WHERE digest = %s", (digest,))
                orphan = cur.fetchone() is None
                conn.commit()
        if orphan:
            try:
                target.unlink()
            except OSError:
                pass
    return result


def resume_package(dsn: str, investigation_id: str, caller_scope: str = "evaluator") -> dict:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM continuation_docs WHERE investigation_id = %s"
                        " ORDER BY created_at DESC LIMIT 1", (investigation_id,))
            row = cur.fetchone()
            if row is None:
                raise SettlementError(f"no continuation for {investigation_id}")
            doc = {k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
                   for k, v in dict(row).items()}
            cur.execute("SELECT id FROM attempts WHERE investigation_id = %s"
                        " AND lifecycle NOT IN ('completed', 'failed', 'cancelled')", (investigation_id,))
            live = [r["id"] for r in cur.fetchall()]
            cur.execute("SELECT id FROM attempts WHERE investigation_id = %s", (investigation_id,))
            every = [r["id"] for r in cur.fetchall()]
            cur.execute("SELECT attempt_id, content FROM attempt_observations WHERE attempt_id = ANY(%s)"
                        " ORDER BY id", (every or ["~none"],))
            observations = [{"attempt_id": r["attempt_id"],
                               "content": dict((r["content"] or {}).get("content", r["content"] or {}))}
                            for r in cur.fetchall()]
            conn.commit()
    reconciliation = store.restart_reconciliation(dsn)
    pending = [op for op in reconciliation["unfinished_operations"]
               if op["id"] in set(doc["unresolved_ops"])
               or (live and op.get("attempt_id") in live)]
    support = {row["id"]: evidence.current_support(dsn, row["id"]) for row in
               evidence.scoped_claims(dsn, caller_scope)}
    return {"continuation": doc, "live_attempts": live, "pending_operations": pending,
            "observations": observations, "support": support,
            "reconciliation": {"execution_versions": reconciliation["execution_versions"]}}
