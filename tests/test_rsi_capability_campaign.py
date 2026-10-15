from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVER_SPEC = importlib.util.spec_from_file_location(
    "p04_driver", ROOT / "experiments" / "capability04" / "driver.py")
driver = importlib.util.module_from_spec(DRIVER_SPEC)
assert DRIVER_SPEC.loader is not None
DRIVER_SPEC.loader.exec_module(driver)
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
    manifest = {"schema": "p04-capability-source/1", "sources": {},
                "limits": {"max_construction_calls": 2}}
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
                        "trajectory": hashlib.sha256(("trace:" + operation_id).encode()).hexdigest(),
                        "status": "completed"},
            "fresh_process": ({"model_calls": 0, "execution": "native-method-episode"}
                              if operation_id == "dev-use" else
                              {"pid": 321, "exit_code": 0, "model_calls": 0}),
            "verdict": {"passed": True}, "solution_files": files,
            "task": task_evidence,
        }

    values = ([3, -2, 7], [-8, -3], [], [4, 4, 1])
    tasks = [task_doc(value, str(i)) for i, value in enumerate(values)]
    constructor_events = b'{"type":"constructed"}\n'
    constructor_events_digest = hashlib.sha256(constructor_events).hexdigest()
    constructor_trajectory = _canonical({
        "scope": "rsi-trajectory",
        "manifest": {"kind": "rsi-trajectory", "files": [{
            "path": "events.jsonl", "digest": constructor_events_digest,
            "size": len(constructor_events), "kind": "file"}]},
        "files": {"events.jsonl": constructor_events.hex()},
    })
    constructor_trajectory_digest = hashlib.sha256(constructor_trajectory).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    report = {
        "schema": "p04-capability-campaign/1",
        "source_manifest_digest": hashlib.sha256(_canonical(manifest)).hexdigest(),
        "parent": parent_doc,
        "construction_calls": 1,
        "construction_operation_id": "construct-use",
        "construction": {"status": "completed", "child": child.digest,
                         "operation_id": "construct-use", "name": "summary",
                         "interface": method.interface, "method_digest": method.digest,
                         "evidence": hashlib.sha256(b"evidence").hexdigest(),
                         "trajectory": constructor_trajectory_digest},
        "operations": [{"operation": {"id": "construct-use",
                                         "dispatch_state": "observed",
                                         "payload": {"effect": "agent-run",
                                                     "payload": {"harness": "codex"}}},
                        "receipts": [{"outcome": "success",
                                      "content": {"trajectory_digest": constructor_events_digest},
                                      "receipt_identity": "fixture:construct-use"}]}],
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
    artifact_blobs = {b"evidence", constructor_trajectory}
    artifact_blobs.update(("trace:" + use["operation_id"]).encode()
                          for use in report["uses"])
    report["artifact_bytes"] = {
        hashlib.sha256(raw).hexdigest(): base64.b64encode(raw).decode()
        for raw in artifact_blobs
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
                                      "artifact", "solution", "construction_receipt"])
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
    elif mutation == "solution":
        report["task"]["reference"]["summary.json"] = "{}\n"
    else:
        report["operations"][0]["receipts"] = []
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


def test_verify_freeze_allows_a_later_documentation_commit(tmp_path):
    manifest = driver.source_manifest(ROOT)
    manifest["commit"] = "later-documentation-only-commit"
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_bytes(_canonical(manifest))

    assert driver.verify_freeze(ROOT, bundle) == manifest


def test_fixture_campaign_constructs_retains_and_reuses_in_fresh_process(
        migrated_db, tmp_path, monkeypatch):

    import settlement.launcher_codex as codex_module
    from settlement import db
    from settlement.broker import LaunchOutcome, ReceiptProposal
    from settlement.launcher_codex import CodexLauncher

    class ScriptedCodex(CodexLauncher):
        def dispatch(self, op):
            run_dir = self._dir(op.operation_id)
            if (run_dir / "result.json").exists() or (run_dir / "claim").exists():
                return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
            workspace = run_dir / "workspace"
            skill = workspace / "genome" / "skills" / "summary"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: summary\ndescription: integer summary\n---\n", encoding="utf-8")
            (skill / "capability.json").write_bytes(_canonical({
                "schema": "rsi-capability/1", "interface": "integer-summary/1",
                "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
                "effects": ["return", "solution-files"],
                "limits": {"timeout_ms": 5000, "max_output_bytes": 65536},
            }))
            (skill / "method.py").write_text(
                "import json\n"
                "def invoke(request):\n"
                "    values = request['value']\n"
                "    result = {'count': len(values), 'total': sum(values), "
                "'minimum': min(values) if values else None, "
                "'maximum': max(values) if values else None}\n"
                "    return {'value': result, 'files': "
                "{'summary.json': json.dumps(result, sort_keys=True)}}\n",
                encoding="utf-8")
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "claim").write_text("fixture\n", encoding="utf-8")
            trajectory = b'{"type":"fixture.completed"}\n'
            (run_dir / "events.jsonl").write_bytes(trajectory)
            result = {
                "status": "completed", "exit_code": 0, "seconds": 0.01,
                "tokens": None, "infra_reason": "", "commands": 0,
                "final_message": "scripted fixture method", "trajectory_digest":
                    hashlib.sha256(trajectory).hexdigest(), "trajectory_bytes": len(trajectory),
            }
            (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            receipt = ReceiptProposal(
                receipt_identity=f"fixture:{op.operation_id}:g{op.dispatch_generation}",
                content={**result, "operation_id": op.operation_id,
                         "response_digest": result["trajectory_digest"]},
                outcome="success", provenance="scripted-fixture", actual_cost=0)
            return LaunchOutcome(sent=True, receipt=receipt)

    def allow_only_empty_operations(dsn):
        with db.connect(dsn) as conn:
            count, = conn.execute("SELECT count(*) FROM operations").fetchone()
        if count:
            raise RuntimeError("fixture refuses a used operations store")

    with pytest.raises(RuntimeError, match="unused dedicated database"):
        driver._refuse_used_database(migrated_db)
    monkeypatch.setattr(driver, "_refuse_used_database", allow_only_empty_operations)
    monkeypatch.setattr(driver, "_route", lambda _: {
        "SETTLEMENT_GATEWAY_ENDPOINT": "https://fixture.invalid",
        "SETTLEMENT_GATEWAY_MODEL": "openrouter/openrouter/free",
        "SETTLEMENT_GATEWAY_KEY": "fixture-only-key",
    })
    monkeypatch.setattr(driver, "_check_route", lambda _: None)
    monkeypatch.setattr(codex_module, "CodexLauncher", ScriptedCodex)

    bundle = tmp_path / "bundle"
    driver.freeze(ROOT, bundle)
    result = driver.run(ROOT, bundle, migrated_db, tmp_path / "route.env",
                        tmp_path / "logs", "scripted-codex")

    assert result["status"] == "completed"
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    assert report["retention"]["status"] == "retained"
    assert report["selection"]["status"] == "selected"
    assert [use["request"]["value"] for use in report["uses"]] == [
        [3, -2, 7], [-8, -3], [], [4, 4, 1]]
    assert all(use["verdict"]["passed"] for use in report["uses"])
    assert report["retention"]["episode_id"] == report["uses"][0]["episode"]["id"]
    assert check.check_bundle(bundle)["checked_uses"] == 4
