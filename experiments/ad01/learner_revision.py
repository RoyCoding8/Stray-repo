"""E4's run: a model proposes an executable change to a real learning decision.

`improve_channel` already owns the decision under study
(`diagnostic-evidence-selection`) and the frozen evaluator. What it does not
own is the run. This module is the run: it freezes the revision interface,
dispatches a model, decides whether the bytes it returned are an eligible
intervention, drives a real improve round with the accepted bytes, and scores
the descendants the round produced against the descendants an unchanged
learner produces on the same fresh cohort.

Two things are held apart on purpose, because conflating them is how a
negative turns into a vacuous one.

The first is acquisition. A refusal reason such as "not executable STEP" is a
property of the returned text. It is reported as an acquisition outcome and
never as a benefit outcome, and it is stored beside the raw reply so a reader
can see that a model answered and that the answer was wrong, rather than that
a run happened to find nothing.

The second is the ceiling. A revision that changes nothing and a revision
that changed everything are both easy to produce; the question a null has to
answer is whether any revision of this decision could have mattered. So the
run also measures the range over the whole reachable input set, and reports
the null against that rather than against zero. A ceiling that is itself
inside its own noise localises the blocker in the substrate, and no prompt
engineering fixes a substrate.

Attribution is carried per dispatch rather than asserted. Every live call
records the operation id, the route that answered, the model that answered
and the digest of the returned bytes, and the evidence builder refuses to
write a result artifact that claims a live acquisition it cannot point at.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_rule as _rules
from experiments.ad01 import frontier as _frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import method_exec as _method_exec

RUN_VERSION = "invl02-e4-run-v1"

# The revision interface, frozen before any model call. A revision may change
# exactly one thing: the integer the learner hands to `probe`. Everything the
# channel's execute path derives from that integer - which descendant the
# probe's output bit selects, how many grants the round spends, which
# obligations the descendant carries - is a consequence, not a second lever.
# Naming the field is what lets the eligibility rule below be a total
# function over a reply rather than a judgement about one.
REVISION_INTERFACE = "improve_channel.STEP.frontier_action.probe.inputs.x"

# The prompt is frozen with the interface. A study that redacts the constant
# is measuring whether the model guesses a literal, which is a different
# question from whether it can choose an input; the incumbent's own value is
# withheld so a reply that echoes the template cannot be scored as agreement.
SYSTEM_PROMPT = (
    "You are revising one decision inside a learning agent. The agent is "
    "learning a four-output Boolean rule over sixteen inputs by probing them. "
    "Each probe returns four bits. The agent may spend at most eight probes, "
    "and the inputs it has not probed are the ones it is later scored on. "
    "Reply with one Python function and nothing else. Do not explain, "
    "reason aloud, or restate the task.")

USER_TEMPLATE = """\
Rewrite the agent's improvement step so it chooses which input to probe.

The only thing you may change is the `x` in the probe action below. Emit the
whole function, unchanged except for that one integer.

```python
{template}
```

The integer must satisfy 0 <= x < 16. It must be computed from the view or
the state, never written as a constant. Reply with the function only. Start
your reply with ```python and end it with ```."""

CONSTANT_X = re.compile(r'"x"\s*:\s*(-?\d+)')
STEP_HEADER = "def STEP(view, state):"

# The gate, the account, the grader. A revision is admitted without any of
# these moving, and the run reports the frozen state digest before and after
# so a violation is a measurement rather than a promise.
FROZEN = {
    "decision_under_study": channel.DECISION,
    "evaluator": channel.EVALUATOR_ID,
    "channel_version": channel.CHANNEL_VERSION,
    "execution_limits": dict(channel.EXECUTION_LIMITS),
    "frozen_fields": tuple(channel.FROZEN_FIELDS),
    "descendant_rule": "unqueried-input accuracy, frozen evaluator",
}

# The judgement states, not a policy artifact origin. `ACQUIRED` here means
# "a reply came back off the wire and holds a usable STEP function". It is
# reachable only through `LiveAcquisition.dispatch`, which builds an
# HttpGatewayAdapter and refuses without a pinned route, so a recording
# double cannot produce it. It is not the `origin` a policy artifact carries
# and it is not what the verdict layer reads; the two vocabularies are kept
# apart on purpose. `live_attributable` re-checks the route and the model on
# the dispatch record before any report may claim the bytes are live.
ACQUIRED = "model-acquired"
AUTHORED = "reviewer-authored"
NO_REPLY = "no-reply"
UNUSABLE = "unusable-reply"


def _frozen_fingerprint() -> dict:
    return dict(FROZEN)


# --- the revision interface ------------------------------------------------


def template_for() -> str:
    """The bytes a revision starts from: the incumbent's own step source."""
    return channel.IMPROVE_LOW_SOURCE


def prompt_for() -> dict:
    """The frozen prompt, as the messages the gateway was handed."""
    return {"system": SYSTEM_PROMPT,
            "user": USER_TEMPLATE.format(template=template_for())}


def extract_source(text: str) -> str:
    """Pull the function out of a reply, or return what the reply really was.

    A model that wraps its answer in a fence is normal and is not a failure.
    A model that returns a paragraph is a different fact, and this returns
    the empty string for it so the eligibility rule can refuse the shape
    rather than the code.
    """
    if not isinstance(text, str) or not text.strip():
        return ""
    body = text
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", body, re.S)
    if fence:
        body = fence.group(1)
    start = body.find(STEP_HEADER)
    if start < 0:
        return ""
    return body[start:].rstrip()


def is_constant_x(source: str) -> bool:
    """True when the probed integer is a literal, whatever else the bytes do.

    The interface permits one integer and the eligibility rule requires it to
    depend on the view. A literal is the shape a prompt-parroting reply takes,
    so it is separated from the other refusals: it is a rejection of the
    reply's content rather than a statement about executability.
    """
    literals = CONSTANT_X.findall(source or "")
    if not literals:
        return False
    return len(literals) == 1 and not _x_uses_view(source)


def _x_uses_view(source: str) -> bool:
    """Whether the bytes' `x` reads the learner's own state."""
    import ast
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return False
    bound: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound[target.id] = node.value
    view_names = frozenset(("view", "state", "exp", "experience", "obs",
                            "observations", "remaining"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == "x"):
                continue
            expression, seen = value, set()
            while isinstance(expression, ast.Name) \
                    and expression.id in bound \
                    and expression.id not in seen:
                seen.add(expression.id)
                expression = bound[expression.id]
            for child in ast.walk(expression):
                if isinstance(child, ast.Name) and child.id in view_names:
                    return True
    return False


def differs_from_incumbent(source: str) -> bool:
    """True when the bytes are not the incumbent step source verbatim.

    The incumbent is a member of the menu, so a reply that returns it
    unchanged is eligible on every other axis and would be measured as a
    run that improved nothing for no reason a reader could see. It is
    recorded as its own outcome.
    """
    return (source or "").strip() != channel.IMPROVE_LOW_SOURCE.strip()


# --- the acquisition gate ---------------------------------------------------


def judge_acquisition(text: str, *, operation_id: str) -> dict:
    """Read one model's reply off the wire and decide what kind of thing it is.

    Every branch records the raw reply, because the difference between "the
    model declined to answer" and "the model answered and the answer was
    refused" is invisible in a verdict string and decisive for a report.
    """
    recorded = {"operation_id": operation_id, "reply": text if isinstance(
        text, str) else "", "reply_chars": len(text) if isinstance(
            text, str) else 0}
    if not recorded["reply"].strip():
        return {**recorded, "acquisition": NO_REPLY,
                "detail": "the route returned no text"}
    source = extract_source(recorded["reply"])
    if not source:
        return {**recorded, "acquisition": UNUSABLE,
                "detail": "the reply holds no STEP function",
                "source": ""}
    try:
        _method_exec.verify_step_source(source, "STEP")
    except Exception as exc:
        return {**recorded, "acquisition": UNUSABLE,
                "detail": "the returned function is not executable STEP: %s"
                          % exc,
                "source": source}
    if is_constant_x(source):
        return {**recorded, "acquisition": UNUSABLE,
                "detail": "the probed input is a literal, so the bytes do not"
                          " choose what to observe",
                "source": source}
    return {**recorded, "acquisition": ACQUIRED, "detail": None,
            "source": source,
            "source_digest": _frontier.source_digest(source)}


# --- the freeze -------------------------------------------------------------


class FreezeViolation(Exception):
    """The run changed something a revision is not allowed to change."""


def frozen_state_digest(store) -> dict:
    """The fields a revision may read but not write, as digests.

    Digests rather than values so a leak of a grant counter into a report
    is a comparison, and so the artifact carries a fingerprint rather than
    the budget.
    """
    state = channel.frozen_state(store)
    return {key: _frontier.source_digest(_frontier.canonical(value))
            for key, value in sorted(state.items())}


def check_frozen(before: dict, after: dict) -> None:
    if before != after:
        moved = sorted(key for key in set(before) | set(after)
                       if before.get(key) != after.get(key))
        raise FreezeViolation("frozen state moved: %s" % (moved,))


# --- the acquisition seam ---------------------------------------------------


@dataclass
class Dispatch:
    operation_id: str
    prompt_digest: str
    route: dict
    model: str
    reply: str = ""
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    error: str = ""


class LiveAcquisition:
    """The only place in this module that may spend a model call.

    The route contract is read from the runtime environment rather than
    written here, because the route is a fact about the provider and this
    study is not entitled to assert one. When the environment names no route
    the class refuses rather than defaulting: an unpinned route is the
    refusal the gateway adapter already makes, and making it here keeps the
    failure at the boundary instead of inside a result.

    The frozen route is stored with the provider exactly as the provider
    attested it. That is not a loosening of the comparison - the gateway
    adapter performs the comparison, and the value recorded here is the one
    it was given, so a report can reproduce the dispatch that was made.
    """

    def __init__(self, *, environ=None) -> None:
        values = dict(environ if environ is not None else os.environ)
        raw = (values.get("SETTLEMENT_EXPECTED_ROUTE") or "").strip()
        if raw[:1] in ("'", '"') and raw[-1:] == raw[:1]:
            raw = raw[1:-1].strip()
        if not raw:
            raise ValueError(
                "no SETTLEMENT_EXPECTED_ROUTE: the endpoint alone does not"
                " establish that the route is free, so this study refuses to"
                " dispatch rather than infer one")
        self.route = json.loads(raw)
        self.model = values.get("INVL02_LIVE_MODEL") or self.route.get(
            "requested_model", "")
        if not self.model:
            raise ValueError("no model to dispatch to")
        self.provider_fold: dict = {}

    def provider_as_attested(self, environ=None) -> str:
        """The provider spelling this gateway answers with.

        The proxy attests the vendor segment of the model id, capitalised.
        `HttpGatewayAdapter._response_meta` compares the returned provider
        for equality against the contract, so a contract written in lower
        case is refused on a response that is in fact the frozen free route.
        The study's own catalog check in the same module is case
        insensitive, so the two comparisons disagree about the same value.

        The attested spelling is therefore used for the dispatch, and both
        spellings are recorded beside the result. Recording only the one
        that worked would present a case-folding workaround as agreement
        about a provider.
        """
        return self.route.get("provider", "")

    def _attested_route(self) -> dict:
        """The contract as the gateway answers it, with the fold recorded."""
        route = dict(self.route)
        attested = self.route.get("provider", "")
        if attested and attested[0].islower():
            folded = attested[0].upper() + attested[1:]
            route["provider"] = folded
            self.provider_fold = {
                "frozen": attested, "dispatched": folded,
                "defect": ("gateway_http._response_meta compares the returned"
                           " provider with == while"
                           " gateway_http.reconcile_model_route compares it"
                           " case-insensitively; the two disagree about the"
                           " same value, so a lower-case contract is refused"
                           " on a response from the frozen free route"),
            }
        return route

    def dispatch(self, index: int, messages: list, *,
                 max_output_tokens: int, timeout_total_ms: int) -> Dispatch:
        from settlement.gateway import ModelRequest
        from settlement.gateway_http import HttpGatewayAdapter

        operation_id = "invl02-e4-revision-%04d" % index
        prompt_digest = _frontier.source_digest(_frontier.canonical(messages))
        route = self._attested_route()
        adapter = HttpGatewayAdapter(
            endpoint=route["endpoint"],
            api_key=os.environ.get("SETTLEMENT_GATEWAY_KEY", ""),
            api="chat", route_mode="free", expected_route=route,
            timeout_connect_ms=5_000, timeout_read_ms=timeout_total_ms - 20_000,
            timeout_total_ms=timeout_total_ms)
        started = time.monotonic()
        response = adapter.infer(ModelRequest(
            model=self.model,
            messages=tuple(messages),
            max_output_tokens=max_output_tokens,
            deadline_ms=timeout_total_ms - 5_000,
            operation_id=operation_id))
        elapsed = int((time.monotonic() - started) * 1000)
        if not hasattr(response, "text"):
            return Dispatch(operation_id, prompt_digest, route, self.model,
                            error="%s: %s" % (getattr(response, "kind", "?"),
                                              getattr(response, "message", "")),
                            latency_ms=elapsed)
        usage = getattr(response, "usage", None)
        return Dispatch(
            operation_id, prompt_digest, route, self.model,
            reply=response.text or "",
            usage={"input_tokens": getattr(usage, "input_tokens", None),
                   "output_tokens": getattr(usage, "output_tokens", None)},
            latency_ms=elapsed)


# --- eligibility -----------------------------------------------------------


def acquire(store, source: str, views: list, *, arm: str = "revision",
            label: str = ACQUIRED, role: str = "") -> dict:
    """Admit bytes under the freeze and the channel's own eligibility rule.

    Two refusals live here that the channel's rule does not have, and both
    are about the study rather than about the bytes. A reply that is the
    incumbent verbatim cannot demonstrate anything, and a reply that reaches
    no boundary is not a disconnected decision - it is no decision at all,
    which is a different failure and is reported as such.

    The channel's rule runs inside `admit_revision_under_freeze`, so this
    never re-decides an eligibility question the channel has already
    decided; it only adds the two the study owes.

    A control that is the incumbent on purpose is admitted through the same
    gate with the identity check waived, because the no-op's whole purpose
    is to reach the measurement. It keeps the control's own label, so the
    waiver is visible in the evidence next to the arm it applied to.
    """
    before = frozen_state_digest(store)
    if not source or not source.strip():
        return {**_refused("no-executable-bytes",
                           "the arm carries no revision source"),
                "arm": arm, "label": label, "role": role}
    if role != "no-op" and not differs_from_incumbent(source):
        return {**_refused("identical-to-incumbent",
                           "the arm's bytes are the incumbent's own step"
                           " source, so there is no revision to attribute"
                           " any difference to"),
                "arm": arm, "label": label, "role": role}
    verdict = dict(channel.admit_revision_under_freeze(store, source, views))
    verdict.update({"arm": arm, "label": label, "role": role})
    if role == "no-op":
        verdict["identity_check_waived_for_control"] = True
    if verdict.get("eligibility") == channel.ELIGIBLE:
        check_frozen(before, frozen_state_digest(store))
        verdict["frozen_state_digest"] = verdict.get("frozen_state_digest") \
            or _frontier.source_digest(_frontier.canonical(before))
    return verdict


def _refused(reason: str, detail: str) -> dict:
    return {"eligibility": reason, "reason": detail,
            "decision": channel.DECISION}


# --- the reviewer's own revision -------------------------------------------
#
# Every control here is the incumbent's own step source with one integer
# changed and one view read added, so a control differs from the arm it is
# compared with at exactly the decision under study and nowhere else.
#
# The view read is not decoration. `improve_channel._x_is_data_dependent`
# refuses a revision whose probed input cannot vary with what the learner has
# seen, and it reads the names the view itself carries rather than following
# an indirection, so each control's `x` names a value derived from
# `view["experience"]` directly. Every control is therefore a genuine
# selector: it answers a different question of the same learner, and the
# rule it applies is stated in the control's own record.


REVIEWER_X = 8
REVIEWER_WHY = (
    "The reviewer read `reachable_descendant_means` in the qualified "
    "headroom artifact, where %d is the highest of the sixteen inputs the "
    "instrument accepts, and wrote a selector that names that input unless "
    "the learner has already spent it. The effect is known before the arm is "
    "run: on the first step the view carries no observation, so the control "
    "names %d, the descendant it selects differs from the incumbent's, and "
    "the size and direction of that difference are properties of the "
    "substrate rather than of the reviewer." % (REVIEWER_X, REVIEWER_X))


def _selector(imp_source: str, preferred: str, fallback: str) -> str:
    """Bind the probed input to a value read out of the learner's experience.

    The rule is one line and is the same shape for all three controls: name
    the preferred input unless the learner has already probed it, and name
    the fallback when it has. Only the two integers differ between them.

    The view read is written at the point of use rather than bound to a name
    on the line above. `improve_channel._probe_x_expression` resolves an
    `x` through module-level assignments and then asks whether the resulting
    expression reads the view, so an intermediate name turns a genuine
    selector into a refusal. That is a property of the rule and the controls
    are written to satisfy it rather than to work around it.
    """
    return imp_source.replace(
        '"x": %s' % preferred,
        '"x": %s if %s not in set(o.get("x") for o in view["experience"])'
        ' else %s' % (preferred, preferred, fallback), 1)


def reviewer_revision() -> dict:
    """A revision a human wrote, with its effect stated in advance.

    It exists to prove the apparatus can carry a known effect through to a
    descendant measurement. It is labeled `reviewer-authored` and never
    enters an acquired arm, and the label travels in the evidence rather
    than in a comment, so a reader cannot mistake it for a model reply.
    """
    return {
        "label": AUTHORED,
        "control_id": "reviewer-authored-x%d" % REVIEWER_X,
        "source": _selector(
            channel._revision_source(str(REVIEWER_X)), str(REVIEWER_X), "3"),
        "known_effect": REVIEWER_WHY,
        "expects_changed_decision": True,
        "x_under_incumbent": 3,
        "x_under_revision": REVIEWER_X,
    }


def no_op_revision() -> dict:
    """The control that must change nothing, and the only one that may not.

    It names the incumbent's own input through the same view read the
    known-effect control uses, so the two differ in the integers they name
    and in nothing else. A revision that returned the incumbent's bytes
    verbatim would be refused by the study's identity check before it could
    be measured, which is correct for an acquired arm and useless for a
    control whose whole purpose is to arrive at the measurement.
    """
    return {
        "label": AUTHORED,
        "control_id": "no-op-incumbent-x3",
        "source": _selector(channel._revision_source("3"), "3", "8"),
        "known_effect": (
            "The incumbent's own input, 3, selected by the same view read "
            "the known-effect control uses. On the first step nothing has "
            "been spent, so it names 3, the descendant it builds is the "
            "incumbent's descendant, and the paired difference is exactly "
            "zero by construction rather than by a measurement that happened "
            "to be small."),
        "expects_changed_decision": False,
        "x_under_incumbent": 3,
        "x_under_revision": 3,
    }


def disconnect_revision() -> dict:
    """A revision that reaches the boundary and cannot change anything.

    The input it names is outside the instrument's own range, so the
    instrument refuses it, the probe returns nothing, and the round has no
    observation to turn into a descendant. This is the failure a no-op
    cannot demonstrate: a no-op is wired correctly and decides correctly and
    correctly chooses the same thing, while this is a decision that is spent
    and arrives at nothing. Reporting both as a flat descendant would hide
    the difference between a learner that learned and one that could not ask.

    It is refused at the action validator, before the instrument sees it,
    which is the earliest point at which the range of an input is known. The
    run records the refusal rather than an exception, so the disconnect is a
    recorded outcome of a real attempt.
    """
    out_of_range = _rules.N_STATES
    return {
        "label": AUTHORED,
        "control_id": "disconnect-x%d" % out_of_range,
        "source": _selector(
            channel._revision_source(str(out_of_range)), str(out_of_range),
            "3"),
        "known_effect": (
            "The decision is reached and the input is named, but the "
            "instrument's own action validator refuses input %d because the "
            "task exposes only inputs 0..%d. The probe returns no "
            "observation, no descendant is built and the round ends without "
            "a candidate. The difference from a no-op is the point: a no-op "
            "learns what the incumbent learns, and this learns nothing at "
            "all, and both would score flat under an evaluator that looked "
            "only at the number." % (out_of_range, _rules.N_STATES - 1)),
        "expects_changed_decision": True,
        "x_under_incumbent": 3,
        "x_under_revision": out_of_range,
        "refused_by_instrument": True,
    }


# The C15 shape, kept under its own name. `disconnect` above is a decision
# the instrument refuses; this is a decision the instrument accepts and that
# still changes nothing, which is the shape that actually shipped once
# already: bytes that differ, behaviour that does not.
DISCONNECT_X = 7
_C15_ANCHOR = '''    if step == 0:
        inner = {"kind": "probe", "inputs": {"x": 3},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}'''
_C15_REPLACEMENT = '''    if step == 0:
        inner = {"kind": "probe",
                 "inputs": {"x": %d if view["experience"] else 3},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}''' % DISCONNECT_X


def disconnect_bytes_revision() -> dict:
    """Bytes that differ, and a decision that does not.

    The other two controls each fail loudly. This one passes every gate and
    still does nothing, because the only branch that would change the probed
    input is the branch the learner is never on: `view["experience"]` is
    empty on the step where the probe is spent, so the `else 3` arm is the
    one that runs and input 3 is the incumbent's own input.

    It is admitted as eligible. `is_constant_x` passes because the bytes are
    not the incumbent verbatim, and the channel's data-dependence rule passes
    because the `x` expression does read the view. Both gates are right and
    both are defeated by a branch no learner takes, which is the whole reason
    this control is here: an eligibility rule cannot tell a revision that
    chooses from one that merely contains a choice.

    The integer is the ceiling's argmax on the audit cohort, so a reader can
    see the rule is not trivial - the same integer, reached, would improve
    the descendant. The control is the unreachability, not the integer.
    """
    source = channel.IMPROVE_LOW_SOURCE
    if _C15_ANCHOR not in source:
        raise _frontier.Refused("the incumbent step source no longer has the"
                                " probe branch this control rewrites")
    return {
        "label": AUTHORED,
        "control_id": "disconnect-bytes-x%d-unreachable" % DISCONNECT_X,
        "source": source.replace(_C15_ANCHOR, _C15_REPLACEMENT, 1),
        "known_effect": (
            "The bytes differ from the incumbent and are admitted as "
            "eligible, because the probed input is a view read and so is "
            "not a constant. The decision does not change: on the step that "
            "spends the probe, `view[\"experience\"]` is empty, so the "
            "expression takes its `else 3` arm and the learner probes the "
            "incumbent's own input. The descendant is therefore the "
            "incumbent's descendant and the paired difference is exactly "
            "zero, while the source digest is not the incumbent's digest. "
            "This is the C15 shape: different bytes, same behaviour."),
        "expects_changed_decision": False,
        "x_under_incumbent": 3,
        "x_under_revision": 3,
        "decoy_x": DISCONNECT_X,
        "shaped_like": "C15",
    }


CONTROL_BUILDERS = {
    "known-effect": reviewer_revision,
    "no-op": no_op_revision,
    "disconnect": disconnect_revision,
    "disconnect-bytes": disconnect_bytes_revision,
}


def build_control(role: str) -> dict:
    try:
        return CONTROL_BUILDERS[role]()
    except KeyError:
        raise _frontier.Refused("unknown E4 control role %r" % (role,))


# --- driving one arm --------------------------------------------------------


def _mission(split: str = "dev", seed: int = 4) -> dict:
    return {"objective": "probe boolean rules within eight queries",
            "constraints": ["deterministic only", "no live network"],
            "success_criteria": ["committed predictor"],
            "environments": [{"instrument": "boolean-rule-v1",
                              "split": split, "seed": seed}]}


def revision_package(imp_source: str, parent: dict, control_id: str, *,
                     provenance: dict = None) -> dict:
    """A package carrying revision bytes, bound the way adoption requires.

    The operational source is copied from the parent rather than supplied,
    because `adopt_revision` refuses a revision whose operational bytes
    differ, and a revision is not permitted an opinion about them.

    An arm whose bytes came from a live dispatch is packaged as `acquired`
    and carries the dispatch provenance that binds it. That is not a label
    this study chooses to apply: `frontier._durable_acquisition` refuses an
    `acquired` package whose provenance does not resolve to a recorded
    gateway dispatch and a finalization, so an arm claiming live bytes
    without a dispatch behind it cannot be adopted at all. The controls are
    packaged as `authored-control`, which is the origin that carries no
    acquisition lineage, and they are labeled that way in the evidence.
    """
    acquired = provenance is not None
    package = {
        "control_id": control_id,
        "origin": "acquired" if acquired else "authored-control",
        "source_kind": "model-response" if acquired else "fixed-menu",
        "op_source": parent["op_source"], "imp_source": imp_source,
        "op_digest": _frontier.source_digest(parent["op_source"]),
        "imp_digest": _frontier.source_digest(imp_source),
        "parent_digest": parent["package_digest"],
        "provenance": provenance,
        "provenance_digest": (
            _frontier.source_digest(_frontier.canonical(provenance))
            if acquired else None),
        "version": int(parent["version"]) + 1,
        "authority_request": dict(parent["authority_request"]),
        "obligations": list(parent["obligations"]),
        "channel": parent["channel"], "package_digest": None,
    }
    package["package_digest"] = _frontier.package_digest(package)
    return package


def dispatch_evidence(dispatch, messages: list, *, arm: str,
                      round_no: int = 1) -> dict:
    """The gateway-dispatch record a live arm is adopted under.

    Built with `frontier.make_evidence_record` and recorded through
    `store.record_evidence`, which also writes the source anchor that later
    re-validates the raw prompt and raw response on disk. So the arm's
    bytes are bound to the prompt that produced them and to the route that
    answered, and a reader can re-derive the provenance rather than trust
    the field.
    """
    raw_prompt = "".join(str(message.get("content", ""))
                         for message in messages if message.get("role") == "user")
    record = _frontier.make_evidence_record(
        "gateway-dispatch", dispatch.operation_id,
        "success" if dispatch.reply.strip() else "unknown",
        attempt=1, arm=arm,
        task_id="e4-:%s" % arm,
        input_digest=_frontier.source_digest(raw_prompt),
        result_digest=_frontier.source_digest(dispatch.reply),
        parse_outcome="pending", accepted_candidate_digest=None,
        round_no=round_no,
        details={"raw_payload": {"raw_prompt": raw_prompt,
                                 "raw_response": dispatch.reply},
                 "route": dict(dispatch.route),
                 "stop_reason": "", "usage": dict(dispatch.usage)})
    record.update({
        "requested_model": dispatch.model,
        "returned_model": dispatch.route.get("resolved_model"),
        "endpoint": dispatch.route.get("endpoint"),
        "provider": dispatch.route.get("provider"),
        "tier": dispatch.route.get("tier"),
        "requested_output_cap": MAX_OUTPUT_TOKENS,
        "response_digest": _frontier.source_digest(dispatch.reply),
        "prompt_digest": _frontier.source_digest(raw_prompt),
        "raw_prompt": raw_prompt, "raw_response": dispatch.reply,
        "stop_reason": "", "usage": dict(dispatch.usage),
        "billed": None, "charge_units": None, "route_error": None,
    })
    return record


def finalize_evidence(original: dict, package: dict, *, parsed_digest: str,
                      round_no: int = 1) -> dict:
    """Close the dispatch against the package the reply was parsed into.

    The finalization is what makes the reply a candidate rather than a
    string: it records which parsed source the dispatch produced, and
    `frontier.validate_acquisition_evidence` refuses a finalization that
    names a different one. Without it an arm could be adopted under bytes
    that no dispatch produced.
    """
    return _frontier.make_evidence_record(
        "gateway-dispatch", original["operation_id"],
        original["outcome"],
        attempt=original["attempt"], arm=original["arm"],
        task_id=original["task_id"],
        input_digest=original["input_digest"],
        result_digest=original["result_digest"],
        package_digest=package["package_digest"],
        parent_digest=package["parent_digest"], round_no=round_no,
        dispatch_evidence_digest=original["evidence_digest"],
        parse_outcome="accepted",
        accepted_candidate_digest=parsed_digest,
        details=dict(original["details"]))


@dataclass
class Round:
    arm: str
    label: str
    x_probed: int = -1
    observations: list = field(default_factory=list)
    candidate_id: str = ""
    descendant_strategy: str = ""
    frozen_before: dict = field(default_factory=dict)
    frozen_after: dict = field(default_factory=dict)
    used: dict = field(default_factory=dict)
    grant: dict = field(default_factory=dict)
    refused_by_instrument: bool = False
    error: str = ""


def drive_arm(store_path: Path, source: str, arm: str, label: str, *,
              control_id: str, verdict: dict, provenance: dict = None) -> Round:
    """Run one improve round with `source` and read the decision off it.

    The store is rebuilt per arm and the revision is adopted into a fresh
    one, so no arm inherits a store, a receipt or a private state from the
    arm before it. The frozen state is captured around the adoption, because
    admission is the only step a revision is close enough to the authority to
    touch it.
    """
    result = Round(arm=arm, label=label)
    result.frozen_before = dict(verdict.get("frozen_before") or {})
    result.frozen_after = dict(verdict.get("frozen_after") or {})
    if verdict.get("eligibility") != channel.ELIGIBLE:
        result.error = "not admitted: %s" % verdict.get("reason", "")
        return result
    store = _frontier.create_store(
        store_path, namespace=_frontier.NAMESPACE, mission=_mission(),
        authority={"queries": 16, "steps": 12})
    parent = channel.make_control("low")
    store.bind_active(parent)
    result.frozen_before = frozen_state_digest(store)
    store.adopt_revision(
        revision_package(source, parent, control_id, provenance=provenance))
    result.frozen_after = frozen_state_digest(store)
    check_frozen(result.frozen_before, result.frozen_after)
    try:
        driven = channel.drive_improve_round(
            store, _rules.make_task("dev", 0), package=store.active_package,
            round_no=1, admit_probes=True)
    except _frontier.Refused as exc:
        result.error = "the round's own action validator refused the arm: %s" \
            % exc
        result.refused_by_instrument = True
        return result
    result.observations = list(driven["observations"])
    result.candidate_id = driven["candidate"]["control_id"]
    result.descendant_strategy = result.candidate_id.removeprefix(
        "control-").rsplit("-r", 1)[0]
    result.used = dict(store._doc.get("used") or {})
    result.grant = dict(store._doc.get("grant") or {})
    if result.observations:
        result.x_probed = int(result.observations[0]["x"])
    else:
        result.error = "the round spent its probe and observed nothing"
    return result


def descendant_of(x_probed: int, split: str, seed: int) -> dict:
    """The descendant one decision produces on one unseen task.

    Not the reviser's score. The reviser probed a development input; the
    packages that input selected run on the cohort, and the number the
    improvement claim is about is what those packages achieve there.
    """
    if x_probed < 0:
        return {"unqueried": 0.0, "queried": 0.0, "overall": 0.0,
                "refused_inputs": 0, "learned_inputs": 0,
                "no_descendant": True}
    if x_probed >= _rules.N_STATES:
        return channel.descendant_score([x_probed], split, seed)
    return channel.lineage_descendant_score(x_probed, split, seed)


# --- the paired comparison --------------------------------------------------


def paired(revised: list, incumbent: list) -> dict:
    """A signed difference with its own standard error, or no measurement."""
    if not revised or not incumbent or len(revised) != len(incumbent):
        return {"delta": None, "n": 0, "measured": False, "paired_sd": None,
                "paired_se": None, "z": None}
    differences = [r - i for r, i in zip(revised, incumbent)]
    n = len(differences)
    delta = sum(differences) / n
    sd = statistics.pstdev(differences) if n > 1 else 0.0
    se = sd / n ** 0.5 if n else 0.0
    return {"delta": delta, "n": n, "measured": True, "paired_sd": sd,
            "paired_se": se, "z": (delta / se) if se else None,
            "rule": FROZEN["descendant_rule"]}


def cohort_scores(x_probed: int, split: str, seeds: list) -> list:
    return [descendant_of(x_probed, split, seed)["unqueried"]
            for seed in seeds]


def compare(x_revised: int, x_incumbent: int, *, split: str,
            seeds: list) -> dict:
    """One arm against the incumbent on one fresh cohort, paired by seed.

    An arm that built no descendant is not measured at all rather than
    scored zero. A disconnect refused at the boundary leaves nothing to
    score, and calling that a large negative difference would report a
    failure of the apparatus as an exceptionally bad result obtained by
    measurement.
    """
    if x_revised < 0:
        return {"delta": None, "n": 0, "measured": False, "paired_sd": None,
                "paired_se": None, "z": None, "split": split,
                "n_seeds": len(seeds), "x_revised": x_revised,
                "x_incumbent": x_incumbent, "mean_revised": None,
                "mean_incumbent": None, "no_descendant": True}
    revised = cohort_scores(x_revised, split, seeds)
    incumbent_scores = cohort_scores(x_incumbent, split, seeds)
    result = paired(revised, incumbent_scores)
    result.update({
        "split": split, "n_seeds": len(seeds),
        "x_revised": x_revised, "x_incumbent": x_incumbent,
        "mean_revised": (sum(revised) / len(revised)) if revised else None,
        "mean_incumbent": (sum(incumbent_scores) / len(incumbent_scores))
        if incumbent_scores else None,
    })
    return result


def ceiling(split: str, seeds: list, *, search: list = None) -> dict:
    """The range over every input the decision can select, paired by seed.

    This is what a null has to be measured against. A run whose arm differs
    from the incumbent by less than this range has not improved learning, and
    a run whose arm differs by more than it has improved something no other
    input could have. It is measured the way a claim would be: the argmax is
    taken on one half of the cohort and scored on the other, so the ceiling
    is not the maximum of the numbers it is reported next to.
    """
    if not seeds:
        return {"measured": False, "n_seeds": 0, "split": split}
    search = list(search or seeds[0::2])
    score_seeds = [seed for seed in seeds if seed not in set(search)] or \
        list(seeds)
    inputs = list(range(_rules.N_STATES))
    search_means = {
        x: sum(channel.lineage_descendant_score(x, split, seed)["unqueried"]
               for seed in search) / len(search) for x in inputs}
    best = max(sorted(search_means), key=search_means.get)
    worst = min(sorted(search_means), key=search_means.get)
    best_scores = [channel.lineage_descendant_score(best, split, seed)[
        "unqueried"] for seed in score_seeds]
    worst_scores = [channel.lineage_descendant_score(worst, split, seed)[
        "unqueried"] for seed in score_seeds]
    estimate = paired(best_scores, worst_scores)
    estimate.update({"measured": True, "split": split,
                     "n_seeds": len(score_seeds), "best_input": best,
                     "worst_input": worst, "best_mean": sum(best_scores) / len(
                         best_scores),
                     "worst_mean": sum(worst_scores) / len(worst_scores)})
    return estimate


def evidence_ceiling(split: str, seeds: list) -> dict:
    """The range available to the learner's own evidence decision.

    This is the measurement a null in this study has to be reported against,
    and it is deliberately wider than the E4 boundary. The E4 boundary
    chooses one development probe, and a descendant runs one fixed input, so
    no revision of that decision can move a descendant further than the gap
    between the best and worst of those sixteen inputs. The frozen reducer
    `rule_learner.VersionSpaceLearner.choose_query` is the real, existing
    evidence-selection decision this codebase makes, and it spends up to
    eight inputs per descendant, so the range it reaches is the range a
    revision of evidence selection could express if the boundary were not
    capped by `leaf_construct`.

    Both are reported. Quoting only the wide one would claim a revision
    could do something the boundary forbids; quoting only the narrow one
    would let a null be read as a property of evidence selection when it is
    a property of how a descendant is built.
    """
    if not seeds:
        return {"measured": False, "n_seeds": 0, "split": split}
    from experiments.ad01 import rule_learner as _reducer
    sequences = []
    for seed in seeds:
        learner = _reducer.VersionSpaceLearner(_rules.CLASS_TABLES, int(seed))
        queried: set = set()
        chosen: list = []
        for _ in range(_rules.MAX_QUERIES):
            pick = learner.choose_query(
                {x: (0,) * _rules.N_OUTPUTS for x in queried})
            if pick is None:
                break
            chosen.append(pick)
            queried.add(pick)
        sequences.append(chosen)
    incumbent = [channel.descendant_score(
        list(channel.INCUMBENT_EVIDENCE), split, seed)["unqueried"]
        for seed in seeds]
    reducer = [channel.descendant_score(seq, split, seed)["unqueried"]
               for seq, seed in zip(sequences, seeds)]
    n = len(seeds)
    return {
        "decision": "evidence-set-selection",
        "learner": "rule_learner.VersionSpaceLearner.choose_query",
        "split": split, "n_seeds": n,
        "incumbent_mean": sum(incumbent) / n,
        "reducer_mean": sum(reducer) / n,
        "mean_queries": sum(len(seq) for seq in sequences) / n,
        "paired": paired(reducer, incumbent),
        "note": ("the frozen reducer's own eight-input evidence set, scored"
                 " on the same cohort and the same evaluator as every other"
                 " number in this file"),
    }


# --- qualification versus outcome ------------------------------------------
#
# The channel already separates these two verdicts and this file does not
# merge them. What it adds is the qualifier: a control here is a real arm
# driven through the same gate, the same round and the same cohort as an
# acquired one, so a control that passes has passed through the machinery a
# benefit claim would have to pass through.

QUALIFIED = channel.QUALIFIED
UNQUALIFIED = channel.UNQUALIFIED


def qualify(rounds: dict) -> dict:
    """The apparatus verdict, from the three controls and nothing else.

    Each control declares what it expects in `build_control`, so the
    expectation is not written next to the number it is checked against. A
    control that produced the wrong effect makes the apparatus untrustworthy
    regardless of how good the acquired arm was.
    """
    checks: dict = {}
    for role, control in CONTROL_BUILDERS.items():
        driven = rounds.get(role) or {}
        measured = driven.get("paired") or {}
        delta = measured.get("delta")
        if role == "known-effect":
            passed = bool(measured.get("measured")) and delta is not None \
                and delta != 0.0
        elif role == "no-op":
            passed = bool(measured.get("measured")) and delta == 0.0
        elif role == "disconnect-bytes":
            passed = bool(measured.get("measured")) and delta == 0.0
            passed = passed and not driven.get("refused_by_instrument")
            passed = passed and bool(driven.get("changed", {}).get(
                "changed_decision")) is False
        else:
            passed = bool(driven.get("refused_by_instrument"))
        checks[role] = {
            "present": role in rounds,
            "passed": passed,
            "delta": delta,
            "x_probed": driven.get("x_probed"),
            "refused_by_instrument": bool(
                driven.get("refused_by_instrument")),
            "descendant_built": bool(driven.get("candidate_id")),
            "eligibility": driven.get("eligibility"),
            "error": driven.get("error"),
            "known_effect": control()["known_effect"],
        }
    passed = all(entry["present"] and entry["passed"]
                 for entry in checks.values())
    return {"qualification": QUALIFIED if passed else UNQUALIFIED,
            "qualified": passed, "checks": checks,
            "note": channel.qualify_apparatus([])["note"]}


def outcome(acquisition: dict, arm: dict, paired_result: dict) -> dict:
    """The benefit verdict for one arm, over an already-qualified apparatus.

    The channel's rule decides benefit from three things and this adds the
    two this study owes it: the arm has to have changed the decision, and
    the change has to be attributable to something rather than to the
    apparatus. A model that returned the incumbent's own bytes has an
    eligible-shaped reply and changes nothing, and calling that a benefit
    would be the whole failure the identity check exists to prevent.
    """
    verdict = dict(channel.benefit_outcome(paired_result, acquisition))
    if verdict["benefit"] and not arm.get("changed_decision"):
        verdict["benefit"] = False
        verdict["blockers"] = list(verdict["blockers"]) + [
            "the arm did not change the decision it was admitted for"]
    verdict["changed_decision"] = bool(arm.get("changed_decision"))
    return verdict


def arm_changed_decision(driven, control: dict = None) -> dict:
    """Whether the arm selected a different input than the incumbent did.

    Reported as a comparison of the two integers rather than as a boolean
    derived from them, because a reader who wants to check the claim needs
    the two numbers, and because the no-op's `x_probed` being equal to the
    incumbent's is the only evidence that the no-op really was one.
    """
    get = driven.get if isinstance(driven, dict) else \
        lambda key: getattr(driven, key, None)
    incumbent_x = (control or {}).get("x_under_incumbent", 3)
    revised_x = get("x_probed")
    revised_x = -1 if revised_x is None else revised_x
    return {"incumbent_x": incumbent_x, "revised_x": revised_x,
            "changed_decision": revised_x != incumbent_x,
            "reached_boundary": revised_x >= 0}


# --- the run ----------------------------------------------------------------

SPLIT = "audit"
COHORT = list(range(150))
ACQUISITION_ATTEMPTS = 6
# The first campaign at 2048 output tokens spent the whole budget on
# reasoning and returned prose truncated before the function: six replies,
# none of them carrying a `def STEP`. The cap is the fix, not the prompt,
# because the reply that did arrive at 1818 tokens shows the model
# reasoning at length before it commits to an answer.
MAX_OUTPUT_TOKENS = 6_144
TIMEOUT_TOTAL_MS = 300_000

NO_BENEFIT = "no-benefit"
INELIGIBLE_REPORTED = "no-eligible-revision-acquired"


def diagnose_refusal(verdict: dict, views: list) -> dict:
    """Why a refused revision was refused, in terms a reader can act on.

    `improve_channel.classify_revision` reports the reason a shape fails.
    That is not the same as reporting why this acquisition failed, and the
    difference matters here: the commonest refusal in this campaign is
    `delegates-to-unchanged-reducer`, whose name says what was disallowed
    and nothing about what the bytes did instead.

    The decision is made at the first step, where the view carries no
    observation, so a revision is judged on the single integer it names
    there. This records that integer, the integer the frozen reducer would
    have named at the same view, and whether they agree - which is what
    turns the refusal into a statement about the model rather than about
    the rule.
    """
    reason = verdict.get("eligibility")
    if reason == channel.ELIGIBLE:
        return {"reason": reason, "diagnosed": False}
    detail: dict = {"reason": reason, "diagnosed": True,
                    "message": verdict.get("reason")}
    if not views:
        return detail
    view = views[0]
    try:
        choices = channel.revision_evidence_choices(
            verdict.get("source") or "", view)
    except Exception as exc:
        return {**detail, "execution_error": str(exc)}
    reducer = channel._reducer_argmax(view)
    detail["selected_at_first_step"] = choices[0] if choices else None
    detail["reducer_own_choice"] = reducer[0] if reducer else None
    detail["incumbent_evidence"] = list(channel.INCUMBENT_EVIDENCE)
    detail["distinct_from_reducer"] = bool(choices) and reducer and \
        choices[0] not in reducer
    detail["observation"] = (
        "the decision is made at the first step, where the view carries no"
        " observation, so a revision is judged on the single integer it"
        " names there; an expression that reads the view can still evaluate"
        " to the same integer under every view it will ever be shown, and"
        " that is a fixed answer wearing a selector's syntax")
    return detail


def _adjudication(judgements: list) -> dict:
    """What the dispatches produced, counted by outcome rather than by hope.

    A campaign that acquired nothing and a campaign that acquired six
    unusable replies are both `no-eligible-revision-acquired`, and they are
    different facts. The counts are reported beside the verdict so the
    difference is not lost in the string.
    """
    by_state: dict = {}
    for judgement in judgements:
        state = judgement["acquisition"]
        by_state[state] = by_state.get(state, 0) + 1
    usable = [judgement for judgement in judgements
              if judgement["acquisition"] == ACQUIRED]
    return {
        "dispatches": len(judgements),
        "acquired": len(usable),
        "by_state": by_state,
        "eligible": any(judgement.get("eligible") for judgement in usable),
        "verdict": INELIGIBLE_REPORTED if not any(
            judgement.get("eligible") for judgement in usable) else None,
    }


def run_campaign(*, workdir: Path, attempts: int = ACQUISITION_ATTEMPTS,
                 split: str = SPLIT, cohort: list = None) -> dict:
    """Dispatch for an eligible revision, then run every arm and control.

    The dispatches stop at the first eligible reply and the rest of the
    budget is returned unused. A campaign that has a revision has no reason
    to buy more, and the cap sheet for a study is written from the matrix
    rather than spent to the end.
    """
    cohort = list(cohort if cohort is not None else COHORT)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    messages = prompt_for()
    frozen = _frozen_fingerprint()

    acquisition: dict = {"acquisition": NO_REPLY,
                         "detail": "no dispatch was attempted",
                         "live_attributable": False, "eligible": False}
    dispatches: list = []
    for index in range(1, attempts + 1):
        try:
            live = LiveAcquisition()
        except ValueError as exc:
            acquisition = {"acquisition": NO_REPLY, "detail": str(exc),
                           "live_attributable": False, "eligible": False}
            break
        dispatch = live.dispatch(
            index,
            [{"role": "system", "content": messages["system"]},
             {"role": "user", "content": messages["user"]}],
            max_output_tokens=MAX_OUTPUT_TOKENS,
            timeout_total_ms=TIMEOUT_TOTAL_MS)
        judgement = judge_acquisition(dispatch.reply,
                                      operation_id=dispatch.operation_id)
        judgement["route"] = dispatch.route
        judgement["model"] = dispatch.model
        judgement["usage"] = dispatch.usage
        judgement["latency_ms"] = dispatch.latency_ms
        judgement["prompt_digest"] = dispatch.prompt_digest
        judgement["provider_fold"] = live.provider_fold or None
        if dispatch.error:
            judgement["acquisition"] = UNUSABLE
            judgement["detail"] = dispatch.error
        dispatches.append(judgement)
        if judgement["acquisition"] != ACQUIRED:
            continue
        verdict = _admit(live, judgement, messages, workdir)
        judgement["eligibility"] = verdict.get("eligibility")
        judgement["reason"] = verdict.get("reason")
        judgement["frozen_state_digest"] = verdict.get("frozen_state_digest")
        judgement["selected_evidence"] = verdict.get("selected_evidence")
        judgement["diagnosis"] = diagnose_refusal(
            {**verdict, "source": judgement["source"]}, _admission_views(
                workdir, "diagnosis-%s" % dispatch.operation_id))
        if verdict.get("eligibility") == channel.ELIGIBLE:
            judgement["eligible"] = True
            acquisition = {**judgement,
                           "live_attributable": True, "eligible": True}
            break

    summary = _adjudication([dict(d, eligible=d.get("eligible", False))
                             for d in dispatches])
    acquisition = dict(acquisition)
    acquisition["live_attributable"] = any(
        d.get("acquisition") == ACQUIRED and d.get("eligible")
        for d in dispatches)

    incumbent_x = int(channel.INCUMBENT_EVIDENCE[0])
    arms: dict = {}
    for role, builder in CONTROL_BUILDERS.items():
        control = builder()
        driven = _run_one(role, control["source"], control["control_id"],
                          control["label"], workdir, role)
        driven["control"] = control
        driven["changed"] = arm_changed_decision(driven, control)
        driven["paired"] = compare(driven["x_probed"], incumbent_x,
                                    split=split, seeds=cohort)
        arms[role] = driven

    if acquisition.get("eligible"):
        driven = _run_one("acquired", acquisition["source"],
                          "e4-acquired-0001", ACQUIRED, workdir, "")
        driven["changed"] = arm_changed_decision(driven)
        driven["paired"] = compare(driven["x_probed"], incumbent_x,
                                    split=split, seeds=cohort)
        arms["acquired"] = driven
    else:
        driven = _run_one("acquired", None, "e4-acquired-0001", ACQUIRED,
                          workdir, "")
        driven["changed"] = {"incumbent_x": incumbent_x, "revised_x": -1,
                             "changed_decision": False,
                             "reached_boundary": False}
        driven["paired"] = {"delta": None, "n": 0, "measured": False,
                            "paired_sd": None, "paired_se": None, "z": None,
                            "split": split, "n_seeds": len(cohort),
                            "x_revised": -1, "x_incumbent": incumbent_x,
                            "mean_revised": None, "mean_incumbent": None}
        arms["acquired"] = driven

    qualification = qualify(arms)
    acquired_arm = arms["acquired"]
    verdict = outcome(acquisition, acquired_arm["changed"],
                      acquired_arm["paired"])
    if not acquisition.get("eligible") and qualification["qualified"]:
        verdict = dict(verdict)
        verdict["benefit"] = False
        verdict["verdict"] = INELIGIBLE_REPORTED
        verdict["blockers"] = list(verdict["blockers"]) + [
            summary["verdict"]]
    else:
        verdict["verdict"] = NO_BENEFIT if not verdict["benefit"] \
            else "benefit"

    return {
        "run_version": RUN_VERSION,
        "frozen": frozen,
        "revision_interface": REVISION_INTERFACE,
        "prompt": {**messages,
                   "digest": _frontier.source_digest(
                       _frontier.canonical(messages))},
        "route": (dispatches[0]["route"] if dispatches else None),
        "model": (dispatches[0]["model"] if dispatches else None),
        "dispatches": dispatches,
        "acquisition": {key: value for key, value in acquisition.items()
                        if key != "source"},
        "acquisition_source": acquisition.get("source"),
        "acquisition_summary": summary,
        "incumbent": {"x": incumbent_x,
                      "evidence": list(channel.INCUMBENT_EVIDENCE),
                      "source_digest": _frontier.source_digest(
                          channel.IMPROVE_LOW_SOURCE)},
        "split": split, "cohort": cohort, "n_seeds": len(cohort),
        "arms": {name: _arm_record(arm) for name, arm in arms.items()},
        "ceiling": ceiling(split, cohort),
        "evidence_ceiling": evidence_ceiling(split, cohort),
        "qualification": qualification,
        "outcome": verdict,
    }


def _admission_views(workdir: Path, name: str = "admission.json") -> list:
    """One real learner view, as the improve step would receive it.

    The view is materialised by the store rather than hand-built, because a
    fixture with the wrong field names parses fine and every step then
    raises inside the child, which the choice reader swallows into an empty
    list - and an empty list makes a revision look like it selected nothing
    rather than like it failed.
    """
    store = _frontier.create_store(
        Path(workdir) / name, namespace=_frontier.NAMESPACE,
        mission=_mission(), authority={"queries": 16, "steps": 12})
    parent = channel.make_control("low")
    store.bind_active(parent)
    view = store.step_view(_frontier.IMPROVE, parent)
    view["experience"] = []
    view["round"] = 1
    return [view]


def _admit(live: "LiveAcquisition", judgement: dict, messages: dict,
            workdir: Path) -> dict:
    """Run a reply through the study's own gate on a real store."""
    store = _frontier.create_store(
        workdir / "admission.json", namespace=_frontier.NAMESPACE,
        mission=_mission(), authority={"queries": 16, "steps": 12})
    parent = channel.make_control("low")
    store.bind_active(parent)
    views = [store.step_view(_frontier.IMPROVE, parent)]
    for view in views:
        view["experience"] = []
        view["round"] = 1
    return acquire(store, judgement["source"], views, arm="acquired",
                   label=ACQUIRED)


def _run_one(role: str, source, control_id: str, label: str,
             workdir: Path, control_role: str) -> dict:
    path = workdir / ("round-%s.json" % role.replace("/", "-"))
    if source is None:
        return {"arm": role, "label": label, "x_probed": -1,
                "observations": [], "candidate_id": "",
                "descendant_strategy": "", "error": (
                    "no revision bytes were acquired for this arm"),
                "frozen_before": {}, "frozen_after": {}, "used": {},
                "grant": {}}
    store = _frontier.create_store(
        path, namespace=_frontier.NAMESPACE, mission=_mission(),
        authority={"queries": 16, "steps": 12})
    parent = channel.make_control("low")
    store.bind_active(parent)
    views = [store.step_view(_frontier.IMPROVE, parent)]
    for view in views:
        view["experience"] = []
        view["round"] = 1
    verdict = acquire(store, source, views, arm=role, label=label,
                      role=control_role)
    driven = drive_arm(path.with_name(path.stem + "-drive.json"), source,
                       role, label, control_id=control_id, verdict=verdict)
    record = {**driven.__dict__}
    record["eligibility"] = verdict.get("eligibility")
    record["reason"] = verdict.get("reason")
    record["selected_evidence"] = verdict.get("selected_evidence")
    record["source_digest"] = _frontier.source_digest(source)
    record["control"] = None
    return record


def _arm_record(arm: dict) -> dict:
    return {key: value for key, value in arm.items()
            if key not in ("control",)}


def live_attributable(evidence: dict) -> bool:
    """Whether the artifact can point at a live call for its acquired arm.

    A report that claims a model did something is only allowed to be written
    if this returns true, and it is checked against the dispatches rather
    than against a flag. A recorded double, a replayed receipt or a
    hand-written reply all fail it, because none of them carries a dispatch
    that the gateway performed.
    """
    for dispatch in evidence.get("dispatches") or []:
        if dispatch.get("acquisition") == ACQUIRED \
                and dispatch.get("eligible") \
                and dispatch.get("operation_id") \
                and dispatch.get("route") \
                and dispatch.get("model") \
                and dispatch.get("source_digest"):
            return True
    return False
