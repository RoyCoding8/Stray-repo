"""coordination-procedure/1 wire schema: versioned step transport.

Reuses the representation-01 canonical-bytes/digest helpers per DEC-EC02-01.
The controller derives phase and the allowed-action set from accepted state;
procedure memory never selects them. Responses echo every request identity
exactly; unknown actions and extra effect-bearing fields are errors.
"""

from __future__ import annotations

import json
from typing import Any

from settlement.common import SettlementError
from settlement.representation import canonical_bytes, sha_hex

PROFILE = "coordination-procedure/1"
PROFILE_VERSION = "coordination-procedure/1"

ACTIONS = ("probe", "plan", "rework", "stop", "unsupported")

PHASE_PRE_PLAN = "pre-plan"
PHASE_POST_PROBE = "post-probe"
PHASE_POST_FAIL_JOIN = "post-fail-join"
PHASE_POST_FAIL_PROBE = "post-fail-probe"
PHASE_TERMINAL = "terminal"

ALLOWED: dict[str, tuple[str, ...]] = {
    PHASE_PRE_PLAN: ("probe", "plan", "unsupported", "stop"),
    PHASE_POST_PROBE: ("plan", "unsupported", "stop"),
    PHASE_POST_FAIL_JOIN: ("probe", "rework", "stop"),
    PHASE_POST_FAIL_PROBE: ("rework", "stop"),
    PHASE_TERMINAL: (),
}

MAX_STATE_BYTES = 16 * 1024
MAX_MESSAGE_BYTES = 65_536
MAX_PROBE_CALLS = 4
MAX_REASON_CHARS = 256
MAX_POLICY_STEPS = 8


class PolicyError(SettlementError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail[:MAX_REASON_CHARS]
        super().__init__(f"coordination-procedure/1 refused: {reason}"
                         + (f": {self.detail}" if self.detail else ""))


def _token(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise PolicyError("malformed", f"{name} must be a bounded non-empty string")
    return value


def build_request(*, decision_id: str, package_digest: str, source_digest: str,
                  plan_revision: int, phase: str, allowed: list[str],
                  state: Any, task: dict) -> dict:
    _token(decision_id, "decision_id")
    _token(package_digest, "package_digest")
    _token(source_digest, "source_digest")
    if phase not in ALLOWED:
        raise PolicyError("malformed", f"unknown phase {phase!r}")
    if sorted(allowed) != sorted(ALLOWED[phase]):
        raise PolicyError("malformed", "allowed set must equal the phase set")
    if not isinstance(task, dict):
        raise PolicyError("malformed", "task must be an object")
    raw_state = canonical_bytes(state)
    if len(raw_state) > MAX_STATE_BYTES:
        raise PolicyError("oversize", "procedure state exceeds 16 KiB")
    return {"profile": PROFILE, "profile_version": PROFILE_VERSION,
            "decision_id": decision_id, "package_digest": package_digest,
            "source_digest": source_digest, "plan_revision": int(plan_revision),
            "phase": phase, "allowed_actions": list(allowed),
            "state": state, "task": task}


def request_bytes(request: dict) -> bytes:
    raw = canonical_bytes(request)
    if len(raw) > MAX_MESSAGE_BYTES:
        raise PolicyError("oversize", "request exceeds the message limit")
    return raw


def _bounded_reason(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_REASON_CHARS:
        raise PolicyError("malformed", "reason must be a bounded string")
    return value


def _check_echo(response: dict, *, decision_id: str, package_digest: str,
                source_digest: str, plan_revision: int, phase: str) -> None:
    for key, want in (("decision_id", decision_id),
                      ("package_digest", package_digest),
                      ("source_digest", source_digest),
                      ("plan_revision", int(plan_revision)),
                      ("phase", phase)):
        if response.get(key) != want:
            raise PolicyError("stale-identity",
                              f"response {key} does not match the invocation")


def _check_state(state: Any) -> Any:
    if len(canonical_bytes(state)) > MAX_STATE_BYTES:
        raise PolicyError("oversize", "response state exceeds 16 KiB")
    return state


def _probe_proposal(proposal: dict) -> dict:
    if set(proposal) != {"action", "invocations"}:
        raise PolicyError("malformed", "probe carries only action+invocations")
    calls = proposal["invocations"]
    if not isinstance(calls, list) or len(calls) > MAX_PROBE_CALLS:
        raise PolicyError("malformed", "probe needs at most four invocations")
    cleaned = []
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"interface", "input"}:
            raise PolicyError("malformed", "probe calls name an interface and input")
        _token(call["interface"], "interface")
        if not isinstance(call["input"], dict):
            raise PolicyError("malformed", "probe input must be an object")
        if len(canonical_bytes(call["input"])) > MAX_MESSAGE_BYTES // 4:
            raise PolicyError("oversize", "probe input is too large")
        cleaned.append({"interface": call["interface"], "input": call["input"]})
    return {"action": "probe", "invocations": cleaned}


def _plan_proposal(proposal: dict) -> dict:
    if set(proposal) != {"action", "shape", "children"}:
        raise PolicyError("malformed", "plan carries only action+shape+children")
    from settlement.team import SHAPES
    if proposal["shape"] not in SHAPES:
        raise PolicyError("malformed", f"unsupported shape {proposal['shape']!r}")
    if not isinstance(proposal["children"], list) or not proposal["children"]:
        raise PolicyError("malformed", "plan needs a non-empty child list")
    return {"action": "plan", "shape": proposal["shape"],
            "children": proposal["children"]}


def _rework_proposal(proposal: dict) -> dict:
    if set(proposal) != {"action", "rework"}:
        raise PolicyError("malformed", "rework carries only action+rework")
    names = proposal["rework"]
    if not isinstance(names, list) or not names \
            or any(not isinstance(n, str) or not n for n in names):
        raise PolicyError("malformed", "rework must name at least one child")
    return {"action": "rework", "rework": list(names)}


def _terminal_proposal(proposal: dict, action: str) -> dict:
    if set(proposal) != {"action", "reason"}:
        raise PolicyError("malformed", f"{action} carries only action+reason")
    return {"action": action, "reason": _bounded_reason(proposal["reason"])}


def validate_response(response: Any, *, decision_id: str, package_digest: str,
                      source_digest: str, plan_revision: int, phase: str,
                      allowed: list[str]) -> dict:
    if not isinstance(response, dict):
        raise PolicyError("malformed", "response must be a JSON object")
    if response.get("profile") != PROFILE \
            or response.get("profile_version") != PROFILE_VERSION:
        raise PolicyError("malformed", "response profile mismatch")
    _check_echo(response, decision_id=decision_id,
                package_digest=package_digest, source_digest=source_digest,
                plan_revision=plan_revision, phase=phase)
    if set(response) != {"profile", "profile_version", "decision_id",
                         "package_digest", "source_digest", "plan_revision",
                         "phase", "proposal", "state"}:
        raise PolicyError("malformed", "response carries no extra fields")
    proposal = response.get("proposal")
    if not isinstance(proposal, dict):
        raise PolicyError("malformed", "proposal must be an object")
    action = proposal.get("action")
    if action not in ACTIONS:
        raise PolicyError("unknown-action", f"unknown action {action!r}")
    if action not in allowed or action not in ALLOWED.get(phase, ()):
        raise PolicyError("malformed", f"action {action!r} is not allowed {phase}")
    if action == "probe":
        clean = _probe_proposal(proposal)
    elif action == "plan":
        clean = _plan_proposal(proposal)
    elif action == "rework":
        clean = _rework_proposal(proposal)
    else:
        clean = _terminal_proposal(proposal, action)
    return {"action": action, "proposal": clean,
            "state": _check_state(response.get("state"))}


def parse_response_bytes(raw: bytes, **echo: Any) -> dict:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise PolicyError("oversize", "response exceeds the message limit")
    try:
        response = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise PolicyError("malformed", "response is not UTF-8 JSON")
    return validate_response(response, **echo)


def next_phase(phase: str, action: str) -> str:
    if action == "probe" and phase == PHASE_PRE_PLAN:
        return PHASE_POST_PROBE
    if action == "probe" and phase == PHASE_POST_FAIL_JOIN:
        return PHASE_POST_FAIL_PROBE
    return PHASE_TERMINAL
