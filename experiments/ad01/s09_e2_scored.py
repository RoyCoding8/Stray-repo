"""A scored dependent variable for the E2 experience contrasts.

`reports/evidence/inv_r1_e2_challenge/RESULT.md` retracts five E2
contrasts because `diagnostic` was a dead field: identical between the
experience arm and the no-experience arm in every condition, so it carried
no signal in either direction. A later pass falsified the "it echoes the
most recent family token" reading that came first, and settled on the
weaker claim — a dead observable, which is a statement about the field and
not about the model.

Nothing here explains why. This is the instrument the retraction asks for
instead: a score that is a property of the *returned policy* rather than of
a label inside the returned text, so that a proposal handed the same
context as another can differ, and a proposal that echoes its context
cannot score.

Two legs, each in [0, 1], summed into a score in [0, 2]:

1. **Evidence.** The same returned bytes are stepped twice, under two
   observations of the same length, and the leg is the fraction of the
   executed action's input values that move between them. The verdict is
   the only thing that changes between the two views, so an action whose
   inputs move has read it and an action whose inputs do not has not. A
   policy that writes its context down and then acts the same way moves
   nothing, which is the point.
2. **Reduction.** The fraction of the task's initial measure that the
   candidate the world produced actually removed, read off the checker's
   own report. This leg was the checker's verdict bit, and it was a
   constant: the oracle that accepts a reducer's trial is the same
   function that grades the output, so every candidate reaching a Reading
   came back `preserved`, the bit could only ever be 1.0, and the
   campaign's one paired contrast was a subtraction of that constant
   against itself. A reducer that returned its input reduces nothing and
   scores 0.0 on this leg; a reducer that found a real reduction scores a
   positive fraction. Neither requires anything of the oracle.
3. **Agreement.** The candidate the world produced is graded by
   `experiments.representation.checkers`, and is then compared against the
   same checker's verdict on an authored control's candidate for the same
   task under the same query budget. The measure rides out beside the
   verdict, because two candidates can share a verdict and still not be the
   same candidate.

Validity is not a third leg. It is a precondition: the returned bytes are
gated by the campaign's own `method_exec.verify_step_source` and stepped in
a child under the real wall, CPU and output limits, and the admitted action
travels the shipped dispatcher into another child. A proposal that cannot
be run is not a policy that scored badly, and it is `unscored`: no score at
all, with a detail naming the stage that stopped. A dispatch that failed
did not produce a worse policy, and a study that read it as zero would be
reporting a transport failure as a result about the model.

The sum is deliberately not normalised. Weighting the agreement leg against
the evidence leg is a pre-registration, not a default, and a module that
picked one would have chosen it on behalf of every study that used it. The
qualitative comparison an E2 contrast needs — does this proposal read its
evidence, and does it agree with the control — is carried by the two legs
separately and by `contract`, which is a word with a rule and never a
number of its own.

One field of the old proposal shape survives, and only as an input. The
scheme's own run under the probe view carries the authored control's method
source under a key the scored run never sees, so a policy that reaches for
it is reaching for the control. The score does not reward the label: the
evidence leg reads the executed inputs, and two proposals differing only in
a label land in the same place.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from . import assessment_profile
from . import method_exec
from . import policy_step
from . import worlds
from experiments.representation.checkers import PRESERVED

SCHEME = "s09-e2-scored/1"

CONTROL_METHOD = "ddmin"
CONTROL_PREFIX = {"software": "seed-sw-", "graph": "seed-gr-"}
REDUCER = {"software": "reduce_software", "graph": "reduce_graph"}
DEFAULT_MAX_QUERIES = 8

# The kinds the STEP ABI admits, and the two that can reach a method
# executor. The contract vocabulary is not in the table: `probe` and `use`
# are what `run_step_out_of_process` refuses, and a scheme that stepped a
# policy written in the contract's names would be running something the
# campaign has already recorded as refused.
STEP_METHOD_KINDS = ("construct_method", "use_method")

MAX_SCORE = 2

# The second leg's bit, and the reason the leg is not the verdict.
#
# `preserved` is a fixpoint of two composed invariants, not a policy
# property. The oracle that accepts a reducer's trial is the same function
# that grades the output, and `reducers.ddmin_reduce`/`greedy_reduce` only
# ever mutate `keep` on a line reading `if probe(trial)["verdict"] ==
# PRESERVED`. So the returned candidate is always either the incumbent task
# or an already-accepted trial, and the verdict of any candidate that
# reaches a Reading is `preserved` by construction. A benefit statistic
# built on that bit can only ever take two values and differs across arms
# only when the evidence leg differs, which made the campaign's one paired
# contrast a subtraction of a constant against itself.
#
# The leg is the checker's *measure* instead: how much of the task's
# initial measure the candidate actually removed. A reducer that returned
# its input scores 0.0 on it and a reducer that found a real reduction
# scores a positive fraction, and the two differ without anything having
# changed about the oracle. Validity stays a precondition and is still not
# a leg: an unscored Reading has no reduction to report, and reports none.
NORMALIZED_REDUCTION = "normalized_reduction"

# Verbatim input fields. They carry the run rather than the evidence: the
# method a policy reaches for, the entry it named, the budget it asked for.
# They differ between the probe run and the scored run and never between
# the two evidence runs, so counting them would have made every policy look
# responsive to a verdict it never saw.
VERBATIM = ("method_source", "source", "entry", "method_id", "max_queries")
VERDICT_FLIP = {"preserved": "not_preserved", "not_preserved": "preserved",
                "invalid": "unknown", "unknown": "invalid"}

PROBE_KEY = "_probe"
PROBE_METHOD = "ddmin"

STEP_TIMEOUT_MS = policy_step.STEP_TIMEOUT_MS
STEP_CPU_SECONDS = policy_step.STEP_CPU_SECONDS
STEP_MAX_OUTPUT_BYTES = policy_step.STEP_MAX_OUTPUT_BYTES

LEG_VALID_ACTION = "valid_action"
LEG_EVIDENCE = "candidate_varies_with_evidence"
LEG_AGREEMENT = "action_agrees_with_control"

CANDIDATE_SITE = "candidate"

PASS = "pass"
FAIL = "fail"
ABSENT = "absent"

UNSCORED_PROPOSAL = "proposal"
UNSCORED_GATE = "gate"
UNSCORED_EXECUTE = "execute"

UNSCORED = "unscored"
TIE = "tie"

CONTRACT_RULE = (
    "Two readings of the same scheme on the same target task. Either "
    "reading that is not scored makes the contrast unscored, because an "
    "absent result cannot be compared with a present one. Otherwise the "
    "leg sums are compared as they stand: the larger wins, and equal sums "
    "are a tie rather than a win."
)


class ScoreRefused(Exception):
    """A proposal that cannot be scored at all."""


# ---------------------------------------------------------------------------
# the proposal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Score:
    """One proposal, held to be scored on one target task.

    `proposal` is the construction response's `entry` source, which is the
    only field of a returned proposal that names bytes. Nothing here
    interprets a label the proposal wrote, and a proposal that carries one
    scores exactly as the policy that carries it would.
    """

    proposal: Mapping[str, Any]
    origin: str
    arm: str
    max_queries: int = DEFAULT_MAX_QUERIES
    control_method: str = CONTROL_METHOD
    scheme: str = SCHEME

    @property
    def source(self) -> str:
        """The bytes this score is about, or nothing.

        A record that says nothing came back says it several ways, and each
        of them has to read as absent rather than as an empty policy: a
        value that means nothing read as a value is the `diagnostic`
        failure in a different costume.
        """
        if not isinstance(self.proposal, Mapping):
            return ""
        source = self.proposal.get("policy_source")
        return source if isinstance(source, str) else ""

    @property
    def digest(self) -> str:
        return _digest(self.source)

    def record(self) -> dict:
        return policy_step.make_policy_artifact(self.source,
                                               origin=self.origin)

    def response(self) -> str:
        """This proposal in the shape a settled construction response has.

        `construct.construct_policy` never hands raw source to its caller,
        so a study cannot be handed this score's proposal without going
        through the same parse a settled response goes through.
        """
        return json.dumps({"entry": self.source, "notes": self.arm},
                          sort_keys=True)

    @classmethod
    def from_response(cls, text: str, max_queries: int = DEFAULT_MAX_QUERIES,
                      *, origin: str, **kwargs) -> "Score":
        """A score over a settled construction response, labelled by its caller.

        `origin` is required rather than defaulted. This classmethod is
        handed response text and nothing else, so it cannot tell a live
        provider's bytes from a recording double's, and it used to assert
        `model-acquired` for whichever it was given. The caller holds the
        receipt, so the caller names the origin; pass
        `construct.acquisition_origin(...)["origin"]` rather than the string.
        """
        return cls({"policy_source": proposal_source(text)}, origin,
                   "response", max_queries, **kwargs)

    def measure(self, task: Mapping[str, Any], observations: Sequence, *,
                eligible_methods: Sequence | None = None,
                remaining: Mapping[str, Any] | None = None,
                authority: Mapping[str, Any]) -> "Reading":
        """Score this policy's bytes on this task, under `authority`.

        `authority` is a required keyword: `{dsn, allocation_id}` for a store
        the caller holds. Measuring a policy means executing it, and executing
        it is the act the executor requires authority for. This used to hold
        none, so every measurement this method returned was an unscored
        reading recorded against the policy.

        The third key, `operation_id`, is derived per execution in `_execute`
        rather than named here. The executor is idempotent on it, so a caller
        naming it would have to get a distinct one per policy per view for the
        measurement to be a measurement rather than a replay of an earlier
        one. Deriving it removes that as something to get right.
        """
        task = dict(task or {})
        task_id = str(task.get("task_id") or "")
        family = str(task.get("family") or "")
        if not task_id or family not in CONTROL_PREFIX:
            raise ScoreRefused(
                "the target task needs a task_id and a family this scheme "
                "has an authored control for; got %r and %r"
                % (task_id, family))
        if not (isinstance(authority, Mapping) and authority.get("dsn")
                and authority.get("allocation_id")):
            raise ScoreRefused(
                "measuring a policy needs a store and an allocation the caller "
                "holds; got %r" % sorted(authority))
        try:
            record = self.record()
            digest = record["artifact"]["source_digest"]
        except (TypeError, ValueError) as malformed:
            return _unscored(self, task, UNSCORED_GATE,
                             "refused: %s" % malformed)
        if digest != self.digest:
            return _unscored(self, task, UNSCORED_GATE,
                             "the artifact digest is not the digest of the "
                             "bytes this score is about")
        refusal = _gate(self.source)
        if refusal is not None:
            return _unscored(self, task, UNSCORED_GATE, refusal)
        control = _control(task, control_name(task, self.control_method),
                           self.max_queries)
        if control is None:
            return _unscored(self, task, UNSCORED_EXECUTE,
                             "the authored control did not run on %s"
                             % task_id)
        views = build_views(task, observations,
                            eligible_methods=eligible_methods,
                            remaining=remaining)
        run = _run(self, record, views, digest, authority)
        if run is None:
            return _unscored(self, task, UNSCORED_EXECUTE,
                             "the returned bytes admitted no action that "
                             "reaches a method executor")
        evidence = _evidence(run["scored"], run["alternate"])
        agreement, reason = _agreement(run["scored"], control)
        graded = _grade(task, run["scored"]["candidate"], raw=True)
        quality = normalized_reduction({"scored": True,
                                        "verdict": graded["verdict"],
                                        "measure": _size(task,
                                                         run["scored"]["candidate"]),
                                        "initial_measure": control["initial_measure"],
                                        "reason": graded["reason"]})
        return Reading(
            scheme=self.scheme, origin=self.origin, arm=self.arm,
            task_id=task_id, family=family,
            control=control_name(task, self.control_method),
            digest=self.digest, executed_source=run["scored"]["executed_source"],
            executed_digest=_digest(run["scored"]["executed_source"]),
            action=run["scored"]["action"], candidate=run["scored"]["candidate"],
            selected_identity=run["scored"]["selected_identity"],
            queries=run["scored"]["queries"], verdict=run["scored"]["verdict"],
            reason=reason, quality=quality,
            query_trace=run["scored"].get("query_trace"),
            evidence=evidence["ratio"], evidence_varied=evidence["varied"],
            evidence_total=len(evidence["sites"]), evidence_sites=evidence["sites"],
            control_inputs=evidence["control_inputs"],
            candidate_digest_scored=evidence["candidate_digest_scored"],
            candidate_digest_alternate=evidence["candidate_digest_alternate"],
            control_verdict=control["verdict"],
            initial_measure=control["initial_measure"],
            candidate_measure=run["scored"]["measure"],
            agreement=agreement,
            score=evidence["ratio"] + quality, scored=True,
            detail="the checker graded the candidate the world produced as "
                   "%s, and the candidate the world produced under flipped "
                   "verdicts %s the one under the arm's own verdicts"
                   % (run["scored"]["verdict"],
                      "differed from" if evidence["varied"] else "matched"))


def proposal_source(text: str) -> str:
    """The returned bytes, through the construction response parser."""
    from . import packet
    source, problem = packet.parse_construction_response(text)
    if problem:
        raise ScoreRefused("proposal does not parse: %s" % problem)
    return source


def score_response(text: str, task: Mapping[str, Any], observations: Sequence,
                   *, max_queries: int = DEFAULT_MAX_QUERIES,
                   origin: str, arm: str = "response",
                   eligible_methods: Sequence | None = None,
                   remaining: Mapping[str, Any] | None = None,
                   authority: Mapping[str, Any],
                   **kwargs) -> Reading:
    """Score one returned response against the named methods.

    `origin` is required. It had a default of `model-acquired`, which meant
    a caller that had a receipt in hand and simply did not pass it got a
    reading claiming a live provider wrote bytes it may not have. The
    function is handed response text, so it cannot earn the label; the
    caller holds the receipt and has to name it.

    `eligible_methods` and `remaining` are named rather than swept into
    `**kwargs`. They were forwarded to the `Score` constructor, which does
    not take them: a caller passing the family's controls got a TypeError,
    and a caller who left them out got a view with `eligible_methods: []`.
    Every policy then read an empty list, took its stop branch, and was
    reported as "admitted no action that reaches a method executor" — the
    same refusal whether the caller passed the argument wrongly or not at
    all. The kwargs that do belong to the constructor still go there.
    """
    return Score({"policy_source": proposal_source(text)}, origin, arm,
                 max_queries, **kwargs).measure(
                     task, observations,
                     eligible_methods=eligible_methods,
                     remaining=remaining,
                     authority=authority)


# ---------------------------------------------------------------------------
# the views
# ---------------------------------------------------------------------------


def build_views(task: Mapping[str, Any], observations: Sequence, *,
                eligible_methods: Sequence | None = None,
                remaining: Mapping[str, Any] | None = None,
                control_method: str = CONTROL_METHOD) -> dict:
    """The views one returned policy is stepped under.

    `scored` and `alternate` are the arm's own view, twice, with each
    verdict flipped between them. Nothing else moves, so they are the same
    length and the same volume, and an action that differs between them
    differs because it read the verdicts.

    `probe` is the scored view plus one key, and it exists so the authored
    control can be executed by the same path a policy's own method is
    executed by rather than by a second path that could drift from it. It
    is not a view any study holds for the policy under test, and a policy
    that would rather be handed the control is free to ask twice — which is
    the `diagnostic` field's honest use, and the only one.
    """
    scored = policy_step.materialize_view(
        task=task, observations=list(observations or []), open_questions=[],
        last_result=None, eligible_methods=list(eligible_methods or []),
        remaining=dict(remaining or {"steps": 1}))
    probe = dict(scored)
    probe[PROBE_KEY] = {"method_source": inline_method(task, control_method),
                        "control": control_name(task, control_method)}
    return {"probe": probe, "scored": scored, "alternate": _flipped(scored)}


def _flipped(view: Mapping[str, Any]) -> dict:
    alternate = dict(view)
    alternate["observations"] = [
        dict(row, verdict=VERDICT_FLIP.get(str(row.get("verdict")),
                                           row.get("verdict")))
        for row in view.get("observations") or []]
    return alternate


def inline_method(task: Mapping[str, Any], method: str) -> str:
    """The authored control as the source the dispatcher executes.

    Written against the child's own namespace, where `reducers` is bound by
    the member driver. `s09_bound_use_proof.SEED_METHOD_SOURCE` is the same
    line, so the two controls cannot quietly diverge: both are the reducer
    under a name.
    """
    family = str((task or {}).get("family") or "")
    if family not in REDUCER:
        raise ScoreRefused("no authored method for family %r" % family)
    return ("def ENTRY(task, oracle, max_queries=16):\n"
            "    return reducers.%s(task, oracle, method=%r,"
            " max_queries=max_queries)\n" % (REDUCER[family], method))


def control_name(task: Mapping[str, Any], method: str = CONTROL_METHOD) -> str:
    family = str((task or {}).get("family") or "")
    if family not in CONTROL_PREFIX:
        raise ScoreRefused("no authored control for family %r" % family)
    return "%s%s" % (CONTROL_PREFIX[family], method)


def control_candidates() -> dict:
    """The authored controls a study may compare against, by family.

    Both names, so a reader can see which one a run used. They are not
    twins: on a dev software target ddmin reaches 3 of 14 ops and greedy
    stops at 7, so agreeing with one is not agreeing with the other.
    """
    return {family: {method: "%s%s" % (prefix, method)
                     for method in ("ddmin", "greedy")}
            for family, prefix in sorted(CONTROL_PREFIX.items())}


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------


def _gate(source: str) -> str | None:
    """The campaign's own source gate, or the refusal it returned.

    The message is kept verbatim rather than a boolean, so an unscored
    reading can name the rule that stopped it.
    """
    try:
        method_exec.verify_step_source(source, policy_step.STEP_ENTRY)
    except method_exec.MethodExecutionError as refusal:
        return str(refusal)
    return None


def _run(score: Score, record: dict, views: Mapping[str, Any],
         digest: str, authority: Mapping[str, Any]) -> dict | None:
    """Step the bytes under each view, and admit what each view admitted.

    The probe run is run first and the run that is scored is the scheme's
    own view, so the control's search space cannot be the run a study
    holds. Every boundary is the campaign's: the step runs in a child under
    the limits `policy_step` already carries, and the action is admitted by
    `assessment_profile.dispatch`, which refuses an action whose target is
    not the task in scope or whose method cannot run, and runs the method in
    a further child.

    Each view gets its own operation identity, derived from the view's own
    digest. The executor reads back the first receipt rather than executing
    again for a repeated id, so a shared identity would return the probe's
    action under every view and the comparison this function exists to make
    would compare a run with itself.
    """
    runs = {}
    for name in ("probe", "scored", "alternate"):
        runs[name] = _execute(score, record, views[name], digest,
                              authority, name)
    if runs["probe"] is None or runs["scored"] is None \
            or runs["alternate"] is None:
        return None
    return runs


def _execute(score: Score, record: dict, view: Mapping[str, Any],
             digest: str, authority: Mapping[str, Any],
             label: str = "step") -> dict | None:
    """One step under one view, or `None` with the reason it did not run.

    The step is a real execution of policy source, so it runs under a store,
    an allocation and an operation identity like every other one. It does not
    get them by default: `authority` is a required argument, because a caller
    that has none has no honest execution to report, and this used to call the
    executor with none, catch the refusal it returned, and record every
    reading as `unscored: execute`. Eighteen tests in `test_s09_e2_scored.py`
    were reading that as a property of the policies under test.

    The operation identity is derived from the policy digest, the view digest
    and `label`. The executor is idempotent on that key, so a repeated step
    under a repeated identity would read back the first receipt rather than run
    again. Deriving it here means a caller supplies a store and gets
    executions that are distinct wherever the work is, and identical wherever
    the work is the same.

    A refusal that is about the bytes (a refused source, a malformed step) is
    still a `None` here, because an unscored reading is the honest stage for a
    policy that will not run. A refusal that is about the authority is not
    swallowed: it propagates, because a caller that reached this without
    authority has a bug and a study that read `None` would record it as the
    policy's failure.
    """
    if not (isinstance(authority, Mapping) and authority.get("dsn")
            and authority.get("allocation_id")):
        raise ScoreRefused(
            "a step needs a store and an allocation the caller holds; got %r"
            % sorted(authority))
    operation_id = "e2-%s-%s-%s" % (
        digest[:12], _candidate_digest(view)[:12], label)
    try:
        stepped = method_exec.run_step_out_of_process(
            score.source, dict(view), {}, entry=policy_step.STEP_ENTRY,
            timeout_ms=STEP_TIMEOUT_MS, cpu_seconds=STEP_CPU_SECONDS,
            max_output_bytes=STEP_MAX_OUTPUT_BYTES,
            dsn=str(authority["dsn"]),
            allocation_id=str(authority["allocation_id"]),
            operation_id=operation_id)
    except method_exec.MethodExecutionError as exc:
        if str(exc).startswith("refused: execution needs explicit "
                               "authority and identity"):
            raise
        return None
    action = dict(stepped.get("action") or {})
    if not action or action.get("kind") not in STEP_METHOD_KINDS:
        return None
    if action.get("target") != \
            str((view.get("task_content") or {}).get("task_id") or ""):
        return None
    effect = _dispatch(record, action, digest, authority, label)
    if not effect.get("accepted") or effect.get("candidate") is None:
        return None
    task = worlds.load_task(worlds.FROZEN_DIR, str(action["target"]))
    return {"action": action, "candidate": effect["candidate"],
            "queries": int(effect.get("queries") or 0),
            "selected_identity": str(effect.get("selected_identity") or ""),
            "verdict": _grade(task, effect["candidate"]),
            "measure": _size(task, effect["candidate"]),
            "query_trace": effect.get("query_trace"),
            "executed_source": _executed_source(action)}


def _dispatch(record: dict, action: dict, digest: str,
              authority: Mapping[str, Any],
              label: str = "step") -> dict:
    """Admit one action through the shipped dispatcher.

    `dsn` and `allocation_id` go to the dispatcher because admitting a
    `construct_method` or `use_method` runs the named method in a further
    child, and that execution is refused without them the same way the step
    was. It held none here, so every admission failed with `owner: none` and
    the reading came back unscored even once the step itself had authority.

    `label` goes into the session so each view is its own dispatcher session.
    The broker's operation identity is derived from the session, the step index
    and the action kind, so one shared session ran all three views under one
    identity, and the second and third came back refused as replays.
    """
    task_id = str(action["target"])
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    requested = dict(action.get("requested_resources") or {})
    inputs = dict(action.get("inputs") or {})
    ceiling = inputs.get("max_queries")
    if type(ceiling) is not int or ceiling < 0:
        ceiling = 0
    ctx = assessment_profile.make_ctx(
        candidate_digest=digest,
        scope={"family": str(task.get("family") or ""), "task_ids": [task_id]},
        session="s09-e2-scored-%s" % label,
        remaining={"queries": max(int(requested.get("queries", 0)), ceiling),
                   "model_calls": int(requested.get("model_calls", 0))})
    return assessment_profile.dispatch(
        profile_name=assessment_profile.DEVELOPMENT, record=record, task=task,
        action=action, ctx=ctx, dsn=str(authority["dsn"]),
        allocation_id=str(authority["allocation_id"]))


def _control(task: Mapping[str, Any], capability_id: str,
             max_queries: int) -> dict | None:
    """The authored control, executed and graded, never simulated.

    `seeds.run_seed` is the campaign's own reducer and the candidate it
    returns goes to the same `checkers` entry point the policy's candidate
    goes to, so the two are graded by one implementation rather than by
    two that agree today.
    """
    from . import seeds
    capability = next((item for item in seeds.SEED_CAPABILITIES
                       if item["capability_id"] == capability_id), None)
    if capability is None or capability["family"] != task.get("family"):
        return None
    try:
        result = seeds.run_seed(capability, task, max_queries=max_queries)
    except Exception:
        return None
    report = _grade(task, result["candidate"], raw=True)
    return {"candidate": result["candidate"],
            "queries": int(result.get("queries") or 0),
            "verdict": report["verdict"], "reason": report["reason"],
            "initial_measure": int(report["initial_measure"] or 0),
            "measure": int(report["measure"] or 0),
            "executed_source": capability_id}


def _grade(task: Mapping[str, Any], candidate: Any,
           raw: bool = False) -> Any:
    from experiments.representation import checkers
    if task.get("family") == "software":
        report = checkers.check_software(task, candidate)
    else:
        report = checkers.check_graph(task, candidate)
    return report if raw else str(report["verdict"])


def _size(task: Mapping[str, Any], candidate: Mapping[str, Any]) -> int:
    if not isinstance(candidate, dict):
        return 0
    if task.get("family") == "software":
        return len(candidate.get("ops") or [])
    return len(candidate.get("vertices") or []) + len(candidate.get("edges") or [])


def _executed_source(action: Mapping[str, Any]) -> str:
    inputs = dict(action.get("inputs") or {})
    return str(inputs.get("method_source") or inputs.get("source")
               or inputs.get("method_id") or "")


# ---------------------------------------------------------------------------
# the legs
# ---------------------------------------------------------------------------


def _evidence(scored: Mapping[str, Any], alternate: Mapping[str, Any]) -> dict:
    """Whether the policy's decision reached the world.

    The two runs are the same policy under the same view except that every
    observation's verdict is flipped, and nothing else about the view is.
    So a candidate that moved moved because the policy read the verdict and
    re-routed on it.

    The site is the candidate the world produced, not the action's inputs.
    An input is a claim the policy made; a candidate is a reduction the
    method ran in a child process. Comparing inputs measured the claim, so
    any policy that copied a verdict into a key it had just been handed
    scored the full evidence leg while deciding nothing, and a policy that
    read and re-routed scored zero because the two fields that can actually
    move the candidate, `method_id` and `max_queries`, are the two the
    `VERBATIM` list excludes. That inversion is the defect: the leg
    rewarded the echo and refused the reader.

    The candidate is also the only site that cannot be gamed by writing.
    `assessment_profile._resolve_method` builds the candidate from the task
    and from `method_id`/`max_queries`; it refuses a policy-supplied
    `candidate` outright, so no policy can put its own text into the thing
    being compared. An action input is writable by the policy, so an input
    is not a witness to anything.
    """
    first = scored["candidate"]
    second = alternate["candidate"]
    first_digest, second_digest = _candidate_digest(first), \
        _candidate_digest(second)
    varied = 1 if first_digest != second_digest else 0
    return {"varied": varied, "total": 1, "sites": [CANDIDATE_SITE],
            "ratio": float(varied),
            "scored_inputs": dict(scored["action"].get("inputs") or {}),
            "alternate_inputs": dict(alternate["action"].get("inputs") or {}),
            "control_inputs": _without_verbatim(
                dict(scored["action"].get("inputs") or {})),
            "candidate_digest_scored": first_digest,
            "candidate_digest_alternate": second_digest}


def _without_verbatim(inputs: Mapping[str, Any]) -> dict:
    return {name: value for name, value in inputs.items()
            if name not in VERBATIM}


def _agreement(executed: Mapping[str, Any],
               control: Mapping[str, Any]) -> tuple:
    """Whether the candidate the world produced agrees with the control's.

    Agreement is measured on the checker's verdict for the executed
    candidate, never on the action that produced it: a policy that differs
    from the control in every input can still land on the same reduction,
    and one that differs in nothing can still be refused. The measure is
    named when the two disagree, because a shared verdict and a shared
    candidate are not the same claim.
    """
    reason = ("the checker graded the candidate %s and the authored "
              "control %s" % (executed["verdict"], control["reason"]))
    if executed["verdict"] != control["verdict"]:
        reason += ("; the policy's candidate measured %d against the "
                   "control's %d" % (executed["measure"],
                                     control["measure"]))
    return (PASS if executed["verdict"] == control["verdict"] else FAIL,
            reason)


def normalized_reduction(report: Mapping[str, Any]) -> float:
    """The fraction of the initial measure a graded report removed.

    Written on the checker's own report dict — `verdict`, `measure`,
    `initial_measure`, `reason` — because that is the shape both a Reading
    and an experience record hold, so the benefit leg is one function read
    from two places rather than two copies of one rule.

    An unscored report, an unpreserved verdict, or a zero initial measure
    are all 0.0 and are told apart by `scored` and `verdict` beside it. None
    of them is a division, and none of them is a claim that the policy did
    no work.
    """
    if not report.get("scored", True) or report.get("verdict") != PRESERVED:
        return 0.0
    initial = report.get("initial_measure") or 0
    if not initial:
        return 0.0
    return (int(initial) - int(report.get("measure") or 0)) / int(initial)


# ---------------------------------------------------------------------------
# the reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """One proposal, measured on one target task under one scheme."""

    scheme: str
    origin: str
    arm: str
    task_id: str
    family: str
    control: str
    digest: str
    executed_source: str
    executed_digest: str
    action: dict | None
    candidate: dict | None
    selected_identity: str
    queries: int
    verdict: str
    reason: str
    quality: float
    evidence: float
    evidence_varied: int
    evidence_total: int
    evidence_sites: tuple
    control_inputs: dict
    candidate_digest_scored: str
    candidate_digest_alternate: str
    control_verdict: str
    initial_measure: int
    candidate_measure: int
    agreement: str
    score: float
    scored: bool
    detail: str
    # The questions the admitted method actually asked, in order, each with
    # the candidate's digest and the verdict and reason the checker graded
    # it. `queries` says how many; this says what. It is `None` when the
    # method ran in process rather than under a host-side walk, and `[]`
    # would be the false claim that it ran and asked nothing.
    query_trace: list | None = None

    @property
    def normalized_reduction(self) -> float:
        return normalized_reduction(self.as_report())

    def as_report(self) -> dict:
        """This Reading as the checker's own report shape.

        `normalized_reduction` is one function over one report dict, and an
        experience record holds that same shape. This is the adapter between
        them, so the benefit leg is not a rule restated per holder.
        """
        return {"scored": self.scored, "verdict": self.verdict,
                "measure": self.candidate_measure,
                "initial_measure": self.initial_measure, "reason": self.reason}

    def leg_status(self) -> dict:
        if not self.scored:
            return {LEG_VALID_ACTION: ABSENT, LEG_EVIDENCE: ABSENT,
                    LEG_AGREEMENT: ABSENT}
        return {LEG_VALID_ACTION: PASS,
                LEG_EVIDENCE: PASS if self.evidence_varied else FAIL,
                LEG_AGREEMENT: self.agreement}

    def as_dict(self) -> dict:
        return {"scheme": self.scheme, "origin": self.origin,
                "arm": self.arm, "task_id": self.task_id,
                "family": self.family, "control": self.control,
                "digest": self.digest,
                "executed_digest": self.executed_digest,
                "executed_source": self.executed_source,
                "action": self.action, "candidate": self.candidate,
                "selected_identity": self.selected_identity,
                "queries": self.queries, "verdict": self.verdict,
                "reason": self.reason, "quality": self.quality,
                "evidence": self.evidence,
                "evidence_varied": self.evidence_varied,
                "evidence_total": self.evidence_total,
                "evidence_sites": list(self.evidence_sites),
                "control_inputs": self.control_inputs,
                "candidate_digest_scored": self.candidate_digest_scored,
                "candidate_digest_alternate": self.candidate_digest_alternate,
                "control_verdict": self.control_verdict,
                "initial_measure": self.initial_measure,
                "candidate_measure": self.candidate_measure,
                "normalized_reduction": self.normalized_reduction,
                "agreement": self.agreement, "score": self.score,
                "scored": self.scored, "detail": self.detail,
                "query_trace": self.query_trace}


def _unscored(score: Score, task: Mapping[str, Any], stage: str,
              reason: str) -> Reading:
    return Reading(
        scheme=score.scheme, origin=score.origin, arm=score.arm,
        task_id=str(task.get("task_id") or ""),
        family=str(task.get("family") or ""), control="", digest=score.digest,
        executed_source="", executed_digest="", action=None, candidate=None,
        selected_identity="", queries=0, verdict="", reason="", quality=0.0,
        evidence=0.0, evidence_varied=0, evidence_total=0, evidence_sites=(),
        control_inputs={}, candidate_digest_scored="",
        candidate_digest_alternate="", control_verdict="", initial_measure=0,
        candidate_measure=0, agreement=ABSENT, score=0.0, scored=False,
        detail="unscored: %s: %s" % (stage, reason))


# ---------------------------------------------------------------------------
# the contrast
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Contract:
    """The word a study records for two readings, derived and not asserted."""

    outcome: str
    left_arm: str
    right_arm: str
    left_score: float
    right_score: float
    reason: str
    rule: str = CONTRACT_RULE

    def as_dict(self) -> dict:
        return {"outcome": self.outcome, "left_arm": self.left_arm,
                "right_arm": self.right_arm, "left_score": self.left_score,
                "right_score": self.right_score, "reason": self.reason,
                "rule": self.rule}


def contract(left: Reading, right: Reading) -> Contract:
    """Compare two readings of the same scheme on the same task.

    An unscored reading is not a bad reading. It is an absent one, and an
    absent result cannot be compared with a present one, so a pair with one
    missing is `unscored` and names which arm is missing. A tie is a tie:
    the campaign has two recorded ties already and refused to break them by
    hand, and this is the third place that rule would otherwise lapse.
    """
    if left.task_id != right.task_id or left.scheme != right.scheme:
        raise ScoreRefused(
            "two readings of different tasks or different schemes are not "
            "one contrast: %r/%r against %r/%r"
            % (left.task_id, left.scheme, right.task_id, right.scheme))
    if not left.scored or not right.scored:
        missing = [reading.arm for reading in (left, right)
                   if not reading.scored]
        return Contract(
            outcome=UNSCORED, left_arm=left.arm, right_arm=right.arm,
            left_score=left.score, right_score=right.score,
            reason="%s is unscored: %s" % (
                ", ".join(missing),
                "; ".join(reading.detail for reading in (left, right)
                          if not reading.scored)))
    if left.score == right.score:
        return Contract(outcome=TIE, left_arm=left.arm, right_arm=right.arm,
                        left_score=left.score, right_score=right.score,
                        reason="both readings scored %.3f on %s: %s"
                               % (left.score, left.task_id, _legs(left)))
    winner, loser = ((left, right) if left.score > right.score
                     else (right, left))
    return Contract(
        outcome=winner.arm, left_arm=left.arm, right_arm=right.arm,
        left_score=left.score, right_score=right.score,
        reason="%s scored %.3f against %.3f on %s: %s"
               % (winner.arm, winner.score, loser.score, left.task_id,
                  _legs(winner)))


def _legs(reading: Reading) -> str:
    """What the two legs actually read, named so a tie can be interpreted.

    The reduction is named as a fraction of the initial measure rather than
    as a grade. Under the verdict bit this line could only ever have said
    "the checker read preserved", which is why the recorded ties were
    indistinguishable from each other.
    """
    return ("the candidate %s under flipped verdicts, the reduction leg read"
            " %.3f of the initial measure and the agreement leg read %s"
            % ("moved" if reading.evidence_varied else "did not move",
               reading.quality, reading.agreement))


def _digest(source: str) -> str:
    return hashlib.sha256((source or "").encode("utf-8")).hexdigest()


def _candidate_digest(candidate: Any) -> str:
    """One candidate, canonically, so two are comparable by digest.

    A candidate is a JSON structure whose key order is not guaranteed, so it
    is canonicalized before hashing. Comparing the serialized forms instead
    would call two identical reductions different whenever the world built
    them in a different order, and the leg would report a read that never
    happened.
    """
    return _digest(json.dumps(candidate, sort_keys=True, default=repr))
