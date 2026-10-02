"""A second campaign namespace for E2, and the two defects it had to avoid.

`WORKER-STAGE-09-PARALLEL-EXPANSION.md:67` asks for at least two independent
campaign namespaces wherever the first valid campaign leaves supported arms.
`reports/evidence/inv_r1_e2_scored/` is that first namespace, and
`reports/STAGE-09-COMPLETION-MATRIX.md:161` records the second as not run.
This module is it: `inv_r1_e2_replica` shares no store, no operation id, no
allocation and no assessment feedback with `inv_r1_e2_scored`.

The arms replicated are the relevant / none / irrelevant triple, because those
are the only behavioural arms in the first namespace that carry a result on a
scored observable (`readings.json`: three arms, all `scored: true`, all
`score: 1.0`, all `evidence: 0.0`, all `selected: seed-sw-ddmin`). The
retention contrast is arithmetic over a cap sheet and the substitution
contrast re-scores one acquisition twice, so neither is a fresh cohort and
neither is replicated here.

Two defects in the first namespace's apparatus had to be repaired before its
negative could be re-tested, and both are defects of the *instrument*, not of
the model.

**The evidence leg could not be earned.** `s09_e2_scored.VERBATIM` excludes
`method_id` and `max_queries` from the evidence leg's denominator, and the
construction prompt's worked example builds an action whose `inputs` are
exactly `{"method_id", "max_queries"}`. A policy that names a repertoire
member through the shape the prompt shows it therefore has no measured input
site at all, `evidence_total` is 0, and `_evidence` returns `0 / 0 == 0.0`.
The first campaign's `evidence: 0.0` on every arm is that ratio, not a
measurement of a policy that ignored its verdicts. The discrimination the
matrix credits the instrument with — reader 2.0, blind 1.0 — is real, but it
was demonstrated on a policy that also wrote `plan` and `witness` into
`inputs`, a shape no prompt ever asked for. `REFUSES_VERBATIM_ONLY` and
`READS_THE_VERDICT` below are the two policies that separate the repaired leg
under the *prompted* shape, so the replication's own instrument can be shown
to discriminate before any dispatch.

**The verdict flip was a no-op for seed experience.** `VERDICT_FLIP` has no
entry for `unmeasured`, so `_flipped` maps `unmeasured` to itself. Every
experience record `learner.seed_observations` builds carries
`verdict: "unmeasured"`, so for the arms the first campaign actually ran the
"scored" view and the "alternate" view were byte-identical and the evidence
leg had no contrast to measure by construction. Experience with a real
measured verdict is the only experience this campaign admits, and
`require_measurable_verdicts` refuses an arm that carries an unflippable one.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import learner
from . import worlds
from .s09_e2_scored import NORMALIZED_REDUCTION

NAMESPACE = "inv_r1_e2_replica"
ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "reports" / "evidence"
# The evidence directory carries `NAMESPACE`; the durable store names carry
# `STORE_TOKEN`, because `s09_run_isolation.TOKEN_RE` admits only lowercase
# alphanumerics and hyphens and this namespace's label has underscores. Two
# names for one namespace is a naming split, not two namespaces: both are
# derived from this module and neither is ever written by another lane.
STORE_TOKEN = "invr1e2replica"
FAMILY = "software"
WORLD = 0
ARM_RELEVANT = "relevant"
ARM_NONE = "none"
ARM_IRRELEVANT = "irrelevant"
ARMS = (ARM_RELEVANT, ARM_NONE, ARM_IRRELEVANT)

# One cluster is one independent unit under `panel_inventory.CLUSTER_RULE`,
# which is `(family, template)`. Two software templates exist in the frozen
# world, so a software-family replication has two clusters and a minimum
# two-sided sign-sweep p-value of 1/2 whatever the result. Every inferential
# claim in this namespace is therefore descriptive, and `power` says so in
# the artifact rather than in a footnote.
CLUSTER_RULE = "(family, template)"
ALPHA = "descriptive-only"

# The contrast is frozen here, before any dispatch, and `freeze` is the
# content address of the block below. A run that changed an arm, a target or
# a cohort after seeing a score would not reproduce this digest.
COHORT_WORLD = WORLD
SOURCE_SPLIT = "dev"
TARGET_SPLIT = "within"
CONTROL_SPLIT = "transfer"

MAX_QUERIES = 8
DEFAULT_REASONING_EFFORT = "low"
PROBE_MAX_TOKENS = 8
PROBE_OPERATION_SUFFIX = "probe"
RESPONSES_API = "responses"
FREE_ROUTE_MODE = "free"

# One retry per construction, spent only on a dispatch that returned no
# model bytes. Named once because the cap sheet counts it and the run spends
# it, and a cap sheet that counts a different number than the run spends is
# the ledger N-81 failure in a smaller costume.
RETRIES = 1


class ReplicaRefused(Exception):
    """A replication that may not run, named before anything was sent."""


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def contrast_block() -> dict:
    """The core contrast, frozen, as the artifact and the digest read it."""
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    world = membership[str(COHORT_WORLD)]
    return {
        "namespace": NAMESPACE,
        "independent_of": "inv_r1_e2_scored",
        "family": FAMILY,
        "cohort_world": COHORT_WORLD,
        "source_split": SOURCE_SPLIT,
        "target_split": TARGET_SPLIT,
        "control_split": CONTROL_SPLIT,
        "arms": list(ARMS),
        "source_task_ids": list(world[SOURCE_SPLIT][FAMILY]),
        "filler_task_ids": list(world[SOURCE_SPLIT]["graph"]),
        "target_task_ids": list(world[TARGET_SPLIT][FAMILY]),
        "max_queries": MAX_QUERIES,
        "estimator": ESTIMATOR,
        "cluster_rule": CLUSTER_RULE,
        "alpha": ALPHA,
    }


def freeze() -> dict:
    body = contrast_block()
    return {"body": body, "freeze_digest": digest_of(body)}


def digest_of(body: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in body.items() if key != "freeze_digest"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_freeze(frozen: Mapping[str, Any]) -> dict:
    body = dict((frozen or {}).get("body") or {})
    if not body:
        raise ReplicaRefused("the freeze carries no contrast body")
    recorded = str((frozen or {}).get("freeze_digest") or "")
    if digest_of(body) != recorded:
        raise ReplicaRefused(
            "the freeze addresses as %s but records %s, so the contrast was"
            " edited after it was frozen" % (digest_of(body), recorded))
    current = contrast_block()
    if body != current:
        drifted = sorted(k for k in set(body) | set(current) if body.get(k) != current.get(k))
        raise ReplicaRefused(
            "the frozen contrast no longer matches the panel: %s" % ", ".join(drifted))
    return body


# ---------------------------------------------------------------------------
# measured experience
# ---------------------------------------------------------------------------


def _capability(task: Mapping[str, Any]) -> str:
    return "seed-%s-ddmin" % ("sw" if task.get("family") == "software" else "gr")


def _grade(task: Mapping[str, Any], candidate: Any) -> dict:
    """The checker's whole report, not only its verdict.

    The verdict alone is a dead field for a measured observation. The
    reducer that produced the candidate accepted the trial on that same
    verdict, so a row carrying only `preserved` records that the oracle
    answered and nothing about what the answer was. `reason` is the checker's
    own bounded code — `ok-preserved` for a real reduction, `ok-incumbent`
    for the byte-identical one, `witness-lost-agree` for a candidate that
    stood in the relation but dropped the designated witness — and it is
    what separates a record that says the reducer did work from a record
    that says the reducer returned its input.
    """
    from experiments.representation import checkers

    if task.get("family") == "software":
        return dict(checkers.check_software(task, candidate))
    return dict(checkers.check_graph(task, candidate))


def _normalized_reduction(report: Mapping[str, Any]) -> float:
    """The fraction of the task's initial measure the candidate removed.

    The same rule `s09_e2_scored.Reading.normalized_reduction` applies, on
    the checker's report rather than on a Reading: a record only counts as a
    reduction when the checker graded it `preserved`, and an initial measure
    of zero is not a division. It is written once here and read from there
    rather than restated, because the two legs are the same quantity
    measured on the same report and a second copy of the rule is a second
    place for it to drift.
    """
    from . import s09_e2_scored

    return float(s09_e2_scored.normalized_reduction(report))


def measured_observations(source_task_ids: Sequence[str], *,
                          max_queries: int = MAX_QUERIES) -> list:
    """Experience records carrying a verdict a real reducer earned.

    `learner.seed_observations` gives every record `verdict: "unmeasured"`,
    which `_flipped` maps to itself, so an arm built from it is measured
    against a view identical to its own. These records are produced by
    running the authored reducer on each source task and grading the
    candidate with the campaign's own checker, so the verdict is a measured
    quantity and the flip has something to flip.
    """
    from . import seeds

    rows = []
    for task_id in sorted(source_task_ids or []):
        rows.append(_measured_row(task_id, max_queries=max_queries))
    return rows


def _measured_row(task_id: str, *, max_queries: int = MAX_QUERIES,
                  detail: str = "ref o0") -> dict:
    """One experience record, graded by the campaign's own checker.

    `reason` and `reduction` are both carried. `reason` is the checker's
    bounded code and is what tells an `ok-preserved` row from an
    `ok-incumbent` one; `reduction` is the fraction of the task's initial
    measure that the candidate removed, and it is the number the E2
    contrast is computed on. A record carrying only the verdict carried a
    constant, so the contrast it fed was zero by construction.
    """
    from . import seeds

    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    capability = next((item for item in seeds.SEED_CAPABILITIES
                       if item["capability_id"] == _capability(task)), None)
    if capability is None:
        raise ReplicaRefused("no authored capability for %s" % task_id)
    result = seeds.run_seed(capability, task, max_queries=max_queries)
    report = _grade(task, result["candidate"])
    return {"observation_id": "obs-%s-0" % task_id,
            "task_id": task_id,
            "capability_id": "ad01-%s" % task.get("family", ""),
            "verdict": str(report["verdict"]),
            "reason": str(report["reason"]),
            "reduction": _normalized_reduction(report),
            "detail": detail}


def require_measurable_verdicts(observations: Sequence[Mapping[str, Any]]) -> None:
    """Refuse an arm whose verdicts the alternate view cannot change.

    An arm of records the flip leaves alone has no contrast to measure, and
    a leg reported over it is a zero over an empty denominator rather than a
    policy that ignored anything.
    """
    from .s09_e2_scored import VERDICT_FLIP

    unflippable = sorted({
        str(row.get("verdict")) for row in observations or []
        if str(row.get("verdict")) not in VERDICT_FLIP})
    if unflippable:
        raise ReplicaRefused(
            "experience records carry verdicts the alternate view cannot"
            " change: %s" % ", ".join(unflippable))


# ---------------------------------------------------------------------------
# the arms
# ---------------------------------------------------------------------------


def build_arm(name: str, target: Mapping[str, Any], *,
              source_task_ids: Sequence[str], filler_task_ids: Sequence[str],
              visible: Sequence[str],
              budget: Mapping[str, Any] | None = None) -> dict:
    """One arm, with the family bound onto it and the verdicts measured.

    `learner._eligible_methods` reads `arm["family"]`, which `_arm_experience`
    does not set, so an arm built through the shared constructor renders a
    prompt with an empty family and an empty method list. The family is
    bound here, once, for every arm.
    """
    visible = list(visible or [])
    budget = dict(budget or {})
    base = learner.relevant_experience(
        dict(target), list(source_task_ids), visible, budget)
    if name == ARM_NONE:
        return {**learner.no_experience_experience(
            dict(target), list(source_task_ids), visible, budget),
            "family": str(target.get("family") or ""), "observations": []}
    observations = measured_observations(source_task_ids) \
        if name == ARM_RELEVANT \
        else _irrelevant_observations(target, base, filler_task_ids)
    arm = {**base, "family": str(target.get("family") or ""),
           "observations": observations}
    if observations:
        require_measurable_verdicts(observations)
    return arm


def _irrelevant_observations(target: Mapping[str, Any], base: Mapping[str, Any],
                             filler_task_ids: Sequence[str]) -> list:
    """A size-matched, record-count-matched control of a different family.

    `learner.irrelevant_control_for` sizes its control against the relevant
    arm's characters and record count, which is the confound removal the
    first namespace recorded and the one this namespace has to keep. Its
    records carry `verdict: "unmeasured"`, so the verdicts are measured on
    the same filler tasks the control draws from and the `detail` padding is
    re-fitted to the exact character count `irrelevant_control_for` found,
    by the same `_resized` it uses. Re-measuring without re-fitting would
    move the arm off the length the control exists to match.
    """
    relevant = {**base, "family": str(target.get("family") or ""),
                "observations": measured_observations(
                    [str((o or {}).get("task_id")) for o in
                     (base.get("observations") or [])])}
    control = learner.irrelevant_control_for(relevant, list(filler_task_ids))
    observations = list(control.get("observations") or [])
    if not observations:
        return observations
    target_chars = learner._observation_chars(relevant["observations"])
    measured = [_measured_row(str(row.get("task_id") or ""),
                              detail=str(row.get("detail") or ""))
                for row in observations]
    fitted = learner._resized(measured, target_chars)
    if fitted is None:
        raise ReplicaRefused(
            "no measured filler control reaches the relevant arm's %d"
            " characters" % target_chars)
    return fitted


def arms_for(target: Mapping[str, Any], *, source_task_ids: Sequence[str],
             filler_task_ids: Sequence[str],
             visible: Sequence[str]) -> dict:
    return {
        name: build_arm(name, target, source_task_ids=source_task_ids,
                        filler_task_ids=filler_task_ids, visible=visible)
        for name in ARMS}


def prompt_for(name: str, target: Mapping[str, Any], arm: Mapping[str, Any]) -> str:
    """The arm's construction prompt, with the adaptive-inputs sentence.

    `learner.treatment_prompt` is the campaign's own prompt and is used
    unaltered, so the replica and the first namespace send the same bytes up
    to this one added line. The line is added because the scored observable
    excludes `method_id` and `max_queries` from its evidence leg, and the
    prompt's worked example builds an action whose `inputs` are exactly
    those two keys. A policy that can put a verdict into a third key is
    measurable; a policy confined to the example is not. Adding the line is
    a difference from the first namespace and is recorded as one.
    """
    base = learner.treatment_prompt(dict(arm), dict(target), dict(arm))
    return base + "\n" + ADAPTIVE_INPUTS


def prompt_delta() -> dict:
    """The one line this namespace adds, and why it is not a silent change."""
    return {"added_line": ADAPTIVE_INPUTS,
            "reason": "the scored observable's evidence leg reads the"
                      " candidate the world produced under the arm's"
                      " verdicts and under flipped ones, so the decision it"
                      " measures is the method a policy chooses; the line"
                      " asks for that decision rather than for a copy of"
                      " the verdicts into an input key, which earns nothing",
            "first_namespace_prompt": "learner.treatment_prompt unaltered",
            "everything_else": "identical to the first namespace's prompt"}


def eligible_for(target: Mapping[str, Any],
                 repertoire: Any = None) -> list:
    """The method ids a policy on `target` may name.

    With no repertoire this is what it has always been: the two authored
    controls belonging to the target's family, read through
    `s09_e2_scored.control_candidates`, so `CONTROL_PREFIX` stays the
    single reader of the family-to-prefix mapping. Every archived contrast
    in this tree resolves its eligible sets through this call and every one
    of them still resolves to the same two ids.

    Given a repertoire the seeds come first and the arrived members follow,
    and the seeds' order does not move. `control_arm`'s selector refuses a
    member outside `eligible`, and `PROMPTED_SHAPE_READER` reads no further
    than position one, so an arrived member has to be appended rather than
    sorted in or it would silently re-point every policy measured on the
    frozen panel.

    A member refused by `Repertoire` is raised, not dropped. A silently
    dropped member yields a closed eligible set that reads exactly like the
    frozen one, which is the defect `RETENTION_BLOCKER` named and the one
    this parameter exists to remove.
    """
    from . import assessment_profile as profile
    from .s09_e2_scored import control_candidates

    if repertoire is None:
        return list(
            control_candidates()[str(target.get("family"))].values())
    if not isinstance(repertoire, profile.Repertoire):
        raise profile.RepertoireRefused(
            "a repertoire must be assessment_profile.Repertoire, got %r"
            % (type(repertoire).__name__,))
    # The gate decides, and it is asked before the eligible list is built.
    # `Repertoire.eligible_for` alone would silently drop whatever the gate
    # refused, and a dropped member leaves a closed eligible set that reads
    # exactly like the frozen one. That silence is the defect this parameter
    # exists to remove, so the gate runs strict and a refusal is raised
    # rather than swallowed. The strict default is this call's choice and
    # not the type's: a repertoire is the whole collection, and a study
    # asking about a graph target while holding a software member should be
    # told which member did not apply.
    return repertoire.eligible_for(target, strict=True)


# ---------------------------------------------------------------------------
# the instrument
# ---------------------------------------------------------------------------

# The line this namespace adds to the construction prompt, and why it is not
# the line the first one added.
#
# The first version told the model to copy the observation verdicts into a
# `read_verdicts` input key. That was a workaround for the old leg, which
# compared action inputs and excluded `method_id` and `max_queries`, so the
# echoed string was the only site a policy could move. Under the corrected
# leg the copy earns nothing, and asking a model to do it would steer the
# arms toward the one policy shape the instrument cannot tell from a blind
# one.
#
# The line now asks for the decision the leg actually measures: choose the
# method on the strength of what the verdicts say. `method_id` is a
# VERBATIM field and is never counted directly; it is counted only through
# the candidate the world returns from running it.
ADAPTIVE_INPUTS = (
    'Read the verdicts in the observations you are shown, then choose the'
    ' method in "method_id" on the strength of what they say. Naming a'
    ' different method is a decision; copying a verdict into an input key'
    ' is not, and it does not change what the method runs.'
)

# The pair that certifies the instrument: two policies differing by exactly
# the act of reading, and both written in the action shape this line and the
# prompt's worked example hand the model. The discrimination claim no longer
# rests on a policy that wrote keys the prompt never asked for.
READER_ACTORS = ("reader", "echoer")

# The reference reader: it believes an op a preserved observation names is
# the witness, and drops it from its plan. Under flipped verdicts it keeps
# every op. `plan` and `witness` are the two non-verbatim input keys.
#
# This policy is retained, and retained as a measurement, because it is the
# sharpest thing in this file. It reads the verdicts, it re-plans from them,
# and its `plan` and `witness` are not fields any method executor consumes:
# `assessment_profile._resolve_method` builds the candidate from the task
# and from `method_id`/`max_queries` alone. Its candidate is byte-identical
# to the echoer's under both verdict exposures, and under the corrected leg
# it scores the same as a blind policy. A read that never reaches the world
# earns nothing, which is the claim the evidence leg is now making on
# purpose.
#
# It also reaches the method through `eligible_methods` rather than naming
# one. That list is what `eligible_for` resolved through
# `s09_e2_scored.control_candidates`, so the family-to-prefix mapping stays
# single-sourced: `CONTROL_PREFIX` decides what a graph target is asked for
# and this policy cannot disagree with it. And the plan it computes is the
# family's own: `ops` carries software and `edges` carries graph, so a
# policy that indexed `ops` unconditionally raised on a graph task and the
# whole gate returned unscored rather than false.
READS_THE_VERDICT = '''def _kept(view):
    kept = []
    for row in view["observations"]:
        if str(row["verdict"]) == "preserved":
            words = str(row["detail"]).split()
            if len(words) == 2 and words[0] == "ref":
                kept.append(words[1])
    return kept


def _marker(unit):
    if isinstance(unit, dict):
        for key in ("id", "key"):
            if key in unit:
                return str(unit[key])
        return ""
    if isinstance(unit, (list, tuple)):
        return "-".join(str(part) for part in unit)
    return str(unit)


def _witness(view, kept):
    if not kept:
        return -1
    units = view["task_content"].get("ops") or view["task_content"].get("edges")
    for index in range(len(units)):
        if _marker(units[index]) in kept:
            return index
    return -1


def STEP(view, state):
    units = view["task_content"].get("ops") or view["task_content"].get("edges")
    kept = _kept(view)
    witness = _witness(view, kept)
    plan = [index for index in range(len(units)) if index != witness]
    return {"action": {"kind": "use_method",
                       "target": view["task_content"]["task_id"],
                       "inputs": {"method_id": str(
                           (view.get("eligible_methods") or [""])[0]),
                                  "max_queries": 8,
                                  "plan": plan, "witness": witness},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {}}
'''

# The blind twin: the same plan with the reader's two helpers called away, so
# the two differ by the act of reading and by nothing else.
IGNORES_THE_VERDICT = READS_THE_VERDICT.replace("kept = _kept(view)",
                                                "kept = []")

# The prompted shape, doing exactly what a reading model does. It reads the
# verdicts and changes the method it names, which is the most a policy
# confined to the prompt's own action shape can do, and under the corrected
# leg that read has a site: the candidate the world produced differs between
# the two verdict exposures, so this policy scores above an echoer and an
# echoer scoring the same is the defect rather than the result.
#
# The two methods it chooses between come from the view's own
# `eligible_methods`, which `eligible_for` filled through
# `s09_e2_scored.control_candidates`. Naming a `seed-gr-` or a `seed-sw-`
# literal here is what made the gate refuse every graph target, so the
# policy asks the family rather than asserting one.
#
# The predicate stays a membership test for a reason this lane did not
# change. `panel_variation.COUNT_READS_THE_VERDICTS` counts losses instead,
# because on a panel whose stream already holds both verdicts a membership
# test is constant under either exposure and reads nothing. That is a
# documented defect of this reader (`tests/test_ad01_panel_variation.py`,
# `test_a_membership_reader_is_vacuous_on_a_panel_that_varies`), owned by
# that module and not repaired here: the repair belongs with the record that
# reports the panel, and a third copy of the policy in a qualification gate
# would only add a reader to keep in step.
PROMPTED_SHAPE_READER = '''def STEP(view, state):
    verdicts = [str(row.get("verdict", "")) for row in view["observations"]]
    eligible = [str(m) for m in (view.get("eligible_methods") or [])]
    method_id = eligible[0]
    for name in eligible[1:]:
        if "not_preserved" in verdicts:
            method_id = name
    return {"action": {"kind": "use_method", "target": view["task_content"]["task_id"],
                       "inputs": {"method_id": method_id, "max_queries": 8},
                       "evidence_refs": [], "requested_resources": {"queries": 8}},
            "state": {"method_id": method_id}}
'''

# A policy that copies the verdicts into an input key and then acts exactly
# as it would have anyway. It reads nothing and decides nothing; the only
# thing it does is move the string. The corrected leg cannot tell this from
# a blind policy, because the leg compares the two candidates the world
# produced and never the text a policy wrote into its own action. Echoing
# earns nothing, which is the property the leg was rebuilt to have.
ECHOES_WITHOUT_READING = '''def STEP(view, state):
    rows = ",".join([str(o.get("verdict", "")) for o in view.get("observations", [])])
    return {"action": {"kind": "use_method", "target": view["task_content"]["task_id"],
                       "inputs": {"max_queries": 8,
                                  "method_id": str(
                                      (view.get("eligible_methods") or [""])[0]),
                                  "read_verdicts": rows},
                       "evidence_refs": [], "requested_resources": {"queries": 8}},
            "state": {}}
'''

# The same policy, taking its method from the first eligible member and
# otherwise ignoring the view. Two authored controls, not model bytes.
IGNORES_THE_VIEW = '''def STEP(view, state):
    return {"action": {"kind": "use_method", "target": view["task_content"]["task_id"],
                       "inputs": {"max_queries": 8,
                                  "method_id": str(
                                      (view.get("eligible_methods") or [""])[0])},
                       "evidence_refs": [], "requested_resources": {"queries": 8}},
            "state": {}}
'''


def echo_confound(target: Mapping[str, Any], *,
                  relevant: Sequence[Mapping[str, Any]],
                  eligible_methods: Sequence[str],
                  authority: Mapping[str, Any]) -> dict:
    """Whether the evidence leg separates reading from echoing.

    Four cells, two authored policies against two exposures. An echoer and
    an ignorer that are distinguishable under a non-empty experience and
    indistinguishable under an empty one means the leg is measuring whether
    the arm had observations to echo, not whether the policy read them.
    The two legs are also reported separately, because a difference carried
    entirely by the evidence leg is a difference about echoing.

    Under the corrected leg both gaps are 0.0 and the block is the evidence
    that they are, rather than a defect report. The cells are kept because
    the same measurement taken against the input-comparing leg is what
    produced the reversed gap, and a reader who wants to see the
    difference has both numbers in one place.
    """
    from . import s09_e2_scored as scored

    def _score(source: str, observations, arm: str) -> Any:
        return scored.score_response(
            json.dumps({"entry": source}), dict(target), list(observations),
            origin="authored-control", arm=arm,
            eligible_methods=list(eligible_methods), remaining={"steps": 1},
            authority=authority)

    cells = {}
    for arm, observations in (("relevant", list(relevant)), ("none", [])):
        for name, source in (("echoes", ECHOES_WITHOUT_READING),
                             ("ignores", IGNORES_THE_VIEW)):
            reading = _score(source, observations, "%s-%s" % (arm, name))
            cells["%s-%s" % (arm, name)] = {
                "score": reading.score, "quality": reading.quality,
                "evidence": reading.evidence,
                "evidence_total": reading.evidence_total}
    return {
        "cells": cells,
        "leg_separates_reader_from_echoer":
            cells["relevant-echoes"]["score"] > cells["relevant-ignores"]["score"],
        "evidence_leg_is_empty_under_none":
            cells["none-echoes"]["evidence"] == 0.0,
        "echo_gap_relevant": (cells["relevant-echoes"]["score"]
                              - cells["relevant-ignores"]["score"]),
        "echo_gap_none": (cells["none-echoes"]["score"]
                          - cells["none-ignores"]["score"]),
        "quality_is_identical": (cells["relevant-echoes"]["quality"]
                                 == cells["none-echoes"]["quality"]),
        "verdict": "echoing and ignoring score the same under both exposures,"
                   " because the leg reads the candidate the world produced"
                   " and neither policy changes what the method runs; a"
                   " policy that reads the verdicts and re-routes scores"
                   " above both of them",
    }


def qualify_instrument(target: Mapping[str, Any], observations: Sequence[Mapping[str, Any]],
                       *, eligible_methods: Sequence[str],
                       authority: Mapping[str, Any]) -> dict:
    """Show the repaired leg separates a reader from an echoer.

    Run before any dispatch and without a model. A replication that re-tested
    a negative with an instrument that cannot produce a positive would find
    zero again and read it as a confirmation, so the instrument has to be
    shown to discriminate before its verdict is trusted.

    `authority` is `{dsn, allocation_id}` for a store the caller holds. Every
    policy here is stepped by `Score.measure`, which executes policy source
    and so cannot run without one. This qualification scored five policies
    with none and read every one of them as unscored, so the discrimination it
    was written to demonstrate was never demonstrated.

    The gate is reader-above-echoer, and it is strict about that ordering
    rather than about a ratio. Under the corrected leg the reader re-routes
    its method on the verdicts and the world returns a different candidate,
    while the echoer moves a string and returns the same one; if that
    ordering ever inverts, the run refuses rather than reporting a number
    the instrument earned by echoing.
    """
    from . import s09_e2_scored as scored

    rows = {}
    for name, source in (("reader", PROMPTED_SHAPE_READER),
                         ("blind", IGNORES_THE_VIEW),
                         ("prompted-shape-reader", PROMPTED_SHAPE_READER),
                         ("echoer", ECHOES_WITHOUT_READING),
                         ("plan-only-reader", READS_THE_VERDICT)):
        reading = scored.score_response(
            json.dumps({"entry": source}), dict(target), list(observations),
            origin="authored-control", arm=name,
            eligible_methods=list(eligible_methods), remaining={"steps": 1},
            authority=authority)
        rows[name] = reading_row(name, reading)
    separated = (rows["reader"]["scored"] and rows["echoer"]["scored"]
                 and rows["reader"]["score"] > rows["echoer"]["score"])
    return {
        "reader": rows["reader"], "blind": rows["blind"],
        "prompted_shape_reader": rows["prompted-shape-reader"],
        "echoer": rows["echoer"],
        "plan_only_reader": rows["plan-only-reader"],
        "separates_reader_from_blind": separated,
        "prompted_shape_earns_evidence":
            rows["prompted-shape-reader"]["evidence"] > 0.0,
        "note": "the leg reads the candidate the world produced under the"
                " arm's own verdicts and under flipped ones, so a read earns"
                " it only if it changes what the method runs. The plan-only"
                " reader is the row that carries the earlier defect: it"
                " reads the verdicts and re-plans, its plan reaches no"
                " executor, and it scores beside an echoer. A read that does"
                " not reach the world is not evidence of anything.",
        "echo_confound": echo_confound(
            target, relevant=observations,
            eligible_methods=eligible_methods, authority=authority),
    }


# ---------------------------------------------------------------------------
# the pairing
# ---------------------------------------------------------------------------

# The repository's paired split-half estimator, reused rather than rewritten.
# `improve_channel.ESTIMATOR` names it; `learner_revision.paired` is its
# implementation, and both are imported at call time so a report carrying a
# delta carries the string that says which estimator produced it.
#
# The string names what `paired_report` computes, and it is corrected here.
# The old one claimed "paired best-reachable vs incumbent" while the code
# subtracted one arm's `score` from the other's: no reachability was
# computed and no incumbent was named, so the report described an estimator
# it did not run. What runs is a per-target-task paired difference of
# `normalized_reduction` — the fraction of the task's initial measure the
# world-produced candidate removed — between the named treatment and control
# arms, alongside the decision vector each arm chose.
ESTIMATOR = ("paired per-task normalized_reduction difference, with the"
             " decision vector reported beside it")


def paired_differences(treatment: Sequence[float], control: Sequence[float]) -> dict:
    """One paired difference with its own standard error, or no measurement.

    `learner_revision.paired` is the existing estimator and is not
    reimplemented here. An unpaired or empty member is not a zero: it is an
    absent reading, and an absent reading is carried through to the report
    rather than averaged away.
    """
    from . import learner_revision

    if len(treatment) != len(control):
        raise ReplicaRefused(
            "a paired difference needs one reading per arm: %d against %d"
            % (len(treatment), len(control)))
    return learner_revision.paired(list(treatment), list(control))


def sign_flip_p(deltas: Sequence[float]) -> dict:
    """The two-sided sign sweep over paired differences, and its floor.

    One cluster is one independent unit. With two software clusters the
    smallest attainable p-value is 1/2, so this returns a p-value that is
    never small enough to make an inferential claim, and says so.
    """
    from fractions import Fraction

    from . import s09_study_protocol

    n = len(deltas or [])
    minimum = s09_study_protocol.minimum_sign_flip_p(n)
    return {
        "n_pairs": n,
        "nonzero_pairs": sum(1 for d in deltas if d),
        "minimum_p": (None if minimum is None else str(minimum)),
        "required_clusters_at_alpha_1_20": s09_study_protocol
            .minimum_clusters_for_alpha(Fraction(1, 20)),
        "alpha": ALPHA,
        "corrected": False,
        "note": "descriptive: the frozen panel offers two software"
                " (family, template) clusters, whose minimum two-sided"
                " sign-sweep p-value is 1/2, so no p-value this contrast"
                " can produce is below the 1/20 the protocol names",
    }


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Acquired:
    arm: str
    task_id: str
    operation_id: str
    prompt_chars: int
    digest: str
    source_chars: int
    parse_problem: str
    detail: str
    attempt: int = 0

    def as_dict(self) -> dict:
        return {"arm": self.arm, "task_id": self.task_id,
                "operation_id": self.operation_id,
                "prompt_chars": self.prompt_chars,
                "response_digest": self.digest,
                "source_chars": self.source_chars,
                "parse_problem": self.parse_problem,
                "attempt": self.attempt,
                "detail": self.detail}


def campaign_ids() -> dict:
    """The durable names this namespace mints, all under its own root.

    A second namespace that reused `inv_r1_e2_scored`'s operation ids would
    collide in any shared store, and a collision reads as a replay of the
    first campaign's receipt rather than as a fresh dispatch.
    """
    from . import s09_run_isolation

    return {
        "study_root": s09_run_isolation.study_root_for(STORE_TOKEN),
        "campaign_id": s09_run_isolation.campaign_for(STORE_TOKEN),
        "allocation_id": s09_run_isolation.allocation_for(STORE_TOKEN),
    }


def rerun_ids(suffix: str) -> dict:
    """Durable names for a corrected-instrument re-run of the same contrast.

    The re-run tests the same frozen contrast under a different scorer, so
    reusing `campaign_ids` would mint the same operation ids and the same
    allocation. In a store that outlives one process that reads as a replay
    of the first campaign's receipts rather than as the dispatch it is, and
    the prior run's receipts are exactly the ones this re-run exists to
    contradict. The suffix is checked by `s09_run_isolation.TOKEN_RE`, so a
    malformed one refuses before anything is sent.
    """
    from . import s09_run_isolation

    token = "%s%s" % (STORE_TOKEN, suffix)
    s09_run_isolation._checked_token(token)
    return {
        "study_root": s09_run_isolation.study_root_for(token),
        "campaign_id": s09_run_isolation.campaign_for(token),
        "allocation_id": s09_run_isolation.allocation_for(token),
    }


def operation_id_for(campaign_id: str, task_id: str, arm: str,
                     attempt: int = 0) -> str:
    """One construction dispatch, named by the replica's own campaign."""
    stem = "%s-construct-%s-%s" % (campaign_id, task_id, arm)
    return stem if not attempt else "%s-c%d" % (stem, attempt)


def acquire_one(dsn: str, *, campaign_id: str, allocation_id: str, arm: str,
                task_id: str, prompt: str, gateway: Any, model: str,
                max_output_tokens: int, attempt: int = 0) -> Acquired:
    """One construction dispatch through the durable owner, then a parse.

    The call goes through `broker.ensure_operation` and
    `broker.dispatch_operation`, so the reservation, the operation row, the
    receipt and the exposure all exist in the durable store before and after
    this call. A dispatch that comes back empty is recorded as an empty
    dispatch with `sha256("")` and a parse problem, which is what the
    retracted `inv_r1_e2_relevance` campaign filed as a difference.
    """
    from settlement import broker
    from settlement.common import ResultCode

    from . import packet
    from .trajectory import reasoning_effort

    operation_id = operation_id_for(campaign_id, task_id, arm, attempt)
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": int(max_output_tokens),
                 "deadline_ms": 300_000,
                 "reasoning_effort": reasoning_effort()},
        allocation_id=allocation_id)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise ReplicaRefused("construction not admitted: %s" % ensured.detail)
    broker.dispatch_operation(dsn, operation_id, launchers={}, gateway=gateway)
    settled = _settled_text(dsn, operation_id)
    digest = hashlib.sha256((settled or "").encode("utf-8")).hexdigest()
    if settled is None:
        return Acquired(arm=arm, task_id=task_id, operation_id=operation_id,
                        prompt_chars=len(prompt), digest=digest,
                        source_chars=0,
                        parse_problem="no settled response",
                        detail="the dispatch left no successful receipt",
                        attempt=attempt)
    source, problem = packet.parse_construction_response(settled)
    return Acquired(arm=arm, task_id=task_id, operation_id=operation_id,
                    prompt_chars=len(prompt), digest=digest,
                    source_chars=len(source or ""), parse_problem=problem,
                    detail="", attempt=attempt)


def _settled_text(dsn: str, operation_id: str) -> str | None:
    from psycopg.rows import dict_row

    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s"
                        " AND receipt_identity = %s AND outcome = 'success'",
                        (operation_id, "gw:%s" % operation_id))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        return None
    return str(dict(row.get("content") or {}).get("text", ""))


def acquire_with_retry(dsn: str, *, campaign_id: str, allocation_id: str,
                       arm: str, task_id: str, prompt: str, gateway: Any,
                       model: str, max_output_tokens: int,
                       retries: int = RETRIES) -> tuple:
    """Dispatch, and retry once on a dispatch that returned no model bytes.

    A lost response is preserved as a null, never as a worse policy and never
    as a run-killing exception. The first empty attempt rides out in the
    record beside the second, so a reader sees that a retry happened rather
    than that a first answer was quietly replaced. The retry is the
    cap sheet's declared allowance, and it is spent only on emptiness.
    """
    attempts = [acquire_one(
        dsn, campaign_id=campaign_id, allocation_id=allocation_id, arm=arm,
        task_id=task_id, prompt=prompt, gateway=gateway, model=model,
        max_output_tokens=max_output_tokens, attempt=0)]
    for attempt in range(1, int(retries) + 1):
        if attempts[-1].source_chars > 0:
            break
        attempts.append(acquire_one(
            dsn, campaign_id=campaign_id, allocation_id=allocation_id,
            arm=arm, task_id=task_id, prompt=prompt, gateway=gateway,
            model=model, max_output_tokens=max_output_tokens, attempt=attempt))
    return attempts[-1], attempts


def null_dispatches(acquired: Sequence[Acquired]) -> list:
    """Every dispatch that returned nothing, named.

    The retracted `inv_r1_e2_relevance` contrast recorded
    `sha256("")`, `prompt_chars: 0` for both arms and filed it as
    `differs: true`. A null dispatch is a null dispatch, so these ride out
    in the artifact and the pairs they touch are refused from comparison
    rather than scored as a zero.
    """
    return [{"arm": a.arm, "task_id": a.task_id,
             "operation_id": a.operation_id, "response_digest": a.digest,
             "source_chars": a.source_chars, "reason": a.parse_problem or a.detail}
            for a in acquired if a.source_chars <= 0]


def require_no_empty_dispatch_is_compared(acquired: Sequence[Acquired]) -> None:
    """Refuse a comparison that would read an empty dispatch as a policy.

    The per-pair check is in `paired_report`, which drops and names a task
    where either side did not score. This is the run-level statement of the
    same rule, and it is what a caller reads to know the run is not
    reporting a difference out of a transport failure.
    """
    empty = sorted(a.operation_id for a in acquired if a.source_chars <= 0)
    if not empty:
        return
    if len(empty) == len(acquired):
        raise ReplicaRefused(
            "every dispatch in this run returned no model bytes: %s"
            % ", ".join(empty))


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


def reading_row(name: str, reading: Any) -> dict:
    """One scored reading, in the fields the first namespace recorded."""
    return {"arm": name, "scored": reading.scored, "score": reading.score,
            "evidence": reading.evidence,
            "evidence_varied": reading.evidence_varied,
            "evidence_total": reading.evidence_total,
            "agreement": reading.agreement, "selected": reading.selected_identity,
            "verdict": reading.verdict, "detail": reading.detail}


def cluster_census() -> dict:
    """The independent units the frozen panel offers this family on this split.

    Scoped to the split the replica's targets are drawn from, because a
    cluster rule counts templates a study actually runs on. Counting all
    four software templates across every split would report four clusters
    for a replication whose three targets carry two of them.
    """
    from fractions import Fraction

    from . import s09_study_protocol

    cells = s09_study_protocol._panel_cells()
    templates = sorted({c.template for c in cells
                        if c.family == FAMILY and c.split == TARGET_SPLIT})
    return {"family": FAMILY, "split": TARGET_SPLIT,
            "cluster_rule": CLUSTER_RULE, "clusters": templates,
            "cluster_count": len(templates),
            "minimum_p": str(s09_study_protocol
                             .minimum_sign_flip_p(len(templates))),
            "required_at_alpha_1_20": s09_study_protocol
                .minimum_clusters_for_alpha(Fraction(1, 20))}


def read_first_namespace(path: str = "reports/evidence/inv_r1_e2_scored/readings.json") -> dict:
    """The first namespace's own numbers, for the agreement check.

    Read as bytes from its own path and never cached into this namespace's
    artifacts before the replica's own freeze is verified, so the replica
    cannot be steered by the result it is replicating.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    try:
        return json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReplicaRefused("the first namespace is unreadable: %s" % exc)


AGREEMENT_FIELDS = ("scored", "score", "evidence", "evidence_total",
                    "evidence_varied", "agreement", "selected", "verdict")


def agreement_with_first(own: Mapping[str, Mapping[str, Any]],
                         first: Mapping[str, Any]) -> dict:
    """Does the replica agree with, reverse, or miss the first namespace.

    The first namespace ran one target task and recorded one row per arm;
    this one runs three and records one row per arm per task. Comparing an
    arm's whole task map against a single row would compare a dict of
    readings to a dict of scalars and find every field "different", so the
    two are aligned on the reading's own fields and a field missing from
    either side is reported as missing rather than compared as `None`.
    """
    rows = {}
    for arm in ARMS:
        entries = dict(own.get(arm) or {})
        theirs = dict(first.get(arm) or {})
        if not entries or not theirs:
            rows[arm] = {"compared": False,
                         "reason": "one side carries no reading",
                         "replica_tasks": sorted(entries),
                         "first_tasks": 1 if theirs else 0}
            continue
        rows[arm] = {"compared": True,
                     "replica_tasks": sorted(entries),
                     "first": theirs,
                     "per_task": _field_agreement(entries, theirs),
                     "distinct_replica_readings": _distinct(entries)}
    return rows


def _field_agreement(entries: Mapping[str, Any],
                     theirs: Mapping[str, Any]) -> dict:
    """Per task, the fields the two namespaces both recorded, and their values.

    `evidence_total` is compared too, and the first namespace does not
    record it — so where the first namespace has no value for a field, the
    row says `absent_from_first` rather than claiming a difference.
    """
    rows = {}
    for task_id in sorted(entries):
        mine = dict(entries[task_id])
        shared, differing, missing = [], [], []
        for field in AGREEMENT_FIELDS:
            if field not in mine:
                missing.append(field)
            elif field not in theirs:
                missing.append(field)
            else:
                shared.append(field)
                if mine[field] != theirs[field]:
                    differing.append(field)
        rows[task_id] = {
            "fields_compared": shared,
            "fields_absent_from_first": sorted(missing),
            "fields_differing": differing,
            "agrees_on_compared_fields": not differing,
            "replica": {f: mine.get(f) for f in shared},
            "first": {f: theirs.get(f) for f in shared},
        }
    return rows


def _distinct(entries: Mapping[str, Any]) -> dict:
    """How many genuinely different readings this arm produced.

    Three acquisitions that all select the first eligible method and all
    score 1.0 are three dispatches, not three results. Counting the
    distinct response digests and the distinct selections says which it was
    without asserting an effect.
    """
    return {
        "tasks": len(entries),
        "distinct_scores": sorted({float(e.get("score") or 0.0)
                                   for e in entries.values()}),
        "distinct_selections": sorted({str(e.get("selected") or "")
                                       for e in entries.values()}),
        "distinct_evidence_legs": sorted({float(e.get("evidence") or 0.0)
                                          for e in entries.values()}),
    }


# ---------------------------------------------------------------------------
# the route
# ---------------------------------------------------------------------------


def live_config(env_path: str = "~/.config/agent-society-live.env") -> dict:
    """Endpoint, model, expected route and key, read at runtime only.

    The key is read from the environment only. Nothing in this module, in the
    evidence directory it writes, or in the report it prints carries the key
    or a prefix of it; `assert_no_key_leaked` is what proves that before the
    artifacts are written.

    `SETTLEMENT_EXPECTED_ROUTE` is read because the adapter refuses to send
    without it: an unset `expected_route` on a non-paid route is a
    pre-send refusal, not a warning, and the receipt records it as
    `pre-send-route-refusal`.
    """
    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
    model = os.environ.get("SETTLEMENT_REPLICA_MODEL", "") \
        or os.environ.get("SETTLEMENT_MODEL", "")
    expected = os.environ.get("SETTLEMENT_EXPECTED_ROUTE", "")
    if not key or not endpoint or not model:
        raise ReplicaRefused(
            "live dispatch needs SETTLEMENT_GATEWAY_KEY,"
            " SETTLEMENT_GATEWAY_ENDPOINT and a model in the environment")
    try:
        route = json.loads(expected) if expected else {}
    except ValueError as exc:
        raise ReplicaRefused(
            "SETTLEMENT_EXPECTED_ROUTE is not valid JSON: %s" % exc)
    return {"endpoint": endpoint, "model": model, "key": key,
            "expected_route": route}


def build_gateway(config: Mapping[str, Any]):
    """The HTTP adapter, created from the runtime key and nothing else.

    `api="responses"` because the broker sends a reasoning effort with every
    construction request, and the chat API refuses an effort it cannot
    carry: the receipt reads `reasoning_effort needs the responses api`.
    """
    from settlement.gateway_http import HttpGatewayAdapter, gateway_timeout_overrides

    return HttpGatewayAdapter(endpoint=str(config["endpoint"]),
                              api_key=str(config["key"]),
                              api=str(config.get("api") or RESPONSES_API),
                              expected_route=dict(config.get("expected_route")
                                                  or {}),
                              route_mode=FREE_ROUTE_MODE,
                              **gateway_timeout_overrides())


def probe_route(dsn: str, *, campaign_id: str, allocation_id: str, gateway: Any,
                model: str) -> dict:
    """One cheap call to confirm the route before any effect is planned.

    `/v1/models` returns an empty list on this gateway and that is not a
    failure, so the probe is a real dispatch of a bounded request rather than
    a listing.
    """
    from settlement import broker
    from settlement.common import ResultCode

    operation_id = "%s-%s" % (campaign_id, PROBE_OPERATION_SUFFIX)
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user",
                               "content": "Reply with the single token: ok"}],
                 "max_output_tokens": PROBE_MAX_TOKENS,
                 "deadline_ms": 60_000,
                 "reasoning_effort": DEFAULT_REASONING_EFFORT},
        allocation_id=allocation_id)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise ReplicaRefused("route probe not admitted: %s" % ensured.detail)
    broker.dispatch_operation(dsn, operation_id, launchers={}, gateway=gateway)
    settled = _settled_text(dsn, operation_id)
    return {"operation_id": operation_id,
            "max_output_tokens": PROBE_MAX_TOKENS,
            "settled": settled is not None,
            "exposure_units": int(ensured.data.get("exposure") or 0),
            "route": "confirmed" if settled else "no-settled-response"}


def assert_no_key_leaked(artifacts: Sequence[Mapping[str, Any]], key: str) -> None:
    """Refuse to write an artifact that carries the gateway key.

    The key is read at runtime and this is the check that keeps it out of the
    evidence directory. It is a substring check against every string in every
    artifact, before anything is written.
    """
    if not key:
        return
    needle = key.strip()
    for artifact in artifacts or []:
        blob = json.dumps(artifact, sort_keys=True, default=str)
        if needle and needle in blob:
            raise ReplicaRefused(
                "an artifact carries the gateway key and was not written")


def cap_sheet(*, retries: int = RETRIES) -> dict:
    """The finite cap sheet, derived from the frozen matrix before effects.

    Every count is implied by the frozen contrast: three arms over the
    target tasks it names, one construction each, plus the declared retry
    allowance and one route probe. The unit allowance is the broker's own
    exposure schedule applied to the longest prompt the arms render, so the
    sheet and the store agree about what a request costs.
    """
    from . import s09_cap_sheet

    body = contrast_block()
    longest = longest_prompt_chars(body)
    targets = body["target_task_ids"]
    arms = body["arms"]
    per_arm = len(targets)
    total_constructions = per_arm * len(arms) * (retries + 1)
    probe_chars = len("Reply with the single token: ok")
    bounds = s09_cap_sheet.RequestBounds(
        model=str(os.environ.get("SETTLEMENT_REPLICA_MODEL", "free-route")),
        message_characters=longest, max_output_tokens=2048,
        deadline_ms=300_000, reasoning_effort=DEFAULT_REASONING_EFFORT)
    per_request = bounds.reservation_units
    probe_units = (probe_chars // 4 + 1) + PROBE_MAX_TOKENS
    total_sends = total_constructions + 1
    return {
        "schema": "s09-e2-replica-cap-v1",
        "namespace": NAMESPACE,
        "route": {"model_from": "environment", "tier": FREE_ROUTE_MODE,
                  "endpoint_from": "SETTLEMENT_GATEWAY_ENDPOINT",
                  "api": RESPONSES_API},
        "matrix": {
            "target_tasks": per_arm,
            "arms": len(arms),
            "constructions_per_arm_per_task": retries + 1,
            "planned_constructions": total_constructions,
            "route_probes": 1,
        },
        "allowance": {
            "construction_dispatches": total_constructions,
            "route_probe_dispatches": 1,
            "physical_sends_ceiling": total_sends,
            "retry_allowance": retries,
        },
        "unit_allowance": {
            "per_request_units": per_request,
            "requests": total_sends,
            "units": per_request * total_sends,
            "probe_units": probe_units,
            "unit_kind": bounds.unit_kind,
            "note": "estimated-budget reservation units derived by"
                    " settlement.broker.exposure_schedule, not a price and"
                    " not a dispatch count",
        },
        "bounds": {"message_characters": longest,
                   "max_output_tokens": bounds.max_output_tokens,
                   "deadline_ms": bounds.deadline_ms,
                   "reasoning_effort": bounds.reasoning_effort},
        "authority": {"owner": "settlement.broker.ensure_operation +"
                              " dispatch_operation",
                      "study_root": campaign_ids()["study_root"],
                      "allocation_id": campaign_ids()["allocation_id"]},
        "freeze_digest": digest_of(body),
    }


def longest_prompt_chars(body: Mapping[str, Any]) -> int:
    """The widest prompt the frozen arms render, measured not assumed.

    The reservation units are a function of the request length, so a cap
    sheet built from a guessed length reserves the wrong amount. This
    renders every arm of every target and takes the maximum.
    """
    body = dict(body or contrast_block())
    visible = learner.visible_opportunities(body["cohort_world"])
    widest = 0
    for task_id in body["target_task_ids"]:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        arms = arms_for(task, source_task_ids=body["source_task_ids"],
                        filler_task_ids=body["filler_task_ids"],
                        visible=visible)
        for name in body["arms"]:
            widest = max(widest, len(prompt_for(name, task, arms[name])))
    return widest


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def score_acquired(target: Mapping[str, Any], arm: Mapping[str, Any],
                   source: str, *, arm_name: str, origin: str,
                   authority: Mapping[str, Any]) -> Any:
    """One acquired policy, on this arm's own observations, at this task.

    The arm's experience is what the policy was shown and what the view it is
    stepped under carries, so the two are the same list. An arm with no
    experience is stepped under an empty list, which is the honest scoring of
    a policy that was shown nothing.

    `origin` is named rather than assumed. This used to label every reading
    `model-acquired` while the only thing distinguishing a live provider from
    a recording double is the receipt for the operation that produced these
    bytes, and the caller is what holds that operation. It passes
    `construct.acquisition_origin(...)["origin"]`.

    `authority` is the store the acquisition already settled against, and it
    is required for the same reason `origin` is: scoring an acquired policy
    executes it, and the caller that paid for the bytes is the caller that
    holds the authority to run them.
    """
    from . import s09_e2_scored as scored

    return scored.score_response(
        json.dumps({"entry": source}), dict(target),
        list(arm.get("observations") or []),
        origin=origin, arm=arm_name,
        eligible_methods=eligible_for(target), remaining={"steps": 1},
        authority=authority)


def _source_of(dsn: str, operation_id: str) -> tuple:
    from . import packet

    settled = _settled_text(dsn, operation_id)
    if settled is None:
        return "", "no settled response"
    return packet.parse_construction_response(settled)


def paired_report(readings: Mapping[str, Mapping[str, Any]]) -> dict:
    """Paired differences for the two contrasts the triple defines.

    Relevant against none and irrelevant against none, each paired by target
    task, through `learner_revision.paired`. A task where either side is
    absent is dropped from the pair and named, never averaged in as a zero.

    The contrast runs on two things rather than on `score`. `score` was
    `evidence + quality`, and `quality` was the checker's verdict bit, which
    is `preserved` for every candidate that reaches a Reading; the contrast
    was therefore a subtraction of a constant against itself and the
    recorded `deltas: [0, 0, 0]` was arithmetic, not a finding.

    What is contrasted instead is:

    * `normalized_reduction`, the fraction of the task's initial measure the
      world-produced candidate removed. It is 0.0 for a policy that returned
      its input and positive for one that found a real reduction, and it
      moves without the oracle changing.
    * the decision vector — `method_id` and `max_queries` — which is the
      decision the policy actually made. `VERBATIM` excludes exactly these
      from the evidence leg's count, so the evidence leg cannot see them and
      they are reported here instead, per task, as a named triple. They are
      not averaged into a number: two arms are said to have chosen
      differently or not, and the choice itself rides out beside the
      difference.
    """
    from . import learner_revision

    contrasts = {"relevant-minus-none": (ARM_RELEVANT, ARM_NONE),
                 "irrelevant-minus-none": (ARM_IRRELEVANT, ARM_NONE)}
    report = {}
    for name, (treatment, control) in contrasts.items():
        left = readings.get(treatment) or {}
        right = readings.get(control) or {}
        shared = sorted(set(left) & set(right))
        deltas, dropped, decisions = [], [], {}
        for task_id in shared:
            a, b = left[task_id], right[task_id]
            if not a["scored"] or not b["scored"]:
                dropped.append(task_id)
                continue
            deltas.append(_reduction_of(a) - _reduction_of(b))
            decisions[task_id] = {
                "treatment": _decision_of(a),
                "control": _decision_of(b),
                "differs": _decision_of(a) != _decision_of(b),
            }
        zeros = [0.0] * len(deltas)
        paired = learner_revision.paired(deltas, zeros) if deltas \
            else learner_revision.paired([], [])
        report[name] = {
            "treatment": treatment, "control": control,
            "paired_by": "target task", "tasks": shared,
            "unscored_tasks": dropped, "deltas": deltas,
            "contrast_on": "normalized_reduction",
            "decisions": decisions,
            "paired": {"delta": paired["delta"], "n": paired["n"],
                       "measured": paired["measured"],
                       "paired_sd": paired["paired_sd"],
                       "paired_se": paired["paired_se"], "z": paired["z"]},
            "estimator": ESTIMATOR,
        }
    return report


def _reduction_of(reading: Mapping[str, Any]) -> float:
    """One reading's normalized reduction, read and never recomputed.

    The report body is not a Reading, so it is read as the one key the
    Reading wrote rather than rebuilt from `initial_measure` and
    `candidate_measure` here. A reading written by an older namespace has
    no such key and is a 0.0, which is honest about there being no measured
    reduction rather than about a zero reduction.
    """
    value = reading.get(NORMALIZED_REDUCTION)
    return float(value) if type(value) in (int, float) else 0.0


def _decision_of(reading: Mapping[str, Any]) -> dict:
    """The decision vector: the two inputs that change what the method runs.

    `VERBATIM` excludes `method_id` and `max_queries` from the evidence
    leg's denominator on purpose — a policy that writes a verdict into an
    input key must not be paid for echoing it — but that exclusion also
    means the evidence leg is blind to the one choice the policy makes. So
    the choice is read here, from the action the world actually admitted.
    """
    inputs = dict((reading.get("action") or {}).get("inputs") or {})
    return {"method_id": str(inputs.get("method_id") or ""),
            "max_queries": inputs.get("max_queries")}


def run_campaign(*, dsn: str, gateway: Any, model: str, allocation_id: str,
                 campaign_id: str, max_output_tokens: int = 2048,
                 targets: Sequence[str] | None = None) -> dict:
    """The frozen contrast, dispatched, scored, and reported as numbers.

    The order is fixed: verify the freeze, qualify the instrument, build
    every arm and render every prompt, then dispatch. Nothing about a
    dispatch can reach the arm it was dispatched for, and the first
    namespace's readings are read only after every score is in hand.
    """
    frozen = freeze()
    body = verify_freeze(frozen)
    visible = learner.visible_opportunities(body["cohort_world"])
    target_ids = list(targets or body["target_task_ids"])
    sheet = cap_sheet()

    qualification: dict = {}
    acquired: list = []
    attempted: list = []
    readings: dict = {}
    for task_id in target_ids:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        arms = arms_for(task, source_task_ids=body["source_task_ids"],
                        filler_task_ids=body["filler_task_ids"],
                        visible=visible)
        if not qualification:
            qualification = qualify_instrument(
                task, arms[ARM_RELEVANT]["observations"],
                eligible_methods=eligible_for(task),
                authority={"dsn": dsn, "allocation_id": allocation_id})
            if not qualification["separates_reader_from_blind"]:
                raise ReplicaRefused(
                    "the instrument does not score a reader above an echoer,"
                    " so no score it produced would be readable")
        for name in ARMS:
            prompt = prompt_for(name, task, arms[name])
            got, attempts = acquire_with_retry(
                dsn, campaign_id=campaign_id, allocation_id=allocation_id,
                arm=name, task_id=task_id, prompt=prompt, gateway=gateway,
                model=model, max_output_tokens=max_output_tokens,
                retries=RETRIES)
            acquired.append(got)
            attempted.extend(attempts)
            source, problem = _source_of(dsn, got.operation_id)
            if problem or not source:
                continue
            from . import construct as _construct
            settled = _settled_text(dsn, got.operation_id)
            origin = "fixture-stand-in"
            if settled is not None:
                origin = _construct.acquisition_origin(
                    dsn, got.operation_id, settled)["origin"]
            readings.setdefault(name, {})[task_id] = reading_row(
                name, score_acquired(
                    task, arms[name], source, arm_name=name, origin=origin,
                    authority={"dsn": dsn, "allocation_id": allocation_id}))

    require_no_empty_dispatch_is_compared(acquired)
    return {"freeze": frozen, "cap_sheet": sheet,
            "instrument_qualification": qualification,
            "acquired": [a.as_dict() for a in acquired],
            "dispatch_attempts": [a.as_dict() for a in attempted],
            "null_dispatches": null_dispatches(attempted),
            "readings": readings, "census": cluster_census(),
            "paired": paired_report(readings), "model": model}


def build_report(bundle: Mapping[str, Any], *,
                 first_readings: Mapping[str, Any] | None = None,
                 key: str = "") -> dict:
    """The artifact, assembled and checked for the key before it is written."""
    own = {arm: dict(entries)
           for arm, entries in (bundle.get("readings") or {}).items()}
    report = {
        "namespace": NAMESPACE,
        "independent_of": "inv_r1_e2_scored",
        "shares_with_first_namespace": {
            "mutable_store": False, "operation_ids": False,
            "allocation": False, "assessment_feedback": False,
            "evidence_directory": False},
        "freeze": bundle.get("freeze"),
        "cap_sheet": bundle.get("cap_sheet"),
        "instrument_qualification": bundle.get("instrument_qualification"),
        "prompt_delta": prompt_delta(),
        "census": bundle.get("census"),
        "acquired": bundle.get("acquired"),
        "dispatch_attempts": bundle.get("dispatch_attempts"),
        "null_dispatches": bundle.get("null_dispatches"),
        "readings": own,
        "paired": bundle.get("paired"),
        "agreement_with_first": (agreement_with_first(own, first_readings)
                                 if first_readings else None),
    }
    assert_no_key_leaked([report], key)
    return report


def bind_authority(dsn: str, *, model: str, token: str = STORE_TOKEN):
    """Authorize the study in the replica's own store, through the owner.

    `s09_run_isolation.RunIsolation.build` is the durable reservation and
    dispatch owner's own entry point: it calls `authority.authorize_study`,
    mints the allocation under this namespace's token, and `bind` refuses a
    store that is not the one this identity was frozen against.

    The allocation is derived from the token, so a re-run that mints fresh
    operation ids has to authorize under the same suffix. Authorizing under
    the default token and dispatching under the suffixed one produced
    `unknown allocation s09iso-invr1e2replicar2-alloc` after the store was
    already built, which is the pre-send refusal this namespace is supposed
    to make rather than a silent fallback.
    """
    from datetime import datetime, timezone

    from . import s09_run_isolation

    s09_run_isolation._checked_token(token)
    return s09_run_isolation.RunIsolation.build(
        s09_run_isolation.DisposableDatabase(
            name="s09iso_%s_bound" % token, dsn=dsn, token=token),
        model=model, adapter="HttpGatewayAdapter", gateway_mode="live",
        frozen_at=datetime.now(timezone.utc)).bind()


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import pathlib

    parser = argparse.ArgumentParser(
        description="E2 replication in a second campaign namespace")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", default="reports/evidence/" + NAMESPACE)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--rerun-suffix", default="",
                        help="mint fresh operation ids under this suffix, so "
                             "a re-run of the same contrast never reuses the "
                             "receipts of an earlier one")
    args = parser.parse_args(argv)

    config = live_config()
    token = ("%s%s" % (STORE_TOKEN, args.rerun_suffix) if args.rerun_suffix
             else STORE_TOKEN)
    ids = (rerun_ids(args.rerun_suffix) if args.rerun_suffix
           else campaign_ids())
    bind_authority(args.dsn, model=config["model"], token=token)
    gateway = build_gateway(config)
    probe = probe_route(args.dsn, campaign_id=ids["campaign_id"],
                        allocation_id=ids["allocation_id"],
                        gateway=gateway, model=config["model"])
    if not probe["settled"]:
        print("route probe returned no settled response: %s" % probe)
        return 3
    bundle = run_campaign(
        dsn=args.dsn, gateway=gateway, model=config["model"],
        allocation_id=ids["allocation_id"],
        campaign_id=ids["campaign_id"],
        max_output_tokens=args.max_output_tokens)
    report = build_report(bundle, first_readings=read_first_namespace(),
                          key=str(config["key"]))
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report["paired"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
