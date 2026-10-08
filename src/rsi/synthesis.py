"""Development tasks proposed from failures, qualified before publication."""

import hashlib
import json
from pathlib import Path

from settlement import artifacts, db, store
from settlement.common import Command, ResultCode, SettlementError

from . import archive, gate, genome, improve, meta, task, verifier

INSTRUCTION = """Use evidence.json to create one new Python development task that exercises
an observed failure mechanism. Write task.json only. It must be a JSON object
with exactly name, instruction, workspace, verifier, reference, test_files.
workspace, verifier and reference map relative paths to UTF-8 file contents.
workspace is an incomplete implementation. reference replaces exactly those
files. verifier contains independent unittest tests with literal expected
values and boundary cases. test_files lists its test modules. Use the standard
library only. Do not copy a source task. Make a distinct task with a precise
instruction and tests. The kernel will run both reference and stub in fresh
processes. A passing reference and failing stub qualify a task, but cannot
prove its specification or tests are correct. Never read outside the workspace.
"""


def parse(raw: bytes) -> task.Task:
    if len(raw) > 262144:
        raise ValueError("synthesized task exceeds byte bound")
    data = json.loads(raw)
    keys = {"name", "instruction", "workspace", "verifier", "reference", "test_files"}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError("synthesized task must match the fixed schema")
    if not all(isinstance(data[k], str) for k in ("name", "instruction")):
        raise ValueError("task name and instruction must be strings")
    if not isinstance(data["test_files"], list) or not all(
        isinstance(p, str) for p in data["test_files"]
    ):
        raise ValueError("test_files must be a list of paths")
    files = {}
    for kind in ("workspace", "verifier", "reference"):
        group = data[kind]
        if not isinstance(group, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in group.items()
        ):
            raise ValueError("task files must map paths to strings")
        files[kind] = {p: s.encode("utf-8") for p, s in group.items()}
    return task.Task(
        data["name"], "dev", data["instruction"], **files, test_files=tuple(data["test_files"])
    )


def run(
    dsn: str,
    agent,
    checker,
    parent: str,
    *,
    operation_id: str,
    token_allocation: str,
    cpu_allocation: str,
    token_ceiling: int,
    timeout_ms: int,
    staging_root: Path,
    artifacts_root: Path,
) -> dict:
    known = archive.decision(dsn, "synthesis:" + operation_id)
    if known:
        if known["data"]["parent"] != parent:
            raise SettlementError("synthesis identity belongs to another parent")
        return known["data"]
    roots = {"staging_root": staging_root, "artifacts_root": artifacts_root}
    report = {"parent": parent, "operation_id": operation_id, "task": None, "scope": "benchmark"}

    def finish(status, detail):
        report.update(status=status, detail=detail)
        archive.record(
            dsn,
            "synthesis:" + operation_id,
            kind="task-qualification",
            actor="fixed",
            subject=report["task"] or parent,
            data=report,
        )
        return report

    def failures():
        data = json.loads(improve.evidence_bundle(dsn, artifacts_root, parent))
        data["dev_episodes"] = [r for r in data["dev_episodes"] if r["verdict"] == "failed"]
        if not data["dev_episodes"]:
            raise SettlementError("synthesis needs observed development task failures")
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    output = meta.execute(
        dsn,
        agent,
        genome.load(dsn, artifacts_root, parent),
        operation_id=operation_id,
        evidence=failures,
        files={"AGENTS.md": INSTRUCTION.encode()},
        instruction=INSTRUCTION,
        allocation_id=token_allocation,
        token_ceiling=token_ceiling,
        timeout_ms=timeout_ms,
        **roots,
    )
    report.update(evidence=output.evidence, trajectory=output.trajectory)
    with db.connect(dsn) as conn:
        pinned = conn.execute(
            "SELECT output FROM rsi_synthesis_outputs WHERE operation_id=%s", (operation_id,)
        ).fetchone()
    if pinned is None:
        digest = None
        source = output.workspace / "task.json"
        if (
            output.status == "completed"
            and not source.is_symlink()
            and not source.is_junction()
            and source.is_file()
            and source.stat().st_size <= 262144
        ):
            raw = source.read_bytes()
            staged = artifacts.stage_package(
                dsn,
                staging_root,
                manifest={
                    "kind": "rsi-synthesis-output",
                    "files": task.file_manifest({"task.json": raw}),
                },
                files={"task.json": raw},
                scope="rsi-synthesis-output",
                access_label="evaluator",
                format="json",
            )
            published = artifacts.publish_package(
                dsn,
                Command(
                    request_id="rsi-synthesis-art:" + staged["digest"],
                    payload={"digest": staged["digest"]},
                ),
                artifacts_root,
                staged,
            )
            if published.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                raise SettlementError(published.detail)
            digest = staged["digest"]

        def pin(cur, control):
            for artifact in (digest, output.evidence, output.trajectory):
                if artifact is None:
                    continue
                artifacts._add_reference(cur, artifact, "evidence", "rsi-synthesis:" + operation_id)
            cur.execute(
                "INSERT INTO rsi_synthesis_outputs (operation_id,parent,evidence,trajectory,output)"
                " VALUES (%s,%s,%s,%s,%s)",
                (operation_id, parent, output.evidence, output.trajectory, digest),
            )
            return ResultCode.APPLIED, "synthesis output pinned", {"output": digest}, [], []

        saved = store.transact(
            dsn,
            Command(request_id="rsi-synthesis-output:" + operation_id, payload={"output": digest}),
            pin,
        )
        if saved.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            raise SettlementError(saved.detail)
    else:
        digest = pinned[0]
    archive.record(
        dsn,
        "synthesis-output:" + operation_id,
        kind="task-synthesis",
        actor="ai",
        subject=digest or parent,
        data={
            "parent": parent,
            "evidence": output.evidence,
            "trajectory": output.trajectory,
            "output": digest,
            "status": output.status,
            "rationale": output.detail,
        },
    )
    if output.status != "completed":
        return finish(output.status, output.detail)
    if digest is None:
        return finish("invalid", "task.json must be a bounded regular file")
    package = (artifacts_root / digest).read_bytes()
    if hashlib.sha256(package).hexdigest() != digest:
        raise SettlementError("synthesis output bytes changed")
    raw = bytes.fromhex(json.loads(package)["files"]["task.json"])
    report["output"] = digest
    try:
        candidate = parse(raw)
    except (ValueError, SettlementError) as exc:
        return finish("invalid", str(exc))
    report["checks"] = {}
    for role, files in (("reference", candidate.reference), ("stub", candidate.workspace)):
        checked = verifier.check(
            dsn,
            checker,
            candidate,
            files,
            operation_id=operation_id + "-" + role,
            allocation_id=cpu_allocation,
            attempt_id=None,
            **roots,
        )
        report["checks"][role] = {
            "status": checked.status,
            "passed": checked.passed,
            "operation_id": checked.operation_id,
        }
    if (
        report["checks"]["reference"]["passed"] is not True
        or report["checks"]["stub"]["passed"] is not False
    ):
        return finish("rejected", "reference must pass and stub must fail")
    identity = gate.anchor_identity(candidate)
    with db.connect(dsn) as conn:
        digests = [
            r[0] for r in conn.execute("SELECT digest FROM rsi_tasks ORDER BY digest").fetchall()
        ]
    for existing in digests:
        item = task.load(dsn, artifacts_root, existing)
        if gate.anchor_identity(item) == identity:
            if item.split != "dev":
                return finish("rejected", "duplicate held-out task content")
            report["task"] = item.digest
            return finish("duplicate", "task content already published")
    report["task"] = task.publish(dsn, candidate, **roots)
    return finish(
        "qualified", "reference passed and stub failed; eligible for a future dev task set"
    )
