"""Pristine verifiers, run as admitted settlement effects after an agent exits.

The local launcher bounds processes, not filesystem or network access. These
results support cooperative benchmark evaluation, not hostile-code acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import stat
import sys
from typing import Mapping

from psycopg.types.json import Json

from settlement import artifacts, broker, db, store
from settlement.common import Command, ResultCode, SettlementError

from . import episode as ep
from .task import DRIVER_PATH, Task, file_manifest, load


class VerifierError(SettlementError):
    pass


@dataclass(frozen=True)
class Verification:
    operation_id: str
    evaluator_version: str
    solution: str
    status: str
    passed: bool | None
    detail: dict


def solution_files(task: Task, workspace: Path) -> dict[str, bytes]:
    """Copy only declared solution slots. Refuse links and path escapes."""
    root = workspace.resolve()
    files = {}
    for rel in task.workspace:
        source = workspace / rel
        resolved = source.resolve()
        if root not in resolved.parents:
            raise VerifierError(f"solution {rel!r} escapes its workspace")
        for part in (source, *source.parents):
            if part == workspace:
                break
            if part.is_symlink() or part.is_junction():
                raise VerifierError(f"solution {rel!r} is a link")
        try:
            mode = source.lstat().st_mode
        except FileNotFoundError:
            continue  # pristine tests report the missing module as an import error
        if not stat.S_ISREG(mode):
            raise VerifierError(f"solution {rel!r} is not a regular file")
        if source.stat().st_size > artifacts.STAGE_MAX_BYTES:
            raise VerifierError("solution exceeds artifact byte bound")
        files[rel] = source.read_bytes()
    return files


def _snapshot(dsn, task, files, staging_root, artifacts_root):
    scope = "rsi-solution"
    manifest = {"kind": scope, "task": task.digest, "files": file_manifest(files)}
    receipt = artifacts.stage_package(
        dsn, staging_root, manifest=manifest, files=dict(files), scope=scope,
        access_label="hidden" if task.split == "anchor" else "candidate", format=scope)
    result = artifacts.publish_package(dsn, Command(
        request_id=f"rsi-solution-{receipt['digest']}", payload={"digest": receipt["digest"]}),
        artifacts_root, receipt)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise VerifierError(result.detail)
    return receipt["digest"]


def _result(dsn, operation_id, evaluator_version, solution) -> Verification:
    receipts = store.operation_receipts(dsn, operation_id)
    if len(receipts) != 1:
        raise VerifierError("verification needs one unambiguous settled receipt")
    content = receipts[0]["content"]
    data = content.get("data", {})
    worker = data.get("worker", {})
    report = worker.get("data", {})
    status, passed = "infra_failed", None
    if data.get("timed_out"):
        status = "timeout"
    elif content.get("truncated"):
        status = "infra_failed"
    elif content.get("parse") == "typed-json" and type(report.get("tests")) is int:
        counts = [report.get(k) for k in ("failures", "errors", "skipped")]
        if report["tests"] > 0 and all(type(n) is int and n >= 0 for n in counts):
            passed = worker.get("status") == "ok" and counts == [0, 0, 0]
            status = "passed" if passed else "failed"
    elif content.get("parse") == "child-failed":
        status, passed = "failed", False
    return Verification(operation_id, evaluator_version, solution, status, passed, content)


def check(dsn: str, launcher, task: Task, files: Mapping[str, bytes], *,
          operation_id: str, allocation_id: str, attempt_id: str | None,
          staging_root: str | Path, artifacts_root: str | Path,
          timeout_ms: int = 30_000, ownership_generation: int | None = None) -> Verification:
    """Run a pinned verifier on solution bytes. Reference/stub checks use this too."""
    task = load(dsn, artifacts_root, task.digest)
    if task.runtime != sys.version:
        raise VerifierError("evaluator Python runtime differs from its pinned version")
    if set(files) - set(task.workspace):
        raise VerifierError("verification accepts only declared solution files")
    solution = _snapshot(dsn, task, files, staging_root, artifacts_root)
    version = solution  # solution package includes the task digest, which pins the evaluator
    if broker.read_operation(dsn, operation_id) is None:
        for rel, raw in {**files, **task.verifier, DRIVER_PATH: task.driver}.items():
            launcher.stage_input(operation_id, version, rel, raw)
    inputs, _ = launcher.exec_dirs(operation_id, version)
    # The script resides in the launcher's operation work tree. No cwd exception
    # or wider sandbox payload is needed to select an isolated verifier workspace.
    argv = [launcher.staged_python(), "-I", "-S", "-B",
            str(Path(inputs) / DRIVER_PATH), *task.test_files]
    result = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile, "argv": argv, "timeout_ms": timeout_ms,
                 "max_output_bytes": 65_536}, allocation_id=allocation_id,
        attempt_id=attempt_id, execution_version=version)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise VerifierError(f"verifier not admitted: {result.detail}")
    status = broker.dispatch_operation(dsn, operation_id,
                                       launchers={launcher.profile: launcher},
                                       ownership_generation=ownership_generation)
    if status.dispatch_state not in ep.TERMINAL:
        raise VerifierError(f"verifier not settled: {status.dispatch_state} {status.next_decision}")
    return _result(dsn, operation_id, task.evaluator_version, solution)


def read_verdict(dsn: str, episode_id: str, evaluator_version: str) -> Verification | None:
    with db.connect(dsn) as conn:
        row = conn.execute("SELECT operation_id, solution, status, passed, detail"
                           " FROM rsi_verdicts WHERE episode = %s AND evaluator_version = %s",
                           (episode_id, evaluator_version)).fetchone()
    if row is None:
        return None
    return Verification(row[0], evaluator_version, row[1], row[2], row[3], row[4])


def verify_episode(dsn: str, agent_launcher, verifier_launcher, episode_id: str, *,
                   allocation_id: str, attempt_id: str | None,
                   staging_root: str | Path, artifacts_root: str | Path,
                   timeout_ms: int = 30_000,
                   ownership_generation: int | None = None) -> Verification:
    """Verify a recorded completed episode, once per frozen evaluator version."""
    episode = ep.read_episode(dsn, episode_id, agent_launcher)
    if episode is None or episode.status != "completed":
        raise VerifierError("verification requires a completed episode; no infrastructure verdict")
    task = load(dsn, artifacts_root, episode.task)
    known = read_verdict(dsn, episode_id, task.evaluator_version)
    if known is not None:
        return known
    operation_id = "rsi-verify-" + hashlib.sha256(
        f"{episode_id}:{task.evaluator_version}".encode()).hexdigest()
    existing = broker.read_operation(dsn, operation_id)
    if existing is None:
        files = solution_files(task, episode.workspace)
        verdict = check(dsn, verifier_launcher, task, files, operation_id=operation_id,
                        allocation_id=allocation_id, attempt_id=attempt_id,
                        staging_root=staging_root, artifacts_root=artifacts_root,
                        timeout_ms=timeout_ms, ownership_generation=ownership_generation)
    else:
        # A crash between settlement and recording must use the original solution,
        # even if the agent workspace has since changed or disappeared.
        version = existing["execution_version"]
        status = broker.dispatch_operation(dsn, operation_id,
                                           launchers={verifier_launcher.profile: verifier_launcher},
                                           ownership_generation=ownership_generation)
        if status.dispatch_state not in ep.TERMINAL:
            raise VerifierError("verification operation needs recovery")
        verdict = _result(dsn, operation_id, task.evaluator_version, version)

    def record(cur, control):
        cur.execute("INSERT INTO rsi_verdicts (episode, evaluator_version, operation_id,"
                    " solution, status, passed, detail) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (episode, evaluator_version) DO NOTHING",
                    (episode_id, verdict.evaluator_version, verdict.operation_id,
                     verdict.solution, verdict.status, verdict.passed, Json(verdict.detail)))
        return (ResultCode.APPLIED, "verdict recorded", {"episode": episode_id},
                [("rsi.verdict", {"episode": episode_id, "status": verdict.status})], [])
    result = store.transact(dsn, Command(request_id=f"rsi-verdict-{operation_id}",
                                         payload={"episode": episode_id}), record)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise VerifierError(result.detail)
    recorded = read_verdict(dsn, episode_id, task.evaluator_version)
    if recorded is None:
        raise VerifierError("verdict was not recorded")
    return recorded
