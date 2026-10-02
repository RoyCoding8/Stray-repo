"""Shared learner/action/result loop: one driver, one resource envelope.

Both investigation domains run through the same boundary: materialize the
lane B1 packet read-only, propose an action, admit it against one envelope,
execute it through broker admission, incorporate post-effect reads, and
continue or stop with pending identities. Every transition journals into the
domain event log under a stable action identity, so a kill/resume cycle
reuses settled results instead of re-sending.

Envelope rules: every effect admits against post-effect reads of a single
study root. Sub-budgets sequence from remaining minus actual diagnostic
spend. A zero-budget probe is refused without touching study lineage.
Learner headroom is sized from measured exposure; an underfunded study
falls back to no-candidate instead of silently underfunding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import authority as _authority
from . import store
from .common import Command, CommandResult, ResultCode, SettlementError, payload_digest

PACKET_VERSION = "ad01-packet-v1"
MEASURED_LEARNER_EXPOSURE = 2600
PROBE_ALLOWANCE_SUFFIX = "-probes"
TRANSITION_EVENT = "loop.transition"

DIAGNOSTIC = "diagnose"
CONSTRUCTION = "construct"
REPAIR = "repair"
USE = "use"
PROBE = "probe"
STOP = "stop"

_EFFECT_FOR = {
    DIAGNOSTIC: "model-inference",
    CONSTRUCTION: "sandbox-exec",
    REPAIR: "sandbox-exec",
    USE: "sandbox-exec",
    PROBE: "observation-adapter",
    "note": "domain-command",
}


@dataclass
class Allowance:
    allowance_id: str
    kind: str
    amount: int
    spent_measured: int = 0
    spent_unknown: int = 0

    def spent(self) -> int:
        return int(self.spent_measured) + int(self.spent_unknown)


@dataclass
class Grant:
    allowance: Allowance
    operation_id: str
    exposure: int
    budget_kind: str
    already: bool = False


@dataclass
class Refusal:
    reason: str
    detail: str = ""


@dataclass
class ResourceEnvelope:
    study_root: str
    allocation_id: str
    authorized: int
    ceilings: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def bind(cls, dsn: str, study_root: str, authorized: int,
             ceilings: dict[str, Any] | None = None) -> "ResourceEnvelope":
        handle = _authority.authorize_study(
            dsn, study_root, authorized=authorized,
            ceilings=dict(ceilings or {}))
        return cls(study_root=handle.study_root,
                   allocation_id=handle.allocation_id,
                   authorized=handle.authorized,
                   ceilings=dict(handle.ceilings))

    def remaining(self, dsn: str, allocation_id: str | None = None) -> int:
        return store.allocation_free(dsn, allocation_id or self.allocation_id)

    def probe_allowance(self, dsn: str, amount: int) -> str:
        child = self.study_root + PROBE_ALLOWANCE_SUFFIX
        store.subdivide_allocation(
            dsn, Command(request_id=f"loop-probes-{self.study_root}",
                         payload={"parent_id": self.study_root, "child_id": child,
                                  "authorized": amount, "domain": "study",
                                  "owner_scope": "probes"}))
        return child

    @staticmethod
    def sequence_construction_allowance(remaining: int, diagnostic_spent: int,
                                        reserve: int = 1) -> int:
        return max(0, int(remaining) - int(reserve) - int(diagnostic_spent))

    def require_learner_headroom(self, dsn: str, calls: int,
                                 unit: int = MEASURED_LEARNER_EXPOSURE,
                                 allocation_id: str | None = None) -> Grant | Refusal:
        if not isinstance(calls, int) or calls <= 0:
            return Refusal(reason="invalid-learner-demand",
                           detail="headroom needs a finite positive call count")
        need = int(calls) * int(unit)
        free = self.remaining(dsn, allocation_id)
        if free < need:
            return Refusal(reason="underfunded-study",
                           detail=f"free {free} cannot cover {calls} admitted"
                                  f" learner calls at measured {unit}; no-candidate")
        return Grant(allowance=Allowance(allowance_id=f"{self.study_root}:learner",
                                         kind=DIAGNOSTIC, amount=need),
                     operation_id="", exposure=need, budget_kind="measured-exposure")

    def admit_probe(self, dsn: str, *, operation_id: str, amount: int,
                    probe_allocation_id: str) -> Grant | Refusal:
        if not isinstance(amount, int) or amount <= 0:
            return Refusal(reason="zero-budget-probe",
                           detail="a probe with no budget is refused;"
                                  " study lineage is untouched")
        free = self.remaining(dsn, probe_allocation_id)
        if free < amount:
            return Refusal(reason="insufficient-probe-allowance",
                           detail=f"probe allowance free {free} cannot cover {amount}")
        return Grant(allowance=Allowance(allowance_id=f"{probe_allocation_id}:{operation_id}",
                                         kind=PROBE, amount=amount),
                     operation_id=operation_id, exposure=amount,
                     budget_kind="recorded-exposure")

    def measured_costs(self, dsn: str, operation_id: str) -> dict[str, Any]:
        return read_measured_costs(dsn, operation_id)


def _operation_row(dsn: str, operation_id: str) -> dict[str, Any] | None:
    from . import broker as _broker

    return _broker.read_operation(dsn, operation_id)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _billing_from_usage(usage: dict[str, Any]) -> tuple[bool | None, int | None]:
    billed = usage.get("billed")
    if billed is False:
        return False, 0
    if billed is not True:
        return None, None
    charge = _nonnegative_int(usage.get("charge_units"))
    return (True, charge) if charge is not None else (None, None)


def _token_from_usage(usage: dict[str, Any], name: str) -> int | None:
    return _nonnegative_int(usage.get(name))


def read_measured_costs(dsn: str, operation_id: str) -> dict[str, Any]:
    row = _operation_row(dsn, operation_id)
    receipts = store.operation_receipts(dsn, operation_id)
    effect = str(dict((row or {}).get("payload") or {}).get("effect", ""))
    if row is not None and effect != "model-inference":
        return {"operation_id": operation_id,
                "dispatch_state": row.get("dispatch_state", "missing"),
                "measured": 0, "provider_charge_units": None,
                "billed": False, "tokens": {"input": 0, "output": 0},
                "unknown": [],
                "receipts": [str(r.get("receipt_identity")) for r in receipts]}
    terminal = receipts[-1] if receipts else None
    content = dict((terminal or {}).get("content") or {})
    raw_usage = content.get("usage")
    usage = dict(raw_usage) if isinstance(raw_usage, dict) else {}
    if terminal is None:
        billing, charge = None, None
        unknown: list[str] = []
    else:
        billing, charge = _billing_from_usage(usage)
        unknown = ([str(terminal.get("receipt_identity"))]
                   if billing is None or terminal.get("outcome") not in
                   ("success", "failure") else [])
    tokens = {name: _token_from_usage(usage, field)
              for name, field in (("input", "input_tokens"),
                                  ("output", "output_tokens"))}
    return {"operation_id": operation_id,
            "dispatch_state": (row or {}).get("dispatch_state", "missing"),
            "measured": charge or 0,
            "provider_charge_units": charge,
            "billed": billing,
            "tokens": tokens,
            "unknown": unknown,
            "receipts": [str(r.get("receipt_identity")) for r in receipts]}


def action_identity(action: dict[str, Any]) -> str:
    return payload_digest({"target": action.get("target"),
                           "instrument": action.get("instrument"),
                           "inputs": action.get("inputs", {}),
                           "dependencies": action.get("dependencies", []),
                           "requested": action.get("requested", {})})[:16]


def validate_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {"ok": False, "reason": "action is not an object"}
    if not isinstance(action.get("target"), str) or not action["target"].strip():
        return {"ok": False, "reason": "action names its target"}
    instrument = action.get("instrument")
    if instrument not in _EFFECT_FOR and instrument != STOP:
        return {"ok": False, "reason": f"unknown instrument {instrument!r}"}
    requested = action.get("requested", {})
    if not isinstance(requested, dict):
        return {"ok": False, "reason": "requested resources map names to amounts"}
    for name, amount in requested.items():
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            return {"ok": False,
                    "reason": f"requested resource {name!r} needs a nonnegative integer"}
    if not isinstance(action.get("inputs", {}), dict):
        return {"ok": False, "reason": "action inputs are an object"}
    if not isinstance(action.get("dependencies", []), list):
        return {"ok": False, "reason": "action dependencies are a list"}
    return {"ok": True, "reason": ""}


def materialize_packet(packet: dict[str, Any]) -> dict[str, Any]:
    digest = payload_digest(packet)
    version = packet.get("packet_version")
    if version != PACKET_VERSION:
        return {"outcome": "stale", "packet_id": f"pkt-{digest[:16]}",
                "packet_digest": digest, "reason": f"packet version {version!r}"
                f" is not {PACKET_VERSION}"}
    if "task" in packet or "candidate_shape" in packet:
        return _materialize_construction(packet, digest)
    return _materialize_decision(packet, digest)


def _materialize_decision(packet: dict[str, Any], digest: str) -> dict[str, Any]:
    required = ((packet.get("required_response") or {}).get("fields") or [])
    missing = [key for key in ("charter", "visible_opportunities", "remaining")
               if packet.get(key) is None]
    observations = list(packet.get("observations") or [])
    gaps = {"curriculum_item": packet.get("curriculum_item"),
            "visible_opportunities": list(packet.get("visible_opportunities") or [])}
    footprint = _footprint(packet)
    if missing or not required:
        return {"outcome": "needs_information", "packet_id": f"pkt-{digest[:16]}",
                "packet_digest": digest, "mandatory": required,
                "evidence": observations, "gaps": gaps, "footprint": footprint,
                "reason": f"missing mandatory content {missing}"}
    if not gaps["visible_opportunities"] and gaps["curriculum_item"] is None \
            and not observations:
        return {"outcome": "needs_information", "packet_id": f"pkt-{digest[:16]}",
                "packet_digest": digest, "mandatory": required,
                "evidence": observations, "gaps": gaps, "footprint": footprint,
                "reason": "no visible opportunity, curriculum item or observation"}
    return {"outcome": "ready", "packet_id": f"pkt-{digest[:16]}",
            "packet_digest": digest, "mandatory": required,
            "evidence": observations, "gaps": gaps, "footprint": footprint,
            "reason": ""}


def _materialize_construction(packet: dict[str, Any], digest: str) -> dict[str, Any]:
    missing = [key for key in ("task", "candidate_shape", "entry_rules",
                               "response_contract") if packet.get(key) is None]
    diagnostics = packet.get("diagnostics") or {}
    evidence = list(diagnostics.get("observations") or [])
    gaps = {"prior_failure": diagnostics.get("prior_failure"),
            "budgets": dict(packet.get("budgets") or {})}
    footprint = _footprint(packet)
    if missing or not packet.get("task"):
        return {"outcome": "needs_information", "packet_id": f"pkt-{digest[:16]}",
                "packet_digest": digest, "mandatory": ["task", "candidate_shape",
                                                       "entry_rules", "response_contract"],
                "evidence": evidence, "gaps": gaps, "footprint": footprint,
                "reason": f"missing mandatory content {missing}"}
    return {"outcome": "ready", "packet_id": f"pkt-{digest[:16]}",
            "packet_digest": digest,
            "mandatory": ["task", "candidate_shape", "entry_rules", "response_contract"],
            "evidence": evidence, "gaps": gaps, "footprint": footprint, "reason": ""}


def _footprint(packet: dict[str, Any]) -> dict[str, Any]:
    import json

    raw = json.dumps(packet, sort_keys=True, default=str)
    return {"bytes": len(raw), "token_estimate": len(raw) // 4 + 1,
            "kind": "estimated-budget"}


@dataclass
class ExperienceTransition:
    packet_id: str
    packet_digest: str
    proposal: dict[str, Any]
    admission: str
    operations: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    costs_measured: dict[str, Any] = field(default_factory=dict)
    costs_unknown: list[str] = field(default_factory=list)
    continuation: dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        return {"packet_id": self.packet_id, "packet_digest": self.packet_digest,
                "proposal": self.proposal, "admission": self.admission,
                "operations": list(self.operations), "results": list(self.results),
                "costs_measured": dict(self.costs_measured),
                "costs_unknown": list(self.costs_unknown),
                "continuation": dict(self.continuation)}

    def journal(self, dsn: str, study_root: str) -> CommandResult:
        body = {**self.asdict(), "study_root": study_root}
        action = str((self.proposal or {}).get("action_id", "refused"))
        identity = payload_digest(
            {"packet": self.packet_id, "action": action,
             "admission": self.admission, "proposal": self.proposal,
             "continuation": self.continuation})[:12]
        return store.transact(
            dsn, Command(request_id=f"loop-{self.packet_id}-{action}-{identity}",
                         payload=body),
            _journal_transition, body)

    @staticmethod
    def read_journal(dsn: str, study_root: str, limit: int = 500) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        epoch, ordinal, guard = 0, -1, 0
        while guard < 10:
            page = store.read_events(dsn, epoch, ordinal, limit=limit)
            for event in page["events"]:
                if event.get("kind") != TRANSITION_EVENT:
                    continue
                payload = dict(event.get("payload") or {})
                if payload.get("study_root") == study_root:
                    found.append(payload)
            epoch, ordinal = page["cursor_epoch"], page["cursor_ordinal"]
            guard += 1
            if len(page["events"]) < limit:
                break
        return found


def _journal_transition(cur, control, body: dict) -> tuple:
    return (ResultCode.APPLIED, "transition recorded", dict(body),
            [(TRANSITION_EVENT, dict(body))], [])


@dataclass
class LoopState:
    objective: str = ""
    opportunities: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    repertoire: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    policy_versions: dict = field(default_factory=dict)
    pending: list = field(default_factory=list)
    corrections_used: int = 0
    corrections: dict = field(default_factory=dict)
    last_failure: dict | None = None


def resume_state(dsn: str, study_root: str) -> LoopState:
    state = LoopState()
    for payload in ExperienceTransition.read_journal(dsn, study_root):
        continuation = dict(payload.get("continuation") or {})
        for observation in continuation.get("observations", []):
            if observation not in state.observations:
                state.observations.append(observation)
        for action in continuation.get("pending", []):
            if action not in state.pending:
                state.pending.append(action)
        for action in continuation.get("resolved", []):
            if action in state.pending:
                state.pending.remove(action)
    state.corrections_used = _authority.corrections_total(dsn, study_root)
    return state


def _spend_correction(dsn: str, study_root: str, decision_key: str,
                      failure: dict[str, Any], state: LoopState,
                      max_corrections: int) -> bool:
    try:
        used = _authority.correction_state(
            dsn, study_root, decision_key)["used"]
        taken = _authority.take_correction(
            dsn, study_root, decision_key, failure,
            attempt=used + 1, budget=max_corrections)
        if taken["allowed"]:
            state.corrections_used += 1
        return taken["allowed"]
    except _authority.MissingAuthority:
        spent = int(state.corrections.get(decision_key, 0)) + 1
        state.corrections[decision_key] = spent
        if spent <= max_corrections:
            state.corrections_used += 1
            return True
        return False


def admit_effect(dsn: str, *, allocation_id: str, operation_id: str, effect: str,
                 payload: dict[str, Any], attempt_id: str | None = None,
                 execution_version: str = "", retries: int = 0,
                 kind: str = "") -> Grant | Refusal:
    from . import broker as _broker

    try:
        clean = _broker.validate_effect(effect, payload)
    except _broker.InvalidEffect as exc:
        return Refusal(reason="malformed-action", detail=str(exc))
    if kind == PROBE:
        return Refusal(reason="probe-needs-allowance",
                       detail="probes admit through admit_probe against a probe allowance")
    exposure, budget_kind = _broker.exposure_schedule(effect, clean, retries)
    free = store.allocation_free(dsn, allocation_id)
    if free < exposure:
        return Refusal(reason="insufficient-authority",
                       detail=f"free {free} cannot cover {exposure} exposure;"
                              " no-candidate, never silently underfunded")
    ensured = _broker.ensure_operation(
        dsn, operation_id=operation_id, effect=effect, payload=clean,
        allocation_id=allocation_id, attempt_id=attempt_id,
        execution_version=execution_version, retries=retries)
    if ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return Grant(allowance=Allowance(allowance_id=f"{allocation_id}:{operation_id}",
                                         kind=kind or effect, amount=exposure),
                     operation_id=operation_id, exposure=exposure,
                     budget_kind=budget_kind,
                     already=ensured.code == ResultCode.ALREADY_APPLIED)
    if ensured.code == ResultCode.INSUFFICIENT_RESOURCES:
        return Refusal(reason="insufficient-authority", detail=ensured.detail)
    return Refusal(reason="admission-refused", detail=ensured.detail)


def _effect_payload(instrument: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if instrument == DIAGNOSTIC:
        prompt = inputs.get("prompt", "")
        return {"model": str(inputs.get("model", "scripted")),
                "messages": [{"role": "user", "content": str(prompt)}],
                "max_output_tokens": int(inputs.get("max_output_tokens", 64)),
                "deadline_ms": 300_000}
    if instrument in (CONSTRUCTION, REPAIR, USE):
        return {"profile": "local-process", "argv": list(inputs.get("argv", [])),
                "timeout_ms": int(inputs.get("timeout_ms", 30_000)),
                "max_output_bytes": int(inputs.get("max_output_bytes", 65_536))}
    if instrument == PROBE:
        return {"adapter": "clock", "input": dict(inputs.get("input", {}))}
    return {"command": "note", "payload": dict(inputs.get("payload", {})),
            "idempotency_key": str(inputs.get("idempotency_key", "loop-note"))}


def run_boundary(dsn: str, *, study_root: str, allocation_id: str,
                 packet: dict[str, Any], propose, launchers: dict[str, Any] | None = None,
                 gateway: Any | None = None, state: LoopState | None = None,
                 max_corrections: int = 2, namespace: str = "loop",
                 attempt_id: str | None = None) -> tuple[ExperienceTransition, LoopState]:
    from . import broker as _broker

    own = state if state is not None else resume_state(dsn, study_root)
    materialized = materialize_packet(packet)
    if materialized["outcome"] != "ready":
        transition = ExperienceTransition(
            packet_id=materialized["packet_id"], packet_digest=materialized["packet_digest"],
            proposal={}, admission=f"refused:{materialized['outcome']}",
            continuation={"pending": list(own.pending), "stop": materialized["reason"]})
        transition.journal(dsn, study_root)
        return transition, own
    decision_key = materialized["packet_id"]
    prior = _authority.correction_state(dsn, study_root, decision_key)
    if prior["failure"]:
        own.last_failure = dict(prior["failure"])
    corrections: list[dict[str, Any]] = []
    if prior["failure"] and prior["used"] >= max_corrections:
        raw = None
        checked = {"ok": False, "reason": own.last_failure["reason"]}
    else:
        raw = propose(materialized, own)
        while True:
            checked = validate_action(raw if isinstance(raw, dict) else {})
            if checked["ok"]:
                break
            failure = {"reason": checked["reason"], "decision": decision_key}
            if isinstance(raw, dict) and raw.get("target"):
                failure["target"] = raw["target"]
            corrections.append({"error": checked["reason"]})
            if not _spend_correction(dsn, study_root, decision_key, failure,
                                     own, max_corrections):
                break
            own.last_failure = failure
            raw = propose(materialized, own)
    if not checked["ok"]:
        transition = ExperienceTransition(
            packet_id=materialized["packet_id"],
            packet_digest=materialized["packet_digest"],
            proposal={"raw": raw, "error": checked["reason"],
                      "corrections": corrections},
            admission="refused:malformed-action",
            continuation={"pending": list(own.pending),
                          "correction": "correction-budget-exhausted"})
        transition.journal(dsn, study_root)
        return transition, own
    action = {"target": raw["target"], "instrument": raw["instrument"],
              "inputs": dict(raw.get("inputs", {})), "dependencies": list(raw.get("dependencies", [])),
              "requested": dict(raw.get("requested", {})),
              "hypothesis": raw.get("hypothesis"),
              "action_id": action_identity(raw)}
    if action["instrument"] == STOP:
        transition = ExperienceTransition(
            packet_id=materialized["packet_id"], packet_digest=materialized["packet_digest"],
            proposal=action, admission="admitted:stop",
            continuation={"pending": list(own.pending), "stop": "learner-stopped"})
        transition.journal(dsn, study_root)
        return transition, own
    operation_id = f"{namespace}:{study_root}:{action['action_id']}"
    granted = admit_effect(dsn, allocation_id=allocation_id, operation_id=operation_id,
                           effect=_EFFECT_FOR[action["instrument"]],
                           payload=_effect_payload(action["instrument"], action["inputs"]),
                           attempt_id=attempt_id, kind=action["instrument"])
    if isinstance(granted, Refusal):
        transition = ExperienceTransition(
            packet_id=materialized["packet_id"], packet_digest=materialized["packet_digest"],
            proposal=action, admission=f"refused:{granted.reason}",
            continuation={"pending": list(own.pending), "stop": granted.detail})
        transition.journal(dsn, study_root)
        return transition, own
    status = _broker.dispatch_operation(dsn, operation_id, launchers=launchers or {},
                                        gateway=gateway)
    receipts = store.operation_receipts(dsn, operation_id)
    costs = read_measured_costs(dsn, operation_id)
    observations = [{"operation_id": operation_id,
                     "dispatch_state": status.dispatch_state,
                     "outcome": receipt.get("outcome"),
                     "receipt": receipt.get("receipt_identity"),
                     "content": dict(receipt.get("content") or {})}
                    for receipt in receipts]
    own.observations.extend(observations)
    own.actions.append(action)
    resolved = status.dispatch_state in ("observed", "reconciled", "cancelled")
    pending = [a for a in own.pending if a != action["action_id"]]
    if not resolved:
        pending.append(action["action_id"])
    own.pending = pending
    transition = ExperienceTransition(
        packet_id=materialized["packet_id"], packet_digest=materialized["packet_digest"],
        proposal={**action, "corrections": corrections} if corrections else action,
        admission="admitted",
        operations=[operation_id],
        results=[str(r.get("receipt_identity")) for r in receipts],
        costs_measured={"measured": costs["measured"],
                        "provider_charge_units": costs["provider_charge_units"],
                        "input_tokens": costs["tokens"]["input"],
                        "output_tokens": costs["tokens"]["output"]},
        costs_unknown=list(costs["unknown"]),
        continuation={"pending": list(pending),
                      "observations": observations,
                      "resolved": [action["action_id"]] if resolved else []})
    transition.journal(dsn, study_root)
    return transition, own


def collect_wakeup_events(dsn: str, cursor_epoch: int = 0, cursor_ordinal: int = -1,
                          messages: list[dict[str, Any]] | None = None,
                          now=None) -> dict[str, Any]:
    from . import steward as _steward

    page = store.read_events(dsn, cursor_epoch, cursor_ordinal, limit=500)
    wakeups = [{"kind": "completed-op" if str(e["kind"]).startswith("work.completed") else "event",
                "ref": f"{e['epoch']}:{e['ordinal']}",
                "detail": f"{e['kind']} {e['payload']}"} for e in page["events"]]
    wakeups.extend({"kind": "deadline", "ref": a["id"],
                    "detail": f"attempt {a['id']} past deadline {a.get('deadline')}"}
                   for a in _steward.due_attempts(dsn, now))
    wakeups.extend({"kind": "message", "ref": m.get("id", str(i)), "detail": m.get("text", "")}
                   for i, m in enumerate(messages or []))
    return {"wakeups": wakeups, "cursor_epoch": page["cursor_epoch"],
            "cursor_ordinal": page["cursor_ordinal"]}
