"""One typed action contract for every policy representation.

Six action vocabularies coexist today, each a plain tuple of strings with
its own hand-written validator: `policy_step.ACTION_KINDS`, the legacy
learner's next actions, `frontier.OPERATE_KINDS`,
`improve_channel.IMPROVE_KINDS`, the settlement loop's instruments, and
the representation profile's `encode/start/advance/decode`. A
representation built against its own vocabulary cannot be compared with
one built against another, because "the same action" has no shared
meaning to hold constant.

This module is that shared meaning. It is a contract, not a runtime:
the broker, the child executor, receipts and authority stay where they
are. A representation-specific adapter converts its own output into an
`Action` here, and everything downstream consumes the same value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONTRACT_VERSION = "s09-policy-action/1"

PROBE = "probe"
OBSERVE = "observe"
CONSTRUCT = "construct"
USE = "use"
CHECK = "check"
STOP = "stop"

ACTION_KINDS = (PROBE, OBSERVE, CONSTRUCT, USE, CHECK, STOP)


class ActionRefused(Exception):
    pass


@dataclass(frozen=True)
class Action:
    kind: str
    target: str = ""
    inputs: dict = field(default_factory=dict)
    evidence_refs: tuple = ()
    requested_resources: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "target": self.target,
                "inputs": dict(self.inputs),
                "evidence_refs": list(self.evidence_refs),
                "requested_resources": dict(self.requested_resources)}


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ActionRefused("%s must be a string" % name)
    return value


def _require_mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise ActionRefused("%s must be an object" % name)
    for key, item in value.items():
        _require_str(key, "%s key" % name)
    return value


def parse_action(payload: Any) -> Action:
    """Validate a representation's action into the shared contract."""
    data = _require_mapping(payload, "action")
    unknown = set(data) - {"kind", "target", "inputs", "evidence_refs",
                           "requested_resources"}
    if unknown:
        raise ActionRefused("unknown action fields %s" % sorted(unknown))
    kind = _require_str(data.get("kind"), "action kind")
    if kind not in ACTION_KINDS:
        raise ActionRefused("unknown action kind %r" % (kind,))
    target = _require_str(data.get("target", ""), "action target")
    if not target:
        raise ActionRefused("action target must be a non-empty string")
    inputs = _require_mapping(data.get("inputs", {}), "action inputs")
    resources = _require_mapping(
        data.get("requested_resources", {}), "requested_resources")
    refs = data.get("evidence_refs", [])
    if not isinstance(refs, (list, tuple)):
        raise ActionRefused("evidence_refs must be a list")
    return Action(kind=kind, target=target, inputs=inputs,
                  evidence_refs=tuple(_require_str(r, "evidence ref")
                                      for r in refs),
                  requested_resources=resources)


def view_contract() -> dict:
    """The observation surface every representation is entitled to see."""
    return {
        "version": CONTRACT_VERSION,
        "fields": ("instrument", "task_id", "observed", "remaining",
                   "public_world", "action_schema"),
        "excluded": "assessor secrets are never present; see packet.public_task_view",
    }


def state_contract() -> dict:
    return {
        "version": CONTRACT_VERSION,
        "step_state_key": "state",
        "step_state": "the policy's own working state returned with each action; "
                      "carried between steps and across processes",
        "campaign_private_state_key": "private_state",
        "campaign_private_state": "durable campaign state owned by the "
                                  "frontier store, reset on binding and on "
                                  "revision adoption; NOT the policy's state",
        "distinct": True,
    }


def parse_step_result(result: Any) -> tuple:
    """Return (action, state) from a representation's step output.

    The policy's own working state is `state`. It is deliberately not
    called `private_state`, which already names the frontier's durable
    campaign state. Conflating them would let one representation's
    memory mean a different thing from another's.
    """
    data = _require_mapping(result, "step result")
    unknown = set(data) - {"action", "state"}
    if unknown:
        raise ActionRefused("unknown step result fields %s" % sorted(unknown))
    if "action" not in data or "state" not in data:
        raise ActionRefused("step result must carry action and state")
    state = _require_mapping(data["state"], "step state")
    return parse_action(data["action"]), state
