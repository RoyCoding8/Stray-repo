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


def _construction_record(report, *, settled):
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
        raise ValueError("construction receipt export is malformed")
    if settled:
        if (operation.get("dispatch_state") not in ("observed", "reconciled")
                or len(receipts) != 1 or receipts[0].get("outcome") != "success"):
            raise ValueError("construction lacks one settled successful broker receipt")
        content = receipts[0].get("content")
        if (not isinstance(content, dict)
                or content.get("trajectory_digest") != report.get("construction", {}).get("trajectory")):
            raise ValueError("constructor receipt does not bind its captured trajectory")
    return record


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


def _check_use(use, genome, method, expected, *, development=False):
    required = {"operation_id", "requested_genome", "executed_genome", "requested_name",
                "executed_name", "method_digest", "interface", "input_digest",
                "execution_version", "status", "output_digest", "request",
                "dispatch_request", "result_artifact", "value", "files", "decision", "episode",
                "fresh_process"}
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
    if request["value"] != expected[0] or use["value"] != expected[1]:
        raise ValueError("method result differs from literal summary expectation")
    if not isinstance(use["files"], dict) or set(use["files"]) != {"summary.json"}:
        raise ValueError("method must return exactly summary.json")
    try:
        actual_file = json.loads(use["files"]["summary.json"])
    except (TypeError, ValueError) as exc:
        raise ValueError("returned summary.json is malformed") from exc
    if actual_file != expected[1]:
        raise ValueError("returned summary.json differs from literal summary expectation")

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
    if episode.get("status") != "completed" or not episode.get("id"):
        raise ValueError("method episode is not completed")
    if not isinstance(episode.get("trajectory"), str):
        raise ValueError("method episode lacks its published trajectory identity")
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
        verdict = use.get("verdict")
        if not isinstance(verdict, dict) or verdict.get("passed") is not True:
            raise ValueError("development method use lacks a passing independent verdict")
        if use.get("solution_files") != use["files"]:
            raise ValueError("pristine solution differs from the published method files")
    else:
        task = use.get("task", {})
        reference = _task_reference(task)
        verdict = use.get("verdict")
        if (not isinstance(verdict, dict) or verdict.get("passed") is not True
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
        raise ValueError("captured artifact bytes are malformed")
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
    if report.get("status") in ("no-acquisition", "candidate-failed-development"):
        return {"status": "no-acquisition", "checked_uses": 0,
                "outcome": report["status"]}
    failed_construction = report.get("construction", {}).get("status")
    if failed_construction in ("invalid", "failed", "no_candidate"):
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
    if not development or development[0].get("request", {}).get("value") != [3, -2, 7]:
        raise ValueError("sealed development input is missing")
    expected_dev = _summary([3, -2, 7])
    task_reference = _task_reference(task)
    try:
        reference = json.loads(task_reference["summary.json"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("pristine development reference is missing or malformed") from exc
    if reference != expected_dev:
        raise ValueError("pristine development reference differs from the fixed expectation")
    if _summary_file(development[0].get("solution_files")) != expected_dev:
        raise ValueError("verified solution differs from the pristine task reference")
    checked = _check_use(development[0], child, method, ([3, -2, 7], expected_dev),
                         development=True)
    if any(use.get("episode", {}).get("trajectory") not in artifact_bytes
           for use in development):
        raise ValueError("method episode trajectory bytes are missing")
    retention = report.get("retention", {})
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
        checked += _check_use(use, child, method, expectation)
    return {"status": "valid", "checked_uses": checked,
            "genome": child.digest, "method_digest": method.digest}


if __name__ == "__main__":
    try:
        print(json.dumps(check_bundle(sys.argv[1]), sort_keys=True))
    except (IndexError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid", "detail": str(exc)}, sort_keys=True))
        raise SystemExit(1)
