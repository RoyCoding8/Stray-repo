from __future__ import annotations

import json
import uuid

import pytest

from rsi import archive, capability
from rsi import genome as genome_module
from settlement import broker, store
from settlement.common import Command
from settlement.launcher_local import LocalLauncher


def _genome(method: str, *, interface: str = "example-interface/1",
            timeout_ms: int = 2_000) -> genome_module.Genome:
    files = {
        "skills/echo/SKILL.md": (
            b"---\nname: echo\ndescription: return a changed input\n---\n"),
        "skills/echo/capability.json": json.dumps({
            "schema": "rsi-capability/1", "interface": interface,
            "entrypoint": "method.py:invoke",
            "dependencies": ["python-stdlib"],
            "effects": ["return", "solution-files"],
            "limits": {"timeout_ms": timeout_ms,
                       "max_output_bytes": 65_536},
        }).encode(),
        "skills/echo/method.py": method.encode(),
    }
    return genome_module.Genome(files)


def _environment(dsn: str, tag: str) -> tuple[str, int, str]:
    allocation = f"{tag}-allocation"
    attempt = f"{tag}-attempt"
    store.seed_allocation(dsn, Command(
        request_id=f"{tag}-allocation-request",
        payload={"allocation_id": allocation, "domain": "cpu", "authorized": 100_000}))
    store.admit_commitment(dsn, Command(
        request_id=f"{tag}-commitment-request",
        payload={"investigation_id": f"{tag}-investigation", "objective": "method runtime"}))
    ownership = store.acquire_work(dsn, Command(
        request_id=f"{tag}-attempt-request",
        payload={"attempt_id": attempt,
                 "investigation_id": f"{tag}-investigation"})).data["ownership_generation"]
    return allocation, int(ownership), attempt


def _request(value, *, interface: str = "example-interface/1") -> dict:
    return {"interface": interface, "value": value,
            "files": {"answer.txt": b"seed".decode()}, "context": {"continuation": 2}}


def test_catalogue_binds_every_method_file_and_rejects_wrong_interface():
    source = "def invoke(request):\n    return {'value': request['value'], 'files': {}}\n"
    genome = _genome(source)
    found, = capability.catalogue(genome)
    changed = _genome(source + "\n# changed closure\n")

    assert (found.name, found.genome, found.interface) == ("echo", genome.digest,
                                                              "example-interface/1")
    assert found.digest != capability.catalogue(changed)[0].digest
    with pytest.raises(capability.CapabilityError, match="interface"):
        capability.invoke("unused", object(), genome, "echo",
                          _request("x", interface="other/1"),
                          operation_id="wrong-interface", allocation_id="a",
                          attempt_id="t", staging_root=".", artifacts_root=".")


def test_local_runtime_returns_changed_values_files_and_replays_once(
        migrated_db, tmp_path):
    dsn = migrated_db
    tag = uuid.uuid4().hex[:8]
    allocation, ownership, attempt = _environment(dsn, tag)
    genome = _genome(
        "print('module log')\n"
        "def invoke(request):\n"
        "    print('method log')\n"
        "    value = request['value']\n"
        "    return {'value': {'echo': value}, 'files': {'answer.txt': str(value)}}\n")
    launcher = LocalLauncher(tmp_path / "runs")
    args = {"operation_id": f"{tag}-method", "allocation_id": allocation,
            "attempt_id": attempt, "staging_root": tmp_path / "staging",
            "artifacts_root": tmp_path / "artifacts", "ownership_generation": ownership}

    first = capability.invoke(dsn, launcher, genome, "echo", _request("first"), **args)
    spawns = list((tmp_path / "runs").glob("*.spawns"))
    replay = capability.invoke(dsn, launcher, genome, "echo", _request("first"), **args)
    with pytest.raises(capability.CapabilityError, match="different method inputs"):
        capability.invoke(dsn, launcher, genome, "echo", _request("altered"), **args)
    second_args = dict(args, operation_id=f"{tag}-method-2")
    second = capability.invoke(dsn, launcher, genome, "echo", _request("second"), **second_args)

    assert (first.status, first.value, dict(first.files)) == (
        "completed", {"echo": "first"}, {"answer.txt": b"first"})
    assert (second.status, second.value, dict(second.files)) == (
        "completed", {"echo": "second"}, {"answer.txt": b"second"})
    assert (replay.output_digest, replay.value, dict(replay.files)) == (
        first.output_digest, {"echo": "first"}, {"answer.txt": b"first"})
    same_operation_spawns = list((tmp_path / "runs").glob(f"{tag}-method_*.spawns"))
    assert len(spawns) == len(same_operation_spawns) == 1
    assert first.output_digest and first.execution_version
    assert broker.read_operation(dsn, first.operation_id)["dispatch_state"] == "observed"
    decision = archive.decision(dsn, "capability-use:" + first.operation_id)
    assert decision["data"]["requested_genome"] == genome.digest
    assert decision["data"]["executed_name"] == "echo"
    assert decision["data"]["input_digest"] == first.input_digest
    assert decision["data"]["result_digest"] == first.output_digest
    receipt = store.operation_receipts(dsn, first.operation_id)[-1]
    assert receipt["content"]["data"]["worker"]["data"]["candidate_stdout"] == "module log\nmethod log\n"


def test_settlement_before_use_record_resumes_without_a_second_send(migrated_db, tmp_path, monkeypatch):
    tag = uuid.uuid4().hex[:8]
    allocation, ownership, attempt = _environment(migrated_db, tag)
    candidate = _genome("def invoke(request):\n"
                        "    return {'value': request['value'], 'files': {'answer.txt': 'once'}}\n")
    launcher = LocalLauncher(tmp_path / "runs")
    kwargs = {"operation_id": tag + "-crash", "allocation_id": allocation, "attempt_id": attempt,
              "ownership_generation": ownership, "staging_root": tmp_path / "stage",
              "artifacts_root": tmp_path / "art"}
    original = archive.record

    def interrupt(*args, **kw):
        if kw.get("kind") == "capability-use":
            raise capability.CapabilityError("interrupted after settlement")
        return original(*args, **kw)

    with monkeypatch.context() as patch:
        patch.setattr(archive, "record", interrupt)
        with pytest.raises(capability.CapabilityError, match="after settlement"):
            capability.invoke(migrated_db, launcher, candidate, "echo", _request(7), **kwargs)
    assert broker.read_operation(migrated_db, kwargs["operation_id"])["dispatch_state"] == "observed"
    assert archive.decision(migrated_db, "capability-use:" + kwargs["operation_id"]) is None
    local_result, = launcher.run_dir.glob("*.result.json")
    replaced = json.loads(local_result.read_text())
    replaced["data"]["worker"]["data"]["output"] = {
        "value": 99, "files": {"answer.txt": "substituted"}}
    local_result.write_text(json.dumps(replaced))
    resumed = capability.invoke(migrated_db, launcher, candidate, "echo", _request(7), **kwargs)
    assert (resumed.status, resumed.value, dict(resumed.files)) == (
        "completed", 7, {"answer.txt": b"once"})
    assert len(list(launcher.run_dir.glob("*.spawns"))) == 1


def test_noop_and_malformed_candidate_output_are_distinct(migrated_db, tmp_path):
    dsn = migrated_db
    tag = uuid.uuid4().hex[:8]
    allocation, ownership, attempt = _environment(dsn, tag)
    launcher = LocalLauncher(tmp_path / "runs")
    common = {"dsn": dsn, "launcher": launcher, "allocation_id": allocation,
              "attempt_id": attempt, "staging_root": tmp_path / "staging",
              "artifacts_root": tmp_path / "artifacts", "ownership_generation": ownership}
    noop = capability.invoke(
        genome=_genome("def invoke(request):\n    return {'value': None, 'files': {}}\n"),
        name="echo", request=_request("x"), operation_id=f"{tag}-noop", **common)
    malformed = capability.invoke(
        genome=_genome("def invoke(request):\n    return {'value': None}\n"),
        name="echo", request=_request("x"), operation_id=f"{tag}-malformed", **common)

    assert (noop.status, noop.value, dict(noop.files), bool(noop.output_digest)) == (
        "completed", None, {}, True)
    assert malformed.status == "failed"
    assert malformed.output_digest is None
    assert malformed.operation_id != noop.operation_id


def test_timeout_is_a_real_settled_failure(migrated_db, tmp_path):
    dsn = migrated_db
    tag = uuid.uuid4().hex[:8]
    allocation, ownership, attempt = _environment(dsn, tag)
    launcher = LocalLauncher(tmp_path / "runs")
    result = capability.invoke(
        dsn, launcher,
        _genome("import time\ndef invoke(request):\n    time.sleep(2)\n    return {'value': 1, 'files': {}}\n"),
        "echo", _request("x"), operation_id=f"{tag}-timeout",
        allocation_id=allocation, attempt_id=attempt,
        staging_root=tmp_path / "staging", artifacts_root=tmp_path / "artifacts",
        ownership_generation=ownership, timeout_ms=200)

    assert result.status == "timeout"
    assert result.output_digest is None
    assert broker.read_operation(dsn, result.operation_id)["dispatch_state"] == "observed"


def test_child_rejects_method_bytes_changed_after_pinning(migrated_db, tmp_path):
    dsn = migrated_db
    tag = uuid.uuid4().hex[:8]
    allocation, ownership, attempt = _environment(dsn, tag)

    class MutatingLauncher(LocalLauncher):
        def stage_input(self, operation_id, execution_version, relpath, data):
            if relpath.endswith("method.py"):
                data = data.replace(b"'value'", b"'tampered'")
            return super().stage_input(operation_id, execution_version, relpath, data)

    result = capability.invoke(
        dsn, MutatingLauncher(tmp_path / "runs"),
        _genome("def invoke(request):\n    return {'value': request['value'], 'files': {}}\n"),
        "echo", _request("pinned"), operation_id=f"{tag}-substitution",
        allocation_id=allocation, attempt_id=attempt,
        staging_root=tmp_path / "staging", artifacts_root=tmp_path / "artifacts",
        ownership_generation=ownership)

    assert result.status == "infra_failed"
    assert result.value is None and not result.files and result.output_digest is None
    receipts = store.operation_receipts(dsn, result.operation_id)
    assert receipts and receipts[-1]["outcome"] == "failure"
