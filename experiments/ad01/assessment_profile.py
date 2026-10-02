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

The two profiles agree on what a learner-revision proposal is. A stage only
a binding profile could consume is a second effect class with no consumer,
so every profile without binding rights refuses it, for the reason the
contract states.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Mapping

from settlement import broker
from settlement.common import ResultCode

from . import (method_exec, packet, policy_action, policy_step, seeds,
               worlds)

DEVELOPMENT = "development"
ASSESSMENT = "assessment"
ASSESSMENT_RESTRICTED = "assessment-restricted"
AUDIT = "audit"

LEGACY_SEALED_PROFILE = ASSESSMENT_RESTRICTED

PRODUCTION = "production"
ASSESSMENT_LOCAL = "assessment-local"

_FAMILY_TAG = {"software": "sw", "graph": "gr"}

# The sealed profiles and the one that may stage. Kept beside the profiles
# rather than at the refusal site so the two places that have to agree about
# it are both declarations you can read side by side.
REVISION_REFUSAL_REASON = policy_action.REVISION_NOT_A_TASK_EFFECT


def default_repertoire() -> tuple:
    return tuple(item["capability_id"] for item in seeds.SEED_CAPABILITIES)


# ---------------------------------------------------------------------------
# the repertoire, and the path an acquired method takes to arrive in one
# ---------------------------------------------------------------------------
#
# `default_repertoire()` above is closed and stays closed. It is the four
# authored seed ids, it is frozen, and every archived run of every campaign
# in this tree reproduced its eligible sets from it. Nothing here changes
# that value; what changes is that closure is no longer the only reachable
# state.
#
# Before this region there was nowhere for a method acquired on one task to
# be nameable on another. `RETENTION_BLOCKER` stated that in code
# (`w2_retention_campaign.py:176-200`) and three archived reports read the
# closure off it, so the defect was not a missing implementation but a
# missing state: the type that would carry an arrived member did not exist,
# and the admission gate that would decide whether it could was
# `_resolve_method`'s single lookup in `seeds.SEED_CAPABILITIES`.
#
# So the shape comes first. A `Repertoire` is the authored seeds plus any
# number of arrived members, and it is the *repertoire in hand* rather than
# a constant that a caller could have grown that decides a task's eligible
# set. Two refusals matter more than the admission and both are stated at
# the type, not at a call site:
#
#   **a member is refused on the task it was acquired on.** Retention means
#   a prior task. A member offered on its own acquisition task measures
#   nothing about retention, and admitting it would let a contrast label a
#   cold acquisition's own result as reuse of itself.
#
#   **a member must carry bytes that verify.** `method_exec.verify_member`
#   is the executor's own gate and is called, not reimplemented, so a member
#   the executor would refuse never reaches an eligible list. The digest is
#   recomputed from the bytes rather than read from the member, for the
#   reason `trajectory.load_repertoire` recomputes it: a digest that is not
#   its bytes' digest is not a receipt for anything.
#
# The arrived member is executable through `method_source` and `entry`,
# beside its id, because `_resolve_method` resolves a bare `method_id`
# through the seed table alone and that function is not this lane's to
# edit. This is the route `trajectory._use_retained_method` and every
# `control_arm` member already take.

RESERVED_ID_PREFIXES = ("seed-", "ctl-")
"""Namespaces an arrived member may not claim.

`seed-` is `seeds.SEED_CAPABILITIES`, and `_resolve_method` resolves a
named id through it: a member claiming one would be two records for one
dispatch, and `trajectory.load_repertoire` already refuses it for the
stored repertoire. `ctl-` is `control_arm.ID_PREFIX`, which exists
precisely so a control member cannot be confused with a seed; an arrived
member in that namespace would be a third kind of record wearing a control
arm's name.
"""


class RepertoireRefused(ValueError):
    """A repertoire an eligible list may not be derived from.

    A refusal rather than a skip. A member that is dropped silently
    produces a closed eligible set that reads as the frozen one, which is
    the defect this region exists to remove.
    """


@dataclass(frozen=True)
class AcquiredMember:
    """Bytes acquired on a prior task, offered to a later one.

    `authored` is absent on purpose and there is no field that could stand
    in for it. Every value in `seeds.SEED_CAPABILITIES` carries
    `authored: True` because a later trajectory must never be able to
    present the reducers' behaviour as acquired; an arrived member is what
    its provenance says it is, and `origin` and `acquired_on` are the two
    facts that make it so. `as_executable` writes `authored: False`, which
    is the shape `trajectory._use_retained_method` and `load_repertoire`
    read.
    """
    capability_id: str
    family: str
    entry: str
    method_source: str
    origin: str
    acquired_on: str

    @property
    def source_digest(self) -> str:
        return hashlib.sha256(self.method_source.encode("utf-8")).hexdigest()

    def as_executable(self) -> dict:
        """The member in the shape the method executor takes.

        The same keys `construct._member` and `trajectory._use_retained_method`
        read, so an arrived member and an acquired one are one record to
        every consumer downstream and two records nowhere.
        """
        return {"capability_id": self.capability_id, "entry": self.entry,
                "method_source": self.method_source,
                "source_digest": self.source_digest, "authored": False,
                "origin": self.origin, "qualified_on": self.acquired_on,
                "scope": {"family": self.family}}

    def admit(self, task: Mapping[str, Any]) -> str | None:
        """Why this member may not be named on `task`, or nothing.

        Every refusal carries the member's own id, so a caller that reports
        one says which member it refused and not merely that something was
        refused.

        There is no digest check here and there was never going to be one
        worth having. `source_digest` is a computed property of
        `method_source` on a frozen dataclass, so comparing the two is a
        tautology and a check that always passes is worse than no check: it
        reads as a guarantee. The guarantee that actually holds is the
        executor's, below, and it is enforced by calling the executor
        rather than by reimplementing what it refuses.

        The order is how badly a member failing each check would misread.
        Identity, then bytes present, then the id namespaces, then the
        acquisition task, then the family's executor gate.
        """
        task_id = str((task or {}).get("task_id") or "")
        family = str((task or {}).get("family") or "")
        if not isinstance(self.capability_id, str) or not self.capability_id:
            return "a repertoire member needs a capability id"
        if not isinstance(self.method_source, str) or not self.method_source:
            return ("acquired member %r carries no executable bytes"
                    % (self.capability_id,))
        for prefix in RESERVED_ID_PREFIXES:
            if self.capability_id.startswith(prefix):
                return ("acquired member %r claims a reserved %r namespace"
                        % (self.capability_id, prefix))
        if self.acquired_on == task_id:
            return ("acquired member %r is refused on the task it was"
                    " acquired on" % (self.capability_id,))
        if family != self.family:
            return ("acquired member %r was acquired on a %s task and this"
                    " task is %s" % (self.capability_id, self.family, family))
        try:
            method_exec.verify_member(self.as_executable())
        except Exception as exc:
            return ("acquired member %r is refused by the method executor:"
                    " %s" % (self.capability_id, exc))
        return None


@dataclass(frozen=True)
class Repertoire:
    """The authored seeds plus whatever arrived, in one addressable set.

    `members` is empty for the repertoire every frozen campaign used, and
    the default is that empty case rather than a separate constant, so
    there is exactly one place a repertoire is built and one place an
    eligible set is derived from one.
    """
    members: tuple = ()

    def eligible_for(self, task: Mapping[str, Any],
                     *, strict: bool = True) -> list:
        """The method ids a policy on `task` may name, in selection order.

        The seeds come first and in their own order, so a policy that takes
        `eligible[0]` or that reads no further than `eligible[1]` behaves
        identically whether or not a member has arrived. That is the whole
        of the compatibility argument, and it is a property of this order
        rather than of any caller.

        A member refused for another family is out of scope, not an error:
        a repertoire holds every member acquired in a study, and asking a
        software member whether it applies to a graph task is a question
        with an answer rather than a malformed one. A member refused on its
        own acquisition task IS an error, because it means the caller
        believes that task is a prior one and it is not. So `admit` takes
        `strict`: under it every refusal is raised, which is what the
        `eligible_for` gate uses so that nothing is dropped silently.
        """
        strict = bool(strict)
        family = str((task or {}).get("family") or "")
        task_id = str((task or {}).get("task_id") or "")
        arrived = []
        for member in self.members:
            refusal = member.admit(task)
            if refusal is None:
                arrived.append(member.capability_id)
                continue
            if strict:
                raise RepertoireRefused(refusal)
            if member.family == family and member.acquired_on == task_id:
                raise RepertoireRefused(refusal)
        return [item["capability_id"] for item in seeds.SEED_CAPABILITIES
                if item["family"] == family] + arrived


def repertoire_with(*members: AcquiredMember) -> Repertoire:
    return Repertoire(tuple(members))


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
             qualify_depth: int = 0, step_index: int = 0,
             remaining: dict | None = None, visible_observation_ids=(),
             trusted: bool = False) -> dict:
    if not isinstance(candidate_digest, str) or not candidate_digest:
        raise ValueError("ctx needs a candidate digest")
    if not isinstance(scope, dict) or "family" not in scope \
            or "task_ids" not in scope:
        raise ValueError("ctx scope needs family plus task ids")
    if not isinstance(session, str) or not session:
        raise ValueError("ctx needs a session namespace")
    if type(qualify_depth) is not int or qualify_depth < 0:
        raise ValueError("qualify_depth must be a nonnegative integer")
    if type(step_index) is not int or step_index < 0:
        raise ValueError("step_index must be a nonnegative integer")
    return {"candidate_digest": candidate_digest, "scope": dict(scope),
            "task_ids": list(scope["task_ids"]), "session": session,
            "qualify_depth": qualify_depth, "step_index": step_index,
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


def _settled_model_response(dsn: str, operation_id: str) -> tuple[dict | None,
                                                                  str]:
    from settlement import store

    operation = broker.read_operation(dsn, operation_id)
    if operation is None:
        return None, "model operation is missing"
    if (operation.get("reconcile_state") in ("conflict", "unresolved")
            or operation.get("dispatch_state") == "unresolved"
            or operation.get("settled") is not True):
        return None, "model operation is not settled"
    receipts = store.operation_receipts(dsn, operation_id)
    if len(receipts) != 1:
        return None, "model operation has conflicting receipts"
    receipt = receipts[0]
    if (receipt.get("outcome") != "success"
            or receipt.get("settled") is not True
            or receipt.get("usable_result") is not True):
        return None, "model operation has no successful usable receipt"
    content = receipt.get("content")
    if not isinstance(content, dict) or not isinstance(content.get("text"),
                                                          str) \
            or not content["text"].strip():
        return None, "model operation has no response text"
    return {"text": content["text"],
            "receipt_identity": str(receipt["receipt_identity"])}, None


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


def _step_authority(dsn: str | None, allocation_id: str | None, session: str,
                    step_index: int) -> dict:
    """Authority for the policy step of one panel cell, or an empty dict.

    Empty is the honest answer for a panel with no store: the executor then
    refuses before a byte is staged, and the arm records the refusal rather
    than a decision the bytes never made. The step identity is distinct from
    the member identity on the same session and step, so the policy's own
    run and the method it chose are two operations rather than one.
    """
    if not (dsn and allocation_id):
        return {}
    return {"dsn": dsn, "allocation_id": allocation_id,
            "operation_id": "%s-step-k%d" % (session, step_index)}


def _execution_identity(profile: Profile, session: str, step_index: int,
                        kind: str) -> str:
    """The operation id a task effect runs under.

    Deterministic, because the same arm replaying the same panel step must
    land on the same operation and read back its own settled receipt rather
    than dispatch a second time. It carries the profile, the session and the
    step so two arms, two sessions and two steps never collide on one row.
    """
    return "%s-%s-%s-k%d" % (profile.op_prefix, session, kind, step_index)


def _resolve_method(task: dict, inputs: dict, kind: str = "use_method", *,
                    authority: dict | None = None) -> tuple:
    """Resolve the method an action names, and the walk it actually took.

    The walk comes back with the candidate. `method_exec.run_member_out_of_process`
    assembles it host-side, one row per query the member really asked, each
    carrying the candidate's digest and the verdict and reason the checker
    graded it `preserved`. It was produced and then dropped here, so a
    reading recorded only how many queries a run spent and not what it
    asked — and the questions are the only thing that distinguishes a
    method that searched from one that was handed its answer. A run with no
    walk returns `None`, which says the walk was absent rather than empty,
    and the two are different claims.

    An inline source is policy source, so it executes only under the same
    authority every other execution needs. A panel step with no store is a
    panel step whose method never ran, which is a different claim from one
    that ran and produced nothing, and it is refused as such.
    """
    if "candidate" in inputs:
        return None, 0, 0, 0, None, "none", (
            "policy-supplied candidate is not a task outcome"), None
    max_queries = inputs.get("max_queries", 16)
    if type(max_queries) is not int or max_queries < 0:
        return None, 0, 0, 0, None, "none", (
            "max_queries must be a nonnegative integer"), None
    exposed = packet.method_task_view(task)
    source = inputs.get("method_source") or inputs.get("source")
    started = time.perf_counter_ns()
    if isinstance(source, str) and source:
        entry = inputs.get("entry", "ENTRY")
        member = {"method_source": source, "entry": entry}
        if not (authority and authority.get("dsn")
                and authority.get("allocation_id")
                and authority.get("operation_id")):
            return None, 0, 0, 0, None, "method_exec", (
                "refused: a method executes only under a durable store, an"
                " allocation and an operation identity"), None
        try:
            method_exec.verify_member(member)
            result = method_exec.run_member_out_of_process(
                member, exposed, max_queries=max_queries, **authority)
        except Exception as exc:
            return None, 0, 0, 0, None, "method_exec", str(exc), None
        identity = "inline:%s:%s" % (entry, _source_digest(source)[:12])
        return (result.get("candidate"), int(result.get("queries", 0)), 0,
                _elapsed_ms(started), identity,
                "method_exec.run_member_out_of_process", None,
                result.get("query_trace"))
    method_id = inputs.get("method_id")
    if method_id is None and kind == "use_method":
        # Only a use names a method it did not build. A construct_method is
        # the action that produces one, so it legitimately arrives without an
        # id, and refusing it broke construction rather than fixing anything.
        return None, 0, 0, 0, None, "none", (
            "use_method action names no task method"), None
    if method_id is None:
        tag = _FAMILY_TAG.get(task.get("family", ""), "")
        method_id = "seed-%s-greedy" % tag
    capability = next((item for item in seeds.SEED_CAPABILITIES
                       if item["capability_id"] == method_id), None)
    if capability is None or capability["family"] != task.get("family") \
            or method_id not in default_repertoire():
        return None, 0, 0, 0, None, "none", ("unknown task method %r"
                                          % (inputs.get("method_id"),)), None
    try:
        result = seeds.run_seed(capability, exposed,
                                max_queries=max_queries)
    except Exception as exc:
        return None, 0, 0, 0, None, "seeds", str(exc), None
    return (result.get("candidate"), int(result.get("queries", 0)), 0,
            _elapsed_ms(started), method_id, "seeds.run_seed", None,
            result.get("query_trace"))


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
             action: dict, ctx: dict, dsn: str | None = None,
             allocation_id: str | None = None, gateway=None,
             model: str = "policy-request") -> dict:
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
        authority = {"dsn": dsn, "allocation_id": allocation_id,
                     "operation_id": _execution_identity(
                         profile, ctx["session"], int(ctx["step_index"]),
                         kind)}
        candidate, queries, _calls, wall_ms, identity, owner, failure, walk = \
            _resolve_method(task, dict(action.get("inputs") or {}), kind,
                            authority=authority)
        if failure is not None:
            return _refused(profile, kind, failure, source_digest, scope)
        return {"profile": profile.name, "kind": kind, "accepted": True,
                "reason": "", "candidate": candidate, "queries": queries,
                "model_calls": 0, "wall_ms": wall_ms,
                "selected_identity": identity, "owner": owner,
                "destination": profile.destination,
                "source_digest": source_digest, "scope": dict(scope),
                "query_trace": walk}
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
        if dsn is None or not allocation_id or gateway is None:
            return {**_refused(
                profile, kind,
                "model execution needs a durable store, allocation, and gateway",
                source_digest, scope), "accounting": "not-admitted"}
        try:
            operation = build_model_operation(
                profile_name=profile.name, action=action, model=model,
                session=ctx["session"],
                step_index=ctx.get("step_index", ctx["qualify_depth"]))
            ensured = broker.ensure_operation(
                dsn, operation_id=operation["operation_id"],
                effect=operation["effect"], payload=operation["payload"],
                allocation_id=allocation_id)
            if ensured.code not in (ResultCode.APPLIED,
                                    ResultCode.ALREADY_APPLIED):
                return {**_refused(
                    profile, kind, "model operation not admitted: %s"
                    % ensured.detail, source_digest, scope),
                    "accounting": "not-admitted"}
            status = broker.dispatch_operation(
                dsn, operation["operation_id"], launchers={}, gateway=gateway)
            response, failure = _settled_model_response(
                dsn, operation["operation_id"])
        except Exception as exc:
            return {**_refused(profile, kind, str(exc), source_digest, scope),
                    "accounting": "unresolved"}
        if failure is not None:
            accounting = "unresolved" \
                if getattr(status, "next_decision", "") in (
                    "needs-reconciliation", "receipt-admission-refused") \
                else "failed"
            return {**_refused(profile, kind, failure, source_digest, scope),
                    "owner": "broker.model-inference",
                    "accounting": accounting, "operation": operation,
                    "selected_identity": operation["operation_id"]}
        result = {"kind": "model_response", "text": response["text"],
                  "digest": _source_digest(response["text"]),
                  "operation_id": operation["operation_id"],
                  "receipt_identity": response["receipt_identity"]}
        return {"profile": profile.name, "kind": kind, "accepted": True,
                "reason": "", "candidate": None, "queries": 0,
                "model_calls": 1, "wall_ms": 0,
                "selected_identity": operation["operation_id"],
                "owner": "broker.model-inference",
                "destination": profile.destination,
                "source_digest": source_digest, "scope": dict(scope),
                "accounting": "settled", "operation": operation,
                "result": result}
    if kind == "propose_revision":
        # A stage only a binding profile could ever consume is a second
        # effect class with no consumer, not a permission. Every profile
        # without binding rights refuses the revision proposal, and the
        # reason is the contract's rather than a local spelling, so the
        # legacy sealed profile at `policy_assess` answers identically.
        if not profile.allow_revision_bind:
            return _refused(profile, kind, REVISION_REFUSAL_REASON,
                            source_digest, scope)
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


def _shared_assessment_arm(policy_record: dict, task_ids: list,
                           rule: dict, session: str, *, dsn: str | None = None,
                           allocation_id: str | None = None, gateway=None,
                           model: str = "policy-request") -> dict:
    from . import policy_assess
    arm = policy_assess._empty_arm(len(task_ids))
    reports = []
    sequence = 0
    digest = policy_step.verify_policy_record(policy_record)["source_digest"]
    for task_id in task_ids:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        state = {}
        observations = []
        last_result = None
        task_report = None
        for step_no in range(rule["max_steps"]):
            model_remaining = max(0, rule["max_steps"]
                                  - arm["resources"]["model_calls"])
            view = policy_step.materialize_view(
                task=task, observations=observations, open_questions=[],
                last_result=last_result,
                eligible_methods=[item["capability_id"] for item
                                  in seeds.SEED_CAPABILITIES
                                  if item["family"] == task["family"]],
                remaining={"steps": rule["max_steps"] - step_no,
                           "model_calls": model_remaining, "queries": 16})
            previous = dict(state)
            started = time.perf_counter_ns()
            try:
                stepped = policy_step.run_policy_step(
                    policy_record, view, state,
                    **_step_authority(dsn, allocation_id, session,
                                      step_no))
            except Exception as exc:
                arm["resources"]["step_calls"] += 1
                arm["resources"]["child_wall_ms"] += _elapsed_ms(started)
                arm["decisions"].append({
                    "seq": sequence, "task_id": task_id,
                    "kind": "step_error", "target": task_id,
                    "state_digest": policy_assess._state_digest(previous)})
                arm["effects"].append({
                    "kind": "step_error", "accepted": False,
                    "reason": str(exc), "owner": "policy_step"})
                sequence += 1
                break
            arm["resources"]["step_calls"] += 1
            arm["resources"]["child_wall_ms"] += _elapsed_ms(started)
            action = dict(stepped["action"])
            state = dict(stepped["state"])
            arm["decisions"].append({
                "seq": sequence, "task_id": task_id,
                "kind": action["kind"], "target": task_id,
                "state_digest": policy_assess._state_digest(state)})
            context = make_ctx(
                candidate_digest=digest,
                scope={"family": task["family"], "task_ids": [task_id]},
                session=session, step_index=step_no,
                remaining={"queries": 16, "model_calls": model_remaining},
                visible_observation_ids=tuple(
                    observation["observation_id"]
                    for observation in observations),
                trusted=True)
            effect = dispatch(
                profile_name=ASSESSMENT, record=policy_record, task=task,
                action=action, ctx=context, dsn=dsn,
                allocation_id=allocation_id, gateway=gateway, model=model)
            arm["effects"].append(effect)
            arm["resources"]["queries"] += int(effect["queries"])
            arm["resources"]["model_calls"] += int(effect["model_calls"])
            arm["resources"]["child_wall_ms"] += int(effect["wall_ms"])
            sequence += 1
            if effect["candidate"] is not None:
                report = policy_assess.trajectory._check(
                    task, effect["candidate"])
                initial, final = policy_assess.trajectory._size(
                    task, effect["candidate"])
                task_report = {"report": report, "initial": initial,
                               "final": final}
                break
            if effect.get("result") is not None:
                last_result = dict(effect["result"])
            else:
                last_result = {"verdict": "unmeasured", "kind": action["kind"],
                               "accepted": effect["accepted"]}
            observations.append({
                "observation_id": "panel-%s-%d" % (task_id, step_no),
                "task_id": task_id, "verdict": "unmeasured",
                "detail": {"accepted": effect["accepted"],
                           "accounting": effect.get("accounting", "none"),
                           "operation_id": effect.get("selected_identity")}})
            if action["kind"] == "stop":
                break
        reports.append(task_report)
    preserved = 0
    reduced = 0
    for task_report in reports:
        if task_report is None:
            continue
        report = task_report["report"]
        if report.get("verdict") == "preserved":
            preserved += 1
            if task_report["final"] < task_report["initial"]:
                reduced += 1
    arm["quality"] = {
        "tasks": len(task_ids), "preserved": preserved, "reduced": reduced,
        "failed": len(task_ids) - preserved}
    return arm


def assess_policy(dsn: str, *, proposal_id: str, candidate_source: str,
                  candidate_digest: str, candidate_artifact: dict,
                  incumbent_source: str, incumbent_digest: str,
                  incumbent_artifact: dict, panel: dict, rule: dict,
                  scope: dict, protocol_id: str,
                  evaluator_version: str, gateway=None,
                  allocation_id: str | None = None,
                  model: str = "policy-request") -> dict:
    from . import policy_assess
    frozen = policy_assess._read_journal(
        dsn, policy_assess._protocol_request_id(proposal_id))
    if frozen is None:
        raise ValueError("policy protocol is not frozen for proposal %r"
                         % proposal_id)
    panel_digest = policy_assess._panel_digest(panel)
    rule_identity = policy_assess._rule_identity(rule)
    if (frozen.get("panel_digest") != panel_digest
            or frozen.get("rule_id") != rule_identity["rule_id"]
            or frozen.get("rule_digest") != policy_assess._rule_digest(
                rule_identity)):
        raise ValueError("policy exposure differs from frozen protocol")
    if _source_digest(candidate_source) != candidate_digest:
        raise ValueError("candidate source digest does not match candidate_digest")
    candidate_unavailable = policy_assess._verify_candidate(
        candidate_source, candidate_digest, candidate_artifact)
    attempt_id = policy_assess.records.assessment_attempt_id(
        proposal_id, candidate_digest)
    if candidate_unavailable is not None:
        empty = policy_assess._empty_arm(len(panel["task_ids"]))
        record = {
            "proposal_id": proposal_id, "attempt_id": attempt_id,
            "outcome": "unavailable",
            "reason": candidate_unavailable["reason"],
            "protocol_id": protocol_id,
            "evaluator_version": evaluator_version, "scope": dict(scope),
            "candidate_digest": candidate_digest,
            "panel": {"panel_id": panel.get("panel_id", ""),
                      "task_ids": list(panel["task_ids"]),
                      "panel_digest": panel_digest,
                      "scope": dict(panel["scope"])},
            "rule": rule_identity,
            "arms": {"candidate": empty, "incumbent": empty}}
        return policy_assess._persist_assessment(dsn, record)
    policy_assess._verify_incumbent(
        incumbent_source, incumbent_digest, incumbent_artifact)
    stored = policy_assess._read_journal(dsn, attempt_id)
    if stored is not None:
        return stored
    candidate_record = {"artifact": dict(candidate_artifact["artifact"]),
                        "policy_source": candidate_source}
    incumbent_record = {"artifact": dict(incumbent_artifact["artifact"]),
                        "policy_source": incumbent_source}
    candidate_arm = _shared_assessment_arm(
        candidate_record, list(panel["task_ids"]), rule_identity,
        proposal_id + "-candidate", dsn=dsn, allocation_id=allocation_id,
        gateway=gateway, model=model)
    incumbent_arm = _shared_assessment_arm(
        incumbent_record, list(panel["task_ids"]), rule_identity,
        proposal_id + "-incumbent", dsn=dsn, allocation_id=allocation_id,
        gateway=gateway, model=model)
    outcome, reason = policy_assess._decision(
        candidate_arm, incumbent_arm, rule_identity)
    record = {
        "proposal_id": proposal_id, "attempt_id": attempt_id,
        "outcome": outcome, "reason": reason, "protocol_id": protocol_id,
        "evaluator_version": evaluator_version, "scope": dict(scope),
        "candidate_digest": candidate_digest,
        "panel": {"panel_id": panel.get("panel_id", ""),
                  "task_ids": list(panel["task_ids"]),
                  "panel_digest": panel_digest, "scope": dict(panel["scope"])},
        "rule": rule_identity,
        "arms": {"candidate": candidate_arm, "incumbent": incumbent_arm}}
    return policy_assess._persist_assessment(dsn, record)


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
