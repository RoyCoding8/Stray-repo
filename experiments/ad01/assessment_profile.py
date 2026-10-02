"""M1 shared action dispatcher: one runtime meaning, declared profile differences.

The same STEP bytes execute through policy_step.run_policy_step in every
profile. Resulting actions route here, to the same effect owners the
operational path uses: broker-validated model-inference operations,
method_exec child execution, and the seeds repertoire. Profiles change only
permissions, visibility, budgets and destinations, never what an action means.

policy_assess._effect stays untouched as the labeled legacy sealed profile
for frozen studies. New qualification uses dispatch in this module.
Method owners receive the packet-stripped task, so sealed keys never reach
child execution through the task route either.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from settlement import broker

from . import method_exec, packet, policy_step, seeds

DEVELOPMENT = "development"
ASSESSMENT = "assessment"
ASSESSMENT_RESTRICTED = "assessment-restricted"
AUDIT = "audit"

LEGACY_SEALED_PROFILE = ASSESSMENT_RESTRICTED

PRODUCTION = "production"
ASSESSMENT_LOCAL = "assessment-local"

_FAMILY_TAG = {"software": "sw", "graph": "gr"}


def default_repertoire() -> tuple:
    return tuple(item["capability_id"] for item in seeds.SEED_CAPABILITIES)


@dataclass(frozen=True)
class Profile:
    name: str
    allow_model: bool
    allow_revision_bind: bool
    allow_nested_qualify: bool
    max_qualify_depth: int
    op_prefix: str
    destination: str
    query_ceiling: int
    model_token_ceiling: int
    repertoire: tuple


def _profiles() -> dict:
    repertoire = default_repertoire()
    return {
        DEVELOPMENT: Profile(DEVELOPMENT, True, True, True, 1,
                              "m1-dev", PRODUCTION, 16, 2048, repertoire),
        ASSESSMENT: Profile(ASSESSMENT, True, False, False, 1,
                            "m1-assess", ASSESSMENT_LOCAL, 16, 2048,
                            repertoire),
        ASSESSMENT_RESTRICTED: Profile(ASSESSMENT_RESTRICTED, False, False,
                                       False, 0, "m1-legacy",
                                       ASSESSMENT_LOCAL, 16, 2048,
                                       repertoire),
        AUDIT: Profile(AUDIT, False, False, False, 0, "m1-audit",
                       ASSESSMENT_LOCAL, 16, 2048, repertoire),
    }


PROFILES = _profiles()


def make_ctx(*, candidate_digest: str, scope: dict, session: str,
             qualify_depth: int = 0, remaining: dict | None = None,
             visible_observation_ids=(), trusted: bool = False) -> dict:
    if not isinstance(candidate_digest, str) or not candidate_digest:
        raise ValueError("ctx needs a candidate digest")
    if not isinstance(scope, dict) or "family" not in scope \
            or "task_ids" not in scope:
        raise ValueError("ctx scope needs family plus task ids")
    if not isinstance(session, str) or not session:
        raise ValueError("ctx needs a session namespace")
    if type(qualify_depth) is not int or qualify_depth < 0:
        raise ValueError("qualify_depth must be a nonnegative integer")
    return {"candidate_digest": candidate_digest, "scope": dict(scope),
            "task_ids": list(scope["task_ids"]), "session": session,
            "qualify_depth": qualify_depth,
            "remaining": dict(remaining or {"queries": 16,
                                            "model_calls": 2}),
            "visible_observation_ids": tuple(visible_observation_ids or ()),
            "trusted": bool(trusted)}


def _refused(profile: Profile, kind: str, reason: str,
             source_digest: str = "", scope: dict | None = None) -> dict:
    return {"profile": profile.name, "kind": kind, "accepted": False,
            "reason": reason, "candidate": None, "queries": 0,
            "model_calls": 0, "wall_ms": 0, "selected_identity": None,
            "owner": "none", "destination": profile.destination,
            "source_digest": source_digest, "scope": dict(scope or {})}


def _elapsed_ms(started: int) -> int:
    import math
    return max(1, int(math.ceil((time.perf_counter_ns() - started)
                                / 1_000_000)))


def _source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def build_model_operation(*, profile_name: str, action: dict, model: str,
                          session: str, step_index: int,
                          reasoning_effort: str = "low") -> dict:
    profile = PROFILES[profile_name]
    inputs = dict(action.get("inputs") or {})
    prompt = inputs.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("model request needs a prompt")
    if len(prompt.encode()) > policy_step.MODEL_PROMPT_LIMIT_CHARS:
        raise ValueError("model prompt exceeds %d chars"
                         % policy_step.MODEL_PROMPT_LIMIT_CHARS)
    tokens = inputs.get("max_output_tokens", 256)
    if type(tokens) is not int or tokens <= 0 or tokens > 2048:
        raise ValueError("max_output_tokens must be 1..2048")
    if tokens > profile.model_token_ceiling:
        raise ValueError("model request exceeds %s token ceiling %d"
                         % (profile.name, profile.model_token_ceiling))
    payload = broker.validate_effect(
        broker.MODEL_INFERENCE,
        {"model": model, "messages": [{"role": "user", "content": prompt}],
         "max_output_tokens": tokens, "deadline_ms": 300_000,
         "reasoning_effort": reasoning_effort})
    return {"operation_id": "%s-%s-model-k%d" % (profile.op_prefix,
                                                 session, step_index),
            "effect": broker.MODEL_INFERENCE, "payload": payload,
            "profile": profile.name, "destination": profile.destination}


def _resolve_method(task: dict, inputs: dict) -> tuple:
    if "candidate" in inputs:
        return None, 0, 0, 0, None, "none", (
            "policy-supplied candidate is not a task outcome")
    max_queries = inputs.get("max_queries", 16)
    if type(max_queries) is not int or max_queries < 0:
        return None, 0, 0, 0, None, "none", (
            "max_queries must be a nonnegative integer")
    exposed = packet.strip_task(task)
    source = inputs.get("method_source") or inputs.get("source")
    started = time.perf_counter_ns()
    if isinstance(source, str) and source:
        entry = inputs.get("entry", "ENTRY")
        member = {"method_source": source, "entry": entry}
        try:
            method_exec.verify_member(member)
            result = method_exec.run_member_out_of_process(
                member, exposed, max_queries=max_queries)
        except Exception as exc:
            return None, 0, 0, 0, None, "method_exec", str(exc)
        identity = "inline:%s:%s" % (entry, _source_digest(source)[:12])
        return (result.get("candidate"), int(result.get("queries", 0)), 0,
                _elapsed_ms(started), identity,
                "method_exec.run_member_out_of_process", None)
    method_id = inputs.get("method_id")
    if method_id is None:
        tag = _FAMILY_TAG.get(task.get("family", ""), "")
        method_id = "seed-%s-greedy" % tag
    capability = next((item for item in seeds.SEED_CAPABILITIES
                       if item["capability_id"] == method_id), None)
    if capability is None or capability["family"] != task.get("family") \
            or method_id not in default_repertoire():
        return None, 0, 0, 0, None, "none", ("unknown task method %r"
                                          % (inputs.get("method_id"),))
    try:
        result = seeds.run_seed(capability, exposed,
                                max_queries=max_queries)
    except Exception as exc:
        return None, 0, 0, 0, None, "seeds", str(exc)
    return (result.get("candidate"), int(result.get("queries", 0)), 0,
            _elapsed_ms(started), method_id, "seeds.run_seed", None)


def _check_budget(profile: Profile, action: dict, ctx: dict) -> str | None:
    requested = dict(action.get("requested_resources") or {})
    remaining = dict(ctx["remaining"])
    for key in ("queries", "model_calls"):
        want = requested.get(key, 0)
        if type(want) is not int or want < 0:
            return "requested resource %s is invalid" % key
        if want > int(remaining.get(key, 0)):
            return "%s budget exhausted under %s" % (key, profile.name)
    queries = dict(action.get("inputs") or {}).get("max_queries")
    if type(queries) is int and queries > profile.query_ceiling:
        return "query request exceeds %s ceiling %d" % (
            profile.name, profile.query_ceiling)
    return None


def dispatch(*, profile_name: str, record: dict, task: dict,
             action: dict, ctx: dict) -> dict:
    try:
        profile = PROFILES[profile_name]
    except KeyError:
        raise ValueError("unknown executor profile %r" % (profile_name,))
    artifact = policy_step.verify_policy_record(record)
    source_digest = artifact["source_digest"]
    policy_step.validate_action(action)
    kind = action["kind"]
    scope = ctx["scope"]
    if ctx["candidate_digest"] != source_digest:
        return _refused(profile, kind, "source identity is not frozen",
                        source_digest, scope)
    if task.get("family") != scope.get("family") \
            or task.get("task_id") not in list(scope.get("task_ids") or []):
        return _refused(profile, kind, "task is outside assessed scope",
                        source_digest, scope)
    if action.get("target") != task.get("task_id"):
        return _refused(profile, kind, "action target does not match task",
                        source_digest, scope)
    unseen = [ref for ref in action.get("evidence_refs") or []
              if ref not in ctx["visible_observation_ids"]]
    if unseen:
        return _refused(profile, kind, "reference %r is not visible"
                        " in this profile" % (unseen[0],),
                        source_digest, scope)
    if dict(action.get("inputs") or {}).get("destination") == PRODUCTION \
            and profile.destination != PRODUCTION:
        return _refused(profile, kind, "production writes are refused"
                        " under %s" % profile.name, source_digest, scope)
    over = _check_budget(profile, action, ctx)
    if over is not None:
        return _refused(profile, kind, over, source_digest, scope)
    if kind in ("diagnose", "stop"):
        effect = _refused(profile, kind, "", source_digest, scope)
        return {**effect, "accepted": True, "reason": "no task effect"}
    if kind in ("construct_method", "use_method"):
        candidate, queries, _calls, wall_ms, identity, owner, failure = \
            _resolve_method(task, dict(action.get("inputs") or {}))
        if failure is not None:
            return _refused(profile, kind, failure, source_digest, scope)
        return {"profile": profile.name, "kind": kind, "accepted": True,
                "reason": "", "candidate": candidate, "queries": queries,
                "model_calls": 0, "wall_ms": wall_ms,
                "selected_identity": identity, "owner": owner,
                "destination": profile.destination,
                "source_digest": source_digest, "scope": dict(scope)}
    if kind == "request_model":
        inputs = dict(action.get("inputs") or {})
        prompt = inputs.get("prompt", "")
        tokens = inputs.get("max_output_tokens", 256)
        if not isinstance(prompt, str) or not prompt.strip():
            return _refused(profile, kind, "model request needs a prompt",
                            source_digest, scope)
        if len(prompt.encode()) > policy_step.MODEL_PROMPT_LIMIT_CHARS \
                or type(tokens) is not int or tokens <= 0 or tokens > 2048:
            return _refused(profile, kind, "model request is malformed",
                            source_digest, scope)
        if not profile.allow_model:
            return _refused(profile, kind, "model execution is refused"
                            " under %s: declared profile difference"
                            % profile.name, source_digest, scope)
        operation = build_model_operation(
            profile_name=profile.name, action=action, model="policy-request",
            session=ctx["session"], step_index=ctx["qualify_depth"])
        return {"profile": profile.name, "kind": kind, "accepted": True,
                "reason": "operation constructed; dispatch owns sending",
                "candidate": None, "queries": 0, "model_calls": 0,
                "wall_ms": 0, "selected_identity": operation["operation_id"],
                "owner": "broker.model-inference",
                "destination": profile.destination,
                "source_digest": source_digest, "scope": dict(scope),
                "operation": operation}
    if kind == "propose_revision":
        inputs = dict(action.get("inputs") or {})
        if inputs.get("request") == "assessment":
            if not profile.allow_nested_qualify or \
                    ctx["qualify_depth"] + 1 > profile.max_qualify_depth:
                return _refused(profile, kind, "nested qualification"
                                " exceeds depth bound %d under %s"
                                % (profile.max_qualify_depth,
                                   profile.name), source_digest, scope)
            depth = ctx["qualify_depth"] + 1
        else:
            depth = ctx["qualify_depth"]
        staged = {"parent_digest": source_digest,
                  "scope": dict(scope), "depth": depth,
                  "motivation": inputs.get("motivation", ""),
                  "destination": profile.destination,
                  "profile": profile.name}
        return {"profile": profile.name, "kind": kind, "accepted": True,
                "reason": "staged locally; only trusted qualification binds",
                "candidate": None, "queries": 0, "model_calls": 0,
                "wall_ms": 0, "selected_identity": None,
                "owner": "assessment_profile.stage",
                "destination": profile.destination,
                "source_digest": source_digest, "scope": dict(scope),
                "staged": staged, "bound": False}
    return _refused(profile, kind, "unknown policy action kind",
                    source_digest, scope)


def bind_revision(*, profile_name: str, staged: dict,
                  candidate_source: str, scope: dict,
                  trusted: bool) -> dict:
    try:
        profile = PROFILES[profile_name]
    except KeyError:
        raise ValueError("unknown executor profile %r" % (profile_name,))
    if not profile.allow_revision_bind:
        return {"bound": False,
                "reason": "binding is refused under %s" % profile.name}
    if not trusted:
        return {"bound": False,
                "reason": "binding needs trusted qualification"}
    if _source_digest(candidate_source) != staged.get("parent_digest"):
        return {"bound": False,
                "reason": "bind covers only the assessed bytes"}
    if dict(scope) != dict(staged.get("scope") or {}):
        return {"bound": False,
                "reason": "bind covers only the assessed scope"}
    return {"bound": True, "profile": profile.name,
            "candidate_digest": staged["parent_digest"],
            "scope": dict(scope),
            "parent_digest": staged["parent_digest"]}
