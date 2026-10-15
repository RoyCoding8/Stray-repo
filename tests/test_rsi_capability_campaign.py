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
        allocation_id = "fixture-allocation"
        attempt_id = "fixture-attempt:" + operation_id
        payload = {"effect": "sandbox-exec",
                   "payload": {"argv": ["python", "trusted_runner.py", "identity.json"]}}
        operation = {"id": operation_id, "allocation_id": allocation_id,
                     "attempt_id": attempt_id, "execution_version": "cap1-test",
                     "payload_digest": hashlib.sha256(_canonical(payload)).hexdigest(),
                     "payload": payload, "dispatch_state": "observed", "settled": True}
        operation_receipt = {"outcome": "success", "content": {
            "_verdict": "success", "parse": "typed-json",
            "data": {"supervised": True, "worker": {
                "status": "ok", "error": "", "data": {
                    "kind": "capability-result",
                    "output": {"value": expected, "files": files}}}}}}
        evaluator_version = json.loads(base64.b64decode(
            task_evidence["package"]))["manifest"]["evaluator_version"]
        verifier_id = "rsi-verify-" + hashlib.sha256(
            f"{operation_id}:{evaluator_version}".encode()).hexdigest()
        solution_bytes = {name: value.encode() for name, value in files.items()}
        solution_package = _canonical({
            "manifest": {"kind": "rsi-solution", "task": task_evidence["digest"],
                         "files": [{"path": name, "kind": "file", "size": len(raw),
                                    "digest": hashlib.sha256(raw).hexdigest()}
                                   for name, raw in sorted(solution_bytes.items())]},
            "scope": "rsi-solution",
            "files": {name: raw.hex() for name, raw in solution_bytes.items()},
        })
        verifier_payload = {"effect": "sandbox-exec", "payload": {
            "argv": ["python", "-I", "-S", "-B", "_rsi_verify.py", "test_summary.py"]}}
        verifier_operation = {**operation, "id": verifier_id,
                              "payload": verifier_payload,
                              "execution_version": hashlib.sha256(solution_package).hexdigest(),
                              "payload_digest": hashlib.sha256(
                                  _canonical(verifier_payload)).hexdigest()}
        verifier_receipt = {"outcome": "success", "content": {
            "_verdict": "success", "parse": "typed-json",
            "data": {"supervised": True, "worker": {
                "status": "ok", "error": "", "data": {
                    "tests": 1, "errors": 0, "failures": 0, "skipped": 0}}}}}
        execution_operations.extend([
            {"operation": operation, "receipts": [operation_receipt]},
            {"operation": verifier_operation, "receipts": [verifier_receipt]},
        ])
        return {
            **identity, "decision": identity, "status": "completed",
            "allocation_id": allocation_id, "attempt_id": attempt_id,
            "payload_digest": hashlib.sha256(_canonical(payload["payload"])).hexdigest(),
            "operation": operation,
            "request": request, "dispatch_request": dispatch_request,
            "value": expected, "files": files,
            "result_artifact": base64.b64encode(artifact_package).decode(),
            "episode": {"id": operation_id, "task_digest": task_evidence["digest"],
                        "trajectory": hashlib.sha256(("trace:" + operation_id).encode()).hexdigest(),
                        "status": "completed"},
            "fresh_process": ({"model_calls": 0, "execution": "native-method-episode"}
                              if operation_id == "dev-use" else
                              {"pid": 321, "exit_code": 0, "model_calls": 0}),
            "verdict": {"operation_id": verifier_id, "status": "passed",
                        "passed": True}, "solution_files": files,
            "task": task_evidence,
        }

    values = ([3, -2, 7], [-8, -3], [], [4, 4, 1])
    tasks = [task_doc(value, str(i)) for i, value in enumerate(values)]
    execution_operations = []
    campaign_uses = [use("dev-use", values[0], tasks[0]),
                     use("transfer-1", values[1], tasks[1]),
                     use("transfer-2", values[2], tasks[2]),
                     use("transfer-3", values[3], tasks[3])]
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
    context_packet = {"schema": "fixture-context/1", "evidence": []}
    construction_input = {
        "parent": parent.digest, "name": "summary", "interface": method.interface,
        "context_digest": hashlib.sha256(_canonical(context_packet)).hexdigest(),
        "operation_id": "construct-use", "model": "fixture-model",
        "allocation_id": "fixture-tokens",
        "timeout_ms": 180000, "token_ceiling": 100000,
    }
    evidence_file = _canonical({"construction": construction_input,
                                "context_packet": context_packet})
    evidence_package = _canonical({
        "scope": "rsi-dev-evidence",
        "manifest": {"kind": "rsi-dev-evidence", "files": [{
            "path": "evidence.json", "digest": hashlib.sha256(evidence_file).hexdigest(),
            "size": len(evidence_file), "kind": "file"}]},
        "files": {"evidence.json": evidence_file.hex()},
    })
    evidence_digest = hashlib.sha256(evidence_package).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    report = {
        "schema": "p04-capability-campaign/1",
        "status": "completed",
        "source_manifest_digest": hashlib.sha256(_canonical(manifest)).hexdigest(),
        "parent": parent_doc,
        "construction_calls": 1,
        "construction_operation_id": "construct-use",
        "construction": {"status": "completed", "child": child.digest,
                         **construction_input,
                         "interface": method.interface, "method_digest": method.digest,
                         "evidence": evidence_digest,
                         "trajectory": constructor_trajectory_digest},
        "operations": [{"operation": {"id": "construct-use",
                                         "dispatch_state": "observed",
                                         "payload": {"effect": "agent-run",
                                                     "payload": {"task": evidence_digest,
                                                                 "genome": parent.digest,
                                                                 "timeout_ms": 180000,
                                                                 "token_ceiling": 100000}}},
                        "receipts": [{"outcome": "success",
                                      "content": {"operation_id": "construct-use",
                                                  "response_digest": constructor_events_digest,
                                                  "trajectory_digest": constructor_events_digest},
                                      "receipt_identity": "fixture:construct-use"}]},
                       *execution_operations],
        "child": child_doc,
        "task": tasks[0][2],
        "uses": campaign_uses,
        "retention": {"status": "retained", "episode_id": "dev-use"},
        "selection": {"status": "selected", "executed_genome": child.digest,
                      "executed_name": "summary", "method_digest": method.digest},
    }
    artifact_blobs = {evidence_package, constructor_trajectory}
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
                                      "artifact", "solution", "construction_receipt",
                                      "construction_evidence"])
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
    elif mutation == "construction_receipt":
        report["operations"][0]["receipts"] = []
    else:
        report["construction"]["evidence"] = report["construction"]["trajectory"]
    (root / "report.json").write_bytes(_canonical(report))

    with pytest.raises(ValueError):
        check.check_bundle(root)


def test_checker_preserves_candidate_failure_as_no_acquisition(tmp_path):
    root, report = _bundle(tmp_path)
    report["construction"]["status"] = "invalid"
    report["status"] = "no-acquisition"
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


@pytest.mark.parametrize("constructor_status,fail_development", [
    ("completed", False), ("completed", True), ("timeout", False), ("infra_failed", False),
])
def test_fixture_campaign_constructs_retains_and_reuses_in_fresh_process(
        migrated_db, tmp_path, monkeypatch, constructor_status, fail_development):

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
                f"    result = {{'count': len(values), 'total': sum(values) + {int(fail_development)}, "
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
                "status": constructor_status, "exit_code": 0, "seconds": 0.01,
                "tokens": None, "infra_reason": "", "commands": 0,
                "final_message": "scripted fixture method", "trajectory_digest":
                    hashlib.sha256(trajectory).hexdigest(), "trajectory_bytes": len(trajectory),
            }
            (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            receipt = ReceiptProposal(
                receipt_identity=f"fixture:{op.operation_id}:g{op.dispatch_generation}",
                content={**result, "operation_id": op.operation_id,
                         "response_digest": result["trajectory_digest"]},
                outcome="success" if constructor_status == "completed" else "failure",
                provenance="scripted-fixture", actual_cost=0)
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

    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    if constructor_status != "completed":
        assert result["status"] == report["status"] == "unscored"
        assert report["uses"] == []
        assert "retention" not in report and "selection" not in report
        expected = {"status": "unscored", "checked_uses": 0,
                    "construction_status": constructor_status, "reported_status": "unscored"}
        assert check.check_bundle(bundle) == expected
        report["status"] = "no-acquisition"
        (bundle / "report.json").write_bytes(_canonical(report))
        assert check.check_bundle(bundle) == {**expected, "reported_status": "no-acquisition"}
        report["operations"][0]["receipts"] = []
        (bundle / "report.json").write_bytes(_canonical(report))
        with pytest.raises(ValueError):
            check.check_bundle(bundle)
        return
    if fail_development:
        assert result["status"] == "candidate-failed-development"
        assert report["retention"]["status"] == "rejected"
        assert len(report["uses"]) == 1
        assert report["uses"][0]["verdict"]["passed"] is False
        assert check.check_bundle(bundle) == {
            "status": "no-acquisition", "checked_uses": 1,
            "construction_status": "candidate-failed-development"}
        return
    assert result["status"] == "completed"
    assert report["retention"]["status"] == "retained"
    assert report["selection"]["status"] == "selected"
    assert [use["request"]["value"] for use in report["uses"]] == [
        [3, -2, 7], [-8, -3], [], [4, 4, 1]]
    assert all(use["verdict"]["passed"] for use in report["uses"])
    assert report["retention"]["episode_id"] == report["uses"][0]["episode"]["id"]
    assert check.check_bundle(bundle)["checked_uses"] == 4

    import copy

    clean = copy.deepcopy(report)
    use_operation_ids = {use["operation_id"] for use in report["uses"]}
    missing_uses = copy.deepcopy(clean)
    missing_uses["operations"] = [row for row in clean["operations"]
                                   if row["operation"]["id"] not in use_operation_ids]
    for use in missing_uses["uses"]:
        use.pop("operation", None)
    (bundle / "report.json").write_bytes(_canonical(missing_uses))
    with pytest.raises(ValueError):
        check.check_bundle(bundle)

    empty_use_receipt = copy.deepcopy(clean)
    operation = next(row for row in empty_use_receipt["operations"]
                     if row["operation"]["id"] == report["uses"][0]["operation_id"])
    operation["receipts"] = []
    (bundle / "report.json").write_bytes(_canonical(empty_use_receipt))
    with pytest.raises(ValueError):
        check.check_bundle(bundle)

    missing_verifiers = copy.deepcopy(clean)
    verifier_ids = {use["verdict"]["operation_id"] for use in clean["uses"]}
    missing_verifiers["operations"] = [row for row in clean["operations"]
                                        if row["operation"]["id"] not in verifier_ids]
    (bundle / "report.json").write_bytes(_canonical(missing_verifiers))
    with pytest.raises(ValueError):
        check.check_bundle(bundle)

    swapped_verifiers = copy.deepcopy(clean)
    first = swapped_verifiers["uses"][0]["verdict"]["operation_id"]
    second = swapped_verifiers["uses"][1]["verdict"]["operation_id"]
    swapped_verifiers["uses"][0]["verdict"]["operation_id"] = second
    swapped_verifiers["uses"][1]["verdict"]["operation_id"] = first
    (bundle / "report.json").write_bytes(_canonical(swapped_verifiers))
    with pytest.raises(ValueError):
        check.check_bundle(bundle)
    (bundle / "report.json").write_bytes(_canonical(clean))


def test_checker_rejects_negative_claim_without_constructor_evidence(tmp_path):
    root, report = _bundle(tmp_path)
    report.update(status="no-acquisition", construction={"status": "invalid"},
                  operations=[], artifact_bytes={}, uses=[])
    (root / "report.json").write_bytes(_canonical(report))

    with pytest.raises(ValueError):
        check.check_bundle(root)


def test_checker_requires_failed_development_receipt_and_rejection(tmp_path):
    root, report = _bundle(tmp_path)
    use = report["uses"][0]
    use["value"] = {"count": 3, "total": 8, "minimum": -2, "maximum": 6}
    use["files"] = {"summary.json": json.dumps(use["value"], sort_keys=True)}
    use["solution_files"] = use["files"]
    result = {"value": use["value"], "files": use["files"]}
    artifact = _canonical({
        "manifest": {"kind": "rsi-capability-result", "operation_id": use["operation_id"]},
        "files": {"result.json": _canonical(result).hex()},
    })
    use["result_artifact"] = base64.b64encode(artifact).decode()
    use["output_digest"] = hashlib.sha256(artifact).hexdigest()
    use["decision"]["output_digest"] = use["output_digest"]
    use_operation = next(row for row in report["operations"]
                         if row["operation"]["id"] == use["operation_id"])
    use_receipt_data = use_operation["receipts"][0]["content"]["data"]["worker"]["data"]
    use_receipt_data["output"] = result
    use["verdict"].update(status="failed", passed=False)
    verifier_operation = next(row for row in report["operations"]
                              if row["operation"]["id"] == use["verdict"]["operation_id"])
    verifier_data = verifier_operation["receipts"][0]["content"]["data"]["worker"]["data"]
    verifier_data.update(failures=1)
    verifier_operation["receipts"][0]["outcome"] = "failure"
    verifier_operation["receipts"][0]["content"]["_verdict"] = "failure"
    verifier_operation["receipts"][0]["content"]["data"]["worker"]["status"] = "error"
    solution_bytes = {name: value.encode() for name, value in use["solution_files"].items()}
    verifier_operation["operation"]["execution_version"] = hashlib.sha256(_canonical({
        "manifest": {"kind": "rsi-solution", "task": use["task"]["digest"],
                     "files": [{"path": name, "kind": "file", "size": len(raw),
                                "digest": hashlib.sha256(raw).hexdigest()}
                               for name, raw in sorted(solution_bytes.items())]},
        "scope": "rsi-solution",
        "files": {name: raw.hex() for name, raw in solution_bytes.items()},
    })).hexdigest()
    report["uses"] = [use]
    report["retention"] = {"status": "rejected", "episode_id": use["episode"]["id"]}
    report["status"] = "candidate-failed-development"
    (root / "report.json").write_bytes(_canonical(report))

    assert check.check_bundle(root) == {
        "status": "no-acquisition", "checked_uses": 1,
        "construction_status": "candidate-failed-development"}

    verifier_operation["receipts"] = []
    (root / "report.json").write_bytes(_canonical(report))
    with pytest.raises(ValueError):
        check.check_bundle(root)
