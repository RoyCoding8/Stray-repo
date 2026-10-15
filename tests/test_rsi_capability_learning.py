from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from test_rsi_memory_integration import _create as _create_context_source
from test_rsi_memory_integration import _task as _context_task

from rsi import archive, capability, context, genome, investigate
from settlement import artifacts, broker, store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fake_capability.py"
NAME = "number-product"
INTERFACE = "scalar-product/1"
TOKEN_CEILING = 5_000
TOKEN_COST = 1_050

METHOD_FILES = {
    f"skills/{NAME}/SKILL.md": (
        b"---\nname: number-product\ndescription: Multiply two finite numbers.\n---\n"
    ),
    f"skills/{NAME}/capability.json": (
        b'{"dependencies":["python-stdlib"],"effects":["return","solution-files"],'
        b'"entrypoint":"method.py:invoke","interface":"scalar-product/1",'
        b'"limits":{"max_output_bytes":65536,"timeout_ms":5000},'
        b'"schema":"rsi-capability/1"}\n'
    ),
    f"skills/{NAME}/method.py": (
        b"def invoke(request):\n"
        b"    if request['interface'] != 'scalar-product/1':\n"
        b"        raise ValueError('unsupported interface')\n"
        b"    value = request['value']['left'] * request['value']['right']\n"
        b"    return {'value': value, 'files': {'solution.txt': f'{value}\\n'}}\n"
    ),
}


def _packet(tmp_path, dsn, label: str, *, purpose: str = "Construct a number method."):
    source = _create_context_source(
        tmp_path, dsn,
        "p04-context-" + label,
        _context_task("p04-context-task-" + label, purpose, empty=True),
        objective=purpose,
    )
    state = source["state"]
    continuation = {
        "objective": state["objective"],
        "objective_revision": state["objective_revision"],
        "state_revision": state["revision"],
        "open_questions": state["open_questions"],
        "artifact_refs": state["artifact_refs"],
        "previous_observation": state["last_observation"],
    }
    request = investigate._context_request(
        source["id"], state["objective_revision"], state["revision"],
        "p04-context-decision-" + label,
        "p04-context-attempt-" + label,
        "p04-context-operation-" + label,
        state["objective"], continuation, state["config"]["context"],
    )
    packet = context.build(dsn, request, artifacts_root=source["artifacts_root"])
    assert packet["status"] == "ready"
    return packet


def _allocation(dsn, allocation_id: str, *, amount: int = 100_000) -> None:
    store.seed_allocation(
        dsn,
        Command(
            request_id="p04-token-grant:" + allocation_id,
            payload={"allocation_id": allocation_id, "domain": "tokens", "authorized": amount},
        ),
    )


def _case(tmp_path, dsn, *, mode: str = "valid", label: str = "case"):
    root = tmp_path / label
    staging_root = root / "staging"
    # Match the existing P03 integration helper so the packet's selected
    # evidence, if any, resolves in the same artifact store used by construct.
    artifacts_root = tmp_path / "p02-artifacts"
    staging_root.mkdir(parents=True)
    artifacts_root.mkdir(exist_ok=True)

    parent = genome.Genome({
        "AGENTS.md": b"Use bounded, explicit procedures.\n",
        "meta/IMPROVE.md": b"Read context evidence before proposing a method.\n",
    })
    genome.publish(
        dsn, parent, parent=None, origin="p04-construction-test",
        staging_root=staging_root, artifacts_root=artifacts_root,
    )

    allocation_id = "p04-tokens-" + label
    _allocation(dsn, allocation_id)
    agent = CodexLauncher(
        root / "runs",
        codex_cmd=[sys.executable, str(FIXTURE), mode],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS,
    )
    packet = _packet(tmp_path, dsn, label, purpose="Construct a number method.")
    return {
        "dsn": dsn,
        "root": root,
        "staging_root": staging_root,
        "artifacts_root": artifacts_root,
        "parent": parent,
        "agent": agent,
        "context_packet": packet,
        "allocation_id": allocation_id,
    }


def _construct(case, *, operation_id: str, allocation_id: str | None = None,
               interface: str = INTERFACE, context_packet: dict | None = None):
    return capability.construct(
        case["dsn"], case["agent"], case["parent"],
        name=NAME,
        interface=interface,
        context_packet=context_packet or case["context_packet"],
        operation_id=operation_id,
        allocation_id=allocation_id or case["allocation_id"],
        token_ceiling=TOKEN_CEILING,
        timeout_ms=30_000,
        staging_root=case["staging_root"],
        artifacts_root=case["artifacts_root"],
    )


def _call_file(case, operation_id: str) -> Path:
    _, operation_dir = case["agent"].exec_dirs(operation_id, "")
    return Path(operation_dir) / "fake-calls.jsonl"


def _read_evidence(case, digest: str) -> dict:
    assert artifacts.artifact_available(case["dsn"], case["artifacts_root"], digest)
    package = json.loads((case["artifacts_root"] / digest).read_bytes())
    assert package["scope"] == "rsi-dev-evidence"
    raw = bytes.fromhex(package["files"]["evidence.json"])
    return json.loads(raw)


def _assert_durable_run(case, operation_id: str, result: dict) -> None:
    receipts = store.operation_receipts(case["dsn"], operation_id)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["outcome"] == "success"
    assert receipt["content"]["operation_id"] == operation_id
    assert receipt["content"]["tokens"] == {
        "input_tokens": 1000,
        "cached_input_tokens": 200,
        "output_tokens": 50,
        "reasoning_output_tokens": 10,
    }
    operation = broker.read_operation(case["dsn"], operation_id)
    assert operation["dispatch_state"] in ("observed", "reconciled")
    assert operation["allocation_id"] == case["allocation_id"]
    ledger = store.allocation_status(case["dsn"], case["allocation_id"])
    assert (ledger["consumed"], ledger["reserved"]) == (TOKEN_COST, 0)
    assert result["trajectory"]
    assert artifacts.artifact_available(case["dsn"], case["artifacts_root"], result["trajectory"])


def test_construct_publishes_fixture_bytes_and_preserves_parent_files(migrated_db, tmp_path):
    case = _case(tmp_path, migrated_db, label="bytes")
    operation_id = "p04-construct-bytes"

    result = _construct(case, operation_id=operation_id)

    assert result["status"] == "completed"
    assert result["child"]
    assert result["method_digest"]
    child = genome.load(migrated_db, case["artifacts_root"], result["child"])
    assert child.digest == result["child"]
    assert child.files == {**case["parent"].files, **METHOD_FILES}
    assert child.files["meta/IMPROVE.md"] == case["parent"].files["meta/IMPROVE.md"]
    stored = archive.decision(migrated_db, "capability-construction:" + operation_id)
    assert stored is not None
    assert stored["data"]
    request = archive.decision(migrated_db, "capability-construction:" + operation_id + ":request")
    assert request is not None
    evidence = _read_evidence(case, result["evidence"])
    assert evidence["context_packet"] == case["context_packet"]
    assert evidence["construction"]["interface"] == INTERFACE
    assert evidence["construction"]["parent"] == case["parent"].digest

    operation = broker.read_operation(migrated_db, operation_id)
    instruction = operation["payload"]["payload"]["instruction"]
    assert json.dumps({
        "schema": "rsi-capability/1",
        "interface": INTERFACE,
        "entrypoint": "method.py:invoke",
        "dependencies": ["python-stdlib"],
        "effects": ["return", "solution-files"],
        "limits": {"timeout_ms": 5000, "max_output_bytes": 65536},
    }, sort_keys=True) in instruction
    assert "invoke(request)" in instruction
    assert "request has exactly interface" in instruction
    assert "value (finite JSON input)" in instruction
    assert "files (public solution slots mapped to UTF-8 text)" in instruction
    assert "context (admitted continuation and development evidence)" in instruction
    assert "Return exactly a JSON-compatible object with value (finite JSON result)" in instruction
    assert "files (solution slots mapped to UTF-8 text)" in instruction
    assert "Returned file names must be a subset of request.files" in instruction
    assert "calls your function unchanged" in instruction
    assert "Use evidence.json for the public objective" in instruction
    _assert_durable_run(case, operation_id, result)


@pytest.mark.parametrize("mode", ["noop", "invalid", "outside"])
def test_constructor_refusal_keeps_cost_trajectory_and_parent(migrated_db, tmp_path, mode):
    case = _case(tmp_path, migrated_db, mode=mode, label="refusal-" + mode)
    operation_id = "p04-construct-refusal-" + mode

    result = _construct(case, operation_id=operation_id)

    assert result["status"] == "invalid"
    assert result["child"] is None
    assert result["evidence"]
    assert result["trajectory"]
    stored = archive.decision(migrated_db, "capability-construction:" + operation_id)
    assert stored is not None
    assert stored["data"]
    _assert_durable_run(case, operation_id, result)
    assert genome.load(migrated_db, case["artifacts_root"], case["parent"].digest).files == \
        case["parent"].files


def test_construct_replay_returns_stored_result_without_second_send(migrated_db, tmp_path):
    case = _case(tmp_path, migrated_db, label="replay")
    operation_id = "p04-construct-replay"

    first = _construct(case, operation_id=operation_id)
    calls = _call_file(case, operation_id).read_text(encoding="utf-8").splitlines()
    second = _construct(case, operation_id=operation_id)

    assert second["status"] == first["status"] == "completed"
    assert second["child"] == first["child"]
    assert second["method_digest"] == first["method_digest"]
    assert second["trajectory"] == first["trajectory"]
    assert _call_file(case, operation_id).read_text(encoding="utf-8").splitlines() == calls
    assert len(calls) == 1
    _assert_durable_run(case, operation_id, first)


@pytest.mark.parametrize("boundary,preexisting", [
    ("report", False), ("lineage", False), ("report", True),
])
def test_construct_recovers_captured_bytes_after_publication_crash(
        migrated_db, tmp_path, monkeypatch, boundary, preexisting):
    case = _case(tmp_path, migrated_db, label="capture")
    operation_id = "p04-construct-capture"
    expected = genome.Genome({**case["parent"].files, **METHOD_FILES})
    if preexisting:
        genome.publish(migrated_db, expected, parent=case["parent"].digest,
                       origin="earlier-construction", staging_root=case["staging_root"],
                       artifacts_root=case["artifacts_root"])
    record, publish = archive.record, genome.publish

    def interrupt_record(dsn, identity, **kwargs):
        if identity == "capability-construction:" + operation_id:
            raise RuntimeError("crash at construction report")
        return record(dsn, identity, **kwargs)

    def interrupt_publish(*args, **kwargs):
        raise RuntimeError("crash at genome lineage")

    if boundary == "report":
        monkeypatch.setattr(archive, "record", interrupt_record)
    else:
        monkeypatch.setattr(genome, "publish", interrupt_publish)
    with pytest.raises(RuntimeError, match="crash at"):
        _construct(case, operation_id=operation_id)
    monkeypatch.setattr(archive, "record", record)
    monkeypatch.setattr(genome, "publish", publish)
    workspace, operation_dir = case["agent"].exec_dirs(operation_id, "")
    source = Path(workspace) / "genome" / "skills" / NAME / "method.py"
    source.write_text("def invoke(request):\n    return {'value': 999, 'files': {}}\n")
    (Path(operation_dir) / "events.jsonl").unlink()

    recovered = _construct(case, operation_id=operation_id)

    assert recovered["child"] == expected.digest
    assert genome.load(migrated_db, case["artifacts_root"], recovered["child"]) == expected
    assert len(_call_file(case, operation_id).read_text().splitlines()) == 1
    _assert_durable_run(case, operation_id, recovered)


@pytest.mark.parametrize("changed", ["interface", "context", "allocation"])
def test_construct_rejects_changed_identity_for_existing_operation(migrated_db, tmp_path, changed):
    case = _case(tmp_path, migrated_db, label="identity-" + changed)
    operation_id = "p04-construct-identity-" + changed
    first = _construct(case, operation_id=operation_id)
    assert first["status"] == "completed"
    before = store.allocation_status(migrated_db, case["allocation_id"])

    kwargs = {}
    allocation_id = case["allocation_id"]
    if changed == "interface":
        kwargs["interface"] = "scalar-sum/1"
    elif changed == "context":
        kwargs["context_packet"] = _packet(
            tmp_path, migrated_db, "identity-changed",
            purpose="Construct a method for a different stated purpose.",
        )
    else:
        allocation_id = "p04-tokens-identity-changed"
        _allocation(migrated_db, allocation_id)

    with pytest.raises(capability.CapabilityError, match="identity was reused with different inputs"):
        _construct(case, operation_id=operation_id, allocation_id=allocation_id, **kwargs)

    assert _call_file(case, operation_id).read_text(encoding="utf-8").count("\n") == 1
    assert store.allocation_status(migrated_db, case["allocation_id"]) == before
    assert len(store.operation_receipts(migrated_db, operation_id)) == 1


def test_retain_rejects_candidate_without_a_passing_method_episode(migrated_db, tmp_path):
    case = _case(tmp_path, migrated_db, label="retention")
    result = _construct(case, operation_id="p04-construct-for-retention")
    assert result["status"] == "completed"
    child = genome.load(migrated_db, case["artifacts_root"], result["child"])

    retention = capability.retain(
        migrated_db,
        "p04-retain-without-use",
        genome=child,
        name=NAME,
        episode_id="p04-no-method-episode",
        artifacts_root=case["artifacts_root"],
    )

    assert retention["status"] == "rejected"
