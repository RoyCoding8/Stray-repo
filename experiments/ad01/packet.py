"""AD01 materialized packets: one typed structure per decision.

Two decisions share this module. The propose/admit decision consumes a
decision packet (charter, visible opportunities, curriculum item,
observations, retained members, remaining budgets, boundary). The
construction decision consumes a construction packet (task content, public
operations, candidate shape, preservation objective, oracle meaning,
verbatim diagnostics, budgets, entry rules). The learner renderer, the
proposal validator, the construction renderer, the response parser and the
executor all read these shapes, so renderer, parser and executor agree by
construction instead of by paraphrase.
"""

from __future__ import annotations

import json

PACKET_VERSION = "ad01-packet-v1"

REQUIRED_RESPONSE = {
    "format": "one JSON object",
    "fields": ["basis_references", "question", "next_action",
               "requested_resources"],
    "next_action": {"kind": "diagnostic|development|stop",
                    "diagnostic": "software|graph",
                    "task_id": ("curriculum_item when not null, else "
                                "one of visible_opportunities"),
                    "max_queries": "positive int"},
    "requested_resources": (
        "object mapping resource name to nonnegative integer "
        "amount, e.g. {\"queries\": 3}"),
}

RESPONSE_CONTRACT = {
    "format": "one JSON object",
    "fields": ["entry", "notes"],
}


SEALED_LABELS = frozenset({"hidden", "evaluator"})

SEALED_KEYS = frozenset({
    "hidden_answer", "sealed_answer", "judgment", "sealed_judgment",
    "blind_key", "assessment_answer", "use_answers",
})

# A held-out value shorter than this is not evidence of a leak. A boolean
# flag or a two-character op name is a substring of ordinary text, so
# matching on it would refuse every arm rather than the leaking one.
MIN_HELD_OUT_CHARS = 4


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def content_digest(value) -> str:
    import hashlib
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def with_held_out_canary(task: dict, marker: str) -> dict:
    """A copy of `task` carrying `marker` where its answer really is.

    The point of a canary is that it is findable, so it goes where a
    leaked answer would actually sit: the private side of the task, which
    `public_task_view` drops and a leak check reads. A marker in a field
    the public view keeps would prove nothing, and one in a field no task
    has would never be found at all.
    """
    task = dict(task or {})
    if not str(marker):
        raise ValueError("a canary needs a marker")
    return {**task, "witness": {"canary": str(marker)}}

# `seed` was in this allowlist and was a second copy of a value the task
# id already gives away: `task_id` names the world, the kind and the
# index, and `splits._ad01_seed` is arithmetic on those three. Dropping
# the field deletes a redundant authority and nothing else. The hole it
# appeared to close is still open, and `template` still carries the fault
# name verbatim. See reports/workstreams/ad01-leak-assessment.md.
PUBLIC_TASK_FIELDS = frozenset({
    "family", "task_id", "template", "split", "world", "kind",
    "ops", "vertices", "edges", "instrument", "max_queries", "remaining",
    "observed", "hypothesis_class", "instruction", "committed",
    "public_ops", "public_observations", "examples", "spec",
})


def _is_sealed_observation(obs: dict) -> bool:
    if not isinstance(obs, dict):
        return False
    if str(obs.get("access_label", "")) in SEALED_LABELS:
        return True
    for key in SEALED_KEYS:
        if obs.get(key) not in (None, "", [], {}):
            return True
    detail = obs.get("detail")
    if isinstance(detail, dict):
        if str(detail.get("access_label", "")) in SEALED_LABELS:
            return True
        for key in SEALED_KEYS:
            if detail.get(key) not in (None, "", [], {}):
                return True
    return False


def _strip_value(value):
    if isinstance(value, dict):
        return {k: _strip_value(v) for k, v in value.items()
                if k not in SEALED_KEYS and k != "access_label"}
    if isinstance(value, list):
        return [_strip_value(v) for v in value]
    return value


def strip_task(task: dict | None) -> dict:
    return public_task_view(task)


def public_task_view(task: dict | None) -> dict:
    return {k: _strip_value(v) for k, v in dict(task or {}).items()
            if k in PUBLIC_TASK_FIELDS}


def method_task_view(task: dict | None) -> dict:
    """Task input for a method executor, which is the task's own oracle.

    A method must see the witness it is scored against; a policy must not.
    Both views drop sealed generic keys, but only the policy view is an
    allowlist.
    """
    return {k: _strip_value(v) for k, v in dict(task or {}).items()
            if k not in SEALED_KEYS and k != "access_label"}


def held_out_values(task: dict | None) -> list:
    """Every string the public view holds privately, and could not be read.

    The public view is an allowlist, so the private side is whatever it
    does not carry. A name list would have to be right about both
    families and would be silently wrong about the third; the difference
    between the two views cannot be. A value the public view already
    shows is then dropped even if it is on the private side too: this
    generator derives the fault name from the template, so the fault
    string is a substring of a public field and a check that looked for
    it would fire on every arm, including one carrying no experience.
    """
    task = dict(task or {})
    public = canonical(public_task_view(task))
    values = []
    for key, value in task.items():
        if key in PUBLIC_TASK_FIELDS:
            continue
        values.extend(_string_values(value))
    seen, unique = set(), []
    for value in values:
        if len(value) < MIN_HELD_OUT_CHARS or value in seen:
            continue
        if value in public:
            continue
        seen.add(value)
        unique.append(value)
    return sorted(unique)


def _string_values(value) -> list:
    """Every string under `value`, whatever the keys are called.

    The whole private side is walked, not only its sealed keys. A leak
    check that walked selectively would miss a canary or a planted
    answer filed under an ordinary name, which is the most likely way
    for one to arrive.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found = []
        for item in value.values():
            found.extend(_string_values(item))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(_string_values(item))
        return found
    return []


def leaked_answers(text: str, task: dict | None) -> list:
    """Held-out values a rendered arm quotes verbatim."""
    body = text or ""
    return [value for value in held_out_values(task) if value in body]


def _dev_task_ids() -> set:
    from . import worlds
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    return {t for w in membership.values()
            for d in w.get("dev", {}).values() for t in d}


def visible_context(*, observations: list, basis_references: list,
                    dev_ids: set | None = None) -> dict:
    by_id = {o.get("observation_id"): o for o in observations or []}
    dev = set(dev_ids) if dev_ids is not None else _dev_task_ids()
    for ref in basis_references or []:
        obs = by_id.get(ref)
        if obs is None:
            continue
        if _is_sealed_observation(obs):
            raise ValueError("sealed assessment reference %r cannot drive"
                             " construction" % (ref,))
        task_id = obs.get("task_id", "")
        if task_id not in dev:
            raise ValueError("protected-use reference %r cannot drive"
                             " development" % (ref,))
    visible = [o for o in observations or []
               if not _is_sealed_observation(o)]
    return {"observations": visible}


def project_observations(observations: list) -> list:
    cleaned = [o for o in observations or []
               if not _is_sealed_observation(o)]
    return [
        {"observation_id": o.get("observation_id"),
         "task_id": o.get("task_id"),
         "capability_id": o.get("capability_id"),
         "verdict": o.get("verdict"),
         "detail": _strip_value(o.get("detail"))}
        for o in cleaned]


def project_retained(retained: list) -> list:
    return [
        {"capability_id": m.get("capability_id"),
         "family": (m.get("scope") or {}).get("family")
                   or m.get("family"),
         "qualified_on": m.get("qualified_on", "")}
        for m in retained or []]


def decision_packet(*, charter: dict | None, visible: list,
                    experience: dict | None, retained: list,
                    remaining: dict | None, curriculum: str | None,
                    boundary: dict | None) -> dict:
    return {
        "packet_version": PACKET_VERSION,
        "charter": {"objective": (charter or {}).get("objective", ""),
                    "freeze_id": (charter or {}).get("freeze_id", "")},
        "visible_opportunities": sorted(visible or []),
        "curriculum_item": curriculum,
        "observations": project_observations(
            (experience or {}).get("observations", [])),
        "retained": project_retained(retained),
        "remaining": dict(remaining or {}),
        "boundary": dict(boundary) if boundary is not None else None,
        "required_response": dict(REQUIRED_RESPONSE),
    }


def entry_rules() -> dict:
    from . import method_exec
    return method_exec.entry_contract()


def candidate_shape(family: str) -> dict:
    if family == "graph":
        return {
            "required_keys": ["family", "task_id", "vertices", "edges"],
            "family_value": "graph",
            "legality": ("candidate vertices/edges must form a legal "
                         "subgraph of the task holding the witness"),
        }
    return {
        "required_keys": ["family", "task_id", "ops", "witness"],
        "family_value": "software",
        "legality": ("candidate ops must be a legal deletion of the task "
                     "ops holding the witness observation"),
    }


def preservation_objective(family: str) -> dict:
    from experiments.representation import checkers
    reasons = sorted(checkers.GRAPH_REASONS if family == "graph"
                     else checkers.SOFTWARE_REASONS)
    return {
        "goal": ("a strictly smaller candidate that keeps the witness; "
                 "the byte-identical incumbent is valid but not an "
                 "improvement"),
        "verdicts": [checkers.PRESERVED, checkers.NOT_PRESERVED,
                     checkers.INVALID, checkers.UNKNOWN],
        "verdict_report": {"verdict": "one of the four verdicts",
                           "measure": "candidate size",
                           "initial_measure": "task size",
                           "reason": "one of the reason codes below"},
        "reason_codes": reasons,
    }


def public_operations(family: str) -> dict:
    from . import method_exec
    contract = method_exec.child_contract()
    return {
        name: {"signature": spec["signature"], "returns": spec["returns"],
               "origin": spec.get("origin", "")}
        for name, spec in contract["callables"].items()
    }


def construction_packet(*, task: dict | None, experience: dict | None,
                        budget: dict | None,
                        prior_failure: dict | None) -> dict:
    task = strip_task(dict(task or {}))
    family = task.get("family", "software")
    return {
        "packet_version": PACKET_VERSION,
        "family": family,
        "task": task,
        "public_operations": public_operations(family),
        "candidate_shape": candidate_shape(family),
        "example_candidate": task,
        "result_envelope": entry_rules()["result_envelope"],
        "preservation_objective": preservation_objective(family),
        "diagnostics": {
            "observations": project_observations(
                (experience or {}).get("observations", [])),
            "prior_failure": _strip_value(prior_failure)
            if prior_failure is not None else None,
        },
        "budgets": dict(budget or {}),
        "entry_rules": entry_rules(),
        "response_contract": dict(RESPONSE_CONTRACT),
    }


def _witness_line(task: dict, family: str) -> str:
    if family == "graph":
        return ("the candidate keeps the witness: a non-bipartite "
                "subgraph of the task.")
    witness = (task.get("witness") or {}).get("observation", "?")
    return ("the candidate keeps witness observation %s: it must stay "
            "a legal deletion holding that observation." % witness)


def render_construction_prompt(packet: dict) -> str:
    family = packet.get("family", "software")
    rules = packet["entry_rules"]
    objective = packet["preservation_objective"]
    lines = [
        "Write one python method that searches explanatory examples.",
        "Family: %s." % family,
        "Task (authoritative content, not a reference): %s" % json.dumps(
            packet.get("task", {}), sort_keys=True),
        "Public operations: %s" % json.dumps(
            packet.get("public_operations", {}), sort_keys=True),
        "Candidate shape: %s" % json.dumps(
            packet.get("candidate_shape", {}), sort_keys=True),
        "Shape example (the incumbent task itself, a valid candidate): %s"
        % json.dumps(packet.get("example_candidate", {}),
                     sort_keys=True),
        "Preservation objective: %s %s Verdicts %s with reasons %s."
        % (objective["goal"], _witness_line(packet.get("task", {}),
                                            family),
           "/".join(objective["verdicts"]),
           ",".join(objective["reason_codes"])),
        "Entry: %s with %s; exactly one module-level function carries "
        "the entry name." % (rules["params"], rules["param_rule"]),
        "The word import anywhere in the entry source fails validation, "
        "so use no imports, no dunder access, no IO. Precisely: %s; %s; "
        "calls to %s fail validation."
        % (rules["forbidden"]["import_statements"],
           rules["forbidden"]["dunder"],
           ",".join(rules["forbidden"]["calls"])),
        "Source must be %s." % rules["source_rule"],
        "Return envelope: %s." % rules["result_envelope"]["rule"],
        "Reply with exactly one JSON object and nothing else, shaped "
        '{"entry": "<complete python source>", "notes": "<sentence>"}.',
        "Budget: %s." % json.dumps(packet.get("budgets", {}),
                                   sort_keys=True),
    ]
    observed = packet.get("diagnostics", {}).get("observations") or []
    if observed:
        lines.append("Prior observations: %s" % json.dumps(
            [{"task_id": o.get("task_id"), "verdict": o.get("verdict"),
              "detail": o.get("detail")}
             for o in observed[-8:]],
            sort_keys=True))
    prior = packet.get("diagnostics", {}).get("prior_failure")
    if prior is not None:
        lines.append("PRIOR FAILURE (repair it): %s" % json.dumps(
            prior, sort_keys=True))
    return "\n".join(lines)


def parse_construction_response(text: str) -> tuple:
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        lines = lines[1:] if len(lines) > 1 else []
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        payload = json.loads(body) if body else None
    except ValueError as exc:
        return None, "parse-failure: %s" % exc
    if not isinstance(payload, dict):
        return None, "parse-failure: response is not an object"
    source = payload.get("entry")
    if not isinstance(source, str) or not source.strip():
        return None, "parse-failure: missing entry source"
    return source, ""
