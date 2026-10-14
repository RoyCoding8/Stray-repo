"""Immutable references from P01 observations into revisioned learner memory.

Development task packages intentionally carry the evaluator access label because
they contain pristine tests and references. This module verifies that package
against the trusted development-task registry, but renders only its instruction.
Solution and trajectory artifacts must be public or candidate-visible; their
bytes are verified without rendering their contents.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from psycopg.rows import dict_row

from settlement import artifacts, db, store
from settlement.common import Command, ResultCode, SettlementError

_LEARNER_ARTIFACT_LABELS = {"public", "candidate"}
_TASK_ARTIFACT_LABELS = _LEARNER_ARTIFACT_LABELS | {"evaluator"}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _revision(cur) -> int:
    cur.execute("SELECT revision FROM rsi_memory_clock WHERE id = 1")
    row = cur.fetchone()
    if row is None:
        raise SettlementError("memory revision clock is unavailable")
    return int(row["revision"] if isinstance(row, dict) else row[0])


def _next_revision(cur) -> int:
    cur.execute("INSERT INTO rsi_memory_clock (id, revision) VALUES (1, 0)"
                " ON CONFLICT (id) DO NOTHING")
    cur.execute("SELECT revision FROM rsi_memory_clock WHERE id = 1 FOR UPDATE")
    row = cur.fetchone()
    if row is None:
        raise SettlementError("memory revision clock is unavailable")
    current = int(row["revision"] if isinstance(row, dict) else row[0])
    revision = current + 1
    cur.execute("UPDATE rsi_memory_clock SET revision = %s WHERE id = 1", (revision,))
    return revision


def _artifact(cur, digest: str, *, expected_scope: str,
              allowed_labels: set[str]) -> dict:
    if not isinstance(digest, str) or len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest):
        raise SettlementError("experience source has an invalid artifact reference")
    cur.execute("SELECT digest, scope, access_label, availability, manifest"
                " FROM artifact_versions WHERE digest = %s", (digest,))
    row = cur.fetchone()
    if (row is None or row["scope"] != expected_scope
            or row["access_label"] not in allowed_labels
            or row["availability"] != "available"):
        raise SettlementError("experience source has protected or unavailable artifact ancestry")
    return dict(row)


def _task_instruction(dsn: str, artifacts_root: str | Path, digest: str,
                      task_row: dict, artifact_row: dict) -> str:
    if not artifacts.artifact_available(dsn, artifacts_root, digest):
        raise SettlementError("development task bytes are unavailable")
    try:
        raw = (Path(artifacts_root) / digest).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("digest mismatch")
        package = json.loads(raw)
        if (not isinstance(package, dict)
                or set(package) != {"manifest", "scope", "files"}
                or package["scope"] != "rsi-task"
                or not isinstance(package["manifest"], dict)
                or not isinstance(package["files"], dict)):
            raise ValueError("invalid task package")
        manifest = package["manifest"]
        if (manifest.get("kind") != "rsi-task"
                or manifest.get("split") != "dev"
                or manifest.get("split") != task_row["split"]
                or manifest.get("name") != task_row["name"]
                or manifest.get("evaluator_version") != task_row["evaluator_version"]
                or artifact_row["access_label"] not in _TASK_ARTIFACT_LABELS):
            raise ValueError("task registry mismatch")
        files = package["files"]
        if any(not isinstance(name, str) or not isinstance(encoded, str)
               for name, encoded in files.items()):
            raise ValueError("invalid task files")
        decoded = {name: bytes.fromhex(encoded) for name, encoded in files.items()}
        if any(value.hex() != files[name] for name, value in decoded.items()):
            raise ValueError("noncanonical task file bytes")
        if artifacts.package_bytes(manifest, decoded, "rsi-task") != raw:
            raise ValueError("noncanonical task package")
        instruction = manifest.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("missing public task instruction")
        return instruction
    except (OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
        raise SettlementError("development task package failed provenance validation") from exc


def _source(cur, dsn: str, artifacts_root: str | Path, observation_id: int,
            *, verify_refs: bool = True) -> dict:
    cur.execute(
        "SELECT ao.id AS observation_id, ao.attempt_id, ao.decision_id, ao.content AS observation,"
        " a.investigation_id, s.domain, s.config, d.subject AS decision_subject, d.kind AS decision_kind,"
        " d.data AS decision, d.data->>'operation_id' AS worker_operation_id,"
        " e.operation_id AS episode_id, e.status AS episode_status, e.task AS episode_task,"
        " e.trajectory AS trajectory_digest, t.digest AS task_digest, t.name AS task_name,"
        " t.split AS task_split, t.evaluator_version, v.operation_id AS verifier_operation_id,"
        " v.solution AS solution_digest, v.status AS verifier_status, v.passed AS verifier_passed"
        " FROM attempt_observations ao"
        " JOIN attempts a ON a.id = ao.attempt_id"
        " JOIN rsi_investigations s ON s.investigation_id = a.investigation_id"
        " JOIN rsi_decisions d ON d.id = ao.decision_id"
        " JOIN rsi_tasks t ON t.digest = s.config->>'task'"
        " LEFT JOIN rsi_episodes e ON e.operation_id = d.data->>'operation_id'"
        " LEFT JOIN rsi_verdicts v ON v.episode = e.operation_id"
        " AND v.operation_id = ao.content->>'verdict'"
        " AND v.evaluator_version = t.evaluator_version"
        " WHERE ao.id = %s",
        (observation_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise SettlementError("observation is not a canonical P01 development-task record")
    source = dict(row)
    observation = dict(source["observation"] or {})
    decision = dict(source["decision"] or {})
    config = dict(source["config"] or {})
    status = observation.get("status")
    passed = observation.get("passed")
    checked = source["verifier_status"] in ("passed", "failed")
    if (source["domain"] != "task" or source["task_split"] != "dev"
            or source["decision_subject"] != source["investigation_id"]
            or source["decision_kind"] != "worker"
            or decision.get("attempt_id") != source["attempt_id"]
            or decision.get("operation_id") != source["worker_operation_id"]
            or config.get("task") != source["task_digest"]
            or observation.get("episode") != source["worker_operation_id"]
            or source["episode_id"] not in (None, source["worker_operation_id"])
            or source["episode_task"] not in (None, source["task_digest"])):
        raise SettlementError("observation failed P01 source identity validation")
    if checked:
        if (source["episode_id"] is None
                or source["verifier_status"] not in ("passed", "failed")
                or source["verifier_passed"] is not (source["verifier_status"] == "passed")
                or observation.get("verdict") != source["verifier_operation_id"]
                or observation.get("solution") != source["solution_digest"]
                or status != source["verifier_status"]
                or passed is not source["verifier_passed"]):
            raise SettlementError("observation failed checked P01 outcome validation")
    elif source["verifier_operation_id"] is not None:
        if (source["episode_id"] is None
                or source["verifier_status"] not in ("timeout", "infra_failed")
                or status != source["verifier_status"] or passed is not None
                or observation.get("verdict") != source["verifier_operation_id"]
                or observation.get("solution") != source["solution_digest"]):
            raise SettlementError("observation failed unresolved-verifier validation")
    elif (status not in ("refused", "unresolved", "failed", "infra_failed", "timeout",
                         "over_budget")
          or passed is not None or observation.get("verdict") is not None
          or observation.get("solution") is not None
          or (status != "refused" and (source["episode_id"] is None
                                      or status != source["episode_status"]))):
        raise SettlementError("observation failed P01 uncertainty validation")

    task_artifact = _artifact(cur, source["task_digest"], expected_scope="rsi-task",
                              allowed_labels=_TASK_ARTIFACT_LABELS)
    task_row = {"name": source["task_name"], "split": source["task_split"],
                "evaluator_version": source["evaluator_version"]}
    instruction = _task_instruction(dsn, artifacts_root, source["task_digest"],
                                    task_row, task_artifact)
    artifact_rows = [("task", source["task_digest"], task_artifact)]
    if source["trajectory_digest"] is not None:
        trajectory_artifact = _artifact(cur, source["trajectory_digest"],
                                         expected_scope="rsi-trajectory",
                                         allowed_labels=_LEARNER_ARTIFACT_LABELS)
        artifact_rows.append(("trajectory", source["trajectory_digest"], trajectory_artifact))
    if source["solution_digest"] is not None:
        solution_artifact = _artifact(cur, source["solution_digest"], expected_scope="rsi-solution",
                                      allowed_labels=_LEARNER_ARTIFACT_LABELS)
        if dict(solution_artifact["manifest"] or {}).get("task") != source["task_digest"]:
            raise SettlementError("solution artifact has protected or unrelated ancestry")
        artifact_rows.append(("solution", source["solution_digest"], solution_artifact))
    artifact_digests = [digest for _kind, digest, _row in artifact_rows]
    if verify_refs:
        for _kind, digest, _artifact_row in artifact_rows:
            if not artifacts.artifact_available(dsn, artifacts_root, digest):
                raise SettlementError("experience source artifact bytes are unavailable")

    scope = {"domain": "task", "task": source["task_digest"]}
    identities = {
        "decision_id": source["decision_id"],
        "attempt_id": source["attempt_id"],
        "worker_operation_id": source["worker_operation_id"],
        "task_digest": source["task_digest"],
        "evaluator_version": source["evaluator_version"],
        "verifier_operation_id": source["verifier_operation_id"],
    }
    canonical = {
        "observation_id": int(source["observation_id"]),
        "identities": identities,
        "scope": scope,
        "observation_digest": _digest(source["observation"]),
        "artifacts": artifact_digests,
        "access_labels": [artifact_row["access_label"] for _, _, artifact_row in artifact_rows],
        "instruction_digest": _digest(instruction),
        "status": status,
        "passed": passed,
    }
    return {
        "observation_id": int(source["observation_id"]),
        "investigation_id": source["investigation_id"],
        "decision_id": source["decision_id"],
        "attempt_id": source["attempt_id"],
        "operation_id": source["worker_operation_id"],
        "task_digest": source["task_digest"],
        "evaluator_version": source["evaluator_version"],
        "verifier_operation_id": source["verifier_operation_id"],
        "artifact_digests": artifact_digests,
        "artifact_refs": [{"kind": kind, "digest": digest}
                          for kind, digest, _artifact_row in artifact_rows],
        "scope": scope,
        "visibility": "learner",
        "instruction": instruction,
        "status": status,
        "passed": passed,
        "source_digest": _digest(canonical),
    }


def _captured(cur, source: dict) -> dict:
    cur.execute("SELECT observation_id, revision, source_digest, scope, visibility"
                " FROM rsi_memory_experiences WHERE observation_id = %s",
                (source["observation_id"],))
    existing = cur.fetchone()
    if existing is not None:
        record = dict(existing)
        if (record["source_digest"] != source["source_digest"]
                or dict(record["scope"] or {}) != source["scope"]
                or record["visibility"] != source["visibility"]):
            raise SettlementError("captured observation source changed")
        return {**record, "scope": dict(record["scope"] or {})}
    revision = _next_revision(cur)
    cur.execute("INSERT INTO rsi_memory_experiences"
                " (observation_id, revision, source_digest, scope, visibility)"
                " VALUES (%s, %s, %s, %s, %s)"
                " RETURNING observation_id, revision, source_digest, scope, visibility",
                (source["observation_id"], revision, source["source_digest"],
                 json.dumps(source["scope"], sort_keys=True), source["visibility"]))
    result = dict(cur.fetchone())
    result["scope"] = dict(result["scope"] or {})
    return result


def capture(dsn: str, observation_id: int, *, artifacts_root: str | Path) -> dict:
    if isinstance(observation_id, bool) or not isinstance(observation_id, int) or observation_id < 1:
        raise SettlementError("observation_id must be a positive integer")
    source_payload = {"observation_id": observation_id}

    def _fn(cur, _control):
        source = _source(cur, dsn, artifacts_root, observation_id)
        result = _captured(cur, source)
        return (ResultCode.APPLIED, "experience reference captured", result,
                [("rsi.memory.experience-captured", {"observation_id": observation_id,
                                                       "revision": result["revision"]})], [])

    result = store.transact(
        dsn, Command(request_id=f"rsi-memory-capture:{observation_id}",
                     payload=source_payload), _fn)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        current = _source(cur, dsn, artifacts_root, observation_id)
        captured = _captured_read(cur, observation_id)
        conn.commit()
    if (captured is None or captured["source_digest"] != current["source_digest"]
            or dict(captured["scope"] or {}) != current["scope"]):
        raise SettlementError("captured observation source changed")
    return captured


def _captured_read(cur, observation_id: int) -> dict | None:
    cur.execute("SELECT observation_id, revision, source_digest, scope, visibility"
                " FROM rsi_memory_experiences WHERE observation_id = %s",
                (observation_id,))
    row = cur.fetchone()
    if row is None:
        return None
    result = dict(row)
    result["scope"] = dict(result["scope"] or {})
    return result


def capture_investigation(dsn: str, investigation_id: str, *,
                          artifacts_root: str | Path) -> list[dict]:
    with db.read_connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT ao.id FROM attempt_observations ao"
                    " JOIN attempts a ON a.id = ao.attempt_id"
                    " WHERE a.investigation_id = %s AND ao.decision_id IS NOT NULL"
                    " ORDER BY ao.id",
                    (investigation_id,))
        ids = [int(row[0]) for row in cur.fetchall()]
        conn.commit()
    return [capture(dsn, observation_id, artifacts_root=artifacts_root)
            for observation_id in ids]


def _visible_artifact(dsn: str, artifacts_root: str | Path, digest: str,
                      *, expected_scope: str, task: bool = False) -> tuple[bool, str]:
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT scope, access_label, availability, manifest"
                    " FROM artifact_versions WHERE digest = %s", (digest,))
        row = cur.fetchone()
        conn.commit()
    allowed = _TASK_ARTIFACT_LABELS if task else _LEARNER_ARTIFACT_LABELS
    if row is None or row["scope"] != expected_scope or row["access_label"] not in allowed:
        return False, "protected or unregistered artifact provenance"
    if row["availability"] != "available" or not artifacts.artifact_available(
            dsn, artifacts_root, digest):
        return False, "artifact bytes are missing or changed"
    return True, ""


def resolve(dsn: str, observation_ids: Iterable[int], *, artifacts_root: str | Path,
            revision: int | None = None, visibility: str = "learner") -> dict:
    if visibility != "learner":
        raise SettlementError("unsupported memory visibility")
    ids = list(observation_ids)
    if len(ids) > 256 or any(isinstance(item, bool) or not isinstance(item, int) or item < 1
                             for item in ids):
        raise SettlementError("observation_ids must contain at most 256 positive integers")
    if len(set(ids)) != len(ids):
        raise SettlementError("observation_ids must be distinct")

    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        current_revision = _revision(cur)
        selected_revision = current_revision if revision is None else revision
        if (isinstance(selected_revision, bool) or not isinstance(selected_revision, int)
                or selected_revision < 0 or selected_revision > current_revision):
            raise SettlementError("requested memory revision is unavailable")
        cur.execute("SELECT observation_id, revision, source_digest, scope, visibility"
                    " FROM rsi_memory_experiences WHERE revision <= %s"
                    " AND visibility = 'learner' AND observation_id = ANY(%s)"
                    " ORDER BY revision, observation_id",
                    (selected_revision, ids))
        records = [dict(row) for row in cur.fetchall()]
        conn.commit()
    by_id = {int(record["observation_id"]): record for record in records}
    observations = []
    missing = []
    for observation_id in ids:
        record = by_id.get(observation_id)
        if record is None:
            missing.append({"observation_id": observation_id,
                            "reason": "not captured at requested memory revision"})
            continue
        try:
            with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
                source = _source(cur, dsn, artifacts_root, observation_id,
                                 verify_refs=False)
                conn.commit()
            if (source["source_digest"] != record["source_digest"]
                    or source["scope"] != dict(record["scope"] or {})
                    or record["visibility"] != "learner"):
                raise SettlementError("captured source changed")
        except SettlementError:
            missing.append({"observation_id": observation_id,
                            "reason": "captured source is unavailable or changed"})
            continue

        refs_by_digest = {
            "task": ("rsi-task", True),
            "trajectory": ("rsi-trajectory", False),
            "solution": ("rsi-solution", False),
        }
        missing_refs = []
        for ref in source["artifact_refs"]:
            kind, digest = ref["kind"], ref["digest"]
            scope_name, is_task = refs_by_digest[kind]
            available, reason = _visible_artifact(
                dsn, artifacts_root, digest, expected_scope=scope_name, task=is_task)
            if not available:
                missing_refs.append({"kind": kind, "digest": digest, "reason": reason})
        if missing_refs:
            missing.append({"observation_id": observation_id,
                            "reason": "one or more source artifacts are unavailable",
                            "artifacts": missing_refs})
            continue
        observations.append({
            "observation_id": observation_id,
            "investigation_id": source["investigation_id"],
            "scope": source["scope"],
            "visibility": "learner",
            "content": {"task_instruction": source["instruction"],
                        "status": source["status"], "passed": source["passed"]},
            "artifacts": source["artifact_digests"],
            "identities": {
                "decision_id": source["decision_id"],
                "attempt_id": source["attempt_id"],
                "worker_operation_id": source["operation_id"],
                "task_digest": source["task_digest"],
                "evaluator_version": source["evaluator_version"],
                "verifier_operation_id": source["verifier_operation_id"],
            },
        })
    return {"revision": selected_revision, "observations": observations,
            "missing_information": missing}
