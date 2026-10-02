"""S1 operation broker over the durable store: prepare, dispatch, observe, reconcile.

Recovery model: ``dispatching`` means may-have-been-sent and is committed
before any send. No database transaction stays open during an external call.
A prepared operation is sent at most once per operation identity; a repeat
broker call after a crash returns recorded state and never re-sends unless
the launcher contract proves idempotency or reconciliation concluded.
"""

from __future__ import annotations

from typing import Any, Protocol

from dbos import DBOS
from pydantic import BaseModel, Field

from . import db, store
from .common import Command, CommandResult, ConflictPayload, ResultCode

MODEL_INFERENCE = "model-inference"
SANDBOX_EXEC = "sandbox-exec"
ARTIFACT_IO = "artifact-io"
OBSERVATION_ADAPTER = "observation-adapter"
DOMAIN_COMMAND = "domain-command"

EFFECTS = (MODEL_INFERENCE, SANDBOX_EXEC, ARTIFACT_IO, OBSERVATION_ADAPTER, DOMAIN_COMMAND)

ADMITTED_OBSERVATION_ADAPTERS = ("clock",)
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
    _no_extra(p, {"model", "messages", "max_output_tokens", "deadline_ms"}, "model-inference")
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
    return {"model": p["model"], "messages": list(messages),
            "max_output_tokens": limit, "deadline_ms": deadline}


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
    grace_s = 5
    return (int(p["timeout_ms"]) // 1000 + grace_s + 1) * (retries + 1), "hard-ceiling"


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
    from psycopg.rows import dict_row  # noqa: PLC0415

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
        dsn, Command(request_id=f"broker-adv-{operation_id}-{launcher_id}", payload=payload))


def _refusal(dsn: str, operation_id: str, result: CommandResult) -> DispatchStatus:
    mapping = {ResultCode.STALE_REVISION: "stale-ownership",
               ResultCode.UNAUTHORIZED: "stale-grant"}
    return _status_of(dsn, operation_id,
                      decision=mapping.get(result.code, f"refused-{result.code.value}"))


def admit_launcher_receipt(dsn: str, operation_id: str, receipt: ReceiptProposal) -> CommandResult:
    from .common import payload_digest  # noqa: PLC0415

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
        return _status_of(dsn, operation_id)
    body = row["payload"]
    effect = body.get("effect")
    payload = body.get("payload", {})
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
    if advanced.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return _refusal(dsn, op.operation_id, advanced)
    if launcher.prior_send(op.operation_id):
        _deliver(dsn, f"dispatch:{op.operation_id}")
        return _status_of(dsn, op.operation_id, decision="needs-reconciliation")
    try:
        outcome = launcher.dispatch(op)
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
    return _finish_send(dsn, op.operation_id, outcome)


def _send_model(dsn: str, row: dict, op: BrokerOp, launchers: dict,
                gateway: Any, ownership_generation: int | None,
                grant_version: int | None, crash: bool) -> DispatchStatus:
    if gateway is None:
        return _status_of(dsn, op.operation_id, decision="awaiting-gateway")
    advanced = _advance(dsn, op.operation_id, "gateway", op.payload.get("model", ""),
                        ownership_generation, grant_version)
    if advanced.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return _refusal(dsn, op.operation_id, advanced)
    from .gateway import GatewayError, ModelRequest  # noqa: PLC0415

    request = ModelRequest(model=op.payload["model"],
                           messages=tuple(op.payload["messages"]),
                           max_output_tokens=op.payload["max_output_tokens"],
                           deadline_ms=op.payload["deadline_ms"],
                           operation_id=op.operation_id)
    response = gateway.infer(request)
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
                               "charge_units": usage.charge_units,
                               "provider_enforced_ceiling": usage.provider_enforced_ceiling}},
            outcome="success", provenance="gateway", actual_cost=usage.charge_units)))
    return outcome


def _run_inline(dsn: str, row: dict, op: BrokerOp, launchers: dict,
                gateway: Any, ownership_generation: int | None,
                grant_version: int | None, crash: bool) -> DispatchStatus:
    advanced = _advance(dsn, op.operation_id, "broker-inline", "",
                        ownership_generation, grant_version)
    if advanced.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return _refusal(dsn, op.operation_id, advanced)
    if op.effect == OBSERVATION_ADAPTER:
        content: dict[str, Any] = {"adapter": op.payload["adapter"]}
        if op.payload["adapter"] == "clock":
            from .common import utcnow  # noqa: PLC0415

            content["utcnow"] = utcnow().isoformat()
    else:
        content = {"command": op.payload["command"], "payload": op.payload["payload"],
                   "idempotency_key": op.payload["idempotency_key"]}
    return _finish_send(dsn, op.operation_id, LaunchOutcome(
        sent=True, receipt=ReceiptProposal(
            receipt_identity=f"inline:{op.operation_id}", content=content,
            outcome="success", provenance="broker-inline")))


def _finish_send(dsn: str, operation_id: str, outcome: LaunchOutcome) -> DispatchStatus:
    if outcome.receipt is not None:
        admit_launcher_receipt(dsn, operation_id, outcome.receipt)
    elif outcome.lost:
        admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
            receipt_identity=f"lost:{operation_id}", content={"lost": True},
            outcome="unknown", provenance="broker"))
    _deliver(dsn, f"dispatch:{operation_id}")
    return _status_of(dsn, operation_id, sent_this_call=True)


def request_cancel(dsn: str, operation_id: str,
                   launchers: dict[str, Any] | None = None) -> CommandResult:
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
    return result


def note_worker_stopped(dsn: str, operation_id: str) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT cancel_state FROM operations WHERE id = %s", (operation_id,))
        row = cur.fetchone()
        if row is None:
            raise _missing(operation_id)
        if row["cancel_state"] == "worker_stopped":
            return (ResultCode.ALREADY_APPLIED, "worker already recorded stopped",
                    {"operation_id": operation_id}, [], [])
        if row["cancel_state"] not in ("requested",):
            raise _cancel_order(operation_id, row["cancel_state"])
        cur.execute("UPDATE operations SET cancel_state = 'worker_stopped',"
                    " updated_at = now() WHERE id = %s", (operation_id,))
        return (ResultCode.APPLIED, "worker stopped",
                {"operation_id": operation_id},
                [("operation.worker_stopped", {"operation_id": operation_id})], [])

    return store.transact(dsn, Command(request_id=f"broker-stopped-{operation_id}",
                                       payload={"operation_id": operation_id}), _fn)


def _missing(operation_id: str):
    from .common import SettlementError  # noqa: PLC0415

    return SettlementError(f"unknown operation {operation_id}")


def _cancel_order(operation_id: str, state: str):
    from .common import SettlementError  # noqa: PLC0415

    return SettlementError(f"operation {operation_id} cancel state is {state}, not requested")


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
    store.reconcile_operation(dsn, Command(request_id=f"broker-recon-{operation_id}",
                                           payload={"operation_id": operation_id,
                                                    "resolution": "unresolved"}))
    return ReconcileDecision(operation_id=operation_id, decision="unresolved-liability",
                             detail="no launcher outcome available; exposure retained",
                             next="retry-later")


def _is_live(launcher: Any, operation_id: str) -> bool:
    check = getattr(launcher, "is_live", None)
    if callable(check):
        try:
            return bool(check(operation_id))
        except Exception:
            return False
    return operation_id in (launcher.live_ids() or [])


def scan_prepared(dsn: str, limit: int = 50) -> list[dict[str, Any]]:
    from psycopg.rows import dict_row  # noqa: PLC0415

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
    report = HeartbeatReport()
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
        if status.sent_this_call and item["operation_id"] not in report.dispatched:
            report.dispatched.append(item["operation_id"])
    for intent in store.scan_outbox(dsn, limit):
        identity = intent["workflow_identity"]
        if not identity.startswith("dispatch:"):
            continue
        operation_id = identity.split(":", 1)[1]
        claimed = store.claim_outbox(dsn, Command(request_id=f"broker-claim-{identity}",
                                                  payload={"workflow_identity": identity}))
        if claimed.data.get("delivered"):
            continue
        row = read_operation(dsn, operation_id)
        if row is None:
            _deliver(dsn, identity)
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
                report.dispatched.append(operation_id)
                report.delivered.append(operation_id)
            continue
        if row["dispatch_state"] in ("observed", "reconciled", "cancelled"):
            _deliver(dsn, identity)
            report.delivered.append(operation_id)
            continue
        decision = reconcile(dsn, operation_id, launchers)
        if decision.decision != "still-running":
            _deliver(dsn, identity)
            report.delivered.append(operation_id)
            report.repaired.append(operation_id)
    if report.dispatched or report.repaired:
        report.next_decision = "work-done"
    elif report.deferred_model:
        report.next_decision = "model-dispatch-deferred"
    return report


def heartbeat(dsn: str, launchers: dict[str, Any], gateway: Any | None = None,
              ownership_generation: int | None = None, repair_due: bool = False,
              limit: int = 50) -> HeartbeatReport:
    report = dispatch_pending(dsn, launchers, gateway, ownership_generation, None, limit)
    if repair_due:
        state = store.restart_reconciliation(dsn)
        for op in state["unfinished_operations"]:
            if op["id"] in report.repaired or op["id"] in report.dispatched:
                continue
            row = read_operation(dsn, op["id"])
            if row is not None and row["payload"].get("effect") == MODEL_INFERENCE:
                if op["id"] not in report.deferred_model:
                    report.deferred_model.append(op["id"])
                continue
            decision = reconcile(dsn, op["id"], launchers)
            if decision.decision != "still-running":
                report.repaired.append(op["id"])
        if report.repaired and report.next_decision == "idle":
            report.next_decision = "repair-done"
    return report


def recover(dsn: str, launchers: dict[str, Any]) -> HeartbeatReport:
    report = HeartbeatReport()
    state = store.restart_reconciliation(dsn)
    for op in state["unfinished_operations"]:
        decision = reconcile(dsn, op["id"], launchers)
        report.repaired.append(f"{op['id']}:{decision.decision}")
    live = state["live_attempts"]
    report.next_decision = f"recovered-{len(report.repaired)}-ops-{len(live)}-attempts"
    return report


ATTEMPT_WORKFLOW_RESOURCES: dict[str, dict[str, Any]] = {}

_TERMINAL_LIFECYCLE = ("completed", "failed", "cancelled")


def init_dbos(system_dsn: str, app_name: str = "settlement-s1") -> None:
    from dbos import DBOS, DBOSConfig  # noqa: PLC0415

    config: DBOSConfig = {"name": app_name, "system_database_url": system_dsn,
                          "database_url": system_dsn}
    DBOS(config=config)
    DBOS.launch()


def shutdown_dbos() -> None:
    from dbos import DBOS  # noqa: PLC0415

    DBOS.destroy()


def wf_snapshot(dsn: str, attempt_id: str) -> dict[str, Any]:
    import json  # noqa: PLC0415
    from psycopg.rows import dict_row  # noqa: PLC0415

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


def wf_ensure_dispatch(dsn: str, op_args: dict[str, Any], retries: int,
                       ownership_generation: int | None, node_id: str,
                       resources_key: str) -> dict[str, Any]:
    res = ATTEMPT_WORKFLOW_RESOURCES[resources_key]
    ensure_operation(dsn, operation_id=op_args["operation_id"], effect=op_args["effect"],
                     payload=op_args["payload"], allocation_id=op_args["allocation_id"],
                     attempt_id=op_args.get("attempt_id"),
                     execution_version=op_args.get("execution_version", ""),
                     retries=retries)
    status = dispatch_operation(dsn, op_args["operation_id"],
                                launchers=res.get("launchers", {}),
                                gateway=res.get("gateway"),
                                ownership_generation=ownership_generation)
    return {"node_id": node_id, "operation_id": op_args["operation_id"],
            "dispatch_state": status.dispatch_state,
            "next_decision": status.next_decision}


def wf_record(dsn: str, attempt_id: str, composition: dict[str, Any],
              cont_dict: dict[str, Any], summary: dict[str, Any],
              identity_base: str) -> dict[str, Any]:
    from . import run as runmod  # noqa: PLC0415

    comp = runmod.Composition.model_validate(composition)
    cont = runmod.Continuation.model_validate(cont_dict)
    node_id = summary["node_id"]
    if summary["dispatch_state"] == "observed":
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
    from . import run as runmod  # noqa: PLC0415

    comp = runmod.Composition.model_validate(composition)
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
        pending = runmod.pending_invokes(comp, cont)
        if not pending:
            return {"attempt_id": attempt_id, "outcome": "waiting",
                    "rounds": round_no, "next": cont.next}
        node = pending[0]
        args = runmod.invoke_to_broker_args(
            node, attempt_id=attempt_id, allocation_id=comp.allocation_id,
            iteration=runmod.iteration_of(comp, cont, node.node_id))
        summary = DBOS.run_step(None, wf_ensure_dispatch, dsn, args, node.retry_max,
                                ownership_generation, node.node_id, attempt_id)
        DBOS.run_step(None, wf_record, dsn, attempt_id, composition,
                      cont.model_dump(mode="json"), summary, f"{wfid}:r{round_no}")
    return {"attempt_id": attempt_id, "outcome": "rounds-exhausted",
            "rounds": int(max_rounds)}


attempt_workflow = DBOS.workflow()(attempt_workflow)
