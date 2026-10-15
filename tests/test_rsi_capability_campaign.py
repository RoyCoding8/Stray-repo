from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p04_check", ROOT / "experiments" / "capability04" / "check.py")
check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _bundle(tmp_path):
    from rsi.capability import catalogue
    from rsi.genome import Genome
    from rsi.task import Task
    from settlement.artifacts import package_bytes

    parent = Genome({"AGENTS.md": b"Public method specification only\n"})
    descriptor = {
        "schema": "rsi-capability/1", "interface": "integer-summary/1",
        "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
        "effects": ["return", "solution-files"],
        "limits": {"timeout_ms": 5000, "max_output_bytes": 65536},
    }
    child = Genome({**parent.files,
                    "skills/summary/SKILL.md": b"---\nname: summary\ndescription: summary\n---\n",
                    "skills/summary/capability.json": _canonical(descriptor),
                    "skills/summary/method.py": b"def invoke(request): return {}\n"})
    method, = catalogue(child)
    manifest = {"schema": "p04-capability-source/1", "sources": {}}
    parent_doc = {"digest": parent.digest,
                  "files": {path: raw.hex() for path, raw in parent.files.items()},
                  "package": base64.b64encode(package_bytes(
                      parent._manifest(), dict(parent.files), "rsi-genome")).decode()}
    child_doc = {"digest": child.digest,
                 "files": {path: raw.hex() for path, raw in child.files.items()},
                 "package": base64.b64encode(package_bytes(
                     child._manifest(), dict(child.files), "rsi-genome")).decode()}

    def task_doc(values, suffix):
        expected = {"count": len(values), "total": sum(values),
                    "minimum": min(values) if values else None,
                    "maximum": max(values) if values else None}
        solution = json.dumps(expected, separators=(",", ":")) + "\n"
        task = Task("campaign-" + suffix, "dev", "public input",
                    {"summary.json": b""},
                    {"test_summary.py": b"from pathlib import Path\nassert Path('summary.json').exists()\n"},
                    {"summary.json": solution.encode()}, ("test_summary.py",))
        doc = {"digest": task.digest, "split": task.split,
               "reference": {"summary.json": solution},
               "package": base64.b64encode(package_bytes(
                   task.manifest(), task.package_files(), "rsi-task")).decode()}
        return expected, solution, doc

    def use(operation_id, values, task):
        expected, solution, task_evidence = task
        files = {"summary.json": solution}
        artifact_doc = {"value": expected, "files": files}
        artifact_package = _canonical({
            "manifest": {"kind": "rsi-capability-result", "operation_id": operation_id},
            "files": {"result.json": _canonical(artifact_doc).hex()},
        })
        request = {"interface": "integer-summary/1", "value": values,
                   "files": {"summary.json": ""}, "context": {}}
        dispatch_request = {**request, "context": {
            "continuation": request["context"], "task_digest": task_evidence["digest"]}}
        identity = {
            "operation_id": operation_id, "requested_genome": child.digest,
            "executed_genome": child.digest, "requested_name": "summary",
            "executed_name": "summary", "method_digest": method.digest,
            "interface": "integer-summary/1",
            "input_digest": hashlib.sha256(_canonical(dispatch_request)).hexdigest(),
            "execution_version": "cap1-test",
            "output_digest": hashlib.sha256(artifact_package).hexdigest(),
        }
        return {
            **identity, "decision": identity, "status": "completed",
            "request": request, "dispatch_request": dispatch_request,
            "value": expected, "files": files,
            "result_artifact": base64.b64encode(artifact_package).decode(),
            "episode": {"id": operation_id, "task_digest": task_evidence["digest"],
                        "status": "completed"},
            "fresh_process": ({"model_calls": 0, "execution": "native-method-episode"}
                              if operation_id == "dev-use" else
                              {"pid": 321, "exit_code": 0, "model_calls": 0}),
            "verdict": {"passed": True}, "solution_files": files,
            "task": task_evidence,
        }

    values = ([3, -2, 7], [-8, -3], [], [4, 4, 1])
    tasks = [task_doc(value, str(i)) for i, value in enumerate(values)]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    report = {
        "schema": "p04-capability-campaign/1",
        "source_manifest_digest": hashlib.sha256(_canonical(manifest)).hexdigest(),
        "parent": parent_doc,
        "construction": {"status": "completed", "child": child.digest,
                         "requested_name": "summary", "interface": method.interface,
                         "method_digest": method.digest},
        "child": child_doc,
        "task": tasks[0][2],
        "uses": [use("dev-use", values[0], tasks[0]),
                 use("transfer-1", values[1], tasks[1]),
                 use("transfer-2", values[2], tasks[2]),
                 use("transfer-3", values[3], tasks[3])],
        "retention": {"status": "retained", "episode_id": "dev-use"},
        "selection": {"status": "selected", "executed_genome": child.digest,
                      "executed_name": "summary", "method_digest": method.digest},
    }
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "manifest.json").write_bytes(_canonical(manifest))
    (root / "report.json").write_bytes(_canonical(report))
    return root, report


def test_checker_accepts_bound_method_use_and_pristine_solutions(tmp_path):
    root, _ = _bundle(tmp_path)

    result = check.check_bundle(root)

    assert result["status"] == "valid"
    assert result["checked_uses"] == 4


@pytest.mark.parametrize("mutation", ["method_digest", "input_digest", "dispatch_task",
                                      "artifact", "solution"])
def test_checker_rejects_broken_identity_or_result_evidence(tmp_path, mutation):
    root, report = _bundle(tmp_path)
    use = report["uses"][0]
    if mutation == "method_digest":
        report["construction"]["method_digest"] = "0" * 64
    elif mutation == "input_digest":
        use["input_digest"] = "0" * 64
    elif mutation == "dispatch_task":
        use["dispatch_request"]["context"]["task_digest"] = "0" * 64
    elif mutation == "artifact":
        use["output_digest"] = "0" * 64
    else:
        report["task"]["reference"]["summary.json"] = "{}\n"
    (root / "report.json").write_bytes(_canonical(report))

    with pytest.raises(ValueError):
        check.check_bundle(root)


def test_checker_preserves_candidate_failure_as_no_acquisition(tmp_path):
    root, report = _bundle(tmp_path)
    report["construction"] = {"status": "invalid", "child": None}
    report.pop("child")
    report["uses"] = []
    (root / "report.json").write_bytes(_canonical(report))

    result = check.check_bundle(root)

    assert result == {"status": "no-acquisition", "checked_uses": 0,
                      "construction_status": "invalid"}
