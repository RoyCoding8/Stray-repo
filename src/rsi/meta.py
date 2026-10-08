"""Broker execution shared by genome proposals and task synthesis."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from settlement import artifacts, broker
from settlement.common import Command, ResultCode, SettlementError

from . import episode, genome, task


@dataclass(frozen=True)
class Output:
    evidence: str
    status: str
    trajectory: str
    detail: str
    workspace: Path


def execute(
    dsn: str,
    launcher,
    parent: genome.Genome,
    *,
    operation_id: str,
    evidence: Callable[[], bytes],
    files: dict[str, bytes],
    instruction: str,
    allocation_id: str,
    token_ceiling: int,
    timeout_ms: int,
    staging_root: Path,
    artifacts_root: Path,
) -> Output:
    existing = broker.read_operation(dsn, operation_id)
    if existing is None:
        raw = evidence()
        manifest = {"kind": "rsi-dev-evidence", "files": task.file_manifest({"evidence.json": raw})}
        staged = artifacts.stage_package(
            dsn,
            staging_root,
            manifest=manifest,
            files={"evidence.json": raw},
            scope="rsi-dev-evidence",
            access_label="candidate",
            format="json",
        )
        published = artifacts.publish_package(
            dsn,
            Command(
                request_id="rsi-evidence:" + staged["digest"], payload={"digest": staged["digest"]}
            ),
            artifacts_root,
            staged,
        )
        if published.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            raise SettlementError(published.detail)
        digest = staged["digest"]
        for rel, data in {**files, "evidence.json": raw}.items():
            launcher.stage_input(operation_id, "", rel, data)
    else:
        admitted = existing["payload"]["payload"]
        if admitted["genome"] != parent.digest:
            raise SettlementError("meta operation belongs to another parent")
        digest = admitted["task"]
    ensured = broker.ensure_operation(
        dsn,
        operation_id=operation_id,
        effect=broker.AGENT_RUN,
        allocation_id=allocation_id,
        payload={
            "harness": parent.harness,
            "genome": parent.digest,
            "task": digest,
            "instruction": instruction,
            "config": genome.settings(parent),
            "timeout_ms": timeout_ms,
            "token_ceiling": token_ceiling,
        },
    )
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(ensured.detail)
    settled = broker.dispatch_operation(dsn, operation_id, launchers={launcher.profile: launcher})
    if settled.dispatch_state not in episode.TERMINAL:
        raise SettlementError("meta run needs dispatch recovery: " + settled.next_decision)
    result = launcher.read_result(operation_id)
    if result is None:
        raise SettlementError("settled meta run has no launcher result: " + settled.next_decision)
    raw = launcher.read_output(operation_id, "", "events.jsonl")
    if hashlib.sha256(raw).hexdigest() != result["trajectory_digest"]:
        raise SettlementError("meta trajectory changed")
    trajectory = episode._publish_trajectory(dsn, raw, staging_root, artifacts_root, "candidate")
    workspace, _ = launcher.exec_dirs(operation_id, "")
    return Output(
        digest, result["status"], trajectory, result.get("final_message", ""), Path(workspace)
    )
