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

from settlement import artifacts, broker, store
from settlement.common import Command, ResultCode, SettlementError

from . import archive
from . import genome as genome_module

CAPABILITY_SCOPE = "rsi-capability-result"
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
    workspace: Path | None = None


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
    decision_id = "capability-use:" + operation_id
    prior = broker.read_operation(dsn, operation_id)
    prior_decision = archive.decision(dsn, decision_id)
    if prior_decision is not None:
        expected = _decision_identity(genome, capability, input_digest, execution_version,
                                      payload, operation_id, allocation_id, attempt_id)
        if any(prior_decision["data"].get(k) != v for k, v in expected.items()):
            raise CapabilityError("operation id already records different method inputs")
        replay = _replay(dsn, launcher, artifacts_root, prior_decision, capability,
                         input_digest, execution_version)
        if replay.output_digest:
            _protect_artifact(dsn, replay.output_digest, operation_id)
        return replay
    if prior is not None:
        if (prior.get("effect") != broker.SANDBOX_EXEC
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
    raw_result = launcher.read_result(operation_id)
    if not isinstance(raw_result, dict):
        raise CapabilityError("settled method operation has no launcher result")
    invocation = _interpret(dsn, launcher, artifacts_root, capability, operation_id,
                            input_digest, execution_version, raw_result, elapsed,
                            output_limit, staging_root)
    data = _decision_identity(genome, capability, input_digest, execution_version,
                              payload, operation_id, allocation_id, attempt_id)
    data.update({"status": invocation.status, "seconds": invocation.seconds,
                 "detail": invocation.detail, "output_digest": invocation.output_digest,
                 "result_digest": invocation.output_digest,
                 "containment": False, "profile": launcher.profile})
    archive.record(dsn, decision_id, kind="capability-use", actor="fixed",
                   subject=capability.digest, data=data)
    if invocation.output_digest:
        _protect_artifact(dsn, invocation.output_digest, operation_id)
    return invocation


def _interpret(dsn: str, launcher: Any, artifacts_root: str | Path,
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
                      tuple(sorted(output_files)), result_artifact, seconds, "",
                      Path(launcher.exec_dirs(operation_id, execution_version)[1]))


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


def _replay(dsn: str, launcher: Any, artifacts_root: str | Path,
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


def _protect_artifact(dsn: str, digest: str, operation_id: str) -> None:
    reference = "rsi-capability-use:" + operation_id

    def add(cur, control):
        artifacts._add_reference(cur, digest, "attempt", reference)
        return ResultCode.APPLIED, "capability result protected", {"digest": digest}, [], []

    store.transact(dsn, Command(request_id="rsi-capability-ref:" + operation_id,
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
