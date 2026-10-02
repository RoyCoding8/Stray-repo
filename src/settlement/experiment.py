"""S3 §11 A/B/C harness: fixed baseline vs textual lessons vs invocable methods.

Arms run under matched information and resources: same tools, same per-task
sandbox budgets, same evaluator. Construction and retrieval costs count in
B/C totals. A fresh attempt per task invokes the retained method through the
broker in arm C; the harness asserts the operation and receipt exist, never
just output equality. Scripted doubles label everything ``simulated=True``;
a real gateway adapter may be passed unchanged with ``simulated=False``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from . import broker, capabilities, db, evaluation, store, trials
from .common import Command, ResultCode, SettlementError

GRADER_TIMEOUT_MS = 30_000
GRADER_MAX_BYTES = 65_536
MODEL_TOKENS = 512

LIVE_COMMAND = ("uv run python experiments/run_live_abc.py --dsn $SETTLEMENT_DSN"
                " --allocation live-abc --artifacts-root $ARTIFACT_ROOT")
LIVE_INPUTS = ("SETTLEMENT_GATEWAY_URL (endpoint URL), SETTLEMENT_GATEWAY_KEY"
               " (key env var), SETTLEMENT_GRANT_UNITS (monetary grant cap)")


def live_blocker() -> dict:
    return {"blocked": True, "command": LIVE_COMMAND, "required_inputs": LIVE_INPUTS}


def _sandbox_receipt(dsn: str, operation_id: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s"
                        " ORDER BY created_at", (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows[-1] if rows else None


def _run_sandbox(dsn: str, launcher: Any, tag: str, argv: list[str],
                 allocation_id: str, attempt_id: str | None) -> tuple[str, dict | None]:
    operation_id = f"{tag}"
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile, "argv": argv,
                 "timeout_ms": GRADER_TIMEOUT_MS,
                 "max_output_bytes": GRADER_MAX_BYTES},
        allocation_id=allocation_id, attempt_id=attempt_id)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"operation {tag} not admitted: {ensured.detail}")
    broker.dispatch_operation(dsn, operation_id,
                              launchers={launcher.profile: launcher})
    return operation_id, _sandbox_receipt(dsn, operation_id)


def _worker_data(receipt: dict | None) -> dict:
    content = dict((receipt or {}).get("content") or {})
    worker = (content.get("data") or {}).get("worker") or {}
    return worker if isinstance(worker, dict) else {}


def _grade(dsn: str, launcher: Any, workdir: Path, candidate_code: str,
           cases: list, tag: str, allocation_id: str,
           attempt_id: str | None, grader_path: str) -> tuple[str, str]:
    cand_path = workdir / f"{tag}-cand.py"
    cases_path = workdir / f"{tag}-cases.json"
    cand_path.write_text(candidate_code)
    cases_path.write_text(json.dumps(cases))
    operation_id, receipt = _run_sandbox(
        dsn, launcher, f"grade-{tag}",
        [sys.executable, grader_path, str(cand_path), str(cases_path)],
        allocation_id, attempt_id)
    worker = _worker_data(receipt)
    data = worker.get("data", {}) if isinstance(worker.get("data"), dict) else {}
    if worker.get("status") == "ok" and data.get("failed", 1) == 0 and \
            data.get("passed", 0) > 0:
        return operation_id, "success"
    if (receipt or {}).get("outcome") == "failure" and \
            dict((receipt.get("content") or {}).get("data", {})).get("timed_out"):
        return operation_id, "timeout"
    return operation_id, "failure"


def _retrieve_capability(dsn: str, family: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM capability_versions ORDER BY created_at")
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    for row in rows:
        applicability = dict(row["applicability"] or {})
        if applicability.get("family", row["family"]) == family and \
                capabilities.quarantine_status(dsn, row["id"]) is None:
            return row
    return None


def _invoke_method(dsn: str, launcher: Any, workdir: Path, artifacts_root: Path,
                   capability: dict, broken_code: str, tag: str,
                   allocation_id: str, attempt_id: str) -> str:
    raw = (artifacts_root / capability["artifact_digest"]).read_bytes()
    package = json.loads(raw.decode())
    files = {rel: bytes.fromhex(h) for rel, h in package["files"].items()}
    manifest = package["manifest"]
    entry = next(e["path"] for e in manifest["files"]
                 if e.get("kind", "file") != "dir" and e["path"].endswith(".py"))
    method_path = workdir / f"{tag}-method.py"
    method_path.write_bytes(files[entry])
    broken_path = workdir / f"{tag}-broken.py"
    fixed_path = workdir / f"{tag}-fixed.py"
    broken_path.write_text(broken_code)
    operation_id, receipt = _run_sandbox(
        dsn, launcher, f"invoke-{tag}",
        [sys.executable, str(method_path), str(broken_path), str(fixed_path)],
        allocation_id, attempt_id)
    worker = _worker_data(receipt)
    if worker.get("status") != "ok" or not fixed_path.exists():
        raise SettlementError(f"method invocation {operation_id} failed")
    proven = broker.read_operation(dsn, operation_id) or {}
    if proven.get("dispatch_state") not in ("observed", "reconciled") or receipt is None:
        raise SettlementError(f"method invocation {operation_id} left no receipt")
    return fixed_path.read_text()


def run_abcs(dsn: str, *, launcher: Any, artifacts_root: str | Path,
             allocation_id: str, investigation_id: str, tasks: list[dict],
             dev_ids: list[str], panel_ids: list[str], transfer_ids: list[str],
             lessons: dict[str, str], double: Any,
             grader_path: str, protocol_prefix: str = "abc",
             fixer_version: str = "", evaluator_id: str = "s3-eval",
             evaluator_version: str = "v1", simulated: bool = True) -> dict:
    roots = Path(artifacts_root)
    workdir = Path(tempfile.mkdtemp(prefix="abc-"))
    evaluation.register_evaluator(
        dsn, Command(request_id=f"{protocol_prefix}-eval"),
        evaluator_id, evaluator_version, {"scope": "protected-eval"})
    by_id = {t["id"]: t for t in tasks}
    for task in tasks:
        evaluation.propose_hidden_answer(
            dsn, Command(request_id=f"{protocol_prefix}-answer-{task['id']}"),
            task["id"], {"cases": task["cases"]})
    protocols = {}
    for name, task_ids, cand, group in [
            ("panel-B", panel_ids, "lessons-v1", "panel"),
            ("panel-C", panel_ids, fixer_version or "fixer-v1", "panel"),
            ("transfer-B", transfer_ids, "lessons-v1", "transfer"),
            ("transfer-C", transfer_ids, fixer_version or "fixer-v1", "transfer")]:
        pid = f"{protocol_prefix}-{name}"
        trials.freeze_protocol(
            dsn, Command(request_id=f"{pid}-freeze"), protocol_id=pid,
            candidate_version=cand, reference_version="baseline-v0",
            evaluator_version=evaluator_version,
            task_groups=[{"name": "development", "kind": "development"},
                         {"name": group, "kind": "protected-eval"}],
            budgets={"per_task_sandbox_ms": GRADER_TIMEOUT_MS,
                     "per_task_tokens": MODEL_TOKENS,
                     "amortization_horizon": {"tasks": 50}},
            metrics=["success_rate"], stopping={"rule": "fixed-panel"},
            exclusions=[], uncertainty={"treatment": "finite-panel-only"})
        protocols[name] = pid
    construction = broker.exposure_schedule(
        broker.SANDBOX_EXEC, {"profile": "local-process", "argv": ["x"],
                              "timeout_ms": GRADER_TIMEOUT_MS,
                              "max_output_bytes": GRADER_MAX_BYTES}, 0)[0]
    for pid in set(protocols.values()):
        trials.record_expenditure(dsn, pid, "construction", construction,
                                  "method verification + lesson authoring")
    retrieval_model = broker.exposure_schedule(
        broker.MODEL_INFERENCE, {"model": "scripted", "messages": [
            {"role": "user", "content": lessons.get("off_by_one", "") or "x"}],
            "max_output_tokens": MODEL_TOKENS, "deadline_ms": 300_000}, 0)[0]
    from .gateway import ModelRequest  # noqa: PLC0415

    report: dict[str, Any] = {"arms": {}, "verdicts": {}, "budgets": {},
                              "invocations": [], "simulated": simulated,
                              "attempts": {}, "grade_ops": {}}
    op_costs: dict[str, list[int]] = {"A": [], "B": [], "C": []}
    seq = 0
    for task_id in panel_ids + transfer_ids:
        task = by_id[task_id]
        group = "panel" if task_id in panel_ids else "transfer"
        for harness_arm in ("A", "B", "C"):
            seq += 1
            tag = f"{protocol_prefix}-{harness_arm}-{task_id}-{seq}"
            attempt_id = f"{tag}-worker"
            acquired = store.acquire_work(dsn, Command(
                request_id=f"{tag}-acquire",
                payload={"attempt_id": attempt_id,
                         "investigation_id": investigation_id,
                         "allocation_id": allocation_id}))
            if acquired.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                raise SettlementError(
                    f"fresh worker {attempt_id} refused: {acquired.detail}")
            report["attempts"].setdefault(harness_arm, []).append(attempt_id)
            if harness_arm == "C":
                capability = _retrieve_capability(dsn, task["family"])
                if capability is None:
                    code = task["broken"]
                    report.setdefault("abstentions", []).append(
                        f"no-applicable-method-{tag}")
                else:
                    capabilities.pin_capability(dsn, attempt_id, capability["id"])
                    code = _invoke_method(dsn, launcher, workdir, roots, capability,
                                          task["broken"], tag, allocation_id, attempt_id)
                    report["invocations"].append(f"invoke-{tag}")
                    op_costs["C"].append(construction)
                    trials.record_expenditure(dsn, protocols[f"{group}-C"],
                                              "retrieval", construction,
                                              f"method retrieval+invoke {task_id}")
            else:
                prompt = task["broken"] if harness_arm == "A" else \
                    lessons.get(task["family"], "") + "\n" + task["broken"]
                response = double.infer(ModelRequest(
                    model="scripted", messages=({"role": "user", "content": json.dumps(
                        {"arm": harness_arm, "task_id": task_id, "prompt": prompt})},),
                    max_output_tokens=MODEL_TOKENS, deadline_ms=300_000,
                    operation_id=f"model-{tag}"))
                code = getattr(response, "text", task["broken"])
                if harness_arm == "B":
                    op_costs["B"].append(retrieval_model)
                    trials.record_expenditure(dsn, protocols[f"{group}-B"],
                                              "retrieval", retrieval_model,
                                              f"lesson retrieval {task_id}")
            op_id, outcome = _grade(dsn, launcher, workdir, code, task["cases"], tag,
                                    allocation_id, attempt_id, grader_path)
            op_costs[harness_arm].append(construction)
            report["grade_ops"].setdefault(harness_arm, {})[task_id] = op_id
            for suffix in ("-B", "-C") if harness_arm == "A" else \
                    (("-B",) if harness_arm == "B" else ("-C",)):
                pid = protocols[f"{group}{suffix}"]
                trials.record_expenditure(dsn, pid, "evaluation", construction,
                                          f"grade {tag}")
                _bind_assignment(dsn, pid, task, group, harness_arm, code, op_id,
                                 outcome, f"{tag}{suffix}", evaluator_id,
                                 evaluator_version, simulated,
                                 {"model": "scripted", "arm": harness_arm,
                                  "env": {"launcher": launcher.profile,
                                          "method": fixer_version
                                          if harness_arm == "C" else None}})
            report["arms"].setdefault(harness_arm, {})[task_id] = {
                "outcome": outcome, "grade_op": op_id, "simulated": simulated}
    for name, pid in protocols.items():
        report["verdicts"][name] = trials.verdict(dsn, pid)
    for arm in ("A", "B", "C"):
        pids = ([protocols["panel-B"], protocols["transfer-B"]] if arm == "B" else
                [protocols["panel-C"], protocols["transfer-C"]] if arm == "C" else
                [protocols["panel-B"], protocols["panel-C"],
                 protocols["transfer-B"], protocols["transfer-C"]])
        by_cat: dict[str, int] = {}
        for pid in set(pids):
            for cat, amount in trials.development_expenditure(
                    dsn, pid)["by_category"].items():
                by_cat[cat] = by_cat.get(cat, 0) + amount
        unique_ops = sum(op_costs[arm])
        report["budgets"][arm] = {"ledger_by_category": by_cat,
                                  "unique_op_cost": unique_ops,
                                  "matched_caps": {"sandbox_ms": GRADER_TIMEOUT_MS,
                                                   "tokens": MODEL_TOKENS}}
    return report


def _bind_assignment(dsn: str, protocol_id: str, task: dict, group: str,
                     harness_arm: str, code: str, op_id: str, outcome: str,
                     tag: str, evaluator_id: str, evaluator_version: str,
                     simulated: bool, conditions: dict | None = None) -> None:
    arm = "candidate" if harness_arm in ("B", "C") else "reference"
    assignment_id = f"{protocol_id}:{arm}:{task['id']}"
    trials.assign(dsn, Command(request_id=f"{tag}-assign"), protocol_id,
                  task["id"], group, arm, {"entry_fn": task["entry_fn"]})
    evaluation.submit_candidate(dsn, Command(request_id=f"{tag}-cand"),
                                assignment_id, {"code": code})
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id=f"{tag}-receipt"), receipt_id=f"eval-{tag}",
        assignment_id=assignment_id, evaluator_id=evaluator_id,
        evaluator_version=evaluator_version, invocation_ref=op_id,
        result={"outcome": outcome, "detail": {"task_id": task["id"]},
                "conditions": conditions or {}, "cost": {},
                "simulated": simulated})
