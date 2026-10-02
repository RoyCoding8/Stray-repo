"""The E2 experience contrast, run as a campaign over constructed evidence.

This is a **campaign-side construction, not a repair of the frozen
instrument**. `e2_replication` is not edited here and is not reachable from
here except through the functions it exports. Three things differ from
`e2_replication.run_campaign`, and each difference is a difference the frozen
instrument could not make from where it sits.

**One: the relevant arm's records are built here, at a budget where the
graded outcome actually varies.** `e2_replication.measured_observations` runs
the authored ddmin at `MAX_QUERIES = 8` on all three dev software tasks and
gets `ok-preserved` on all three, so the three records a policy reads differ
only in `task_id`. The same reducer at `max_queries = 3` grades
`ok-preserved / ok-incumbent / ok-preserved` on those same three tasks, with
`reduction` 0.5 / 0.0 / 0.5. The budget is the only thing that moved, the
reducer is the campaign's own, and the grading is the campaign's own checker.
Nothing here claims the panel's dev tasks are hard; the claim is that a
uniform graded outcome cannot be read, and a varying one can.

The control is built by `learner.irrelevant_control_for` and then re-measured
and re-fitted through the same `_resized` the frozen arm uses, so equal
character counts and equal record counts hold across the two arms. That is
the property the size-matched control exists to hold, and it is asserted
before any dispatch rather than described afterwards.

**Two: the scored observable is the whole `Reading`, not `reading_row`.**
`reading_row` writes nine keys and `paired_report` reads
`normalized_reduction` and `action`, neither of which it writes. So
`_reduction_of` returns 0.0 for every reading and `_decision_of` returns
`{'', None}` for every reading, and every paired delta is 0.0 by arithmetic
rather than by measurement. `Reading.as_dict` carries both keys, so keeping
the `Reading` makes the **frozen** `paired_report` work unchanged. This
campaign therefore calls `e2_replication.paired_report` as it stands and
reports whatever it computes.

**Three: the reachability census is reported next to the contrast.** The
benefit metric can only move if some decision in the arm's action space beats
the zero-information default. That is a property of the panel, measurable
offline with no model and no dispatch, and it bounds the contrast before the
contrast is run. On this panel the default is at the grid ceiling for all
three targets, so the attainable positive delta is 0.0 and every live number
below is read against that.

**The accounting is not the adapter's.** `gateway_http._decode_usage` reads
`billed` and `charge_units` out of the provider's `usage` object; this route
emits `usage.cost` and neither of the two, so `billed` is absent and
`charge_units` is absent and both ride out in the report as absent rather
than as zero.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import e2_replication as replica
from . import learner
from . import packet as _packet
from . import s09_e2_scored as scored
from . import worlds

NAMESPACE = "invr1e2contrast"
R2_NAMESPACE = "invr1e2contrastr2"

# The budget the constructed evidence is measured at. `MAX_QUERIES` is 8,
# and ddmin at 8 reduces all three dev software tasks; 3 is the largest
# whole budget at which the graded outcome still varies across them. Frozen
# here, before any dispatch, and asserted in `verify_contrast`.
EVIDENCE_MAX_QUERIES = 3
# The budget the control is measured at. The graph pool's third task is only
# reduced from 6 upward, so 6 is the smallest budget at which the control's
# own graded outcome varies. The two budgets differ on purpose: they are
# chosen so each arm's records vary, not so the arms agree.
CONTROL_MAX_QUERIES = 6

# `packet.project_observations` is an allowlist of five keys:
# observation_id, task_id, capability_id, verdict, detail. `verdict` is
# `preserved` on every record the panel's own reducers can produce, and
# `reason` and `reduction` are outside the allowlist, so a record that
# varies only in those two is a constant by the time the policy reads it.
# `detail` is inside the allowlist and is the record's free-text field, so
# this is where the graded outcome is narrated for the policy that reads it.
DETAIL_TEMPLATE = "%s on %s at %d queries: %s"


def _detail_for(record: Mapping[str, Any], *, max_queries: int) -> str:
    """The record's narrative, in the one graded field the policy receives.

    The values are the record's own `capability_id`, `task_id`, the budget
    it was earned at, and the checker's `reason` and measured `reduction` on
    that task. So the text a policy reads is a re-derivable function of the
    record's other fields, which is what lets the offline verifier check the
    treatment instead of trusting it.

    This says what the reducer did on a *development* task. It is not the
    target's reduction, and a policy that reads it is being asked whether
    that transfers, which is the question the contrast exists to ask.
    """
    return DETAIL_TEMPLATE % (
        str(record.get("capability_id") or ""),
        str(record.get("task_id") or ""),
        int(max_queries),
        "%s, reduction %s" % (str(record.get("reason") or ""),
                              _trim(float(record.get("reduction") or 0.0))))


def _trim(value: float) -> str:
    return ("%.3f" % value).rstrip("0").rstrip(".") or "0"

# The action space the policy may choose from, and the decision the contrast
# reads. Both are the frozen action shape: `method_id` names a repertoire
# member and `max_queries` is its budget.
DECISION_FIELDS = ("method_id", "max_queries")
DEFAULT_METHOD = "seed-sw-ddmin"
# The action a policy with no information writes. `_resolve_method` refuses
# a `construct_method` with no `method_id` and a `use_method` with no
# `method_id`, so a policy that declines to choose is not reachable; naming
# the first eligible method is what zero information looks like here.
DEFAULT_MAX_QUERIES = replica.MAX_QUERIES

DECISION_GRID = tuple(
    (method, budget)
    for method in ("seed-sw-ddmin", "seed-sw-greedy")
    for budget in (4, 8, 12, 16, 24, 32))


class ContrastRefused(Exception):
    """A campaign that may not run, named before anything was sent."""


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def contrast_block() -> dict:
    """The contrast, frozen, as the digest reads it.

    Every field here is checked by `verify_contrast` against the panel and
    the module, so an edited body is refused rather than reported.
    """
    frozen = replica.contrast_block()
    return {
        "namespace": NAMESPACE,
        "independent_of": ["inv_r1_e2_scored", "inv_r1_e2_replica"],
        "family": replica.FAMILY,
        "cohort_world": frozen["cohort_world"],
        "source_split": frozen["source_split"],
        "target_split": frozen["target_split"],
        "control_split": frozen["control_split"],
        "arms": list(replica.ARMS),
        "source_task_ids": list(frozen["source_task_ids"]),
        "filler_task_ids": list(frozen["filler_task_ids"]),
        "target_task_ids": list(frozen["target_task_ids"]),
        "evidence_max_queries": EVIDENCE_MAX_QUERIES,
        "control_max_queries": CONTROL_MAX_QUERIES,
        "max_queries": replica.MAX_QUERIES,
        "decision_fields": list(DECISION_FIELDS),
        "decision_grid": [list(pair) for pair in DECISION_GRID],
        "scored_observable": "Reading.as_dict (carries normalized_reduction"
                             " and action, which paired_report reads)",
        "estimator": replica.ESTIMATOR,
        "cluster_rule": replica.CLUSTER_RULE,
        "alpha": replica.ALPHA,
    }


def freeze() -> dict:
    body = contrast_block()
    return {"body": body, "freeze_digest": replica.digest_of(body)}


def verify_contrast(frozen: Mapping[str, Any]) -> dict:
    """The freeze, re-derived and refused on any drift.

    Same rule as `replica.verify_freeze` and for the same reason: a contrast
    edited after it was frozen reproduces a digest nobody agreed to.
    """
    body = dict((frozen or {}).get("body") or {})
    if not body:
        raise ContrastRefused("the freeze carries no contrast body")
    recorded = str((frozen or {}).get("freeze_digest") or "")
    if replica.digest_of(body) != recorded:
        raise ContrastRefused("the freeze addresses as %s but records %s"
                              % (replica.digest_of(body), recorded))
    current = contrast_block()
    if body != current:
        drifted = sorted(k for k in set(body) | set(current)
                         if body.get(k) != current.get(k))
        raise ContrastRefused("the frozen contrast no longer matches the"
                              " panel: %s" % ", ".join(drifted))
    return body


# ---------------------------------------------------------------------------
# the constructed evidence
# ---------------------------------------------------------------------------


def evidence_row(task_id: str, *, max_queries: int) -> dict:
    """One experience record, graded at the campaign's evidence budget.

    Every field is produced by running the campaign's own reducer and
    grading with the campaign's own checker, so `verdict` and `reason` are
    measurements rather than labels. `reason` is what separates a record that
    says the reducer found a reduction from one that says it handed its input
    back, and `reduction` is the number the same checker produced. `detail`
    is the same two facts in prose, because `detail` is the only graded field
    `packet.project_observations` delivers to the policy.
    """
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    capability = next((item for item in _seed_capabilities()
                       if item["capability_id"] == replica._capability(task)),
                      None)
    if capability is None:
        raise ContrastRefused("no authored capability for %s" % task_id)
    result = _run_seed(capability, task, max_queries=max_queries)
    report = replica._grade(task, result["candidate"])
    row = {"observation_id": "obs-%s-0" % task_id,
           "task_id": task_id,
           "capability_id": "ad01-%s" % str(task.get("family") or ""),
           "verdict": str(report["verdict"]),
           "reason": str(report["reason"]),
           "reduction": replica._normalized_reduction(report)}
    return {**row, "detail": _detail_for(row, max_queries=max_queries)}


def _seed_capabilities() -> list:
    from . import seeds

    return seeds.SEED_CAPABILITIES


def _run_seed(capability: Mapping[str, Any], task: Mapping[str, Any],
              *, max_queries: int) -> dict:
    from . import seeds

    return seeds.run_seed(dict(capability), dict(task), max_queries=max_queries)


def _measured_rows(task_ids: Sequence[str], *, max_queries: int) -> list:
    return [evidence_row(task_id, max_queries=max_queries)
            for task_id in sorted(task_ids or [])]


def graded_outcome_profile(rows: Sequence[Mapping[str, Any]]) -> dict:
    """How many distinct graded outcomes an arm's records carry.

    Four things are counted, and the distinction is the whole point.

    `verdict` is the checker's headline bit. It is `preserved` on every
    record the panel's own reducers can produce, because both reducers only
    ever emit legal deletions that keep the witness, so a reducer's output
    cannot fail. It is a constant here and the profile says so.

    `reason` is the checker's bounded code and it is the field that
    separates a record saying the reducer found a reduction from one saying
    it handed its input back. It varies across the panel.

    What a policy receives is the record as
    `packet.project_observations` projects it, and that is the five-key
    allowlist. `reason` and `reduction` are outside it, so the only graded
    field that reaches a policy is `detail`.

    The count that decides is `delivered_grades`, and it deliberately
    ignores the identity fields. The `detail` this campaign writes embeds
    `task_id` and `capability_id`, so counting distinct `detail` strings
    would report three varied outcomes for three records that all say
    `ok-incumbent, reduction 0`, which is the same uniformity defect wearing
    a different field. What a policy can act on is the graded part of the
    text, so the template is split on its last colon and the outcome is
    counted on that half.
    """
    verdicts = {str(r.get("verdict")) for r in rows or []}
    reasons = {str(r.get("reason")) for r in rows or []}
    projected = _project(rows or [])
    projected_grades = {_grade_of(r) for r in projected}
    return {
        "records": len(list(rows or [])),
        "distinct_verdicts": sorted(verdicts),
        "verdict_is_constant": len(verdicts) <= 1,
        "distinct_reasons": sorted(reasons),
        "distinct_reductions": sorted({round(float(r.get("reduction") or 0.0), 6)
                                        for r in rows or []}),
        "distinct_task_ids": len({str(r.get("task_id")) for r in rows or []}),
        "delivered_grades": len(projected_grades),
        "delivered_grades_seen": sorted(projected_grades),
        "delivered_uniform": len(projected_grades) <= 1,
        "projected_record_keys": sorted(projected[0]) if projected else [],
        "fields_dropped_by_projection": sorted(
            set(rows[0]) - set(projected[0])) if (rows and projected) else [],
        "uniform": len(projected_grades) <= 1,
    }


def _grade_of(row: Mapping[str, Any]) -> str:
    """The graded half of a record's `detail`, without its identity half.

    The template is `"<capability> on <task> at <n> queries: <reason>,
    reduction <value>"`, so the graded half is everything after the last
    colon. Reading it off the last colon rather than off a fixed offset
    means a template change moves this with it instead of silently
    returning the whole string.
    """
    detail = str(row.get("detail") or "")
    _, separator, tail = detail.rpartition(":")
    return tail.strip() if separator else detail.strip()


def _project(rows: Sequence[Mapping[str, Any]]) -> list:
    """The records as `policy_step.materialize_view` will hand them over."""
    from . import packet

    return packet.project_observations(list(rows or []))


def build_arms(target: Mapping[str, Any], *,
               source_task_ids: Sequence[str],
               filler_task_ids: Sequence[str],
               visible: Sequence[str]) -> dict:
    """The three arms, with the relevant arm's records constructed here.

    `replica.build_arm` is not used. It reads its records from
    `measured_observations`, which grades at 8 and is uniform, and a campaign
    that wants a varying arm has to build its own. The shape it returns is
    `replica.build_arm`'s shape, because the prompt, the view and the scorer
    all read that shape and nothing here re-defines any of them.
    """
    target = dict(target or {})
    family = str(target.get("family") or "")
    base = learner.relevant_experience(
        target, list(source_task_ids), list(visible), {})

    relevant = {**base, "family": family,
                "observations": _measured_rows(
                    source_task_ids, max_queries=EVIDENCE_MAX_QUERIES)}
    replica.require_measurable_verdicts(relevant["observations"])
    none = {**learner.no_experience_experience(
        target, list(source_task_ids), list(visible), {}),
        "family": family, "observations": []}

    irrelevant = {**base, "family": family,
                  "observations": _irrelevant_rows(relevant, filler_task_ids)}

    arms = {replica.ARM_RELEVANT: relevant, replica.ARM_NONE: none,
            replica.ARM_IRRELEVANT: irrelevant}
    require_size_matched(arms)
    require_varying_graded_outcome(relevant, irrelevant)
    return arms


def _irrelevant_rows(relevant: Mapping[str, Any],
                     filler_task_ids: Sequence[str]) -> list:
    """A size-matched, record-count-matched control, re-measured.

    `learner.irrelevant_control_for` is the campaign's own size matcher and
    is used unchanged: it draws from a different family's pool and refuses
    rather than shipping a control of the wrong size. Its records carry
    `verdict: "unmeasured"`, so they are re-measured on the same filler tasks
    at `CONTROL_MAX_QUERIES` and the `detail` padding is re-fitted to the
    exact character count the matcher found, by the same `learner._resized`
    it uses. Re-measuring without re-fitting would move the arm off the
    length the control exists to match.

    The control's budget differs from the relevant arm's. Each is the
    smallest whole budget at which its own arm's graded outcome varies, and
    a control whose outcome profile matched the treatment's exactly would
    confound relevance with the informativeness of the experience. What the
    control must match is subject matter, size and record count, and what
    both arms must have is a varied outcome.
    """
    control = learner.irrelevant_control_for(dict(relevant),
                                            list(filler_task_ids))
    observations = list(control.get("observations") or [])
    if not observations:
        return observations
    target_chars = learner._observation_chars(relevant["observations"])
    measured = _measured_rows(
        [str(row.get("task_id") or "") for row in observations],
        max_queries=CONTROL_MAX_QUERIES)
    fitted = _fit_to(measured, target_chars)
    if fitted is None:
        raise ContrastRefused(
            "the measured control at %d queries cannot reach the relevant"
            " arm's %d characters: its %d characters are above the target and"
            " padding only adds" % (CONTROL_MAX_QUERIES, target_chars,
                                   learner._observation_chars(measured)))
    return fitted


def _fit_to(records: Sequence[Mapping[str, Any]], target: int) -> list | None:
    """`records` padded to exactly `target` characters, or `None`.

    The padding goes in a `padding` key, and that is not cosmetic.

    `learner._resized` pads the last record's `detail`, which is the one
    graded field `packet.project_observations` delivers. Padding it with
    `x` overwrites the checker's `reason` and `reduction` with noise, and a
    control whose graded text is a row of `x` carries no outcome at all: the
    first version of this construction produced exactly that, and the
    uniformity gate caught it. `padding` is outside the five-key allowlist,
    so it is counted by the serialiser that the size matcher measures and
    delivered to no policy. The size match is preserved and the graded text
    survives.

    The fitter moves the control onto the treatment's exact character count
    by spending a field that carries no grade, and the field it spends is
    chosen per record rather than once.

    `learner._resized` pads the last record's `detail`, which is the one
    graded field `packet.project_observations` delivers. Padding it with
    `x` overwrites the checker's `reason` and `reduction` with noise, and a
    control whose graded text is a row of `x` carries no outcome at all: the
    first version of this construction produced exactly that, and the
    uniformity gate caught it.

    Any key outside the five-key allowlist is invisible to a policy, and any
    of them costs characters in every record of the arm. The graph family
    name is longer than the software one and the control's graded text is
    longer with it, so the measured control can land just under or just over
    the treatment's count depending on the budget, and a pad key's own cost
    can be larger than the gap.

    So the fitter adjusts on both sides. It shortens the control's graded
    text from the front, which drops the family prefix while leaving the
    graded half the policy reads intact, until the remaining gap is one the
    pad key can absorb exactly. If no prefix length lands on the target, it
    returns `None` and the campaign refuses rather than shipping a control
    of the wrong size.
    """
    for key in _PAD_KEYS:
        for trim in range(_MAX_TRIM + 1):
            fitted = _fit_with(records, int(target), key, trim=trim)
            if fitted is not None:
                return fitted
    return None


_PAD_KEYS = ("p", "pad", "_pad", "pad_", "x_pad", "fill", "filler_pad")
"""Candidate keys for the size-matching padding, shortest first.

Every one is outside `packet.project_observations`' five-key allowlist, so
none of them reaches a policy. The order is by length because the key's
characters are spent in every record of the arm, and a shorter key leaves
more of the budget for the gap it has to close.
"""

_MAX_TRIM = 40
"""How many leading characters of the graded prefix may be dropped.

The prefix is `"<capability_id> on <task_id> at <n> queries"`, and the task
id is the bulk of it. Trimming from the front leaves the graded half
(`"<reason>, reduction <value>"`) untouched, which is the half a policy can
act on, and removes only the identity the allowlist already carries in its
own `capability_id` and `task_id` fields.
"""


def _fit_with(records: Sequence[Mapping[str, Any]], target: int, key: str,
              trim: int = 0) -> list | None:
    trimmed = [_trim_detail(record, trim) for record in records]
    bare = [dict(record, **{key: ""}) for record in trimmed]
    if not bare:
        return None
    width = int(target) - learner._observation_chars(bare)
    if width < 0:
        return None
    candidate = [dict(record, **{key: ("" if index < len(bare) - 1
                                      else "x" * width)})
                 for index, record in enumerate(bare)]
    if learner._observation_chars(candidate) != int(target):
        return None
    return candidate


def _trim_detail(record: Mapping[str, Any], trim: int) -> dict:
    """The record with about `trim` characters cut off its detail's prefix.

    The detail is `"<prefix>: <grade>"`, so the cut is made on the last
    colon and the graded half after it is left alone. A trim longer than the
    prefix is clamped, so an over-trim shortens the prefix to nothing rather
    than cutting into the grade.

    The cut always lands on a word boundary, and the boundary chosen is the
    one nearest the requested length. A prefix cut mid-token leaves a
    fragment like `"s"` that reads as damage to the record rather than as
    the elision it is, and a policy reading three records would see a
    different-looking prefix on each. The graded half is never touched,
    which is the half a policy can act on; only the identity prefix goes,
    and the allowlist already carries that in its own `capability_id` and
    `task_id` fields.
    """
    if trim <= 0:
        return dict(record)
    detail = str(record.get("detail") or "")
    head, separator, tail = detail.rpartition(":")
    if not separator:
        return dict(record)
    cut = max(len(head) - trim, 0)
    spaces = [index for index, char in enumerate(head) if char == " "]
    if spaces:
        cut = min(spaces, key=lambda index: abs(index - cut))
    if cut <= 0:
        return dict(record, detail=separator + tail)
    return dict(record, detail=head[cut:] + separator + tail)


def require_size_matched(arms: Mapping[str, Mapping[str, Any]]) -> dict:
    """Equal character counts across the two arms that carry experience.

    The irrelevant control is meaningless at a different volume from the
    arm it controls, so this is asserted before any dispatch. The `none` arm
    carries no experience by definition and is reported rather than
    constrained: forcing it to the same length would give it experience.
    """
    sized = {}
    for name in (replica.ARM_RELEVANT, replica.ARM_IRRELEVANT):
        rows = list((arms.get(name) or {}).get("observations") or [])
        sized[name] = {"characters": learner._observation_chars(rows),
                       "records": len(rows)}
    sized[replica.ARM_NONE] = {
        "characters": learner._observation_chars([]), "records": 0,
        "note": "empty by construction; the no-experience arm is defined by"
                " having the opportunity and not drawing it"}
    left, right = sized[replica.ARM_RELEVANT], sized[replica.ARM_IRRELEVANT]
    if left["characters"] != right["characters"] or left["records"] != right["records"]:
        raise ContrastRefused(
            "the relevant and irrelevant arms are not size matched: %r"
            " against %r" % (left, right))
    return sized


def require_varying_graded_outcome(relevant: Mapping[str, Any],
                                   irrelevant: Mapping[str, Any]) -> dict:
    """The defect this campaign exists to remove, refused if it is present.

    The frozen instrument's relevant arm grades uniformly, so its three
    records are one constant carrying three ids. A contrast read off a
    constant measures the reader, not the experience. This is the gate the
    assignment names, and it is checked on the records rather than described.
    """
    profiles = {
        replica.ARM_RELEVANT: graded_outcome_profile(
            relevant.get("observations")),
        replica.ARM_IRRELEVANT: graded_outcome_profile(
            irrelevant.get("observations")),
    }
    if profiles[replica.ARM_RELEVANT]["uniform"]:
        raise ContrastRefused(
            "the relevant arm's records carry one graded outcome, so the"
            " contrast would read a constant: %r"
            % profiles[replica.ARM_RELEVANT])
    if profiles[replica.ARM_IRRELEVANT]["uniform"]:
        raise ContrastRefused(
            "the control arm's records carry one graded outcome, so the"
            " contrast would be uniformity against uniformity: %r"
            % profiles[replica.ARM_IRRELEVANT])
    return profiles


# ---------------------------------------------------------------------------
# what each treatment receives
# ---------------------------------------------------------------------------


def treatment_input_audit(target: Mapping[str, Any],
                          arms: Mapping[str, Mapping[str, Any]]) -> dict:
    """What each arm's prompt and each arm's view actually contain.

    The assignment asks for this explicitly, and a prior bug dropped
    information at three points, so it is derived from the rendered bytes
    rather than asserted. For each arm: the prompt's prior-observation
    line, the observation keys the record carries, the keys the view
    delivers, and the keys lost in between. A field the prompt names and
    the view drops is a dropped decision, and it is named here.
    """
    rows = {}
    for name in replica.ARMS:
        arm = dict(arms.get(name) or {})
        observations = list(arm.get("observations") or [])
        prompt = replica.prompt_for(name, target, arm)
        line = next((ln for ln in prompt.splitlines()
                     if ln.startswith("Prior observations:")), "")
        view = scored.build_views(
            dict(target), observations,
            eligible_methods=replica.eligible_for(target),
            remaining={"steps": 1})
        delivered = list(view["scored"].get("observations") or [])
        record_keys = sorted(observations[0]) if observations else []
        view_keys = sorted(delivered[0]) if delivered else []
        prompt_keys = _prompt_keys(line)
        rows[name] = {
            "prompt_characters": len(prompt),
            "prompt_prior_observation_line": line or None,
            "prompt_names_fields": prompt_keys,
            "record_carries": record_keys,
            "view_delivers": view_keys,
            "dropped_before_the_policy": sorted(set(record_keys) - set(view_keys)),
            "named_in_prompt_but_not_delivered": sorted(set(prompt_keys) - set(view_keys)),
            "observations": len(observations),
            "verdicts_delivered": sorted({str(o.get("verdict")) for o in delivered}),
            "reasons_delivered": sorted({str(o.get("reason")) for o in delivered
                                         if "reason" in o}),
            "eligible_methods": list(view["scored"].get("eligible_methods") or []),
            "remaining": dict(view["scored"].get("remaining") or {}),
        }
    return {
        "arms": rows,
        "interfaces_equal": _interfaces_equal(rows),
        "opportunity_equal": _opportunity_equal(rows),
        "notes": [
            "`packet.project_observations` is an allowlist of five keys. Any"
            " record field outside it is dropped before the policy runs, and"
            " a field the prompt names is not thereby delivered.",
            "The none arm is stepped under an empty observation list, which"
            " is the honest scoring of a policy shown nothing.",
        ],
    }


def _prompt_keys(line: str) -> list:
    if not line:
        return []
    try:
        parsed = json.loads(line.split(": ", 1)[1])
    except (IndexError, ValueError):
        return []
    keys = set()
    for row in parsed or []:
        if isinstance(row, dict):
            keys.update(str(k) for k in row)
    return sorted(keys)


def _interfaces_equal(rows: Mapping[str, Mapping[str, Any]]) -> bool:
    """Same interface, same target, same eligible methods, same allowance.

    Compares everything the prompt states about the machinery rather than
    the prompt's length, because the experience is what should differ and
    its length is expected to.
    """
    fields = ("eligible_methods", "remaining")
    first = rows[replica.ARMS[0]]
    return all([first.get(f) for f in fields]
               == [rows[name].get(f) for f in fields] for name in replica.ARMS)


def _opportunity_equal(rows: Mapping[str, Mapping[str, Any]]) -> bool:
    """Same visible opportunity for every arm, and the same record count.

    The irrelevant arm differs from the relevant one in subject matter only.
    A control holding a different number of records confounds relevance with
    volume, so both are compared here.
    """
    counts = {name: rows[name].get("observations") for name in replica.ARMS}
    return counts[replica.ARM_RELEVANT] == counts[replica.ARM_IRRELEVANT]


# ---------------------------------------------------------------------------
# reachability, measured offline
# ---------------------------------------------------------------------------


def reachability_census(target_task_ids: Sequence[str],
                        *, method_ids: Sequence[str],
                        budgets: Sequence[int]) -> dict:
    """The benefit metric at every decision the arms can actually make.

    The policy's only lever on this instrument is the action's decision
    vector, so the set of values the metric can take is the image of that
    grid under the campaign's own grader. It is computed with no model and
    no dispatch. Two numbers matter: the default, which is what a policy
    with no information writes, and the ceiling, which is the best any
    decision reaches. `attainable_positive_delta` is the difference, and it
    bounds the contrast before the contrast is run.
    """
    rows = []
    for task_id in target_task_ids:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        grid = {}
        for method_id in method_ids:
            capability = next((c for c in _seed_capabilities()
                               if c["capability_id"] == method_id), None)
            if capability is None:
                continue
            for budget in budgets:
                result = _run_seed(capability, task, max_queries=int(budget))
                report = replica._grade(task, result["candidate"])
                grid["%s@%d" % (method_id, budget)] = {
                    "normalized_reduction": replica._normalized_reduction(report),
                    "verdict": str(report["verdict"]),
                    "reason": str(report["reason"]),
                    "queries": int(result.get("queries") or 0)}
        values = [v["normalized_reduction"] for v in grid.values()]
        default = grid.get("%s@%d" % (DEFAULT_METHOD, DEFAULT_MAX_QUERIES))
        rows.append({
            "task_id": task_id,
            "grid": grid,
            "distinct_values": sorted({round(v, 6) for v in values}),
            "default": default,
            "ceiling": max(values) if values else 0.0,
            "floor": min(values) if values else 0.0,
            "attainable_positive_delta": round(
                (max(values) if values else 0.0)
                - (default or {}).get("normalized_reduction", 0.0), 6),
            "attainable_negative_delta": round(
                (default or {}).get("normalized_reduction", 0.0)
                - (min(values) if values else 0.0), 6),
        })
    return {
        "decision_fields": list(DECISION_FIELDS),
        "grid": [list(pair) for pair in DECISION_GRID],
        "default_decision": [DEFAULT_METHOD, DEFAULT_MAX_QUERIES],
        "rows": rows,
        "max_attainable_positive_delta": max(
            (r["attainable_positive_delta"] for r in rows), default=0.0),
        "max_attainable_negative_delta": max(
            (r["attainable_negative_delta"] for r in rows), default=0.0),
        "reading": "a positive paired delta needs a decision that beats the"
                   " zero-information default. This is the largest such"
                   " difference the frozen panel admits, and it is 0.0 when"
                   " the default is already the best decision available."
                   " The negative side is not bounded this way, so a"
                   " negative delta is the one the instrument can produce.",
    }


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def acquire_one(dsn: str, *, campaign_id: str, allocation_id: str, arm: str,
                task_id: str, prompt: str, gateway: Any, model: str,
                max_output_tokens: int, attempt: int = 0):
    """One construction dispatch, through the same durable owner.

    Identical to `replica.acquire_one` except that the payload carries no
    `reasoning_effort`, and the reason is a live route conflict rather than a
    preference.

    `broker._validate_model` (broker.py:82) accepts an absent effort and
    `broker.dispatch_operation` passes `payload.get("reasoning_effort")` to
    the adapter, so an omitted key is `None` and the adapter sends no effort.
    The frozen `acquire_one` always sets one, and the two constraints it
    runs into are both correct and both frozen:

    * a frozen route can only be attested on the `chat` surface, because
      `responses` publishes no provider and the adapter refuses to infer one
      from the requested model id (gateway_http.py:924);
    * `chat` refuses a request carrying a `reasoning_effort`
      (gateway_http.py:960).

    So the only request this route will admit is a chat request with no
    effort, and the effort the cap sheet names is the reservation unit, not
    a value the wire can carry. The record below states the effort as
    `none-sent` rather than as `low`, so the receipt cannot be read as
    claiming a control the request did not apply.

    Everything else is the frozen path: the same operation id, the same
    reservation, the same receipt, the same parse, and the same digest.
    """
    from settlement import broker
    from settlement.common import ResultCode

    from . import packet

    operation_id = replica.operation_id_for(campaign_id, task_id, arm, attempt)
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": int(max_output_tokens),
                 "deadline_ms": 300_000},
        allocation_id=allocation_id)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise ContrastRefused("construction not admitted: %s" % ensured.detail)
    broker.dispatch_operation(dsn, operation_id, launchers={}, gateway=gateway)
    settled = replica._settled_text(dsn, operation_id)
    digest = hashlib.sha256((settled or "").encode("utf-8")).hexdigest()
    if settled is None:
        return _acquired(arm, task_id, operation_id, prompt, digest, 0,
                         "no settled response",
                         "the dispatch left no successful receipt", attempt)
    source, problem = packet.parse_construction_response(settled)
    return _acquired(arm, task_id, operation_id, prompt, digest,
                     len(source or ""), problem, "", attempt)


def _acquired(arm: str, task_id: str, operation_id: str, prompt: str,
              digest: str, source_chars: int, problem: str, detail: str,
              attempt: int):
    return replica.Acquired(arm=arm, task_id=task_id,
                            operation_id=operation_id,
                            prompt_chars=len(prompt), digest=digest,
                            source_chars=source_chars,
                            parse_problem=problem, detail=detail,
                            attempt=attempt)


def acquire_with_retry(dsn: str, *, campaign_id: str, allocation_id: str,
                       arm: str, task_id: str, prompt: str, gateway: Any,
                       model: str, max_output_tokens: int,
                       retries: int = replica.RETRIES) -> tuple:
    """Dispatch, and retry once on a dispatch that returned no model bytes.

    The frozen allowance and the frozen rule: a retry is spent only on
    emptiness, never on a worse policy and never on a run-killing exception,
    and every attempt rides out in the record beside the others.
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


def prompt_for(name: str, target: Mapping[str, Any],
               arm: Mapping[str, Any]) -> str:
    """The arm's construction prompt, the frozen one plus its one line.

    `replica.prompt_for` unchanged, so this campaign sends the same bytes
    the frozen replica sends and the two campaigns differ in their evidence
    and their scored observable rather than in their instructions.
    """
    return replica.prompt_for(name, target, arm)


def cap_sheet(body: Mapping[str, Any]) -> dict:
    """The finite cap sheet, derived from the frozen matrix before effects.

    Three arms over the three target tasks the freeze names, one
    construction each, plus the declared retry allowance and one route
    probe. The unit allowance is the broker's own exposure schedule applied
    to the widest prompt the arms actually render.
    """
    from . import s09_cap_sheet

    targets = list(body["target_task_ids"])
    arms = list(body["arms"])
    longest = _longest_prompt(body)
    bounds = s09_cap_sheet.RequestBounds(
        model=str(os.environ.get("SETTLEMENT_CONTRAST_MODEL", "free-route")),
        message_characters=longest, max_output_tokens=2048,
        deadline_ms=300_000, reasoning_effort=replica.DEFAULT_REASONING_EFFORT)
    constructions = len(targets) * len(arms) * (replica.RETRIES + 1)
    sends = constructions + 1
    return {
        "schema": "s09-e2-contrast-cap-v1",
        "namespace": NAMESPACE,
        "evidence_max_queries": body["evidence_max_queries"],
        "matrix": {"target_tasks": len(targets), "arms": len(arms),
                   "constructions_per_arm_per_task": replica.RETRIES + 1,
                   "planned_constructions": constructions,
                   "route_probes": 1},
        "allowance": {"construction_dispatches": constructions,
                      "route_probe_dispatches": 1,
                      "physical_sends_ceiling": sends,
                      "retry_allowance": replica.RETRIES},
        "unit_allowance": {"per_request_units": bounds.reservation_units,
                           "requests": sends,
                           "units": bounds.reservation_units * sends,
                           "unit_kind": bounds.unit_kind,
                           "note": "estimated-budget reservation units"
                                   " derived by settlement.broker's exposure"
                                   " schedule, not a price and not a"
                                   " dispatch count"},
        "bounds": {"message_characters": longest,
                   "max_output_tokens": bounds.max_output_tokens,
                   "deadline_ms": bounds.deadline_ms,
                   "reasoning_effort": bounds.reasoning_effort,
                   "reasoning_effort_on_the_wire": "none-sent",
                   "why": "the value above is the reservation unit the"
                          " broker's exposure schedule prices a request at."
                          " A frozen route can only be attested on the chat"
                          " surface, and chat refuses a request carrying a"
                          " reasoning_effort, so no request in this campaign"
                          " sends one. The cap sheet prices the request it"
                          " sends and the receipt records no effort rather"
                          " than a control the wire never applied."},
        "freeze_digest": replica.digest_of(body),
    }


def _longest_prompt(body: Mapping[str, Any]) -> int:
    visible = learner.visible_opportunities(body["cohort_world"])
    widest = 0
    for task_id in body["target_task_ids"]:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        arms = build_arms(task, source_task_ids=body["source_task_ids"],
                          filler_task_ids=body["filler_task_ids"],
                          visible=visible)
        for name in body["arms"]:
            widest = max(widest, len(prompt_for(name, task, arms[name])))
    return widest


def score_one(target: Mapping[str, Any], arm: Mapping[str, Any],
              source: str, *, arm_name: str, origin: str,
              authority: Mapping[str, Any]):
    """One acquired policy, scored through the campaign's own scorer.

    `replica.score_acquired` unchanged. The arm's observations are the list
    the policy was shown and the list the view it is stepped under carries,
    so the two are the same list and the arm with no experience is stepped
    under an empty one.

    `authority` is the campaign's own store. Scoring the acquired policy
    executes it, so the campaign that dispatched it is the one that can run
    it, and it forwards that rather than leaving the scorer to decide.
    """
    return replica.score_acquired(target, arm, source, arm_name=arm_name,
                                  origin=origin, authority=authority)


def run_campaign(*, dsn: str, gateway: Any, model: str, allocation_id: str,
                 campaign_id: str, max_output_tokens: int = 2048,
                 targets: Sequence[str] | None = None) -> dict:
    """The frozen contrast, dispatched, scored, and reported as numbers.

    The order is fixed and is the order the freeze requires: verify the
    freeze, build every arm and render every prompt, audit what each arm
    receives, measure reachability, and only then dispatch. Nothing about a
    dispatch can reach the arm it was dispatched for.
    """
    frozen = freeze()
    body = verify_contrast(frozen)
    visible = learner.visible_opportunities(body["cohort_world"])
    target_ids = list(targets or body["target_task_ids"])

    qualification: dict = {}
    census: dict = {}
    audit: dict = {}
    profiles: dict = {}
    sized: dict = {}
    acquired: list = []
    attempted: list = []
    readings: dict = {}

    for task_id in target_ids:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        arms = build_arms(task, source_task_ids=body["source_task_ids"],
                          filler_task_ids=body["filler_task_ids"],
                          visible=visible)
        sized = require_size_matched(arms)
        profiles = require_varying_graded_outcome(
            arms[replica.ARM_RELEVANT], arms[replica.ARM_IRRELEVANT])
        audit = treatment_input_audit(task, arms)
        if not qualification:
            qualification = replica.qualify_instrument(
                task, list(arms[replica.ARM_RELEVANT]["observations"]),
                eligible_methods=replica.eligible_for(task),
                authority={"dsn": dsn, "allocation_id": allocation_id})
            if not qualification["separates_reader_from_blind"]:
                raise ContrastRefused(
                    "the instrument does not score a reader above an echoer,"
                    " so no score it produced would be readable")
        if not census:
            census = reachability_census(
                body["target_task_ids"],
                method_ids=sorted({pair[0] for pair in DECISION_GRID}),
                budgets=sorted({pair[1] for pair in DECISION_GRID}))
        for name in body["arms"]:
            prompt = prompt_for(name, task, arms[name])
            got, attempts = acquire_with_retry(
                dsn, campaign_id=campaign_id, allocation_id=allocation_id,
                arm=name, task_id=task_id, prompt=prompt, gateway=gateway,
                model=model, max_output_tokens=max_output_tokens,
                retries=replica.RETRIES)
            acquired.append(got)
            attempted.extend(attempts)
            source, problem = replica._source_of(dsn, got.operation_id)
            if problem or not source:
                continue
            settled = replica._settled_text(dsn, got.operation_id)
            origin = "fixture-stand-in"
            if settled is not None:
                from . import construct as _construct

                origin = _construct.acquisition_origin(
                    dsn, got.operation_id, settled)["origin"]
            reading = score_one(
                task, arms[name], source, arm_name=name, origin=origin,
                authority={"dsn": dsn, "allocation_id": allocation_id})
            # The whole Reading, not `reading_row`. `reading_row` writes nine
            # keys and drops `normalized_reduction` and `action`, which are
            # the two `paired_report` reads, so a row from it makes every
            # delta 0.0 by arithmetic. `as_dict` carries both, and this is
            # the frozen instrument's own serialisation of its own Reading.
            readings.setdefault(name, {})[task_id] = reading.as_dict()

    replica.require_no_empty_dispatch_is_compared(acquired)
    return {"freeze": frozen, "cap_sheet": cap_sheet(body),
            "instrument_qualification": qualification,
            "evidence_budget": {"max_queries": EVIDENCE_MAX_QUERIES,
                                "control_max_queries": CONTROL_MAX_QUERIES,
                                "detail_template": DETAIL_TEMPLATE},
            "graded_outcome_profiles": profiles,
            "size_matching": sized,
            "treatment_input_audit": audit,
            "reachability_census": census,
            "acquired": [a.as_dict() for a in acquired],
            "dispatch_attempts": [a.as_dict() for a in attempted],
            "null_dispatches": replica.null_dispatches(attempted),
            "readings": readings,
            "census": replica.cluster_census(),
            "paired": replica.paired_report(readings),
            "model": model,
            "campaign_id": campaign_id}


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


def reading_row_both(name: str, reading) -> dict:
    """One reading in both projections, and the keys each one lost.

    Kept so the artifact shows the contrast on the whole `Reading` beside
    the contrast the frozen `reading_row` would have produced. The second is
    what the prior namespaces reported, and it is a 0.0 delta by arithmetic.
    """
    whole = reading.as_dict()
    row = replica.reading_row(name, reading)
    return {"whole_reading": whole,
            "reading_row_projection": row,
            "keys_reading_row_drops": sorted(set(whole) - set(row)),
            "paired_report_reads_from_row": sorted(
                k for k in (replica.NORMALIZED_REDUCTION, "action")
                if k not in row)}


def accounting(dsn: str, operation_ids: Sequence[str]) -> dict:
    """What the store recorded about exposure, cost and billing.

    `gateway_http._decode_usage` reads `billed` and `charge_units` out of the
    provider's `usage` object and treats a missing `billed` as absent rather
    than as `False`. This route emits `usage.cost` and neither of the two, so
    both are expected to be absent here. `usage_keys` is recorded raw so a
    reader can see the provider's own field names rather than take this
    campaign's word for the discrepancy.

    The schema is read rather than assumed. `receipts` carries
    `operation_id`, `outcome`, `content` and `provenance`; the response
    classification, the route error, the usage and the HTTP status all live
    inside `content`, which is the receipt's own record of what the gateway
    returned. A query naming a column the table does not have is a crash
    here, so the columns are listed from the table first and every one the
    accounting wants is asserted to exist.
    """
    from psycopg.rows import dict_row

    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT column_name FROM information_schema.columns"
                        " WHERE table_name = 'receipts'")
            columns = sorted(str(r["column_name"]) for r in cur.fetchall())
            cur.execute(
                "SELECT operation_id, outcome, content, provenance"
                " FROM receipts WHERE operation_id = ANY(%s)"
                " ORDER BY operation_id",
                (list(operation_ids),))
            rows = []
            for record in cur.fetchall():
                content = dict(record.get("content") or {})
                usage = content.get("usage")
                rows.append({
                    "operation_id": str(record.get("operation_id") or ""),
                    "outcome": str(record.get("outcome") or ""),
                    "response_class": str(content.get("response_class") or ""),
                    "route_error": content.get("route_error"),
                    "response_status": content.get("response_status"),
                    "response_received": content.get("response_received"),
                    "error": content.get("error"),
                    "usage": usage if isinstance(usage, dict) else None,
                    "provenance": str(record.get("provenance") or ""),
                })
            conn.commit()

    usage_keys, billed, charge = set(), set(), set()
    for row in rows:
        usage = row.get("usage")
        if not isinstance(usage, dict):
            continue
        usage_keys.update(str(k) for k in usage)
        for name, sink in (("billed", billed), ("charge_units", charge)):
            # Every value, null included. A field the provider never sent and
            # a field it sent as null are the same observation here, because
            # the receipt carries the adapter's normalised `Usage` and not
            # the provider's own payload, so a sink that recorded only
            # non-nulls would report "absent" for a field that is present
            # and null. The two must not be told apart by accident.
            sink.add(repr(usage.get(name)))
    classes: dict = {}
    for row in rows:
        key = row["response_class"] or row["outcome"]
        classes[key] = classes.get(key, 0) + 1
    return {
        "receipts": rows,
        "receipt_count": len(rows),
        "schema_columns_read": columns,
        "outcome_counts": classes,
        "route_error_counts": _counts({r["operation_id"]:
                                       str(r["route_error"])
                                       for r in rows if r["route_error"]}),
        "usage_keys_seen": sorted(usage_keys),
        "billed_values_seen": sorted(billed),
        "charge_units_values_seen": sorted(charge),
        "billed": "null on every receipt: the adapter read no `billed` key"
                  " from the provider's usage, and `Usage.billed is None` is"
                  " how it records that",
        "charge_units": "null on every receipt: the adapter read no"
                        " `charge_units` key from the provider's usage",
        "discrepancy": DISCREPANCY,
    }


DISCREPANCY = (
    "This route states its price as `usage.cost`, and the adapter reads"
    " `billed` and `charge_units`. The `usage` object stored on each receipt"
    " is the adapter's own normalised `Usage`, not the provider's raw"
    " payload, so it always carries all five keys and the three the route"
    " does not supply are `null` rather than missing. The consequence is"
    " that `billed` and `charge_units` are indistinguishable here from a"
    " provider that returned them as `null`, and `usage.cost` never reaches"
    " the store at all. Exposure is therefore counted in dispatches, token"
    " counts and estimated-budget units, and no cost figure is asserted"
    " from this route in either direction. It is not a statement that the"
    " route is free, and not a statement that it is not.")


def _counts(values: Mapping[str, str]) -> dict:
    out: dict = {}
    for value in values.values():
        out[value] = out.get(value, 0) + 1
    return out


def key_discrepancy(usage_keys: Sequence[str], usage_values: Mapping[str, set]) -> dict:
    """What the adapter reads, against what this route supplies.

    The `usage` on a receipt is the adapter's own normalised `Usage`, so its
    key set is fixed by the dataclass and says nothing about what the
    provider returned. Only the values say that: `billed` and
    `charge_units` are `null` on every receipt, which is what the adapter
    records when the provider's payload carried neither. The route's own
    `usage.cost` is not in this object at all, so it is stated here as a
    fact about the route and not presented as a value the store holds.
    """
    adapter_reads = {"input_tokens", "output_tokens", "charge_units",
                     "charge_scale", "billed"}
    null = {name for name, values in usage_values.items()
            if values and values <= {"None"}}
    return {
        "adapter_reads": sorted(adapter_reads),
        "receipt_usage_keys": sorted(usage_keys),
        "receipt_usage_is_adapter_normalised": True,
        "supplied_by_this_route": sorted(adapter_reads - null),
        "null_on_every_receipt": sorted(adapter_reads & null),
        "route_states_price_as": "usage.cost",
        "usage_cost_reaches_the_store": False,
        "discrepancy": DISCREPANCY,
    }


PROBE_ATTEMPTS = 4
"""How many times the route probe may re-ask before the campaign refuses.

The free route returned HTTP 502 on 9 of 12 requests in the most recent
campaign, and the probe here hit one on its first attempt. A 502 is a
provider failure the adapter itself marks retryable, not a refusal, so
re-asking is the adapter's advice rather than this campaign's tolerance. The
count is bounded so a persistently broken route costs four cheap calls and
then refuses, rather than spinning against a route that is down.
"""


def probe_route(dsn: str, *, campaign_id: str, allocation_id: str,
                gateway: Any, model: str,
                attempts: int = PROBE_ATTEMPTS) -> dict:
    """One cheap call to confirm the route before any effect is planned.

    The frozen `replica.probe_route` sends a `reasoning_effort`, which the
    chat surface refuses, so this sends the same request without one. Same
    operation id, same reservation, same receipt, same read of the settled
    text. The probe is a real dispatch of a bounded request rather than a
    listing, because `/v1/models` on this gateway does not attest a route.
    """
    from settlement import broker
    from settlement.common import ResultCode

    from psycopg.rows import dict_row

    from settlement import db

    tried = []
    for attempt in range(max(int(attempts), 1)):
        operation_id = "%s-%s" % (campaign_id,
                                  replica.PROBE_OPERATION_SUFFIX
                                  if not attempt else "%s-a%d" % (
                                      replica.PROBE_OPERATION_SUFFIX, attempt))
        ensured = broker.ensure_operation(
            dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
            payload={"model": model,
                     "messages": [{"role": "user",
                                   "content": "Reply with the single token: ok"}],
                     "max_output_tokens": replica.PROBE_MAX_TOKENS,
                     "deadline_ms": 60_000},
            allocation_id=allocation_id)
        if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            raise ContrastRefused("route probe not admitted: %s"
                                  % ensured.detail)
        broker.dispatch_operation(dsn, operation_id, launchers={},
                                  gateway=gateway)
        settled = replica._settled_text(dsn, operation_id)
        with db.connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT content FROM receipts"
                            " WHERE operation_id = %s", (operation_id,))
                receipt = cur.fetchone()
                conn.commit()
        content = dict((dict(receipt or {}).get("content") or {}))
        tried.append({"operation_id": operation_id,
                      "settled": settled is not None,
                      "outcome": str(content.get("response_class") or ""),
                      "error": content.get("error"),
                      "exposure_units": int(ensured.data.get("exposure") or 0)})
        if settled is not None:
            return {"operation_id": operation_id,
                    "max_output_tokens": replica.PROBE_MAX_TOKENS,
                    "settled": True,
                    "exposure_units": tried[-1]["exposure_units"],
                    "api": "chat", "route": "confirmed",
                    "attempts": tried}
    return {"operation_id": tried[-1]["operation_id"],
            "max_output_tokens": replica.PROBE_MAX_TOKENS,
            "settled": False,
            "exposure_units": sum(t["exposure_units"] for t in tried),
            "api": "chat", "route": "no-settled-response",
            "attempts": tried}


def build_report(bundle: Mapping[str, Any], *, key: str = "",
                 first_readings: Mapping[str, Any] | None = None) -> dict:
    """The artifact, assembled and checked for the key before it is written."""
    report = {
        "namespace": NAMESPACE,
        "independent_of": ["inv_r1_e2_scored", "inv_r1_e2_replica"],
        "is_replication_of": None,
        "campaign_kind": "first-contrast",
        "shares_with_prior_namespaces": {
            "mutable_store": False, "operation_ids": False,
            "allocation": False, "assessment_feedback": False,
            "evidence_directory": False,
            "frozen_contrast_body": False},
        "campaign_side_construction": {
            "what": "the relevant arm's experience records are built by"
                    " this module at EVIDENCE_MAX_QUERIES, not read from"
                    " e2_replication.measured_observations",
            "why": "the frozen arm grades ok-preserved on all three dev"
                   " software tasks at MAX_QUERIES=8, so its records differ"
                   " only in task_id and a contrast read off them measures a"
                   " constant",
            "what_it_is_not": "a repair. e2_replication is not edited, and"
                              " this campaign cannot change what the frozen"
                              " instrument measures. The same defect still"
                              " stands in e2_replication.",
            "size_matching": "held, and asserted before dispatch",
        },
        "freeze": bundle.get("freeze"),
        "cap_sheet": bundle.get("cap_sheet"),
        "evidence_budget": bundle.get("evidence_budget"),
        "graded_outcome_profiles": bundle.get("graded_outcome_profiles"),
        "size_matching": bundle.get("size_matching"),
        "treatment_input_audit": bundle.get("treatment_input_audit"),
        "instrument_qualification": bundle.get("instrument_qualification"),
        "reachability_census": bundle.get("reachability_census"),
        "acquired": bundle.get("acquired"),
        "dispatch_attempts": bundle.get("dispatch_attempts"),
        "null_dispatches": bundle.get("null_dispatches"),
        "readings": bundle.get("readings"),
        "paired": bundle.get("paired"),
        "sign_flip": bundle.get("sign_flip"),
        "census": bundle.get("census"),
        "accounting": bundle.get("accounting"),
        "key_discrepancy": bundle.get("key_discrepancy"),
        "model": bundle.get("model"),
        "campaign_id": bundle.get("campaign_id"),
        "agreement_with_first": (replica.agreement_with_first(
            bundle.get("readings") or {}, first_readings)
            if first_readings else None),
    }
    replica.assert_no_key_leaked([report], key)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="the E2 experience contrast over constructed evidence")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", default=None,
                        help="evidence directory; defaults to this"
                             " namespace's own, and a rerun writes to the"
                             " replication namespace's own rather than"
                             " over the first run's")
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--rerun", action="store_true",
                        help="mint a second namespace under R2, which is a"
                             " replication rather than a re-run")
    args = parser.parse_args(argv)

    config = replica.live_config()
    # `api` is `chat`, and not the frozen `responses`. Both constraints below
    # are the adapter's own and both are correct:
    #
    # * a frozen route can only be attested on `chat`, because `responses`
    #   publishes no provider and the adapter refuses to infer one from the
    #   requested model id (gateway_http.py:924);
    # * `chat` refuses a request carrying a `reasoning_effort`
    #   (gateway_http.py:960).
    #
    # `replica.acquire_one` always sends one, so the frozen dispatch and a
    # frozen route cannot both hold on this route. The resolution is the
    # dispatch, not the route: `acquire_one` above is the frozen path with
    # the effort omitted, which `broker._validate_model` accepts and which
    # the cap sheet records as `none-sent`.
    config = {**config, "api": "chat"}
    suffix = "r2" if args.rerun else ""
    token = "%s%s" % (NAMESPACE, suffix)
    from . import s09_run_isolation

    s09_run_isolation._checked_token(token)
    ids = {"study_root": s09_run_isolation.study_root_for(token),
           "campaign_id": s09_run_isolation.campaign_for(token),
           "allocation_id": s09_run_isolation.allocation_for(token)}
    replica.bind_authority(args.dsn, model=config["model"], token=token)
    gateway = replica.build_gateway(config)
    probe = probe_route(args.dsn, campaign_id=ids["campaign_id"],
                        allocation_id=ids["allocation_id"],
                        gateway=gateway, model=config["model"])
    if not probe["settled"]:
        print("route probe returned no settled response after %d attempts: %s"
              % (len(probe.get("attempts") or []), probe))
        return 3
    print("route probe confirmed on attempt %d of %d (%s)"
          % (len(probe["attempts"]), PROBE_ATTEMPTS, probe["operation_id"]))
    bundle = run_campaign(
        dsn=args.dsn, gateway=gateway, model=config["model"],
        allocation_id=ids["allocation_id"], campaign_id=ids["campaign_id"],
        max_output_tokens=args.max_output_tokens)
    readings = bundle.get("readings") or {}
    bundle["sign_flip"] = replica.sign_flip_p(
        [d for d in (bundle["paired"].get("relevant-minus-none") or {})
         .get("deltas") or []])
    ledger = accounting(args.dsn, [a["operation_id"] for a in
                                   bundle.get("acquired") or []])
    bundle["accounting"] = ledger
    bundle["key_discrepancy"] = key_discrepancy(
        ledger["usage_keys_seen"],
        {"billed": set(ledger["billed_values_seen"]),
         "charge_units": set(ledger["charge_units_values_seen"])})
    report = build_report(bundle, key=str(config["key"]),
                          first_readings=replica.read_first_namespace())
    if args.rerun:
        report["namespace"] = R2_NAMESPACE
        report["campaign_kind"] = "replication"
        report["is_replication_of"] = NAMESPACE
    out = Path(args.out or ("reports/evidence/"
                            + (R2_NAMESPACE if args.rerun else NAMESPACE)))
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8")
    print(json.dumps(report["paired"], indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
