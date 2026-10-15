"""Offline verifier for an exported P04 construction-and-reuse bundle."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from rsi.genome import Genome


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _genome(doc):
    if not isinstance(doc, dict) or set(doc) != {"digest", "files", "package"}:
        raise ValueError("genome export must contain digest, files, and package")
    if not isinstance(doc["files"], dict) or any(not isinstance(raw, str)
                                                  for raw in doc["files"].values()):
        raise ValueError("genome file bytes must be lowercase hex strings")
    try:
        genome = Genome({name: bytes.fromhex(raw) for name, raw in doc["files"].items()})
    except (ValueError, TypeError) as exc:
        raise ValueError("genome file bytes are malformed") from exc
    if genome.digest != doc["digest"]:
        raise ValueError("genome package digest mismatch")
    try:
        package_raw = base64.b64decode(doc["package"], validate=True)
        package = json.loads(package_raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("published genome package is missing or malformed") from exc
    if (_sha(package_raw) != genome.digest or package.get("scope") != "rsi-genome"
            or package.get("files") != {name: raw.hex() for name, raw in genome.files.items()}):
        raise ValueError("published genome artifact differs from exported genome closure")
    return genome


def _task_reference(task):
    try:
        package_raw = base64.b64decode(task["package"], validate=True)
        package = json.loads(package_raw)
        reference = {name.removeprefix("reference/"): bytes.fromhex(raw).decode("utf-8")
                     for name, raw in package["files"].items()
                     if name.startswith("reference/")}
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("published Task package is missing or malformed") from exc
    if (_sha(package_raw) != task.get("digest") or package.get("scope") != "rsi-task"
            or package.get("manifest", {}).get("split") != task.get("split")
            or reference != task.get("reference")):
        raise ValueError("pristine task package differs from exported solution reference")
    return reference


def _construction_record(report, *, settled, outcome="success"):
    operation_id = report.get("construction_operation_id")
    matches = [item for item in report.get("operations", [])
               if isinstance(item, dict)
               and isinstance(item.get("operation"), dict)
               and item["operation"].get("id") == operation_id]
    if len(matches) != 1:
        raise ValueError("construction operation is missing or ambiguous in journal export")
    record = matches[0]
    operation = record["operation"]
    payload = operation.get("payload")
    if (not isinstance(payload, dict) or payload.get("effect") != "agent-run"
            or not isinstance(payload.get("payload"), dict)):
        raise ValueError("construction operation does not bind the agent-run effect")
    receipts = record.get("receipts")
    if not isinstance(receipts, list):
        raise TypeError("construction receipt export is malformed")
    if settled:
        if (operation.get("dispatch_state") not in ("observed", "reconciled")
                or len(receipts) != 1 or receipts[0].get("outcome") != outcome):
            raise ValueError("construction lacks one settled broker receipt with matching outcome")
        content = receipts[0].get("content")
        trajectory_digest = report.get("construction", {}).get("trajectory")
        try:
            trajectory_raw = base64.b64decode(
                report["artifact_bytes"][trajectory_digest], validate=True)
            trajectory = json.loads(trajectory_raw)
            file_digests = {item.get("digest") for item in
                            trajectory["manifest"]["files"]}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("constructor trajectory artifact is malformed") from exc
        if (not isinstance(content, dict)
                or content.get("operation_id") != operation_id
                or content.get("response_digest") != content.get("trajectory_digest")
                or content.get("trajectory_digest") not in file_digests):
            raise ValueError("constructor receipt does not bind its captured trajectory")
    return record


def _check_construction_evidence(report, record):
    construction = report["construction"]
    evidence_digest = construction.get("evidence")
    try:
        package_raw = base64.b64decode(report["artifact_bytes"][evidence_digest], validate=True)
        package = json.loads(package_raw)
        evidence = json.loads(bytes.fromhex(package["files"]["evidence.json"]))
        request = evidence["construction"]
        context_packet = evidence["context_packet"]
        evidence_bytes = bytes.fromhex(package["files"]["evidence.json"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("constructor evidence artifact is missing or malformed") from exc
    expected = {key: construction.get(key) for key in (
        "parent", "name", "interface", "context_digest", "operation_id",
        "model", "allocation_id", "timeout_ms", "token_ceiling")}
    if (package.get("scope") != "rsi-dev-evidence"
            or package.get("manifest", {}).get("kind") != "rsi-dev-evidence"
            or package["manifest"].get("files") != [{
                "path": "evidence.json", "digest": _sha(evidence_bytes),
                "size": len(evidence_bytes), "kind": "file"}]
            or request != expected
            or _sha(_canonical(context_packet)) != construction.get("context_digest")):
        raise ValueError("constructor evidence does not bind the recorded request and context")
    operation = record["operation"]
    payload = operation["payload"]["payload"]
    if (payload.get("task") != evidence_digest
            or payload.get("genome") != construction.get("parent")
            or payload.get("timeout_ms") != construction.get("timeout_ms")
            or payload.get("token_ceiling") != construction.get("token_ceiling")):
        raise ValueError("constructor operation does not consume the captured evidence")


def _worker_result(report, operation_id, *, status="ok"):
    outcome = "success" if status == "ok" else "failure"
    matches = [item for item in report.get("operations", [])
               if isinstance(item, dict)
               and isinstance(item.get("operation"), dict)
               and item["operation"].get("id") == operation_id]
    if len(matches) != 1:
        raise ValueError("execution operation is missing or ambiguous in journal export")
    record = matches[0]
    operation = record["operation"]
    payload = operation.get("payload")
    if (not isinstance(payload, dict) or payload.get("effect") != "sandbox-exec"
            or not isinstance(payload.get("payload"), dict)):
        raise ValueError("execution operation does not bind sandbox-exec")
    receipts = record.get("receipts")
    if (operation.get("dispatch_state") not in ("observed", "reconciled")
            or operation.get("settled") is not True
            or not isinstance(receipts, list) or len(receipts) != 1
            or not isinstance(receipts[0], dict)
            or receipts[0].get("outcome") != outcome):
        raise ValueError("execution lacks one settled broker receipt for its result")
    content = receipts[0].get("content")
    if not isinstance(content, dict):
        raise TypeError("execution receipt has no typed content")
    data = content.get("data")
    worker = data.get("worker") if isinstance(data, dict) else None
    if (content.get("_verdict") != outcome or content.get("parse") != "typed-json"
            or not isinstance(data, dict)
            or data.get("supervised") is not True or not isinstance(worker, dict)
            or worker.get("status") != status or worker.get("error") != ""
            or not isinstance(worker.get("data"), dict)):
        raise ValueError("execution receipt differs from its typed worker result")
    return record, worker["data"]


def _check_verdict(report, use, task):
    verdict = use.get("verdict")
    if (not isinstance(verdict, dict) or not isinstance(verdict.get("operation_id"), str)
            or type(verdict.get("passed")) is not bool):
        raise ValueError("method use lacks its independent verifier operation")
    try:
        task_package = json.loads(base64.b64decode(task["package"], validate=True))
        manifest = task_package["manifest"]
        test_files = manifest["test_files"]
        evaluator_version = manifest["evaluator_version"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("verifier lacks its pinned Task evaluator identity") from exc
    episode = use.get("episode", {})
    expected_id = "rsi-verify-" + _sha(
        f"{episode.get('id')}:{evaluator_version}".encode())
    if verdict["operation_id"] != expected_id:
        raise ValueError("verifier operation is not assigned to this episode and Task")
    record, result = _worker_result(report, verdict["operation_id"],
                                    status="ok" if verdict["passed"] else "error")
    operation = record["operation"]
    solution_files = use.get("solution_files")
    if not isinstance(solution_files, dict):
        raise TypeError("verifier lacks the episode's materialized solution files")
    solution_bytes = {name: value.encode("utf-8") for name, value in solution_files.items()
                      if isinstance(value, str)}
    if len(solution_bytes) != len(solution_files):
        raise ValueError("verifier solution files must be UTF-8 text")
    solution_manifest = {
        "kind": "rsi-solution", "task": task.get("digest"),
        "files": [{"path": name, "kind": "file", "size": len(raw), "digest": _sha(raw)}
                  for name, raw in sorted(solution_bytes.items())],
    }
    solution_artifact = _canonical({
        "manifest": solution_manifest, "scope": "rsi-solution",
        "files": {name: raw.hex() for name, raw in solution_bytes.items()},
    })
    argv = operation.get("payload", {}).get("payload", {}).get("argv")
    if (operation.get("execution_version") != _sha(solution_artifact)
            or operation.get("allocation_id") != use.get("allocation_id")
            or operation.get("attempt_id") != use.get("attempt_id")
            or not isinstance(argv, list) or len(argv) <= len(test_files)
            or not str(argv[-len(test_files) - 1]).endswith("_rsi_verify.py")
            or argv[-len(test_files):] != test_files):
        raise ValueError("verifier operation does not bind this Task and solution")
    if (type(result.get("tests")) is not int or result["tests"] < 1
            or type(result.get("errors")) is not int
            or type(result.get("failures")) is not int
            or type(result.get("skipped")) is not int):
        raise ValueError("verifier receipt lacks typed test results")
    passed = result["errors"] == 0 and result["failures"] == 0 and result["skipped"] == 0
    if verdict.get("passed") is not passed or verdict.get("status") != (
            "passed" if passed else "failed"):
        raise ValueError("verdict differs from its settled verifier receipt")
    return passed


def _summary(value):
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        raise ValueError("summary request value must be a list of integers")
    return {"count": len(value), "total": sum(value),
            "minimum": min(value) if value else None,
            "maximum": max(value) if value else None}


def _summary_file(files):
    if not isinstance(files, dict) or set(files) != {"summary.json"}:
        raise ValueError("solution must contain exactly summary.json")
    try:
        return json.loads(files["summary.json"])
    except (TypeError, ValueError) as exc:
        raise ValueError("summary.json is malformed") from exc


def _check_use(report, use, genome, method, expected, task, *, development=False,
               require_pass=True):
    required = {"operation_id", "requested_genome", "executed_genome", "requested_name",
                "executed_name", "method_digest", "interface", "input_digest",
                "execution_version", "status", "output_digest", "request",
                "dispatch_request", "result_artifact", "value", "files", "decision", "episode",
                "fresh_process", "operation", "allocation_id", "attempt_id", "payload_digest"}
    if not isinstance(use, dict) or required - use.keys():
        raise ValueError("use evidence is missing identity, result, or process fields")
    if (use["status"] != "completed" or use["requested_genome"] != genome.digest
            or use["executed_genome"] != genome.digest
            or use["requested_name"] != method.name
            or use["executed_name"] != method.name
            or use["method_digest"] != method.digest
            or use["interface"] != method.interface
            or not use["operation_id"] or not use["execution_version"]):
        raise ValueError("use identities do not bind the selected method")
    operation_record, worker_output = _worker_result(report, use["operation_id"])
    operation = operation_record["operation"]
    if (use["operation"] != operation
            or operation.get("execution_version") != use["execution_version"]
            or not isinstance(operation.get("payload"), dict)
            or _sha(_canonical(operation["payload"].get("payload"))) != use["payload_digest"]
            or operation.get("allocation_id") != use["allocation_id"]
            or operation.get("attempt_id") != use["attempt_id"]):
        raise ValueError("method use does not bind its journaled execution request")
    request = use["request"]
    dispatch_request = use["dispatch_request"]
    episode = use["episode"]
    if not isinstance(episode, dict):
        raise TypeError("method episode identity must be an object")
    if not isinstance(request, dict) or set(request) != {"interface", "value", "files", "context"}:
        raise ValueError("use request does not match the public method ABI")
    if (not isinstance(dispatch_request, dict)
            or set(dispatch_request) != {"interface", "value", "files", "context"}
            or not isinstance(dispatch_request["context"], dict)
            or set(dispatch_request["context"]) != {"continuation", "task_digest"}
            or dispatch_request["context"]["continuation"] != request["context"]
            or dispatch_request["context"]["task_digest"] != use["episode"].get("task_digest")
            or {**dispatch_request, "context": request["context"]} != request):
        raise ValueError("dispatch input does not preserve the public request and Task identity")
    if (request["interface"] != method.interface
            or _sha(_canonical(dispatch_request)) != use["input_digest"]):
        raise ValueError("use input digest or interface mismatch")
    if (not isinstance(task, dict) or episode.get("task_digest") != task.get("digest")
            or dispatch_request["context"]["task_digest"] != task.get("digest")):
        raise ValueError("method execution is not bound to its exported Task")
    if request["value"] != expected[0]:
        raise ValueError("method request differs from its fixed input")
    if not isinstance(use["files"], dict) or set(use["files"]) != {"summary.json"}:
        raise ValueError("method must return exactly summary.json")
    try:
        actual_file = json.loads(use["files"]["summary.json"])
    except (TypeError, ValueError) as exc:
        raise ValueError("returned summary.json is malformed") from exc
    if worker_output.get("kind") != "capability-result" or worker_output.get("output") != {
            "value": use["value"], "files": use["files"]}:
        raise ValueError("typed worker output differs from the exported method result")
    result_matches = use["value"] == expected[1] and actual_file == expected[1]

    try:
        artifact = base64.b64decode(use["result_artifact"], validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("result artifact is not valid base64") from exc
    if _sha(artifact) != use["output_digest"]:
        raise ValueError("published result artifact digest mismatch")
    try:
        package = json.loads(artifact)
        result = json.loads(bytes.fromhex(package["files"]["result.json"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("published result artifact package is malformed") from exc
    if (package.get("manifest", {}).get("operation_id") != use["operation_id"]
            or result != {"value": use["value"], "files": use["files"]}):
        raise ValueError("published result artifact does not match the use receipt")
    decision = use["decision"]
    if not isinstance(decision, dict) or any(decision.get(key) != use[key] for key in (
            "operation_id", "requested_genome", "executed_genome", "requested_name",
            "executed_name", "method_digest", "interface", "input_digest",
            "execution_version", "output_digest")):
        raise ValueError("durable capability-use decision differs from invocation")
    if (episode.get("status") != "completed" or not episode.get("id")
            or episode.get("id") != use["operation_id"]):
        raise ValueError("method episode is not completed")
    if not isinstance(episode.get("trajectory"), str):
        raise TypeError("method episode lacks its published trajectory identity")
    process = use["fresh_process"]
    if not isinstance(process, dict) or process.get("model_calls") != 0:
        raise ValueError("later method use lacks fresh model-free process evidence")
    if development:
        if process.get("execution") != "native-method-episode":
            raise ValueError("development use was not a native method episode")
    elif (process.get("exit_code") != 0 or type(process.get("pid")) is not int
          or process["pid"] <= 0):
        raise ValueError("later method use lacks a successful fresh process identity")
    if development:
        passed = _check_verdict(report, use, task)
        if passed != require_pass:
            raise ValueError("development verdict does not match the claimed outcome")
        if require_pass and (not result_matches or use.get("solution_files") != use["files"]):
            raise ValueError("passing development result differs from its pristine reference")
        if not require_pass and (result_matches or use.get("solution_files") != use["files"]):
            raise ValueError("failed-development claim does not bind the failing candidate output")
    else:
        task = use.get("task", {})
        reference = _task_reference(task)
        passed = _check_verdict(report, use, task)
        if (not passed or not result_matches
                or task.get("split") != "dev" or not task.get("digest")
                or _summary_file(reference) != expected[1]
                or _summary_file(use.get("solution_files")) != expected[1]):
            raise ValueError("changed-input method use lacks a passing pristine verifier result")
    return 1


def check_bundle(root):
    """Check hashes and use evidence without opening a database or network."""
    root = Path(root)
    manifest = _object(root / "manifest.json")
    report = _object(root / "report.json")
    if manifest.get("schema") != "p04-capability-source/1":
        raise ValueError("unsupported frozen source manifest")
    if report.get("schema") != "p04-capability-campaign/1":
        raise ValueError("unsupported campaign report")
    artifact_bytes = report.get("artifact_bytes", {})
    if not isinstance(artifact_bytes, dict):
        raise TypeError("captured artifact bytes are malformed")
    for digest, encoded in artifact_bytes.items():
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("captured artifact bytes are not valid base64") from exc
        if not isinstance(digest, str) or _sha(raw) != digest:
            raise ValueError("captured artifact bytes differ from their pinned digest")
    limits = manifest.get("limits", {})
    maximum = limits.get("max_construction_calls")
    calls = report.get("construction_calls")
    if (type(maximum) is not int or maximum < 1 or type(calls) is not int
            or calls < 0 or calls > maximum):
        raise ValueError("construction call count exceeds the frozen campaign limit")
    if report.get("source_manifest_digest") != _sha(_canonical(manifest)):
        raise ValueError("campaign report does not bind the frozen manifest")
    if report.get("status") == "unresolved":
        if report.get("construction", {}).get("status") == "unresolved":
            _construction_record(report, settled=False)
        return {"status": "unresolved", "checked_uses": 0,
                "stop": report.get("stop", report.get("construction_operation_id"))}
    failed_construction = report.get("construction", {}).get("status")
    if failed_construction in ("timeout", "infra_failed"):
        if (report.get("status") not in ("unscored", "no-acquisition") or calls != 1
                or report.get("uses") != [] or report.get("child")
                or report.get("retention") or report.get("selection")
                or report["construction"].get("child")):
            raise ValueError("unscored constructor cannot support acquisition or method use")
        record = _construction_record(report, settled=True, outcome="failure")
        _check_construction_evidence(report, record)
        if (record["operation"].get("settled") is not True
                or record["receipts"][0]["content"].get("status") != failed_construction):
            raise ValueError("unscored constructor differs from its settled failure receipt")
        return {"status": "unscored", "checked_uses": 0,
                "construction_status": failed_construction,
                "reported_status": report["status"]}
    if failed_construction in ("invalid", "failed", "no_candidate"):
        if report.get("status") != "no-acquisition" or calls != 1:
            raise ValueError("construction failure is not bound to a completed constructor attempt")
        constructor_record = _construction_record(report, settled=True)
        _check_construction_evidence(report, constructor_record)
        for key in ("evidence", "trajectory"):
            digest = report["construction"].get(key)
            if not isinstance(digest, str) or digest not in artifact_bytes:
                raise ValueError("failed constructor evidence or trajectory bytes are missing")
        return {"status": "no-acquisition", "checked_uses": 0,
                "construction_status": failed_construction}
    if failed_construction == "unresolved":
        _construction_record(report, settled=False)
        return {"status": "unresolved", "checked_uses": 0,
                "operation_id": report.get("construction_operation_id")}
    if failed_construction != "completed":
        raise ValueError("construction did not settle to completed or a candidate failure")
    if calls != 1:
        raise ValueError("completed construction must bind exactly one constructor call")
    construction_record = _construction_record(report, settled=True)
    _check_construction_evidence(report, construction_record)
    construction = report["construction"]
    for key in ("evidence", "trajectory"):
        digest = construction.get(key)
        if not isinstance(digest, str) or digest not in artifact_bytes:
            raise ValueError("constructor evidence or trajectory bytes are missing")

    parent = _genome(report.get("parent"))
    child = _genome(report.get("child"))
    construction = report["construction"]
    if (construction.get("status") != "completed" or construction.get("child") != child.digest
            or construction.get("name") != "summary"
            or construction.get("operation_id") != report.get("construction_operation_id")
            or construction_record["operation"].get("dispatch_state") not in
               ("observed", "reconciled")):
        raise ValueError("construction report does not bind the child genome")
    old = {name: raw for name, raw in parent.files.items()
           if not name.startswith("skills/summary/")}
    new = {name: raw for name, raw in child.files.items()
           if not name.startswith("skills/summary/")}
    if old != new:
        raise ValueError("construction changed bytes outside the requested skill")

    from rsi.capability import catalogue

    methods = [method for method in catalogue(child) if method.name == "summary"]
    if len(methods) != 1:
        raise ValueError("child genome does not contain exactly one summary method")
    method, = methods
    if (method.interface != "integer-summary/1"
            or construction.get("interface") != method.interface
            or construction.get("method_digest") != method.digest):
        raise ValueError("constructed method closure or interface digest mismatch")
    task = report.get("task", {})
    if task.get("split") != "dev" or not task.get("digest"):
        raise ValueError("development task identity is missing")
    development = report.get("uses", [])
    failed_development = report.get("status") == "candidate-failed-development"
    if report.get("status") not in ("completed", "candidate-failed-development"):
        raise ValueError("campaign status does not match completed construction")
    if (not development or development[0].get("request", {}).get("value") != [3, -2, 7]
            or (not failed_development and len(development) != 4)
            or (failed_development and len(development) != 1)):
        raise ValueError("sealed development input is missing")
    use_ids = [use.get("operation_id") for use in development]
    verifier_ids = [use.get("verdict", {}).get("operation_id")
                    for use in development if isinstance(use.get("verdict"), dict)]
    if (len(set(use_ids)) != len(use_ids) or len(verifier_ids) != len(use_ids)
            or len(set(verifier_ids)) != len(verifier_ids)
            or set(use_ids) & set(verifier_ids)):
        raise ValueError("method uses and verifier runs require unique operation identities")
    expected_dev = _summary([3, -2, 7])
    task_reference = _task_reference(task)
    try:
        reference = json.loads(task_reference["summary.json"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("pristine development reference is missing or malformed") from exc
    if reference != expected_dev:
        raise ValueError("pristine development reference differs from the fixed expectation")
    if (not failed_development
            and _summary_file(development[0].get("solution_files")) != expected_dev):
        raise ValueError("verified solution differs from the pristine task reference")
    checked = _check_use(report, development[0], child, method,
                         ([3, -2, 7], expected_dev), task, development=True,
                         require_pass=not failed_development)
    if any(use.get("episode", {}).get("trajectory") not in artifact_bytes
           for use in development):
        raise ValueError("method episode trajectory bytes are missing")
    retention = report.get("retention", {})
    if failed_development:
        if (retention.get("status") != "rejected"
                or retention.get("episode_id") != development[0]["episode"]["id"]):
            raise ValueError("failed candidate was not rejected against its development episode")
        return {"status": "no-acquisition", "checked_uses": checked,
                "construction_status": "candidate-failed-development"}
    if retention.get("status") != "retained" or retention.get("episode_id") != development[0]["episode"]["id"]:
        raise ValueError("retention is not bound to the passing development episode")
    selection = report.get("selection", {})
    if (selection.get("status") != "selected" or selection.get("executed_genome") != child.digest
            or selection.get("executed_name") != method.name
            or selection.get("method_digest") != method.digest):
        raise ValueError("selection does not bind the retained method")
    expected_later = [([-8, -3], _summary([-8, -3])), ([], _summary([])),
                      ([4, 4, 1], _summary([4, 4, 1]))]
    later = development[1:]
    if [use.get("request", {}).get("value") for use in later] != [x[0] for x in expected_later]:
        raise ValueError("changed-input uses are missing or out of order")
    for use, expectation in zip(later, expected_later, strict=True):
        checked += _check_use(report, use, child, method, expectation, use.get("task"))
    return {"status": "valid", "checked_uses": checked,
            "genome": child.digest, "method_digest": method.digest}


if __name__ == "__main__":
    try:
        print(json.dumps(check_bundle(sys.argv[1]), sort_keys=True))
    except (IndexError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid", "detail": str(exc)}, sort_keys=True))
        raise SystemExit(1)
