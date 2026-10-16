"""Genome-embedded executable methods and their bounded native invocation."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any

from settlement import artifacts, broker, db, store
from settlement.common import Command, ResultCode, SettlementError

from . import archive
from . import genome as genome_module

CAPABILITY_SCOPE = "rsi-capability-result"
CAPABILITY_INPUT_SCOPE = "rsi-capability-input"
MAX_TIMEOUT_MS = 300_000
MAX_OUTPUT_BYTES = 1_048_576
_DESCRIPTOR_KEYS = frozenset({"schema", "interface", "entrypoint", "dependencies",
                              "effects", "limits"})
_BOOTSTRAP = (
    "import hashlib,json,sys\n"
    "runner_path,meta_path=sys.argv[1],sys.argv[2]\n"
    "if hashlib.sha256(open(meta_path,'rb').read()).hexdigest()!='__META_DIGEST__':\n"
    " raise SystemExit('invocation identity bytes changed')\n"
    "runner=open(runner_path,'rb').read()\n"
    "meta=json.load(open(meta_path,encoding='utf-8'))\n"
    "if hashlib.sha256(runner).hexdigest()!=meta['runner_digest']:\n"
    " raise SystemExit('trusted runner bytes changed')\n"
    "if sys.version!=meta['python_version'] or sys.executable!=meta['python_executable']:\n"
    " raise SystemExit('python runtime identity changed')\n"
    "sys.argv=[runner_path,meta_path]\n"
    "exec(compile(runner,runner_path,'exec'),{'__name__':'__main__','__file__':runner_path})\n"
)


class CapabilityError(SettlementError):
    """A method package, request, or invocation identity is invalid."""


@dataclass(frozen=True)
class Capability:
    name: str
    genome: str
    digest: str
    interface: str
    files: tuple[tuple[str, bytes], ...]
    descriptor: Mapping[str, Any]


@dataclass(frozen=True)
class Invocation:
    operation_id: str
    genome: str
    name: str
    method_digest: str
    input_digest: str
    execution_version: str
    status: str
    value: Any
    files: tuple[tuple[str, bytes], ...]
    output_digest: str | None
    seconds: float
    detail: str


def catalogue(genome: genome_module.Genome) -> tuple[Capability, ...]:
    """Return validated methods, each bound to all bytes under its skill folder."""
    names = sorted({rel.split("/")[1] for rel in genome.files
                    if rel.startswith("skills/") and len(rel.split("/")) >= 3})
    found = []
    for name in names:
        prefix = f"skills/{name}/"
        descriptor_path = prefix + "capability.json"
        if descriptor_path not in genome.files:
            continue
        closure = tuple((rel[len(prefix):], raw) for rel, raw in genome.files.items()
                        if rel.startswith(prefix))
        descriptor = _parse_descriptor(name, dict(closure))
        manifest = _file_manifest(closure)
        digest = _sha(_canonical(manifest))
        frozen_descriptor = MappingProxyType({**descriptor,
                                               "limits": MappingProxyType(dict(descriptor["limits"]))})
        found.append(Capability(name, genome.digest, digest, descriptor["interface"],
                                closure, frozen_descriptor))
    return tuple(found)


def invoke(dsn: str, launcher: Any, genome: genome_module.Genome, name: str,
           request: Mapping[str, Any], *, operation_id: str, allocation_id: str,
           attempt_id: str | None, staging_root: str | Path,
           artifacts_root: str | Path,
           ownership_generation: int | None = None,
           timeout_ms: int | None = None,
           max_output_bytes: int | None = None) -> Invocation:
    """Run one pinned method through the broker and publish its observed result."""
    capability = _capability(genome, name)
    clean_request, request_raw = _request(request, capability)
    input_digest = _sha(request_raw)
    input_artifact_digest = _publish_request(
        dsn, operation_id, request_raw, staging_root, artifacts_root)
    declared_limits = capability.descriptor["limits"]
    timeout = _ceiling(timeout_ms, declared_limits["timeout_ms"], MAX_TIMEOUT_MS,
                       "timeout_ms")
    output_limit = _ceiling(max_output_bytes, declared_limits["max_output_bytes"],
                            MAX_OUTPUT_BYTES, "max_output_bytes")
    if not _nonempty(operation_id) or not _nonempty(allocation_id) or (
            attempt_id is not None and not _nonempty(attempt_id)):
        raise CapabilityError("operation and allocation identities are required")

    runner_raw = Path(__file__).with_name("_method_runner.py").read_bytes()
    runner_digest = _sha(runner_raw)
    python_version = sys.version
    python_executable = str(Path(launcher.staged_python()).resolve())
    entrypoint, function_name = capability.descriptor["entrypoint"].split(":", 1)
    inputs = {"request.json": request_raw, "trusted_runner.py": runner_raw}
    inputs.update({f"method/{rel}": raw for rel, raw in capability.files})
    method_manifest = _file_manifest(tuple(sorted(inputs.items())))
    runtime = {"python_version": python_version, "python_executable": python_executable,
               "implementation": platform.python_implementation()}
    meta = {"interface": capability.interface, "name": name,
            "entrypoint": entrypoint, "function": function_name,
            "request_digest": input_digest,
            "files": method_manifest,
            "input_slots": sorted(clean_request["files"]),
            "runner_digest": runner_digest, "python_version": python_version,
            "python_executable": python_executable,
            "max_output_bytes": output_limit, "timeout_ms": timeout}
    meta_raw = _canonical(meta)
    bootstrap = _BOOTSTRAP.replace("__META_DIGEST__", _sha(meta_raw))
    bound_inputs = {**inputs, "identity.json": meta_raw}
    execution_version = "cap1-" + _sha(_canonical({
        "files": _file_manifest(tuple(sorted(bound_inputs.items()))),
        "runtime": runtime, "bootstrap": _sha(bootstrap.encode())}))
    input_dir, _ = launcher.exec_dirs(operation_id, execution_version)
    input_path = Path(input_dir)
    runner_path = input_path / "trusted_runner.py"
    meta_path = input_path / "identity.json"

    payload = {"profile": "local-process",
               "argv": [python_executable, "-I", "-S", "-B", "-c", bootstrap,
                        str(runner_path), str(meta_path)],
               "timeout_ms": timeout,
               "max_output_bytes": MAX_OUTPUT_BYTES}
    payload = broker.validate_effect(broker.SANDBOX_EXEC, payload)
    decision_id = "capability-use:" + operation_id
    prior = broker.read_operation(dsn, operation_id)
    prior_decision = archive.decision(dsn, decision_id)
    if prior_decision is not None:
        expected = _decision_identity(genome, capability, input_digest, execution_version,
                                      payload, operation_id, allocation_id, attempt_id)
        if any(prior_decision["data"].get(k) != v for k, v in expected.items()):
            raise CapabilityError("operation id already records different method inputs")
        recorded_input = prior_decision["data"].get("input_artifact_digest")
        if recorded_input is not None and recorded_input != input_artifact_digest:
            raise CapabilityError("operation id already records different request bytes")
        replay = _replay(dsn, artifacts_root, prior_decision, capability,
                         input_digest, execution_version)
        if replay.output_digest:
            _protect_artifact(dsn, replay.output_digest, 'rsi-capability-use:' + operation_id)
        return replay
    if prior is not None:
        if (prior.get("payload", {}).get("effect") != broker.SANDBOX_EXEC
                or prior.get("execution_version") != execution_version
                or prior.get("payload", {}).get("payload") != payload):
            raise CapabilityError("operation id already belongs to different invocation inputs")
    else:
        launcher.stage_input(operation_id, execution_version, "request.json", request_raw)
        launcher.stage_input(operation_id, execution_version, "trusted_runner.py", runner_raw)
        for rel, raw in capability.files:
            launcher.stage_input(operation_id, execution_version, "method/" + rel, raw)
        launcher.stage_input(operation_id, execution_version, "identity.json", meta_raw)

    prepared = broker.ensure_operation(dsn, operation_id=operation_id,
                                       effect=broker.SANDBOX_EXEC, payload=payload,
                                       allocation_id=allocation_id, attempt_id=attempt_id,
                                       execution_version=execution_version)
    if prepared.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise CapabilityError("method invocation was not admitted: " + prepared.detail)
    started = time.monotonic()
    status = broker.dispatch_operation(
        dsn, operation_id, launchers={launcher.profile: launcher},
        ownership_generation=ownership_generation)
    elapsed = time.monotonic() - started
    if status.dispatch_state not in ("observed", "reconciled"):
        raise CapabilityError(f"method operation remains unsettled: {status.dispatch_state} "
                              f"{status.next_decision}")
    receipts = store.operation_receipts(dsn, operation_id)
    if len(receipts) != 1:
        raise CapabilityError("settled method operation needs one unambiguous receipt")
    raw_result = receipts[0]['content']
    invocation = _interpret(dsn, artifacts_root, capability, operation_id,
                            input_digest, execution_version, raw_result, elapsed,
                            output_limit, staging_root)
    data = _decision_identity(genome, capability, input_digest, execution_version,
                              payload, operation_id, allocation_id, attempt_id)
    data.update({"status": invocation.status, "seconds": invocation.seconds,
                 "detail": invocation.detail, "output_digest": invocation.output_digest,
                 "result_digest": invocation.output_digest,
                 "containment": False, "profile": launcher.profile,
                 "input_artifact_digest": input_artifact_digest})
    archive.record(dsn, decision_id, kind="capability-use", actor="fixed",
                   subject=capability.digest, data=data)
    _protect_artifact(dsn, input_artifact_digest, 'rsi-capability-input:' + operation_id)
    if invocation.output_digest:
        _protect_artifact(dsn, invocation.output_digest, 'rsi-capability-use:' + operation_id)
    return invocation


def _interpret(dsn: str, artifacts_root: str | Path,
               capability: Capability, operation_id: str, input_digest: str,
               execution_version: str, result: dict[str, Any], elapsed: float,
               output_limit: int, staging_root: str | Path) -> Invocation:
    data = result.get("data") or {}
    wall_ms = data.get("wall_ms")
    seconds = max(float(wall_ms) / 1000, 0) if isinstance(wall_ms, (int, float)) else elapsed
    if data.get("timed_out"):
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "timeout",
                          None, (), None, seconds, "method exceeded its declared timeout")
    worker = data.get("worker")
    if not isinstance(worker, dict) or worker.get("status") not in ("ok", "error"):
        reason = (data.get("stderr") or data.get("parse") or "worker returned no typed output")
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "infra_failed",
                          None, (), None, seconds, str(reason))
    worker_data = worker.get("data")
    if not isinstance(worker_data, dict):
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "infra_failed",
                          None, (), None, seconds, "worker output data is malformed")
    if worker_data.get("kind") == "candidate-error":
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "failed",
                          None, (), None, seconds, str(worker_data.get("detail", "candidate failed")))
    if worker_data.get("kind") == "infra-error":
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "infra_failed",
                          None, (), None, seconds, str(worker_data.get("detail", "runner identity failed")))
    if worker_data.get("kind") != "capability-result":
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "infra_failed",
                          None, (), None, seconds, "trusted runner returned an unknown result")
    if worker.get("status") != "ok":
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "infra_failed",
                          None, (), None, seconds, "trusted runner rejected the invocation")
    output = worker_data.get("output")
    if (not isinstance(output, dict) or set(output) != {"value", "files"}
            or not _is_json(output["value"]) or not isinstance(output["files"], dict)):
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "failed",
                          None, (), None, seconds, "candidate output must have exactly value and files")
    try:
        output_files = _text_files(output["files"])
    except CapabilityError as exc:
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "failed",
                          None, (), None, seconds, str(exc))
    input_slots = set(worker_data.get("input_slots", []))
    if {slot for slot, _ in output_files} - input_slots:
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "failed",
                          None, (), None, seconds, "candidate returned an undeclared solution file")
    output_doc = {"value": output["value"],
                  "files": {slot: content.decode("utf-8")
                            for slot, content in output_files}}
    output_raw = _canonical(output_doc)
    if len(output_raw) > output_limit:
        return Invocation(operation_id, capability.genome, capability.name,
                          capability.digest, input_digest, execution_version, "failed",
                          None, (), None, seconds, "method output exceeds its declared byte limit")
    result_artifact = _publish_result(dsn, operation_id, output_raw, artifacts_root,
                                      staging_root)
    return Invocation(operation_id, capability.genome, capability.name, capability.digest,
                      input_digest, execution_version, "completed", output["value"],
                      tuple(sorted(output_files)), result_artifact, seconds, "")


def _publish_request(dsn: str, operation_id: str, raw: bytes,
                     staging_root: str | Path, artifacts_root: str | Path) -> str:
    manifest = {"kind": CAPABILITY_INPUT_SCOPE, "operation_id": operation_id,
                "files": [{"path": "request.json", "kind": "file", "size": len(raw),
                           "digest": _sha(raw)}]}
    receipt = artifacts.stage_package(
        dsn, staging_root, manifest=manifest, files={"request.json": raw},
        scope=CAPABILITY_INPUT_SCOPE, access_label="candidate",
        format=CAPABILITY_INPUT_SCOPE, version="1")
    result = artifacts.publish_package(
        dsn, Command(request_id="rsi-capability-input-" + receipt["digest"],
                     payload={"digest": receipt["digest"]}), artifacts_root, receipt)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise CapabilityError(result.detail)
    return receipt["digest"]


def _publish_result(dsn: str, operation_id: str, raw: bytes,
                    artifacts_root: str | Path, staging_root: str | Path) -> str:
    manifest = {"kind": CAPABILITY_SCOPE, "operation_id": operation_id,
                "files": [{"path": "result.json", "kind": "file", "size": len(raw),
                           "digest": _sha(raw)}]}
    receipt = artifacts.stage_package(dsn, staging_root, manifest=manifest,
                                      files={"result.json": raw}, scope=CAPABILITY_SCOPE,
                                      format="rsi-capability-result", version="1")
    artifacts.publish_package(dsn, Command(
        request_id="rsi-capability-result-" + receipt["digest"],
        payload={"digest": receipt["digest"]}), artifacts_root, receipt)
    return receipt["digest"]


def _replay(dsn: str, artifacts_root: str | Path,
            record: dict, capability: Capability, input_digest: str,
            execution_version: str) -> Invocation:
    data = record["data"]
    status = data["status"]
    digest = data.get("output_digest")
    value, output_files = None, ()
    if status == "completed":
        if not digest or not artifacts.artifact_available(dsn, artifacts_root, digest):
            raise CapabilityError("settled capability result artifact is unavailable")
        path = Path(artifacts_root) / digest
        package = json.loads(path.read_text(encoding="utf-8"))
        doc = json.loads(bytes.fromhex(package["files"]["result.json"]))
        value = doc["value"]
        output_files = tuple(sorted((slot, text.encode("utf-8"))
                                    for slot, text in doc["files"].items()))
    return Invocation(data["operation_id"], capability.genome, capability.name,
                      capability.digest, input_digest, execution_version, status,
                      value, output_files, digest, float(data["seconds"]),
                      data.get("detail", ""))


def _protect_artifact(dsn: str, digest: str, reference: str) -> None:
    def add(cur, control):
        artifacts._add_reference(cur, digest, "attempt", reference)
        return ResultCode.APPLIED, "capability result protected", {"digest": digest}, [], []

    store.transact(dsn, Command(request_id="rsi-capability-ref:" + reference,
                                payload={"digest": digest}), add)


def _decision_identity(genome: genome_module.Genome, capability: Capability,
                       input_digest: str, execution_version: str, payload: dict,
                       operation_id: str, allocation_id: str,
                       attempt_id: str | None) -> dict:
    return {"operation_id": operation_id, "requested_genome": genome.digest,
            "requested_name": capability.name, "executed_genome": capability.genome,
            "executed_name": capability.name, "method_digest": capability.digest,
            "interface": capability.interface, "input_digest": input_digest,
            "execution_version": execution_version,
            "allocation_id": allocation_id, "attempt_id": attempt_id,
            "payload_digest": _sha(_canonical(payload))}


def _capability(genome: genome_module.Genome, name: str) -> Capability:
    for item in catalogue(genome):
        if item.name == name:
            return item
    raise CapabilityError(f"genome has no executable capability named {name!r}")


def _parse_descriptor(name: str, files: dict[str, bytes]) -> dict[str, Any]:
    raw = files.get("capability.json")
    if raw is None or "SKILL.md" not in files:
        raise CapabilityError(f"skills/{name} needs SKILL.md and capability.json")
    try:
        descriptor = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CapabilityError(f"skills/{name}/capability.json is not finite UTF-8 JSON") from exc
    if not isinstance(descriptor, dict) or set(descriptor) != _DESCRIPTOR_KEYS:
        raise CapabilityError("capability descriptor must have exactly the six declared fields")
    if descriptor["schema"] != "rsi-capability/1":
        raise CapabilityError("unsupported capability descriptor schema")
    if not _nonempty(descriptor["interface"]):
        raise CapabilityError("capability interface must be a nonempty string")
    entrypoint = descriptor["entrypoint"]
    if not isinstance(entrypoint, str) or entrypoint.count(":") != 1:
        raise CapabilityError("entrypoint must be relativePythonFile:identifier")
    source, function = entrypoint.split(":", 1)
    if not _safe_relative(source) or not source.endswith(".py") or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", function) or source not in files:
        raise CapabilityError("entrypoint must name a declared Python file and identifier")
    if descriptor["dependencies"] != ["python-stdlib"]:
        raise CapabilityError("capability dependencies must be exactly python-stdlib")
    if descriptor["effects"] != ["return", "solution-files"]:
        raise CapabilityError("capability effects must be return and solution-files")
    limits = descriptor["limits"]
    if not isinstance(limits, dict) or set(limits) != {"timeout_ms", "max_output_bytes"}:
        raise CapabilityError("capability limits must declare timeout_ms and max_output_bytes")
    timeout, output = limits["timeout_ms"], limits["max_output_bytes"]
    if type(timeout) is not int or not 0 < timeout <= MAX_TIMEOUT_MS:
        raise CapabilityError(f"timeout_ms must be in 1..{MAX_TIMEOUT_MS}")
    if type(output) is not int or not 0 < output <= MAX_OUTPUT_BYTES:
        raise CapabilityError(f"max_output_bytes must be in 1..{MAX_OUTPUT_BYTES}")
    return descriptor


def _request(request: Mapping[str, Any], capability: Capability) -> tuple[dict, bytes]:
    if not isinstance(request, Mapping) or set(request) != {"interface", "value", "files", "context"}:
        raise CapabilityError("request must contain exactly interface, value, files, and context")
    if request["interface"] != capability.interface:
        raise CapabilityError("requested interface does not match capability interface")
    if not isinstance(request["files"], Mapping):
        raise CapabilityError("request files must map declared solution slots to UTF-8 text")
    files = _text_map(request["files"])
    clean = {"interface": request["interface"], "value": request["value"],
             "files": files, "context": request["context"]}
    if not _is_json(clean):
        raise CapabilityError("request must contain only finite JSON values")
    raw = _canonical(clean)
    if len(raw) > artifacts.STAGE_MAX_BYTES:
        raise CapabilityError("request exceeds artifact byte limit")
    if len(files) > artifacts.STAGE_MAX_FILES:
        raise CapabilityError("request contains too many declared solution files")
    return clean, raw


def _text_map(value: Mapping[str, Any]) -> dict[str, str]:
    result = {}
    for path, text in value.items():
        if not isinstance(path, str) or not _safe_relative(path) or not isinstance(text, str):
            raise CapabilityError("solution slots must be safe relative paths with UTF-8 text")
        result[path] = text
    folded = {path.casefold() for path in result}
    if len(folded) != len(result) or any(
            "/".join(path.split("/")[:index]).casefold() in folded
            for path in result for index in range(1, len(path.split("/")))):
        raise CapabilityError("solution slots collide by name or parent path")
    return result


def _text_files(value: Mapping[str, Any]) -> tuple[tuple[str, bytes], ...]:
    return tuple(sorted((path, text.encode("utf-8"))
                        for path, text in _text_map(value).items()))


def _safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return (bool(path) and "\\" not in path and not pure.is_absolute()
            and not PureWindowsPath(path).drive
            and all(part not in ("", ".", "..") for part in path.split("/")))


def _file_manifest(files: tuple[tuple[str, bytes], ...]) -> list[dict[str, Any]]:
    return [{"path": path, "size": len(raw), "sha256": _sha(raw)}
            for path, raw in sorted(files)]


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CapabilityError(f"value is not canonical finite JSON: {exc}") from exc


def _is_json(value: Any) -> bool:
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json(item)
                   for key, item in value.items())
    return False


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant {value}")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _ceiling(requested: int | None, declared: int, maximum: int, label: str) -> int:
    if requested is None:
        return declared
    if type(requested) is not int or not 0 < requested <= maximum:
        raise CapabilityError(f"{label} must be in 1..{maximum}")
    return min(requested, declared)


def _known(dsn: str, identity: str, kind: str, request: dict) -> dict | None:
    found = archive.decision(dsn, identity)
    if found is None:
        return None
    if found['kind'] != kind or any(found['data'].get(k) != v for k, v in request.items()):
        raise CapabilityError('capability decision identity was reused with different inputs')
    return found['data']


def _record(dsn: str, identity: str, kind: str, subject: str, data: dict) -> dict:
    return archive.record(dsn, identity, kind=kind, actor='fixed', subject=subject,
                          data=data)['data']


def _checked_use(dsn: str, genome: genome_module.Genome, name: str,
                 episode_id: str, artifacts_root: str | Path, *,
                 require_condition: bool = False) -> dict:
    from . import gate, verifier
    from . import task as task_module

    method = _capability(genome, name)
    if genome_module.load(dsn, artifacts_root, genome.digest) != genome:
        raise CapabilityError("retention genome bytes changed")
    use = archive.decision(dsn, "capability-use:" + episode_id)
    with db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT genome, task, status, trajectory FROM rsi_episodes WHERE operation_id=%s",
            (episode_id,),
        ).fetchone()
    if row is None or row[0] != genome.digest or row[2] != "completed":
        raise CapabilityError("checked use needs a completed episode of this genome")
    item = task_module.load(dsn, artifacts_root, row[1])
    if item.split != "dev":
        raise CapabilityError("applicability evidence accepts development tasks only")
    verdict = verifier.read_verdict(dsn, episode_id, item.evaluator_version)
    if (verdict is None or type(verdict.passed) is not bool
            or verdict.status != ("passed" if verdict.passed else "failed")
            or not verdict.solution):
        raise CapabilityError("checked use needs a definitive pristine verifier outcome")
    if (use is None or use["kind"] != "capability-use" or use["actor"] != "fixed"
            or use["subject"] != method.digest):
        raise CapabilityError("checked use needs its immutable capability decision")
    data = use["data"]
    expected = {"executed_genome": genome.digest, "requested_genome": genome.digest,
                "executed_name": name, "requested_name": name,
                "method_digest": method.digest, "interface": method.interface,
                "operation_id": episode_id, "status": "completed"}
    required = set(expected) | {"execution_version", "allocation_id", "attempt_id",
                                "payload_digest", "input_digest", "output_digest"}
    if (not required.issubset(data)
            or any(data.get(k) != v for k, v in expected.items())):
        raise CapabilityError("checked use does not match the executed method")
    operation = broker.read_operation(dsn, episode_id)
    receipts = store.operation_receipts(dsn, episode_id)
    payload = operation.get("payload", {}) if operation is not None else {}
    if (operation is None or payload.get("effect") != broker.SANDBOX_EXEC
            or operation.get("execution_version") != data["execution_version"]
            or _sha(_canonical(payload.get("payload"))) != data["payload_digest"]
            or operation.get("allocation_id") != data["allocation_id"]
            or operation.get("attempt_id") != data["attempt_id"]
            or operation.get("dispatch_state") not in ("observed", "reconciled")
            or operation.get("settled") is not True or len(receipts) != 1
            or receipts[0]["outcome"] != "success"):
        raise CapabilityError("checked use needs one settled native operation")

    expected_verifier = verifier.operation_id_for(episode_id, item.evaluator_version)
    verifier_operation = broker.read_operation(dsn, verdict.operation_id)
    verifier_receipts = store.operation_receipts(dsn, verdict.operation_id)
    verifier_payload = (verifier_operation.get("payload", {})
                        if verifier_operation is not None else {})
    if (verdict.operation_id != expected_verifier or verifier_operation is None
            or verifier_payload.get("effect") != broker.SANDBOX_EXEC
            or verifier_operation.get("execution_version") != verdict.solution
            or verifier_operation.get("dispatch_state") not in ("observed", "reconciled")
            or verifier_operation.get("settled") is not True or len(verifier_receipts) != 1
            or verifier_receipts[0]["outcome"] not in ("success", "failure")):
        raise CapabilityError("checked use needs its settled pristine verifier result")
    observed_verdict = verifier._result(
        dsn, verdict.operation_id, item.evaluator_version, verdict.solution)
    if (observed_verdict.operation_id != verdict.operation_id
            or observed_verdict.evaluator_version != verdict.evaluator_version
            or observed_verdict.solution != verdict.solution
            or observed_verdict.status != verdict.status
            or observed_verdict.passed is not verdict.passed):
        raise CapabilityError("recorded verifier outcome differs from its settled receipt")

    result_raw = _load_artifact_file(
        dsn, artifacts_root, data.get("output_digest"), scope=CAPABILITY_SCOPE,
        path="result.json", operation_id=episode_id)
    try:
        result_doc = json.loads(result_raw, parse_constant=_reject_constant)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CapabilityError("checked method result artifact is malformed") from exc
    if (not isinstance(result_doc, dict) or set(result_doc) != {"value", "files"}
            or not _is_json(result_doc["value"]) or not isinstance(result_doc["files"], dict)):
        raise CapabilityError("checked method result artifact is malformed")
    returned_files = _text_map(result_doc["files"])

    if not artifacts.artifact_available(dsn, artifacts_root, verdict.solution):
        raise CapabilityError("checked method evidence is unavailable")
    solution_raw = (Path(artifacts_root) / verdict.solution).read_bytes()
    if _sha(solution_raw) != verdict.solution:
        raise CapabilityError("pristine verifier solution artifact changed")
    try:
        solution_doc = json.loads(solution_raw, parse_constant=_reject_constant)
        manifest = solution_doc["manifest"]
        if (solution_doc.get("scope") != "rsi-solution"
                or manifest.get("kind") != "rsi-solution"
                or manifest.get("task") != item.digest
                or not isinstance(solution_doc["files"], dict)
                or not isinstance(manifest.get("files"), list)):
            raise ValueError("solution package identity differs")
        entries = {entry["path"]: entry for entry in manifest["files"]}
        if len(entries) != len(manifest["files"]) or set(entries) != set(solution_doc["files"]):
            raise ValueError("solution package manifest differs")
        actual = {}
        for path, encoded in solution_doc["files"].items():
            raw = bytes.fromhex(encoded)
            if entries[path] != {"path": path, "kind": "file", "size": len(raw),
                                 "digest": _sha(raw)}:
                raise ValueError("solution file digest differs")
            actual[path] = raw
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise CapabilityError("pristine verifier solution package is invalid") from exc
    expected_files = {path: raw.encode("utf-8") for path, raw in returned_files.items()}
    if actual != expected_files:
        raise CapabilityError("development check did not grade the returned method files")

    trajectory_raw = _load_artifact_file(
        dsn, artifacts_root, row[3], scope="rsi-trajectory", path="events.jsonl")
    try:
        lines = trajectory_raw.decode("utf-8").splitlines()
        if len(lines) != 1:
            raise ValueError("trajectory must contain one native use")
        event = json.loads(lines[0], parse_constant=_reject_constant)
        expected_event = {
            "type": "method.invocation.result", "operation_id": episode_id,
            "genome": genome.digest, "task": item.digest, "name": name,
            "method_digest": method.digest, "input_digest": data["input_digest"],
            "output_digest": data["output_digest"],
            "execution_version": data["execution_version"],
            "allocation_id": data["allocation_id"], "attempt_id": data["attempt_id"],
            "status": "completed",
        }
        if any(event.get(key) != value for key, value in expected_event.items()):
            raise ValueError("trajectory identity differs from the checked use")
        if _canonical(event["value"]) != _canonical(result_doc["value"]):
            raise ValueError("trajectory result differs from its published output")
        file_rows = [{"slot": path, "size": len(raw.encode("utf-8")),
                      "digest": _sha(raw.encode("utf-8"))}
                     for path, raw in sorted(returned_files.items())]
        if event["files"] != file_rows:
            raise ValueError("trajectory files differ from the published output")
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise CapabilityError("checked use trajectory is invalid") from exc

    condition = None
    input_artifact = data.get("input_artifact_digest")
    if input_artifact is not None:
        request_raw = _load_artifact_file(
            dsn, artifacts_root, input_artifact, scope=CAPABILITY_INPUT_SCOPE,
            path="request.json", operation_id=episode_id)
        if _sha(request_raw) != data.get("input_digest"):
            raise CapabilityError("bound request bytes differ from the method input digest")
        try:
            request = json.loads(request_raw, parse_constant=_reject_constant)
            _clean, canonical = _request(request, method)
            context = request["context"]
            if (canonical != request_raw or not isinstance(context, dict)
                    or set(context) != {"continuation", "task_digest"}
                    or context["task_digest"] != item.digest):
                raise ValueError("request does not bind the episode task")
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise CapabilityError("bound method request is invalid") from exc
        condition = {"task_id": item.digest, "value": request["value"],
                     "value_digest": _sha(_canonical(request["value"]))}
    elif require_condition:
        raise CapabilityError("checked use lacks its immutable bound request artifact")

    checked = {"method_digest": method.digest, "interface": method.interface,
               "task": item.digest, "evaluator_version": item.evaluator_version,
               "verdict": verdict.operation_id, "solution": verdict.solution,
               "output_digest": data["output_digest"], "input_digest": data["input_digest"],
               "passed": verdict.passed if gate._known_test_result(dsn, verdict) else None}
    if condition is not None:
        checked["condition"] = condition
        checked["input_artifact_digest"] = input_artifact
    return checked


def _load_artifact_file(dsn: str, artifacts_root: str | Path, digest: str | None, *,
                        scope: str, path: str, operation_id: str | None = None) -> bytes:
    if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not artifacts.artifact_available(dsn, artifacts_root, digest)):
        raise CapabilityError("checked method artifact is unavailable")
    try:
        package_raw = (Path(artifacts_root) / digest).read_bytes()
        if _sha(package_raw) != digest:
            raise ValueError("package digest differs")
        package = json.loads(package_raw, parse_constant=_reject_constant)
        manifest = package["manifest"]
        if (set(package) != {"manifest", "scope", "files"} or package["scope"] != scope
                or manifest["kind"] != scope
                or (operation_id is not None
                    and manifest.get("operation_id") != operation_id)
                or not isinstance(package["files"], dict)
                or set(package["files"]) != {path}):
            raise ValueError("package identity differs")
        content = bytes.fromhex(package["files"][path])
        expected = [{"path": path, "kind": "file", "size": len(content),
                     "digest": _sha(content)}]
        if manifest["files"] != expected:
            raise ValueError("package file manifest differs")
        return content
    except (OSError, KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise CapabilityError("checked method artifact package is invalid") from exc


def _selection_condition(task_id: str, value: Any) -> dict:
    if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{64}", task_id):
        raise CapabilityError("selection task_id must be a canonical task digest")
    if not _is_json(value):
        raise CapabilityError("selection value must be finite JSON")
    canonical = _canonical(value)
    return {"task_id": task_id, "value": json.loads(canonical),
            "value_digest": _sha(canonical)}


def retain(dsn: str, retention_id: str, *, genome: genome_module.Genome, name: str,
           episode_id: str, artifacts_root: str | Path) -> dict:
    """Retain experimental use evidence, without promoting trust or generality."""
    identity = "capability-retention:" + retention_id
    request = {"retention_id": retention_id, "genome": genome.digest,
               "name": name, "episode_id": episode_id}
    known = _known(dsn, identity, "capability-retention", request)
    if known is not None:
        return known
    try:
        checked = _checked_use(dsn, genome, name, episode_id, artifacts_root)
        if checked["passed"] is not True:
            raise CapabilityError("retention requires a passing independent development check")
    except SettlementError as exc:
        report = {**request, "status": "rejected", "reason": str(exc)}
    else:
        report = {**request, **checked, "status": "retained",
                  "scope": "experimental-interface", "reason": "passing development method use"}
    return _record(dsn, identity, "capability-retention", genome.digest, report)


def eligibility(dsn: str, *, genome: genome_module.Genome, name: str,
                interface: str, task_id: str, value: Any,
                artifacts_root: str | Path) -> dict:
    """Compute fresh selection eligibility without recording a decision."""
    condition = _selection_condition(task_id, value)
    report = {"status": "declined", "executed_genome": None,
              "executed_name": None, "method_digest": None, "retention_id": None}
    try:
        from . import task as task_module

        item = task_module.load(dsn, artifacts_root, task_id)
        if item.split != "dev":
            raise CapabilityError("method selection accepts development tasks only")
        method = _capability(genome, name)
        if method.interface != interface:
            raise CapabilityError("requested interface is outside the checked method interface")
        with db.connect(dsn) as conn:
            rows = conn.execute(
                "SELECT d.data, e.created_at FROM rsi_decisions d"
                " JOIN rsi_episodes e ON e.operation_id=d.data->>'episode_id'"
                " WHERE d.kind='capability-retention' AND d.subject=%s"
                " AND d.data->>'name'=%s AND d.data->>'status'='retained'"
                " ORDER BY d.created_at,d.id", (genome.digest, name),
            ).fetchall()
        retained, retained_at = None, None
        for prior, created_at in rows:
            try:
                checked = _checked_use(
                    dsn, genome, name, prior["episode_id"], artifacts_root)
            except (SettlementError, KeyError, TypeError, ValueError, OSError, AttributeError):
                continue
            core = ("method_digest", "interface", "task", "evaluator_version", "verdict",
                    "solution", "output_digest", "input_digest")
            if (checked["passed"] is True and not any(
                    prior.get(key) != checked.get(key) for key in core)):
                retained, retained_at = prior, created_at
                break
        if retained is None:
            raise CapabilityError("method has no passing checked experimental retention")
        contrary = _contrary_use(
            dsn, genome, method, condition, retained_at, artifacts_root)
        if contrary is not None:
            report.update(reason="a checked later native use failed this exact condition",
                          contrary_use=contrary)
        else:
            report.update(status="selected", executed_genome=genome.digest,
                          executed_name=name, method_digest=method.digest,
                          retention_id=retained["retention_id"],
                          reason="checked exact interface; applicability remains conditional")
    except SettlementError as exc:
        report["reason"] = str(exc)
    return report


def select(dsn: str, selection_id: str, *, genome: genome_module.Genome, name: str,
           interface: str, task_id: str, value: Any,
           artifacts_root: str | Path) -> dict:
    """Record selection eligibility for one canonical task and exact input value."""
    condition = _selection_condition(task_id, value)
    identity = "capability-selection:" + selection_id
    request = {"selection_id": selection_id, "requested_genome": genome.digest,
               "requested_name": name, "interface": interface, **condition}
    known = _known(dsn, identity, "capability-selection", request)
    if known is not None:
        return known
    result = eligibility(dsn, genome=genome, name=name, interface=interface,
                         task_id=task_id, value=value, artifacts_root=artifacts_root)
    return _record(dsn, identity, "capability-selection", genome.digest,
                   {**request, **result})


def _contrary_use(dsn: str, genome: genome_module.Genome, method: Capability,
                  condition: dict, retained_at, artifacts_root: str | Path) -> dict | None:
    with db.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT e.operation_id FROM rsi_episodes e"
            " JOIN rsi_decisions d ON d.id='capability-use:' || e.operation_id"
            " WHERE d.kind='capability-use' AND d.subject=%s"
            " AND e.genome=%s AND e.task=%s AND e.status='completed'"
            " AND e.created_at>%s AND d.data->>'executed_name'=%s"
            " AND d.data->>'method_digest'=%s"
            " ORDER BY e.created_at,e.operation_id",
            (method.digest, genome.digest, condition["task_id"], retained_at,
             method.name, method.digest),
        ).fetchall()
    for (episode_id,) in rows:
        try:
            checked = _checked_use(
                dsn, genome, method.name, episode_id, artifacts_root, require_condition=True)
        except (SettlementError, KeyError, TypeError, ValueError, OSError, AttributeError):
            continue
        observed = checked.get("condition")
        if (checked["passed"] is False and observed is not None
                and observed["task_id"] == condition["task_id"]
                and observed["value_digest"] == condition["value_digest"]):
            return {"episode_id": episode_id, "task_id": observed["task_id"],
                    "value": observed["value"], "value_digest": observed["value_digest"],
                    "input_digest": checked["input_digest"],
                    "input_artifact_digest": checked["input_artifact_digest"],
                    "method_digest": checked["method_digest"],
                    "verdict": checked["verdict"], "solution": checked["solution"],
                    "output_digest": checked["output_digest"]}
    return None


def validate_selection(dsn: str, selection: dict, *, genome: genome_module.Genome,
                       name: str, interface: str, task_id: str, value: Any,
                       artifacts_root: str | Path) -> None:
    """Validate the admitted selection without reconsidering later evidence."""
    if not isinstance(selection, dict) or selection.get("status") != "selected":
        raise CapabilityError("method use needs an admitted selection")
    condition = _selection_condition(task_id, value)
    request = {"selection_id": selection.get("selection_id"),
               "requested_genome": genome.digest, "requested_name": name,
               "interface": interface, **condition}
    known = _known(dsn, "capability-selection:" + str(request["selection_id"]),
                   "capability-selection", request)
    if known != selection:
        raise CapabilityError("selection differs from the recorded choice")
    from . import task as task_module

    item = task_module.load(dsn, artifacts_root, task_id)
    if item.split != "dev":
        raise CapabilityError("method selection accepts development tasks only")
    retained = archive.decision(dsn, "capability-retention:" + selection["retention_id"])
    if retained is None or retained["data"].get("status") != "retained":
        raise CapabilityError("selected retention is unavailable")
    checked = _checked_use(dsn, genome, name, retained["data"]["episode_id"], artifacts_root)
    core = ("method_digest", "interface", "task", "evaluator_version", "verdict",
            "solution", "output_digest", "input_digest")
    if (checked["passed"] is not True
            or any(retained["data"].get(key) != checked.get(key) for key in core)
            or checked["interface"] != interface
            or selection["method_digest"] != checked["method_digest"]
            or selection["executed_genome"] != genome.digest
            or selection["executed_name"] != name):
        raise CapabilityError("selected method differs from its checked evidence")


def construct(dsn: str, agent: Any, parent: genome_module.Genome, *, name: str,
              interface: str, context_packet: dict, operation_id: str, allocation_id: str,
              token_ceiling: int, timeout_ms: int, staging_root: str | Path,
              artifacts_root: str | Path) -> dict:
    """Ask the broker-routed constructor for bytes under the declared method ABI."""
    from . import context, meta

    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
        raise CapabilityError('construction name must be a bounded skill directory name')
    if not _nonempty(interface) or len(interface) > 200:
        raise CapabilityError('construction interface must be a bounded nonempty string')
    request = {'parent': parent.digest, 'name': name, 'interface': interface,
               'context_digest': _sha(_canonical(context_packet)), 'operation_id': operation_id,
               'model': agent.provider.model,
               'allocation_id': allocation_id, 'token_ceiling': token_ceiling,
               'timeout_ms': timeout_ms}
    identity = 'capability-construction:' + operation_id
    known = _known(dsn, identity, 'capability-construction', request)
    if known is not None:
        if known['child'] is not None:
            candidate = genome_module.load(dsn, artifacts_root, known['child'])
            if _capability(candidate, name).digest != known['method_digest']:
                raise CapabilityError('constructed method bytes changed')
        return known
    validation = context.validate(dsn, context_packet, artifacts_root=artifacts_root)
    if validation['status'] != 'ready' or context_packet.get('schema') != context.SCHEMA:
        raise CapabilityError('construction requires a ready pinned P03 development packet')
    genome_module.load(dsn, artifacts_root, parent.digest)
    _record(dsn, identity + ':request', 'capability-construction-request', parent.digest, request)
    prefix = f'skills/{name}/'
    descriptor = {'schema': 'rsi-capability/1', 'interface': interface,
                  'entrypoint': 'method.py:invoke', 'dependencies': ['python-stdlib'],
                  'effects': ['return', 'solution-files'],
                  'limits': {'timeout_ms': 5000, 'max_output_bytes': 65536}}
    instruction = (
        f'Construct one reusable Python method in genome/{prefix}. Edit only that directory. '
        'Preserve all other genome bytes. Use standard library only. Never read outside the workspace. '
        'Write SKILL.md with name and description frontmatter, capability.json with exactly this '
        f'descriptor: {json.dumps(descriptor, sort_keys=True)}. '
        'Write method.py defining invoke(request). request has exactly interface (the version above), '
        'value (finite JSON input), files (public solution slots mapped to UTF-8 text), and context '
        '(admitted continuation and development evidence). '
        'For task episodes, context has exactly continuation (the original admitted context) '
        'and task_digest (the canonical task identity). Read continuation fields inside '
        'request["context"]["continuation"]. '
        'Return exactly a JSON-compatible object with value (finite JSON result) and files '
        '(solution slots mapped to UTF-8 text). '
        'Returned file names must be a subset of request.files. Do not guess hidden paths. '
        'The fixed child adapter handles serialization. It calls your function unchanged. '
        'Use evidence.json for the public objective, method specification and development evidence. '
        'Do not claim to have passed independent checks. Explain the procedure in your final message.'
    )
    capture_id = identity + ':candidate'
    captured = _known(dsn, capture_id, 'capability-construction-capture', request)
    if captured is None:
        output = meta.execute(
            dsn, agent, parent, operation_id=operation_id,
            evidence=lambda: _canonical({'construction': request, 'context_packet': context_packet}),
            files={**{'genome/' + rel: raw for rel, raw in parent.files.items()},
                   'AGENTS.md': instruction.encode()}, instruction=instruction,
            allocation_id=allocation_id, token_ceiling=token_ceiling, timeout_ms=timeout_ms,
            staging_root=Path(staging_root), artifacts_root=Path(artifacts_root))
        report = {**request, 'status': output.status, 'child': None, 'method_digest': None,
                  'evidence': output.evidence, 'trajectory': output.trajectory, 'detail': output.detail}
    else:
        report = dict(captured)
    if report['status'] == 'completed':
        try:
            if captured is None:
                candidate = genome_module.from_dir(output.workspace / 'genome', parent.harness)
            else:
                digest = captured['child']
                if not artifacts.artifact_available(dsn, artifacts_root, digest):
                    raise CapabilityError('captured construction artifact is unavailable')
                package = json.loads((Path(artifacts_root) / digest).read_bytes())
                candidate = genome_module.Genome(
                    {rel: bytes.fromhex(raw) for rel, raw in package['files'].items()},
                    harness=parent.harness)
                if candidate.digest != digest:
                    raise CapabilityError('captured construction bytes changed')
            before = {rel: raw for rel, raw in parent.files.items() if not rel.startswith(prefix)}
            after = {rel: raw for rel, raw in candidate.files.items() if not rel.startswith(prefix)}
            if before != after or candidate.digest == parent.digest:
                raise CapabilityError('construction must change only the assigned method directory')
            method = _capability(candidate, name)
            if method.interface != interface:
                raise CapabilityError('constructed method uses a different interface')
            if captured is None:
                receipt = artifacts.stage_package(
                    dsn, staging_root, manifest=candidate._manifest(),
                    files=dict(candidate.files), scope=genome_module.SCOPE, format='rsi-genome')
                published = artifacts.publish_package(dsn, Command(
                    request_id='rsi-genome-art-' + candidate.digest,
                    payload={'digest': candidate.digest}), artifacts_root, receipt)
                if published.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                    raise CapabilityError('constructed artifact not published: ' + published.detail)
                _protect_artifact(dsn, candidate.digest, capture_id)
                _record(dsn, capture_id, 'capability-construction-capture', candidate.digest,
                        {**report, 'child': candidate.digest, 'method_digest': method.digest})
            genome_module.publish(dsn, candidate, parent=parent.digest,
                                  origin='capability-construction:' + operation_id,
                                  staging_root=staging_root, artifacts_root=artifacts_root)
            report.update(child=candidate.digest, method_digest=method.digest)
        except SettlementError as exc:
            report.update(status='invalid', child=None, method_digest=None, detail=str(exc))
    return archive.record(dsn, identity, kind='capability-construction', actor='ai',
                          subject=report['child'] or parent.digest, data=report)['data']
