"""Representation-01 invocation profile, runner and durable step state.

Covers RPR-02 (package/profile and interpretation boundary), RPR-05 (real
execution with independent checking and costs) and RPR-07 (restart and
subsequent use) for the cognitive batch.

The profile is a bounded JSON invocation over ``python <entry>
<request.json> <response.json>`` with actions encode/start/advance/decode.
Generated entries execute exclusively through the Launcher/broker boundary
(``sandbox-exec`` via a caller-supplied launcher, normally
``launcher_local.LocalLauncher``); the host never imports or calls
generated Python. A separately supplied trusted source checker is invoked
by the controller through the same boundary. Durable step state reuses the
existing settlement tables only: every component invocation and every
witness query is a real broker operation with real receipts, and per-step
records are additional receipts on those operations, so a fresh process
resumes from the database without rerunning settled effects. Composition
records reuse ``capability_versions``; no new tables, no second registry,
no second event log, no generic RPC framework and no universal
interpreter are introduced here.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from . import artifacts, broker, capabilities, db, store
from .common import Command, CommandResult, ResultCode, SettlementError

PROFILE = "representation-01"
PROFILE_VERSION = "representation-01/1"
SUPPORTED_VERSIONS = (PROFILE_VERSION,)
ACTIONS = ("encode", "start", "advance", "decode")
ACTION_ROLE = {"encode": "adapter", "start": "core",
               "advance": "core", "decode": "adapter"}

CORE_FILENAME = "core.py"
ADAPTER_FILENAME = "adapter.py"
DESCRIPTION_FILENAME = "DESCRIPTION.md"
ROLE_FILES = {"core": CORE_FILENAME, "adapter": ADAPTER_FILENAME}

MAX_WITNESS_QUERIES = 16
MAX_VALIDATION_QUERIES = 2
MAX_INVOCATIONS = 64
TASK_ELAPSED_S = 120.0
INVOCATION_TIMEOUT_MS = 2000
MAX_MESSAGE_BYTES = 65536
MAX_REASON_CHARS = 256

FEEDBACK_VERDICTS = ("preserved", "not_preserved", "invalid", "unknown")
ENTRY_REFUSALS = ("unknown-version", "malformed", "stale-identity",
                  "oversize", "unsupported")
DISPOSITIONS = ("improved", "no_improvement", "unsupported", "refused",
                "budget_exhausted", "paused")


class ProfileRefusal(SettlementError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail[:MAX_REASON_CHARS]
        super().__init__(f"representation-01 refused: {reason}"
                         + (f": {self.detail}" if self.detail else ""))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def check_version(version: Any) -> str:
    if version not in SUPPORTED_VERSIONS:
        raise ProfileRefusal("unknown-version", f"unsupported {version!r}")
    return str(version)


def _identity_token(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProfileRefusal("malformed", f"{name} must be a non-empty string")
    if len(value) > 128 or any(c not in
       "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in value):
        raise ProfileRefusal("malformed", f"{name} has an illegal shape")
    return value


def build_request(action: str, *, task_id: str, composition_id: str,
                  core_digest: str, adapter_digest: str, state: Any,
                  payload: dict, remaining: dict) -> dict:
    if action not in ACTIONS:
        raise ProfileRefusal("malformed", f"unknown action {action!r}")
    if not isinstance(payload, dict) or not isinstance(remaining, dict):
        raise ProfileRefusal("malformed", "payload and budget must be objects")
    return {"profile": PROFILE, "profile_version": PROFILE_VERSION,
            "action": action, "task_id": task_id,
            "composition_id": composition_id, "core_digest": core_digest,
            "adapter_digest": adapter_digest, "state": state,
            "payload": payload, "budget": remaining}


def request_bytes(request: dict) -> bytes:
    raw = canonical_bytes(request)
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProfileRefusal("oversize",
                             f"request {len(raw)} bytes exceeds {MAX_MESSAGE_BYTES}")
    return raw


def _bounded_reason(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_REASON_CHARS:
        raise ProfileRefusal("malformed", "reason must be a bounded string")
    return value


def _check_identity_echo(response: dict, *, task_id: str,
                         composition_id: str, core_digest: str,
                         adapter_digest: str) -> None:
    for key, want in (("task_id", task_id),
                      ("composition_id", composition_id),
                      ("core_digest", core_digest),
                      ("adapter_digest", adapter_digest)):
        if response.get(key) != want:
            raise ProfileRefusal("stale-identity",
                                 f"response {key} does not match the invocation")


_RESULT_KEYS = {
    "encode": {"encoded_object", "aux", "applicability"},
    "start": {"proposal"},
    "advance": {"proposal"},
    "decode": {"candidate_source"},
}
_FINAL_KEYS = {"final_object"}


def validate_response(action: str, response: Any, *, task_id: str,
                      composition_id: str, core_digest: str,
                      adapter_digest: str) -> dict:
    if not isinstance(response, dict):
        raise ProfileRefusal("malformed", "response must be a JSON object")
    if response.get("profile") != PROFILE:
        raise ProfileRefusal("malformed", "response profile mismatch")
    check_version(response.get("profile_version"))
    if response.get("action") != action:
        raise ProfileRefusal("malformed", "response action mismatch")
    _check_identity_echo(response, task_id=task_id,
                         composition_id=composition_id,
                         core_digest=core_digest, adapter_digest=adapter_digest)
    status = response.get("status")
    if status == "refuse":
        reason = response.get("reason")
        if reason not in ENTRY_REFUSALS:
            raise ProfileRefusal("malformed",
                                 f"unknown refusal reason {reason!r}")
        _bounded_reason(reason)
        detail = response.get("detail", "")
        if not isinstance(detail, str) or len(detail) > MAX_REASON_CHARS:
            raise ProfileRefusal("malformed", "refusal detail is not bounded")
        return {"status": "refuse", "reason": reason, "detail": detail}
    if action in ("start", "advance") and status == "final":
        result = response.get("result")
        if not isinstance(result, dict) or set(result) != _FINAL_KEYS:
            raise ProfileRefusal("malformed",
                                 "final result must carry only final_object")
        return {"status": "final", "result": result,
                "state": response.get("state")}
    if status != "ok":
        raise ProfileRefusal("malformed", f"unknown status {status!r}")
    result = response.get("result")
    if not isinstance(result, dict) or set(result) != _RESULT_KEYS[action]:
        raise ProfileRefusal("malformed",
                             f"ok result keys for {action} are"
                             f" {sorted(_RESULT_KEYS[action])}")
    if action == "encode":
        app = result["applicability"]
        if not isinstance(app, dict) or set(app) != {"supported", "reason"} \
                or not isinstance(app["supported"], bool):
            raise ProfileRefusal("malformed", "applicability shape is wrong")
        _bounded_reason(app["reason"])
    return {"status": status, "result": result, "state": response.get("state")}


def parse_response_bytes(action: str, raw: bytes, *, task_id: str,
                         composition_id: str, core_digest: str,
                         adapter_digest: str) -> dict:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProfileRefusal("oversize",
                             f"response {len(raw)} bytes exceeds"
                             f" {MAX_MESSAGE_BYTES}")
    try:
        response = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ProfileRefusal("malformed", "response is not UTF-8 JSON")
    return validate_response(action, response, task_id=task_id,
                             composition_id=composition_id,
                             core_digest=core_digest,
                             adapter_digest=adapter_digest)


def manifest_for(core_bytes: bytes, adapter_bytes: bytes,
                 description_bytes: bytes, *,
                 version: str = PROFILE_VERSION) -> dict:
    check_version(version)
    files = {CORE_FILENAME: core_bytes, ADAPTER_FILENAME: adapter_bytes,
             DESCRIPTION_FILENAME: description_bytes}
    entries = [{"path": path, "digest": sha_hex(raw), "size": len(raw)}
               for path, raw in files.items()]
    return {"files": entries, "entry": CORE_FILENAME,
            "representation_entries": dict(ROLE_FILES),
            "verify_args": ["--selftest"], "profile": PROFILE,
            "profile_version": version}


def resolve_entry(manifest: dict, role: str) -> str:
    named = (manifest.get("representation_entries") or {}).get(role)
    paths = {e.get("path") for e in manifest.get("files", [])
             if isinstance(e, dict)}
    if not isinstance(named, str) or named not in paths:
        raise SettlementError(
            f"representation manifest names no {role} entry")
    return named


def manifest_component_digests(manifest: dict) -> dict:
    by_path = {e.get("path"): e for e in manifest.get("files", [])
               if isinstance(e, dict)}
    return {role: str(by_path[resolve_entry(manifest, role)]["digest"])
            for role in ("core", "adapter")}


def _package_files(artifacts_root: str | Path, digest: str) -> dict:
    raw = (Path(artifacts_root) / digest).read_bytes()
    if sha_hex(raw) != digest:
        raise SettlementError(
            f"representation package {digest[:12]} bytes do not match")
    try:
        package = json.loads(raw.decode("utf-8"))
        return {rel: bytes.fromhex(hexed)
                for rel, hexed in package["files"].items()}
    except (ValueError, KeyError, TypeError) as exc:
        raise SettlementError(
            f"representation package {digest[:12]} is unreadable: {exc}")


def stage_composition(staging_root: str | Path, *, core_bytes: bytes,
                      adapter_bytes: bytes, description: bytes,
                      version: str = PROFILE_VERSION,
                      scope: str = "rpr", dsn: str | None = None) -> dict:
    manifest = manifest_for(core_bytes, adapter_bytes, description,
                            version=version)
    files = {CORE_FILENAME: core_bytes, ADAPTER_FILENAME: adapter_bytes,
             DESCRIPTION_FILENAME: description}
    digests = manifest_component_digests(manifest)
    return artifacts.stage_package(
        dsn, staging_root, manifest=manifest, files=files, scope=scope,
        access_label="public", format=PROFILE, version=version,
        dependencies=[f"core:{digests['core']}",
                      f"adapter:{digests['adapter']}"])


def publish_composition(dsn: str, cmd: Command, artifacts_root: str | Path,
                        receipt: dict) -> CommandResult:
    if (receipt.get("manifest") or {}).get("profile") != PROFILE:
        raise SettlementError("staging receipt is not a representation-01 package")
    return artifacts.publish_package(dsn, cmd, artifacts_root, receipt)


def record_composition(dsn: str, cmd: Command, artifacts_root: str | Path, *,
                       composition_id: str, package_digest: str, role: str,
                       protocol_id: str = "",
                       scope: dict | None = None) -> CommandResult:
    _identity_token(composition_id, "composition_id")
    if role not in ("source", "transfer"):
        raise SettlementError(f"unknown composition role {role!r}")
    if not artifacts.artifact_available(dsn, artifacts_root, package_digest):
        raise SettlementError(
            f"package {package_digest[:12]} is not available")
    files = _package_files(artifacts_root, package_digest)
    package = json.loads((Path(artifacts_root) / package_digest)
                         .read_bytes().decode("utf-8"))
    digests = manifest_component_digests(package["manifest"])
    core_digest, adapter_digest = digests["core"], digests["adapter"]
    if files[CORE_FILENAME] is None or files[ADAPTER_FILENAME] is None:
        raise SettlementError("representation package misses core or adapter")

    def _fn(cur, control):
        cur.execute("SELECT id FROM capability_versions WHERE id = %s",
                    (composition_id,))
        if cur.fetchone() is not None:
            raise SettlementError(
                f"representation composition {composition_id} already recorded")
        from psycopg.types.json import Json
        cur.execute(
            "INSERT INTO capability_versions (id, family, invocation,"
            " artifact_digest, applicability, scope, dependencies, protocol_id)"
            " VALUES (%s, 'representation', %s, %s, %s, %s, %s, %s)",
            (composition_id,
             Json({"profile": PROFILE, "profile_version": PROFILE_VERSION,
                   "entries": dict(ROLE_FILES), "verify_args": ["--selftest"]}),
             package_digest,
             Json({"role": role, "core_digest": core_digest,
                   "adapter_digest": adapter_digest}),
             Json({"role": role}), Json([core_digest, adapter_digest]),
             protocol_id))
        return (ResultCode.APPLIED,
                f"representation composition {composition_id} recorded",
                {"composition_id": composition_id,
                 "package_digest": package_digest,
                 "core_digest": core_digest,
                 "adapter_digest": adapter_digest, "role": role},
                [("representation.composed", {"composition_id": composition_id})],
                [])
    return store.transact(dsn, cmd, _fn)


def get_composition(dsn: str, composition_id: str) -> dict | None:
    return capabilities.get_version(dsn, composition_id)


def check_composition(dsn: str, artifacts_root: str | Path,
                      composition_id: str) -> dict:
    row = get_composition(dsn, composition_id)
    if row is None or (row.get("family") or "") != "representation":
        raise SettlementError(
            f"unknown representation composition {composition_id}")
    recorded = dict(row.get("applicability") or {})
    package_digest = row.get("artifact_digest") or ""
    checked = artifacts.verify_bytes(dsn, artifacts_root, package_digest)
    if not checked.get("ok"):
        raise SettlementError(
            f"representation composition {composition_id} binding invalid:"
            f" {checked.get('reason')}")
    files = _package_files(artifacts_root, package_digest)
    live = {role: sha_hex(files[ROLE_FILES[role]]) for role in ("core", "adapter")}
    for role in ("core", "adapter"):
        if live[role] != recorded.get(f"{role}_digest"):
            raise SettlementError(
                f"representation composition {composition_id} binding invalid:"
                f" live {role} bytes differ")
    return {"composition_id": composition_id, "ok": True,
            "package_digest": package_digest,
            "core_digest": live["core"], "adapter_digest": live["adapter"],
            "role": recorded.get("role", "")}


def compositions_share_core(first: dict, second: dict) -> bool:
    return bool(first.get("core_digest")) and \
        first.get("core_digest") == second.get("core_digest")


def step_op_id(run_id: str, task_id: str, action: str, seq: int) -> str:
    _identity_token(run_id, "run_id")
    _identity_token(task_id, "task_id")
    if action not in ACTIONS or seq < 0:
        raise SettlementError(f"illegal step identity {action}:{seq}")
    return f"rpr:{run_id}:{task_id}:{action}:{seq:04d}"


def check_op_id(run_id: str, task_id: str, seq: int) -> str:
    _identity_token(run_id, "run_id")
    _identity_token(task_id, "task_id")
    if seq < 0:
        raise SettlementError(f"illegal check identity {seq}")
    return f"rpr:{run_id}:{task_id}:check:{seq:04d}"


def _receipts(dsn: str, operation_id: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT receipt_identity, outcome, content FROM receipts"
                        " WHERE operation_id = %s ORDER BY created_at",
                        (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def _find_receipt(receipts: list[dict], identity: str) -> dict | None:
    return next((r for r in receipts
                 if r.get("receipt_identity") == identity), None)


def _sandbox_receipt(receipts: list[dict]) -> dict | None:
    cands = [r for r in receipts
             if (r.get("receipt_identity") or "").startswith("local:")]
    return cands[-1] if cands else None


def _sandbox_timed_out(receipt: dict | None) -> bool:
    try:
        return bool(((receipt or {}).get("content") or {}).get("data", {})
                    .get("timed_out", False))
    except AttributeError:
        return False


def _task_operations(dsn: str, run_id: str, task_id: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, dispatch_state, created_at FROM operations"
                        " WHERE id LIKE %s ORDER BY id",
                        (f"rpr:{run_id}:{task_id}:%",))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return rows


def task_usage(dsn: str, run_id: str, task_id: str) -> dict:
    operations = _task_operations(dsn, run_id, task_id)
    invocations = len([r for r in operations
                       if _find_receipt(_receipts(dsn, r["id"]),
                                        f"rpr-step:{r['id']}") is not None])
    queries = len([r for r in operations
                   if r["id"].split(":")[-2] == "check" and _find_receipt(
                       _receipts(dsn, r["id"]),
                       f"rpr-check:{r['id']}") is not None])
    validation = len([r for r in operations
                      if r["id"].split(":")[-2] == "validate" and _find_receipt(
                          _receipts(dsn, r["id"]),
                          f"rpr-validate:{r['id']}") is not None])
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT min(created_at) FROM operations WHERE id LIKE %s",
                        (f"rpr:{run_id}:{task_id}:%",))
            first = cur.fetchone()[0]
            conn.commit()
    return {"invocations": invocations, "queries": queries,
            "validation": validation,
            "started_at": first.timestamp() if first is not None else None}


def _admit_record(dsn: str, operation_id: str, identity: str,
                  content: dict) -> CommandResult:
    return broker.admit_launcher_receipt(
        dsn, operation_id,
        broker.ReceiptProposal(receipt_identity=identity, content=content,
                               outcome="unknown", provenance="representation-01"))


def _invoke_entry(dsn: str, launcher: Any, *, run_id: str, task_id: str,
                  action: str, seq: int, role: str, entry_bytes: bytes,
                  request: dict, allocation_id: str, attempt_id: str,
                  execution_version: str = "",
                  timeout_ms: int = INVOCATION_TIMEOUT_MS) -> dict:
    entry_rel = ROLE_FILES[role]
    op_id = step_op_id(run_id, task_id, action, seq)
    raw_request = request_bytes(request)
    recorded = _find_receipt(_receipts(dsn, op_id), f"rpr-step:{op_id}")
    if recorded is not None:
        content = dict(recorded.get("content") or {})
        return {"op_id": op_id, "reused": True,
                "timed_out": bool(content.get("timed_out", False)),
                "transport_lost": bool(content.get("transport_lost", False)),
                "response": content.get("response")}
    in_dir, out_dir = launcher.exec_dirs(op_id, execution_version)
    ensured = broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile,
                 "argv": [launcher.staged_python(), f"{in_dir}/{entry_rel}",
                          f"{in_dir}/request.json", f"{out_dir}/response.json"],
                 "timeout_ms": timeout_ms,
                 "max_output_bytes": MAX_MESSAGE_BYTES},
        allocation_id=allocation_id, attempt_id=attempt_id,
        execution_version=execution_version)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        if ensured.code != ResultCode.INVALID_INPUT or \
                broker.read_operation(dsn, op_id) is None:
            raise SettlementError(
                f"representation invocation {op_id} not admitted:"
                f" {ensured.detail}")
    launcher.stage_input(op_id, execution_version, entry_rel, entry_bytes)
    launcher.stage_input(op_id, execution_version, "request.json", raw_request)
    broker.dispatch_operation(dsn, op_id,
                              launchers={launcher.profile: launcher})
    receipts = _receipts(dsn, op_id)
    sandbox = _sandbox_receipt(receipts)
    timed_out = _sandbox_timed_out(sandbox)
    try:
        raw_response = launcher.read_output(op_id, execution_version,
                                            "response.json")
    except OSError:
        raw_response = None
    if timed_out or raw_response is None:
        lost = sandbox is not None and raw_response is None and not timed_out
        content = {"kind": "rpr-step", "run_id": run_id, "task_id": task_id,
                   "action": action, "seq": seq, "role": role, "op_id": op_id,
                   "request_digest": sha_hex(raw_request),
                   "request": json.loads(raw_request.decode("utf-8")),
                   "response": None, "timed_out": timed_out,
                   "transport_lost": lost}
        _admit_record(dsn, op_id, f"rpr-step:{op_id}", content)
        return {"op_id": op_id, "reused": False, "timed_out": timed_out,
                "transport_lost": lost, "response": None}
    try:
        parsed = parse_response_bytes(
            action, raw_response, task_id=request["task_id"],
            composition_id=request["composition_id"],
            core_digest=request["core_digest"],
            adapter_digest=request["adapter_digest"])
    except ProfileRefusal as exc:
        content = {"kind": "rpr-step", "run_id": run_id, "task_id": task_id,
                   "action": action, "seq": seq, "role": role, "op_id": op_id,
                   "request_digest": sha_hex(raw_request),
                   "request": json.loads(raw_request.decode("utf-8")),
                   "response": None, "timed_out": False,
                   "transport_lost": False,
                   "protocol_refusal": {"reason": exc.reason,
                                        "detail": exc.detail}}
        _admit_record(dsn, op_id, f"rpr-step:{op_id}", content)
        raise
    content = {"kind": "rpr-step", "run_id": run_id, "task_id": task_id,
               "action": action, "seq": seq, "role": role, "op_id": op_id,
               "request_digest": sha_hex(raw_request),
               "request": json.loads(raw_request.decode("utf-8")),
               "response": parsed, "timed_out": False,
               "transport_lost": False}
    _admit_record(dsn, op_id, f"rpr-step:{op_id}", content)
    return {"op_id": op_id, "reused": False, "timed_out": False,
            "transport_lost": False, "response": parsed}


def validate_verdict(verdict: Any) -> dict:
    if not isinstance(verdict, dict):
        raise ProfileRefusal("malformed", "checker verdict must be an object")
    if verdict.get("verdict") not in FEEDBACK_VERDICTS:
        raise ProfileRefusal("malformed",
                             "checker verdict vocabulary is fixed")
    measure = verdict.get("measure")
    if measure is not None and \
            (not isinstance(measure, (int, float))
             or not (measure == measure) or measure < 0):
        raise ProfileRefusal("malformed", "checker measure must be a number")
    reason = verdict.get("reason", "")
    if not isinstance(reason, str) or not reason \
            or len(reason) > MAX_REASON_CHARS:
        raise ProfileRefusal("malformed", "checker reason must be bounded")
    return {"verdict": verdict["verdict"], "measure": measure,
            "reason": reason}


def validation_op_id(run_id: str, task_id: str, seq: int) -> str:
    _identity_token(run_id, "run_id")
    _identity_token(task_id, "task_id")
    if seq < 0:
        raise SettlementError(f"illegal validation identity {seq}")
    return f"rpr:{run_id}:{task_id}:validate:{seq:04d}"


def run_checker(dsn: str, launcher: Any, *, run_id: str, task_id: str,
                seq: int, checker_bytes: bytes, checker_id: str,
                candidate_doc: dict, allocation_id: str, attempt_id: str,
                execution_version: str = "",
                timeout_ms: int = INVOCATION_TIMEOUT_MS,
                namespace: str = "check") -> dict:
    if namespace not in ("check", "validate"):
        raise SettlementError(f"unknown checker namespace {namespace!r}")
    op_id = (check_op_id(run_id, task_id, seq) if namespace == "check"
             else validation_op_id(run_id, task_id, seq))
    record_id = f"rpr-{namespace}:{op_id}"
    recorded = _find_receipt(_receipts(dsn, op_id), record_id)
    if recorded is not None:
        content = dict(recorded.get("content") or {})
        return {"op_id": op_id, "reused": True, **dict(content["verdict"])}
    candidate_raw = canonical_bytes(candidate_doc)
    if len(candidate_raw) > MAX_MESSAGE_BYTES:
        return {"op_id": op_id, "reused": False, "verdict": "invalid",
                "measure": None, "reason": "oversize"}
    in_dir, out_dir = launcher.exec_dirs(op_id, execution_version)
    ensured = broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile,
                 "argv": [launcher.staged_python(), f"{in_dir}/checker.py",
                          f"{in_dir}/candidate.json", f"{out_dir}/verdict.json"],
                 "timeout_ms": timeout_ms,
                 "max_output_bytes": MAX_MESSAGE_BYTES},
        allocation_id=allocation_id, attempt_id=attempt_id,
        execution_version=execution_version)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        if ensured.code != ResultCode.INVALID_INPUT or \
                broker.read_operation(dsn, op_id) is None:
            raise SettlementError(
                f"representation check {op_id} not admitted: {ensured.detail}")
    launcher.stage_input(op_id, execution_version, "checker.py", checker_bytes)
    launcher.stage_input(op_id, execution_version, "candidate.json",
                         candidate_raw)
    broker.dispatch_operation(dsn, op_id,
                              launchers={launcher.profile: launcher})
    receipts = _receipts(dsn, op_id)
    if _sandbox_timed_out(_sandbox_receipt(receipts)):
        verdict = {"verdict": "unknown", "measure": None, "reason": "timeout"}
    else:
        try:
            raw = launcher.read_output(op_id, execution_version,
                                       "verdict.json")
            verdict = validate_verdict(json.loads(raw.decode("utf-8")))
        except (OSError, ValueError, ProfileRefusal):
            verdict = {"verdict": "unknown", "measure": None,
                       "reason": "checker-failure"}
    _admit_record(dsn, op_id, record_id,
                  {"kind": f"rpr-{namespace}", "run_id": run_id,
                   "task_id": task_id, "seq": seq, "op_id": op_id,
                   "checker_id": checker_id,
                   "checker_digest": sha_hex(checker_bytes),
                   "candidate_digest": sha_hex(candidate_raw),
                   "candidate": json.loads(candidate_raw.decode("utf-8")),
                   "verdict": verdict})
    return {"op_id": op_id, "reused": False, **verdict}


def _usage_or_raise(usage: dict, started: float, now: float) -> None:
    if usage["invocations"] >= MAX_INVOCATIONS:
        raise ProfileRefusal("oversize", "component invocation budget exhausted")
    if now - started >= TASK_ELAPSED_S:
        raise ProfileRefusal("oversize", "task elapsed budget exhausted")


def _remaining(usage: dict, started: float, now: float) -> dict:
    return {"remaining_invocations": MAX_INVOCATIONS - usage["invocations"],
            "remaining_queries": MAX_WITNESS_QUERIES - usage["queries"],
            "remaining_ms": max(0, int((TASK_ELAPSED_S - (now - started))
                                      * 1000))}


def _best_verified(dsn: str, run_id: str, task_id: str) -> dict:
    best: dict = {"measure": None, "candidate": None, "verdicts": []}
    for row in _task_operations(dsn, run_id, task_id):
        for identity in (f"rpr-check:{row['id']}", f"rpr-validate:{row['id']}"):
            found = _find_receipt(_receipts(dsn, row["id"]), identity)
            if found is None:
                continue
            content = dict(found.get("content") or {})
            verdict = dict(content.get("verdict") or {})
            best["verdicts"].append({"op_id": row["id"],
                                     **verdict})
            doc = content.get("candidate") or {}
            raw = doc.get("candidate", doc) if isinstance(doc, dict) else doc
            if verdict.get("verdict") == "preserved" and \
                    verdict.get("measure") is not None and \
                    (best["measure"] is None
                     or verdict["measure"] < best["measure"]):
                best["measure"] = verdict["measure"]
                best["candidate"] = raw
    return best


def _task_steps(dsn: str, run_id: str, task_id: str) -> list[dict]:
    steps: list[dict] = []
    for row in _task_operations(dsn, run_id, task_id):
        receipts = _receipts(dsn, row["id"])
        for identity in (f"rpr-step:{row['id']}", f"rpr-check:{row['id']}",
                         f"rpr-validate:{row['id']}"):
            found = _find_receipt(receipts, identity)
            if found is None:
                continue
            content = dict(found.get("content") or {})
            steps.append({"op_id": row["id"], "kind": content.get("kind"),
                          "action": content.get("action"),
                          "seq": content.get("seq"),
                          "timed_out": bool(content.get("timed_out", False)),
                          "response": content.get("response"),
                          "verdict": content.get("verdict")})
    return steps


def run_task(dsn: str, launcher: Any, artifacts_root: str | Path, *,
             run_id: str, task_id: str, composition_id: str,
             source_task: Any, domain_spec: dict,
             checker_bytes: bytes, checker_id: str,
             initial_incumbent: Any, initial_measure: float,
             allocation_id: str, attempt_id: str, execution_version: str = "",
             max_advances: int | None = None, now: Any = None,
             started_at: float | None = None,
             candidate_doc: Any = None) -> dict:
    clock = now if callable(now) else time.time
    composition = check_composition(dsn, artifacts_root, composition_id)
    files = _package_files(artifacts_root, composition["package_digest"])
    core_bytes, adapter_bytes = files[CORE_FILENAME], files[ADAPTER_FILENAME]
    core_digest, adapter_digest = (composition["core_digest"],
                                  composition["adapter_digest"])
    doc_of = candidate_doc or (lambda proposal, _task, _aux:
                               {"task_id": task_id, "source_task": _task,
                                "aux": _aux, "candidate": proposal,
                                "role": "candidate"})
    usage = task_usage(dsn, run_id, task_id)
    started = started_at if started_at is not None else (
        usage["started_at"] if usage["started_at"] is not None else clock())
    base = {"task_id": task_id, "composition_id": composition_id,
            "core_digest": core_digest, "adapter_digest": adapter_digest}

    def _invoke(action: str, seq: int, role: str, payload: dict,
                state: Any) -> dict:
        live = task_usage(dsn, run_id, task_id)
        _usage_or_raise(live, started, clock())
        entry = core_bytes if role == "core" else adapter_bytes
        return _invoke_entry(
            dsn, launcher, run_id=run_id, task_id=task_id, action=action,
            seq=seq, role=role, entry_bytes=entry,
            request=build_request(action, state=state, payload=payload,
                                  remaining=_remaining(live, started, clock()),
                                  **base),
            allocation_id=allocation_id, attempt_id=attempt_id,
            execution_version=execution_version)

    def _check(seq: int, proposal: Any, aux: Any) -> dict:
        live = task_usage(dsn, run_id, task_id)
        if live["queries"] >= MAX_WITNESS_QUERIES:
            raise ProfileRefusal("oversize", "witness query budget exhausted")
        _usage_or_raise(live, started, clock())
        return run_checker(
            dsn, launcher, run_id=run_id, task_id=task_id, seq=seq,
            checker_bytes=checker_bytes, checker_id=checker_id,
            candidate_doc=doc_of(proposal, source_task, aux),
            allocation_id=allocation_id, attempt_id=attempt_id,
            execution_version=execution_version)

    def _validate(incumbent: Any, aux: Any, role: str, seq: int) -> dict | None:
        if task_usage(dsn, run_id, task_id)["validation"] \
                >= MAX_VALIDATION_QUERIES:
            return None
        return run_checker(
            dsn, launcher, run_id=run_id, task_id=task_id, seq=seq,
            checker_bytes=checker_bytes, checker_id=checker_id,
            candidate_doc={"task_id": task_id, "source_task": source_task,
                           "aux": aux, "candidate": incumbent, "role": role},
            allocation_id=allocation_id, attempt_id=attempt_id,
            execution_version=execution_version, namespace="validate")

    def _finish(disposition: str, reason: str, aux: Any = None) -> dict:
        best = _best_verified(dsn, run_id, task_id)
        incumbent = best["candidate"] if best["candidate"] is not None \
            else initial_incumbent
        final_check = _validate(incumbent, aux, "final", 1)
        if final_check is not None:
            best = _best_verified(dsn, run_id, task_id)
            incumbent = best["candidate"] if best["candidate"] is not None \
                else initial_incumbent
        final_usage = task_usage(dsn, run_id, task_id)
        return {"run_id": run_id, "task_id": task_id,
                "composition_id": composition_id,
                "core_digest": core_digest, "adapter_digest": adapter_digest,
                "role": composition["role"], "checker_id": checker_id,
                "incumbent": incumbent, "best_measure": best["measure"],
                "initial_measure": initial_measure,
                "verified": bool(final_check is not None and
                                 final_check.get("verdict") == "preserved"),
                "invocations_used": final_usage["invocations"],
                "queries_used": final_usage["queries"],
                "validation_used": final_usage["validation"],
                "elapsed_s": clock() - started,
                "disposition": disposition, "reason": reason,
                "steps": _task_steps(dsn, run_id, task_id)}

    try:
        encoded_step = _invoke(
            "encode", 0, "adapter",
            {"source_task": source_task, "domain_spec": domain_spec}, None)
    except ProfileRefusal as exc:
        return _finish("refused", exc.reason)
    if encoded_step["response"] is None:
        return _finish("refused", "timeout")
    encoded = encoded_step["response"]
    if encoded["status"] == "refuse":
        if encoded["reason"] == "unsupported":
            return _finish("unsupported", encoded.get("detail") or "unsupported")
        return _finish("refused", encoded["reason"])
    applicability = encoded["result"]["applicability"]
    if not applicability["supported"]:
        return _finish("unsupported", applicability["reason"])
    encoded_object = encoded["result"]["encoded_object"]
    aux = encoded["result"].get("aux")
    _validate(initial_incumbent, aux, "initial", 0)
    feedback: dict | None = None
    state: Any = encoded.get("state")
    advances = 0
    proposal_index = 0
    while True:
        action = "start" if proposal_index == 0 else "advance"
        try:
            step = _invoke(
                action, proposal_index, "core",
                {"encoded_object": encoded_object,
                 "feedback": feedback,
                 "limits": {"max_proposals": 1}}, state)
        except ProfileRefusal as exc:
            if exc.reason == "oversize" and \
                    "budget" in (exc.detail or ""):
                return _finish("budget_exhausted", exc.detail)
            return _finish("refused", exc.reason)
        if step["response"] is None:
            feedback = {"verdict": "unknown", "measure": None,
                        "reason": "timeout" if step["timed_out"]
                        else "transport-lost"}
        else:
            current = step["response"]
            if current["status"] == "refuse":
                return _finish("refused", current["reason"])
            state = current.get("state")
            proposal = current["result"].get("proposal") \
                if current["status"] == "ok" \
                else current["result"]["final_object"]
            try:
                decoded = _invoke(
                    "decode", proposal_index, "adapter",
                    {"proposal": proposal, "source_task": source_task,
                     "aux": aux}, None)
            except ProfileRefusal as exc:
                if exc.reason == "oversize" and \
                        "budget" in (exc.detail or ""):
                    return _finish("budget_exhausted", exc.detail)
                return _finish("refused", exc.reason)
            if decoded["response"] is None or \
                    decoded["response"]["status"] == "refuse":
                feedback = {"verdict": "unknown", "measure": None,
                            "reason": "decode-refused"}
            else:
                try:
                    checked = _check(proposal_index,
                                     decoded["response"]["result"]
                                     ["candidate_source"], aux)
                except ProfileRefusal as exc:
                    if exc.reason == "oversize" and \
                            "budget" in (exc.detail or ""):
                        return _finish("budget_exhausted", exc.detail)
                    return _finish("refused", exc.reason)
                feedback = {"verdict": checked["verdict"],
                            "measure": checked["measure"],
                            "reason": checked["reason"]}
            if step["response"]["status"] == "final":
                best = _best_verified(dsn, run_id, task_id)["measure"]
                if best is not None and best < initial_measure:
                    return _finish("improved", "final proposal checked")
                return _finish("no_improvement", "final proposal checked")
        proposal_index += 1
        if action == "advance":
            advances += 1
        if max_advances is not None and advances >= max_advances:
            return _finish("paused", f"{advances} advances reached the cap")


def operator_view(dsn: str, run_id: str, task_id: str) -> dict:
    steps = _task_steps(dsn, run_id, task_id)
    usage = task_usage(dsn, run_id, task_id)
    composition_id = ""
    domain_spec: Any = None
    checker_id = ""
    for entry in steps:
        if entry.get("kind") == "rpr-step" and \
                entry.get("action") == "encode":
            request = ((_find_receipt(
                _receipts(dsn, entry["op_id"]),
                f"rpr-step:{entry['op_id']}") or {}).get("content") or {}) \
                .get("request") or {}
            composition_id = request.get("composition_id", "")
            domain_spec = (request.get("payload") or {}).get("domain_spec")
        if entry.get("kind") == "rpr-check":
            checker_id = (((_find_receipt(
                _receipts(dsn, entry["op_id"]),
                f"rpr-check:{entry['op_id']}") or {}).get("content") or {})
                .get("checker_id", ""))
    composition: dict = {}
    if composition_id:
        row = get_composition(dsn, composition_id)
        if row is not None:
            applied = dict(row.get("applicability") or {})
            composition = {"composition_id": composition_id,
                           "role": applied.get("role", ""),
                           "core_digest": applied.get("core_digest", ""),
                           "adapter_digest": applied.get("adapter_digest", ""),
                           "package_digest": row.get("artifact_digest", "")}
    best = _best_verified(dsn, run_id, task_id)
    checks = [s for s in steps if s.get("kind") == "rpr-check"]
    last_verdict = (checks[-1].get("verdict") or {}) if checks else {}
    finals = [s for s in steps
              if (s.get("response") or {}).get("status") == "final"]
    refuses = [s for s in steps
               if (s.get("response") or {}).get("status") == "refuse"]
    if finals:
        disposition, next_action = "complete", "done"
    elif refuses and (refuses[-1].get("response") or {}).get("reason") \
            == "unsupported":
        disposition, next_action = "unsupported", "done"
    elif refuses:
        disposition, next_action = "refused", "done"
    elif usage["invocations"] >= MAX_INVOCATIONS or \
            usage["queries"] >= MAX_WITNESS_QUERIES:
        disposition, next_action = "capped", "done"
    elif not steps:
        disposition, next_action = "pending", "encode"
    else:
        disposition = "pending"
        last_core = max(
            (s["seq"] for s in steps
             if s.get("action") in ("start", "advance")
             and isinstance(s.get("seq"), int)), default=-1)
        next_action = f"advance:{last_core + 1}"
    return {"run_id": run_id, "task_id": task_id,
            "composition": composition,
            "witness": {"domain_spec": domain_spec,
                        "last_verdict": last_verdict.get("verdict"),
                        "last_measure": last_verdict.get("measure"),
                        "checker_id": checker_id},
            "next_action": next_action,
            "budget": {"invocations_used": usage["invocations"],
                       "invocations_max": MAX_INVOCATIONS,
                       "queries_used": usage["queries"],
                       "queries_max": MAX_WITNESS_QUERIES,
                       "elapsed_max_s": TASK_ELAPSED_S},
            "result": {"best_measure": best["measure"],
                       "verified_candidate": best["candidate"] is not None,
                       "records": len(steps)},
            "disposition": disposition}
