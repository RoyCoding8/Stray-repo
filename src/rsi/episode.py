"""Episode: one budgeted, recorded run of a genome on a task.

The run is a kernel ``agent-run`` operation, so it is admitted against an
allocation, sent at most once, and settled with its real token cost. The
trajectory (the harness's event log) becomes an artifact; ``rsi_episodes``
links operation, genome, task and trajectory.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from psycopg.types.json import Json

from settlement import artifacts, broker, db, store
from settlement.common import Command, ResultCode, SettlementError

from . import genome as g
from . import task as t

TRAJECTORY_SCOPE = "rsi-trajectory"
TERMINAL = ("observed", "reconciled")


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
                ownership_generation: int | None = None) -> Episode:
    """Run `genome` on a task once. Calling again with the same id returns the record."""
    task = t.load(dsn, artifacts_root, task.digest)
    known = read_episode(dsn, operation_id, launcher)
    if known is not None:
        if (known.genome, known.task) != (genome.digest, task.digest):
            raise EpisodeError("operation id already belongs to another genome or task")
        return known
    files = task.workspace
    view = g.workspace_view(genome)
    paths = [rel.casefold() for rel in (*view, *files)]
    unique = set(paths)
    if len(paths) != len(unique) or any(
            "/".join(rel.split("/")[:i]) in unique
            for rel in unique for i in range(1, len(rel.split("/")))):
        raise EpisodeError("task files collide with genome files")
    if broker.read_operation(dsn, operation_id) is None:
        for rel, raw in {**files, **view}.items():
            launcher.stage_input(operation_id, "", rel, raw)
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.AGENT_RUN,
        payload={"harness": genome.harness, "genome": genome.digest, "task": task.digest,
                 "instruction": task.instruction, "config": g.settings(genome),
                 "timeout_ms": timeout_ms, "token_ceiling": token_ceiling},
        allocation_id=allocation_id, attempt_id=attempt_id)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise EpisodeError(f"agent-run not admitted: {ensured.detail}")
    status = broker.dispatch_operation(dsn, operation_id,
                                       launchers={launcher.profile: launcher},
                                       ownership_generation=ownership_generation)
    if status.dispatch_state not in TERMINAL:
        raise EpisodeError(f"agent-run {operation_id} not settled:"
                           f" {status.dispatch_state} {status.next_decision}")
    result = launcher.read_result(operation_id)
    if result is None:
        raise EpisodeError(f"agent-run {operation_id} settled without a launcher result")
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


def _publish_trajectory(dsn: str, raw: bytes, staging_root: str | Path,
                        artifacts_root: str | Path, label: str) -> str:
    manifest = {"kind": "rsi-trajectory", "files": [
        {"path": "events.jsonl", "kind": "file", "size": len(raw),
         "digest": hashlib.sha256(raw).hexdigest()}]}
    receipt = artifacts.stage_package(dsn, staging_root, manifest=manifest,
                                      files={"events.jsonl": raw}, scope=TRAJECTORY_SCOPE,
                                      access_label=label, format="codex-jsonl")
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
    result = launcher.read_result(operation_id) or {}
    workspace, _ = launcher.exec_dirs(operation_id, "")
    return Episode(operation_id=operation_id, genome=row[0], task=row[1], status=row[2],
                   tokens=row[3], seconds=row[4], trajectory=row[5],
                   workspace=Path(workspace), infra_reason=result.get("infra_reason", ""))
