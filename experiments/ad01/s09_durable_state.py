"""Shared durable policy-step state over the existing S09 store."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from . import policy_action
from . import policy_step


POLICY_DIGEST_KINDS = ("ast", "source", "policy-record")


class PolicyBindingMismatch(ValueError):
    pass


class TransitionConflict(ValueError):
    pass


@dataclass(frozen=True)
class PolicyBinding:
    policy_id: str
    digest: str
    digest_kind: str
    origin: str = "authored-control"

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id:
            raise ValueError("policy_id must be a non-empty string")
        if not isinstance(self.digest, str) or len(self.digest) != 64:
            raise ValueError("policy digest must be a SHA-256 hex digest")
        try:
            int(self.digest, 16)
        except ValueError as exc:
            raise ValueError(
                "policy digest must be a SHA-256 hex digest") from exc
        if self.digest_kind not in POLICY_DIGEST_KINDS:
            raise ValueError(
                "policy digest kind must be one of %s"
                % (", ".join(POLICY_DIGEST_KINDS),))
        if self.origin not in policy_step.POLICY_ORIGINS:
            raise ValueError("unknown policy origin: %r" % (self.origin,))

    def as_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "digest": self.digest,
            "digest_kind": self.digest_kind,
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, value: Any) -> PolicyBinding:
        if not isinstance(value, dict):
            raise ValueError("stored policy identity must be an object")
        try:
            return cls(
                policy_id=value["policy_id"],
                digest=value["digest"],
                digest_kind=value["digest_kind"],
                origin=value["origin"],
            )
        except KeyError as exc:
            raise ValueError(
                "stored policy identity is missing %s" % exc.args[0]) from exc


@dataclass(frozen=True)
class DurableStep:
    cid: str
    seq: int
    binding: PolicyBinding
    view_digest: str
    action: dict
    state: dict
    attempt_id: str
    effect_id: str

    def as_dict(self) -> dict:
        return {
            "cid": self.cid,
            "seq": self.seq,
            "binding": self.binding.as_dict(),
            "view_digest": self.view_digest,
            "action": deepcopy(self.action),
            "state": deepcopy(self.state),
            "attempt_id": self.attempt_id,
            "effect_id": self.effect_id,
        }


def view_digest(view: dict) -> str:
    if not isinstance(view, dict):
        raise ValueError("policy view must be an object")
    raw = json.dumps(
        view,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _identity(cid: str, seq: int) -> tuple[str, str]:
    if not isinstance(cid, str) or not cid:
        raise ValueError("cid must be a non-empty string")
    if type(seq) is not int or seq < 0:
        raise ValueError("seq must be a nonnegative integer")
    return policy_step._s09_ids(cid, seq)


def _same_step(left: DurableStep, right: DurableStep) -> bool:
    return left.as_dict() == right.as_dict()


def _names_a_settled_operation(dsn: str, operation_id: str) -> bool:
    """Whether this id is a settled operation, asked of the table."""
    from settlement import db as _db

    with _db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT 1 FROM operations WHERE id = %s AND settled",
            (operation_id,)).fetchone()
        conn.commit()
    return row is not None


def _loaded_step(dsn: str, cid: str, seq: int,
                 binding: PolicyBinding) -> DurableStep | None:
    row = policy_step.load_policy_state(dsn, cid, seq)
    if row is None:
        return None
    accepted = row.get("accepted_action")
    if not isinstance(accepted, dict):
        raise PolicyBindingMismatch(
            "durable policy step has no accepted action")
    if accepted.get("status") != "step-committed":
        raise PolicyBindingMismatch(
            "durable policy step is not committed by this API")
    try:
        stored_binding = PolicyBinding.from_dict(
            accepted.get("policy_identity"))
        stored_view = accepted["view_digest"]
        stored_action = accepted["action"]
        stored_state = accepted["state"]
    except KeyError as exc:
        raise PolicyBindingMismatch(
            "durable policy step is missing %s" % exc.args[0]) from exc
    if stored_binding != binding:
        raise PolicyBindingMismatch(
            "durable policy identity does not match the resumed policy")
    if not isinstance(stored_view, str) or len(stored_view) != 64:
        raise PolicyBindingMismatch("durable policy view digest is invalid")
    if not isinstance(stored_action, dict) \
            or not isinstance(stored_state, dict):
        raise PolicyBindingMismatch("durable policy step shape is invalid")
    policy_step.validate_state(stored_state)
    attempt_id, effect_id = _identity(cid, seq)
    # The attempt identity is what this API owns and recomputes. The effect
    # identity is no longer a constant it can recompute: it is the operation
    # the boundary admitted, set when the effect is incorporated, and empty
    # until then. So the binding check here is on the attempt, plus the shape
    # the effect column is allowed to take. Comparing against a recomputed
    # effect constant would be the RF-02 defect restated as a guard, and it
    # would refuse every row that had correctly adopted a real operation.
    stored_effect = row.get("effect_id")
    if row.get("attempt_id") != attempt_id \
            or not isinstance(stored_effect, str):
        raise PolicyBindingMismatch(
            "durable policy step has a different attempt or effect identity")
    if stored_effect and not _names_a_settled_operation(dsn, stored_effect):
        raise PolicyBindingMismatch(
            "durable policy step names effect %r, which is not a settled"
            " operation" % (stored_effect,))
    output = row.get("policy_output")
    if not isinstance(output, dict) \
            or output.get("source_digest") != binding.digest:
        raise PolicyBindingMismatch(
            "durable policy source digest does not match the resumed policy")
    return DurableStep(
        cid=cid,
        seq=seq,
        binding=binding,
        view_digest=stored_view,
        action=deepcopy(stored_action),
        state=deepcopy(stored_state),
        attempt_id=attempt_id,
        effect_id=stored_effect,
    )


def load_step(dsn: str, cid: str, seq: int, *,
              binding: PolicyBinding) -> DurableStep | None:
    """Load only a step bound to the exact policy that committed it."""
    if not dsn:
        raise ValueError("durable policy state requires a database DSN")
    _identity(cid, seq)
    if not isinstance(binding, PolicyBinding):
        raise ValueError("binding must be a PolicyBinding")
    return _loaded_step(dsn, cid, seq, binding)


def _parsed_step(view: dict, action: dict, state: dict) -> tuple[str, dict, dict]:
    if not isinstance(state, dict):
        raise ValueError("policy state must be an object")
    policy_step.validate_state(state)
    parsed = policy_action.parse_step_result({
        "action": action,
        "state": state,
    })
    parsed_action, parsed_state = parsed
    return view_digest(view), parsed_action.as_dict(), deepcopy(parsed_state)


def persist_step(dsn: str, cid: str, seq: int, *,
                 binding: PolicyBinding, view: dict, action: dict,
                 state: dict) -> DurableStep:
    """Persist one policy step through ``persist_step_transition``."""
    if not dsn:
        raise ValueError("durable policy state requires a database DSN")
    if not isinstance(binding, PolicyBinding):
        raise ValueError("binding must be a PolicyBinding")
    _identity(cid, seq)
    digest, parsed_action, parsed_state = _parsed_step(view, action, state)
    attempt_id, effect_id = _identity(cid, seq)
    step = DurableStep(
        cid=cid,
        seq=seq,
        binding=binding,
        view_digest=digest,
        action=parsed_action,
        state=parsed_state,
        attempt_id=attempt_id,
        effect_id=effect_id,
    )
    existing = _loaded_step(dsn, cid, seq, binding)
    if existing is not None:
        if not _same_step(existing, step):
            raise TransitionConflict(
                "durable policy seq already holds a different transition")
        return existing
    accepted = {
        "status": "step-committed",
        "policy_identity": binding.as_dict(),
        "view_digest": digest,
        "action": parsed_action,
        "state": parsed_state,
    }
    policy_step.persist_step_transition(
        dsn,
        cid,
        seq,
        views=[{"digest": digest}],
        results=[{"action": parsed_action, "state": parsed_state}],
        transitions=[{"previous": None, "next": parsed_state}],
        investigation=accepted,
        source_digest=binding.digest,
        status="accepted",
    )
    persisted = _loaded_step(dsn, cid, seq, binding)
    if persisted is None:
        raise RuntimeError("durable policy step was not persisted")
    if not _same_step(persisted, step):
        raise TransitionConflict(
            "concurrent durable policy transition conflicts with this step")
    return persisted


def resume_or_step(dsn: str, cid: str, seq: int, *,
                   binding: PolicyBinding, view: dict,
                   execute: Callable[[dict], dict]) -> DurableStep:
    """Resume a committed step or execute and durably commit the next one."""
    committed = load_step(dsn, cid, seq, binding=binding)
    if committed is not None:
        return committed
    result = execute(deepcopy(view))
    if not isinstance(result, dict):
        raise ValueError("policy executor must return an object")
    return persist_step(
        dsn,
        cid,
        seq,
        binding=binding,
        view=view,
        action=result.get("action"),
        state=result.get("state"),
    )


def durable_model_calls(dsn: str, cid: str, seq: int) -> int:
    return policy_step.durable_model_calls(dsn, cid, seq)


__all__ = [
    "DurableStep",
    "POLICY_DIGEST_KINDS",
    "PolicyBinding",
    "PolicyBindingMismatch",
    "TransitionConflict",
    "durable_model_calls",
    "load_step",
    "persist_step",
    "resume_or_step",
    "view_digest",
]
