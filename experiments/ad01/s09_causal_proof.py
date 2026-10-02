"""Did a policy's decision cause an operation, or was its digest copied on?

Finding S09R-02. A live study dispatched three operations, received three
`failure` receipts with empty text, and exited 0. Every use record it wrote
carried a policy digest. A prior campaign read those records and scored them
as evidence the policy governed the use. It was never invoked.

The circularity is the reason nobody caught it. Launch qualification read
the bundle the study was about to write, so the only way to reach a pass was
to manufacture the success the experiment was meant to measure. The predicate
it evaluated was a list of loosely related fields: a nonempty digest list on
some record, a nonempty action on some record, two distinct digest tuples
overall. No field of that predicate claims a policy caused anything, and two
unrelated records satisfy it between them.

This module separates the two questions that were fused, and gives each a
shape that answers only what it can.

    qualify_pre_launch   Can this apparatus produce a causal chain at all?
                         Deterministic, no store, no gateway, no clock.
                         Reads reviewer-authored policies in a namespace of
                         their own. It qualifies launch. It establishes
                         nothing about acquisition, and it never reads a
                         use record, so a bundle cannot witness itself.

    join_post_effect     Did this policy's decision cause this operation?
                         Reads the persisted chain and recomputes every
                         link from bytes. A third party can rerun it offline
                         from the export with no gateway and no store.

The chain is one where each link is the digest of the link before it:

    policy source -> sha256 -> the decision those bytes returned for this
    view -> the action that decision admitted -> the operation the action
    authorized -> the receipt that operation produced

The method is a second, separate artifact on the use side, and its digest is
joined to its own executed bytes. It is not compared to the policy's digest.
A policy STEP and a task method ENTRY are different things and may hold
different bytes; the reviewer correction is explicit that any ledger rule
equating the two is too broad. What must hold is that each one matches its
own bytes and that the policy's decision caused the admitted action.

Two states, and only two, because a live run is not this module's to
re-judge and so nothing here returns `fail`. `unproven` covers a claim
whose links are partly absent, a link that disagrees with the bytes, and a
receipt from another lineage.

What the pipeline persists today, measured on `evidence_s09_m3_live` and
`evidence_s09_live_opus`: 24 of 24 use records carry `policy_digest`,
`executed_source`, `executed_source_digest` and `operation_ids`, and 0 of
24 carry `policy_actions`. No bundle member holds a use-phase view, a
use-phase decision, or an operation's study root, and
`persist_step_transition` is never called from the use path at all. So the
post-effect join has links to read that no export carries yet, and the
launch check is the only one of the two a preflight can honestly run
today. The `unproven` those records earn is the correct reading of them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from . import policy_step

PROVEN = "proven"
UNPROVEN = "unproven"

CLAIMED_DIGEST_FIELD = "policy_digest"
EXECUTED_SOURCE_FIELD = "executed_source"
EXECUTED_DIGEST_FIELD = "executed_source_digest"
OPERATION_IDS_FIELD = "operation_ids"
RECORD_ID_FIELD = "record_id"
TASK_ID_FIELD = "task_id"

# One reason per broken link, in chain order. A record that names a policy
# and cannot produce its decision reports this, and it is the live failure.
NO_POLICY_DECISION = "no-policy-decision"
POLICY_BYTES_MISMATCH = "policy-bytes-mismatch"
VIEW_BYTES_MISMATCH = "view-bytes-mismatch"
NO_ADMITTED_ACTION = "no-admitted-action"
ACTION_MISMATCH = "action-mismatch"
NO_ADMITTED_OPERATION = "no-admitted-operation"
NO_RECEIPT = "no-receipt"
RECEIPT_IDENTITY_MISMATCH = "receipt-identity-mismatch"
FOREIGN_STUDY_ROOT = "foreign-study-root"
NO_METHOD_BYTES = "no-method-bytes"
METHOD_BYTES_MISMATCH = "method-bytes-mismatch"

REASONS = (
    NO_POLICY_DECISION, POLICY_BYTES_MISMATCH, VIEW_BYTES_MISMATCH,
    NO_ADMITTED_ACTION, ACTION_MISMATCH, NO_ADMITTED_OPERATION,
    NO_ADMITTED_OPERATION, NO_RECEIPT, RECEIPT_IDENTITY_MISMATCH,
    FOREIGN_STUDY_ROOT, NO_METHOD_BYTES, METHOD_BYTES_MISMATCH,
)


def sha256_of(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def view_digest(view: Mapping[str, Any]) -> str:
    """The digest of the view a decision was taken against."""
    return sha256_of(json.dumps(dict(view), sort_keys=True))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


class LinkBroken(RuntimeError):
    """One link of the chain does not follow from the bytes.

    The reason is a closed vocabulary, so a caller can branch on it and a
    test can assert it without matching prose.
    """

    def __init__(self, reason: str, detail: str) -> None:
        if reason not in REASONS:
            raise ValueError("unknown chain reason %r" % (reason,))
        self.reason = reason
        self.detail = detail
        super().__init__("%s: %s" % (reason, detail))


@dataclass(frozen=True)
class Link:
    """One step of the chain, and what was recomputed to check it.

    `persisted` distinguishes the two checks. A link read off bytes a third
    party can reopen is persisted. A link produced by this module's own
    replay is not, and no pre-launch result is a substitute for one.
    """

    name: str
    detail: str
    persisted: bool


@dataclass(frozen=True)
class PolicyChain:
    """A policy's bytes, its decision, the action it admitted, the effect.

    Every field here is a digest or an identity recomputed from bytes. The
    writer of the record is never the source of a value in this object.
    """

    record_id: str
    task_id: str
    policy_digest: str
    view_digest: str
    action_digest: str
    operation_id: str
    receipt_identity: str
    method_digest: str
    study_root: str
    persisted: bool

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in (
            "record_id", "task_id", "policy_digest", "view_digest",
            "action_digest", "operation_id", "receipt_identity",
            "method_digest", "study_root", "persisted")}


@dataclass(frozen=True)
class Verdict:
    """`proven` walks the whole chain. Everything else is `unproven`.

    Two states, and only two, because a live run is not this module's
    to re-judge and so nothing here returns `fail`. A claim whose links are
    partly absent, a link that disagrees with the bytes, and a receipt
    from another lineage are all `unproven`.
    """

    status: str
    reasons: tuple = ()
    chains: tuple = ()
    links: tuple = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if self.status not in (PROVEN, UNPROVEN):
            raise ValueError("unknown causal status %r" % (self.status,))
        if self.status == PROVEN and (self.reasons or not self.chains):
            raise ValueError("a proven verdict carries a chain and no reason")
        if self.status == UNPROVEN and not self.reasons:
            raise ValueError("an unproven verdict must name what is missing")
        if any(reason not in REASONS for reason in self.reasons):
            raise ValueError("a verdict may only report closed reasons")

    @property
    def proved(self) -> bool:
        return self.status == PROVEN

    def as_dict(self) -> dict:
        return {"status": self.status, "reasons": list(self.reasons),
                "detail": self.detail,
                "chains": [chain.as_dict() for chain in self.chains],
                "links": [{"name": link.name, "detail": link.detail,
                           "persisted": link.persisted}
                          for link in self.links]}


@dataclass(frozen=True)
class PolicyRun:
    """One replayed policy: source bytes, the view, the operation it drove.

    A launch qualification is built from these, so the object that carries
    a policy into the check is also the one that says what happened. There
    is no field on it for a digest a caller supplied, which is why a
    backfilled string cannot reach the launch path at all.
    """

    policy_source: str
    view: dict
    operations: tuple = ()
    state: dict = field(default_factory=dict)
    entry: str = policy_step.STEP_ENTRY
    limits: dict | None = None

    def __post_init__(self) -> None:
        if not self.policy_source.strip():
            raise ValueError("a policy run needs source bytes")
        policy_step.validate_view(self.view)
        policy_step.validate_state(self.state)

    @property
    def source_digest(self) -> str:
        return sha256_of(self.policy_source)


@dataclass(frozen=True)
class AdmittedOperation:
    """An operation the store recorded, read from its own row.

    `method_digest` is the method the operation executed, which is a
    different artifact from the policy that authorized it. `study_root` is
    the namespace that separates this lineage from every other one, and it
    is the field a foreign receipt is caught on.
    """

    operation_id: str
    effect: str
    study_root: str
    method_digest: str = ""

    @classmethod
    def from_row(cls, payload: Any) -> "AdmittedOperation | None":
        if not isinstance(payload, Mapping):
            return None
        return cls(operation_id=str(payload.get("operation_id", "")),
                   effect=str(payload.get("effect", "")),
                   study_root=str(payload.get("study_root", "")),
                   method_digest=str(payload.get("method_digest", "")))


def _receipt_for(operation_id: str,
                 receipts: Sequence[Any]) -> Mapping[str, Any] | None:
    for receipt in receipts:
        if isinstance(receipt, Mapping) and str(
                receipt.get("operation_id", "")) == operation_id:
            return receipt
    return None


def _gateway_identity(receipt: Mapping[str, Any]) -> str | None:
    """The broker's response class for this receipt, or None if not its own.

    The broker mints `gw:<operation>` for a response and appends a class for
    anything else. Any other gateway identity is not this lineage's
    receipt, and None keeps that distinct from the bare class-less form.
    """
    operation_id = receipt.get("operation_id", "")
    identity = _text(receipt.get("receipt_identity"))
    if identity.startswith("gw:%s:" % operation_id):
        return identity[len("gw:%s:" % operation_id):]
    if identity == "gw:%s" % operation_id:
        return ""
    return None


def _receipt_root(receipt: Mapping[str, Any], operation: AdmittedOperation
                  ) -> str:
    """Whose lineage the receipt claims, from the receipt or its operation."""
    content = receipt.get("content")
    if isinstance(content, Mapping):
        claimed = _text(content.get("study_root"))
        if claimed:
            return claimed
    return operation.study_root


def _source_link(policy_source: str,
                 decision: Mapping[str, Any]) -> str:
    """Link one: the bytes this decision ran under are the bytes we hold."""
    source_digest = sha256_of(policy_source)
    if source_digest != _text(decision.get("source_digest")):
        raise LinkBroken(POLICY_BYTES_MISMATCH,
                         "sha256 of %d policy bytes is %s, the decision ran"
                         " under %s" % (
                             len(policy_source), source_digest,
                             _text(decision.get("source_digest"))))
    return source_digest


def _view_link(view: Mapping[str, Any],
               decision: Mapping[str, Any]) -> str:
    """Link two: the view is recomputed, not taken from the decision."""
    digest = view_digest(view)
    if digest != _text(decision.get("view_digest")):
        raise LinkBroken(VIEW_BYTES_MISMATCH,
                         "sha256 of the view is %s, the decision was taken"
                         " against %s" % (digest,
                                          _text(decision.get("view_digest"))))
    return digest


def _action_link(action: Any, decision: Mapping[str, Any]) -> str:
    """Link three: the admitted action is the one the bytes returned."""
    if not isinstance(action, Mapping) or not action:
        raise LinkBroken(NO_ADMITTED_ACTION,
                         "the decision admitted no action")
    if _canonical(dict(action)) != _canonical(dict(
            decision.get("action") or {})):
        raise LinkBroken(ACTION_MISMATCH,
                         "the admitted action is not the one the decision"
                         " returned")
    return sha256_of(_canonical(dict(action)))


def _operation_link(operation: AdmittedOperation) -> str:
    """Link four: the action authorized an operation the store recorded."""
    if not operation.operation_id:
        raise LinkBroken(NO_ADMITTED_OPERATION,
                         "the admitted action authorized no operation")
    return operation.operation_id


def _receipt_link(receipt: Mapping[str, Any],
                  operation: AdmittedOperation) -> str:
    """Links five and six: the operation's receipt, and whose lineage it is.

    Identity is where a doubled receipt is caught. The broker mints
    `gw:<operation>:<class>` and no other gateway identity, and a live
    lineage's operation carries this lineage's study root. A receipt that
    breaks either is evidence from somewhere else.
    """
    identity = _gateway_identity(receipt)
    if identity is None:
        raise LinkBroken(RECEIPT_IDENTITY_MISMATCH,
                         "receipt identity %r is not the gw:<operation>"
                         "[:<class>] the broker mints"
                         % _text(receipt.get("receipt_identity")))
    root = _receipt_root(receipt, operation)
    if root != operation.study_root:
        raise LinkBroken(FOREIGN_STUDY_ROOT,
                         "the receipt belongs to %r and this operation to %r"
                         % (root, operation.study_root))
    return _text(receipt.get("receipt_identity"))


def _method_link(method_source: str, operation: AdmittedOperation) -> str:
    """Link seven: the method is joined to its own executed bytes.

    The method is a different artifact from the policy, so its digest is
    never compared to the policy's. It is compared to what the store says
    the operation executed.
    """
    if not method_source:
        raise LinkBroken(NO_METHOD_BYTES,
                         "the use record persisted no executed method bytes")
    digest = sha256_of(method_source)
    if digest != _text(operation.method_digest):
        raise LinkBroken(METHOD_BYTES_MISMATCH,
                         "sha256 of the executed method is %s and the store"
                         " recorded %s" % (digest, operation.method_digest))
    return digest


def walk(*, policy_source: str, view: Mapping[str, Any],
         decision: Mapping[str, Any], action: Mapping[str, Any],
         operation: AdmittedOperation, receipt: Mapping[str, Any],
         method_source: str) -> PolicyChain:
    """Walk the seven links of the post-effect chain, in order.

    Every link is recomputed from bytes, so a third party holding the same
    export reaches the same answer without our process, a gateway or a
    store. The first link that does not hold raises, naming itself.
    """
    source_digest = _source_link(policy_source, decision)
    digest = _view_link(view, decision)
    action_digest = _action_link(action, decision)
    operation_id = _operation_link(operation)
    identity = _receipt_link(receipt, operation)
    method_digest = _method_link(method_source, operation)
    return PolicyChain(
        record_id="", task_id="", policy_digest=source_digest,
        view_digest=digest, action_digest=action_digest,
        operation_id=operation_id, receipt_identity=identity,
        method_digest=method_digest, study_root=operation.study_root,
        persisted=True)


def _records(store: Mapping[str, Any]) -> list:
    records = store.get("use_records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        return []
    return [record for record in records if isinstance(record, Mapping)]


def _operations(store: Mapping[str, Any]) -> dict:
    rows = store.get("operations")
    if not isinstance(rows, Mapping):
        return {}
    return {str(operation_id): AdmittedOperation.from_row(row)
            for operation_id, row in rows.items()}


def _admitted_actions(record: Mapping[str, Any]) -> list:
    """The actions this record says the policy admitted, in its own order.

    A record naming no action cannot have had one admitted, and the
    decision's own return value is not a substitute for one. That value is
    the claim under test, so it is matched against what the record holds
    and never copied out of it to stand in.
    """
    listed = record.get("policy_actions")
    if not isinstance(listed, Sequence) or isinstance(listed, (str, bytes)):
        return []
    return [dict(item) for item in listed if isinstance(item, Mapping)]


def join_post_effect(store: Any) -> Verdict:
    """Join each use record to the chain of bytes that caused its operation.

    One record, one chain. A record that holds only a digest cannot borrow
    an action from a record that holds only an action, because the two are
    never pooled. A record that claims a policy and cannot produce the
    decision that admitted its operation is `unproven`, and so is a record
    whose chain is whole but whose receipt came from another lineage.
    """
    if not isinstance(store, Mapping):
        return Verdict(UNPROVEN, (NO_POLICY_DECISION,),
                       detail=("%r is not a persisted record set" % (store,)))
    source = store.get("policy_source")
    view = store.get("view")
    decision = store.get("decision")
    receipts = store.get("receipts")
    receipts = list(receipts) if isinstance(receipts, Sequence) \
        and not isinstance(receipts, (str, bytes)) else []
    operations = _operations(store)
    records = _records(store)
    if not records:
        return Verdict(UNPROVEN, (NO_POLICY_DECISION,),
                       detail="the record set is empty, so no use record"
                              " claims a policy")

    chains, reasons, links = [], set(), []
    for record in records:
        attempt, refused = _one_record(
            record, source, view, decision, operations, receipts)
        reasons.update(reason for reason, _ in refused)
        links.extend(Link(reason, detail, True) for reason, detail in refused)
        chains.extend(attempt)
    if chains:
        return Verdict(PROVEN, (), tuple(chains), tuple(links))
    return Verdict(UNPROVEN, tuple(sorted(reasons)) or (NO_POLICY_DECISION,),
                   (), tuple(links),
                   detail=_summary(records, sorted(reasons)))


def _one_record(record: Mapping[str, Any], source: Any, view: Any,
                decision: Any, operations: Mapping[str, Any],
                receipts: Sequence[Any]) -> tuple:
    """One use record, one chain. Never pooled with any other record."""
    claimed = _text(record.get(CLAIMED_DIGEST_FIELD))
    if not claimed:
        return (), ()
    method_source = _text(record.get(EXECUTED_SOURCE_FIELD))
    recorded = _text(record.get(EXECUTED_DIGEST_FIELD))
    if method_source and recorded \
            and sha256_of(method_source) != recorded:
        return (), ((METHOD_BYTES_MISMATCH,
                     "the recorded %s is not sha256 of the executed bytes"
                     % EXECUTED_DIGEST_FIELD),)
    if not isinstance(decision, Mapping) \
            or _text(decision.get("source_digest")) != claimed:
        return (), ((NO_POLICY_DECISION,
                     "no persisted decision runs under digest %s" % claimed),)
    if not isinstance(source, str) or sha256_of(source) != claimed:
        return (), ((POLICY_BYTES_MISMATCH,
                     "the persisted policy bytes do not hash to %s" % claimed),)
    if not isinstance(view, Mapping):
        return (), ((VIEW_BYTES_MISMATCH, "no persisted view to recompute"),)
    actions = _admitted_actions(record)
    if not actions:
        return (), ((NO_ADMITTED_ACTION,
                     "the record names no action the policy admitted"),)
    chains, refused = [], []
    for action in actions:
        chain, broken = _one_chain(
            record, source, view, decision, action, operations, receipts,
            method_source)
        if broken is None:
            chains.append(_named(chain, record))
        else:
            refused.append((broken.reason, broken.detail))
    return tuple(chains), tuple(refused)


def _one_chain(record, source, view, decision, action, operations, receipts,
               method_source) -> tuple:
    operation = None
    for operation_id in record.get(OPERATION_IDS_FIELD) or ():
        candidate = operations.get(str(operation_id))
        if candidate is not None:
            operation = candidate
            break
    if operation is None:
        return None, LinkBroken(
            NO_ADMITTED_OPERATION,
            "the record names operations %s and the store holds none of them"
            % (list(record.get(OPERATION_IDS_FIELD) or ()),))
    receipt = _receipt_for(operation.operation_id, receipts)
    if receipt is None:
        return None, LinkBroken(
            NO_RECEIPT, "operation %s produced no receipt" % operation.operation_id)
    try:
        return walk(policy_source=source, view=view, decision=decision,
                    action=action, operation=operation, receipt=receipt,
                    method_source=method_source), None
    except LinkBroken as broken:
        return None, broken


def _summary(records: Sequence[Any], reasons: Sequence[str]) -> str:
    claiming = sum(1 for record in records
                   if _text(record.get(CLAIMED_DIGEST_FIELD)))
    if not claiming:
        return ("no use record names a policy digest, so none of the %d"
                " records claims a policy governed it" % len(records))
    return ("%d of %d use records name a policy digest and none produced the"
            " chain: %s" % (claiming, len(records), ", ".join(reasons)))


def _named(chain: PolicyChain, record: Mapping[str, Any]) -> PolicyChain:
    import dataclasses
    return dataclasses.replace(
        chain, record_id=_text(record.get(RECORD_ID_FIELD)),
        task_id=_text(record.get(TASK_ID_FIELD)))


def qualify_pre_launch(*, policies: Sequence[PolicyRun],
                       operations: Sequence[Any]) -> Verdict:
    """Ask whether the apparatus turns a policy's decision into an effect.

    Deterministic, and it reads nothing a study would write. Each policy's
    own bytes are executed through the same out-of-process step boundary
    the study uses, so the admitted action is produced here rather than
    supplied. The operations the caller names are the ones the action was
    admitted to authorize. There is no receipt to join and no method to
    join, because neither exists before launch, and the chain says so by
    carrying neither.

    This qualifies launch. It establishes nothing about a model acquiring a
    policy, and it never reads a use record, so a post-effect record set
    cannot be mistaken for a qualification and a bundle cannot witness the
    study that is about to write it.
    """
    if not policies:
        return Verdict(UNPROVEN, (NO_POLICY_DECISION,),
                       detail="no policy was offered to qualify, so the"
                              " apparatus was never asked to decide anything")
    known = {str(row.get("operation_id", "")): row
             for row in operations if isinstance(row, Mapping)}
    chains, reasons, links = [], set(), []
    for run in policies:
        if run.entry != policy_step.STEP_ENTRY:
            reasons.add(NO_ADMITTED_ACTION)
            links.append(Link("entry", "this check executes the %s boundary,"
                             " not %s" % (policy_step.STEP_ENTRY, run.entry),
                             False))
            continue
        try:
            action = _replay(run)["action"]
            decision = {"source_digest": run.source_digest,
                        "view_digest": view_digest(run.view),
                        "action": dict(action)}
        except Exception as exc:
            reasons.add(NO_ADMITTED_ACTION)
            links.append(Link("step", "%s: %s" % (type(exc).__name__, exc),
                             False))
            continue
        links.append(Link("source", "the policy's %d bytes ran in a fresh"
                          " interpreter" % len(run.policy_source), False))
        links.append(Link("action", "the bytes admitted %s"
                          % _text(action.get("kind")), False))
        if not run.operations:
            reasons.add(NO_ADMITTED_OPERATION)
            links.append(Link("operations", "the policy admitted an action"
                                               " that authorized no operation",
                             False))
            continue
        for operation_id in run.operations:
            try:
                chains.append(_launch_chain(
                    run, decision, action,
                    known.get(str(operation_id), {"operation_id":
                                                  operation_id})))
            except LinkBroken as broken:
                reasons.add(broken.reason)
                links.append(Link(broken.reason, broken.detail, False))
    if chains:
        return Verdict(PROVEN, (), tuple(chains), tuple(links))
    return Verdict(UNPROVEN, tuple(sorted(reasons)) or (NO_ADMITTED_ACTION,),
                   (), tuple(links),
                   detail="no policy admitted an action the store recorded")


def _launch_chain(run: PolicyRun, decision: Mapping[str, Any],
                  action: Mapping[str, Any],
                  row: Mapping[str, Any]) -> PolicyChain:
    """The launch chain: four links, every one of them unpersisted.

    Source, view, action, operation. The receipt and the method do not
    exist before a run does, so they are not links of this chain rather
    than empty links of the other one. Every link here was produced by this
    module's replay, so the chain is marked unpersisted: no export can
    carry it, and nothing downstream may read it as live evidence.
    """
    operation = AdmittedOperation.from_row(row) or AdmittedOperation(
        operation_id="", effect="", study_root="")
    return PolicyChain(
        record_id="pre-launch", task_id="",
        policy_digest=_source_link(run.policy_source, decision),
        view_digest=_view_link(run.view, decision),
        action_digest=_action_link(action, decision),
        operation_id=_operation_link(operation),
        receipt_identity="", method_digest="",
        study_root=operation.study_root, persisted=False)


def _replay(run: PolicyRun) -> dict:
    from . import method_exec
    limits = dict(run.limits or policy_step.step_limits())
    return policy_step.validate_step_result(method_exec.run_step_out_of_process(
        run.policy_source, run.view, dict(run.state), entry=run.entry,
        timeout_ms=int(limits.get("timeout_ms", policy_step.STEP_TIMEOUT_MS)),
        cpu_seconds=int(limits.get("cpu_seconds",
                                    policy_step.STEP_CPU_SECONDS)),
        max_output_bytes=int(limits.get(
            "max_output_bytes", policy_step.STEP_MAX_OUTPUT_BYTES))))


__all__ = [
    "AdmittedOperation",
    "FOREIGN_STUDY_ROOT",
    "Link",
    "LinkBroken",
    "METHOD_BYTES_MISMATCH",
    "NO_ADMITTED_ACTION",
    "NO_ADMITTED_OPERATION",
    "NO_METHOD_BYTES",
    "NO_POLICY_DECISION",
    "NO_RECEIPT",
    "POLICY_BYTES_MISMATCH",
    "PROVEN",
    "PolicyChain",
    "PolicyRun",
    "REASONS",
    "RECEIPT_IDENTITY_MISMATCH",
    "UNPROVEN",
    "Verdict",
    "VIEW_BYTES_MISMATCH",
    "join_post_effect",
    "qualify_pre_launch",
    "sha256_of",
    "view_digest",
]
