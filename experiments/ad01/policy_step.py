"""AD01 policy step ABI: versioned JSON step contract.

M0 scaffold pins the version plus field shapes before any executor
exists. M2 adds bounded child execution. Lanes import the version
constant instead of restating the name.

This module also carries the STEP half of the translation onto
`policy_action`, the one action contract every representation shares.
A STEP policy and a contract policy must produce the same action type,
or they cannot be compared; see `STEP_KIND_TO_CONTRACT`.
"""

from __future__ import annotations

from . import policy_action

POLICY_STEP_VERSION = "ad01-policy-step-v1"

VIEW_REQUIRED = (
    "task_content",
    "observations",
    "open_questions",
    "last_result",
    "eligible_methods",
    "remaining",
    "contract_versions",
)

ACTION_KINDS = (
    "diagnose",
    "construct_method",
    "use_method",
    "request_model",
    "propose_revision",
    "stop",
)

ACTION_REQUIRED = (
    "kind",
    "target",
    "inputs",
    "evidence_refs",
    "requested_resources",
)

# One meaning held constant across representations. The contract wins on
# names and on count: a STEP kind that would need a seventh contract kind
# is a mis-mapping, not a reason to widen the contract.
#
# `propose_revision` and `check` are both the vocabulary's gate: the point
# at which the policy judges the current trajectory against a stated
# criterion and the judgement decides whether the run continues. The
# contract keeps the gate and drops whether what is judged is a task
# result or the policy itself, which is the abstraction the six kinds
# exist to draw.
#
# The forward map is a bijection. That is load-bearing, not incidental:
# it is why the reverse map is total, and it is asserted against both
# vocabularies rather than left to this comment.
STEP_KIND_TO_CONTRACT = {
    "diagnose": policy_action.PROBE,
    "construct_method": policy_action.CONSTRUCT,
    "use_method": policy_action.USE,
    "request_model": policy_action.OBSERVE,
    "propose_revision": policy_action.CHECK,
    "stop": policy_action.STOP,
}

CONTRACT_KIND_TO_STEP = {contract_kind: step_kind
                         for step_kind, contract_kind
                         in STEP_KIND_TO_CONTRACT.items()}

STATE_LIMIT_BYTES = 4096


def _contract_fields(action: dict) -> dict:
    return {"kind": action["kind"], "target": action["target"],
            "inputs": dict(action["inputs"]),
            "evidence_refs": list(action["evidence_refs"]),
            "requested_resources": dict(action["requested_resources"])}


def as_contract_action(action: dict) -> dict:
    """A STEP action restated in the shared contract's vocabulary.

    The STEP ABI admits extra fields, so a field the contract does not
    name would otherwise be dropped here and the action would pass as
    translated while carrying less than the policy asked for. Refused at
    this boundary instead, using the contract's exception so a caller
    translating in either direction catches one type.
    """
    validate_action(action)
    kind = action["kind"]
    if kind not in STEP_KIND_TO_CONTRACT:
        raise policy_action.ActionRefused(
            "STEP kind %r has no shared-contract equivalent" % (kind,))
    extra = sorted(set(action) - set(ACTION_REQUIRED))
    if extra:
        raise policy_action.ActionRefused(
            "unknown action fields %s" % extra)
    contract = _contract_fields(action)
    contract["kind"] = STEP_KIND_TO_CONTRACT[kind]
    return contract


def as_step_action(shared: dict) -> dict:
    """A shared-contract action restated in the STEP vocabulary.

    Reverse translation of a bijection. A contract action reaches here
    already carrying a kind the STEP ABI validates, so the STEP rules
    are re-run rather than assumed.
    """
    contract = policy_action.parse_action(shared)
    translated = contract.as_dict()
    translated["kind"] = CONTRACT_KIND_TO_STEP[contract.kind]
    return validate_action(translated)


def vocabulary_coverage() -> dict:
    """Whether either vocabulary has outgrown the table.

    Both empty is the only correct answer for a shared contract: a
    contract arm's action that no STEP action can express, or a STEP
    arm's action with nowhere to go, is a comparability gap that reads
    as agreement until a study depends on it.
    """
    return {
        "step_unmapped": sorted(set(ACTION_KINDS) - set(STEP_KIND_TO_CONTRACT)),
        "contract_unmapped": sorted(
            set(policy_action.ACTION_KINDS) - set(CONTRACT_KIND_TO_STEP)),
        "step_kinds": sorted(STEP_KIND_TO_CONTRACT),
        "contract_kinds": sorted(CONTRACT_KIND_TO_STEP),
    }


def validate_view(view: dict) -> dict:
    missing = [k for k in VIEW_REQUIRED if k not in view]
    if missing:
        raise ValueError("policy view missing: %s" % ", ".join(sorted(missing)))
    return view


def validate_state(state: dict) -> dict:
    import json

    raw = json.dumps(state, sort_keys=True)
    if len(raw.encode()) > STATE_LIMIT_BYTES:
        raise ValueError("policy state exceeds %d bytes" % STATE_LIMIT_BYTES)
    return state


def validate_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise ValueError("policy action must be an object")
    missing = [k for k in ACTION_REQUIRED if k not in action]
    if missing:
        raise ValueError("policy action missing: %s" % ", ".join(sorted(missing)))
    if action["kind"] not in ACTION_KINDS:
        raise ValueError("unknown policy action kind: %r" % (action.get("kind"),))
    target = action.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError("policy action needs a string target")
    if not isinstance(action.get("inputs"), dict):
        raise ValueError("policy action inputs must be an object")
    refs = action.get("evidence_refs")
    if not isinstance(refs, list) or any(
            not isinstance(r, str) for r in refs):
        raise ValueError("policy action evidence_refs must hold strings")
    resources = action.get("requested_resources")
    if not isinstance(resources, dict) or any(
            not isinstance(k, str) or type(v) is not int or v < 0
            for k, v in resources.items()):
        raise ValueError("policy action requested_resources must hold"
                         " nonnegative integers")
    return action


STEP_ENTRY = "STEP"


def compile_step(source: str, *, origin: str = "<policy>") -> object:
    """Return a bounded STEP callable for legacy fixture callers.

    Source is never compiled in this process.  The returned callable keeps
    the old fixture shape, but invokes the existing child executor for every
    decision.  Production callers should pass the source bytes to
    ``trajectory.run_use(policy_source=...)`` so durable use accounting can
    include the policy operation.
    """
    # ``origin`` remains a diagnostic label for callers that still use the
    # compatibility entry point.  It is deliberately not a trust claim about
    # the supplied source; all such source runs under the child boundary.
    del origin
    record = make_policy_artifact(source, origin="fixture-stand-in")
    verify_policy_record(record)
    return BoundedPolicy(record)

POLICY_ORIGINS = (
    "authored-control",
    "model-acquired",
    "fixture-stand-in",
)

STEP_TIMEOUT_MS = 10_000
STEP_CPU_SECONDS = 10
STEP_MAX_OUTPUT_BYTES = 65_536
VIEW_LIMIT_BYTES = 1_048_576
POLICY_MAX_STEPS = 6
MODEL_PROMPT_LIMIT_CHARS = 4096
MODEL_RESPONSE_VIEW_CHARS = 4000

ARTIFACT_REQUIRED = (
    "kind",
    "source_digest",
    "entry",
    "abi",
    "origin",
)


class BoundedPolicy:
    """Legacy callable facade over a verified source policy artifact."""

    def __init__(self, record: dict):
        self.record = dict(record)
        verify_policy_record(self.record)

    def run(self, view: dict, state: dict, **execution) -> dict:
        if "contract_versions" not in view:
            from . import method_exec, packet
            view = dict(view)
            view["contract_versions"] = {
                "policy_step": POLICY_STEP_VERSION,
                "child": method_exec.CHILD_CONTRACT_VERSION,
                "packet": packet.PACKET_VERSION,
            }
        return run_policy_step(self.record, view, state, **execution)

    def __call__(self, view: dict, state: dict) -> dict:
        try:
            result = self.run(view, state)
        except Exception as exc:
            # Historical fixture callers expect a ValueError for an invalid
            # decision.  The production path catches the richer child error
            # before it reaches this facade.
            raise ValueError(str(exc)) from exc
        return {"action": result["action"], "state": result["state"]}


def step_limits() -> dict:
    return {"timeout_ms": STEP_TIMEOUT_MS,
            "cpu_seconds": STEP_CPU_SECONDS,
            "max_output_bytes": STEP_MAX_OUTPUT_BYTES}


def materialize_view(*, task: dict, observations: list,
                     open_questions: list, last_result,
                     eligible_methods: list,
                     remaining: dict) -> dict:
    from . import method_exec
    from . import packet as _packet
    view = {
        "task_content": _packet.strip_task(task),
        "observations": _packet.project_observations(observations),
        "open_questions": list(open_questions or []),
        "last_result": last_result,
        "eligible_methods": list(eligible_methods or []),
        "remaining": dict(remaining or {}),
        "contract_versions": {
            "policy_step": POLICY_STEP_VERSION,
            "child": method_exec.CHILD_CONTRACT_VERSION,
            "packet": _packet.PACKET_VERSION,
        },
    }
    return validate_view(view)


def validate_step_result(result: dict) -> dict:
    if not isinstance(result, dict) or "action" not in result \
            or "state" not in result:
        raise ValueError("policy step must return {action, state}")
    if not isinstance(result["state"], dict):
        raise ValueError("policy state must be a JSON object")
    validate_action(result["action"])
    validate_state(result["state"])
    return result


def make_policy_artifact(source: str, *, origin: str,
                         parent_digest: str | None = None,
                         applicability: dict | None = None,
                         dependencies: list | None = None,
                         instruments: list | None = None) -> dict:
    import hashlib
    if origin not in POLICY_ORIGINS:
        raise ValueError("unknown policy origin: %r" % (origin,))
    if not isinstance(source, str) or not source.strip():
        raise ValueError("policy artifact needs source bytes")
    return {
        "artifact": {
            "kind": "learning-policy",
            "source_digest": hashlib.sha256(
                source.encode("utf-8")).hexdigest(),
            "entry": STEP_ENTRY,
            "abi": POLICY_STEP_VERSION,
            "dependencies": list(dependencies or []),
            "instruments": list(instruments or []),
            "origin": origin,
            "parent_digest": parent_digest,
            "applicability": dict(applicability or {}),
        },
        "policy_source": source,
    }


def verify_policy_record(record: dict) -> dict:
    import hashlib
    if not isinstance(record, dict) or not isinstance(
            record.get("artifact"), dict) \
            or not isinstance(record.get("policy_source"), str):
        raise ValueError("policy record needs artifact plus source bytes")
    artifact = dict(record["artifact"])
    missing = [k for k in ARTIFACT_REQUIRED if k not in artifact]
    if missing:
        raise ValueError("policy artifact missing: %s"
                         % ", ".join(sorted(missing)))
    if artifact["abi"] != POLICY_STEP_VERSION:
        raise ValueError("policy artifact abi %r is not %r" % (
            artifact.get("abi"), POLICY_STEP_VERSION))
    if artifact["entry"] != STEP_ENTRY:
        raise ValueError("policy artifact entry %r is not %r" % (
            artifact.get("entry"), STEP_ENTRY))
    if artifact["origin"] not in POLICY_ORIGINS:
        raise ValueError("unknown policy origin: %r"
                         % (artifact.get("origin"),))
    source = record["policy_source"]
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != \
            artifact["source_digest"]:
        raise ValueError("policy source bytes do not match their digest")
    from . import method_exec
    method_exec.verify_step_source(source, artifact["entry"])
    return artifact


def _s09_ids(cid: str, seq: int) -> tuple:
    """The attempt a policy step belongs to, and no effect identity.

    The second element is empty, and that is the honest answer rather than a
    placeholder. This row is written when the step is persisted, which is
    before the boundary's effect has run, so there is no operation to name yet.
    The identity is set when the effect is incorporated, in
    `trajectory._s09_ensure_incorporated`, by reading the operation that
    actually ran.

    It used to return the constant `ad01-<cid>-b<seq>-effect`, which named no
    `operations` row at all. That is RF-02: both sides of the "admitted effect
    -> observation" arrow were durable rows and the only thing joining them
    was `(investigation_id, seq)`.
    """
    from .trajectory import _attempt_id
    return _attempt_id(cid, seq), ""


def load_policy_state(dsn: str | None, cid: str, seq: int):
    if dsn is None:
        return None
    from .trajectory import _s09_get
    return _s09_get(dsn, cid, seq)


def load_prior_final_state(dsn: str | None, cid: str, seq: int) -> dict:
    if dsn is None or seq <= 0:
        return {}
    row = load_policy_state(dsn, cid, seq - 1)
    if row is None:
        return {}
    transition = dict(row["state_transition"] or {})
    final = transition.get("final_state")
    return dict(final) if isinstance(final, dict) else {}


def durable_model_calls(dsn: str | None, cid: str, seq: int) -> int:
    if dsn is None:
        return 0
    from .trajectory import _read_conn
    prefix = "ad01-%s-policy-s%d-model-" % (cid, seq)
    like_construct = "%" + cid + "%-b" + str(seq) + "-%construct%"
    like_any = "%construct%"
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM operations"
            " WHERE payload->>'effect' = 'model-inference'"
            " AND (starts_with(id, %s)"
            " OR (id LIKE %s AND id LIKE %s))",
            (prefix, like_construct, like_any)).fetchone()
        conn.commit()
    return int((row or {}).get("n", 0))


def persist_step_transition(dsn: str | None, cid: str, seq: int, *,
                            views: list, results: list,
                            transitions: list, investigation: dict,
                            source_digest: str,
                            status: str = "accepted") -> None:
    if dsn is None:
        return
    import json
    from psycopg.types.json import Json
    from .trajectory import _read_conn
    if status not in ("accepted", "incorporated"):
        raise ValueError("unknown s09 status %r" % (status,))
    existing = load_policy_state(dsn, cid, seq)
    if existing is not None:
        accepted = dict(existing["accepted_action"] or {})
        if accepted.get("status") != "pending":
            return
        import json as _json
        final_state = results[-1]["state"] if results else {}
        payload = {
            "policy_input": {"initial_view": views[0] if views else {},
                              "views": views},
            "policy_output": {"results": results,
                               "source_digest": source_digest},
            "state_transition": {"transitions": transitions,
                                  "final_state": final_state},
        }
        if len(_json.dumps(payload, sort_keys=True).encode()) > VIEW_LIMIT_BYTES:
            raise ValueError("policy transition exceeds durable size cap")
        with _read_conn(dsn) as conn:
            conn.execute(
                "UPDATE s09_policy_state SET policy_input = %s,"
                " policy_output = %s, state_transition = %s,"
                " accepted_action = %s, status = %s, updated_at = now()"
                " WHERE investigation_id = %s AND seq = %s"
                " AND accepted_action->>'status' = 'pending'",
                (Json(payload["policy_input"]), Json(payload["policy_output"]),
                 Json(payload["state_transition"]), Json(investigation),
                 status, cid, seq))
            conn.commit()
        return
    attempt_id, effect_id = _s09_ids(cid, seq)
    initial = views[0] if views else {}
    final_state = results[-1]["state"] if results else {}
    payload = {
        "policy_input": {"initial_view": initial, "views": views},
        "policy_output": {"results": results,
                          "source_digest": source_digest},
        "state_transition": {"transitions": transitions,
                             "final_state": final_state},
    }
    raw = json.dumps(payload, sort_keys=True)
    if len(raw.encode()) > VIEW_LIMIT_BYTES:
        raise ValueError("policy transition exceeds durable size cap")
    with _read_conn(dsn) as conn:
        conn.execute(
            "INSERT INTO s09_policy_state"
            " (investigation_id, seq, attempt_id, effect_id,"
            " policy_input, policy_output, state_transition,"
            " accepted_action, status, provenance, driver_version)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s,"
            " %s, 's09-m2', %s)"
            " ON CONFLICT (investigation_id, seq) DO NOTHING",
            (cid, seq, attempt_id, effect_id,
             Json(payload["policy_input"]),
             Json(payload["policy_output"]),
             Json(payload["state_transition"]),
             Json(investigation), status, POLICY_STEP_VERSION))
        conn.commit()


def run_policy_step(record: dict, view: dict, state: dict, *,
                    timeout_ms: int = STEP_TIMEOUT_MS,
                    cpu_seconds: int = STEP_CPU_SECONDS,
                    max_output_bytes: int = STEP_MAX_OUTPUT_BYTES,
                    memory_bytes: int | None = None,
                    dsn: str | None = None,
                    allocation_id: str | None = None,
                    operation_id: str | None = None) -> dict:
    artifact = verify_policy_record(record)
    validate_view(view)
    validate_state(state)
    import json as _json
    raw_view = _json.dumps(view, sort_keys=True)
    if len(raw_view.encode()) > VIEW_LIMIT_BYTES:
        raise ValueError("policy view exceeds durable size cap")
    from . import method_exec
    return method_exec.run_step_out_of_process(
        record["policy_source"], view, state, entry=artifact["entry"],
        timeout_ms=timeout_ms, cpu_seconds=cpu_seconds,
        max_output_bytes=max_output_bytes, memory_bytes=memory_bytes,
        dsn=dsn, allocation_id=allocation_id,
        operation_id=operation_id)
