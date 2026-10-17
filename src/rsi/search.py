"""Content-addressed search frames and evidence-backed replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from settlement import artifacts, db, store
from settlement.common import Command, ResultCode, SettlementError

from . import archive, capability, genome, investigation

FRAME_SCOPE = "rsi-search-frame"
BRANCH_SCOPE = "rsi-search-branch"
EVALUATION_SCOPE = "rsi-search-evaluation"
POLICY_INTERFACE = "exploration-policy/1"
MAX_FRAME_BYTES = 4 * 1024 * 1024


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SettlementError("search data must be finite JSON") from exc


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _artifact_bytes(scope: str, kind: str, value: dict) -> bytes:
    raw = _canonical(value)
    path = kind + ".json"
    manifest = {"kind": scope, "files": [{"path": path, "kind": "file",
                "size": len(raw), "digest": _digest(raw)}]}
    return artifacts.package_bytes(manifest, {path: raw}, scope)


def _publish(dsn: str, staging_root: str | Path, artifacts_root: str | Path,
             scope: str, kind: str, value: dict) -> str:
    raw = _canonical(value)
    path = kind + ".json"
    manifest = {"kind": scope, "files": [{"path": path, "kind": "file",
                "size": len(raw), "digest": _digest(raw)}]}
    receipt = artifacts.stage_package(dsn, staging_root, manifest=manifest,
                                      files={path: raw}, scope=scope,
                                      format=kind, version="1")
    result = artifacts.publish_package(
        dsn, Command(request_id=f"rsi-search-{kind}-{receipt['digest']}",
                     payload={"digest": receipt["digest"]}), artifacts_root, receipt)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    def protect(cur, control):
        artifacts._add_reference(cur, receipt["digest"], "evidence",
                                 f"p06-{kind}:{receipt['digest']}")
        return (ResultCode.APPLIED, "search artifact protected",
                {"digest": receipt["digest"]}, [], [])
    protected = store.transact(
        dsn, Command(request_id=f"rsi-search-ref-{receipt['digest']}",
                     payload={"digest": receipt["digest"], "kind": kind}), protect)
    if protected.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(protected.detail)
    return receipt["digest"]


def _load(dsn: str, digest: str, *, artifacts_root: str | Path,
          scope: str, kind: str) -> dict:
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT manifest,scope,availability FROM artifact_versions WHERE digest=%s",
                    (digest,))
        artifact = cur.fetchone()
    if (artifact is None or artifact["scope"] != scope
            or artifact["availability"] != "available"):
        raise SettlementError(f"unknown or unavailable {kind} artifact")
    package_raw = (Path(artifacts_root) / digest).read_bytes()
    if _digest(package_raw) != digest:
        raise SettlementError(f"{kind} artifact bytes do not match their identity")
    package = json.loads(package_raw)
    manifest = artifact["manifest"]
    if package.get("manifest") != manifest or package.get("scope") != scope:
        raise SettlementError(f"{kind} artifact manifest is inconsistent")
    files = package.get("files")
    if not isinstance(files, dict) or len(files) != 1 or kind + ".json" not in files:
        raise SettlementError(f"{kind} artifact has an invalid file set")
    raw = bytes.fromhex(files[kind + ".json"])
    if _digest(raw) != manifest["files"][0]["digest"]:
        raise SettlementError(f"{kind} contents do not match their manifest")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise SettlementError(f"{kind} contents must be an object")
    return value


def _check_frame(frame: dict) -> None:
    if (frame.get("schema") != "p06-frame/1" or not isinstance(frame.get("visible"), dict)
            or not isinstance(frame.get("starts"), dict) or not frame["starts"]
            or not isinstance(frame.get("source"), dict)):
        raise SettlementError("frame must contain schema, visible request, starts, and source")
    for opportunity_id, start in frame["starts"].items():
        required = {"investigation_id", "target_revision", "visible_input", "task",
                    "genome", "model", "runtime", "evaluator_version", "limits"}
        if (not isinstance(opportunity_id, str) or not opportunity_id
                or not isinstance(start, dict) or required - start.keys()
                or type(start["target_revision"]) is not int or start["target_revision"] < 0
                or not isinstance(start["investigation_id"], str) or not start["investigation_id"]
                or not isinstance(start["visible_input"], dict)
                or not isinstance(start["task"], str) or not start["task"]
                or not isinstance(start["genome"], str) or not start["genome"]
                or (start["model"] is not None and not isinstance(start["model"], str))
                or (start["model"] == "" and start.get("method") is None)
                or not isinstance(start["runtime"], dict)
                or not isinstance(start["evaluator_version"], str)
                or not start["evaluator_version"]
                or not isinstance(start["limits"], dict)
                or start.get("method") != start["visible_input"].get("capability")):
            raise SettlementError("each opportunity must pin its exact prepared P01 start")
        _canonical(start)
    raw = _canonical(frame)
    if len(raw) > MAX_FRAME_BYTES:
        raise SettlementError("frame exceeds its JSON size bound")


def publish_frame(dsn: str, visible: dict, starts: dict, source: dict, *,
                  staging_root: str | Path, artifacts_root: str | Path) -> str:
    frame = {"schema": "p06-frame/1", "visible": visible,
             "starts": starts, "source": source}
    _check_frame(frame)
    return _publish(dsn, staging_root, artifacts_root, FRAME_SCOPE, "frame", frame)


def load_frame(dsn: str, digest: str, *, artifacts_root: str | Path) -> dict:
    frame = _load(dsn, digest, artifacts_root=artifacts_root,
                  scope=FRAME_SCOPE, kind="frame")
    _check_frame(frame)
    return frame


def _step_identity(investigation_id: str, revision: int) -> tuple[str, str, str]:
    identity = hashlib.sha256(f"{investigation_id}:{revision}".encode()).hexdigest()
    return ("p01-decision-" + identity, "p01-attempt-" + identity,
            "p01-worker-" + identity)


def _attempt_effects(dsn: str, attempt_id: str) -> dict:
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id,payload,reservation_id,allocation_id,execution_version,settled,"
                    "dispatch_state,reconcile_state "
                    "FROM operations WHERE attempt_id=%s ORDER BY id", (attempt_id,))
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["effect"] = dict(row["payload"] or {}).get("effect")
        row["receipts"] = store.operation_receipts(dsn, row["id"])
    return {row["id"]: row for row in rows}


def _branch_evidence(dsn: str, start: dict, artifacts_root: str | Path) -> dict:
    investigation_id, revision = start["investigation_id"], start["target_revision"]
    history = investigation.export(dsn, investigation_id)
    base = {"schema": "p06-branch/1", "investigation_id": investigation_id,
            "target_revision": revision, "status": "gap", "reason": "P01 decision is missing"}
    if history is None:
        return {**base, "reason": "P01 investigation is missing"}
    decision_id, attempt_id, operation_id = _step_identity(investigation_id, revision)
    decision = next((item for item in history["decisions"] if item["id"] == decision_id), None)
    if decision is None or decision["kind"] != "worker":
        return base
    consumed = decision["data"].get("visible_input")
    if consumed != start["visible_input"]:
        return {**base, "decision_id": decision_id,
                "reason": "prepared input differs from the input P01 consumed"}
    observation = next((item["content"] for item in history["observations"]
                        if item["decision_id"] == decision_id
                        and item["content"].get("episode") == operation_id), None)
    if observation is None:
        return {**base, "decision_id": decision_id, "reason": "worker observation is missing"}
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT a.model,e.genome,e.task,e.status AS episode_status,e.trajectory,"
                    "t.evaluator_version,v.status AS verdict_status,v.passed,v.solution,"
                    "w.execution_version AS worker_execution,w.launcher_id AS worker_launcher,"
                    "w.provider_id AS worker_provider,w.settled AS worker_settled,"
                    "w.dispatch_state AS worker_dispatch,w.reconcile_state AS worker_reconcile,"
                    "vop.execution_version AS verifier_execution,vop.settled AS verifier_settled,"
                    "vop.dispatch_state AS verifier_dispatch,vop.reconcile_state AS verifier_reconcile "
                    "FROM attempts a JOIN rsi_episodes e ON e.operation_id=%s "
                    "JOIN rsi_tasks t ON t.digest=e.task "
                    "LEFT JOIN rsi_verdicts v ON v.episode=e.operation_id "
                    "LEFT JOIN operations vop ON vop.id=v.operation_id "
                    "LEFT JOIN operations w ON w.id=e.operation_id WHERE a.id=%s",
                    (operation_id, attempt_id))
        actual = cur.fetchone()
    if actual is None:
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "reason": "worker or verifier record is missing"}
    actual = dict(actual)
    identity_checks = {"task": actual["task"], "genome": actual["genome"],
                       "model": actual["model"], "evaluator_version": actual["evaluator_version"]}
    method_expected = start.get("method")
    method_actual = consumed.get("capability") if isinstance(consumed, dict) else None
    if method_expected != method_actual:
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "reason": "prepared method closure differs"}
    config = history["state"].get("config", {})
    actual_limits = {key: config.get(key) for key in
                     ("timeout_ms", "token_ceiling", "max_steps", "token_allocation",
                      "cpu_allocation") if key in config}
    if start["limits"] != actual_limits:
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "reason": "prepared execution limits differ",
                "mismatches": ["limits"]}
    mismatches = [name for name, value in identity_checks.items() if start.get(name) != value]
    runtime = start.get("runtime", {})
    runtime_actual = {"execution_version": actual["worker_execution"],
                      "launcher_id": actual["worker_launcher"],
                      "provider_id": actual["worker_provider"]}
    if isinstance(runtime, dict):
        mismatches.extend("runtime." + key for key, value in runtime.items()
                          if key in runtime_actual and runtime_actual.get(key) != value)
    runtime_required = ["execution_version"]
    if method_expected is not None:
        runtime_required.extend(("python_version", "python_executable", "implementation"))
    if (not isinstance(runtime, dict)
            or any(not isinstance(runtime.get(key), str) or not runtime[key]
                   for key in runtime_required)
            or not actual["worker_execution"] or not actual["verifier_execution"]
            or not actual["solution"]
            or actual["verifier_execution"] != actual["solution"]):
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id,
                "reason": "worker or verifier execution identity is incomplete or inconsistent",
                "known_observation": {"status": observation.get("status"),
                                      "passed": observation.get("passed")},
                "actual_runtime": runtime_actual}
    if mismatches:
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "reason": "prepared worker identity differs",
                "mismatches": mismatches}
    if (not actual["worker_settled"] or actual["worker_dispatch"] not in ("observed", "reconciled")
            or actual["worker_reconcile"] in ("conflict", "unresolved")
            or not actual["verifier_settled"] or actual["verifier_dispatch"] not in ("observed", "reconciled")
            or actual["verifier_reconcile"] in ("conflict", "unresolved")
            or actual["verdict_status"] not in ("passed", "failed")
            or observation.get("status") not in ("passed", "failed")
            or type(observation.get("passed")) is not bool):
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "reason": "worker or pristine verifier is unresolved"}
    unresolved = {item["id"] for item in history["unresolved_effects"]}
    verifier_id = observation.get("verdict")
    if operation_id in unresolved or verifier_id in unresolved:
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "reason": "branch has unresolved effects"}
    full_effects = _attempt_effects(dsn, attempt_id)
    worker_effect = full_effects.get(operation_id, {})
    verifier_effect = full_effects.get(verifier_id, {})
    if not worker_effect or not verifier_effect:
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id, "reason": "worker or verifier receipts are missing"}
    worker_receipts, verifier_receipts = worker_effect["receipts"], verifier_effect["receipts"]
    expected_worker_effect = ("sandbox-exec" if method_expected is not None else "agent-run")
    if (len(worker_receipts) != 1 or worker_receipts[0].get("outcome") != "success"
            or len(verifier_receipts) != 1
            or verifier_receipts[0].get("outcome") not in ("success", "failure")
            or store.operation_receipt_conflicts(dsn, operation_id)
            or store.operation_receipt_conflicts(dsn, verifier_id)
            or worker_effect.get("payload", {}).get("effect") != expected_worker_effect
            or verifier_effect.get("payload", {}).get("effect") != "sandbox-exec"
            or not worker_effect.get("execution_version")
            or not verifier_effect.get("execution_version")):
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id,
                "reason": "worker or verifier receipts are conflicted or mismatched"}
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        reservation_ids = [effect.get("reservation_id") for effect in
                           (worker_effect, verifier_effect) if effect.get("reservation_id")]
        cur.execute("SELECT id,allocation_id,amount,state FROM reservations WHERE id=ANY(%s)",
                    (reservation_ids,))
        reservations = {row["id"]: dict(row) for row in cur.fetchall()}
    worker_reservation = reservations.get(worker_effect.get("reservation_id"))
    verifier_reservation = reservations.get(verifier_effect.get("reservation_id"))
    if (not worker_reservation or not verifier_reservation
            or worker_reservation["state"] != "settled"
            or verifier_reservation["state"] != "settled"
            or worker_reservation["allocation_id"] != worker_effect["allocation_id"]
            or verifier_reservation["allocation_id"] != verifier_effect["allocation_id"]
            or worker_effect["allocation_id"] != (config["cpu_allocation"]
                                                    if method_expected is not None
                                                    else config["token_allocation"])
            or verifier_effect["allocation_id"] != config["cpu_allocation"]
            or not artifacts.artifact_available(dsn, artifacts_root, actual["trajectory"])
            or not artifacts.artifact_available(dsn, artifacts_root, actual["solution"])):
        return {**base, "decision_id": decision_id, "attempt_id": attempt_id,
                "operation_id": operation_id,
                "reason": "worker/verifier artifacts or resource charges are incomplete"}
    return {"schema": "p06-branch/1", "investigation_id": investigation_id,
            "target_revision": revision, "decision_id": decision_id,
            "attempt_id": attempt_id, "operation_id": operation_id,
            "status": "supported", "outcome": "passed" if actual["passed"] else "failed",
            "quality": {"passed": actual["passed"], "verdict": actual["verdict_status"]},
            "consumed_input": consumed, "actual": {**identity_checks,
                "runtime": {**runtime, "execution_version": actual["worker_execution"],
                            **{key: runtime[key] for key in ("launcher_id", "provider_id")
                               if key in runtime}},
                "verifier_execution_version": actual["verifier_execution"],
                "episode_status": actual["episode_status"],
                "trajectory": actual["trajectory"], "solution": actual["solution"],
                "limits": actual_limits},
            "receipts": {"worker": worker_effect["receipts"],
                         "verifier": verifier_effect["receipts"]},
            "resources": {"worker": worker_reservation,
                          "verifier": verifier_reservation}}


def capture(dsn: str, frame_digest: str, opportunity_id: str, *,
            staging_root: str | Path, artifacts_root: str | Path) -> dict:
    frame = load_frame(dsn, frame_digest, artifacts_root=artifacts_root)
    start = frame["starts"].get(opportunity_id)
    if start is None:
        raise SettlementError("opportunity is not eligible in this frame")
    branch = _branch_evidence(dsn, start, artifacts_root)
    branch.update({"frame": frame_digest, "opportunity_id": opportunity_id})
    digest = _publish(dsn, staging_root, artifacts_root, BRANCH_SCOPE, "branch", branch)
    branch["digest"] = digest
    return branch


def _policy_action(policy: dict, frame: dict, invocation: Any) -> tuple[str, str | None, str | None]:
    if invocation.status != "completed" or invocation.files:
        return "refused", None, "native policy execution did not return a clean value"
    value = invocation.value
    if not isinstance(value, dict) or set(value) - {"action", "opportunity_id", "reason"}:
        return "refused", None, "policy output has an invalid shape"
    if value.get("action") == "choose" and set(value) == {"action", "opportunity_id"}:
        selected = value["opportunity_id"]
        if isinstance(selected, str) and selected in frame["starts"]:
            return "choose", selected, None
    if value.get("action") == "stop" and set(value) == {"action", "reason"}:
        reason = value["reason"]
        if isinstance(reason, str) and reason.strip():
            return "stop", None, reason
    return "refused", None, "policy output is not one eligible closed action"


def evaluate(dsn: str, checker: Any, policy: dict, frames: list[str], branches: list[str], *,
             evaluation_id: str, allocation_id: str, max_decisions: int = 1,
             staging_root: str | Path,
             artifacts_root: str | Path) -> dict:
    if (not isinstance(policy, dict) or policy.get("interface") != POLICY_INTERFACE
            or not isinstance(policy.get("genome"), str) or not isinstance(policy.get("name"), str)):
        raise SettlementError("policy must pin a genome, method name, and exploration interface")
    if (type(max_decisions) is not int or max_decisions not in (1, 2)
            or not frames or len(set(frames)) != len(frames)
            or len(set(branches)) != len(branches)):
        raise SettlementError("evaluation needs unique corpora and max_decisions of one or two")
    genome_obj = genome.load(dsn, artifacts_root, policy["genome"])
    methods = [item for item in capability.catalogue(genome_obj)
               if item.name == policy["name"] and item.interface == POLICY_INTERFACE]
    if len(methods) != 1:
        raise SettlementError("policy genome lacks one method for the exploration interface")
    pinned_policy = {"genome": policy["genome"], "name": policy["name"],
                     "interface": POLICY_INTERFACE, "method_digest": methods[0].digest,
                     "timeout_ms": policy.get("timeout_ms"),
                     "max_output_bytes": policy.get("max_output_bytes"),
                     "frames": list(frames), "branches": list(branches),
                     "allocation_id": allocation_id,
                     "max_decisions": max_decisions}
    archive.record(dsn, "p06-evaluation:" + evaluation_id,
                   kind="p06-evaluation", actor="fixed",
                   subject=evaluation_id, data=pinned_policy)
    results = []
    frame_docs = {frame_digest: load_frame(
        dsn, frame_digest, artifacts_root=artifacts_root) for frame_digest in frames}
    branch_docs, branch_index = {}, {}
    for branch_digest in branches:
        branch = _load(dsn, branch_digest, artifacts_root=artifacts_root,
                       scope=BRANCH_SCOPE, kind="branch")
        branch_docs[branch_digest] = branch
        branch_frame, opportunity_id = branch.get("frame"), branch.get("opportunity_id")
        if (branch_frame not in frame_docs or not isinstance(opportunity_id, str)
                or opportunity_id not in frame_docs[branch_frame]["starts"]):
            raise SettlementError("branch is not bound to a declared frame opportunity")
        key = (branch_frame, opportunity_id)
        if key in branch_index:
            raise SettlementError("branch corpus has conflicting evidence for one opportunity")
        branch_index[key] = branch_digest
    for index, frame_digest in enumerate(frames):
        frame = frame_docs[frame_digest]
        operation_id = f"p06-policy-{evaluation_id}-{index:04d}"
        invocation = capability.invoke(
            dsn, checker, genome_obj, policy["name"],
            {"interface": POLICY_INTERFACE, "value": frame["visible"],
             "files": {}, "context": {}}, operation_id=operation_id,
            allocation_id=allocation_id, attempt_id=None, staging_root=staging_root,
            artifacts_root=artifacts_root, timeout_ms=policy.get("timeout_ms"),
            max_output_bytes=policy.get("max_output_bytes"))
        action, selected, reason = _policy_action(policy, frame, invocation)
        branch_digest = branch_index.get((frame_digest, selected)) if selected is not None else None
        branch = branch_docs.get(branch_digest)
        with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id,allocation_id,reservation_id,execution_version,settled,"
                        "dispatch_state,reconcile_state,payload FROM operations WHERE id=%s",
                        (operation_id,))
            operation = cur.fetchone()
            reservation = None
            if operation and operation["reservation_id"]:
                cur.execute("SELECT id,operation_id,allocation_id,amount,state FROM reservations "
                            "WHERE id=%s",
                            (operation["reservation_id"],))
                reservation = cur.fetchone()
        if operation is not None:
            operation = dict(operation)
            payload = operation.pop("payload") or {}
            operation["effect"] = payload.get("effect")
            operation["actual_cost_present"] = "_receipt_actual_cost" in payload
            operation["actual_cost"] = payload.get("_receipt_actual_cost")
        receipts = store.operation_receipts(dsn, operation_id)
        for receipt in receipts:
            receipt["operation_id"] = operation_id
        policy_output = ({"value": invocation.value,
                          "files": {slot: text.decode("utf-8")
                                    for slot, text in invocation.files}}
                         if invocation.output_digest else None)
        results.append({"frame": frame_digest, "branch": branch_digest,
                        "request_digest": invocation.input_digest,
                        "operation_id": operation_id, "status": action,
                        "policy_result": invocation.value,
                        "selected": selected, "reason": reason,
                        "branch_status": branch.get("status", "gap") if branch else "gap",
                        "outcome": branch.get("outcome") if branch else None,
                        "quality": branch.get("quality") if branch else None,
                        "continuation_query": (
                            {"status": "gap", "reason": "recorded child frame is missing"}
                            if max_decisions == 2 and action == "choose" else None),
                        "receipts": receipts,
                        "resources": dict(reservation) if reservation else None,
                        "operation": dict(operation) if operation else None,
                        "policy_output": policy_output,
                        "invocation": {"status": invocation.status,
                                       "method_digest": invocation.method_digest,
                                       "execution_version": invocation.execution_version,
                                       "output_digest": invocation.output_digest,
                                       "seconds": invocation.seconds}})
    result = {"schema": "p06-evaluation/1", "evaluation_id": evaluation_id,
              "policy": {key: policy[key] for key in
                         ("genome", "name", "interface", "timeout_ms", "max_output_bytes")
                         if key in policy} | {"method_digest": methods[0].digest},
              "evaluation_decision": "p06-evaluation:" + evaluation_id,
              "allocation_id": allocation_id,
              "max_decisions": max_decisions,
              "pinned_evaluation": pinned_policy,
              "frames": frames, "branches": branches,
              "frame_artifacts": frame_docs, "branch_artifacts": branch_docs,
              "results": results}
    result["recomputed"] = recompute(result)
    result["digest"] = _publish(dsn, staging_root, artifacts_root,
                                EVALUATION_SCOPE, "evaluation", result)
    return result


def recompute(bundle: dict) -> dict:
    """Recompute support and outcomes from saved evaluation facts, without execution."""
    if not isinstance(bundle, dict) or not isinstance(bundle.get("results"), list):
        raise SettlementError("offline bundle must contain evaluation results")
    results = bundle["results"]
    pinned = bundle.get("pinned_evaluation")
    evaluation_id = bundle.get("evaluation_id")
    policy = bundle.get("policy")
    max_decisions = bundle.get("max_decisions", 1)
    if (not isinstance(evaluation_id, str) or not evaluation_id
            or type(max_decisions) is not int or max_decisions not in (1, 2)
            or bundle.get("evaluation_decision") != "p06-evaluation:" + evaluation_id
            or not isinstance(policy, dict)
            or not isinstance(pinned, dict) or pinned.get("frames") != bundle.get("frames")
            or pinned.get("branches") != bundle.get("branches")
            or pinned.get("allocation_id") != bundle.get("allocation_id")
            or pinned.get("max_decisions") != bundle.get("max_decisions", 1)
            or not isinstance(pinned.get("method_digest"), str)
            or not isinstance(bundle.get("frames"), list)
            or not isinstance(bundle.get("branches"), list)
            or len(results) != len(bundle["frames"])
            or any(policy.get(key) != pinned.get(key)
                   for key in ("genome", "name", "interface", "method_digest",
                               "timeout_ms", "max_output_bytes"))):
        raise SettlementError("offline evaluation identity is missing or inconsistent")
    frames = bundle.get("frame_artifacts", {})
    branches = bundle.get("branch_artifacts", {})
    if not isinstance(frames, dict) or not isinstance(branches, dict):
        raise SettlementError("offline bundle must contain its frame and branch artifacts")

    def artifact_digest(scope: str, kind: str, value: dict) -> str:
        return _digest(_artifact_bytes(scope, kind, value))

    if (set(frames) != set(bundle["frames"])
            or set(branches) != set(bundle["branches"])):
        raise SettlementError("offline artifact corpus differs from its pinned identity")
    if any(artifact_digest(FRAME_SCOPE, "frame", frame) != digest
           for digest, frame in frames.items()):
        raise SettlementError("offline frame identity does not match its contents")
    if any(artifact_digest(BRANCH_SCOPE, "branch", branch) != digest
           for digest, branch in branches.items()):
        raise SettlementError("offline branch identity does not match its contents")
    for digest, branch in branches.items():
        if (branch.get("frame") not in frames
                or branch.get("opportunity_id") not in frames[branch["frame"]].get("starts", {})):
            raise SettlementError("offline branch references an undeclared opportunity")
    branch_index = {}
    for digest, branch in branches.items():
        key = (branch["frame"], branch["opportunity_id"])
        if key in branch_index:
            raise SettlementError("offline branch corpus has conflicting opportunity evidence")
        branch_index[key] = digest
    def policy_effect_evidence(row: dict, index: int) -> tuple[bool, int | None]:
        """Validate a policy effect; unknown reservations leave only its cost unknown."""
        invocation = row.get("invocation")
        operation = row.get("operation")
        receipts = row.get("receipts")
        resources = row.get("resources")
        expected_id = f"p06-policy-{bundle.get('evaluation_id')}-{index:04d}"
        valid_receipt = (isinstance(receipts, list) and len(receipts) == 1
                         and isinstance(receipts[0], dict)
                         and isinstance(receipts[0].get("receipt_identity"), str)
                         and bool(receipts[0]["receipt_identity"].strip())
                         and receipts[0].get("operation_id") == expected_id
                         and receipts[0].get("outcome") in ("success", "failure")
                         and isinstance(receipts[0].get("content"), dict)
                         and isinstance(receipts[0].get("provenance"), str)
                         and bool(receipts[0]["provenance"].strip()))
        reservation_valid = (isinstance(resources, dict)
                             and isinstance(operation, dict)
                             and isinstance(operation.get("reservation_id"), str)
                             and bool(operation["reservation_id"])
                             and resources.get("id") == operation.get("reservation_id")
                             and resources.get("operation_id") == expected_id
                             and resources.get("allocation_id") == bundle.get("allocation_id")
                             and resources.get("state") == "settled"
                             and type(resources.get("amount")) is int
                             and resources["amount"] >= 0)
        actual_cost = operation.get("actual_cost") if isinstance(operation, dict) else None
        actual_cost_valid = (isinstance(operation, dict)
                             and operation.get("actual_cost_present") is True
                             and (actual_cost is None or type(actual_cost) is int
                                  and actual_cost >= 0)
                             and (actual_cost is None or not reservation_valid
                                  or actual_cost <= resources["amount"]))
        operation_valid = (isinstance(invocation, dict) and isinstance(operation, dict)
                           and row.get("operation_id") == expected_id
                           and operation.get("id") == expected_id
                           and operation.get("effect") == "sandbox-exec"
                           and isinstance(operation.get("reservation_id"), str)
                           and bool(operation["reservation_id"])
                           and operation.get("allocation_id") == bundle.get("allocation_id")
                           and isinstance(operation.get("execution_version"), str)
                           and bool(operation["execution_version"])
                           and invocation.get("execution_version") == operation.get("execution_version")
                           and operation.get("settled") is True
                           and operation.get("dispatch_state") in ("observed", "reconciled")
                           and operation.get("reconcile_state") not in ("conflict", "unresolved")
                           and actual_cost_valid)
        if not (valid_receipt and operation_valid):
            return False, None
        if actual_cost is not None:
            return True, actual_cost
        if reservation_valid:
            return True, resources["amount"]
        return True, None

    def policy_invocation_matches(row: dict) -> bool:
        """Bind the policy label to the method that produced the recorded action."""
        invocation = row.get("invocation")
        expected_digest = policy.get("method_digest")
        actual_digest = invocation.get("method_digest") if isinstance(invocation, dict) else None
        return (isinstance(expected_digest, str) and bool(expected_digest)
                and actual_digest == expected_digest)

    supported = gaps = stops = refusals = passed = failed = continuation_gaps = 0
    cpu_seconds = 0.0
    cpu_seconds_unknown = 0
    screening_cpu_units = 0
    screening_cpu_units_unknown = 0
    # Cost accounting is independent of whether a chosen historical branch is
    # covered. A stop, refusal, malformed choice, or valid choice with a gap
    # still paid for its durable native policy invocation.
    for index, row in enumerate(results):
        if not isinstance(row, dict):
            cpu_seconds_unknown += 1
            screening_cpu_units_unknown += 1
            continue
        invocation = row.get("invocation")
        seconds = invocation.get("seconds") if isinstance(invocation, dict) else None
        if type(seconds) in (int, float) and seconds >= 0:
            cpu_seconds += float(seconds)
        else:
            cpu_seconds_unknown += 1
        effect_known, charged_units = policy_effect_evidence(row, index)
        if effect_known and charged_units is not None:
            screening_cpu_units += charged_units
        else:
            screening_cpu_units_unknown += 1
    for index, row in enumerate(results):
        if not isinstance(row, dict):
            gaps += 1
            continue
        effect_known, _ = policy_effect_evidence(row, index)
        if not effect_known:
            gaps += 1
            continue
        if not policy_invocation_matches(row):
            gaps += 1
            continue
        frame = frames.get(row.get("frame"))
        branch_digest = row.get("branch")
        branch = branches.get(branch_digest) if isinstance(branch_digest, str) else None
        evaluation_id = bundle.get("evaluation_id")
        if (not isinstance(frame, dict)
                or row.get("frame") != bundle["frames"][index]
                or (branch_digest is not None
                    and (branch is None or branch_digest not in bundle["branches"]
                         or branch.get("frame") != row.get("frame")))):
            gaps += 1
            continue
        request = {"interface": POLICY_INTERFACE, "value": frame.get("visible"),
                   "files": {}, "context": {}}
        if row.get("request_digest") != _digest(_canonical(request)):
            gaps += 1
            continue
        invocation = row.get("invocation", {})
        resources = row.get("resources")
        seconds = invocation.get("seconds") if isinstance(invocation, dict) else None
        output = row.get("policy_output")
        output_digest = invocation.get("output_digest")
        if output_digest is not None:
            if not isinstance(output, dict) or not isinstance(output.get("files"), dict):
                gaps += 1
                continue
            output_raw = _canonical(output)
            output_manifest = {"kind": capability.CAPABILITY_SCOPE,
                               "operation_id": row.get("operation_id"),
                               "files": [{"path": "result.json", "kind": "file",
                                          "size": len(output_raw),
                                          "digest": _digest(output_raw)}]}
            expected_output = _digest(artifacts.package_bytes(
                output_manifest, {"result.json": output_raw}, capability.CAPABILITY_SCOPE))
            if output_digest != expected_output:
                gaps += 1
                continue
        elif output is not None:
            gaps += 1
            continue
        response = row.get("policy_result")
        invocation_status = invocation.get("status")
        if row.get("status") == "stop":
            if (invocation_status != "completed"
                    or not isinstance(response, dict) or set(response) != {"action", "reason"}
                    or response.get("action") != "stop" or not response.get("reason")):
                gaps += 1
                continue
            if (not isinstance(output, dict) or output.get("value") != response
                    or output.get("files") != {}
                    or row.get("branch") is not None
                    or row.get("continuation_query") is not None):
                gaps += 1
                continue
            stops += 1
            continue
        if row.get("status") == "refused":
            if (not isinstance(row.get("reason"), str) or not row["reason"]
                    or (invocation_status == "completed"
                        and (not isinstance(output, dict) or output.get("value") != response
                             or not isinstance(output.get("files"), dict)))
                    or (invocation_status != "completed"
                        and (output_digest is not None or output is not None))
                    or row.get("branch") is not None
                    or row.get("continuation_query") is not None):
                gaps += 1
                continue
            refusals += 1
            continue
        if (row.get("status") != "choose" or invocation_status != "completed"
                or not isinstance(response, dict)
                or response.get("action") != "choose"
                or response.get("opportunity_id") != row.get("selected")
                or set(response) != {"action", "opportunity_id"}
                or not isinstance(output, dict) or output.get("value") != response
                or output.get("files") != {}
                or row.get("selected") not in frame.get("starts", {})):
            gaps += 1
            continue
        if max_decisions == 2:
            if row.get("continuation_query") != {
                    "status": "gap", "reason": "recorded child frame is missing"}:
                gaps += 1
                continue
            continuation_gaps += 1
            gaps += 1
        elif row.get("continuation_query") is not None:
            gaps += 1
            continue
        expected_branch = branch_index.get((row["frame"], row["selected"]))
        if row.get("branch") != expected_branch:
            gaps += 1
            continue
        if branch is None:
            if (row.get("branch_status") != "gap" or row.get("outcome") is not None
                    or row.get("quality") is not None):
                gaps += 1
                continue
            gaps += 1
            continue
        if (row.get("selected") != branch.get("opportunity_id")
                or row.get("branch_status") != branch.get("status")
                or row.get("outcome") != branch.get("outcome")
                or row.get("quality") != branch.get("quality")
                or branch.get("status") != "supported"
                or branch.get("quality") != {"passed": branch.get("outcome") == "passed",
                                              "verdict": branch.get("outcome")}):
            gaps += 1
            continue
        start = frame["starts"][row["selected"]]
        actual = branch.get("actual", {})
        receipts = branch.get("receipts", {})
        resources = branch.get("resources", {})
        if (branch.get("consumed_input") != start.get("visible_input")
                or any(actual.get(field) != start.get(field)
                       for field in ("task", "genome", "model", "evaluator_version"))
                or any(actual.get("runtime", {}).get(key) != value
                       for key, value in start.get("runtime", {}).items())
                or any(not start.get("runtime", {}).get(key)
                       for key in (("execution_version", "python_version",
                                    "python_executable", "implementation")
                                   if start.get("method") is not None
                                   else ("execution_version",)))
                or not receipts.get("worker") or not receipts.get("verifier")
                or resources.get("worker") is None or resources.get("verifier") is None
                or not row.get("invocation", {}).get("output_digest")):
            gaps += 1
            continue
        supported += 1
        if row.get("outcome") == "passed":
            passed += 1
        elif row.get("outcome") == "failed":
            failed += 1
        else:
            gaps += 1
            supported -= 1
    return {"supported": supported, "gaps": gaps, "stops": stops,
            "refusals": refusals, "passed": passed, "failed": failed,
            "continuation_gaps": continuation_gaps,
            "screening_cpu_seconds": cpu_seconds,
            "screening_cpu_seconds_unknown": cpu_seconds_unknown,
            "screening_cpu_units": (screening_cpu_units
                                    if screening_cpu_units_unknown == 0 else None),
            "screening_cpu_units_known": screening_cpu_units,
            "screening_cpu_units_unknown": screening_cpu_units_unknown}
