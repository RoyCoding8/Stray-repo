"""Recompute a frozen P05 arm from public exports, without opening a database."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from rsi.agenda_policy import rank


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _package(encoded: str, digest: str, scope: str) -> dict:
    try:
        raw = base64.b64decode(encoded, validate=True)
        package = json.loads(raw)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"{scope} artifact is malformed") from exc
    if _sha(raw) != digest or package.get("scope") != "rsi-" + scope:
        raise ValueError(f"{scope} artifact digest or scope differs")
    return package


def _receipt(operation: dict, records: dict, operation_id: str, effect: str) -> dict:
    row = records.get(operation_id)
    if not isinstance(row, dict) or row.get("operation", {}).get("id") != operation_id:
        raise ValueError(f"missing {effect} operation export")
    op = row["operation"]
    if (op.get("payload", {}).get("effect") != effect or op.get("settled") is not True
            or op.get("dispatch_state") not in {"observed", "reconciled"}):
        raise ValueError(f"{effect} operation was not settled")
    receipts = row.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != 1:
        raise ValueError(f"{effect} operation must have one receipt")
    receipt = receipts[0]
    content = receipt.get("content") if isinstance(receipt, dict) else None
    if (not isinstance(content, dict)
            or not isinstance(receipt.get("receipt_identity"), str)
            or operation_id not in receipt["receipt_identity"]
            or receipt.get("outcome") not in {"success", "failure", "unknown"}):
        raise ValueError(f"{effect} receipt is missing, swapped, or altered")
    if effect == "agent-run":
        if (content.get("operation_id") != operation_id
                or content.get("response_digest") != content.get("trajectory_digest")
                or (content.get("status") == "completed") != (receipt.get("outcome") == "success")):
            raise ValueError("agent-run receipt is not bound to its operation trajectory")
        return {"operation": op, "receipt": receipt, "result": content}
    if content.get("_verdict") != receipt.get("outcome"):
        raise ValueError(f"{effect} receipt verdict differs from its stored outcome")
    data = content.get("data", {})
    worker = data.get("worker") if isinstance(data, dict) else None
    if (content.get("parse") != "typed-json" or not isinstance(worker, dict)
            or type(data.get("supervised")) is not bool):
        return {"operation": op, "receipt": receipt, "result": None}
    status = "ok" if receipt["outcome"] == "success" else "error"
    if worker.get("status") != status or not isinstance(worker.get("data"), dict):
        raise ValueError(f"{effect} receipt differs from typed result")
    return {"operation": op, "receipt": receipt, "result": worker["data"]}


def _task_solution(report: dict, solution: str, task_id: str) -> dict:
    try:
        package = _package(report["artifacts"][solution], solution, "solution")
        manifest = package["manifest"]
        files = {name: bytes.fromhex(value) for name, value in package["files"].items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("P01 solution package is missing or malformed") from exc
    entries = [{"path": name, "kind": "file", "size": len(data), "digest": _sha(data)}
               for name, data in sorted(files.items())]
    if (manifest.get("kind") != "rsi-solution" or manifest.get("task") != task_id
            or manifest.get("files") != entries):
        raise ValueError("solution bytes are not bound to the selected Task")
    return package


def _verify_choice(report: dict, choice: dict, ack: dict, task_id: str,
                   genome_id: str, task_package: dict, operations: dict) -> dict:
    inv_id = choice.get("investigation_id")
    history = report.get("investigations", {}).get(inv_id)
    if not isinstance(history, dict) or history.get("state", {}).get("config", {}).get(
            "task") != task_id or history["state"].get("config", {}).get("genome") != genome_id:
        raise ValueError("P01 investigation is bound to the wrong task or genome")
    decision_id = ack.get("decision_id")
    decisions = [row for row in history.get("decisions", [])
                 if row.get("id") == decision_id and row.get("kind") == "worker"]
    if len(decisions) != 1:
        raise ValueError("agenda acknowledgement lacks its exact P01 worker decision")
    data = decisions[0]["data"]
    attempt_id, worker_id = data.get("attempt_id"), data.get("operation_id")
    if (attempt_id != ack.get("attempt_id") or worker_id != ack.get("operation_id")
            or not attempt_id or not worker_id):
        raise ValueError("agenda acknowledgement differs from P01 operation identity")
    worker = _receipt(None, operations, worker_id, "agent-run")
    if ack.get("receipts", {}).get("worker") != operations[worker_id].get("receipts"):
        raise ValueError("acknowledgement worker receipt differs from operation export")
    payload = worker["operation"].get("payload", {}).get("payload", {})
    if (worker["operation"].get("attempt_id") != attempt_id
            or payload.get("task") != task_id or payload.get("genome") != genome_id):
        raise ValueError("worker operation does not match P01 Task and Genome")
    observation = ack.get("observation")
    observations = [row.get("content") for row in history.get("observations", [])
                    if row.get("decision_id") == decision_id]
    if len(observations) != 1 or observations[0] != observation:
        raise ValueError("acknowledged P01 observation is missing or changed")
    if observation.get("episode") != worker_id or observation.get("solution") is None:
        raise ValueError("P01 observation does not identify its worker solution")
    _task_solution(report, observation["solution"], task_id)
    tests = task_package.get("manifest", {}).get("test_files")
    evaluator = task_package.get("manifest", {}).get("evaluator_version")
    if not isinstance(tests, list) or not tests or not isinstance(evaluator, str):
        raise ValueError("selected Task lacks a pinned pristine evaluator")
    verifier_id = "rsi-verify-" + _sha(f"{worker_id}:{evaluator}".encode())
    if observation.get("verdict") != verifier_id:
        raise ValueError("P01 observation names another verifier")
    verifier = _receipt(None, operations, verifier_id, "sandbox-exec")
    if ack.get("receipts", {}).get("verifier") != operations[verifier_id].get("receipts"):
        raise ValueError("acknowledgement verifier receipt differs from operation export")
    verify_op = verifier["operation"]
    verify_payload = verify_op.get("payload", {}).get("payload", {})
    argv = verify_payload.get("argv")
    if (verify_op.get("attempt_id") != attempt_id
            or verify_op.get("execution_version") != observation["solution"]
            or not isinstance(argv, list) or len(argv) <= len(tests)
            or not str(argv[-len(tests) - 1]).endswith("_rsi_verify.py")
            or argv[-len(tests):] != tests):
        raise ValueError("pristine verifier operation is detached from the solution or Task")
    result = verifier["result"]
    if result is None:
        if observation.get("passed") is not None or observation.get("status") not in {
                "infra_failed", "timeout"}:
            raise ValueError("unscored verifier receipt was reported as a task result")
        return {"status": "unscored"}
    counts = [result.get(key) for key in ("tests", "failures", "errors", "skipped")]
    if any(type(value) is not int for value in counts) or counts[0] < 1 or any(v < 0 for v in counts):
        raise ValueError("pristine verifier receipt lacks typed test counts")
    passed = verifier["receipt"]["outcome"] == "success" and counts[1:] == [0, 0, 0]
    status = "passed" if passed else "failed"
    if observation.get("passed") is not passed or observation.get("status") != status:
        raise ValueError("P01 verdict differs from recomputed pristine test result")
    return {"status": status, "tests": counts[0], "failures": counts[1],
            "errors": counts[2], "skipped": counts[3]}


def _verify_prior(report: dict, task_id: str, genome_id: str,
                  task_package: dict, operations: dict) -> None:
    claim = report.get("initial_claim", {})
    history = report.get("initial_investigation", {})
    supports = claim.get("support", [])
    observed = next((row for row in history.get("observations", [])
                    if row.get("id") in supports and row.get("content", {}).get("passed") is True), None)
    if claim.get("status") != "supported" or claim.get("version") != 1 or observed is None:
        raise ValueError("initial supported lesson lacks its checked source observation")
    decision = next((row for row in history.get("decisions", [])
                     if row.get("id") == observed.get("decision_id")
                     and row.get("kind") == "worker"), None)
    if decision is None:
        raise ValueError("initial checked observation lacks its P01 worker decision")
    data = decision["data"]
    worker = _receipt(None, operations, data.get("operation_id"), "agent-run")
    payload = worker["operation"].get("payload", {}).get("payload", {})
    if (data.get("attempt_id") != worker["operation"].get("attempt_id")
            or payload.get("task") != task_id or payload.get("genome") != genome_id):
        raise ValueError("initial lesson source is not bound to the frozen task and genome")
    solution = observed["content"].get("solution")
    _task_solution(report, solution, task_id)
    evaluator = task_package.get("manifest", {}).get("evaluator_version")
    verifier_id = "rsi-verify-" + _sha(f"{data['operation_id']}:{evaluator}".encode())
    verifier = _receipt(None, operations, verifier_id, "sandbox-exec")
    result = verifier["result"]
    if (result is None or verifier["operation"].get("attempt_id") != data.get("attempt_id")
            or verifier["operation"].get("execution_version") != solution
            or verifier["receipt"].get("outcome") != "success"
            or result.get("failures") != 0 or result.get("errors") != 0):
        raise ValueError("initial lesson is not supported by a pristine passing verifier")


def recompute(frozen: dict, report: dict) -> dict:
    """Validate one frozen campaign arm and independently grade its task receipts."""
    if frozen.get("schema") != "p05-agenda-freeze/1" or report.get("schema") != "p05-agenda-arm/1":
        raise ValueError("unsupported P05 freeze or report")
    if report.get("freeze_sha256") != _sha(_canonical(frozen)):
        raise ValueError("report is bound to a different freeze")
    try:
        scenario = json.loads(base64.b64decode(frozen["scenario"], validate=True))
        arm_id = report["arm_id"]
        arm = scenario["arms"][arm_id]
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("report arm is absent from the frozen scenario") from exc
    initial = scenario.get("initial_evidence", {})
    claim = report.get("initial_claim")
    if (not isinstance(claim, dict)
            or report.get("initial_evidence_sha256") != scenario.get("initial_evidence_sha256")
            or claim.get("claim_id") != initial.get("claim_id")
            or claim.get("version") != initial.get("version")
            or claim.get("source") != "authored-from-scripted-pristine-example"):
        raise ValueError("initial lesson identity differs from the frozen evidence")
    agenda = report.get("agenda_export", {})
    state = agenda.get("agenda", {})
    if (report.get("agenda_id") != arm["agenda_id"] or report.get("policy") != arm["policy"]
            or state.get("agenda_id") != arm["agenda_id"]
            or state.get("charter_digest") != hashlib.sha256(
                _canonical(arm["charter"])).hexdigest()
            or state.get("charter") != arm["charter"]):
        raise ValueError("agenda identity or charter differs from freeze")
    rows = agenda.get("decisions", [])
    choices = [row["data"] for row in rows if row.get("kind") == "p05.choice"]
    acks = [row["data"] for row in rows if row.get("kind") == "p05.ack"]
    if not choices or len(choices) > scenario["choice_cap"]:
        raise ValueError("campaign exceeds its cap or has no choices")
    ack_by_choice = {row.get("choice_id"): row for row in acks}
    if None in ack_by_choice or len(ack_by_choice) != len(acks):
        raise ValueError("agenda acknowledgements are duplicated or unidentified")
    operations = {row.get("operation_id", row.get("operation", {}).get("id")): row
                  for row in report.get("operations", [])}
    if len(operations) != len(report.get("operations", [])):
        raise ValueError("operation exports are duplicated or unidentified")
    expected_roots = [arm["charter"]["allocations"][domain]["id"]
                      for domain in ("tokens", "cpu")]
    if report.get("allocation_ids") != expected_roots:
        raise ValueError("reported allocation roots differ from the frozen charter")
    catalog = {row["id"]: row for row in arm["charter"]["opportunities"]}
    packages = report.get("task_packages", {})
    genome_package = _package(report.get("genome_package"), arm["genome_id"], "genome")
    if not genome_package.get("files"):
        raise ValueError("published Genome package is empty")
    source_task = scenario["initial_evidence"]["task_id"]
    _verify_prior(report, source_task, arm["genome_id"],
                  _package(packages[source_task], source_task, "task"), operations)
    results, used_feedback = [], []
    for choice in choices:
        ack = ack_by_choice.get(choice.get("choice_id"))
        option = catalog.get(choice.get("opportunity_id"))
        if option is None or choice.get("policy") != arm["policy"]:
            raise ValueError("selected choice is outside the frozen catalogue or policy")
        task_id, genome_id = option["task_id"], option["genome_id"]
        task_package = _package(packages.get(task_id), task_id, "task")
        if task_package.get("manifest", {}).get("split") != "dev":
            raise ValueError("selected task is not a development task")
        if ack is None:
            inv_id = choice.get("investigation_id")
            history = report.get("investigations", {}).get(inv_id)
            config = history.get("state", {}).get("config", {}) if isinstance(history, dict) else {}
            if config.get("task") != task_id or config.get("genome") != genome_id:
                raise ValueError("unacknowledged choice lacks its pinned P01 identity")
            expected_ops = {row.get("data", {}).get("operation_id")
                            for row in history.get("decisions", []) if row.get("kind") == "worker"}
            expected_ops.update(row.get("content", {}).get("verdict")
                                for row in history.get("observations", []))
            expected_ops.update(row.get("id") for row in history.get("unresolved_effects", []))
            expected_ops.discard(None)
            if not expected_ops <= operations.keys():
                raise ValueError("unacknowledged P01 effects are absent from the export")
            for operation_id in expected_ops:
                row = operations[operation_id]
                op = row.get("operation")
                if op is not None:
                    payload = op.get("payload", {}).get("payload", {})
                    if (op.get("id") != operation_id or payload.get("task") != task_id
                            or payload.get("genome") != genome_id):
                        raise ValueError("unacknowledged P01 operation has a different identity")
            results.append({"status": "unscored", "reason": "choice lacks settled acknowledgement",
                            "accounted_operations": sorted(expected_ops)})
            continue
        if choice.get("choice_id") != ack.get("choice_id"):
            raise ValueError("agenda acknowledgement is paired with a different choice")
        ranked = choice.get("ranked")
        if not isinstance(ranked, list) or rank(ranked, arm["policy"]) != ranked:
            raise ValueError("choice ranking does not recompute under the frozen policy")
        if not ranked or ranked[0].get("id") != choice["opportunity_id"]:
            raise ValueError("agenda chose a different option from its ranked list")
        if option.get("scope_probe") and any(row.get("id") == option["id"] and row.get("triggered")
                                              for row in ranked):
            source_id = option["scope_probe"]["source_opportunity_id"]
            source = next((row for row in choices if row.get("opportunity_id") == source_id), None)
            if source is None:
                raise ValueError("scope feedback refers to an unselected source opportunity")
            refs = {(row["claim_id"], row["version"])
                    for row in option["scope_probe"]["lesson_refs"]}
            history = report["investigations"].get(source["investigation_id"], {})
            source_ack = next((row for row in acks if row.get("choice_id") == source.get("choice_id")), None)
            if source_ack is None:
                raise ValueError("scope feedback source lacks a settled acknowledgement")
            source_worker = next((row for row in history.get("decisions", [])
                                  if row.get("kind") == "worker" and row.get("id") == source_ack.get("decision_id")), None)
            if source_worker is None:
                raise ValueError("scope feedback source lacks its P01 worker")
            visible = (source_worker.get("data", {}).get("visible_input", {})
                       .get("context_packet", {}).get("memory_view", {}))
            visible_refs = {(row.get("claim_id"), row.get("version"))
                            for row in visible.get("claims", []) if isinstance(row, dict)}
            if not refs <= visible_refs:
                raise ValueError("scope feedback lesson was disconnected from the worker context")
            result = _verify_choice(report, source, source_ack,
                                    catalog[source_id]["task_id"], genome_id,
                                    _package(packages[catalog[source_id]["task_id"]],
                                             catalog[source_id]["task_id"], "task"), operations)
            if result["status"] != "failed":
                raise ValueError("scope feedback did not follow a checked failed experience")
            no_feedback = [{**row, "triggered": False} for row in ranked]
            control = rank(no_feedback, arm["policy"])
            changed = bool(control and control[0]["id"] != ranked[0]["id"])
            if not control or (arm["policy"] == "adaptive/1") != changed:
                raise ValueError("policy feedback did not match the selected opportunity")
            used_feedback.append({"source": source_id, "selected": ranked[0]["id"],
                                  "without_feedback": control[0]["id"],
                                  "changed_selection": changed})
        result = _verify_choice(report, choice, ack, task_id, genome_id, task_package, operations)
        results.append(result)
    return {"schema": "p05-agenda-recomputed/1", "arm": arm_id,
            "evidence_basis": "attested runtime exports; no independent provider authentication",
            "choices": len(choices), "verified": sum(r["status"] == "passed" for r in results),
            "failed": sum(r["status"] == "failed" for r in results),
            "unscored": sum(r["status"] == "unscored" for r in results),
            "feedback_effects": used_feedback, "task_results": results}


def recompute_pair(frozen: dict, reports: list[dict]) -> dict:
    """Compare seed/adaptive exports after validating each arm independently."""
    if len(reports) != 2:
        raise ValueError("paired comparison requires exactly two arm reports")
    by_id = {report.get("arm_id"): report for report in reports}
    if by_id.keys() != {"seed", "adaptive"}:
        raise ValueError("paired comparison must include seed and adaptive arms")
    grades = {arm_id: recompute(frozen, report) for arm_id, report in by_id.items()}
    scenario = json.loads(base64.b64decode(frozen["scenario"], validate=True))
    seed, adaptive = by_id["seed"], by_id["adaptive"]
    seed_arm, adaptive_arm = scenario["arms"]["seed"], scenario["arms"]["adaptive"]
    seed_tasks = {item["id"]: item["task_id"] for item in seed_arm["charter"]["opportunities"]}
    adaptive_tasks = {item["id"]: item["task_id"]
                      for item in adaptive_arm["charter"]["opportunities"]}
    roots = [seed.get("allocation_ids"), adaptive.get("allocation_ids")]
    seed_source = [row.get("content") for row in seed.get("initial_investigation", {}).get(
        "observations", [])]
    adaptive_source = [row.get("content") for row in adaptive.get("initial_investigation", {}).get(
        "observations", [])]
    if (seed_tasks != adaptive_tasks or seed_arm["genome_id"] != adaptive_arm["genome_id"]
            or seed.get("initial_evidence_sha256") != scenario["initial_evidence_sha256"]
            or adaptive.get("initial_evidence_sha256") != scenario["initial_evidence_sha256"]
            or seed.get("initial_claim") != adaptive.get("initial_claim")
            or seed_source != adaptive_source
            or any(not isinstance(row, list) or len(row) != 2 for row in roots)
            or set(roots[0]) & set(roots[1])
            or not any(row["changed_selection"] is False
                       for row in grades["seed"]["feedback_effects"])
            or not any(row["changed_selection"] is True
                       for row in grades["adaptive"]["feedback_effects"])):
        raise ValueError("arms do not share initial evidence or isolate their allocation pools")
    return {"schema": "p05-agenda-pair/1", "arms": grades,
            "evidence_basis": "attested runtime exports; no independent provider authentication",
            "same_task_packages": True, "same_genome": True,
            "same_initial_evidence": True, "separate_allocation_pools": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--paired-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    frozen = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if args.paired_report:
        result = recompute_pair(frozen, [report, json.loads(
            args.paired_report.read_text(encoding="utf-8"))])
    else:
        result = recompute(frozen, report)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
