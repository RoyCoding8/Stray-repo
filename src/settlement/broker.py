"""S1 operation broker over the durable store: prepare, dispatch, observe, reconcile.

Recovery model: ``dispatching`` means may-have-been-sent and is committed
before any send. No database transaction stays open during an external call.
A prepared operation is sent at most once per operation identity; a repeat
broker call after a crash returns recorded state and never re-sends unless
the launcher contract proves idempotency or reconciliation concluded.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from dbos import DBOS
from pydantic import BaseModel, Field

from . import db, store
from .common import Command, CommandResult, ConflictPayload, ResultCode, SettlementError

MODEL_INFERENCE = "model-inference"
SANDBOX_EXEC = "sandbox-exec"
ARTIFACT_IO = "artifact-io"
OBSERVATION_ADAPTER = "observation-adapter"
DOMAIN_COMMAND = "domain-command"

EFFECTS = (MODEL_INFERENCE, SANDBOX_EXEC, ARTIFACT_IO, OBSERVATION_ADAPTER, DOMAIN_COMMAND)

ADMITTED_OBSERVATION_ADAPTERS = ("clock", "agenda-probe")
AG01_PROBE_ADAPTER = "agenda-probe"
ADMITTED_DOMAIN_COMMANDS = ("note",)


class InvalidEffect(ValueError):
    code = ResultCode.INVALID_INPUT


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise InvalidEffect(msg)


def _no_extra(payload: dict[str, Any], allowed: set[str], effect: str) -> None:
    extra = set(payload) - allowed
    if extra:
        raise InvalidEffect(f"{effect} rejects unknown keys {sorted(extra)}")


def _nonempty_str(value: Any, msg: str) -> str:
    _require(isinstance(value, str) and value.strip(), msg)
    return value


def validate_effect(effect: str, payload: dict[str, Any]) -> dict[str, Any]:
    _require(effect in EFFECTS, f"unknown effect {effect!r}")
    _require(isinstance(payload, dict), "effect payload must be an object")
    validators = {
        MODEL_INFERENCE: _validate_model,
        SANDBOX_EXEC: _validate_sandbox,
        ARTIFACT_IO: _validate_artifact,
        OBSERVATION_ADAPTER: _validate_observation,
        DOMAIN_COMMAND: _validate_domain,
    }
    return validators[effect](payload)


def _validate_model(p: dict[str, Any]) -> dict[str, Any]:
    _no_extra(p, {"model", "messages", "max_output_tokens", "deadline_ms",
                  "reasoning_effort"}, "model-inference")
    _nonempty_str(p.get("model"), "model-inference needs a model reference")
    messages = p.get("messages")
    _require(isinstance(messages, list) and messages, "model-inference needs non-empty messages")
    for m in messages:
        _require(isinstance(m, dict) and isinstance(m.get("role"), str)
                 and isinstance(m.get("content"), str), "each message needs role/content strings")
    limit = p.get("max_output_tokens")
    _require(isinstance(limit, int) and limit > 0, "max_output_tokens must be a positive integer")
    deadline = p.get("deadline_ms", 300_000)
    _require(isinstance(deadline, int) and deadline > 0, "deadline_ms must be a positive integer")
    effort = p.get("reasoning_effort")
    if effort is not None:
        _require(effort in ("low", "medium", "high"),
                 "reasoning_effort must be low|medium|high")
    return {"model": p["model"], "messages": list(messages),
            "max_output_tokens": limit, "deadline_ms": deadline,
            "reasoning_effort": effort}


def _validate_sandbox(p: dict[str, Any]) -> dict[str, Any]:
    _no_extra(p, {"profile", "argv", "timeout_ms", "max_output_bytes", "cpu_seconds", "memory_bytes"}, "sandbox-exec")
    _require(p.get("profile") in ("local-process", "gvisor"), "sandbox-exec needs profile local-process|gvisor")
    argv = p.get("argv")
    _require(isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv),
             "sandbox-exec needs a non-empty argv of strings")
    timeout = p.get("timeout_ms", 30_000)
    _require(isinstance(timeout, int) and timeout > 0, "timeout_ms must be a positive integer")
    out = p.get("max_output_bytes", 1_048_576)
    _require(isinstance(out, int) and out > 0, "max_output_bytes must be a positive integer")
    for key in ("cpu_seconds", "memory_bytes"):
        if p.get(key) is not None:
            _require(isinstance(p[key], int) and p[key] > 0, f"{key} must be a positive integer")
    return {"profile": p["profile"], "argv": list(argv), "timeout_ms": timeout,
            "max_output_bytes": out, "cpu_seconds": p.get("cpu_seconds"),
            "memory_bytes": p.get("memory_bytes")}


def _validate_artifact(p: dict[str, Any]) -> dict[str, Any]:
    _no_extra(p, {"direction", "relpath", "size_max"}, "artifact-io")
    _require(p.get("direction") in ("read", "write", "stage"), "artifact-io needs direction read|write|stage")
    rel = _nonempty_str(p.get("relpath"), "artifact-io needs a relpath")
    _require(not rel.startswith("/") and ".." not in rel.split("/"), "relpath must be relative without traversal")
    size = p.get("size_max", 1_048_576)
    _require(isinstance(size, int) and size > 0, "size_max must be a positive integer")
    return {"direction": p["direction"], "relpath": rel, "size_max": size}


def _validate_observation(p: dict[str, Any]) -> dict[str, Any]:
    _no_extra(p, {"adapter", "input"}, "observation-adapter")
    _require(p.get("adapter") in ADMITTED_OBSERVATION_ADAPTERS,
             f"unknown observation adapter {p.get('adapter')!r}")
    _require(isinstance(p.get("input", {}), dict), "observation input must be an object")
    return {"adapter": p["adapter"], "input": dict(p.get("input", {}))}


def _validate_domain(p: dict[str, Any]) -> dict[str, Any]:
    _no_extra(p, {"command", "payload", "idempotency_key"}, "domain-command")
    _require(p.get("command") in ADMITTED_DOMAIN_COMMANDS,
             f"unknown domain command {p.get('command')!r}")
    _require(isinstance(p.get("payload", {}), dict), "domain payload must be an object")
    key = _nonempty_str(p.get("idempotency_key"), "domain-command needs an idempotency_key")
    return {"command": p.get("command"), "payload": dict(p.get("payload", {})),
            "idempotency_key": key}


def exposure_schedule(effect: str, payload: dict[str, Any], retries: int = 0) -> tuple[int, str]:
    table = {
        MODEL_INFERENCE: _model_exposure,
        SANDBOX_EXEC: _sandbox_exposure,
        ARTIFACT_IO: lambda p, r: (int(p["size_max"]) // 1024 + 1, "hard-ceiling"),
        OBSERVATION_ADAPTER: lambda p, r: (1, "hard-ceiling"),
        DOMAIN_COMMAND: lambda p, r: (1, "hard-ceiling"),
    }
    units, kind = table[effect](payload, max(int(retries), 0))
    return units, kind


def _model_exposure(p: dict[str, Any], retries: int) -> tuple[int, str]:
    inbound = sum(len(m["content"]) for m in p["messages"]) // 4 + 1
    return (inbound + int(p["max_output_tokens"])) * (retries + 1), "estimated-budget"


def _sandbox_exposure(p: dict[str, Any], retries: int) -> tuple[int, str]:
    from .exec_profile import STOP_SETTLE_S
    return ((int(p["timeout_ms"]) // 1000 + STOP_SETTLE_S + 1)
            * (retries + 1)), "hard-ceiling"


class ReceiptProposal(BaseModel):
    receipt_identity: str
    content: dict[str, Any] = Field(default_factory=dict)
    outcome: str = "unknown"
    provenance: str = ""
    actual_cost: int | None = None

    model_config = {"extra": "forbid"}


class LaunchOutcome(BaseModel):
    sent: bool
    lost: bool = False
    refused_reason: str = ""
    receipt: ReceiptProposal | None = None

    model_config = {"extra": "forbid"}


class BrokerOp(BaseModel):
    operation_id: str
    effect: str
    payload: dict[str, Any]
    execution_version: str = ""
    attempt_id: str | None = None
    dispatch_generation: int = 0

    model_config = {"extra": "forbid"}


class Launcher(Protocol):
    launcher_id: str
    profile: str
    idempotent_resend: bool

    def dispatch(self, op: BrokerOp) -> LaunchOutcome: ...
    def prior_send(self, operation_id: str) -> bool: ...
    def stop(self, operation_id: str) -> bool: ...
    def live_ids(self) -> list[str]: ...
    def is_live(self, operation_id: str) -> bool: ...
    def read_result(self, operation_id: str) -> dict[str, Any] | None: ...

    def stage_input(self, operation_id: str, execution_version: str,
                    relpath: str, data: bytes) -> Any: ...
    def exec_dirs(self, operation_id: str,
                  execution_version: str) -> tuple[str, str]: ...
    def staged_python(self) -> str: ...
    def read_output(self, operation_id: str, execution_version: str,
                    relpath: str) -> bytes: ...

    def prove_never_sent(self, operation_id: str) -> bool:
        """True only with positive proof nothing was ever sent under this identity.

        The proof is valid only while the launcher's run state survives broker
        restarts (stable run directory). Wiping run state voids it: when the
        run directory itself is gone the answer must be False (park, don't reset).
        """


class DispatchStatus(BaseModel):
    operation_id: str
    dispatch_state: str
    reconcile_state: str = "none"
    cancel_state: str = "none"
    settled: bool = False
    sent_this_call: bool = False
    next_decision: str = ""

    model_config = {"extra": "forbid"}


def read_operation(dsn: str, operation_id: str) -> dict[str, Any] | None:
    from psycopg.rows import dict_row

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM operations WHERE id = %s", (operation_id,))
            row = cur.fetchone()
            conn.commit()
            if row is None:
                return None
            out = dict(row)
            out["payload"] = dict(out.get("payload") or {})
            return out


def ensure_operation(
    dsn: str,
    *,
    operation_id: str,
    effect: str,
    payload: dict[str, Any],
    allocation_id: str,
    attempt_id: str | None = None,
    execution_version: str = "",
    retries: int = 0,
) -> CommandResult:
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        return CommandResult(code=ResultCode.INVALID_INPUT,
                             request_id=f"broker-prep-{operation_id}",
                             detail="retries must be a non-negative integer", data={})
    try:
        clean = validate_effect(effect, payload)
    except InvalidEffect as exc:
        return CommandResult(code=ResultCode.INVALID_INPUT, request_id=f"broker-prep-{operation_id}",
                             detail=str(exc), data={})
    exposure, budget_kind = exposure_schedule(effect, clean, retries)
    body = {"effect": effect, "payload": clean, "retries": max(int(retries), 0),
            "budget_kind": budget_kind}
    cmd = Command(
        request_id=f"broker-prep-{operation_id}",
        payload={"operation_id": operation_id, "attempt_id": attempt_id,
                 "allocation_id": allocation_id, "reservation_id": f"res-{operation_id}",
                 "exposure": exposure, "operation": body, "execution_version": execution_version},
    )
    try:
        result = store.prepare_operation(dsn, cmd)
    except ConflictPayload as exc:
        return CommandResult(code=ResultCode.INVALID_INPUT, request_id=cmd.request_id,
                             detail=str(exc), data={})
    result.data.update({"exposure": exposure, "budget_kind": budget_kind, "effect": effect})
    return result


def _status_of(dsn: str, operation_id: str, sent_this_call: bool = False,
               decision: str = "") -> DispatchStatus:
    row = read_operation(dsn, operation_id)
    if row is None:
        return DispatchStatus(operation_id=operation_id, dispatch_state="unknown",
                              sent_this_call=sent_this_call, next_decision=decision or "not-found")
    return DispatchStatus(operation_id=operation_id, dispatch_state=row["dispatch_state"],
                          reconcile_state=row["reconcile_state"], cancel_state=row["cancel_state"],
                          settled=bool(row["settled"]), sent_this_call=sent_this_call,
                          next_decision=decision or _next_for(row))


def _next_for(row: dict[str, Any]) -> str:
    return {"prepared": "awaiting-dispatch", "dispatching": "awaiting-receipt",
            "sent": "awaiting-receipt", "observed": "terminal",
            "unresolved": "needs-reconciliation", "reconciled": "terminal",
            "cancelled": "terminal"}.get(row["dispatch_state"], "unknown")


def _advance(dsn: str, operation_id: str, launcher_id: str, provider_id: str,
             ownership_generation: int | None, grant_version: int | None) -> CommandResult:
    payload: dict[str, Any] = {"operation_id": operation_id, "launcher_id": launcher_id,
                               "provider_id": provider_id}
    if ownership_generation is not None:
        payload["ownership_generation"] = ownership_generation
    if grant_version is not None:
        payload["grant_version"] = grant_version
    return store.advance_dispatch(
        dsn, Command(request_id=f"broker-adv-{operation_id}-{launcher_id}-{uuid.uuid4().hex[:12]}",
                     payload=payload))


def _refusal(dsn: str, operation_id: str, result: CommandResult) -> DispatchStatus:
    mapping = {ResultCode.STALE_REVISION: "stale-ownership",
               ResultCode.UNAUTHORIZED: "stale-grant"}
    return _status_of(dsn, operation_id,
                      decision=mapping.get(result.code, f"refused-{result.code.value}"))


def _revalidate(dsn: str, operation_id: str, launcher_id: str, provider_id: str,
                ownership_generation: int | None,
                grant_version: int | None,
                expected_generation: int) -> DispatchStatus | None:
    current = _advance(dsn, operation_id, launcher_id, provider_id,
                       ownership_generation, grant_version)
    if current.code == ResultCode.ALREADY_APPLIED:
        live = int((current.data or {}).get("dispatch_generation", 0))
        if live != int(expected_generation):
            return _status_of(dsn, operation_id, decision="stale-dispatch-generation")
        return None
    if current.code == ResultCode.APPLIED:
        return _status_of(dsn, operation_id)
    return _refusal(dsn, operation_id, current)


def _decided_receipt(dsn: str, operation_id: str) -> bool:
    return any(r["outcome"] in ("success", "failure")
               for r in store.operation_receipts(dsn, operation_id))


def _park_decided(dsn: str, operation_id: str) -> DispatchStatus:
    _deliver(dsn, f"dispatch:{operation_id}")
    return _status_of(dsn, operation_id, decision="needs-reconciliation")


def admit_launcher_receipt(dsn: str, operation_id: str, receipt: ReceiptProposal) -> CommandResult:
    from .common import payload_digest

    row = read_operation(dsn, operation_id)
    if row is not None and row["dispatch_state"] == "prepared" \
            and int((row["payload"] or {}).get("_dispatch_generation", 0)) == 0:
        return CommandResult(code=ResultCode.INVALID_INPUT,
                             request_id=f"broker-rc-{receipt.receipt_identity}",
                             detail=f"operation {operation_id} was never dispatched;"
                                    " receipt refused",
                             data={"operation_id": operation_id})

    payload: dict[str, Any] = {"operation_id": operation_id,
                               "receipt_identity": receipt.receipt_identity,
                               "content": receipt.content, "outcome": receipt.outcome,
                               "provenance": receipt.provenance}
    if receipt.actual_cost is not None:
        payload["actual_cost"] = receipt.actual_cost
    request_id = f"broker-rc-{receipt.receipt_identity}-{payload_digest(receipt.content)[:12]}"
    return store.admit_receipt(dsn, Command(request_id=request_id, payload=payload))


def _deliver(dsn: str, workflow_identity: str) -> None:
    store.record_delivery(dsn, Command(request_id=f"broker-del-{workflow_identity}",
                                       payload={"workflow_identity": workflow_identity}))


def _resume_dispatching(dsn: str, row: dict[str, Any], operation_id: str,
                          launchers: dict[str, Any] | None,
                          gateway: Any | None,
                          ownership_generation: int | None,
                          grant_version: int | None) -> DispatchStatus:
    if row["dispatch_state"] != "dispatching":
        return _status_of(dsn, operation_id)
    if store.operation_receipts(dsn, operation_id):
        return _status_of(dsn, operation_id)
    body = row["payload"]
    effect = body.get("effect")
    payload = body.get("payload", {})
    if effect == SANDBOX_EXEC:
        launcher = (launchers or {}).get(payload.get("profile"))
    elif effect == OBSERVATION_ADAPTER and (payload.get("adapter") or "") != "clock":
        launcher = (launchers or {}).get("adapter:%s" % payload.get("adapter", ""))
    else:
        return _status_of(dsn, operation_id)
    if launcher is None:
        return _status_of(dsn, operation_id)
    if launcher.read_result(operation_id) is not None:
        return _status_of(dsn, operation_id)
    if _is_live(launcher, operation_id):
        return _status_of(dsn, operation_id)
    prove = getattr(launcher, "prove_never_sent", None)
    if prove is not None:
        if not prove(operation_id):
            return _status_of(dsn, operation_id)
    elif launcher.prior_send(operation_id):
        return _status_of(dsn, operation_id)
    return redispatch_after_reset(
        dsn, operation_id, launchers or {},
        int(body.get("_dispatch_generation", 0)), gateway,
        ownership_generation, grant_version)


def dispatch_operation(
    dsn: str,
    operation_id: str,
    *,
    launchers: dict[str, Any] | None = None,
    gateway: Any | None = None,
    ownership_generation: int | None = None,
    grant_version: int | None = None,
    _crash_after_send: bool = False,
) -> DispatchStatus:
    row = read_operation(dsn, operation_id)
    if row is None:
        return DispatchStatus(operation_id=operation_id, dispatch_state="unknown",
                              next_decision="not-found")
    if row["dispatch_state"] != "prepared":
        return _resume_dispatching(dsn, row, operation_id, launchers,
                                   gateway, ownership_generation,
                                   grant_version)
    body = row["payload"]
    effect = body.get("effect")
    payload = body.get("payload", {})
    if effect == OBSERVATION_ADAPTER and (payload.get("adapter") or "") != "clock":
        return _send_adapter(dsn, row, BrokerOp(operation_id=operation_id, effect=effect,
                                                payload=payload,
                                                execution_version=row["execution_version"],
                                                attempt_id=row["attempt_id"]),
                             launchers or {}, ownership_generation, grant_version,
                             _crash_after_send)
    routes = {MODEL_INFERENCE: _send_model, SANDBOX_EXEC: _send_sandbox,
              OBSERVATION_ADAPTER: _run_inline, DOMAIN_COMMAND: _run_inline}
    if effect == ARTIFACT_IO:
        return _status_of(dsn, operation_id, decision="awaiting-artifact-store")
    if effect not in routes:
        return _status_of(dsn, operation_id, decision="unknown-effect")
    return routes[effect](dsn, row, BrokerOp(operation_id=operation_id, effect=effect,
                                             payload=payload,
                                             execution_version=row["execution_version"],
                                             attempt_id=row["attempt_id"]),
                          launchers or {}, gateway, ownership_generation, grant_version,
                          _crash_after_send)


def _send_sandbox(dsn: str, row: dict, op: BrokerOp, launchers: dict,
                  gateway: Any, ownership_generation: int | None,
                  grant_version: int | None, crash: bool) -> DispatchStatus:
    launcher = launchers.get(op.payload.get("profile"))
    if launcher is None:
        return _status_of(dsn, op.operation_id, decision="incompatible-profile")
    advanced = _advance(dsn, op.operation_id, launcher.launcher_id, "",
                        ownership_generation, grant_version)
    if advanced.code == ResultCode.ALREADY_APPLIED:
        return _status_of(dsn, op.operation_id)
    if advanced.code != ResultCode.APPLIED:
        return _refusal(dsn, op.operation_id, advanced)
    generation = int((advanced.data or {}).get("dispatch_generation", 0))
    held = _revalidate(dsn, op.operation_id, launcher.launcher_id, "",
                       ownership_generation, grant_version, generation)
    if held is not None:
        return held
    if _decided_receipt(dsn, op.operation_id):
        return _park_decided(dsn, op.operation_id)
    if launcher.prior_send(op.operation_id):
        _deliver(dsn, f"dispatch:{op.operation_id}")
        return _status_of(dsn, op.operation_id, decision="needs-reconciliation")
    try:
        outcome = launcher.dispatch(op.model_copy(update={"dispatch_generation": generation}))
    except Exception as exc:
        code = getattr(exc, "code", ResultCode.INCOMPATIBLE_VERSION)
        if code == ResultCode.INCOMPATIBLE_VERSION:
            return _status_of(dsn, op.operation_id, decision="incompatible-profile")
        return _status_of(dsn, op.operation_id, decision=f"launcher-error-{exc}")
    if not outcome.sent:
        return _status_of(dsn, op.operation_id,
                          decision=outcome.refused_reason or "launcher-refused")
    if crash:
        return _status_of(dsn, op.operation_id, sent_this_call=True)
    return _finish_send(dsn, op.operation_id, outcome, generation)


def _send_model(dsn: str, row: dict, op: BrokerOp, launchers: dict,
                gateway: Any, ownership_generation: int | None,
                grant_version: int | None, crash: bool) -> DispatchStatus:
    if gateway is None:
        return _status_of(dsn, op.operation_id, decision="awaiting-gateway")
    advanced = _advance(dsn, op.operation_id, "gateway", op.payload.get("model", ""),
                        ownership_generation, grant_version)
    if advanced.code == ResultCode.ALREADY_APPLIED:
        return _status_of(dsn, op.operation_id)
    if advanced.code != ResultCode.APPLIED:
        return _refusal(dsn, op.operation_id, advanced)
    generation = int((advanced.data or {}).get("dispatch_generation", 0))
    held = _revalidate(dsn, op.operation_id, "gateway", op.payload.get("model", ""),
                       ownership_generation, grant_version, generation)
    if held is not None:
        return held
    if _decided_receipt(dsn, op.operation_id):
        return _park_decided(dsn, op.operation_id)
    from .gateway import GatewayError, ModelRequest

    request = ModelRequest(model=op.payload["model"],
                           messages=tuple(op.payload["messages"]),
                           max_output_tokens=op.payload["max_output_tokens"],
                           deadline_ms=op.payload["deadline_ms"],
                           operation_id=op.operation_id,
                           dispatch_generation=generation,
                           reasoning_effort=op.payload.get("reasoning_effort"))
    try:
        response = gateway.infer(request)
    except Exception:
        response = None
    if response is None or isinstance(response, GatewayError):
        admit_launcher_receipt(dsn, op.operation_id, ReceiptProposal(
            receipt_identity=f"gw:{op.operation_id}:unknown",
            content={"error": getattr(response, "message", "lost-response")},
            outcome="unknown", provenance="gateway"))
        _deliver(dsn, f"dispatch:{op.operation_id}")
        return _status_of(dsn, op.operation_id, sent_this_call=True)
    if crash:
        return _status_of(dsn, op.operation_id, sent_this_call=True)
    usage = response.usage
    outcome = _finish_send(dsn, op.operation_id, LaunchOutcome(
        sent=True, receipt=ReceiptProposal(
            receipt_identity=f"gw:{op.operation_id}",
            content={"text": response.text, "model_meta": dict(response.model_meta),
                     "stop_reason": response.stop_reason,
                     "usage": {"input_tokens": usage.input_tokens,
                               "output_tokens": usage.output_tokens,
                               "model_calls": 1,
                               "charge_units": usage.charge_units,
                               "billed": bool(usage.billed),
                               "provider_enforced_ceiling": usage.provider_enforced_ceiling}},
            outcome="success", provenance="gateway",
            actual_cost=usage.charge_units if usage.billed else (
                usage.input_tokens + usage.output_tokens))),
        generation)
    return outcome


def _send_adapter(dsn: str, row: dict, op: BrokerOp, launchers: dict,
                  ownership_generation: int | None, grant_version: int | None,
                  crash: bool) -> DispatchStatus:
    launcher = launchers.get(f"adapter:{op.payload.get('adapter', '')}")
    if launcher is None:
        return _status_of(dsn, op.operation_id, decision="awaiting-launcher")
    advanced = _advance(dsn, op.operation_id, launcher.launcher_id, "",
                        ownership_generation, grant_version)
    if advanced.code == ResultCode.ALREADY_APPLIED:
        return _status_of(dsn, op.operation_id)
    if advanced.code != ResultCode.APPLIED:
        return _refusal(dsn, op.operation_id, advanced)
    generation = int((advanced.data or {}).get("dispatch_generation", 0))
    held = _revalidate(dsn, op.operation_id, launcher.launcher_id, "",
                       ownership_generation, grant_version, generation)
    if held is not None:
        return held
    if _decided_receipt(dsn, op.operation_id):
        return _park_decided(dsn, op.operation_id)
    if launcher.prior_send(op.operation_id):
        _deliver(dsn, f"dispatch:{op.operation_id}")
        return _status_of(dsn, op.operation_id, decision="needs-reconciliation")
    try:
        outcome = launcher.dispatch(op.model_copy(update={"dispatch_generation": generation}))
    except Exception as exc:
        return _status_of(dsn, op.operation_id, decision=f"launcher-error-{exc}")
    if not outcome.sent:
        return _status_of(dsn, op.operation_id,
                          decision=outcome.refused_reason or "launcher-refused")
    if crash:
        return _status_of(dsn, op.operation_id, sent_this_call=True)
    return _finish_send(dsn, op.operation_id, outcome, generation)


def _run_inline(dsn: str, row: dict, op: BrokerOp, launchers: dict,
                gateway: Any, ownership_generation: int | None,
                grant_version: int | None, crash: bool) -> DispatchStatus:
    advanced = _advance(dsn, op.operation_id, "broker-inline", "",
                        ownership_generation, grant_version)
    if advanced.code == ResultCode.ALREADY_APPLIED:
        return _status_of(dsn, op.operation_id)
    if advanced.code != ResultCode.APPLIED:
        return _refusal(dsn, op.operation_id, advanced)
    generation = int((advanced.data or {}).get("dispatch_generation", 0))
    held = _revalidate(dsn, op.operation_id, "broker-inline", "",
                       ownership_generation, grant_version, generation)
    if held is not None:
        return held
    if op.effect == OBSERVATION_ADAPTER:
        content: dict[str, Any] = {"adapter": op.payload["adapter"]}
        if op.payload["adapter"] == "clock":
            from .common import utcnow

            content["utcnow"] = utcnow().isoformat()
    else:
        content = {"command": op.payload["command"], "payload": op.payload["payload"],
                   "idempotency_key": op.payload["idempotency_key"]}
    return _finish_send(dsn, op.operation_id, LaunchOutcome(
        sent=True, receipt=ReceiptProposal(
            receipt_identity=f"inline:{op.operation_id}", content=content,
            outcome="success", provenance="broker-inline")), generation)


def _admitted(result: Any) -> bool:
    return getattr(result, "code", None) in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)


def _finish_send(dsn: str, operation_id: str, outcome: LaunchOutcome,
                 admitted_generation: int | None = None) -> DispatchStatus:
    if admitted_generation is not None:
        row = read_operation(dsn, operation_id)
        live = int((((row or {}).get("payload")) or {}).get("_dispatch_generation", 0))
        if row is None or live != int(admitted_generation):
            if outcome.receipt is not None:
                admit_launcher_receipt(dsn, operation_id, outcome.receipt)
            elif outcome.lost:
                admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
                    receipt_identity=f"lost:{operation_id}", content={"lost": True},
                    outcome="unknown", provenance="broker"))
            fence = admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
                receipt_identity=f"fenced:{operation_id}:g{admitted_generation}",
                content={"fenced": True, "admitted_generation": int(admitted_generation),
                         "current_generation": live,
                         "late_receipt": (outcome.receipt.receipt_identity
                                          if outcome.receipt is not None else "")},
                outcome="unknown", provenance="broker-fence"))
            if _admitted(fence):
                _deliver(dsn, f"dispatch:{operation_id}")
                return _status_of(dsn, operation_id, sent_this_call=True)
            return _status_of(dsn, operation_id, decision="needs-reconciliation")
    if outcome.receipt is not None:
        admitted = admit_launcher_receipt(dsn, operation_id, outcome.receipt)
    elif outcome.lost:
        admitted = admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
            receipt_identity=f"lost:{operation_id}", content={"lost": True},
            outcome="unknown", provenance="broker"))
    else:
        admitted = None
    if admitted is None or _admitted(admitted):
        _deliver(dsn, f"dispatch:{operation_id}")
        return _status_of(dsn, operation_id, sent_this_call=True)
    return _status_of(dsn, operation_id, decision="needs-reconciliation")


def request_cancel(dsn: str, operation_id: str,
                   launchers: dict[str, Any] | None = None,
                   gateway: Any | None = None) -> CommandResult:
    result = store.request_cancellation(
        dsn, Command(request_id=f"broker-cancel-{operation_id}",
                     payload={"operation_id": operation_id}))
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return result
    stopped: list[str] = []
    for launcher in (launchers or {}).values():
        try:
            if launcher.stop(operation_id):
                stopped.append(launcher.launcher_id)
        except Exception:
            continue
    if stopped:
        result.data["workers_stopped"] = stopped
    if gateway is not None:
        try:
            if gateway.cancel(operation_id):
                result.data["gateway_cancelled"] = True
        except Exception:
            pass
    return result


def note_worker_stopped(dsn: str, operation_id: str) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT cancel_state FROM operations WHERE id = %s", (operation_id,))
        row = cur.fetchone()
        if row is None:
            raise SettlementError(f"unknown operation {operation_id}")
        if row["cancel_state"] == "worker_stopped":
            return (ResultCode.ALREADY_APPLIED, "worker already recorded stopped",
                    {"operation_id": operation_id}, [], [])
        if row["cancel_state"] not in ("requested",):
            raise SettlementError(
                f"operation {operation_id} cancel state is {row['cancel_state']}, not requested")
        cur.execute("UPDATE operations SET cancel_state = 'worker_stopped',"
                    " updated_at = now() WHERE id = %s", (operation_id,))
        return (ResultCode.APPLIED, "worker stopped",
                {"operation_id": operation_id},
                [("operation.worker_stopped", {"operation_id": operation_id})], [])

    return store.transact(dsn, Command(request_id=f"broker-stopped-{operation_id}",
                                       payload={"operation_id": operation_id}), _fn)


def confirm_cancel(dsn: str, operation_id: str) -> CommandResult:
    return store.confirm_cancellation(
        dsn, Command(request_id=f"broker-confirm-{operation_id}",
                     payload={"operation_id": operation_id}))


class ReconcileDecision(BaseModel):
    operation_id: str
    decision: str
    detail: str = ""
    next: str = ""

    model_config = {"extra": "forbid"}


class HeartbeatReport(BaseModel):
    dispatched: list[str] = Field(default_factory=list)
    delivered: list[str] = Field(default_factory=list)
    repaired: list[str] = Field(default_factory=list)
    deferred_model: list[str] = Field(default_factory=list)
    next_decision: str = "idle"

    model_config = {"extra": "forbid"}


def _launcher_index(launchers: dict[str, Any]) -> dict[str, Any]:
    index = dict(launchers)
    for launcher in launchers.values():
        index.setdefault(getattr(launcher, "launcher_id", ""), launcher)
    return index


def reconcile(dsn: str, operation_id: str, launchers: dict[str, Any],
              supervision_left: int = 3) -> ReconcileDecision:
    row = read_operation(dsn, operation_id)
    if row is None:
        return ReconcileDecision(operation_id=operation_id, decision="not-found", next="ignore")
    if row["dispatch_state"] in ("observed", "reconciled", "cancelled"):
        return ReconcileDecision(operation_id=operation_id, decision="already-terminal",
                                 detail=row["dispatch_state"], next="none")
    if supervision_left <= 0:
        return ReconcileDecision(operation_id=operation_id, decision="unresolved-liability",
                                 detail="supervision budget exhausted", next="retry-later")
    index = _launcher_index(launchers)
    launcher = index.get(row["launcher_id"])
    if launcher is not None:
        try:
            found = launcher.read_result(operation_id)
        except Exception:
            found = None
        if found is not None:
            admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
                receipt_identity=f"reconciled:{operation_id}",
                content={"recovered": found}, outcome=str(found.get("outcome", "unknown")),
                provenance=f"{launcher.launcher_id}-recovery"))
            return ReconcileDecision(operation_id=operation_id, decision="receipt-admitted",
                                     detail="launcher result recovered", next="none")
        if _is_live(launcher, operation_id):
            return ReconcileDecision(operation_id=operation_id, decision="still-running",
                                     next="retry-later")
    if row["dispatch_state"] == "prepared":
        return ReconcileDecision(operation_id=operation_id, decision="awaiting-dispatch",
                                 next="dispatch")
    if row["dispatch_state"] == "unresolved":
        return ReconcileDecision(operation_id=operation_id, decision="unresolved-liability",
                                 detail="already parked; exposure retained",
                                 next="retry-later")
    store.reconcile_operation(dsn, Command(request_id=f"broker-recon-{operation_id}",
                                           payload={"operation_id": operation_id,
                                                    "resolution": "unresolved"}))
    if launcher is None and row["dispatch_state"] == "dispatching":
        detail = (f"no launcher registered for {row['launcher_id']!r}"
                  f" (registered: {sorted(index)}); exposure retained")
    else:
        detail = "no launcher outcome available; exposure retained"
    return ReconcileDecision(operation_id=operation_id, decision="unresolved-liability",
                             detail=detail, next="retry-later")


def _is_live(launcher: Any, operation_id: str) -> bool:
    check = getattr(launcher, "is_live", None)
    if callable(check):
        try:
            return bool(check(operation_id))
        except Exception:
            return False
    return operation_id in (launcher.live_ids() or [])


def scan_prepared(dsn: str, limit: int = 50) -> list[dict[str, Any]]:
    from psycopg.rows import dict_row

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, payload FROM operations WHERE dispatch_state = 'prepared'"
                        " ORDER BY id LIMIT %s", (limit,))
            rows = [{"operation_id": r["id"],
                     "effect": (dict(r["payload"]) or {}).get("effect")} for r in cur.fetchall()]
            conn.commit()
            return rows


def dispatch_pending(dsn: str, launchers: dict[str, Any], gateway: Any | None = None,
                     ownership_generation: int | None = None,
                     grant_version: int | None = None, limit: int = 50) -> HeartbeatReport:
    return sweep(dsn, launchers, gateway, ownership_generation, grant_version,
                 limit, repair=False, wake=False)


def sweep(dsn: str, launchers: dict[str, Any], gateway: Any | None = None,
            ownership_generation: int | None = None, grant_version: int | None = None,
            limit: int = 50, repair: bool = False, wake: bool = True) -> HeartbeatReport:
    """One driver over prepared work, the outbox, unfinished ops and continuations.

    Every operation is decided at most once per sweep: a claim set dedupes the
    prepared scan, the outbox pass and the repair pass, and an operation joins
    ``repaired`` only when this sweep transitioned its durable state. All
    legacy drivers delegate here, so overlapping scans can never double-claim.
    """
    for attempt in store.attempts_with_continuations(dsn):
        if attempt["id"] not in ATTEMPT_WORKFLOW_RESOURCES:
            restore_workflow_resources(dsn, attempt["id"], launchers, gateway)
    report = HeartbeatReport()
    claimed: set[str] = set()
    for item in scan_prepared(dsn, limit):
        if item["effect"] == MODEL_INFERENCE:
            if item["operation_id"] not in report.deferred_model:
                report.deferred_model.append(item["operation_id"])
            continue
        if item["effect"] == ARTIFACT_IO:
            continue
        status = dispatch_operation(dsn, item["operation_id"], launchers=launchers,
                                    gateway=gateway,
                                    ownership_generation=ownership_generation,
                                    grant_version=grant_version)
        if status.sent_this_call:
            claimed.add(item["operation_id"])
            if item["operation_id"] not in report.dispatched:
                report.dispatched.append(item["operation_id"])
    for intent in store.scan_outbox(dsn, limit):
        identity = intent["workflow_identity"]
        if not identity.startswith("dispatch:"):
            continue
        operation_id = identity.split(":", 1)[1]
        checked = store.claim_outbox(dsn, Command(request_id=f"broker-claim-{identity}",
                                                  payload={"workflow_identity": identity}))
        if checked.data.get("delivered"):
            continue
        row = read_operation(dsn, operation_id)
        if row is None:
            _deliver(dsn, identity)
            if operation_id not in report.delivered:
                report.delivered.append(operation_id)
            continue
        if row["payload"].get("effect") == MODEL_INFERENCE and row["dispatch_state"] in (
                "prepared", "dispatching", "sent"):
            if operation_id not in report.deferred_model:
                report.deferred_model.append(operation_id)
            continue
        if row["dispatch_state"] == "prepared":
            status = dispatch_operation(dsn, operation_id, launchers=launchers,
                                        gateway=gateway,
                                        ownership_generation=ownership_generation,
                                        grant_version=grant_version)
            if status.sent_this_call:
                claimed.add(operation_id)
                if operation_id not in report.dispatched:
                    report.dispatched.append(operation_id)
                if operation_id not in report.delivered:
                    report.delivered.append(operation_id)
            continue
        if row["dispatch_state"] in ("observed", "reconciled", "cancelled"):
            _deliver(dsn, identity)
            if operation_id not in report.delivered:
                report.delivered.append(operation_id)
            continue
        if operation_id in claimed:
            continue
        before = row["dispatch_state"]
        before_receipts = len(store.operation_receipts(dsn, operation_id))
        decision = reconcile(dsn, operation_id, launchers)
        claimed.add(operation_id)
        if decision.decision == "still-running":
            continue
        _deliver(dsn, identity)
        if operation_id not in report.delivered:
            report.delivered.append(operation_id)
        if _transitioned(dsn, operation_id, before, before_receipts):
            report.repaired.append(operation_id)
    if repair:
        state = store.restart_reconciliation(dsn)
        for op in state["unfinished_operations"]:
            if op["id"] in claimed:
                continue
            claimed.add(op["id"])
            row = read_operation(dsn, op["id"])
            if row is not None and row["payload"].get("effect") == MODEL_INFERENCE:
                if op["id"] not in report.deferred_model:
                    report.deferred_model.append(op["id"])
                continue
            before = (row or {}).get("dispatch_state", "")
            before_receipts = len(store.operation_receipts(dsn, op["id"]))
            decision = reconcile(dsn, op["id"], launchers)
            if decision.decision != "still-running" \
                    and _transitioned(dsn, op["id"], before, before_receipts):
                report.repaired.append(op["id"])
        if report.repaired and report.next_decision == "idle":
            report.next_decision = "repair-done"
    if report.dispatched or report.repaired:
        report.next_decision = "work-done"
    elif report.deferred_model:
        report.next_decision = "model-dispatch-deferred"
    if wake:
        woken = _wake_waiting_workflows(dsn, launchers, gateway)
        for aid in woken["woken"]:
            if f"wake:{aid}" not in report.repaired:
                report.repaired.append(f"wake:{aid}")
        if woken["woken"] and report.next_decision == "idle":
            report.next_decision = "work-done"
    return report


def _transitioned(dsn: str, operation_id: str, before: str,
                    before_receipts: int) -> bool:
    row = read_operation(dsn, operation_id)
    if row is None:
        return before != "missing"
    if row["dispatch_state"] != before:
        return True
    return len(store.operation_receipts(dsn, operation_id)) > before_receipts


def redispatch_after_reset(dsn: str, operation_id: str, launchers: dict[str, Any],
                           expected_generation: int, gateway: Any | None = None,
                           ownership_generation: int | None = None,
                           grant_version: int | None = None) -> DispatchStatus:
    reset = store.reset_dispatch(
        dsn, Command(request_id=f"broker-redispatch-{operation_id}-g{expected_generation}",
                     payload={"operation_id": operation_id,
                              "expected_generation": expected_generation}))
    if reset.code != ResultCode.APPLIED:
        return _status_of(dsn, operation_id, decision=f"reset-refused-{reset.code.value}")
    return dispatch_operation(dsn, operation_id, launchers=launchers, gateway=gateway,
                              ownership_generation=ownership_generation,
                              grant_version=grant_version)


def _stored_composition(resources_key: str) -> dict[str, Any] | None:
    import json

    raw = (ATTEMPT_WORKFLOW_RESOURCES.get(resources_key) or {}).get("composition")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def wake_waiting_workflows(dsn: str, launchers: dict[str, Any] | None = None,
                           gateway: Any | None = None,
                           limit: int = 200) -> dict[str, Any]:
    return _wake_waiting_workflows(dsn, launchers, gateway, limit)


def _wake_waiting_workflows(dsn: str, launchers: dict[str, Any] | None = None,
                            gateway: Any | None = None,
                            limit: int = 200) -> dict[str, Any]:
    from . import run as runmod

    woken: list[str] = []
    resumed: list[str] = []
    deferred: list[str] = []
    for attempt in store.attempts_with_continuations(dsn)[:limit]:
        aid = attempt["id"]
        try:
            restore_workflow_resources(dsn, aid, launchers or {}, gateway)
        except Exception:
            continue
        snap = wf_snapshot(dsn, aid)
        if snap["lifecycle"] in _TERMINAL_LIFECYCLE or not snap["continuation"]:
            continue
        composition = _stored_composition(aid)
        if composition is None:
            continue
        try:
            comp = runmod.Composition.model_validate(composition)
            cont = runmod.Continuation.model_validate(snap["continuation"])
        except Exception:
            continue
        advanced = False
        for entry in list(cont.unresolved_ops):
            node_id, _, operation_id = entry.partition(":")
            if not operation_id or cont.completed.get(node_id) == f"op:{operation_id}":
                continue
            outcome = runmod.operation_outcome(dsn, operation_id)
            if outcome["outcome"] not in ("success", "failure"):
                continue
            consumed = wf_consume(dsn, aid, composition, cont.model_dump(mode="json"),
                                 node_id, operation_id, f"wake:{aid}")
            if consumed.get("applied"):
                cont = runmod.Continuation.model_validate(consumed["continuation"])
                advanced = True
        if advanced:
            woken.append(aid)
        if not advanced and cont.next.get("decision") not in ("invoke", "fork", "done"):
            continue
        try:
            from dbos import SetWorkflowID

            with SetWorkflowID(f"attempt:{aid}:gen{attempt['ownership_generation']}"):
                DBOS.start_workflow(attempt_workflow, dsn, aid,
                                    attempt["ownership_generation"], composition, 10)
            resumed.append(aid)
        except Exception:
            deferred.append(aid)
    return {"woken": woken, "resumed": resumed, "resume_deferred": deferred}


def heartbeat(dsn: str, launchers: dict[str, Any], gateway: Any | None = None,
              ownership_generation: int | None = None, repair_due: bool = False,
              limit: int = 50, grant_version: int | None = None) -> HeartbeatReport:
    return sweep(dsn, launchers, gateway, ownership_generation, grant_version,
                 limit, repair=repair_due, wake=True)


def recover(dsn: str, launchers: dict[str, Any]) -> HeartbeatReport:
    report = HeartbeatReport()
    claimed: set[str] = set()
    state = store.restart_reconciliation(dsn)
    for op in state["unfinished_operations"]:
        if op["id"] in claimed:
            continue
        claimed.add(op["id"])
        decision = reconcile(dsn, op["id"], launchers)
        report.repaired.append(f"{op['id']}:{decision.decision}")
    live = state["live_attempts"]
    report.next_decision = f"recovered-{len(report.repaired)}-ops-{len(live)}-attempts"
    return report


ATTEMPT_WORKFLOW_RESOURCES: dict[str, dict[str, Any]] = {}

_TERMINAL_LIFECYCLE = ("completed", "failed", "cancelled")


def init_dbos(system_dsn: str, app_name: str = "settlement-s1") -> None:
    from dbos import DBOS, DBOSConfig

    config: DBOSConfig = {"name": app_name, "system_database_url": system_dsn,
                          "database_url": system_dsn}
    DBOS(config=config)
    DBOS.launch()


def shutdown_dbos() -> None:
    from dbos import DBOS

    DBOS.destroy()


def wf_snapshot(dsn: str, attempt_id: str) -> dict[str, Any]:
    import json
    from psycopg.rows import dict_row

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT lifecycle, continuation_ref FROM attempts WHERE id = %s",
                        (attempt_id,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        return {"lifecycle": "unknown", "continuation": None}
    continuation = None
    if row["continuation_ref"]:
        try:
            continuation = json.loads(row["continuation_ref"]).get("continuation")
        except ValueError:
            continuation = None
    return {"lifecycle": row["lifecycle"], "continuation": continuation}


def restore_workflow_resources(dsn: str, attempt_id: str,
                               launchers: dict[str, Any],
                               gateway: Any | None = None,
                               admitted_execution_versions: tuple[str, ...] = ()
                               ) -> dict[str, Any]:
    from psycopg.rows import dict_row

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, allocation_id, composition, model, env, lifecycle"
                        " FROM attempts WHERE id = %s", (attempt_id,))
            attempt = cur.fetchone()
            if attempt is None:
                raise SettlementError(f"unknown attempt {attempt_id}")
            cur.execute("SELECT execution_version FROM operations WHERE attempt_id = %s"
                        " AND execution_version <> '' ORDER BY id", (attempt_id,))
            versions = sorted({r["execution_version"] for r in cur.fetchall()})
            conn.commit()
    admitted = set(admitted_execution_versions)
    unknown = [v for v in versions if admitted and v not in admitted]
    if unknown:
        raise SettlementError(
            f"attempt {attempt_id} needs unadmitted execution versions {unknown}")
    ATTEMPT_WORKFLOW_RESOURCES[attempt_id] = {
        "launchers": launchers, "gateway": gateway,
        "allocation_id": attempt["allocation_id"], "composition": attempt["composition"],
        "model": attempt["model"], "env": attempt["env"],
        "lifecycle": attempt["lifecycle"], "execution_versions": versions}
    return {"attempt_id": attempt_id, "lifecycle": attempt["lifecycle"],
            "execution_versions": versions}


def wf_ensure_dispatch(dsn: str, op_args: dict[str, Any], retries: int,
                       ownership_generation: int | None, node_id: str,
                       resources_key: str) -> dict[str, Any]:
    try:
        res = ATTEMPT_WORKFLOW_RESOURCES[resources_key]
    except KeyError:
        raise SettlementError(
            f"workflow resources for {resources_key!r} need restore_workflow_resources first"
        ) from None
    from . import run as runmod

    prior = runmod.operation_outcome(dsn, op_args["operation_id"])
    if prior["found"] and prior["outcome"] == "failure":
        return {"node_id": node_id, "operation_id": op_args["operation_id"],
                "dispatch_state": prior["dispatch_state"],
                "next_decision": "already-failed", "failed_try": True}
    ensured = ensure_operation(dsn, operation_id=op_args["operation_id"], effect=op_args["effect"],
                               payload=op_args["payload"], allocation_id=op_args["allocation_id"],
                               attempt_id=op_args.get("attempt_id"),
                               execution_version=op_args.get("execution_version", ""),
                               retries=retries)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return {"node_id": node_id, "operation_id": op_args["operation_id"],
                "dispatch_state": prior["dispatch_state"] if prior["found"] else "unknown",
                "next_decision": f"ensure-refused-{ensured.code.value}",
                "ensure_refused": ensured.detail, "failed_try": False}
    status = dispatch_operation(dsn, op_args["operation_id"],
                                launchers=res.get("launchers", {}),
                                gateway=res.get("gateway"),
                                ownership_generation=ownership_generation)
    return {"node_id": node_id, "operation_id": op_args["operation_id"],
            "dispatch_state": status.dispatch_state,
            "next_decision": status.next_decision}


def wf_consume(dsn: str, attempt_id: str, composition: dict[str, Any],
               cont_dict: dict[str, Any], node_id: str, operation_id: str,
               identity_base: str) -> dict[str, Any]:
    from . import run as runmod

    comp = runmod.Composition.model_validate(composition)
    cont = runmod.Continuation.model_validate(cont_dict)
    outcome = runmod.operation_outcome(dsn, operation_id)
    if cont.completed.get(node_id) == f"op:{operation_id}":
        return {"continuation": cont.model_dump(mode="json"), "applied": False,
                "outcome": outcome}
    cont = runmod.consume_operation_outcome(comp, cont, node_id, operation_id,
                                            outcome["outcome"])
    receipts = outcome.get("receipts") or [{}]
    try:
        recorded = runmod.record_continuation(
            dsn, attempt_id, cont,
            f"{identity_base}:{operation_id}:{receipts[0].get('receipt_identity', outcome['dispatch_state'])}",
            None)
    except ConflictPayload:
        return {"continuation": cont.model_dump(mode="json"), "applied": False,
                "outcome": outcome, "record": "conflict-replay"}
    return {"continuation": cont.model_dump(mode="json"), "applied": True,
            "outcome": outcome, "record": recorded.code.value}


def wf_record(dsn: str, attempt_id: str, composition: dict[str, Any],
              cont_dict: dict[str, Any], summary: dict[str, Any],
              identity_base: str) -> dict[str, Any]:
    from . import run as runmod

    comp = runmod.Composition.model_validate(composition)
    cont = runmod.Continuation.model_validate(cont_dict)
    node_id = summary["node_id"]
    iteration = summary.get("iteration")
    if summary.get("failed_try"):
        cont = runmod.record_failed_try(comp, cont, node_id,
                                        summary["operation_id"], iteration)
        runmod.record_continuation(dsn, attempt_id, cont, identity_base, None)
        return cont.model_dump(mode="json")
    outcome = runmod.operation_outcome(dsn, summary["operation_id"])
    if outcome["found"]:
        if outcome["outcome"] == "success":
            cont = runmod.advance(comp, cont,
                                  {"type": "node_completed", "node_id": node_id,
                                   "result_ref": f"op:{summary['operation_id']}"})
        elif outcome["outcome"] == "failure":
            cont = runmod.consume_operation_outcome(comp, cont, node_id,
                                                    summary["operation_id"], "failure")
        else:
            cont = runmod.register_ops(comp, cont, {node_id: summary["operation_id"]})
    elif summary["dispatch_state"] == "observed":
        cont = runmod.advance(comp, cont,
                              {"type": "node_completed", "node_id": node_id,
                               "result_ref": f"op:{summary['operation_id']}"})
    else:
        cont = runmod.register_ops(comp, cont, {node_id: summary["operation_id"]})
    runmod.record_continuation(dsn, attempt_id, cont, identity_base, None)
    return cont.model_dump(mode="json")


def wf_finish(dsn: str, attempt_id: str, ownership_generation: int | None,
              outcome: str, identity_base: str) -> dict[str, Any]:
    result = store.complete_attempt(
        dsn, Command(request_id=identity_base,
                     payload={"attempt_id": attempt_id,
                              "ownership_generation": ownership_generation,
                              "outcome": outcome}))
    return {"code": result.code.value, "detail": result.detail}


def attempt_workflow(dsn: str, attempt_id: str, ownership_generation: int,
                     composition: dict[str, Any], max_rounds: int = 10) -> dict[str, Any]:
    from . import run as runmod

    comp = runmod.Composition.model_validate(composition)
    runmod.validate_composition(comp)
    wfid = f"attempt:{attempt_id}:gen{ownership_generation}"
    for round_no in range(max(int(max_rounds), 1)):
        snap = DBOS.run_step(None, wf_snapshot, dsn, attempt_id)
        if snap["lifecycle"] in _TERMINAL_LIFECYCLE:
            return {"attempt_id": attempt_id, "outcome": snap["lifecycle"],
                    "rounds": round_no}
        cont = runmod.Continuation.model_validate(snap["continuation"]) \
            if snap["continuation"] else runmod.fresh_continuation(comp, attempt_id)
        if cont.next.get("decision") == "done":
            DBOS.run_step(None, wf_finish, dsn, attempt_id, ownership_generation,
                          "completed", f"{wfid}:finish")
            return {"attempt_id": attempt_id, "outcome": "completed",
                    "rounds": round_no + 1}
        for entry in list(cont.unresolved_ops):
            node_id, _, operation_id = entry.partition(":")
            if not operation_id or cont.completed.get(node_id) == f"op:{operation_id}":
                continue
            consumed = DBOS.run_step(None, wf_consume, dsn, attempt_id, composition,
                                    cont.model_dump(mode="json"), node_id,
                                    operation_id, wfid)
            if consumed.get("applied"):
                cont = runmod.Continuation.model_validate(consumed["continuation"])
        if cont.next.get("decision") == "done":
            DBOS.run_step(None, wf_finish, dsn, attempt_id, ownership_generation,
                          "completed", f"{wfid}:finish")
            return {"attempt_id": attempt_id, "outcome": "completed",
                    "rounds": round_no + 1}
        pending = runmod.pending_invokes(comp, cont)
        if not pending:
            return {"attempt_id": attempt_id, "outcome": "waiting",
                    "rounds": round_no, "next": cont.next}
        node = pending[0]
        iteration = runmod.iteration_of(comp, cont, node.node_id)
        args = runmod.invoke_to_broker_args(
            node, attempt_id=attempt_id, allocation_id=comp.allocation_id,
            iteration=iteration)
        args["operation_id"] = runmod.retry_operation_id(
            args["operation_id"], cont, node.node_id, iteration)
        summary = DBOS.run_step(None, wf_ensure_dispatch, dsn, args, node.retry_max,
                                ownership_generation, node.node_id, attempt_id)
        summary = dict(summary)
        summary["iteration"] = iteration
        DBOS.run_step(None, wf_record, dsn, attempt_id, composition,
                      cont.model_dump(mode="json"), summary, f"{wfid}:r{round_no}")
    return {"attempt_id": attempt_id, "outcome": "rounds-exhausted",
            "rounds": int(max_rounds)}


attempt_workflow = DBOS.workflow()(attempt_workflow)
