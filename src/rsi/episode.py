"""Episode: one budgeted, recorded run of a genome on a task.

The run is a kernel ``agent-run`` operation, so it is admitted against an
allocation, sent at most once, and settled with its real token cost. The
trajectory (the harness's event log) becomes an artifact; ``rsi_episodes``
links operation, genome, task and trajectory.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from settlement import artifacts, broker, db, store
from settlement.common import Command, ResultCode, SettlementError

from . import capability as c
from . import genome as g
from . import task as t

TRAJECTORY_SCOPE = "rsi-trajectory"
TERMINAL = ("observed", "reconciled")
SOLUTION_SCOPE = "rsi-solution"
CONTINUATION_MAX_BYTES = 64 * 1024


@dataclass(frozen=True)
class Episode:
    operation_id: str
    genome: str
    task: str
    status: str
    tokens: Mapping[str, int] | None
    seconds: float
    trajectory: str
    workspace: Path
    infra_reason: str = ""


class EpisodeError(SettlementError):
    pass


def run_episode(dsn: str, launcher: Any, genome: g.Genome, *, operation_id: str,
                task: t.Task,
                allocation_id: str, attempt_id: str | None, timeout_ms: int,
                token_ceiling: int, staging_root: str | Path, artifacts_root: str | Path,
                continuation: dict | None = None, solution: str | None = None,
                ownership_generation: int | None = None) -> Episode:
    """Run `genome` on a task once. Calling again with the same id returns the record."""
    task = t.load(dsn, artifacts_root, task.digest)
    known = read_episode(dsn, operation_id, launcher)
    if known is not None and (known.genome, known.task) != (genome.digest, task.digest):
        raise EpisodeError("operation id already belongs to another genome or task")

    solution_files = _read_solution(dsn, artifacts_root, task, solution)
    files = {**task.workspace, **solution_files}
    view = g.workspace_view(genome)
    paths = [rel.casefold() for rel in (*view, *files)]
    unique = set(paths)
    if len(paths) != len(unique) or any(
            "/".join(rel.split("/")[:i]) in unique
            for rel in unique for i in range(1, len(rel.split("/")))):
        raise EpisodeError("task files collide with genome files")

    staged = {**files, **view}
    instruction = _instruction(task.instruction, continuation, staged,
                                include_digest=continuation is not None or solution is not None)
    payload = {"harness": genome.harness, "genome": genome.digest, "task": task.digest,
               "instruction": instruction, "config": g.settings(genome),
               "timeout_ms": timeout_ms, "token_ceiling": token_ceiling}
    existing = broker.read_operation(dsn, operation_id)
    if known is not None:
        if existing is None:
            raise EpisodeError("recorded episode has no admitted operation")
        recorded = existing.get("payload") or {}
        if recorded.get("effect") != broker.AGENT_RUN or recorded.get("payload") != payload:
            raise EpisodeError("operation id already belongs to different input")
    elif existing is None:
        for rel, raw in staged.items():
            launcher.stage_input(operation_id, "", rel, raw)
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.AGENT_RUN,
        payload=payload,
        allocation_id=allocation_id, attempt_id=attempt_id)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise EpisodeError(f"agent-run not admitted: {ensured.detail}")
    if known is not None:
        return known
    status = broker.dispatch_operation(dsn, operation_id,
                                       launchers={launcher.profile: launcher},
                                       ownership_generation=ownership_generation)
    if status.dispatch_state not in TERMINAL:
        raise EpisodeError(f"agent-run {operation_id} not settled:"
                           f" {status.dispatch_state} {status.next_decision}")
    result = launcher.read_result(operation_id)
    if result is None:
        raise EpisodeError(f"agent-run {operation_id} settled without a launcher result: {status.next_decision}")
    raw = launcher.read_output(operation_id, "", "events.jsonl")
    if hashlib.sha256(raw).hexdigest() != result["trajectory_digest"]:
        raise EpisodeError(f"trajectory of {operation_id} changed after the run")
    trajectory = _publish_trajectory(dsn, raw, staging_root, artifacts_root,
                                     "hidden" if task.split == "anchor" else "candidate")

    def _fn(cur, control):
        artifacts._add_reference(cur, trajectory, "attempt", "rsi-episode:" + operation_id)
        cur.execute("INSERT INTO rsi_episodes (operation_id, genome, task, status, tokens,"
                    " seconds, trajectory) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (operation_id) DO NOTHING",
                    (operation_id, genome.digest, task.digest, result["status"],
                     Json(result["tokens"]) if result["tokens"] is not None else None,
                     float(result["seconds"]), trajectory))
        return (ResultCode.APPLIED, "episode recorded", {"operation_id": operation_id},
                [("rsi.episode", {"operation_id": operation_id, "status": result["status"]})], [])
    store.transact(dsn, Command(request_id=f"rsi-episode-{operation_id}",
                                payload={"operation_id": operation_id}), _fn)
    found = read_episode(dsn, operation_id, launcher)
    if found is None:
        raise EpisodeError(f"episode {operation_id} was not recorded")
    return found


def run_method_episode(dsn: str, launcher: Any, genome: g.Genome, *, name: str,
                       request: dict, operation_id: str, task: t.Task,
                       allocation_id: str, attempt_id: str | None,
                       staging_root: str | Path, artifacts_root: str | Path,
                       timeout_ms: int | None = None,
                       ownership_generation: int | None = None) -> Episode:
    """Run a genome method once and record it as a native, zero-token episode."""
    task = t.load(dsn, artifacts_root, task.digest)
    _validate_method_request_files(request, task)

    # invoke owns the broker operation and returns its immutable result on replay.
    # The child sees context as {continuation, task_digest}; binding the canonical
    # task here prevents a pre-episode-row replay from changing verifier identity.
    method_request = {**request, "context": {
        "continuation": request["context"], "task_digest": task.digest}}
    invocation = c.invoke(
        dsn, launcher, genome, name, method_request, operation_id=operation_id,
        allocation_id=allocation_id, attempt_id=attempt_id,
        staging_root=staging_root, artifacts_root=artifacts_root,
        timeout_ms=timeout_ms,
        ownership_generation=ownership_generation)
    if invocation.genome != genome.digest or invocation.name != name:
        raise EpisodeError("method invocation identity disagrees with its request")
    if invocation.status == "completed":
        _write_method_outputs(launcher, invocation, task)

    known = read_episode(dsn, operation_id, launcher)
    if known is not None:
        if (known.genome, known.task) != (genome.digest, task.digest):
            raise EpisodeError("operation id already belongs to another genome or task")
        return known

    raw = _method_trajectory(invocation, task, allocation_id, attempt_id)
    trajectory = _publish_trajectory(
        dsn, raw, staging_root, artifacts_root,
        "hidden" if task.split == "anchor" else "candidate", format="native-jsonl")

    def record(cur, control):
        artifacts._add_reference(cur, trajectory, "attempt", "rsi-episode:" + operation_id)
        cur.execute("INSERT INTO rsi_episodes (operation_id, genome, task, status, tokens,"
                    " seconds, trajectory) VALUES (%s, %s, %s, %s, NULL, %s, %s)"
                    " ON CONFLICT (operation_id) DO NOTHING",
                    (operation_id, genome.digest, task.digest, invocation.status,
                     float(invocation.seconds), trajectory))
        return (ResultCode.APPLIED, "method episode recorded", {"operation_id": operation_id},
                [("rsi.episode", {"operation_id": operation_id,
                                  "status": invocation.status, "kind": "method"})], [])
    result = store.transact(dsn, Command(request_id=f"rsi-method-episode-{operation_id}",
                                         payload={"operation_id": operation_id}), record)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise EpisodeError(result.detail)
    found = read_episode(dsn, operation_id, launcher)
    if found is None:
        raise EpisodeError(f"method episode {operation_id} was not recorded")
    # The broker result is durable, and Invocation.detail is the method runner's
    # bounded status detail. Preserve it for the call that first records the row.
    infra_reason = str(invocation.detail) if invocation.status == "infra_failed" else ""
    return Episode(**{**found.__dict__, "infra_reason": infra_reason})


def _validate_method_request_files(request: dict, task: t.Task) -> None:
    if not isinstance(request, dict) or set(request) != {"interface", "value", "files", "context"}:
        raise EpisodeError("method request must contain interface, value, files and context")
    files = request["files"]
    if not isinstance(files, Mapping) or set(files) - set(task.workspace):
        raise EpisodeError("method request files must use task workspace slots")
    for slot, content in files.items():
        if not isinstance(content, str):
            raise EpisodeError(f"method request file {slot!r} must be UTF-8 text")
        try:
            content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise EpisodeError(f"method request file {slot!r} is not valid UTF-8") from exc


def _write_method_outputs(launcher: Any, invocation: Any, task: t.Task) -> Path:
    _, output_dir = launcher.exec_dirs(invocation.operation_id, invocation.execution_version)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    files = dict(invocation.files)
    if set(files) - set(task.workspace):
        raise EpisodeError("method returned a file outside the task workspace")
    if any(not isinstance(raw, bytes) for raw in files.values()):
        raise EpisodeError("method returned invalid solution bytes")

    # Clear declared slots first so a replay cannot inherit files from a prior
    # workspace state when the immutable invocation omitted one.
    for rel in task.workspace:
        dest = root.joinpath(*rel.split("/"))
        _check_method_path(root, dest)
        if dest.is_symlink():
            raise EpisodeError(f"method output {rel!r} is a link")
        if dest.exists():
            if not dest.is_file():
                raise EpisodeError(f"method output {rel!r} is not a regular file")
            dest.unlink()
    for rel, raw in sorted(files.items()):
        dest = root.joinpath(*rel.split("/"))
        _check_method_path(root, dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _check_method_path(root, dest)
        dest.write_bytes(raw)
    return root


def _check_method_path(root: Path, dest: Path) -> None:
    try:
        dest.relative_to(root)
    except ValueError as exc:
        raise EpisodeError("method output path escapes its workspace") from exc
    current = root
    for part in dest.relative_to(root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise EpisodeError("method output path contains a link")


def _method_trajectory(invocation: Any, task: t.Task, allocation_id: str,
                       attempt_id: str | None) -> bytes:
    event = {
        "type": "method.invocation.result",
        "operation_id": invocation.operation_id,
        "genome": invocation.genome,
        "task": task.digest,
        "name": invocation.name,
        "method_digest": invocation.method_digest,
        "input_digest": invocation.input_digest,
        "output_digest": invocation.output_digest,
        "execution_version": invocation.execution_version,
        "allocation_id": allocation_id,
        "attempt_id": attempt_id,
        "status": invocation.status,
        "value": invocation.value,
        "files": [{"slot": slot, "size": len(raw),
                   "digest": hashlib.sha256(raw).hexdigest()}
                  for slot, raw in invocation.files],
        "seconds": invocation.seconds,
        "detail": invocation.detail,
    }
    try:
        return (json.dumps(event, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise EpisodeError(f"method result is not canonical JSON: {exc}") from exc


def _instruction(base: str, continuation: dict | None, files: Mapping[str, bytes], *,
                 include_digest: bool) -> str:
    if continuation is None and not include_digest:
        return base
    parts = [base]
    if continuation is not None:
        if not isinstance(continuation, dict) or not _is_json_value(continuation):
            raise EpisodeError("continuation must be a JSON object")
        try:
            encoded = json.dumps(continuation, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False)
            raw = encoded.encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise EpisodeError(f"continuation must be canonical JSON: {exc}") from exc
        if len(raw) > CONTINUATION_MAX_BYTES:
            raise EpisodeError("continuation exceeds 65536 bytes")
        parts.append("Continuation (JSON):\n" + encoded)
    if include_digest:
        manifest = [{"path": rel, "size": len(raw),
                     "digest": hashlib.sha256(raw).hexdigest()}
                    for rel, raw in sorted(files.items())]
        digest = hashlib.sha256(json.dumps(
            manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        parts.append("Input digest: " + digest)
    return "\n\n".join(parts)


def _is_json_value(value: Any) -> bool:
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    return value is None or type(value) in (str, int, float, bool)


def _read_solution(dsn: str, artifacts_root: str | Path, task: t.Task,
                   solution: str | None) -> dict[str, bytes]:
    if solution is None:
        return {}
    if (not isinstance(solution, str) or len(solution) != 64
            or any(c not in "0123456789abcdef" for c in solution)):
        raise EpisodeError("solution must be a lowercase SHA-256 digest")
    path = Path(artifacts_root) / solution
    try:
        if path.is_symlink() or not path.is_file():
            raise EpisodeError("solution artifact is unavailable")
        raw_package = path.read_bytes()
    except OSError as exc:
        raise EpisodeError(f"solution artifact is unavailable: {exc}") from exc
    if hashlib.sha256(raw_package).hexdigest() != solution:
        raise EpisodeError("solution artifact digest mismatch")
    if not artifacts.artifact_available(dsn, artifacts_root, solution):
        raise EpisodeError("solution artifact is not registered and available")
    try:
        package = json.loads(raw_package)
    except (ValueError, UnicodeError) as exc:
        raise EpisodeError("solution artifact package is malformed") from exc
    if (not isinstance(package, dict) or set(package) != {"manifest", "scope", "files"}
            or package["scope"] != SOLUTION_SCOPE
            or not isinstance(package["manifest"], dict)
            or not isinstance(package["files"], dict)):
        raise EpisodeError("artifact is not an RSI solution package")
    manifest = package["manifest"]
    encoded_files = package["files"]
    if (set(manifest) != {"kind", "task", "files"}
            or manifest["kind"] != SOLUTION_SCOPE):
        raise EpisodeError("solution artifact manifest is malformed")
    if manifest.get("task") != task.digest:
        raise EpisodeError("solution artifact belongs to another task")
    files: dict[str, bytes] = {}
    for rel, encoded in encoded_files.items():
        if rel not in task.workspace:
            raise EpisodeError("solution path is outside the task workspace")
        if not isinstance(encoded, str):
            raise EpisodeError("solution artifact contains invalid file bytes")
        try:
            content = bytes.fromhex(encoded)
        except ValueError as exc:
            raise EpisodeError("solution artifact contains invalid file bytes") from exc
        if content.hex() != encoded:
            raise EpisodeError("solution artifact file bytes are not canonical")
        files[rel] = content
    if (manifest["files"] != t.file_manifest(files)
            or sum(map(len, files.values())) > artifacts.STAGE_MAX_BYTES):
        raise EpisodeError("solution artifact files disagree with their manifest")
    return files


def _publish_trajectory(dsn: str, raw: bytes, staging_root: str | Path,
                        artifacts_root: str | Path, label: str, *,
                        format: str = "codex-jsonl") -> str:
    manifest = {"kind": "rsi-trajectory", "files": [
        {"path": "events.jsonl", "kind": "file", "size": len(raw),
         "digest": hashlib.sha256(raw).hexdigest()}]}
    receipt = artifacts.stage_package(dsn, staging_root, manifest=manifest,
                                      files={"events.jsonl": raw}, scope=TRAJECTORY_SCOPE,
                                      access_label=label, format=format)
    artifacts.publish_package(dsn, Command(request_id=f"rsi-traj-{receipt['digest']}",
                                           payload={"digest": receipt["digest"]}),
                              artifacts_root, receipt)
    return receipt["digest"]


def read_episode(dsn: str, operation_id: str, launcher: Any) -> Episode | None:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT genome, task, status, tokens, seconds, trajectory"
                        " FROM rsi_episodes WHERE operation_id = %s", (operation_id,))
            row = cur.fetchone()
        conn.commit()
    if row is None:
        return None
    operation = broker.read_operation(dsn, operation_id)
    if operation is None:
        raise EpisodeError(f"episode {operation_id} has no admitted operation")
    envelope = operation.get("payload") or {}
    effect = envelope.get("effect")
    if effect == broker.AGENT_RUN:
        execution_version = ""
        workspace, _ = launcher.exec_dirs(operation_id, execution_version)
    elif effect == broker.SANDBOX_EXEC:
        execution_version = operation.get("execution_version", "")
        if not execution_version:
            raise EpisodeError(f"method episode {operation_id} has no execution version")
        _, workspace = launcher.exec_dirs(operation_id, execution_version)
    else:
        raise EpisodeError(f"episode {operation_id} has unsupported operation effect {effect!r}")
    result = launcher.read_result(operation_id) or {}
    return Episode(operation_id=operation_id, genome=row[0], task=row[1], status=row[2],
                   tokens=row[3], seconds=row[4], trajectory=row[5],
                   workspace=Path(workspace), infra_reason=result.get("infra_reason", ""))
